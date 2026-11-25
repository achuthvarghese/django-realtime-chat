"""Plain-data views of rooms and messages for templates, JSON and sockets."""

from django.db.models import OuterRef, Subquery

from chat.models import Message, Room


def initials(name):
    """Two-letter initials: first letters of the first two words, else the
    first two characters."""
    words = [w for w in (name or "").replace("@", "").split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def display_name(user):
    return user.get_full_name() or user.username


def room_title(room, viewer):
    """The other person's name for a private room, else the room name."""
    if room.type == Room.RoomTypes.PRIVATE:
        other = next((m for m in room.members.all() if m.pk != viewer.pk), None)
        if other is not None:
            return display_name(other)
    return room.name


def rooms_for(user):
    """The user's rooms, most recently active first, with the last message
    they can still see."""
    visible = Message.objects.filter(room=OuterRef("pk"), visible_for=user).order_by(
        "-created_at"
    )
    rooms = (
        user.rooms.all()
        .prefetch_related("members")
        .annotate(
            last_content=Subquery(visible.values("content")[:1]),
            last_at=Subquery(visible.values("created_at")[:1]),
            last_user_id=Subquery(visible.values("user_id")[:1]),
        )
    )
    summaries = []
    for room in rooms:
        title = room_title(room, user)
        summaries.append(
            {
                "id": str(room.id),
                "title": title,
                "initials": initials(title),
                "type": room.type,
                "member_count": len(room.members.all()),
                "last_content": room.last_content or "",
                "last_at": room.last_at,
                "last_is_mine": room.last_user_id == user.pk,
                "sort_key": room.last_at or room.created_at,
            }
        )
    summaries.sort(key=lambda r: r["sort_key"], reverse=True)
    return summaries


def message_data(message):
    """The shape sent to the browser for one message (also used over the
    WebSocket; see docs/websocket-protocol.md)."""
    name = display_name(message.user)
    return {
        "id": str(message.id),
        "message": message.content,
        "user": message.user.username,
        "name": name,
        "initials": initials(name),
        "created_at": message.created_at.isoformat(),
    }
