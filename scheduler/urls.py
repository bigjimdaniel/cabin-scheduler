from django.urls import path

from .views import CalendarView, HomeView, ReservationCreateView, ReservationListView


urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("reservations/new/", ReservationCreateView.as_view(), name="reservation-create"),
    path("reservations/", ReservationListView.as_view(), name="reservation-list"),
]
