"""Creating rooms: direct chats between two people and group rooms."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q

from chat import live_rooms
from chat.models import Membership, Room

User = get_user_model()

MAX_GROUP_MEMBERS = 50
MAX_GROUP_NAME = 50


class RoomError(ValueError):
    """A request to create a room that cannot be honoured."""


def search_people(viewer, query, limit=20):
    """Active users other than the viewer whose username or name matches."""
    query = (query or "").strip().lstrip("@")
    if not query:
        return User.objects.none()
    match = (
        Q(username__icontains=query)
        | Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
    )
    if " " in query:
        first, _, last = query.partition(" ")
        match |= Q(first_name__icontains=first, last_name__icontains=last.strip())
    return (
        User.objects.filter(match, is_active=True)
        .exclude(pk=viewer.pk)
        .order_by("username")[:limit]
    )


def get_or_create_direct_room(user, other):
    """The private room for exactly these two people, created if needed."""
    if other.pk == user.pk:
        raise RoomError("You can't start a chat with yourself.")
    if not other.is_active:
        raise RoomError("That account is not active.")

    # Count members in a separate query: annotating after the two membership
    # filters would count only the joined rows, not the room's full size.
    shared = Room.objects.filter(type=Room.RoomTypes.PRIVATE, members=user).filter(
        members=other
    )
    existing = (
        Room.objects.filter(pk__in=shared.values("pk"))
        .annotate(size=Count("members"))
        .filter(size=2)
        .order_by("created_at")
        .first()
    )
    if existing:
        return existing, False

    with transaction.atomic():
        names = sorted([user.username, other.username])
        room = Room.objects.create(
            name="-".join(names)[:MAX_GROUP_NAME], type=Room.RoomTypes.PRIVATE
        )
        room.members.add(user, other)
        live_rooms.room_added(room, [user, other])
    return room, True


def create_group_room(creator, name, usernames):
    """A group room named `name` with the creator and the given users."""
    name = (name or "").strip()
    if not name:
        raise RoomError("Give the group a name.")
    if len(name) > MAX_GROUP_NAME:
        raise RoomError(f"Group names can be at most {MAX_GROUP_NAME} characters.")

    wanted = {u.strip().lstrip("@") for u in usernames if u and u.strip()}
    wanted.discard(creator.username)
    if not wanted:
        raise RoomError("Add at least one other person.")
    if len(wanted) + 1 > MAX_GROUP_MEMBERS:
        raise RoomError(f"Groups can have at most {MAX_GROUP_MEMBERS} members.")

    members = list(User.objects.filter(username__in=wanted, is_active=True))
    missing = wanted - {m.username for m in members}
    if missing:
        raise RoomError("Unknown people: " + ", ".join(sorted(missing)) + ".")

    with transaction.atomic():
        room = Room.objects.create(
            name=name, type=Room.RoomTypes.GROUP, created_by=creator
        )
        Membership.objects.create(room=room, user=creator, is_admin=True)
        room.members.add(*members)
        live_rooms.room_added(room, [creator, *members])
    return room
