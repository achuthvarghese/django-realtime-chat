from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from chat.models import Message, Room


@login_required
def chat(request):
    rooms = request.user.rooms.all()
    room_messages = []
    current_room = request.GET.get("room", None)
    room = None
    try:
        room = Room.objects.get(id=current_room)
        room_messages = Message.objects.filter(
            room=current_room, visible_for__in=[request.user.id]
        )
    except Room.DoesNotExist:
        pass
    template = "chat/chat.html"
    context = {
        "title": "Home",
        "rooms": rooms,
        "room": room,
        "room_messages": room_messages,
    }
    return render(request, template, context)
