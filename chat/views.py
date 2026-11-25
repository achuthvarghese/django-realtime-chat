import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from chat.models import Message
from chat.presenters import display_name, initials, message_data, rooms_for
from chat.services import (
    MAX_GROUP_NAME,
    RoomError,
    create_group_room,
    get_or_create_direct_room,
    search_people,
)

User = get_user_model()

HISTORY_LIMIT = 200


def room_url(room):
    return f"{reverse('chat:chat')}?room={room.id}"


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
        "max_group_name": MAX_GROUP_NAME,
    }
    return render(request, "chat/chat.html", context)


@login_required
@require_GET
def people(request):
    """People search for starting chats: JSON list of matching users."""
    results = []
    for user in search_people(request.user, request.GET.get("q")):
        name = display_name(user)
        results.append(
            {"username": user.username, "name": name, "initials": initials(name)}
        )
    return JsonResponse({"results": results})


@login_required
@require_POST
def start_direct(request):
    other = get_object_or_404(User, username=request.POST.get("username", ""))
    try:
        room, _created = get_or_create_direct_room(request.user, other)
    except RoomError as error:
        messages.error(request, str(error))
        return redirect("chat:chat")
    return redirect(room_url(room))


@login_required
@require_POST
def start_group(request):
    try:
        room = create_group_room(
            request.user, request.POST.get("name"), request.POST.getlist("members")
        )
    except RoomError as error:
        messages.error(request, str(error))
        return redirect("chat:chat")
    messages.success(request, f"Created {room.name}.")
    return redirect(room_url(room))
