# hms/email_service.py
# Call this from anywhere in Django to send emails via the Lambda function.

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


LAMBDA_URL = getattr(settings, "EMAIL_LAMBDA_URL", "http://localhost:4000/email/send")


def _call(action, to_email, data):
    """Fire-and-forget POST to the Lambda. Never raises."""
    try:
        resp = requests.post(
            LAMBDA_URL,
            json={"action": action, "to_email": to_email, "data": data},
            timeout=5,
        )
        if resp.status_code != 200:
            logger.error(f"[Email] Lambda returned {resp.status_code}: {resp.text}")
        else:
            logger.info(f"[Email] {action} sent to {to_email}")
    except Exception as e:
        logger.error(f"[Email] Failed to call Lambda: {e}")


def send_signup_welcome(user):
    _call(
        action="SIGNUP_WELCOME",
        to_email=user.email,
        data={
            "name": user.get_full_name() or user.username,
            "role": user.role,
            "login_url": f"{settings.SITE_URL}/auth/login/",
        },
    )


def send_booking_confirmation(appointment):
    patient = appointment.patient
    doctor = appointment.doctor

    shared_data = {
        "patient_name": patient.get_full_name() or patient.username,
        "doctor_name": doctor.get_full_name() or doctor.username,
        "date": appointment.appointment_date.strftime("%A, %B %d, %Y"),
        "time": f"{appointment.start_time.strftime('%I:%M %p')} – {appointment.end_time.strftime('%I:%M %p')}",
        "reason": appointment.reason or "Not specified",
        "booking_id": appointment.pk,
    }

    if patient.email:
        _call(
            "BOOKING_CONFIRMATION",
            patient.email,
            {**shared_data, "recipient": "patient"},
        )

    # Email to doctor
    if doctor.email:
        _call(
            "BOOKING_CONFIRMATION", doctor.email, {**shared_data, "recipient": "doctor"}
        )
