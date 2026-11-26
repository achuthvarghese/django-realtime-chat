"""Sending events to room and inbox sockets from anywhere (views, services).

Group names live here so the consumers and the HTTP side agree on them.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


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


def broadcast_frame(room_id, data):
    """Deliver `data` as a frame to every socket in the room."""
    send_to_room(room_id, {"type": "chat_response", "data": data})
