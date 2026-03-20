from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Cabin(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BlackoutRange(TimestampedModel):
    cabin = models.ForeignKey(
        Cabin,
        on_delete=models.CASCADE,
        related_name="blackout_ranges",
    )
    start_date = models.DateField()
    end_date = models.DateField(help_text="Checkout date for the blackout window.")
    reason = models.CharField(max_length=255)

    class Meta:
        ordering = ["start_date", "end_date"]

    def __str__(self) -> str:
        return f"{self.cabin} blackout {self.start_date} to {self.end_date}"

    def clean(self) -> None:
        if self.end_date <= self.start_date:
            raise ValidationError(
                {"end_date": "End date must be after the start date for overnight stays."}
            )


class Reservation(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    cabin = models.ForeignKey(
        Cabin,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    start_date = models.DateField()
    end_date = models.DateField(help_text="Checkout date for the reservation.")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "created_at"]

    def __str__(self) -> str:
        return f"{self.user} {self.start_date} to {self.end_date} ({self.status})"

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    def clean(self) -> None:
        errors = {}
        if self.end_date <= self.start_date:
            errors["end_date"] = "End date must be after the start date for overnight stays."

        if not self.cabin_id:
            errors["cabin"] = "A cabin is required."

        if errors:
            raise ValidationError(errors)

        if self.status in {self.Status.PENDING, self.Status.APPROVED}:
            self._validate_against_conflicts()

    def _validate_against_conflicts(self) -> None:
        overlap_filter = {
            "start_date__lt": self.end_date,
            "end_date__gt": self.start_date,
        }
        conflicting_reservations = (
            Reservation.objects.filter(
                cabin=self.cabin,
                status=self.Status.APPROVED,
                **overlap_filter,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if conflicting_reservations:
            raise ValidationError("This stay overlaps with an approved reservation.")

        conflicting_blackouts = BlackoutRange.objects.filter(
            cabin=self.cabin,
            **overlap_filter,
        ).exists()
        if conflicting_blackouts:
            raise ValidationError("This stay overlaps with a blackout range.")

    @transaction.atomic
    def approve(self, *, decided_by, admin_notes: str = "") -> None:
        self.status = self.Status.APPROVED
        self.decided_by = decided_by
        self.decided_at = timezone.now()
        if admin_notes:
            self.admin_notes = admin_notes
        self.full_clean()
        self.save()

    def reject(self, *, decided_by, admin_notes: str = "") -> None:
        self.status = self.Status.REJECTED
        self.decided_by = decided_by
        self.decided_at = timezone.now()
        if admin_notes:
            self.admin_notes = admin_notes
        self.save(
            update_fields=[
                "status",
                "decided_by",
                "decided_at",
                "admin_notes",
                "updated_at",
            ]
        )
