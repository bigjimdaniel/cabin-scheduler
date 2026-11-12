from django.contrib import admin, messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from smtplib import SMTPException

from .forms import CarouselPhotoForm, DocumentForm, InvitationForm
from .invitations import create_invitation, send_invitation
from .models import BlackoutRange, Cabin, CarouselPhoto, Document, Invitation, Reservation


@admin.register(CarouselPhoto)
class CarouselPhotoAdmin(admin.ModelAdmin):
    form = CarouselPhotoForm
    list_display = ("display_title", "thumbnail", "position", "is_active")
    list_editable = ("position", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "image")
    readonly_fields = ("thumbnail", "created_at", "updated_at")
    fields = ("title", "thumbnail", "image", "position", "is_active", "created_at", "updated_at")

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        if not obj.pk:
            return "Upload a photo to see its preview."
        return format_html('<img src="{}" alt="{}" width="96" height="64" style="object-fit:cover">', reverse("photo-image", args=[obj.pk]), obj.alt_text)


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "invited_by", "expires_at", "accepted_at")
    search_fields = ("email",)
    readonly_fields = ("email", "status", "invited_by", "expires_at", "accepted_at", "created_at", "updated_at")
    fields = readonly_fields

    def has_change_permission(self, request, obj=None):
        return False

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = InvitationForm(request.POST or None)
        enrollment_url = None
        invitation = None
        if request.method == "POST" and form.is_valid():
            try:
                invitation_kwargs = {
                    "email": form.cleaned_data["email"], "invited_by": request.user,
                    "base_url": settings.SITE_URL or request.build_absolute_uri("/").rstrip("/"),
                }
                if form.cleaned_data["delivery"] == "link":
                    invitation, enrollment_url = create_invitation(**invitation_kwargs)
                else:
                    invitation = send_invitation(**invitation_kwargs)
            except ValidationError as exc:
                form.add_error("email", exc)
            except IntegrityError:
                form.add_error("email", "This invitation changed while creating it. Please try again.")
            except (SMTPException, OSError):
                form.add_error(None, "The invitation could not be sent. Check email delivery settings and try again.")
            else:
                self.log_addition(request, invitation, "Created enrollment link." if enrollment_url else "Sent enrollment invitation.")
                if enrollment_url:
                    return self.invitation_response(request, form, {
                        "enrollment_url": enrollment_url, "invitation": invitation,
                        "title": "Invitation link ready",
                    })
                elif settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
                    self.message_user(request, "Invitation written to the server console. Configure SMTP to deliver email.", level=messages.WARNING)
                else:
                    self.message_user(request, "Invitation sent. The enrollment link expires in seven days.")
                return redirect(reverse("admin:scheduler_invitation_changelist"))
        return self.invitation_response(request, form, extra_context)

    def invitation_response(self, request, form, extra_context=None):
        context = {
            **self.admin_site.each_context(request),
            "title": "Invite a guest", "opts": self.model._meta,
            "form": form, **(extra_context or {}),
        }
        response = TemplateResponse(request, "admin/scheduler/invitation/send.html", context)
        response.headers["Cache-Control"] = "no-store, private"
        # Preserve the same-origin Origin header on form POSTs; no-referrer
        # makes browsers send Origin: null, which Django correctly rejects.
        response.headers["Referrer-Policy"] = "same-origin"
        return response


@admin.register(Cabin)
class CabinAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "is_active", "updated_at")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "location")


@admin.register(BlackoutRange)
class BlackoutRangeAdmin(admin.ModelAdmin):
    list_display = ("cabin", "start_date", "end_date", "reason", "created_by_display")
    list_filter = ("cabin",)
    search_fields = ("reason", "created_by__username", "created_by__first_name", "created_by__last_name")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "cabin",
        "start_date",
        "end_date",
        "reason",
        "created_by",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentForm
    list_display = ("title", "filename", "is_published", "uploaded_by_display", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("title", "description", "file", "uploaded_by__username")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "title",
        "description",
        "file",
        "is_published",
        "uploaded_by",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.action(description="Approve selected reservation requests")
def approve_reservations(modeladmin, request, queryset):
    approved = 0
    for reservation in queryset:
        try:
            reservation.approve(decided_by=request.user)
            approved += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"Could not approve #{reservation.pk}: {exc}",
                level=messages.ERROR,
            )
    if approved:
        modeladmin.message_user(request, f"Approved {approved} reservation(s).")


@admin.action(description="Reject selected reservation requests")
def reject_reservations(modeladmin, request, queryset):
    updated = queryset.exclude(status=Reservation.Status.REJECTED)
    for reservation in updated:
        reservation.reject(decided_by=request.user)
    modeladmin.message_user(request, f"Rejected {updated.count()} reservation(s).")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    change_form_template = "admin/scheduler/reservation/change_form.html"
    list_display = (
        "requested_by_display",
        "reserved_for",
        "cabin",
        "start_date",
        "end_date",
        "status",
        "decided_by",
        "updated_at",
        "review_request_link",
    )
    list_filter = ("status", "cabin")
    search_fields = ("user__username", "user__email", "guest_name", "notes", "admin_notes")
    readonly_fields = ("created_at", "updated_at", "decided_at")
    fields = (
        "cabin",
        "user",
        "guest_name",
        "start_date",
        "end_date",
        "status",
        "notes",
        "admin_notes",
        "decided_by",
        "decided_at",
        "created_at",
        "updated_at",
    )
    actions = (approve_reservations, reject_reservations)

    @admin.display(description="Review")
    def review_request_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>', reverse("reservation-review", args=[obj.pk]),
            "Review request" if obj.status == Reservation.Status.PENDING else "View decision",
        )
