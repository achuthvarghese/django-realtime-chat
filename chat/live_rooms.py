"""Keep everyone's room list current without a reload.

Each function queues inbox frames to run after the current transaction
commits, so the summaries they send match what's in the database (and
nothing is sent if it rolls back).

| Frame          | Sent to                    | When                                      |
| -------------- | -------------------------- | ----------------------------------------- |
| `room_added`   | people who gain a room     | new direct chat, new group, added to one  |
| `room_changed` | every member               | group renamed                             |
| `room_removed` | people who lose a room     | removed, left (their other tabs), deleted |

Building the frames takes a fixed number of queries however many people
get them. A send that fails is logged and skipped: the change has already
been saved, and the other recipients still hear about it.

See docs/websocket-protocol.md#inbox-socket.
"""

import logging

from django.db import transaction

from chat import realtime
from chat.models import Room
from chat.presenters import room_changed_data, room_summaries_for_users

logger = logging.getLogger(__name__)


def _send(frame_type, room_id, user_pk, event):
    try:
        realtime.send_to_inbox(user_pk, event)
    except Exception as error:
        logger.warning(
            "Couldn't send %s for room %s to user %s (%s)",
            frame_type,
            room_id,
            user_pk,
            type(error).__name__,
        )


def _send_added(room_id, users):
    try:
        summaries = room_summaries_for_users(room_id, users)
    except Exception as error:
        logger.warning(
            "Couldn't build room_added for room %s (%s)",
            room_id,
            type(error).__name__,
        )
        return
    for user in users:
        summary = summaries.get(user.pk)
        if summary is not None:
            _send(
                "room_added",
                room_id,
                user.pk,
                {"type": "inbox.room", "frame": "room_added", "room": summary},
            )


def _send_changed(room_id):
    try:
        room = Room.objects.prefetch_related("members").filter(pk=room_id).first()
        if room is None or room.type != Room.RoomTypes.GROUP:
            return
        data = room_changed_data(room)
    except Exception as error:
        logger.warning(
            "Couldn't build room_changed for room %s (%s)",
            room_id,
            type(error).__name__,
        )
        return
    event = {"type": "inbox.room", "frame": "room_changed", "room": data}
    for member in room.members.all():
        _send("room_changed", room_id, member.pk, event)


def room_added(room, users):
    users = list(users)
    room_id = room.id
    transaction.on_commit(lambda: _send_added(room_id, users))


def room_changed(room):
    """A group's name changed: one partial room object for every member."""
    room_id = room.id
    transaction.on_commit(lambda: _send_changed(room_id))


def room_removed(room_id, user_pks):
    user_pks = list(user_pks)

    def send():
        event = {"type": "inbox.room_removed", "room": str(room_id)}
        for pk in user_pks:
            _send("room_removed", room_id, pk, event)

    transaction.on_commit(send)
