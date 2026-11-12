from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .document_files import ALLOWED_EXTENSIONS
from .models import CarouselPhoto, Document, Reservation


class CarouselPhotoForm(forms.ModelForm):
    class Meta:
        model = CarouselPhoto
        fields = ("title", "image", "is_active")
        widgets = {"image": forms.FileInput(attrs={"accept": ".jpg,.jpeg,.png,.webp"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].label = "Title (optional)"
        self.fields["image"].required = not (self.instance.image or self.instance.legacy_image)
        self.fields["image"].help_text = "JPG, PNG, or WebP. Leave blank when editing to keep the current photo."


class CarouselPhotoActionForm(forms.Form):
    action = forms.ChoiceField(choices=[(value, value) for value in ("up", "down", "show", "hide")])


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ("title", "description", "file", "is_published")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "file": forms.FileInput(attrs={
                "accept": ",".join(f".{extension}" for extension in ALLOWED_EXTENSIONS),
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["file"].help_text = "Choose a new file to replace the current one, or leave this blank to keep it."


class InvitationForm(forms.Form):
    email = forms.EmailField(label="Guest's email address")
    delivery = forms.ChoiceField(
        label="How would you like to share the invitation?",
        choices=(
            ("link", "Copy a link to share yourself"),
            ("email", "Send by email (requires email delivery setup)"),
        ),
        initial="link",
        required=False,
        widget=forms.RadioSelect,
    )

    def clean_delivery(self):
        return self.cleaned_data["delivery"] or "link"


class EnrollmentForm(UserCreationForm):
    first_name = forms.CharField(
        label="First name", max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        label="Last name", max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("first_name", "last_name", "username")

    def __init__(self, *args, email, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.email = email


class ReservationDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=(("approve", "Approve"), ("reject", "Reject")))
    admin_notes = forms.CharField(
        label="Admin note (optional)", required=False, max_length=5000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Only administrators can see this note.",
    )


class ReservationRequestForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["guest_name", "start_date", "end_date", "notes"]
        widgets = {
            "guest_name": forms.TextInput(
                attrs={"placeholder": "Leave blank if this reservation is for you"}
            ),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "guest_name": "Optional. Leave blank if this reservation is for you.",
            "end_date": "Choose the checkout date. Same-day bookings are not allowed.",
        }

    def __init__(self, *args, cabin=None, **kwargs):
        self.cabin = cabin
        super().__init__(*args, **kwargs)
        if self.cabin is not None:
            self.instance.cabin = self.cabin

    def save(self, commit=True, user=None):
        reservation = super().save(commit=False)
        reservation.cabin = self.cabin
        if user is not None:
            reservation.user = user
        if commit:
            reservation.full_clean()
            reservation.save()
        return reservation
