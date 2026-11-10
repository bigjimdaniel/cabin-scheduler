from django.urls import path

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
