"""Presence and read state.

Presence: each open inbox socket stores a Connection row and pings every 30
seconds. A user is online while one of their connections was seen within
ONLINE_WINDOW. This works across server processes and recovers from crashed
processes, whose rows simply go stale.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from chat.models import Connection, Message, ReadState

User = get_user_model()

ONLINE_WINDOW = timedelta(seconds=90)
STALE_AFTER = timedelta(hours=1)


def fresh_since():
    return timezone.now() - ONLINE_WINDOW


def is_online(user):
    return Connection.objects.filter(user=user, last_seen__gte=fresh_since()).exists()


def contacts_of(user):
    """Everyone who shares at least one room with `user`, excluding them."""
    return User.objects.filter(rooms__members=user).exclude(pk=user.pk).distinct()


def online_usernames(users):
    return set(
        Connection.objects.filter(user__in=users, last_seen__gte=fresh_since())
        .values_list("user__username", flat=True)
        .distinct()
    )


def open_connection(user, channel_name):
    """Record a connection. Returns True if the user just came online."""
    was_online = is_online(user)
    now = timezone.now()
    Connection.objects.filter(last_seen__lt=now - STALE_AFTER).delete()
    Connection.objects.update_or_create(
        channel_name=channel_name, defaults={"user": user, "last_seen": now}
    )
    return not was_online


def touch_connection(channel_name):
    Connection.objects.filter(channel_name=channel_name).update(
        last_seen=timezone.now()
    )


def close_connection(user, channel_name):
    """Forget a connection. Returns True if the user just went offline."""
    Connection.objects.filter(channel_name=channel_name).delete()
    return not is_online(user)


def mark_read(user, room, when=None):
    ReadState.objects.update_or_create(
        user=user, room=room, defaults={"last_read_at": when or timezone.now()}
    )


def unread_counts(user, room_ids):
    """{room_id: unread count} for the given rooms, in one grouped query.
    A room the user has never opened counts every message from others."""
    room_ids = list(room_ids)
    if not room_ids:
        return {}
    last_read = dict(
        ReadState.objects.filter(user=user, room_id__in=room_ids).values_list(
            "room_id", "last_read_at"
        )
    )
    scope = Q(room_id__in=[r for r in room_ids if r not in last_read])
    for room_id, when in last_read.items():
        scope |= Q(room_id=room_id, created_at__gt=when)
    rows = (
        Message.objects.filter(scope, visible_for=user, deleted_at__isnull=True)
        .exclude(user=user)
        .values("room_id")
        .annotate(n=Count("pk"))
    )
    counts = {r: 0 for r in room_ids}
    counts.update({row["room_id"]: row["n"] for row in rows})
    return counts


def unread_count(user, room):
    return unread_counts(user, [room.pk])[room.pk]
