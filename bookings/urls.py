from django.urls import path

from . import views

urlpatterns = [
    path("book/", views.book_appointment, name="book_appointment"),
    path("book/confirm/", views.confirm_booking, name="confirm_booking"),
    path("doctor/availability/", views.add_availability, name="add_availability"),
    path(
        "doctor/availability/<int:slot_id>/delete/",
        views.delete_slot,
        name="delete_slot",
    ),
    path("appointments/", views.patient_appointments, name="patient_appointments"),
    path(
        "appointments/<int:appt_id>/cancel/",
        views.cancel_appointment,
        name="cancel_appointment",
    ),
    path("appointments/doctor/", views.doctor_appointments, name="doctor_appointments"),
    path(
        "appointments/doctor/<int:appt_id>/update/",
        views.doctor_update_appointment,
        name="doctor_update_appointment",
    ),
]
