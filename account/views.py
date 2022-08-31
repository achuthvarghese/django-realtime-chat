from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render

User = get_user_model()


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


def user_signup(request):
    template = "account/signup.html"
    context = {
        "title": "Signup",
    }

    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            return redirect("account:signup")

        if username and email and password1 and password2:
            user = User.objects.create_user(username, email, password1)
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            return redirect("account:login")
        else:
            return redirect("account:signup")
    else:
        if request.user.is_authenticated:
            return redirect("chat:chat")
        else:
            return render(request, template, context)
