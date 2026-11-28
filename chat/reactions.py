"""Reactions: one of a fixed set of emoji on a text message.

Anyone who can see a text message can react to it (their own included),
with several emoji each but one of each kind. Changes reach the room sockets
of everyone who can still see the message as a `reactions_updated` frame
(see docs/websocket-protocol.md). Reactions don't touch the room list,
previews or unread counts.
"""

import time
import uuid

from django.core.cache import cache
from django.db import IntegrityError, transaction

from chat import realtime
from chat.models import Message, Reaction, ReactionEmoji
from chat.presenters import reactions_for_message

# One answer for every reason a reaction is refused (unknown or malformed
# id, another room, hidden from the sender, deleted, a system event, an
# unknown emoji, a bad `on`), so the error says nothing about messages the
# sender can't see.
CANT_REACT = "You can't react to that message"

# At most RATE_LIMIT react frames per RATE_WINDOW seconds per user, across
# all their sockets (refused frames count too); the rest get a 429.
RATE_LIMIT = 10
RATE_WINDOW = 5.0


class CantReact(Exception):
    """The react frame names something the sender can't react with or to."""


def _message_id(value):
    if not isinstance(value, str):
        raise CantReact
    try:
        return uuid.UUID(value)
    except ValueError:
        raise CantReact from None


def rate_limited(user_pk, now=None):
    """True when `user_pk` has sent RATE_LIMIT react frames in the last
    RATE_WINDOW seconds; otherwise counts this one. The window lives in the
    Django cache, so every socket of the user (in any process sharing the
    cache) draws on it and reconnecting doesn't reset it. The read and write
    aren't atomic: racing frames can slip a few over, never far."""
    now = time.time() if now is None else now
    key = f"react:{user_pk}"
    recent = [t for t in cache.get(key, []) if now - t < RATE_WINDOW]
    if len(recent) >= RATE_LIMIT:
        return True
    recent.append(now)
    cache.set(key, recent, timeout=int(RATE_WINDOW) + 1)
    return False


def _target(user, room, message_id):
    """The text message the sender may react to, or raise CantReact."""
    message = Message.objects.filter(
        id=message_id,
        room=room,
        kind=Message.Kinds.TEXT,
        deleted_at__isnull=True,
        visible_for=user,
    ).first()
    if message is None:
        raise CantReact
    return message


def reactions_frame(message):
    return {
        "type": "reactions_updated",
        "id": str(message.id),
        "reactions": reactions_for_message(message),
    }


def audience(message, room):
    """Pks of current room members who can still see `message`: not those
    who cleared it, joined after it, or left."""
    return list(
        message.visible_for.filter(memberships__room=room).values_list("pk", flat=True)
    )


def set_reaction(user, room, message_id, emoji, on):
    """Turn `user`'s `emoji` on `message_id` in `room` on or off.

    Idempotent: turning on a reaction that is already on (or off one that is
    off) succeeds without a change. Returns (frame, changed), where `frame` is
    the message's current `reactions_updated` frame. A change is sent to the
    message's audience once the transaction commits. Raises CantReact for
    anything the sender may not do."""
    message_id = _message_id(message_id)
    if not isinstance(emoji, str) or emoji not in ReactionEmoji.values:
        raise CantReact
    if not isinstance(on, bool):
        raise CantReact

    # Refused frames and no-ops are settled by reads alone, without taking
    # the write lock.
    message = _target(user, room, message_id)
    already = Reaction.objects.filter(message=message, user=user, emoji=emoji).exists()
    if already == on:
        return reactions_frame(message), False

    # Check again and write in one IMMEDIATE transaction (it holds the write
    # lock throughout), so a delete can't slip in between and leave a
    # reaction on a deleted message.
    with transaction.atomic():
        message = _target(user, room, message_id)
        if on:
            try:
                with transaction.atomic():
                    Reaction.objects.create(message=message, user=user, emoji=emoji)
                changed = True
            except IntegrityError:
                changed = False  # added meanwhile by another socket
        else:
            deleted, _ = Reaction.objects.filter(
                message=message, user=user, emoji=emoji
            ).delete()
            changed = deleted > 0
        frame = reactions_frame(message)
        if changed:
            realtime.broadcast_frame_after_commit(
                room.id, frame, visible_to=audience(message, room)
            )
    return frame, changed
