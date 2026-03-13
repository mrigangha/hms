from bookings.models import Appointment
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from .decorators import role_required
from .forms import LoginForm, RegisterForm


def redirect_by_role(user):
    if user.is_doctor():
        return redirect("doctor_dashboard")
    elif user.is_patient():
        return redirect("patient_dashboard")
    return redirect("admin:index")


def register_view(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.username}!")

            try:
                from hms.email_service import send_signup_welcome

                send_signup_welcome(user)
            except Exception as e:
                print(f"[Email] signup welcome failed: {e}")

            return redirect_by_role(user)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RegisterForm()

    return render(request, "register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get("next")
            if next_url:
                return redirect(next_url)
            return redirect_by_role(user)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()
    return render(request, "login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("login")


@role_required("doctor")
def doctor_dashboard(request):
    today = timezone.localdate()
    doctor = request.user

    todays_appointments = (
        Appointment.objects.filter(
            doctor=doctor,
            appointment_date=today,
            status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
        )
        .select_related("patient")
        .order_by("start_time")
    )

    upcoming_appointments = (
        Appointment.objects.filter(
            doctor=doctor,
            appointment_date__gt=today,
            status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
        )
        .select_related("patient")
        .order_by("appointment_date", "start_time")[:10]
    )

    qs = Appointment.objects.filter(doctor=doctor)
    total = qs.count()
    pending = qs.filter(status=Appointment.STATUS_PENDING).count()
    confirmed = qs.filter(status=Appointment.STATUS_CONFIRMED).count()
    completed = qs.filter(status=Appointment.STATUS_COMPLETED).count()
    cancelled = qs.filter(status=Appointment.STATUS_CANCELLED).count()

    context = {
        "todays_appointments": todays_appointments,
        "upcoming_appointments": upcoming_appointments,
        "stats": {
            "total": total,
            "pending": pending,
            "confirmed": confirmed,
            "completed": completed,
            "cancelled": cancelled,
        },
    }
    return render(request, "doctor_dashboard.html", context)


@role_required("patient")
def patient_dashboard(request):
    today = timezone.localdate()
    patient = request.user

    upcoming_appointments = (
        Appointment.objects.filter(
            patient=patient,
            appointment_date__gte=today,
            status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
        )
        .select_related("doctor")
        .order_by("appointment_date", "start_time")[:10]
    )

    past_appointments = (
        Appointment.objects.filter(
            patient=patient,
            appointment_date__lt=today,
        )
        .select_related("doctor")
        .order_by("-appointment_date", "-start_time")[:5]
    )

    qs = Appointment.objects.filter(patient=patient)
    total = qs.count()
    upcoming = qs.filter(
        appointment_date__gte=today,
        status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
    ).count()
    completed = qs.filter(status=Appointment.STATUS_COMPLETED).count()
    cancelled = qs.filter(status=Appointment.STATUS_CANCELLED).count()

    context = {
        "upcoming_appointments": upcoming_appointments,
        "past_appointments": past_appointments,
        "stats": {
            "total": total,
            "upcoming": upcoming,
            "completed": completed,
            "cancelled": cancelled,
        },
    }
    return render(request, "test.html", context)


@login_required
def profile(request):
    user = request.user
    success = None
    error = None

    gcal_success = request.GET.get("gcal_success")
    gcal_error = request.GET.get("gcal_error")

    if gcal_success == "connected":
        success = "gcal_connected"
    elif gcal_success == "disconnected":
        success = "gcal_disconnected"
    elif gcal_error:
        error = f"Google Calendar error: {gcal_error.replace('_', ' ')}"

    if request.method == "POST":
        section = request.POST.get("section")

        if section == "personal":
            user.first_name = request.POST.get("first_name", "").strip()
            user.last_name = request.POST.get("last_name", "").strip()
            user.email = request.POST.get("email", "").strip()
            user.phone = request.POST.get("phone", "").strip()
            user.address = request.POST.get("address", "").strip()
            user.profile_bio = request.POST.get("profile_bio", "").strip()
            dob = request.POST.get("date_of_birth", "").strip()
            if dob:
                try:
                    from datetime import date

                    user.date_of_birth = date.fromisoformat(dob)
                except ValueError:
                    error = "Invalid date of birth."
            else:
                user.date_of_birth = None
            if not error:
                user.save()
                success = "personal"

        elif section == "doctor" and user.is_doctor():
            user.specialization = request.POST.get("specialization", "").strip()
            user.license_number = request.POST.get("license_number", "").strip()
            yrs = request.POST.get("years_experience", "").strip()
            fee = request.POST.get("consultation_fee", "").strip()
            user.years_experience = int(yrs) if yrs.isdigit() else None
            try:
                user.consultation_fee = float(fee) if fee else None
            except ValueError:
                user.consultation_fee = None
            user.save()
            success = "doctor"

        elif section == "patient" and user.is_patient():
            user.blood_group = request.POST.get("blood_group", "").strip()
            user.allergies = request.POST.get("allergies", "").strip()
            user.emergency_contact_name = request.POST.get(
                "emergency_contact_name", ""
            ).strip()
            user.emergency_contact_phone = request.POST.get(
                "emergency_contact_phone", ""
            ).strip()
            user.save()
            success = "patient"

        elif section == "password":
            current = request.POST.get("current_password", "")
            new_pw = request.POST.get("new_password", "")
            confirm = request.POST.get("confirm_password", "")
            if not user.check_password(current):
                error = "Current password is incorrect."
            elif len(new_pw) < 8:
                error = "New password must be at least 8 characters."
            elif new_pw != confirm:
                error = "Passwords do not match."
            else:
                user.set_password(new_pw)
                user.save()
                update_session_auth_hash(request, user)
                success = "password"

    context = {"user": user, "success": success, "error": error}
    return render(request, "profile.html", context)
