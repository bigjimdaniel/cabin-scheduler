import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .invitations import send_invitation
from .models import Invitation


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="https://cabin.example")
class InvitationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("owner", "owner@example.com", "owner-password")
        cls.guest = User.objects.create_user("existing", "existing@example.com", "existing-password")

    def send(self, email="guest@example.com"):
        invitation = send_invitation(email=email, invited_by=self.admin, base_url="https://cabin.example")
        url = re.search(r"https://\S+/accounts/enroll/\S+/", mail.outbox[-1].body).group()
        return invitation, urlsplit(url).path

    def payload(self, **kwargs):
        return {"username": "newguest", "password1": "Cabin!92-Blue-Sky", "password2": "Cabin!92-Blue-Sky", **kwargs}

    def test_admin_sends_invitation_without_creating_account(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:scheduler_invitation_add"), {"email": "Guest@Example.com", "delivery": "email"})
        self.assertRedirects(response, reverse("admin:scheduler_invitation_changelist"))
        self.assertEqual(User.objects.count(), 2)
        invitation = Invitation.objects.get(email="guest@example.com")
        self.assertEqual(invitation.invited_by, self.admin)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["guest@example.com"])
        self.assertIn("https://cabin.example/accounts/enroll/", mail.outbox[0].body)
        token = re.search(r"/enroll/([^/]+)/", mail.outbox[0].body).group(1)
        self.assertNotEqual(invitation.token_digest, token)
        self.assertNotIn(token, str(invitation.__dict__))

    def test_enrollment_creates_account_with_invited_email_and_no_admin_privileges(self):
        invitation, url = self.send()
        self.assertContains(self.client.get(url), "guest@example.com")
        invitation.refresh_from_db()
        self.assertIsNone(invitation.accepted_at)
        response = self.client.post(url, self.payload(email="attacker@example.com", is_staff="1"))
        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(username="newguest")
        self.assertEqual(user.email, invitation.email)
        self.assertTrue(user.check_password("Cabin!92-Blue-Sky"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.assertTrue(self.client.login(username="newguest", password="Cabin!92-Blue-Sky"))

    def test_invitation_cannot_be_reused(self):
        _, url = self.send()
        self.client.post(url, self.payload())
        response = self.client.post(url, self.payload(username="another"))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="another").exists())

    def test_expired_revoked_and_unknown_links_are_rejected(self):
        invitation, url = self.send()
        Invitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(url, self.payload()).status_code, 400)
        invitation.delete()
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.get(reverse("enroll", kwargs={"token": "made-up"})).status_code, 400)
        self.assertFalse(User.objects.filter(username="newguest").exists())

    def test_resend_replaces_old_link(self):
        invitation, old_url = self.send()
        replacement, new_url = self.send()
        self.assertEqual(invitation.pk, replacement.pk)
        self.assertNotEqual(old_url, new_url)
        self.assertEqual(self.client.get(old_url).status_code, 400)
        self.assertEqual(self.client.get(new_url).status_code, 200)

    def test_password_and_username_validation_leave_invitation_available(self):
        invitation, url = self.send()
        for payload in (
            self.payload(password1="short", password2="short"),
            self.payload(password2="does-not-match"),
            self.payload(username="existing"),
            self.payload(username="invalid username!"),
        ):
            with self.subTest(payload=payload["username"]):
                response = self.client.post(url, payload)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.accepted_at)

    def test_existing_email_is_rejected_case_insensitively(self):
        with self.assertRaises(ValidationError):
            self.send("EXISTING@example.com")
        self.assertFalse(Invitation.objects.exists())

    def test_account_created_since_invite_prevents_enrollment(self):
        invitation, url = self.send()
        User.objects.create_user("alreadycreated", "GUEST@example.com", "some-password")
        response = self.client.post(url, self.payload())
        self.assertContains(response, "already exists")
        self.assertFalse(User.objects.filter(username="newguest").exists())
        invitation.refresh_from_db()
        self.assertIsNone(invitation.accepted_at)

    def test_only_authorized_admin_can_send(self):
        url = reverse("admin:scheduler_invitation_add")
        self.assertEqual(self.client.post(url, {"email": "guest@example.com", "delivery": "email"}).status_code, 302)
        self.client.force_login(self.guest)
        self.assertEqual(self.client.post(url, {"email": "guest@example.com", "delivery": "email"}).status_code, 302)
        self.guest.is_staff = True
        self.guest.save()
        self.assertEqual(self.client.post(url, {"email": "guest@example.com", "delivery": "email"}).status_code, 403)
        self.assertFalse(Invitation.objects.exists())

    def test_failed_delivery_is_shown_and_can_be_retried(self):
        self.client.force_login(self.admin)
        with patch("scheduler.invitations.send_mail", side_effect=OSError("connection failed")):
            response = self.client.post(reverse("admin:scheduler_invitation_add"), {"email": "guest@example.com", "delivery": "email"})
        self.assertContains(response, "could not be sent")
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(self.client.post(reverse("admin:scheduler_invitation_add"), {"email": "guest@example.com", "delivery": "email"}).status_code, 302)

    def test_failed_resend_preserves_old_link(self):
        _, old_url = self.send()
        with patch("scheduler.invitations.send_mail", return_value=0), self.assertRaises(OSError):
            self.send()
        self.assertEqual(self.client.get(old_url).status_code, 200)

    def test_csrf_is_required_for_enrollment_and_admin_send(self):
        _, url = self.send()
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(url, self.payload()).status_code, 403)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("admin:scheduler_invitation_add"), {"email": "another@example.com"}).status_code, 403)

    def test_enrollment_page_is_not_cached_and_does_not_leak_referrer(self):
        _, url = self.send()
        response = self.client.get(url)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_backend_does_not_claim_email_was_delivered(self):
        self.client.force_login(self.admin)
        with patch("scheduler.invitations.send_mail", return_value=1):
            response = self.client.post(reverse("admin:scheduler_invitation_add"), {"email": "guest@example.com", "delivery": "email"}, follow=True)
        self.assertContains(response, "written to the server console")

    def test_default_admin_flow_creates_copyable_link_without_email(self):
        self.client.force_login(self.admin)
        with patch("scheduler.invitations.send_mail", side_effect=AssertionError("Email must not be used")):
            response = self.client.post(reverse("admin:scheduler_invitation_add"), {"email": "copy@example.com"})
        self.assertContains(response, "No email was sent")
        self.assertContains(response, "Copy link")
        url = response.context["enrollment_url"]
        self.assertTrue(url.startswith("https://cabin.example/accounts/enroll/"))
        invitation = Invitation.objects.get(email="copy@example.com")
        self.assertNotIn(urlsplit(url).path.split("/")[-2], str(invitation.__dict__))
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        self.assertNotIn(url, str(self.client.session.items()))
        from django.contrib.admin.models import LogEntry
        self.assertNotIn(url, str(list(LogEntry.objects.values())))
        self.assertRedirects(self.client.post(urlsplit(url).path, self.payload()), reverse("login"))
        self.assertEqual(User.objects.get(username="newguest").email, "copy@example.com")

    def test_copy_flow_replaces_link_and_rejects_existing_account(self):
        self.client.force_login(self.admin)
        admin_url = reverse("admin:scheduler_invitation_add")
        first = self.client.post(admin_url, {"email": "copy@example.com", "delivery": "link"})
        old_url = urlsplit(first.context["enrollment_url"]).path
        second = self.client.post(admin_url, {"email": "copy@example.com", "delivery": "link"})
        self.assertEqual(Invitation.objects.filter(email="copy@example.com").count(), 1)
        self.assertEqual(self.client.get(old_url).status_code, 400)
        self.assertEqual(self.client.get(urlsplit(second.context["enrollment_url"]).path).status_code, 200)
        rejected = self.client.post(admin_url, {"email": "EXISTING@example.com", "delivery": "link"})
        self.assertContains(rejected, "already exists")
        self.assertIsNone(rejected.context.get("enrollment_url"))

    @override_settings(SITE_URL="")
    def test_copy_link_uses_request_origin_when_site_url_is_unset(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:scheduler_invitation_add"), {"email": "copy@example.com"}, secure=True)
        self.assertTrue(response.context["enrollment_url"].startswith("https://testserver/accounts/enroll/"))

    def test_copy_link_requires_admin_permission_and_valid_delivery_choice(self):
        url = reverse("admin:scheduler_invitation_add")
        self.client.force_login(self.guest)
        self.assertEqual(self.client.post(url, {"email": "copy@example.com", "delivery": "link"}).status_code, 302)
        self.client.force_login(self.admin)
        response = self.client.post(url, {"email": "copy@example.com", "delivery": "unknown"})
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Invitation.objects.exists())

    def test_admin_and_enrollment_forms_work_with_browser_csrf_checks(self):
        admin_client = Client(enforce_csrf_checks=True)
        admin_client.force_login(self.admin)
        admin_url = reverse("admin:scheduler_invitation_add")
        page = admin_client.get(admin_url)
        # no-referrer on these pages causes browsers to send Origin: null
        # for form POSTs, even when the cookie and CSRF token are correct.
        self.assertEqual(page.headers["Referrer-Policy"], "same-origin")
        created = admin_client.post(admin_url, {
            "email": "browser@example.com", "delivery": "link",
            "csrfmiddlewaretoken": admin_client.cookies["csrftoken"].value,
        }, HTTP_ORIGIN="http://testserver")
        self.assertContains(created, "Copy link")

        guest_client = Client(enforce_csrf_checks=True)
        enroll_url = urlsplit(created.context["enrollment_url"]).path
        page = guest_client.get(enroll_url)
        self.assertEqual(page.headers["Referrer-Policy"], "same-origin")
        enrolled = guest_client.post(enroll_url, {
            **self.payload(),
            "csrfmiddlewaretoken": guest_client.cookies["csrftoken"].value,
        }, HTTP_ORIGIN="http://testserver")
        self.assertRedirects(enrolled, reverse("login"))
        self.assertEqual(User.objects.get(username="newguest").email, "browser@example.com")

    def test_null_origin_is_still_rejected_with_valid_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        url = reverse("admin:scheduler_invitation_add")
        client.get(url)
        response = client.post(url, {
            "email": "browser@example.com", "delivery": "link",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }, HTTP_ORIGIN="null")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Invitation.objects.exists())
