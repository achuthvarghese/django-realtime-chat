import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from chat.models import Message
from chat.presenters import display_name, initials, message_data, rooms_for

HISTORY_LIMIT = 200


@login_required
def chat(request):
    rooms = rooms_for(request.user)
    room = None
    room_summary = None
    room_messages = []

    room_id = request.GET.get("room")
    if room_id:
        try:
            room = request.user.rooms.get(id=uuid.UUID(room_id))
        except (ValueError, request.user.rooms.model.DoesNotExist):
            # Unknown ids and rooms the user is not a member of look the same.
            raise Http404("Room not found")
        room_summary = next(r for r in rooms if r["id"] == str(room.id))
        recent = (
            Message.objects.filter(room=room, visible_for=request.user)
            .select_related("user")
            .order_by("-created_at")[:HISTORY_LIMIT]
        )
        room_messages = [message_data(m) for m in reversed(recent)]

    me = display_name(request.user)
    context = {
        "title": room_summary["title"] if room_summary else "Chats",
        "rooms": rooms,
        "room": room,
        "room_summary": room_summary,
        "room_messages": room_messages,
        "me": {"username": request.user.username, "name": me, "initials": initials(me)},
    }
    return render(request, "chat/chat.html", context)
