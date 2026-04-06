from datetime import date

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from .admin import BlackoutRangeAdmin, ReservationAdmin
from .models import BlackoutRange, Cabin, Reservation


User = get_user_model()


class ReservationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member",
            password="testpass123",
            first_name="Casey",
            last_name="Member",
        )
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

    def test_reserved_for_uses_guest_name_when_present(self):
        reservation = Reservation(
            cabin=self.cabin,
            user=self.user,
            guest_name="Taylor Guest",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 17),
        )
        self.assertEqual(reservation.reserved_for, "Taylor Guest")

    def test_reserved_for_falls_back_to_requester_display_name(self):
        reservation = Reservation(
            cabin=self.cabin,
            user=self.user,
            start_date=date(2026, 4, 18),
            end_date=date(2026, 4, 20),
        )
        self.assertEqual(reservation.reserved_for, "Casey Member")

    def test_requester_display_falls_back_to_username(self):
        user = User.objects.create_user(username="plainuser", password="testpass123")
        reservation = Reservation(
            cabin=self.cabin,
            user=user,
            start_date=date(2026, 4, 21),
            end_date=date(2026, 4, 23),
        )
        self.assertEqual(reservation.requested_by_display, "plainuser")

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
            guest_name="Taylor Guest",
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


class BlackoutRangeModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="caretaker",
            password="testpass123",
            first_name="Taylor",
            last_name="Caretaker",
        )
        self.cabin = Cabin.objects.get(slug="main-cabin")

    def test_created_by_display_uses_full_name_when_present(self):
        blackout = BlackoutRange(
            cabin=self.cabin,
            created_by=self.user,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3),
            reason="Repairs",
        )
        self.assertEqual(blackout.created_by_display, "Taylor Caretaker")

    def test_created_by_display_falls_back_to_unknown(self):
        blackout = BlackoutRange(
            cabin=self.cabin,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3),
            reason="Repairs",
        )
        self.assertEqual(blackout.created_by_display, "Unknown")


class ReservationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member",
            password="testpass123",
            first_name="Casey",
            last_name="Member",
        )
        self.other_user = User.objects.create_user(
            username="other",
            password="testpass123",
            first_name="Jordan",
            last_name="Other",
        )
        self.admin = User.objects.create_user(
            username="admin",
            password="testpass123",
            is_staff=True,
            first_name="Admin",
            last_name="User",
        )
        self.cabin = Cabin.objects.get(slug="main-cabin")

    def test_calendar_requires_authentication(self):
        response = self.client.get(reverse("calendar"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_calendar_renders_details_panel_for_approved_reservations(self):
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            guest_name="Taylor Guest",
            start_date=date(2026, 5, 4),
            end_date=date(2026, 5, 7),
            status=Reservation.Status.APPROVED,
        )
        self.client.login(username="member", password="testpass123")

        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 5})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-calendar-details')
        self.assertContains(response, 'data-calendar-day')
        self.assertContains(response, 'data-detail-type="reservation"')
        self.assertContains(response, 'data-reserved-for="Taylor Guest"')
        self.assertContains(response, 'data-requested-by="Casey Member"')
        self.assertContains(response, 'data-selected-date="May 04, 2026"')
        self.assertContains(response, 'Click a booked or blocked day in the calendar to see the details.')
        self.assertContains(response, 'js/calendar-details')

    def test_calendar_renders_details_panel_for_blocked_dates(self):
        BlackoutRange.objects.create(
            cabin=self.cabin,
            created_by=self.admin,
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 12),
            reason="Water heater repair",
        )
        self.client.login(username="member", password="testpass123")

        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 5})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-detail-type="blackout"')
        self.assertContains(response, 'data-blocked-reason="Water heater repair"')
        self.assertContains(response, 'data-blocked-by="Admin User"')
        self.assertContains(response, 'Block Reason')
        self.assertContains(response, 'Blocked By')

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
                "guest_name": "",
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
        self.assertEqual(reservation.reserved_for, "Casey Member")

    def test_authenticated_user_can_submit_request_for_guest_without_account(self):
        self.client.login(username="member", password="testpass123")
        response = self.client.post(
            reverse("reservation-create"),
            {
                "guest_name": "Taylor Guest",
                "start_date": "2026-08-20",
                "end_date": "2026-08-23",
                "notes": "Family visit",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        reservation = Reservation.objects.get(start_date=date(2026, 8, 20))
        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.guest_name, "Taylor Guest")
        self.assertEqual(reservation.reserved_for, "Taylor Guest")

    def test_user_only_sees_their_own_reservations(self):
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            guest_name="Taylor Guest",
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
        self.assertContains(response, "Taylor Guest")
        self.assertNotContains(response, "Jordan Other")

    def test_staff_can_view_all_reservations(self):
        Reservation.objects.create(
            cabin=self.cabin,
            user=self.user,
            guest_name="Taylor Guest",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 3),
        )
        Reservation.objects.create(
            cabin=self.cabin,
            guest_name="Morgan Visitor",
            user=self.other_user,
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 12),
        )
        self.client.login(username="admin", password="testpass123")
        response = self.client.get(reverse("reservation-list"))
        self.assertEqual(len(response.context["reservations"]), 2)
        self.assertContains(response, "Casey Member")
        self.assertContains(response, "Jordan Other")
        self.assertContains(response, "Taylor Guest")
        self.assertContains(response, "Morgan Visitor")


class ReservationAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.requester = User.objects.create_user(
            username="member",
            password="testpass123",
            first_name="Casey",
            last_name="Member",
        )
        self.cabin = Cabin.objects.get(slug="main-cabin")
        self.reservation = Reservation.objects.create(
            cabin=self.cabin,
            user=self.requester,
            guest_name='Taylor Guest',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
        )

    def test_admin_search_finds_guest_name(self):
        model_admin = ReservationAdmin(Reservation, self.site)
        request = self.factory.get("/admin/scheduler/reservation/", {"q": "Taylor Guest"})
        request.user = self.admin_user

        queryset = Reservation.objects.all()
        filtered_queryset, use_distinct = model_admin.get_search_results(
            request,
            queryset,
            "Taylor Guest",
        )

        self.assertFalse(use_distinct)
        self.assertEqual(list(filtered_queryset), [self.reservation])


class BlackoutRangeAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
            first_name="Admin",
            last_name="User",
        )
        self.cabin = Cabin.objects.get(slug="main-cabin")

    def test_admin_save_model_sets_created_by_on_create(self):
        model_admin = BlackoutRangeAdmin(BlackoutRange, self.site)
        request = self.factory.post("/admin/scheduler/blackoutrange/add/")
        request.user = self.admin_user
        blackout = BlackoutRange(
            cabin=self.cabin,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 3),
            reason="Maintenance",
        )
        model_admin.save_model(request, blackout, None, change=False)

        self.assertEqual(blackout.created_by, self.admin_user)
