from account.decorators import role_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from bookings.models import Appointment, AvailabilitySlot

User = get_user_model()


def _gcal_create(appointment):
    try:
        from bookings.gcal_service import create_appointment_events

        create_appointment_events(appointment)
    except Exception as e:
        print(f"[GCal] create failed: {e}")


def _gcal_delete(appointment):
    try:
        from bookings.gcal_service import delete_appointment_events

        delete_appointment_events(appointment)
    except Exception as e:
        print(f"[GCal] delete failed: {e}")


@role_required("patient")
def book_appointment(request):
    today = timezone.localdate()

    slots_qs = AvailabilitySlot.objects.filter(
        date__gte=today,
        is_booked=False,
    ).order_by("date", "start_time")

    doctors = (
        User.objects.filter(
            role="doctor",
            availability_slots__date__gte=today,
            availability_slots__is_booked=False,
        )
        .annotate(
            open_slots=Count(
                "availability_slots",
                filter=Q(
                    availability_slots__date__gte=today,
                    availability_slots__is_booked=False,
                ),
            )
        )
        .prefetch_related(Prefetch("availability_slots", queryset=slots_qs))
        .order_by("first_name", "last_name")
        .distinct()
    )

    context = {
        "doctors": doctors,
        "today": today,
        "selected_doctor": request.GET.get("doctor"),
    }
    return render(request, "book_appointment.html", context)


@role_required("patient")
def confirm_booking(request):
    if request.method != "POST":
        return redirect("book_appointment")

    from django.db import transaction

    slot_id = request.POST.get("slot_id")
    reason = request.POST.get("reason", "").strip()

    if not slot_id or not str(slot_id).isdigit():
        return render(
            request,
            "booking_failed.html",
            {"message": "Invalid slot. Please select a slot and try again."},
        )

    slot = get_object_or_404(AvailabilitySlot, pk=slot_id)

    if slot.date < timezone.localdate():
        return render(
            request,
            "booking_failed.html",
            {"message": "That slot is in the past and can no longer be booked."},
        )

    if slot.is_booked:
        return render(
            request,
            "booking_failed.html",
            {
                "message": "Sorry, that slot was just booked by someone else. Please choose another."
            },
        )

    try:
        with transaction.atomic():
            slot = AvailabilitySlot.objects.select_for_update().get(
                pk=slot_id,
                is_booked=False,
                date__gte=timezone.localdate(),
            )
            appointment = Appointment.objects.create(
                patient=request.user,
                doctor=slot.doctor,
                slot=slot,
                appointment_date=slot.date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                status=Appointment.STATUS_PENDING,
                reason=reason,
            )
            slot.is_booked = True
            slot.save(update_fields=["is_booked"])

    except AvailabilitySlot.DoesNotExist:
        return render(
            request,
            "booking_failed.html",
            {
                "message": "Sorry, that slot was just booked by someone else. Please choose another."
            },
        )

    # creates the calender event for both doctor and patient
    _gcal_create(appointment)

    # Send booking confirmation emails via Lambda
    try:
        from hms.email_service import send_booking_confirmation

        send_booking_confirmation(appointment)
    except Exception as e:
        print(f"[Email] booking confirmation failed: {e}")

    return render(request, "booking_success.html", {"appointment": appointment})


@role_required("doctor")
def add_availability(request):
    from django.db import IntegrityError

    error = None
    success = None
    today = timezone.localdate()

    slots = AvailabilitySlot.objects.filter(
        doctor=request.user,
        date__gte=today,
    ).order_by("date", "start_time")

    if request.method == "POST":
        date = request.POST.get("date")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")

        if not date or not start_time or not end_time:
            error = "All fields are required."
        elif start_time >= end_time:
            error = "Start time must be before end time."
        else:
            try:
                AvailabilitySlot.objects.create(
                    doctor=request.user,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                )
                success = "Slot added successfully."
                slots = AvailabilitySlot.objects.filter(
                    doctor=request.user,
                    date__gte=today,
                ).order_by("date", "start_time")
            except IntegrityError:
                error = "A slot already exists for that date and start time."

    context = {
        "slots": slots,
        "error": error,
        "success": success,
        "today": today.isoformat(),
    }
    return render(request, "add_slot.html", context)


