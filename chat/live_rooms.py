"""Keep everyone's room list current without a reload.

Each function queues inbox frames to run after the current transaction
commits, so the summaries they send match what's in the database.

| Frame          | Sent to                    | When                                      |
| -------------- | -------------------------- | ----------------------------------------- |
| `room_added`   | people who gain a room     | new direct chat, new group, added to one  |
| `room_changed` | every member               | group renamed                             |
| `room_removed` | people who lose a room     | removed, left (their other tabs), deleted |

See docs/websocket-protocol.md#inbox-socket.
"""

from django.db import transaction

from chat import realtime
from chat.presenters import room_summary


def _summary_frames(frame_type, room_id, users):
    for user in users:
        summary = room_summary(user, room_id)
        if summary is not None:
            realtime.send_to_inbox(
                user.pk, {"type": "inbox.room", "frame": frame_type, "room": summary}
            )


def room_added(room, users):
    users = list(users)
    transaction.on_commit(lambda: _summary_frames("room_added", room.id, users))


def room_changed(room):
    users = list(room.members.all())
    transaction.on_commit(lambda: _summary_frames("room_changed", room.id, users))


def room_removed(room_id, user_pks):
    user_pks = list(user_pks)

    def send():
        for pk in user_pks:
            realtime.send_to_inbox(
                pk, {"type": "inbox.room_removed", "room": str(room_id)}
            )

    transaction.on_commit(send)
