"""Presence and read state.

Presence: each open inbox socket stores a Connection row and pings every 30
seconds. A user is online while one of their connections was seen within
ONLINE_WINDOW. This works across server processes and recovers from crashed
processes, whose rows simply go stale.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils import timezone

from chat.models import Connection, Mention, Message, ReadState, Room

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


# Unread and mention counts stop at this many per chat (badges show "99+"),
# so a chat with years of unread history costs no more than a busy day.
COUNT_CAP = 100


def _cap(n):
    return min(n, COUNT_CAP)


def _for_you(user, check_room=True):
    """Messages "for" `user` in a group: they mention them, or reply to one
    of their messages that they can still see. Direct chats never count
    (`check_room=False` when the caller already knows it's a group).
    Uncorrelated IN subqueries rather than joins, so counting with it
    doesn't multiply or drop rows and each subquery runs once."""
    for_you = Q(pk__in=Mention.objects.filter(user=user).values("message_id")) | Q(
        reply_to__in=Message.objects.filter(user=user, visible_for=user).values("pk")
    )
    if check_room:
        for_you &= Q(room__type=Room.RoomTypes.GROUP)
    return for_you


def _unread_messages(user):
    """Text messages from others that `user` can still see."""
    return Message.objects.filter(
        visible_for=user, deleted_at__isnull=True, kind=Message.Kinds.TEXT
    ).exclude(user=user)


def unread_and_mentions(user, room_ids):
    """{room_id: (unread, mentions)} for the given rooms: unread messages
    from others since the user last read each room (every one if they never
    opened it), and how many of those mention them or reply to one of their
    messages (always 0 in direct chats). Both stop at COUNT_CAP. One grouped
    query; each room's last read time comes from a subquery."""
    room_ids = list(room_ids)
    if not room_ids:
        return {}
    last_read = ReadState.objects.filter(user=user, room_id=OuterRef("room_id"))
    rows = (
        _unread_messages(user)
        .filter(room_id__in=room_ids)
        .annotate(read_at=Subquery(last_read.values("last_read_at")[:1]))
        .filter(Q(read_at__isnull=True) | Q(created_at__gt=F("read_at")))
        .values("room_id")
        .annotate(n=Count("pk"), m=Count("pk", filter=_for_you(user)))
        .values_list("room_id", "n", "m")
    )
    counts = {r: (0, 0) for r in room_ids}
    counts.update({room_id: (_cap(n), _cap(m)) for room_id, n, m in rows})
    return counts


def unread_counts(user, room_ids):
    """{room_id: unread count} for the given rooms (see unread_and_mentions)."""
    return {r: n for r, (n, _m) in unread_and_mentions(user, room_ids).items()}


def unread_count(user, room):
    return unread_counts(user, [room.pk])[room.pk]


def room_counts(user, room_id, group):
    """(unread, mentions) for one room, without loading the room (the inbox
    socket asks this for every new message). `group` says whether it's a
    group; direct chats always have 0 mentions. Reads the read state first
    so the counts use the (room, created_at) index range, and stops each
    count at COUNT_CAP rows: at most three small queries."""
    when = (
        ReadState.objects.filter(user=user, room_id=room_id)
        .values_list("last_read_at", flat=True)
        .first()
    )
    unread = _unread_messages(user).filter(room_id=room_id)
    if when is not None:
        unread = unread.filter(created_at__gt=when)
    n = unread.values("pk")[:COUNT_CAP].count()
    m = 0
    if group and n:
        m = (
            unread.filter(_for_you(user, check_room=False))
            .values("pk")[:COUNT_CAP]
            .count()
        )
    return n, m
