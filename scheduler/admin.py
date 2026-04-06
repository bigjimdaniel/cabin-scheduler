from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import BlackoutRange, Cabin, Reservation


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
    list_display = (
        "requested_by_display",
        "reserved_for",
        "cabin",
        "start_date",
        "end_date",
        "status",
        "decided_by",
        "updated_at",
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
