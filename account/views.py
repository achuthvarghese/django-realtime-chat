from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render


def user_login(request):
    template = "account/login.html"
    context = {
        "title": "Login",
    }
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("chat:chat")
        else:
            return redirect("account:login")
    else:
        if request.user.is_authenticated:
            return redirect("chat:chat")
        else:
            return render(request, template, context)


def user_logout(request):
    logout(request)
    return redirect("account:login")
