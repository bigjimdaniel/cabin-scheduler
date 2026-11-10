import calendar
import mimetypes
from dataclasses import dataclass
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.conf import settings
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import DocumentForm, EnrollmentForm, ReservationRequestForm
from .document_files import ALLOWED_EXTENSIONS, preview_type
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
    paginate_by = 20

    def get_queryset(self):
        queryset = visible_documents(self.request.user).select_related("uploaded_by")
        self.query = self.request.GET.get("q", "").strip()[:200]
        if self.query:
            queryset = queryset.filter(
                Q(title__icontains=self.query) | Q(description__icontains=self.query)
                | Q(file__icontains=self.query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.query
        context["query_string"] = self.request.GET.copy()
        context["query_string"].pop("page", None)
        context["query_string"] = context["query_string"].urlencode()
        return context


def visible_documents(user):
    queryset = Document.objects.all()
    if user.is_active and user.is_staff and any(
        user.has_perm(f"scheduler.{action}_document")
        for action in ("view", "add", "change", "delete")
    ):
        return queryset
    return queryset.filter(is_published=True)


class DocumentManagementMixin(LoginRequiredMixin, PermissionRequiredMixin):
    model = Document
    success_url = reverse_lazy("document-list")

    def has_permission(self):
        return self.request.user.is_active and self.request.user.is_staff and super().has_permission()


class DocumentFormMixin:
    form_class = DocumentForm
    template_name = "scheduler/document_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["max_upload_mb"] = f"{settings.DOCUMENT_MAX_UPLOAD_BYTES / (1024 * 1024):g}"
        context["allowed_extensions"] = ", ".join(extension.upper() for extension in ALLOWED_EXTENSIONS)
        return context


class DocumentCreateView(DocumentManagementMixin, DocumentFormMixin, CreateView):
    permission_required = "scheduler.add_document"

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Document uploaded." if self.object.is_published else "Document saved as unpublished.")
        return response


class DocumentUpdateView(DocumentManagementMixin, DocumentFormMixin, UpdateView):
    permission_required = "scheduler.change_document"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Document updated.")
        return response


class DocumentDeleteView(DocumentManagementMixin, DeleteView):
    permission_required = "scheduler.delete_document"
    template_name = "scheduler/document_confirm_delete.html"
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Document deleted.")
        return response


class DocumentFileView(LoginRequiredMixin, TemplateView):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(visible_documents(request.user), pk=kwargs["pk"])
        preview_content_type = preview_type(document.filename)
        as_attachment = request.GET.get("download") == "1" or not preview_content_type
        content_type = preview_content_type or mimetypes.guess_type(document.filename)[0]
        try:
            file = document.file.open("rb")
        except (OSError, ValueError):
            raise Http404("This file is unavailable. Please contact the site administrator.")
        response = FileResponse(
            file,
            as_attachment=as_attachment,
            filename=document.filename,
            content_type=content_type or "application/octet-stream",
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
