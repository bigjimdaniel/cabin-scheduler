from django import forms

from .models import Reservation


class ReservationRequestForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["start_date", "end_date", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
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
