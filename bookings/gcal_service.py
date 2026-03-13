# bookings/gcal.py

from datetime import timezone as dt_timezone

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _creds_from_user(user):
    """Build a Credentials object from tokens stored on the user model."""
    print(
        f"[GCal] _creds_from_user: {user.username} | gcal_connected={user.gcal_connected}"
    )

    if not user.gcal_connected:
        print(f"[GCal] Skipping {user.username} — not connected")
        return None

    if not user.gcal_access_token:
        print(f"[GCal] Skipping {user.username} — no access token")
        return None

    if not user.gcal_refresh_token:
        print(f"[GCal] WARNING {user.username} — no refresh token")

    expiry = None
    if user.gcal_token_expiry:
        expiry = user.gcal_token_expiry.replace(tzinfo=None)

    print(f"[GCal] Building creds for {user.username} | expiry={expiry}")

    return Credentials(
        token=user.gcal_access_token or None,
        refresh_token=user.gcal_refresh_token or None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
        expiry=expiry,
    )


def _refresh_and_save(user, creds):
    """Refresh expired credentials and persist the new access token."""
    print(
        f"[GCal] _refresh_and_save: expired={creds.expired} | has_refresh={bool(creds.refresh_token)}"
    )

    if creds and creds.expired and creds.refresh_token:
        print(f"[GCal] Refreshing token for {user.username}...")
        try:
            creds.refresh(Request())
            user.gcal_access_token = creds.token
            user.gcal_token_expiry = (
                creds.expiry.replace(tzinfo=dt_timezone.utc) if creds.expiry else None
            )
            user.save(update_fields=["gcal_access_token", "gcal_token_expiry"])
            print(f"[GCal] Token refreshed and saved for {user.username}")
        except Exception as e:
            print(f"[GCal] Token refresh FAILED for {user.username}: {e}")
            return None
    return creds


def _build_service(user):
    print(f"[GCal] Building service for {user.username}...")
    creds = _creds_from_user(user)
    if not creds:
        print(f"[GCal] No creds — cannot build service for {user.username}")
        return None
    creds = _refresh_and_save(user, creds)
    if not creds:
        print(f"[GCal] Creds invalid after refresh for {user.username}")
        return None
    try:
        service = build("calendar", "v3", credentials=creds)
        print(f"[GCal] Service built OK for {user.username}")
        return service
    except Exception as e:
        print(f"[GCal] build() FAILED for {user.username}: {e}")
        return None


def _make_event_body(title, description, appointment_date, start_time, end_time):
    """Return a Google Calendar event resource dict."""
    date_str = appointment_date.isoformat()
    start_iso = f"{date_str}T{start_time.strftime('%H:%M:%S')}"
    end_iso = f"{date_str}T{end_time.strftime('%H:%M:%S')}"

    return {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": settings.TIME_ZONE},
        "end": {"dateTime": end_iso, "timeZone": settings.TIME_ZONE},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }


# ── Public API ─────────────────────────────────────────────────────────────────


def create_appointment_events(appointment):
    """
    Create a Google Calendar event for both doctor and patient.
    Silently skips users who haven't connected Google Calendar.
    """
    doctor = appointment.doctor
    patient = appointment.patient

    print(f"[GCal] create_appointment_events — appt #{appointment.pk}")
    print(f"[GCal] Doctor:  {doctor.username}  | connected={doctor.gcal_connected}")
    print(f"[GCal] Patient: {patient.username} | connected={patient.gcal_connected}")

    specialization = getattr(doctor, "specialization", None)

    doc_event_id = _create_event_for_user(
        user=doctor,
        title=f"Appointment with {patient.get_full_name() or patient.username}",
        description=(
            f"Patient: {patient.get_full_name() or patient.username}\n"
            f"Reason: {appointment.reason or 'N/A'}\n"
            f"Booking ID: #{appointment.pk}"
        ),
        appointment=appointment,
    )

    pat_event_id = _create_event_for_user(
        user=patient,
        title=f"Appointment with Dr. {doctor.get_full_name() or doctor.username}",
        description=(
            f"Doctor: Dr. {doctor.get_full_name() or doctor.username}\n"
            + (f"Specialization: {specialization}\n" if specialization else "")
            + f"Reason: {appointment.reason or 'N/A'}\n"
            f"Booking ID: #{appointment.pk}"
        ),
        appointment=appointment,
    )

    print(f"[GCal] doc_event_id={doc_event_id} | pat_event_id={pat_event_id}")

    update_fields = []
    if doc_event_id:
        appointment.gcal_event_id_doctor = doc_event_id
        update_fields.append("gcal_event_id_doctor")
    if pat_event_id:
        appointment.gcal_event_id_patient = pat_event_id
        update_fields.append("gcal_event_id_patient")
    if update_fields:
        appointment.save(update_fields=update_fields)

    return doc_event_id, pat_event_id


def _create_event_for_user(user, title, description, appointment):
    print(f"[GCal] _create_event_for_user: {user.username} | title={title}")
    service = _build_service(user)
    if not service:
        print(f"[GCal] No service for {user.username} — skipping event creation")
        return None
    try:
        body = _make_event_body(
            title=title,
            description=description,
            appointment_date=appointment.appointment_date,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
        )
        print(f"[GCal] Inserting event for {user.username}...")
        event = service.events().insert(calendarId="primary", body=body).execute()
        event_id = event.get("id")
        print(f"[GCal] Event created for {user.username}: {event_id}")
        return event_id
    except HttpError as e:
        print(f"[GCal] HttpError creating event for {user.username}: {e}")
        return None
    except Exception as e:
        print(f"[GCal] Unexpected error creating event for {user.username}: {e}")
        return None


def delete_appointment_events(appointment):
    """Delete calendar events for both doctor and patient on cancellation."""
    print(f"[GCal] delete_appointment_events — appt #{appointment.pk}")

    if appointment.gcal_event_id_doctor:
        _delete_event_for_user(appointment.doctor, appointment.gcal_event_id_doctor)
        appointment.gcal_event_id_doctor = ""

    if appointment.gcal_event_id_patient:
        _delete_event_for_user(appointment.patient, appointment.gcal_event_id_patient)
        appointment.gcal_event_id_patient = ""

    appointment.save(update_fields=["gcal_event_id_doctor", "gcal_event_id_patient"])


def _delete_event_for_user(user, event_id):
    service = _build_service(user)
    if not service or not event_id:
        return
    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        print(f"[GCal] Event {event_id} deleted for {user.username}")
    except HttpError as e:
        print(f"[GCal] Failed to delete event {event_id} for {user.username}: {e}")
