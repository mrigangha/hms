from django.conf import settings
from django.db import models
from django.utils import timezone


class AvailabilitySlot(models.Model):
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_slots",
        limit_choices_to={"role": "doctor"},
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "date", "start_time"],
                name="unique_availability_slot_per_doctor",
            )
        ]

    @property
    def is_available(self):
        return not self.is_booked and self.date >= timezone.localdate()

    def __str__(self):
        status = "booked" if self.is_booked else "open"
        return (
            f"Dr. {self.doctor.get_full_name()} | "
            f"{self.date} {self.start_time}–{self.end_time} [{status}]"
        )


class Appointment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPLETED, "Completed"),
    ]

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointments_as_patient",
        limit_choices_to={"role": "patient"},
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointments_as_doctor",
        limit_choices_to={"role": "doctor"},
    )
    slot = models.OneToOneField(  # ← moved up with other FKs
        "bookings.AvailabilitySlot",
        on_delete=models.PROTECT,
        related_name="appointment",
        null=True,
        blank=True,
    )

    appointment_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    gcal_event_id_doctor = models.CharField(max_length=255, blank=True)
    gcal_event_id_patient = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-appointment_date", "-start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "appointment_date", "start_time"],
                name="unique_appointment_per_doctor",
            )
        ]

    def __str__(self):
        return (
            f"Appointment({self.patient.get_full_name()} → "
            f"Dr. {self.doctor.get_full_name()} | "
            f"{self.appointment_date} {self.start_time} [{self.status}])"
        )
