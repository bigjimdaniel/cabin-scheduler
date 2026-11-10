import calendar
import mimetypes
from dataclasses import dataclass
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import EnrollmentForm, ReservationRequestForm
from .invitations import accept_invitation, token_digest
from .models import BlackoutRange, Cabin, Document, Invitation, Reservation


@sensitive_post_parameters("password1", "password2")
@never_cache
@require_http_methods(["GET", "POST"])
def enroll(request, token):
    invitation = Invitation.objects.filter(
        token_digest=token_digest(token), accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    form = None
    if invitation:
        form = EnrollmentForm(request.POST or None, email=invitation.email)
        if request.method == "POST" and form.is_valid():
            try:
                accept_invitation(invitation=invitation, form=form)
            except ValidationError as exc:
                form.add_error(None, exc)
            except IntegrityError:
                form.add_error(None, "That username is no longer available. Choose another and try again.")
            else:
                messages.success(request, "Your account is ready. Sign in with your new username and password.")
                return redirect("login")
    response = render(request, "registration/enroll.html", {
        "invitation": invitation, "form": form,
    }, status=200 if invitation else 400)
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@dataclass
class CalendarDay:
    day: date
    in_month: bool
    state: str
    label: str
    selected_date_label: str = ""
    detail_type: str = ""
    reservation_id: int | None = None
    reserved_for: str = ""
    requested_by: str = ""
    blocked_reason: str = ""
    blocked_by: str = ""
    date_range_label: str = ""
    nights: int | None = None


def get_primary_cabin() -> Cabin | None:
    return Cabin.objects.filter(is_active=True).order_by("id").first()


def parse_month(query_value: str | None, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(query_value or fallback)
    except (TypeError, ValueError):
        return fallback
    return min(max(parsed, minimum), maximum)


def build_calendar_days(cabin: Cabin, current_month: date) -> list[list[CalendarDay]]:
    month_days = calendar.Calendar(firstweekday=6).monthdatescalendar(
        current_month.year,
        current_month.month,
    )
    approved = list(
        cabin.reservations.filter(status=Reservation.Status.APPROVED)
        .select_related("user")
        .only(
            "id",
            "start_date",
            "end_date",
            "guest_name",
            "user__username",
            "user__first_name",
            "user__last_name",
        )
    )
    pending = list(
        cabin.reservations.filter(status=Reservation.Status.PENDING).only(
            "start_date",
            "end_date",
        )
    )
    blackouts = list(
        cabin.blackout_ranges.select_related("created_by").only(
            "id",
            "start_date",
            "end_date",
            "reason",
            "created_by__username",
            "created_by__first_name",
            "created_by__last_name",
        )
    )

    def approved_for_day(day_value: date) -> Reservation | None:
        return next(
            (item for item in approved if item.start_date <= day_value < item.end_date),
            None,
        )

    def blackout_for_day(day_value: date) -> BlackoutRange | None:
        return next(
            (item for item in blackouts if item.start_date <= day_value < item.end_date),
            None,
        )

    def state_for_day(
        day_value: date,
    ) -> tuple[str, str, Reservation | None, BlackoutRange | None]:
        blackout = blackout_for_day(day_value)
        if blackout:
            return ("blocked", "Blocked", None, blackout)
        approved_reservation = approved_for_day(day_value)
        if approved_reservation:
            return ("approved", "Booked", approved_reservation, None)
        if any(item.start_date <= day_value < item.end_date for item in pending):
            return ("pending", "Pending", None, None)
        return ("open", "Open", None, None)

    weeks: list[list[CalendarDay]] = []
    for week in month_days:
        rendered_week = []
        for day_value in week:
            state, label, reservation, blackout = state_for_day(day_value)
            rendered_week.append(
                CalendarDay(
                    day=day_value,
                    in_month=day_value.month == current_month.month,
                    state=state,
                    label=label,
                    selected_date_label=day_value.strftime("%b %d, %Y"),
                    detail_type=(
                        "reservation" if reservation else "blackout" if blackout else ""
                    ),
                    reservation_id=reservation.id if reservation else None,
                    reserved_for=reservation.reserved_for if reservation else "",
                    requested_by=reservation.requested_by_display if reservation else "",
                    blocked_reason=blackout.reason if blackout else "",
                    blocked_by=blackout.created_by_display if blackout else "",
                    date_range_label=(
                        f"{reservation.start_date:%b %-d, %Y} to {reservation.end_date:%b %-d, %Y}"
                        if reservation
                        else (
                            f"{blackout.start_date:%b %-d, %Y} to {blackout.end_date:%b %-d, %Y}"
                            if blackout
                            else ""
                        )
                    ),
                    nights=(
                        reservation.nights
                        if reservation
                        else (blackout.end_date - blackout.start_date).days if blackout else None
                    ),
                )
            )
        weeks.append(rendered_week)
    return weeks


class HomeView(TemplateView):
    template_name = "scheduler/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabin = get_primary_cabin()
        today = date.today()
        context["cabin"] = cabin
        context["today"] = today
        if cabin:
            context["upcoming_reservations"] = cabin.reservations.filter(
                status=Reservation.Status.APPROVED,
                end_date__gte=today,
            )[:5]
            context["pending_count"] = cabin.reservations.filter(
                status=Reservation.Status.PENDING
            ).count()
        else:
            context["upcoming_reservations"] = []
            context["pending_count"] = 0
        return context


class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = "scheduler/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabin = get_primary_cabin()
        if not cabin:
            raise Http404("No cabin has been configured yet.")

        today = date.today()
        year = parse_month(self.request.GET.get("year"), today.year, 2000, 2100)
        month = parse_month(self.request.GET.get("month"), today.month, 1, 12)
        current_month = date(year, month, 1)
        previous_month = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        context["cabin"] = cabin
        context["current_month"] = current_month
        context["weeks"] = build_calendar_days(cabin, current_month)
        context["previous_month"] = previous_month
        context["next_month"] = next_month
        return context


class ReservationCreateView(LoginRequiredMixin, CreateView):
    template_name = "scheduler/reservation_form.html"
    form_class = ReservationRequestForm
    success_url = reverse_lazy("reservation-list")

    def dispatch(self, request, *args, **kwargs):
        self.cabin = get_primary_cabin()
        if not self.cabin:
            raise Http404("No cabin has been configured yet.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["cabin"] = self.cabin
        return kwargs

    def form_valid(self, form):
        self.object = form.save(user=self.request.user)
        messages.success(
            self.request,
            "Reservation request submitted. An admin must approve it before the stay is confirmed.",
        )
        return redirect(self.get_success_url())


class ReservationListView(LoginRequiredMixin, ListView):
    template_name = "scheduler/reservation_list.html"
    context_object_name = "reservations"

    def get_queryset(self):
        queryset = Reservation.objects.select_related("cabin", "user", "decided_by")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)


class DocumentListView(LoginRequiredMixin, ListView):
    template_name = "scheduler/document_list.html"
    context_object_name = "documents"
    queryset = Document.objects.select_related("uploaded_by")


class DocumentFileView(LoginRequiredMixin, TemplateView):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(Document, pk=kwargs["pk"])
        as_attachment = request.GET.get("download") == "1"
        content_type, _ = mimetypes.guess_type(document.file.name)
        response = FileResponse(
            document.file.open("rb"),
            as_attachment=as_attachment,
            filename=document.filename,
            content_type=content_type or "application/octet-stream",
        )
        return response
