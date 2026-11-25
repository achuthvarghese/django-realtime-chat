import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from chat import presence
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

PAGE_SIZE = 50


def history_page(room, user, before=None, limit=PAGE_SIZE):
    """Up to `limit` messages the user can see, oldest first, ending just
    before `before` (a Message) when given. Returns (messages, has_more)."""
    qs = Message.objects.filter(room=room, visible_for=user).select_related("user")
    if before is not None:
        qs = qs.filter(
            Q(created_at__lt=before.created_at)
            | Q(created_at=before.created_at, id__lt=before.id)
        )
    page = list(qs.order_by("-created_at", "-id")[: limit + 1])
    has_more = len(page) > limit
    return [message_data(m) for m in reversed(page[:limit])], has_more


def room_url(room):
    return f"{reverse('chat:chat')}?room={room.id}"


@login_required
def chat(request):
    rooms = rooms_for(request.user)
    room = None
    room_summary = None
    room_messages = []
    has_more = False

    room_id = request.GET.get("room")
    if room_id:
        try:
            room = request.user.rooms.get(id=uuid.UUID(room_id))
        except (ValueError, request.user.rooms.model.DoesNotExist):
            # Unknown ids and rooms the user is not a member of look the same.
            raise Http404("Room not found")
        presence.mark_read(request.user, room)
        room_summary = next(r for r in rooms if r["id"] == str(room.id))
        room_summary["unread"] = 0
        room_messages, has_more = history_page(room, request.user)

    me = display_name(request.user)
    context = {
        "title": room_summary["title"] if room_summary else "Chats",
        "rooms": rooms,
        "room": room,
        "room_summary": room_summary,
        "room_messages": room_messages,
        "history": {"has_more": has_more, "page_size": PAGE_SIZE},
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


@login_required
@require_GET
def room_history(request, room_id):
    """Older messages for infinite scroll: ?before=<message id>&limit=<1..100>."""
    room = get_object_or_404(request.user.rooms, id=room_id)
    before = None
    if request.GET.get("before"):
        try:
            before = Message.objects.get(id=uuid.UUID(request.GET["before"]), room=room)
        except (ValueError, Message.DoesNotExist):
            return JsonResponse({"error": "Unknown message"}, status=400)
    try:
        limit = max(1, min(100, int(request.GET.get("limit", PAGE_SIZE))))
    except ValueError:
        limit = PAGE_SIZE
    messages_, has_more = history_page(room, request.user, before, limit)
    return JsonResponse({"messages": messages_, "has_more": has_more})
