import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from chat import groups, presence
from chat.models import Message
from chat.presenters import (
    display_name,
    initials,
    message_data,
    room_summaries,
    room_summary,
    rooms_for,
)
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


# Shown for a room id the user can't open, whether it never existed, was
# deleted, or they were removed: the same words, so nothing leaks.
ROOM_UNAVAILABLE = (
    "That chat isn’t available. You may have been removed, or it was deleted."
)


@login_required
def chat(request):
    room = None
    summary = None
    room_messages = []
    has_more = False

    room_id = request.GET.get("room")
    if room_id:
        try:
            room = request.user.rooms.get(id=uuid.UUID(room_id))
        except (ValueError, request.user.rooms.model.DoesNotExist):
            # Unknown, deleted and forbidden rooms look the same.
            messages.info(request, ROOM_UNAVAILABLE)
            return redirect("chat:chat")
        presence.mark_read(request.user, room)

    rooms = rooms_for(request.user)
    if room is not None:
        summary = next((r for r in rooms if r["id"] == str(room.id)), None)
        if summary is None:
            # Removed (or the room deleted) between the two queries.
            messages.info(request, ROOM_UNAVAILABLE)
            return redirect("chat:chat")
        room_messages, has_more = history_page(room, request.user)

    me = display_name(request.user)
    context = {
        "title": summary["title"] if summary else "Chats",
        "rooms": rooms,
        "room": room,
        "room_summary": summary,
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


# Group details and management


def _member_room(request, room_id):
    return get_object_or_404(request.user.rooms, id=room_id)


@login_required
@require_GET
def room_details(request, room_id):
    """The Details panel for a room, as an HTML fragment."""
    room = _member_room(request, room_id)
    memberships = list(
        room.memberships.select_related("user").order_by("joined_at", "id")
    )
    viewer = next(m for m in memberships if m.user_id == request.user.pk)
    members = []
    for m in memberships:
        name = display_name(m.user)
        members.append(
            {
                "username": m.user.username,
                "name": name,
                "initials": initials(name),
                "is_admin": m.is_admin,
                "is_me": m.user_id == request.user.pk,
            }
        )
    members.sort(key=lambda m: (not m["is_me"], not m["is_admin"], m["name"].lower()))
    summary = next(r for r in rooms_for(request.user) if r["id"] == str(room.id))
    context = {
        "room": room,
        "summary": summary,
        "members": members,
        "is_group": room.type == room.RoomTypes.GROUP,
        "viewer_is_admin": viewer.is_admin,
        "admin_count": sum(1 for m in memberships if m.is_admin),
        "created_by": display_name(room.created_by) if room.created_by else None,
        "max_group_name": MAX_GROUP_NAME,
    }
    return render(request, "chat/partials/details.html", context)


def _group_response(request, room, error=None, gone=False, notice=None):
    """JSON for the panel's scripts; redirects with a notice otherwise."""
    wants_json = "application/json" in request.headers.get("Accept", "")
    target = reverse("chat:chat") if gone else room_url(room)
    if wants_json:
        if error:
            return JsonResponse({"ok": False, "error": error}, status=400)
        return JsonResponse({"ok": True, "redirect": target if gone else None})
    if error:
        messages.error(request, error)
    elif notice:
        messages.success(request, notice)
    return redirect(target)


@login_required
@require_POST
def group_action(request, room_id, action):
    room = _member_room(request, room_id)
    user = request.user
    try:
        if action == "add":
            groups.add_members(room, user, request.POST.getlist("members"))
        elif action == "rename":
            groups.rename(room, user, request.POST.get("name"))
        elif action in ("remove", "make-admin", "remove-admin"):
            target = get_object_or_404(User, username=request.POST.get("username", ""))
            if action == "remove":
                groups.remove_member(room, user, target)
            else:
                groups.set_admin(room, user, target, action == "make-admin")
        elif action == "leave":
            name = room.name
            groups.leave(room, user)
            return _group_response(request, room, gone=True, notice=f"You left {name}.")
        elif action == "delete":
            name = room.name
            groups.delete_group(room, user)
            return _group_response(request, room, gone=True, notice=f"Deleted {name}.")
        else:
            raise Http404
    except groups.GroupError as error:
        return _group_response(request, room, error=groups.error_message(error.code))
    return _group_response(request, room)


@login_required
@require_GET
def room_summary_view(request, room_id):
    """One sidebar row as JSON (used when the list hears of a room it lacks)."""
    summary = room_summary(request.user, room_id)
    if summary is None:
        raise Http404("Room not found")
    return JsonResponse(summary)


@login_required
@require_GET
def room_summaries_view(request):
    """Every sidebar row as JSON, most recent first. The list resyncs with it
    after its socket reconnects."""
    return JsonResponse({"rooms": room_summaries(request.user)})
