from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from account.forms import (
    AppearanceForm,
    ProfileForm,
    StyledPasswordChangeForm,
    UserLoginForm,
    UserSignUpForm,
)
from account.models import Preference
from core import theme

User = get_user_model()


def _safe_next(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def user_login(request):
    if request.user.is_authenticated:
        return redirect("chat:chat")

    if request.method == "POST":
        form = UserLoginForm(request.POST, request=request)
        if form.is_valid():
            login(request, form.user)
            return redirect(_safe_next(request) or "chat:chat")
    else:
        form = UserLoginForm(request=request)

    context = {
        "title": "Sign in",
        "now_text": "signing in…",
        "form": form,
        "next": _safe_next(request) or "",
    }
    return render(request, "account/login.html", context)


@require_POST
def user_logout(request):
    logout(request)
    return redirect("account:login")


def user_signup(request):
    if request.user.is_authenticated:
        return redirect("chat:chat")

    if request.method == "POST":
        form = UserSignUpForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                username=data["username"],
                email=data["email"],
                password=data["password1"],
                first_name=data["first_name"],
                last_name=data["last_name"],
            )
            palette = request.POST.get("signup_palette")
            if palette in theme.PALETTE_KEYS:
                Preference.objects.create(user=user, palette=palette)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("chat:chat")
    else:
        form = UserSignUpForm()

    context = {"title": "Create account", "now_text": "joining relay…", "form": form}
    return render(request, "account/signup.html", context)


@login_required
def user_settings(request):
    """Profile, appearance and password on one page; each form posts its own
    `section` so only that form is validated."""
    profile_form = ProfileForm(instance=request.user)
    password_form = StyledPasswordChangeForm(request.user)
    section = request.POST.get("section") if request.method == "POST" else None

    if section == "profile":
        profile_form = ProfileForm(request.POST, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile saved.")
            return redirect("account:settings")
    elif section == "password":
        password_form = StyledPasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password changed.")
            return redirect("account:settings")

    context = {
        "title": "Settings",
        "profile_form": profile_form,
        "password_form": password_form,
        "section": section,
    }
    return render(request, "account/settings.html", context)


@login_required
@require_POST
def appearance(request):
    """Save any of palette, mode and density. JSON for scripts; a redirect
    back to settings for the no-JavaScript form."""
    form = AppearanceForm(request.POST)
    wants_json = "application/json" in request.headers.get("Accept", "")
    if not form.is_valid():
        if wants_json:
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "That appearance option isn't available.")
        return redirect("account:settings")

    pref = Preference.for_user(request.user)
    for field, value in form.changes().items():
        setattr(pref, field, value)
    pref.save()

    if wants_json:
        return JsonResponse(
            {
                "ok": True,
                "palette": pref.palette,
                "mode": pref.mode,
                "density": pref.density,
            }
        )
    messages.success(request, "Appearance saved.")
    return redirect("account:settings")
