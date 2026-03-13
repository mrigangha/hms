from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.role not in roles:
                return HttpResponseForbidden("Access Denied")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
