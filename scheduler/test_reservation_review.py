from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from .models import BlackoutRange, Cabin, Reservation


User = get_user_model()


class ReservationReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("reviewadmin", "owner@example.com", "admin-password")
        cls.member = User.objects.create_user("requester", password="member-password")
        cls.staff = User.objects.create_user("reviewstaff", is_staff=True)
        cls.cabin = Cabin.objects.get(slug="main-cabin")

    def setUp(self):
        self.reservation = Reservation.objects.create(
            cabin=self.cabin, user=self.member, guest_name="Family Guest",
            start_date=date(2027, 4, 10), end_date=date(2027, 4, 13),
            notes="Arriving late on Friday.",
        )
        self.url = reverse("reservation-review", args=[self.reservation.pk])

    def test_review_screen_shows_details_and_explicit_decision_buttons(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        for text in ("Family Guest", "requester", "Arriving late", "Check-in", "Check-out", "Approve request", "Reject request", "Only administrators"):
            self.assertContains(response, text)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
        self.assertIsNone(self.reservation.decided_at)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_approval_saves_actor_timestamp_and_optional_note(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {"decision": "approve", "admin_notes": "Confirmed with family."})
        self.assertRedirects(response, self.url)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(self.reservation.decided_by, self.admin)
        self.assertIsNotNone(self.reservation.decided_at)
        self.assertEqual(self.reservation.admin_notes, "Confirmed with family.")
        response = self.client.get(self.url)
        self.assertContains(response, "Confirmed with family.")
        self.assertContains(response, "Reviewed by")
        self.assertNotContains(response, 'name="decision"')
        calendar = self.client.get(reverse("calendar"), {"year": 2027, "month": 4})
        days = [day for week in calendar.context["weeks"] for day in week]
        self.assertEqual(next(day for day in days if day.day == date(2027, 4, 10)).state, "approved")

    def test_rejection_with_no_note_saves_decision(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(self.url, {"decision": "reject"}), self.url)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.REJECTED)
        self.assertEqual(self.reservation.decided_by, self.admin)
        self.assertEqual(self.reservation.admin_notes, "")
        self.assertIsNotNone(self.reservation.decided_at)

    def test_conflict_with_approved_stay_prevents_approval_but_allows_rejection(self):
        Reservation.objects.create(cabin=self.cabin, user=self.member, start_date=date(2027, 4, 11), end_date=date(2027, 4, 12), status=Reservation.Status.APPROVED)
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {"decision": "approve", "admin_notes": "Do not persist"})
        self.assertContains(response, "overlaps with an approved reservation")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
        self.assertEqual(self.reservation.admin_notes, "")
        self.assertIsNone(self.reservation.decided_by)
        self.assertRedirects(self.client.post(self.url, {"decision": "reject"}), self.url)

    def test_blackout_prevents_approval(self):
        BlackoutRange.objects.create(cabin=self.cabin, start_date=date(2027, 4, 11), end_date=date(2027, 4, 14), reason="Maintenance")
        self.client.force_login(self.admin)
        self.assertContains(self.client.post(self.url, {"decision": "approve"}), "overlaps with a blackout range")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
        self.assertIsNone(self.reservation.decided_at)

    def test_anonymous_member_and_unprivileged_staff_cannot_review_or_decide(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, {"decision": "approve"}).status_code, 302)
        for user in (self.member, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, {"decision": "approve"}).status_code, 403)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

    def test_authorized_staff_can_review(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="change_reservation"))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertRedirects(self.client.post(self.url, {"decision": "approve"}), self.url)

    def test_missing_or_invalid_decision_and_overlong_notes_are_rejected(self):
        self.client.force_login(self.admin)
        for payload in ({}, {"decision": "cancel"}, {"decision": "approve", "admin_notes": "x" * 5001}):
            response = self.client.post(self.url, payload)
            self.assertTrue(response.context["form"].errors)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

    def test_completed_and_cancelled_requests_cannot_be_overwritten(self):
        self.client.force_login(self.admin)
        for status in (Reservation.Status.APPROVED, Reservation.Status.REJECTED, Reservation.Status.CANCELLED):
            Reservation.objects.filter(pk=self.reservation.pk).update(status=status, admin_notes="Original note")
            response = self.client.post(self.url, {"decision": "reject", "admin_notes": "Changed"})
            self.assertContains(response, "no longer pending")
            self.reservation.refresh_from_db()
            self.assertEqual(self.reservation.status, status)
            self.assertEqual(self.reservation.admin_notes, "Original note")

    def test_duplicate_or_stale_submissions_preserve_first_decision(self):
        self.client.force_login(self.admin)
        self.client.get(self.url)
        self.client.post(self.url, {"decision": "approve", "admin_notes": "First"})
        self.reservation.refresh_from_db()
        decided_at = self.reservation.decided_at
        self.assertContains(self.client.post(self.url, {"decision": "reject", "admin_notes": "Second"}), "no longer pending")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(self.reservation.admin_notes, "First")
        self.assertEqual(self.reservation.decided_at, decided_at)

    def test_pending_requests_appear_first_and_review_links_are_admin_only(self):
        earlier = Reservation.objects.create(cabin=self.cabin, user=self.member, start_date=date(2027, 1, 1), end_date=date(2027, 1, 2), status=Reservation.Status.APPROVED)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reservation-list"))
        self.assertEqual(list(response.context["reservations"]), [self.reservation, earlier])
        self.assertContains(response, self.url)
        self.assertContains(response, "Review request")
        self.assertContains(response, "View decision")
        self.client.force_login(self.member)
        response = self.client.get(reverse("reservation-list"))
        self.assertNotContains(response, self.url)
        self.assertNotContains(response, "Review request")

    def test_private_admin_notes_are_not_exposed_to_requester(self):
        self.reservation.admin_notes = "Private conversation with administrator"
        self.reservation.save()
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse("reservation-list")), self.reservation.admin_notes)

    def test_csrf_enforced_browser_round_trip(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url, {"decision": "approve"}).status_code, 403)
        page = client.get(self.url)
        self.assertNotEqual(page.headers.get("Referrer-Policy"), "no-referrer")
        response = client.post(self.url, {
            "decision": "approve", "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }, HTTP_ORIGIN="http://testserver")
        self.assertRedirects(response, self.url)

    def test_admin_has_explicit_review_links(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("admin:scheduler_reservation_changelist")), self.url)
        self.assertContains(self.client.get(reverse("admin:scheduler_reservation_change", args=[self.reservation.pk])), "Review and decide")

    def test_missing_request_is_404_and_get_does_not_accept_actions(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("reservation-review", args=[999999])).status_code, 404)
        self.client.get(self.url, {"decision": "approve"})
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