@role_required("doctor")
def delete_slot(request, slot_id):
    from django.shortcuts import get_object_or_404

    slot = get_object_or_404(
        AvailabilitySlot,
        pk=slot_id,
        doctor=request.user,
    )
    if not slot.is_booked:
        slot.delete()
    return redirect("add_availability")


@role_required("patient")
def patient_appointments(request):
    today = timezone.localdate()
    status_filter = request.GET.get("status", "all")

    qs = (
        Appointment.objects.filter(patient=request.user)
        .select_related("doctor")
        .order_by("appointment_date", "start_time")
    )

    if status_filter in ("pending", "confirmed", "cancelled", "completed"):
        qs = qs.filter(status=status_filter)

    all_appts = Appointment.objects.filter(patient=request.user)
    total_count = all_appts.count()
    upcoming_count = all_appts.filter(
        status__in=["pending", "confirmed"],
        appointment_date__gte=today,
    ).count()
    completed_count = all_appts.filter(status="completed").count()
    cancelled_count = all_appts.filter(status="cancelled").count()

    context = {
        "appointments": qs,
        "active_filter": status_filter,
        "today": today,
        "total_count": total_count,
        "upcoming_count": upcoming_count,
        "completed_count": completed_count,
        "cancelled_count": cancelled_count,
    }
    return render(request, "patient_appointments.html", context)


@role_required("patient")
def cancel_appointment(request, appt_id):
    appt = get_object_or_404(
        Appointment,
        pk=appt_id,
        patient=request.user,
        status__in=["pending", "confirmed"],
    )

    if appt.slot:
        appt.slot.is_booked = False
        appt.slot.save(update_fields=["is_booked"])

    appt.status = Appointment.STATUS_CANCELLED
    appt.save(update_fields=["status"])

    _gcal_delete(appt)

    return redirect("patient_appointments")


@role_required("doctor")
def doctor_appointments(request):
    today = timezone.localdate()
    status_filter = request.GET.get("status", "all")

    qs = (
        Appointment.objects.filter(doctor=request.user)
        .select_related("patient")
        .order_by("appointment_date", "start_time")
    )

    if status_filter in ("pending", "confirmed", "cancelled", "completed"):
        qs = qs.filter(status=status_filter)

    # Counts always across ALL (ignore filter)
    all_appts = Appointment.objects.filter(doctor=request.user)
    total_count = all_appts.count()
    pending_count = all_appts.filter(status="pending").count()
    confirmed_count = all_appts.filter(status="confirmed").count()
    completed_count = all_appts.filter(status="completed").count()

    context = {
        "appointments": qs,
        "active_filter": status_filter,
        "today": today,
        "total_count": total_count,
        "pending_count": pending_count,
        "confirmed_count": confirmed_count,
        "completed_count": completed_count,
    }
    return render(request, "doctor_appointments.html", context)


@role_required("doctor")
def doctor_update_appointment(request, appt_id):
    if request.method != "POST":
        return redirect("doctor_appointments")

    appt = get_object_or_404(
        Appointment,
        pk=appt_id,
        doctor=request.user,
    )

    action = request.POST.get("action")

    if action == "confirm" and appt.status == Appointment.STATUS_PENDING:
        appt.status = Appointment.STATUS_CONFIRMED
        appt.save(update_fields=["status"])
        _gcal_create(appt)
        try:
            from hms.email_service import send_booking_confirmation

            send_booking_confirmation(appt)
        except Exception as e:
            print(f"[Email] booking confirmation failed: {e}")

    elif action == "complete" and appt.status == Appointment.STATUS_CONFIRMED:
        appt.status = Appointment.STATUS_COMPLETED
        appt.save(update_fields=["status"])

    elif action == "cancel" and appt.status in (
        Appointment.STATUS_PENDING,
        Appointment.STATUS_CONFIRMED,
    ):
        if appt.slot:
            appt.slot.is_booked = False
            appt.slot.save(update_fields=["is_booked"])
        appt.status = Appointment.STATUS_CANCELLED
        appt.save(update_fields=["status"])
        _gcal_delete(appt)

    elif action == "notes":
        appt.notes = request.POST.get("notes", "").strip()
        appt.save(update_fields=["notes"])

    return redirect("doctor_appointments")
