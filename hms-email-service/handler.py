import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger()
logger.setLevel(logging.INFO)


SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER)
FROM_NAME = os.environ.get("FROM_NAME", "HMS Health")


def _template_signup_welcome(data):
    name = data.get("name", "there")
    role = data.get("role", "user").capitalize()
    return (
        f"Welcome to HMS, {name}!",
        f"""
        <html><body style="font-family:sans-serif;color:#1a1a2e;max-width:600px;margin:auto;padding:32px">
          <div style="background:linear-gradient(135deg,#3de8c0,#4f8ef7);border-radius:16px;padding:32px;text-align:center;margin-bottom:24px">
            <h1 style="color:#0b0f1a;margin:0;font-size:28px">Welcome to HMS 🏥</h1>
          </div>
          <h2 style="color:#1a1a2e">Hi {name},</h2>
          <p style="color:#555;line-height:1.7">
            Your account has been created successfully as a <strong>{role}</strong>.
          </p>
          <p style="color:#555;line-height:1.7">
            {"You can now browse available doctors and book appointments." if role == "Patient" else "You can now add your availability slots and manage your appointments."}
          </p>
          <div style="margin:32px 0;text-align:center">
            <a href="{data.get("login_url", "#")}"
               style="background:linear-gradient(135deg,#3de8c0,#4f8ef7);color:#0b0f1a;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:700;font-size:16px">
              Go to Dashboard →
            </a>
          </div>
          <p style="color:#aaa;font-size:13px;text-align:center">HMS Health Management System</p>
        </body></html>
        """,
    )


def _template_booking_confirmation(data):
    patient_name = data.get("patient_name", "Patient")
    doctor_name = data.get("doctor_name", "Doctor")
    date = data.get("date", "—")
    time = data.get("time", "—")
    reason = data.get("reason", "Not specified")
    booking_id = data.get("booking_id", "—")
    recipient = data.get("recipient", "patient")  # "patient" or "doctor"

    if recipient == "doctor":
        subject = f"New Appointment Confirmed — {patient_name}"
        heading = f"New appointment booked with {patient_name}"
        body_line = f"A patient has booked an appointment with you."
    else:
        subject = f"Appointment Confirmed with Dr. {doctor_name}"
        heading = f"Your appointment is confirmed!"
        body_line = f"Your appointment with <strong>Dr. {doctor_name}</strong> has been confirmed."

    return (
        subject,
        f"""
        <html><body style="font-family:sans-serif;color:#1a1a2e;max-width:600px;margin:auto;padding:32px">
          <div style="background:linear-gradient(135deg,#3de8c0,#4f8ef7);border-radius:16px;padding:32px;text-align:center;margin-bottom:24px">
            <h1 style="color:#0b0f1a;margin:0;font-size:26px">Appointment Confirmed ✓</h1>
          </div>
          <h2 style="color:#1a1a2e">{heading}</h2>
          <p style="color:#555;line-height:1.7">{body_line}</p>

          <div style="background:#f8f9ff;border:1px solid #e0e4ff;border-radius:12px;padding:20px;margin:24px 0">
            <table style="width:100%;border-collapse:collapse">
              <tr><td style="color:#888;font-size:13px;padding:8px 0;border-bottom:1px solid #eee;width:40%">Booking ID</td>
                  <td style="font-weight:700;padding:8px 0;border-bottom:1px solid #eee">#{booking_id}</td></tr>
              <tr><td style="color:#888;font-size:13px;padding:8px 0;border-bottom:1px solid #eee">Patient</td>
                  <td style="font-weight:700;padding:8px 0;border-bottom:1px solid #eee">{patient_name}</td></tr>
              <tr><td style="color:#888;font-size:13px;padding:8px 0;border-bottom:1px solid #eee">Doctor</td>
                  <td style="font-weight:700;padding:8px 0;border-bottom:1px solid #eee">Dr. {doctor_name}</td></tr>
              <tr><td style="color:#888;font-size:13px;padding:8px 0;border-bottom:1px solid #eee">Date</td>
                  <td style="font-weight:700;padding:8px 0;border-bottom:1px solid #eee">{date}</td></tr>
              <tr><td style="color:#888;font-size:13px;padding:8px 0;border-bottom:1px solid #eee">Time</td>
                  <td style="font-weight:700;padding:8px 0;border-bottom:1px solid #eee">{time}</td></tr>
              <tr><td style="color:#888;font-size:13px;padding:8px 0">Reason</td>
                  <td style="font-weight:700;padding:8px 0">{reason}</td></tr>
            </table>
          </div>

          <p style="color:#aaa;font-size:13px;text-align:center">HMS Health Management System</p>
        </body></html>
        """,
    )


# ── Template router ────────────────────────────────────────────────────────────

TEMPLATES = {
    "SIGNUP_WELCOME": _template_signup_welcome,
    "BOOKING_CONFIRMATION": _template_booking_confirmation,
}


# ── SMTP sender ────────────────────────────────────────────────────────────────


def _send_smtp(to_email, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(FROM_EMAIL, to_email, msg.as_string())

    logger.info(f"Email sent to {to_email} | subject={subject}")


def send_email(event, context):
    """
    Expected POST body:
    {
        "action":   "SIGNUP_WELCOME" | "BOOKING_CONFIRMATION",
        "to_email": "recipient@example.com",
        "data":     { ...template-specific fields... }
    }
    """
    try:
        body = json.loads(event.get("body") or "{}")

        action = body.get("action", "").upper()
        to_email = body.get("to_email", "").strip()
        data = body.get("data", {})

        # Validate
        if not action:
            return _response(400, {"error": "Missing 'action'"})
        if not to_email:
            return _response(400, {"error": "Missing 'to_email'"})
        if action not in TEMPLATES:
            return _response(
                400, {"error": f"Unknown action '{action}'. Valid: {list(TEMPLATES)}"}
            )

        # Build and send
        subject, html_body = TEMPLATES[action](data)
        _send_smtp(to_email, subject, html_body)

        return _response(200, {"ok": True, "action": action, "to": to_email})

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP auth failed — check SMTP_USER and SMTP_PASSWORD")
        return _response(500, {"error": "SMTP authentication failed"})
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return _response(500, {"error": f"SMTP error: {str(e)}"})
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return _response(500, {"error": str(e)})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
