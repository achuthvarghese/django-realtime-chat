"""Sending events to room and inbox sockets from anywhere (views, services).

Group names live here so the consumers and the HTTP side agree on them.

Services that change the database inside a transaction use the
`*_after_commit` helpers: the event goes out only once the change is saved
(never on rollback), in the order it was queued, and a failed send is logged
and skipped so it can't break the request.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)


def room_group(room_id):
    """Channel layer group for everyone with this room open."""
    return f"chat_room_{room_id.hex}"


def inbox_group(user_pk):
    """Channel layer group for all of one user's inbox sockets."""
    return f"inbox_user_{user_pk}"


def send_to_room(room_id, event):
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(room_group(room_id), event)


def send_to_inbox(user_pk, event):
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(inbox_group(user_pk), event)


def frame_event(data, visible_to=None):
    """A room event that delivers `data` as a frame to every socket in the
    room, or only to sockets of users whose pks are in `visible_to`."""
    event = {"type": "chat_response", "data": data}
    if visible_to is not None:
        event["visible_to"] = list(visible_to)
    return event


def broadcast_frame(room_id, data, visible_to=None):
    """Deliver `data` as a frame to the room's sockets now (see frame_event)."""
    send_to_room(room_id, frame_event(data, visible_to))


def _event_name(event):
    if event.get("type") == "chat_response":
        return f"chat_response/{event['data'].get('type')}"
    return event.get("type")


def _send_to_room_safely(room_id, event):
    try:
        send_to_room(room_id, event)
    except Exception as error:
        logger.warning(
            "Couldn't send %s to room %s (%s)",
            _event_name(event),
            room_id,
            type(error).__name__,
        )


def send_to_room_after_commit(room_id, event):
    """Send `event` to the room's sockets once the current transaction
    commits (at once outside one). Failures are logged, not raised."""
    transaction.on_commit(lambda: _send_to_room_safely(room_id, event))


def broadcast_frame_after_commit(room_id, data, visible_to=None):
    send_to_room_after_commit(room_id, frame_event(data, visible_to))
