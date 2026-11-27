"""Plain-data views of rooms and messages for templates, JSON and sockets."""

from datetime import datetime
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db.models import Count, DateTimeField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from chat.models import Message, ReadState, Room
from chat.presence import unread_counts

User = get_user_model()


def initials(name):
    """Two-letter initials from letters and digits only: the first letter or
    digit of the first two words that have one, else the first two of the
    only such word, else "?". Punctuation and symbols are skipped, so
    "<img src=x>" gives "IS" and "@lee" gives "LE"."""
    words = ["".join(c for c in w if c.isalnum()) for w in (name or "").split()]
    words = [w for w in words if w]
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


def _visible_texts(room, user):
    """Text messages in `room` that `user` can still see (either may be an
    OuterRef)."""
    return Message.objects.filter(
        room=room, visible_for=user, deleted_at__isnull=True, kind=Message.Kinds.TEXT
    )


def _summary_row(room, user, last_content, last_at, last_user_id, unread):
    """One sidebar row. `room.members` must be prefetched."""
    members = list(room.members.all())
    title = room_title(room, user)
    others = [m for m in members if m.pk != user.pk]
    return {
        "id": str(room.id),
        "title": title,
        "initials": initials(title),
        "type": room.type,
        "member_count": len(members),
        "last_content": last_content or "",
        "last_at": last_at,
        "last_is_mine": last_user_id == user.pk,
        "unread": unread,
        "other_username": (
            others[0].username
            if room.type == Room.RoomTypes.PRIVATE and len(others) == 1
            else ""
        ),
        "member_usernames": [m.username for m in members],
        "sort_key": last_at or room.created_at,
    }


def _jsonable(row):
    """A rooms_for() row as the JSON room object (no sort key, ISO time)."""
    row = dict(row)
    row.pop("sort_key")
    row["last_at"] = row["last_at"].isoformat() if row["last_at"] else None
    return row


def rooms_for(user, room_ids=None):
    """The user's rooms, most recently active first, with the last message
    they can still see. `room_ids` limits it to those rooms."""
    visible = _visible_texts(OuterRef("pk"), user).order_by("-created_at")
    rooms = user.rooms.all()
    if room_ids is not None:
        rooms = rooms.filter(pk__in=room_ids)
    rooms = rooms.prefetch_related("members").annotate(
        last_content=Subquery(visible.values("content")[:1]),
        last_at=Subquery(visible.values("created_at")[:1]),
        last_user_id=Subquery(visible.values("user_id")[:1]),
    )
    rooms = list(rooms)
    unread = unread_counts(user, [r.pk for r in rooms])
    summaries = [
        _summary_row(
            room,
            user,
            room.last_content,
            room.last_at,
            room.last_user_id,
            unread[room.pk],
        )
        for room in rooms
    ]
    summaries.sort(key=lambda r: r["sort_key"], reverse=True)
    return summaries


def room_summaries(user):
    """Every sidebar row for `user` as JSON room objects, most recent first.
    The list uses it to resync after a reconnect."""
    return [_jsonable(row) for row in rooms_for(user)]


def room_summary(user, room_id):
    """One room's sidebar row for `user`, ready for JSON (or None if they're
    not a member). Used to add or refresh rooms in the list live."""
    rows = rooms_for(user, room_ids=[room_id])
    return _jsonable(rows[0]) if rows else None


# Before a member first opens a room, every message from others is unread.
_NEVER_READ = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)


def room_summaries_for_users(room_id, users):
    """{user pk: room object} for one room seen by many people, in a fixed
    number of queries however many there are. People who aren't members are
    left out. Each object equals room_summary(user, room_id)."""
    room = Room.objects.filter(pk=room_id).prefetch_related("members").first()
    if room is None:
        return {}
    member_pks = {m.pk for m in room.members.all()}
    pks = [u.pk for u in users if u.pk in member_pks]
    if not pks:
        return {}
    visible = _visible_texts(room_id, OuterRef("pk"))
    latest = visible.order_by("-created_at")
    last_read = ReadState.objects.filter(user=OuterRef("pk"), room=room_id).values(
        "last_read_at"
    )[:1]
    unread = (
        visible.exclude(user=OuterRef("pk"))
        .filter(created_at__gt=OuterRef("last_read_at"))
        .order_by()
        .values("room")
        .annotate(n=Count("pk"))
        .values("n")
    )
    viewers = (
        User.objects.filter(pk__in=pks)
        .annotate(
            last_content=Subquery(latest.values("content")[:1]),
            last_at=Subquery(latest.values("created_at")[:1]),
            last_user_id=Subquery(latest.values("user_id")[:1]),
            last_read_at=Coalesce(
                Subquery(last_read), Value(_NEVER_READ, output_field=DateTimeField())
            ),
        )
        .annotate(unread=Coalesce(Subquery(unread), 0))
    )
    return {
        viewer.pk: _jsonable(
            _summary_row(
                room,
                viewer,
                viewer.last_content,
                viewer.last_at,
                viewer.last_user_id,
                viewer.unread,
            )
        )
        for viewer in viewers
    }


def room_changed_data(room):
    """The partial room object for `room_changed`: the same for every member,
    so it's built once. Only for groups (direct rooms are never renamed).
    `room.members` should be prefetched."""
    members = list(room.members.all())
    return {
        "id": str(room.id),
        "title": room.name,
        "initials": initials(room.name),
        "member_count": len(members),
        "member_usernames": [m.username for m in members],
    }


def message_data(message):
    """The shape sent to the browser for one message (also used over the
    WebSocket; see docs/websocket-protocol.md)."""
    name = display_name(message.user)
    return {
        "id": str(message.id),
        "message": "" if message.is_deleted else message.content,
        "user": message.user.username,
        "name": name,
        "initials": initials(name),
        "created_at": message.created_at.isoformat(),
        "edited": message.edited_at is not None and not message.is_deleted,
        "deleted": message.is_deleted,
        "kind": message.kind,
    }
