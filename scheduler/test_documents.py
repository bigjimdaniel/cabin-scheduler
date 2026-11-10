import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import DocumentForm
from .models import Document


User = get_user_model()


class SharedDocumentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("fileadmin", "admin@example.com", "admin-password")
        cls.member = User.objects.create_user("reader", password="member-password")
        cls.staff = User.objects.create_user("staff", password="staff-password", is_staff=True)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=Path(self.directory.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def upload(self, name="guide.pdf", content=b"%PDF-1.4\nCabin guide"):
        return SimpleUploadedFile(name, content)

    def document(self, **kwargs):
        return Document.objects.create(
            title=kwargs.pop("title", "Cabin guide"),
            file=kwargs.pop("file", self.upload()), uploaded_by=self.admin, **kwargs,
        )

    def test_admin_uploads_published_document_and_metadata(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("document-create"), {
            "title": "Cabin guide", "description": "Read before arrival",
            "file": self.upload(), "is_published": "on",
            "uploaded_by": self.member.pk,
        })
        self.assertRedirects(response, reverse("document-list"))
        document = Document.objects.get()
        self.assertEqual(document.uploaded_by, self.admin)
        self.assertTrue(document.is_published)
        self.assertEqual(document.file_type, "PDF")
        self.assertEqual(document.file_size, len(b"%PDF-1.4\nCabin guide"))
        self.assertTrue(Path(document.file.path).exists())

    def test_admin_can_save_draft_and_edit_metadata_without_replacing_file(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("document-create"), {"title": "Draft", "file": self.upload()})
        self.assertEqual(response.status_code, 302)
        document = Document.objects.get()
        self.assertFalse(document.is_published)
        original_name = document.file.name
        response = self.client.post(reverse("document-update", args=[document.pk]), {
            "title": "Published guide", "description": "New description", "is_published": "on",
        })
        self.assertRedirects(response, reverse("document-list"))
        document.refresh_from_db()
        self.assertTrue(document.is_published)
        self.assertEqual(document.file.name, original_name)
        self.assertEqual(document.title, "Published guide")

    def test_member_can_only_list_and_download_published_files(self):
        published = self.document(title="Published guide")
        draft = self.document(title="Secret draft", is_published=False)
        self.client.force_login(self.member)
        response = self.client.get(reverse("document-list"))
        self.assertContains(response, published.title)
        self.assertNotContains(response, draft.title)
        self.assertNotContains(response, "Upload document")
        self.assertNotContains(response, reverse("document-update", args=[published.pk]))
        self.assertEqual(self.client.get(reverse("document-file", args=[draft.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("document-file", args=[draft.pk]), {"download": 1}).status_code, 404)

    def test_admin_can_list_and_download_drafts(self):
        draft = self.document(is_published=False)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("document-list"))
        self.assertContains(response, "Unpublished")
        self.assertContains(response, reverse("document-update", args=[draft.pk]))
        file_response = self.client.get(reverse("document-file", args=[draft.pk]))
        self.assertEqual(file_response.status_code, 200)
        file_response.close()

    def test_unpublishing_revokes_download_access(self):
        document = self.document()
        self.client.force_login(self.admin)
        self.client.post(reverse("document-update", args=[document.pk]), {"title": document.title})
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("document-file", args=[document.pk])).status_code, 404)

    def test_anonymous_cannot_access_files_or_management(self):
        document = self.document()
        for url in (
            reverse("document-list"), reverse("document-create"),
            reverse("document-update", args=[document.pk]),
            reverse("document-delete", args=[document.pk]),
            reverse("document-file", args=[document.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertEqual(self.client.post(url, {}).status_code, 302)
        self.assertEqual(self.client.get(document.file.url).status_code, 404)

    def test_member_and_staff_without_permissions_cannot_manage(self):
        document = self.document(is_published=False)
        for user in (self.member, self.staff):
            self.client.force_login(user)
            for url in (
                reverse("document-create"), reverse("document-update", args=[document.pk]),
                reverse("document-delete", args=[document.pk]),
            ):
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {"title": "Tampered"}).status_code, 403)
            self.assertEqual(self.client.get(reverse("document-file", args=[document.pk])).status_code, 404)
        document.refresh_from_db()
        self.assertEqual(document.title, "Cabin guide")

    def test_staff_permissions_are_checked_per_action(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="add_document"))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("document-create")).status_code, 200)
        response = self.client.post(reverse("document-create"), {"title": "New", "file": self.upload()})
        self.assertEqual(response.status_code, 302)
        document = Document.objects.get()
        self.assertEqual(self.client.get(reverse("document-update", args=[document.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("document-delete", args=[document.pk])).status_code, 403)

    def test_search_matches_title_description_and_filename_but_not_hidden_documents(self):
        first = self.document(title="Arrival guide", description="Door code instructions")
        second = self.document(title="Packing list", file=self.upload("packing.xlsx", b"Spreadsheet"))
        self.document(title="Hidden arrival guide", is_published=False)
        self.client.force_login(self.member)
        for term, expected in (("arrival", first), ("Door code", first), ("packing.xlsx", second)):
            with self.subTest(term=term):
                response = self.client.get(reverse("document-list"), {"q": term})
                self.assertEqual(list(response.context["documents"]), [expected])
        self.assertContains(self.client.get(reverse("document-list"), {"q": "no matches"}), "No documents match")

    def test_pagination_preserves_search_query(self):
        for index in range(21):
            self.document(title=f"Guide {index:02d}")
        self.client.force_login(self.member)
        response = self.client.get(reverse("document-list"), {"q": "Guide"})
        self.assertEqual(len(response.context["documents"]), 20)
        self.assertContains(response, "q=Guide&amp;page=2")
        second = self.client.get(reverse("document-list"), {"q": "Guide", "page": 2})
        self.assertEqual(len(second.context["documents"]), 1)

    def test_pdf_and_images_preview_but_office_files_are_attachments(self):
        self.client.force_login(self.member)
        for name, content_type, disposition in (
            ("guide.PDF", "application/pdf", "inline"),
            ("map.png", "image/png", "inline"),
            ("rules.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "attachment"),
            ("inventory.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "attachment"),
            ("notes.txt", "text/plain", "attachment"),
        ):
            with self.subTest(name=name):
                document = self.document(file=self.upload(name))
                response = self.client.get(reverse("document-file", args=[document.pk]))
                self.assertEqual(response.headers["Content-Type"], content_type)
                self.assertIn(disposition, response.headers["Content-Disposition"])
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["Cache-Control"], "private, no-store")
                response.close()
        response = self.client.get(reverse("document-file", args=[document.pk]), {"download": 1})
        self.assertIn("attachment", response.headers["Content-Disposition"])
        response.close()

    def test_missing_files_show_unavailable_and_return_404(self):
        document = self.document()
        document.file.storage.delete(document.file.name)
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("document-list")), "File unavailable")
        self.assertEqual(self.client.get(reverse("document-file", args=[document.pk])).status_code, 404)

    def test_upload_validation_rejects_unsupported_and_empty_files(self):
        self.client.force_login(self.admin)
        for filename, content in (("bad.html", b"<script>"), ("bad.exe", b"exe"), ("bad.svg", b"<svg>"), ("empty.pdf", b"")):
            with self.subTest(filename=filename):
                response = self.client.post(reverse("document-create"), {"title": "Invalid", "file": self.upload(filename, content)})
                self.assertEqual(response.status_code, 200)
                self.assertIn("file", response.context["form"].errors)
        self.assertFalse(Document.objects.exists())
        self.assertEqual(list(Path(self.directory.name).rglob("*")), [])

    @override_settings(DOCUMENT_MAX_UPLOAD_BYTES=10)
    def test_upload_size_limit_is_enforced_on_site_and_admin_forms(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("document-create"), {"title": "Large", "file": self.upload(content=b"x" * 11)})
        self.assertIn("file", response.context["form"].errors)
        response = self.client.post(reverse("admin:scheduler_document_add"), {"title": "Large", "file": self.upload(content=b"x" * 11)})
        self.assertIn("file", response.context["adminform"].form.errors)
        exact_limit = DocumentForm({"title": "Fits"}, {"file": self.upload(content=b"x" * 10)})
        self.assertTrue(exact_limit.is_valid(), exact_limit.errors)
        self.assertFalse(Document.objects.exists())

    def test_supported_extensions_accept_uppercase_and_common_formats(self):
        for extension in ("doc", "DOCX", "xls", "xlsx", "ppt", "pptx", "pdf", "txt", "csv", "jpg", "jpeg", "png", "gif", "webp"):
            with self.subTest(extension=extension):
                form = DocumentForm({"title": "File"}, {"file": self.upload(f"guide.{extension}")})
                self.assertTrue(form.is_valid(), form.errors)

    def test_replacement_removes_old_file_after_commit_and_preserves_uploader(self):
        document = self.document()
        old_path = Path(document.file.path)
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("document-update", args=[document.pk]), {
                "title": "Revised guide", "file": self.upload("replacement.pdf", b"%PDF-new"), "is_published": "on",
            })
            self.assertTrue(old_path.exists())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(old_path.exists())
        document.refresh_from_db()
        self.assertEqual(document.uploaded_by, self.admin)
        self.assertTrue(Path(document.file.path).exists())

    def test_invalid_replacement_preserves_original_file(self):
        document = self.document()
        old_name = document.file.name
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("document-update", args=[document.pk]), {"title": "Changed", "file": self.upload("bad.exe")})
        self.assertIn("file", response.context["form"].errors)
        document.refresh_from_db()
        self.assertEqual(document.file.name, old_name)
        self.assertTrue(Path(document.file.path).exists())

    def test_delete_requires_confirmation_post_and_removes_stored_file(self):
        document = self.document()
        old_path = Path(document.file.path)
        self.client.force_login(self.admin)
        url = reverse("document-delete", args=[document.pk])
        self.assertContains(self.client.get(url), "Delete document?")
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(url), reverse("document-list"))
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
        self.assertFalse(old_path.exists())

    def test_bulk_deletion_cleans_up_files(self):
        first = self.document()
        second = self.document()
        paths = [Path(first.file.path), Path(second.file.path)]
        with self.captureOnCommitCallbacks(execute=True):
            Document.objects.all().delete()
        self.assertTrue(all(not path.exists() for path in paths))

    def test_rollback_does_not_remove_original_file(self):
        document = self.document()
        old_path = Path(document.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    document.delete()
                    raise ValueError("Roll back deletion")
            except ValueError:
                pass
        self.assertTrue(old_path.exists())
        self.assertEqual(Document.objects.count(), 1)

    def test_shared_storage_reference_is_not_deleted_until_last_record(self):
        first = self.document()
        second = self.document(file=first.file.name)
        path = Path(first.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            second.delete()
        self.assertFalse(path.exists())

    def test_csrf_enforced_management_forms(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        document = self.document()
        for url in (reverse("document-create"), reverse("document-update", args=[document.pk]), reverse("document-delete", args=[document.pk])):
            self.assertEqual(client.post(url, {}).status_code, 403)
            client.get(url)
        response = client.post(reverse("document-create"), {
            "title": "Browser upload", "file": self.upload(), "is_published": "on",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }, HTTP_ORIGIN="http://testserver")
        self.assertEqual(response.status_code, 302)
