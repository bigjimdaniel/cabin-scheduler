import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Invitation


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


@transaction.atomic
def create_invitation(*, email, invited_by, base_url):
    email = email.strip().lower()
    if get_user_model().objects.filter(email__iexact=email).exists():
        raise ValidationError("An account with this email address already exists.")
    invitation = Invitation.objects.select_for_update().filter(email=email).first()
    if invitation and invitation.accepted_at:
        raise ValidationError("This invitation has already been accepted.")
    token = secrets.token_urlsafe(32)
    if invitation is None:
        invitation = Invitation(email=email)
    invitation.token_digest = token_digest(token)
    invitation.invited_by = invited_by
    invitation.expires_at = timezone.now() + timedelta(days=7)
    invitation.full_clean()
    invitation.save()
    url = base_url.rstrip("/") + reverse("enroll", kwargs={"token": token})
    return invitation, url


@transaction.atomic
def send_invitation(*, email, invited_by, base_url):
    invitation, url = create_invitation(email=email, invited_by=invited_by, base_url=base_url)
    delivered = send_mail(
        "You're invited to Daniel Dream",
        render_to_string("registration/invitation_email.txt", {
            "enrollment_url": url, "expires_at": invitation.expires_at,
        }),
        settings.DEFAULT_FROM_EMAIL,
        [invitation.email],
        fail_silently=False,
    )
    if delivered != 1:
        raise OSError("The email backend did not accept the invitation.")
    return invitation


@transaction.atomic
def accept_invitation(*, invitation, form):
    # Claim the invitation atomically, including on SQLite where row locks are unavailable.
    now = timezone.now()
    claimed = Invitation.objects.filter(
        pk=invitation.pk, token_digest=invitation.token_digest,
        accepted_at__isnull=True, expires_at__gt=now,
    ).update(accepted_at=now)
    if not claimed:
        raise ValidationError("This invitation has expired or has already been used.")
    if get_user_model().objects.filter(email__iexact=invitation.email).exists():
        raise ValidationError("An account with this email address already exists. Please sign in.")
    user = form.save(commit=False)
    user.email = invitation.email
    user.is_staff = False
    user.is_superuser = False
    user.save()
    return user
