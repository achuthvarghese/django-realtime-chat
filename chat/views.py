import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from chat.models import Message


@login_required
def chat(request):
    rooms = request.user.rooms.all()
    room = None
    room_messages = Message.objects.none()

    room_id = request.GET.get("room")
    if room_id:
        try:
            room = rooms.get(id=uuid.UUID(room_id))
        except (ValueError, rooms.model.DoesNotExist):
            # Unknown ids and rooms the user is not a member of look the same.
            raise Http404("Room not found")
        room_messages = (
            Message.objects.filter(room=room, visible_for=request.user)
            .select_related("user")
            .order_by("created_at")
        )

    context = {
        "title": "Home",
        "rooms": rooms,
        "room": room,
        "room_messages": room_messages,
    }
    return render(request, "chat/chat.html", context)
