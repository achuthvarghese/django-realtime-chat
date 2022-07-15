from django.shortcuts import render

from chat.models import Room


def chat(request):
    rooms = Room.objects.all()
    template = "chat/chat.html"
    context = {
        "title": "Home",
        "rooms": rooms,
    }
    return render(request, template, context)
