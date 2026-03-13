from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    DOCTOR = "doctor"
    PATIENT = "patient"
    ADMIN = "admin"
    ROLE_CHOICES = [
        (DOCTOR, "Doctor"),
        (PATIENT, "Patient"),
        (ADMIN, "Admin"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=PATIENT)

    gcal_access_token = models.TextField(blank=True)
    gcal_refresh_token = models.TextField(blank=True)
    gcal_token_expiry = models.DateTimeField(null=True, blank=True)
    gcal_connected = models.BooleanField(default=False)

    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    profile_bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # ── Doctor-only fields ────────────────────────────────────────────────
    specialization = models.CharField(max_length=100, blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    years_experience = models.PositiveIntegerField(null=True, blank=True)
    consultation_fee = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    blood_group = models.CharField(max_length=5, blank=True)
    allergies = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)

    def is_doctor(self):
        return self.role == self.DOCTOR

    def is_patient(self):
        return self.role == self.PATIENT

    def is_admin(self):
        return self.role == self.ADMIN
