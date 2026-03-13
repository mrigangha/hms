# account/gcal_views.py

import base64
import hashlib
import os
import secrets
from datetime import timezone as dt_timezone

import requests as http_requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from google_auth_oauthlib.flow import Flow

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _build_flow():
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )


def _generate_code_verifier():
    """Generate a PKCE code verifier and its SHA-256 challenge."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


@login_required
def gcal_connect(request):
    flow = _build_flow()

    code_verifier, code_challenge = _generate_code_verifier()

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )

    request.session["gcal_oauth_state"] = state
    request.session["gcal_code_verifier"] = code_verifier
    request.session.modified = True
    request.session.save()

    return redirect(auth_url)


@login_required
def gcal_callback(request):
    # Google returned an error
    error = request.GET.get("error")
    if error:
        return redirect(f"/auth/profile/?gcal_error={error}")

    google_state = request.GET.get("state", "")
    code_verifier = request.session.get("gcal_code_verifier", "")

    flow = _build_flow()
    flow.state = google_state

    # Force http for localhost
    callback_url = request.build_absolute_uri()
    if "127.0.0.1" in callback_url or "localhost" in callback_url:
        callback_url = callback_url.replace("https://", "http://")

    try:
        flow.fetch_token(
            authorization_response=callback_url,
            code_verifier=code_verifier,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"[GCal] error: {repr(e)}")
        return redirect("/auth/profile/?gcal_error=token_fetch_failed")

    creds = flow.credentials

    if not creds or not creds.token:
        return redirect("/auth/profile/?gcal_error=no_token_received")

    user = request.user
    user.gcal_access_token = creds.token
    user.gcal_refresh_token = creds.refresh_token or user.gcal_refresh_token
    user.gcal_token_expiry = (
        creds.expiry.replace(tzinfo=dt_timezone.utc) if creds.expiry else None
    )
    user.gcal_connected = True
    user.save(
        update_fields=[
            "gcal_access_token",
            "gcal_refresh_token",
            "gcal_token_expiry",
            "gcal_connected",
        ]
    )

    request.session.pop("gcal_oauth_state", None)
    request.session.pop("gcal_code_verifier", None)

    return redirect("/auth/profile/?gcal_success=connected")


@login_required
def gcal_disconnect(request):
    user = request.user

    if user.gcal_access_token:
        try:
            http_requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": user.gcal_access_token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
        except Exception:
            pass

    user.gcal_access_token = ""
    user.gcal_refresh_token = ""
    user.gcal_token_expiry = None
    user.gcal_connected = False
    user.save(
        update_fields=[
            "gcal_access_token",
            "gcal_refresh_token",
            "gcal_token_expiry",
            "gcal_connected",
        ]
    )

    return redirect("/auth/profile/?gcal_success=disconnected")
