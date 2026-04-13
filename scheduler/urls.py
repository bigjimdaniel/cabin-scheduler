from django.urls import path

from .views import (
    CalendarView,
    DocumentFileView,
    DocumentListView,
    HomeView,
    ReservationCreateView,
    ReservationListView,
)


urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentFileView.as_view(), name="document-file"),
    path("reservations/new/", ReservationCreateView.as_view(), name="reservation-create"),
    path("reservations/", ReservationListView.as_view(), name="reservation-list"),
]
