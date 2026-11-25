from django.contrib.auth import get_user_model, login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from account.forms import UserLoginForm, UserSignUpForm

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

    context = {"title": "Login", "form": form, "next": _safe_next(request) or ""}
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
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("chat:chat")
    else:
        form = UserSignUpForm()

    return render(request, "account/signup.html", {"title": "Signup", "form": form})
