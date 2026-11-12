from django.urls import path
from .photo_views import PhotoCreateView, PhotoDeleteView, PhotoListView, PhotoUpdateView, photo_action, photo_image

from .views import (
    CalendarView,
    DocumentFileView,
    DocumentListView,
    DocumentCreateView,
    DocumentUpdateView,
    DocumentDeleteView,
    HomeView,
    ReservationCreateView,
    ReservationListView,
    reservation_review,
)


urlpatterns = [
    path("photos/manage/", PhotoListView.as_view(), name="photo-list"),
    path("photos/manage/new/", PhotoCreateView.as_view(), name="photo-create"),
    path("photos/manage/<int:pk>/edit/", PhotoUpdateView.as_view(), name="photo-update"),
    path("photos/manage/<int:pk>/delete/", PhotoDeleteView.as_view(), name="photo-delete"),
    path("photos/manage/<int:pk>/action/", photo_action, name="photo-action"),
    path("photos/<int:pk>/image/", photo_image, name="photo-image"),
    path("", HomeView.as_view(), name="home"),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/new/", DocumentCreateView.as_view(), name="document-create"),
    path("documents/<int:pk>/edit/", DocumentUpdateView.as_view(), name="document-update"),
    path("documents/<int:pk>/delete/", DocumentDeleteView.as_view(), name="document-delete"),
    path("documents/<int:pk>/", DocumentFileView.as_view(), name="document-file"),
    path("reservations/new/", ReservationCreateView.as_view(), name="reservation-create"),
    path("reservations/", ReservationListView.as_view(), name="reservation-list"),
    path("reservations/<int:pk>/review/", reservation_review, name="reservation-review"),
]
