from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=[
            ("doctor", "Doctor"),
            ("patient", "Patient"),
        ]
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2", "role"]


class LoginForm(AuthenticationForm):
    pass
