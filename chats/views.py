from django.shortcuts import render


def index(request):
    context = {
        "title": "Home",
        "body": "Welcome to Real-time Chat application.",
    }
    return render(request, "chats/index.html", context)
