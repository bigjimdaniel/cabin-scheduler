from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import CarouselPhotoActionForm, CarouselPhotoForm
from .models import CarouselPhoto
from .photo_files import PHOTO_TYPES


def can_manage_photos(user):
    return user.is_authenticated and user.is_active and user.is_staff and any(
        user.has_perm(f"scheduler.{action}_carouselphoto") for action in ("view", "add", "change", "delete")
    )


class PhotoManagementMixin(LoginRequiredMixin, PermissionRequiredMixin):
    model = CarouselPhoto
    success_url = reverse_lazy("photo-list")

    def has_permission(self):
        return self.request.user.is_active and self.request.user.is_staff and super().has_permission()


class PhotoListView(PhotoManagementMixin, ListView):
    template_name = "scheduler/photo_list.html"
    context_object_name = "photos"

    def has_permission(self):
        return can_manage_photos(self.request.user)


class PhotoFormMixin:
    form_class = CarouselPhotoForm
    template_name = "scheduler/photo_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["max_upload_mb"] = f"{settings.CAROUSEL_MAX_UPLOAD_BYTES / 1048576:g}"
        return context


class PhotoCreateView(PhotoManagementMixin, PhotoFormMixin, CreateView):
    permission_required = "scheduler.add_carouselphoto"

    def form_valid(self, form):
        form.instance.position = (CarouselPhoto.objects.aggregate(last=Max("position"))["last"] or 0) + 1
        response = super().form_valid(form)
        messages.success(self.request, "Photo added to the carousel." if self.object.is_active else "Photo saved as hidden.")
        return response


class PhotoUpdateView(PhotoManagementMixin, PhotoFormMixin, UpdateView):
    permission_required = "scheduler.change_carouselphoto"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Photo updated.")
        return response


class PhotoDeleteView(PhotoManagementMixin, DeleteView):
    permission_required = "scheduler.delete_carouselphoto"
    template_name = "scheduler/photo_confirm_delete.html"
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Photo removed from the carousel.")
        return response


@require_POST
def photo_action(request, pk):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not (request.user.is_active and request.user.is_staff and request.user.has_perm("scheduler.change_carouselphoto")):
        raise PermissionDenied
    form = CarouselPhotoActionForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Choose a valid photo action.")
    action = form.cleaned_data["action"]
    with transaction.atomic():
        photos = list(CarouselPhoto.objects.select_for_update())
        index = next((index for index, photo in enumerate(photos) if photo.pk == pk), None)
        if index is None:
            raise Http404
        photo = photos[index]
        if action in ("show", "hide"):
            photo.is_active = action == "show"
            photo.save(update_fields=["is_active", "updated_at"])
        else:
            neighbor = index + (-1 if action == "up" else 1)
            if 0 <= neighbor < len(photos):
                photos[index], photos[neighbor] = photos[neighbor], photos[index]
                for position, item in enumerate(photos):
                    item.position = position
                    item.updated_at = timezone.now()
                CarouselPhoto.objects.bulk_update(photos, ["position", "updated_at"])
    messages.success(request, "Photo order updated." if action in ("up", "down") else "Photo visibility updated.")
    return redirect("photo-list")


@never_cache
def photo_image(request, pk):
    photo = get_object_or_404(CarouselPhoto, pk=pk)
    if not photo.is_active and not can_manage_photos(request.user):
        raise Http404
    try:
        if photo.image:
            file = photo.image.open("rb")
            content_type = PHOTO_TYPES[Path(photo.image.name).suffix.lower()][1]
        else:
            # Only the five shipped gallery files may be served as legacy images.
            if photo.legacy_image not in {f"img/home-carousel/cabin{i}.jpg" for i in range(1, 6)}:
                raise Http404
            path = finders.find(photo.legacy_image)
            if not path:
                raise Http404
            file = open(path, "rb")
            content_type = "image/jpeg"
    except (OSError, ValueError, KeyError):
        raise Http404("This photo is unavailable.")
    response = FileResponse(file, content_type=content_type)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
