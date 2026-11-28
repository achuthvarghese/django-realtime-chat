"""Plain-data views of rooms and messages for templates, JSON and sockets."""

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, F, Max, OuterRef, Q, Subquery, Value

from chat.mentions import find_mentions
from chat.models import Mention, Message, Reaction, ReactionEmoji, ReadState, Room
from chat.presence import unread_and_mentions

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


def _summary_row(room, user, last_content, last_at, last_user_id, unread, mentions=0):
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
        # Unread messages that mention the user or reply to them (groups).
        "mentions": mentions,
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
    # Ties on time go to the highest id (room_summaries_for_users agrees).
    visible = _visible_texts(OuterRef("pk"), user).order_by("-created_at", "-id")
    rooms = user.rooms.all()
    if room_ids is not None:
        rooms = rooms.filter(pk__in=room_ids)
    rooms = rooms.prefetch_related("members").annotate(
        last_content=Subquery(visible.values("content")[:1]),
        last_at=Subquery(visible.values("created_at")[:1]),
        last_user_id=Subquery(visible.values("user_id")[:1]),
    )
    rooms = list(rooms)
    counts = unread_and_mentions(user, [r.pk for r in rooms])
    summaries = [
        _summary_row(
            room,
            user,
            room.last_content,
            room.last_at,
            room.last_user_id,
            *counts[room.pk],
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


def room_summaries_for_users(room_id, users):
    """{user pk: room object} for one room seen by many people. People who
    aren't members are left out. Each object equals room_summary(user,
    room_id).

    Set-based: a fixed number of queries, each a grouped scan of the room's
    visibility rows for these people, so the cost doesn't multiply people by
    room history (adding 40 people to a long-running group stays fast)."""
    room = Room.objects.filter(pk=room_id).prefetch_related("members").first()
    if room is None:
        return {}
    member_pks = {m.pk for m in room.members.all()}
    pks = [u.pk for u in users if u.pk in member_pks]
    if not pks:
        return {}
    seen = Message.visible_for.through.objects.filter(
        user_id__in=pks,
        message__room=room_id,
        message__deleted_at__isnull=True,
        message__kind=Message.Kinds.TEXT,
    )

    # Newest message time each person can see, then the rows at those times
    # (only messages that person can see; ties go to the highest id, as in
    # rooms_for).
    last_at = dict(
        seen.values("user_id")
        .annotate(t=Max("message__created_at"))
        .values_list("user_id", "t")
    )
    latest = {}
    if last_at:
        rows = seen.filter(message__created_at__in=set(last_at.values())).values_list(
            "user_id",
            "message_id",
            "message__content",
            "message__created_at",
            "message__user_id",
        )
        for user_id, message_id, content, created_at, author_id in rows:
            if created_at != last_at[user_id]:
                continue
            best = latest.get(user_id)
            if best is None or message_id > best[0]:
                latest[user_id] = (message_id, content, created_at, author_id)

    # Unread: messages from others after each person's last read (all of
    # them if they never opened the room), and in groups how many of those
    # mention that person or reply to one of their messages.
    reads = dict(
        ReadState.objects.filter(room=room_id, user_id__in=pks).values_list(
            "user_id", "last_read_at"
        )
    )
    scope = Q(user_id__in=[pk for pk in pks if pk not in reads])
    for pk, when in reads.items():
        scope |= Q(user_id=pk, message__created_at__gt=when)
    if room.type == Room.RoomTypes.GROUP:
        for_you = Count(
            "pk",
            filter=Q(
                Exists(
                    Mention.objects.filter(
                        message=OuterRef("message_id"), user=OuterRef("user_id")
                    )
                )
            )
            | Q(
                Exists(
                    Message.objects.filter(
                        pk=OuterRef("message__reply_to_id"), user=OuterRef("user_id")
                    )
                )
            ),
        )
    else:
        for_you = Value(0)
    counts = {
        user_id: (n, m)
        for user_id, n, m in seen.filter(scope)
        .exclude(message__user_id=F("user_id"))
        .values("user_id")
        .annotate(n=Count("pk"), m=for_you)
        .values_list("user_id", "n", "m")
    }

    summaries = {}
    for viewer in User.objects.filter(pk__in=pks):
        _id, content, created_at, author_id = latest.get(
            viewer.pk, (None, None, None, None)
        )
        summaries[viewer.pk] = _jsonable(
            _summary_row(
                room,
                viewer,
                content,
                created_at,
                author_id,
                *counts.get(viewer.pk, (0, 0)),
            )
        )
    return summaries


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


REPLY_EXCERPT_LENGTH = 200


def reply_excerpt(content):
    """The quoted original on one line: whitespace runs collapsed to one
    space, trimmed, at most REPLY_EXCERPT_LENGTH characters."""
    return " ".join((content or "").split())[:REPLY_EXCERPT_LENGTH]


def reply_data(message, visible):
    """The `reply_to` object for `message` as seen by a viewer who can
    (`visible`) or can't see the original. None for plain messages and for
    deleted replies. A viewer who can't see the original learns only its id.
    `message.reply_to.user` should be loaded (select_related)."""
    if message.reply_to_id is None or message.is_deleted:
        return None
    original = message.reply_to
    # Replies only quote messages from the same room (checked on save; this
    # guards against anything that slipped past).
    if original is None or not visible or original.room_id != message.room_id:
        return {"id": str(message.reply_to_id), "available": False}
    data = {
        "id": str(original.id),
        "available": True,
        "deleted": original.is_deleted,
        "user": original.user.username,
        "name": display_name(original.user),
    }
    if not original.is_deleted:
        data["excerpt"] = reply_excerpt(original.content)
    return data


# Names for the fixed reaction set (aria labels and tooltips), in display
# order. The keys match ReactionEmoji.
REACTION_NAMES = {
    ReactionEmoji.THUMBS_UP: "Thumbs up",
    ReactionEmoji.HEART: "Heart",
    ReactionEmoji.LAUGH: "Laughing",
    ReactionEmoji.WOW: "Surprised",
    ReactionEmoji.SAD: "Sad",
    ReactionEmoji.PARTY: "Party",
}
_REACTION_ORDER = {key: i for i, key in enumerate(ReactionEmoji.values)}


def reaction_emoji_table():
    """The reaction picker's data: [{key, char, label}] in display order."""
    return [
        {"key": key, "char": char, "label": REACTION_NAMES[key]}
        for key, char in ReactionEmoji.choices
    ]


def reactions_for_messages(message_ids):
    """{message id: `reactions` list} for these messages in one query.
    Messages without reactions are left out (use .get(id, []))."""
    message_ids = list(message_ids)
    if not message_ids:
        return {}
    rows = (
        Reaction.objects.filter(message_id__in=message_ids)
        .order_by("created_at", "id")
        .values_list(
            "message_id",
            "emoji",
            "user__username",
            "user__first_name",
            "user__last_name",
        )
    )
    # message id -> emoji -> [{user, name}], in reaction time order. Plain
    # tuples and one person dict per user keep heavy pages cheap.
    people = {}
    grouped = {}
    for message_id, emoji, username, first, last in rows:
        person = people.get(username)
        if person is None:
            # Same rule as display_name (User.get_full_name, else username).
            name = f"{first} {last}".strip() or username
            person = people[username] = {"user": username, "name": name}
        per_emoji = grouped.setdefault(message_id, {})
        per_emoji.setdefault(emoji, []).append(person)
    return {
        message_id: [
            {"emoji": emoji, "count": len(users), "users": users}
            for emoji, users in sorted(
                per_emoji.items(), key=lambda item: _REACTION_ORDER[item[0]]
            )
        ]
        for message_id, per_emoji in grouped.items()
    }


def reactions_for_message(message):
    """The `reactions` list for one message ([] for deleted and system
    messages, which can't have any)."""
    if message.is_deleted or message.is_system:
        return []
    return reactions_for_messages([message.pk]).get(message.pk, [])


class _Person:
    """Just enough of a user for find_mentions and the `mentions` list."""

    __slots__ = ("pk", "username", "data")

    def __init__(self, pk, username, name):
        self.pk = pk
        self.username = username
        self.data = {"user": username, "name": name}


def mentions_for_messages(messages):
    """{message id: `mentions` list} for these messages in one query, each
    list in order of appearance in the text. Messages without mentions are
    left out (use .get(id, [])). Deleted and system messages are skipped."""
    by_id = {m.pk: m for m in messages if not m.is_deleted and not m.is_system}
    if not by_id:
        return {}
    rows = Mention.objects.filter(message_id__in=list(by_id)).values_list(
        "message_id", "user_id", "user__username", "user__first_name", "user__last_name"
    )
    people = {}
    grouped = {}
    for message_id, user_id, username, first, last in rows:
        person = people.get(user_id)
        if person is None:
            # Same rule as display_name (User.get_full_name, else username).
            name = f"{first} {last}".strip() or username
            person = people[user_id] = _Person(user_id, username, name)
        grouped.setdefault(message_id, []).append(person)
    result = {}
    for message_id, mentioned in grouped.items():
        ordered = find_mentions(by_id[message_id].content, mentioned)
        # Anyone the text no longer names (it shouldn't happen) goes last.
        ordered += [p for p in mentioned if p not in ordered]
        result[message_id] = [p.data for p in ordered]
    return result


def mentions_data(users):
    """The `mentions` list for users from find_mentions, in that order."""
    return [{"user": u.username, "name": display_name(u)} for u in users]


def message_data(message, reply_visible=None, reactions=None, mentions=None):
    """The shape sent to the browser for one message (also used over the
    WebSocket; see docs/websocket-protocol.md).

    `reply_visible` says whether the viewer can see the message this one
    replies to; when None it comes from a `reply_visible` annotation (see
    views.history_page), and without one the quote is shown as unavailable,
    so nothing leaks by default.

    `reactions` is the message's `reactions` list (see
    reactions_for_messages); None means none, as for a new message.
    `mentions` is the message's `mentions` list (see mentions_for_messages
    and mentions_data); None means none. Deleted and system messages always
    get [] for both."""
    if reply_visible is None:
        reply_visible = getattr(message, "reply_visible", False)
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
        "reply_to": reply_data(message, bool(reply_visible)),
        "reactions": (
            []
            if reactions is None or message.is_deleted or message.is_system
            else reactions
        ),
        "mentions": (
            []
            if mentions is None or message.is_deleted or message.is_system
            else mentions
        ),
    }
