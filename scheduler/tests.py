from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import BlackoutRange, Cabin, Reservation


User = get_user_model()


class ReservationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="testpass123")
        self.admin = User.objects.create_user(
            username="admin",
            password="testpass123",
            is_staff=True,
        )
        self.cabin = Cabin.objects.get(slug="main-cabin")

    def test_accepts_valid_non_overlapping_request(self):
        reservation = Reservation(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 12),
        )
        reservation.full_clean()

    def test_rejects_overlap_with_approved_reservation(self):
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 12),
            status=Reservation.Status.APPROVED,
        )
        reservation = Reservation(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 4, 11),
            end_date=date(2026, 4, 13),
        )
        with self.assertRaises(ValidationError):
            reservation.full_clean()

    def test_rejects_overlap_with_blackout_range(self):
        BlackoutRange.objects.create(
            cabin=self.cabin,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 4),
            reason="Maintenance",
        )
        reservation = Reservation(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 5, 2),
            end_date=date(2026, 5, 5),
        )
        with self.assertRaises(ValidationError):
            reservation.full_clean()

    def test_rejects_invalid_date_range(self):
        reservation = Reservation(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 10),
        )
        with self.assertRaises(ValidationError):
            reservation.full_clean()

    def test_approve_rechecks_conflicts(self):
        first = Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 13),
        )
        second = Reservation.objects.create(
            cabin=self.cabin,
            user=self.admin,
            start_date=date(2026, 7, 11),
            end_date=date(2026, 7, 14),
        )
        first.approve(decided_by=self.admin)
        with self.assertRaises(ValidationError):
            second.approve(decided_by=self.admin)


class ReservationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="testpass123")
        self.other_user = User.objects.create_user(username="other", password="testpass123")
        self.admin = User.objects.create_user(
            username="admin",
            password="testpass123",
            is_staff=True,
        )
        self.cabin = Cabin.objects.get(slug="main-cabin")

    def test_calendar_requires_authentication(self):
        response = self.client.get(reverse("calendar"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_home_page_renders_photo_carousel(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-carousel')
        self.assertContains(response, "img/home-carousel/cabin1")
        self.assertContains(response, "img/home-carousel/cabin5")
        self.assertContains(response, "Show photo 5")

    def test_home_page_renders_hamburger_menu(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-menu-toggle')
        self.assertContains(response, 'id="site-nav"')
        self.assertContains(response, 'aria-controls="site-nav"')

    def test_authenticated_user_can_submit_request(self):
        self.client.login(username="member", password="testpass123")
        response = self.client.post(
            reverse("reservation-create"),
            {
                "start_date": "2026-08-10",
                "end_date": "2026-08-12",
                "notes": "Weekend trip",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

    def test_user_only_sees_their_own_reservations(self):
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 3),
        )
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.other_user,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 12),
        )
        self.client.login(username="member", password="testpass123")
        response = self.client.get(reverse("reservation-list"))
        reservations = list(response.context["reservations"])
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0].user, self.user)

    def test_staff_can_view_all_reservations(self):
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 3),
        )
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.other_user,
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 12),
        )
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(reverse("reservation-list"))
        self.assertEqual(len(response.context["reservations"]), 2)
