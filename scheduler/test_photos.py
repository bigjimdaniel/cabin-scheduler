from io import BytesIO
from pathlib import Path
import tempfile

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import CarouselPhotoForm
from .models import CarouselPhoto


User = get_user_model()


class CarouselPhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("photoadmin", "photos@example.com", "admin-password")
        cls.member = User.objects.create_user("photomember")
        cls.staff = User.objects.create_user("photostaff", is_staff=True)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(MEDIA_ROOT=Path(self.directory.name))
        self.override.enable()
        self.addCleanup(self.override.disable)

    def image(self, name="photo.png", format="PNG"):
        buffer = BytesIO()
        Image.new("RGB", (40, 30), "green").save(buffer, format=format)
        return SimpleUploadedFile(name, buffer.getvalue())

    def create(self, **kwargs):
        return CarouselPhoto.objects.create(
            title=kwargs.pop("title", "New cabin photo"),
            image=self.image(), position=10, **kwargs,
        )

    def test_original_five_photos_are_seeded_and_publicly_accessible(self):
        photos = list(CarouselPhoto.objects.all())
        self.assertEqual(len(photos), 5)
        self.assertEqual([p.legacy_image for p in photos], [f"img/home-carousel/cabin{i}.jpg" for i in range(1, 6)])
        response = self.client.get(reverse("home"))
        self.assertEqual(list(response.context["carousel_photos"]), photos)
        self.assertContains(response, "Show photo 5")
        for photo in photos:
            image = self.client.get(reverse("photo-image", args=[photo.pk]))
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.headers["Content-Type"], "image/jpeg")
            self.assertGreater(len(b"".join(image.streaming_content)), 0)

    def test_admin_can_upload_and_photo_is_appended_to_homepage(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("photo-create"), {
            "title": "Lake view", "alt_text": "Lake seen from the porch", "image": self.image(), "is_active": "on",
        })
        self.assertRedirects(response, reverse("photo-list"))
        photo = CarouselPhoto.objects.get(title="Lake view")
        self.assertEqual(photo.position, 6)
        self.assertTrue(Path(photo.image.path).exists())
        home = self.client.get(reverse("home"))
        self.assertEqual(list(home.context["carousel_photos"])[-1], photo)
        self.assertContains(home, 'alt="Lake view"')

    def test_staff_permissions_are_required_for_each_management_action(self):
        photo = CarouselPhoto.objects.first()
        urls = [reverse("photo-list"), reverse("photo-create"), reverse("photo-update", args=[photo.pk]), reverse("photo-delete", args=[photo.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        for user in (self.member, self.staff):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(reverse("photo-action", args=[photo.pk]), {"action": "hide"}).status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(codename="view_carouselphoto"))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("photo-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("photo-create")).status_code, 403)

    def test_hidden_photos_are_not_shown_publicly_but_admin_can_preview(self):
        photo = self.create(is_active=False)
        url = reverse("photo-image", args=[photo.pk])
        self.assertNotContains(self.client.get(reverse("home")), url)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        response.close()
        self.assertContains(self.client.get(reverse("photo-list")), "Hidden")

    def test_show_and_hide_actions_take_effect_immediately(self):
        photo = self.create()
        self.client.force_login(self.admin)
        action_url = reverse("photo-action", args=[photo.pk])
        self.assertRedirects(self.client.post(action_url, {"action": "hide"}), reverse("photo-list"))
        photo.refresh_from_db()
        self.assertFalse(photo.is_active)
        self.assertRedirects(self.client.post(action_url, {"action": "show"}), reverse("photo-list"))
        photo.refresh_from_db()
        self.assertTrue(photo.is_active)
        self.assertEqual(self.client.get(action_url).status_code, 405)
        self.assertEqual(self.client.post(action_url, {"action": "bad"}).status_code, 400)

    def test_reordering_moves_one_step_and_handles_duplicate_positions(self):
        self.client.force_login(self.admin)
        photos = list(CarouselPhoto.objects.all())
        CarouselPhoto.objects.all().update(position=1)
        self.client.post(reverse("photo-action", args=[photos[2].pk]), {"action": "up"})
        expected = [photos[0], photos[2], photos[1], photos[3], photos[4]]
        self.assertEqual(list(CarouselPhoto.objects.all()), expected)
        self.assertEqual(list(self.client.get(reverse("home")).context["carousel_photos"]), expected)
        self.client.post(reverse("photo-action", args=[photos[2].pk]), {"action": "down"})
        self.assertEqual(list(CarouselPhoto.objects.all()), photos)
        self.client.post(reverse("photo-action", args=[photos[0].pk]), {"action": "up"})
        self.client.post(reverse("photo-action", args=[photos[-1].pk]), {"action": "down"})
        self.assertEqual(list(CarouselPhoto.objects.all()), photos)

    def test_empty_and_single_photo_carousels_render_correctly(self):
        CarouselPhoto.objects.all().update(is_active=False)
        self.assertNotContains(self.client.get(reverse("home")), "data-carousel-slide")
        photo = CarouselPhoto.objects.first()
        photo.is_active = True
        photo.save()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "data-carousel-slide", count=1)
        self.assertNotContains(response, "data-carousel-indicator")

    def test_valid_photo_is_required(self):
        for data, files, field in (
            ({"title": "A", "alt_text": "A"}, {}, "image"),
            ({"title": "A", "alt_text": "A"}, {"image": SimpleUploadedFile("fake.jpg", b"not an image")}, "image"),
            ({"title": "A", "alt_text": "A"}, {"image": self.image("wrong.jpg")}, "image"),
            ({"title": "A", "alt_text": "A"}, {"image": SimpleUploadedFile("bad.svg", b"<svg/>")}, "image"),
        ):
            form = CarouselPhotoForm(data, files)
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_upload_needs_no_title_or_alt_text_and_uses_filename_in_manager(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("photo-create"), {"image": self.image("untitled.png"), "is_active": "on"})
        self.assertRedirects(response, reverse("photo-list"))
        photo = CarouselPhoto.objects.get(image__endswith="untitled.png")
        self.assertEqual(photo.title, "")
        self.assertEqual(photo.display_title, "untitled.png")
        self.assertContains(self.client.get(reverse("photo-list")), "untitled.png")
        self.assertContains(self.client.get(reverse("home")), 'alt="Cabin photo"')

    def test_photo_forms_hide_alt_text_and_label_title_optional(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("photo-create"))
        self.assertContains(response, "Title (optional)")
        self.assertNotContains(response, 'name="alt_text"')
        self.assertFalse(response.context["form"].fields["title"].required)
        response = self.client.get(reverse("admin:scheduler_carouselphoto_add"))
        self.assertNotContains(response, 'name="alt_text"')
        self.assertFalse(response.context["adminform"].form.fields["title"].required)

    def test_title_can_be_cleared_without_replacing_photo(self):
        photo = self.create()
        original_image = photo.image.name
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse("photo-update", args=[photo.pk]), {"title": "", "is_active": "on"}), reverse("photo-list"))
        photo.refresh_from_db()
        self.assertEqual(photo.title, "")
        self.assertEqual(photo.image.name, original_image)
        self.assertTrue(photo.display_title)
        self.assertEqual(photo.alt_text, "Cabin photo")

    @override_settings(CAROUSEL_MAX_UPLOAD_BYTES=10)
    def test_photo_size_limit_is_enforced(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("photo-create"), {"title": "Large", "alt_text": "Large photo", "image": self.image()})
        self.assertIn("image", response.context["form"].errors)
        self.assertEqual(CarouselPhoto.objects.count(), 5)

    def test_supported_actual_image_formats(self):
        for name, format in (("photo.JPG", "JPEG"), ("photo.png", "PNG"), ("photo.webp", "WEBP")):
            form = CarouselPhotoForm({"title": "Photo", "alt_text": "A cabin"}, {"image": self.image(name, format)})
            self.assertTrue(form.is_valid(), form.errors)

    def test_legacy_photo_can_be_edited_without_reupload_and_replaced(self):
        photo = CarouselPhoto.objects.first()
        self.client.force_login(self.admin)
        url = reverse("photo-update", args=[photo.pk])
        self.assertRedirects(self.client.post(url, {"title": "New title", "alt_text": "New description", "is_active": "on"}), reverse("photo-list"))
        photo.refresh_from_db()
        self.assertEqual(photo.title, "New title")
        self.assertTrue(photo.legacy_image)
        self.assertFalse(photo.image)
        self.assertRedirects(self.client.post(url, {"title": "Replaced", "alt_text": "Replacement", "image": self.image(), "is_active": "on"}), reverse("photo-list"))
        photo.refresh_from_db()
        self.assertTrue(photo.image)
        response = self.client.get(reverse("photo-image", args=[photo.pk]))
        self.assertEqual(response.headers["Content-Type"], "image/png")
        response.close()

    def test_replacing_upload_cleans_old_file_only_after_commit(self):
        photo = self.create()
        old_path = Path(photo.image.path)
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("photo-update", args=[photo.pk]), {"title": "Replaced", "alt_text": "New photo", "image": self.image("replacement.png"), "is_active": "on"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(old_path.exists())
        self.assertFalse(old_path.exists())
        photo.refresh_from_db()
        self.assertTrue(Path(photo.image.path).exists())

    def test_invalid_replacement_preserves_original_upload(self):
        photo = self.create()
        old_path = Path(photo.image.path)
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("photo-update", args=[photo.pk]), {"title": "Invalid", "alt_text": "Photo", "image": SimpleUploadedFile("bad.jpg", b"bad")})
        self.assertEqual(response.status_code, 200)
        photo.refresh_from_db()
        self.assertEqual(Path(photo.image.path), old_path)
        self.assertTrue(old_path.exists())

    def test_confirmed_delete_removes_upload_and_bulk_delete_keeps_static_assets(self):
        photo = self.create()
        path = Path(photo.image.path)
        self.client.force_login(self.admin)
        url = reverse("photo-delete", args=[photo.pk])
        self.assertContains(self.client.get(url), "Delete photo?")
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(url), reverse("photo-list"))
        self.assertFalse(path.exists())
        from django.contrib.staticfiles import finders
        original = Path(finders.find("img/home-carousel/cabin1.jpg"))
        with self.captureOnCommitCallbacks(execute=True):
            CarouselPhoto.objects.all().delete()
        self.assertTrue(original.exists())

    def test_rolled_back_deletion_preserves_image(self):
        photo = self.create()
        path = Path(photo.image.path)
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    photo.delete()
                    raise ValueError("rollback")
            except ValueError:
                pass
        self.assertTrue(path.exists())

    def test_shared_image_is_only_deleted_when_last_reference_removed(self):
        first = self.create()
        second = CarouselPhoto.objects.create(title="Shared", image=first.image.name)
        path = Path(first.image.path)
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            second.delete()
        self.assertFalse(path.exists())

    def test_missing_or_arbitrary_image_paths_cannot_be_served(self):
        photo = self.create()
        photo.image.storage.delete(photo.image.name)
        self.assertEqual(self.client.get(reverse("photo-image", args=[photo.pk])).status_code, 404)
        photo.image = ""
        photo.legacy_image = "../../.env"
        photo.save()
        self.assertEqual(self.client.get(reverse("photo-image", args=[photo.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("photo-image", args=[999999])).status_code, 404)

    def test_admin_forms_and_authenticated_preview_do_not_expose_public_media_urls(self):
        photo = self.create(is_active=False)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:scheduler_carouselphoto_change", args=[photo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("photo-image", args=[photo.pk]))
        self.assertNotContains(response, photo.image.url)

    def test_csrf_enforced_upload_and_actions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        photo = CarouselPhoto.objects.first()
        url = reverse("photo-action", args=[photo.pk])
        self.assertEqual(client.post(url, {"action": "hide"}).status_code, 403)
        client.get(reverse("photo-list"))
        self.assertRedirects(client.post(url, {"action": "hide", "csrfmiddlewaretoken": client.cookies["csrftoken"].value}, HTTP_ORIGIN="http://testserver"), reverse("photo-list"))
        response = client.post(reverse("photo-create"), {"title": "Browser photo", "alt_text": "Cabin", "image": self.image(), "csrfmiddlewaretoken": client.cookies["csrftoken"].value}, HTTP_ORIGIN="http://testserver")
        self.assertRedirects(response, reverse("photo-list"))
