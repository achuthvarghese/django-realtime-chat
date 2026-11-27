"""Keep everyone's room list current without a reload.

Each function queues inbox frames to run after the current transaction
commits, so the summaries they send match what's in the database (and
nothing is sent if it rolls back).

| Frame          | Sent to                        | When                                      |
| -------------- | ------------------------------ | ----------------------------------------- |
| `room_added`   | people who gain a room         | new direct chat, new group, added to one  |
| `room_changed` | members (not the newly added)  | group renamed, people added, removed, left |
| `room_removed` | people who lose a room         | removed, left (their other tabs), deleted |
| `room_refresh` | people who can see the message | a message was edited or deleted           |

Building the frames takes a fixed number of queries however many people
get them. A send that fails is skipped (the change is already saved and the
others still hear about it); each action logs one warning with the room id,
the failed user pks and how many failed.

See docs/websocket-protocol.md#inbox-socket.
"""

import logging

from django.db import transaction

from chat import realtime
from chat.models import Room
from chat.presenters import room_changed_data, room_summaries_for_users

logger = logging.getLogger(__name__)


def _send_all(frame_type, room_id, events):
    """Send each (user pk, event); log one warning if any fail."""
    failed = []
    error_name = None
    for user_pk, event in events:
        try:
            realtime.send_to_inbox(user_pk, event)
        except Exception as error:
            failed.append(user_pk)
            error_name = type(error).__name__
    if failed:
        logger.warning(
            "Couldn't send %s for room %s to %d of %d users %s (%s)",
            frame_type,
            room_id,
            len(failed),
            len(events),
            failed,
            error_name,
        )


def _build_failed(frame_type, room_id):
    logger.warning("Couldn't build %s for room %s", frame_type, room_id, exc_info=True)


def _send_added(room_id, users):
    try:
        summaries = room_summaries_for_users(room_id, users)
    except Exception:
        _build_failed("room_added", room_id)
        return
    events = [
        (
            user.pk,
            {"type": "inbox.room", "frame": "room_added", "room": summaries[user.pk]},
        )
        for user in users
        if user.pk in summaries
    ]
    _send_all("room_added", room_id, events)


def _send_changed(room_id, skip):
    try:
        room = Room.objects.prefetch_related("members").filter(pk=room_id).first()
        if room is None or room.type != Room.RoomTypes.GROUP:
            return
        data = room_changed_data(room)
    except Exception:
        _build_failed("room_changed", room_id)
        return
    event = {"type": "inbox.room", "frame": "room_changed", "room": data}
    events = [(m.pk, event) for m in room.members.all() if m.pk not in skip]
    _send_all("room_changed", room_id, events)


def room_added(room, users):
    users = list(users)
    room_id = room.id
    transaction.on_commit(lambda: _send_added(room_id, users))


def room_changed(room, skip=()):
    """A group's name or members changed: one partial room object for every
    member at commit time, except the user pks in `skip` (people who were
    just added get `room_added` instead)."""
    room_id = room.id
    skip = set(skip)
    transaction.on_commit(lambda: _send_changed(room_id, skip))


def room_removed(room_id, user_pks):
    event = {"type": "inbox.room_removed", "room": str(room_id)}
    events = [(pk, event) for pk in user_pks]
    transaction.on_commit(lambda: _send_all("room_removed", room_id, events))


def room_refresh(room_id, user_pks):
    """A message was edited or deleted, so the room's preview may have
    changed: ask these people's lists to refetch its row. Pass only people
    who can see the message."""
    event = {"type": "inbox.room_refresh", "room": str(room_id)}
    events = [(pk, event) for pk in user_pks]
    transaction.on_commit(lambda: _send_all("room_refresh", room_id, events))
