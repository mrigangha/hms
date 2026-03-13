from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from . import goauth, views

urlpatterns = [
    # auth
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # setup
    path("doctor/dashboard", views.doctor_dashboard, name="doctor_dashboard"),
    path("patient/dashboard", views.patient_dashboard, name="patient_dashboard"),
    path("profile/", views.profile, name="profile"),
    path("gcal/connect/", goauth.gcal_connect, name="gcal_connect"),
    path("gcal/callback/", goauth.gcal_callback, name="gcal_callback"),
    path("gcal/disconnect/", goauth.gcal_disconnect, name="gcal_disconnect"),
]
