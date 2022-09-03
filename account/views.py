from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render

from account.forms import UserLoginForm, UserSignUpForm

User = get_user_model()


def user_login(request):
    template = "account/login.html"
    form = UserLoginForm()
    context = {
        "title": "Login",
        "form": form,
    }

    if request.method == "POST":
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect("chat:chat")
            else:
                context.update({"form": form})
        else:
            print(form.errors)
            context.update({"form": form})
    else:
        if request.user.is_authenticated:
            return redirect("chat:chat")
    return render(request, template, context)


def user_logout(request):
    logout(request)
    return redirect("account:login")


def user_signup(request):
    template = "account/signup.html"
    form = UserSignUpForm()
    context = {
        "title": "Signup",
        "form": form,
    }

    if request.method == "POST":
        form = UserSignUpForm(request.POST)
        if form.is_valid():
            first_name = request.POST.get("first_name")
            last_name = request.POST.get("last_name")
            username = request.POST.get("username")
            email = request.POST.get("email")
            password1 = request.POST.get("password1")

            user = User.objects.create_user(username, email, password1)
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            return redirect("account:login")
        else:
            context.update({"form": form})
    else:
        if request.user.is_authenticated:
            return redirect("chat:chat")
    return render(request, template, context)
