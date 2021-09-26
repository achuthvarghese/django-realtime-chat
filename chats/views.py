from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render

User = get_user_model()


def index(request):
    chat_users = User.objects.filter(is_active=True)
    context = {
        "title": "Home",
        "body": "Welcome to Real-time Chat application.",
        "chat_users": chat_users,
    }
    return render(request, "chats/index.html", context)


def chat(request):
    chat_with = request.GET.get("with", None)

    if not chat_with:
        return redirect("chats:index")

    chat_with_user = User.objects.get(id=chat_with)
    context = {
        "title": chat_with_user.get_full_name(),
        "chat_with": chat_with_user,
    }
    return render(request, "chats/box.html", context)
