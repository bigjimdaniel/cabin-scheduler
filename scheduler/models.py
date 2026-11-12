from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.utils import timezone
from pathlib import Path

from .document_files import ALLOWED_EXTENSIONS, preview_type, validate_document_size
from .photo_files import validate_carousel_image


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Invitation(TimestampedModel):
    email = models.EmailField(unique=True)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField(editable=False)
    accepted_at = models.DateTimeField(null=True, blank=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="sent_invitations", editable=False,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def status(self):
        if self.accepted_at:
            return "Accepted"
        return "Expired" if self.expires_at <= timezone.now() else "Pending"


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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_blackout_ranges",
    )
    start_date = models.DateField()
    end_date = models.DateField(help_text="Checkout date for the blackout window.")
    reason = models.CharField(max_length=255)

    class Meta:
        ordering = ["start_date", "end_date"]

    def __str__(self) -> str:
        return f"{self.cabin} blackout {self.start_date} to {self.end_date}"

    @property
    def created_by_display(self) -> str:
        if not self.created_by:
            return "Unknown"
        full_name = self.created_by.get_full_name().strip()
        return full_name or self.created_by.get_username()

    def clean(self) -> None:
        if self.end_date <= self.start_date:
            raise ValidationError(
                {"end_date": "End date must be after the start date for overnight stays."}
            )


class Document(TimestampedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(
        upload_to="documents/%Y/%m/",
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS), validate_document_size],
    )
    is_published = models.BooleanField(
        default=True, help_text="Published files are available to all signed-in users.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )

    class Meta:
        ordering = ["title", "-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def filename(self) -> str:
        return Path(self.file.name).name

    @property
    def file_type(self):
        return Path(self.file.name).suffix.lstrip(".").upper()

    @property
    def file_size(self):
        try:
            return self.file.size
        except (OSError, ValueError):
            return None

    @property
    def can_preview(self):
        return preview_type(self.file.name) is not None

    @property
    def uploaded_by_display(self) -> str:
        if not self.uploaded_by:
            return "Unknown"
        full_name = self.uploaded_by.get_full_name().strip()
        return full_name or self.uploaded_by.get_username()


class CarouselPhoto(TimestampedModel):
    title = models.CharField(max_length=150, blank=True)
    image = models.ImageField(upload_to="carousel/%Y/%m/", blank=True, validators=[validate_carousel_image])
    # Initial gallery photos stay in the bundled static assets; replacements use uploaded images.
    legacy_image = models.CharField(max_length=100, blank=True, editable=False)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, verbose_name="Show on homepage")

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "carousel photo"

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        return self.title.strip() or Path(self.image.name or self.legacy_image).name or "Photo"

    @property
    def alt_text(self):
        return self.title.strip() or "Cabin photo"

    def clean(self):
        super().clean()
        if not self.image and not self.legacy_image:
            raise ValidationError({"image": "Choose a photo to upload."})


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
    guest_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional name of the person staying, if different from the requester.",
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
        return f"{self.reserved_for} {self.start_date} to {self.end_date} ({self.status})"

    @property
    def requested_by(self):
        return self.user

    @property
    def requested_by_display(self) -> str:
        full_name = self.user.get_full_name().strip()
        return full_name or self.user.get_username()

    @property
    def reserved_for(self) -> str:
        return self.guest_name.strip() or self.requested_by_display

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
