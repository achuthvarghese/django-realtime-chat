import json
import uuid
from enum import Enum

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.utils import timezone

from chat.models import Message, Room
from chat.presenters import message_data

MAX_MESSAGE_LENGTH = 4000


class WSChatType(str, Enum):
    CLEAR_ROOM = "clear_room"
    CHAT_RESPONSE = "chat_response"
    SAVE_MESSAGE = "save_message"
    ERROR = "error"


class CloseCode:
    """Application close codes (4000-4999 are reserved for applications)."""

    UNAUTHENTICATED = 4401
    FORBIDDEN = 4403
    NOT_FOUND = 4404


class ChatConsumer(WebsocketConsumer):
    """One WebSocket per open room.

    Only authenticated members of the room may connect. Clients send JSON
    objects with a ``type`` of ``save_message`` or ``clear_room``; see
    docs/websocket-protocol.md.
    """

    room = None
    room_group_name = None

    def connect(self):
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            self.close(code=CloseCode.UNAUTHENTICATED)
            return

        self.room = self.get_room(self.scope["url_route"]["kwargs"].get("room_id"))
        if self.room is None:
            self.reject(404, "Room not found", CloseCode.NOT_FOUND)
            return
        if not self.room.members.filter(pk=self.user.pk).exists():
            self.reject(403, "You are not a member of this room", CloseCode.FORBIDDEN)
            return

        self.room_group_name = f"chat_room_{self.room.id.hex}"
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        if self.room_group_name:
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name, self.channel_name
            )

    def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "")
        except (TypeError, ValueError):
            self.send_error("Invalid JSON")
            return
        if not isinstance(payload, dict):
            self.send_error("Expected a JSON object")
            return

        handlers = {
            WSChatType.SAVE_MESSAGE.value: self.handle_save_message,
            WSChatType.CLEAR_ROOM.value: self.handle_clear_room,
        }
        handler = handlers.get(payload.get("type"))
        if handler is None:
            self.send_error("Invalid type")
            return
        handler(payload)

    # Handlers

    def handle_save_message(self, payload):
        content = payload.get("message")
        if not isinstance(content, str) or not content.strip():
            self.send_error("Message cannot be empty")
            return
        content = content.strip()
        if len(content) > MAX_MESSAGE_LENGTH:
            self.send_error(f"Message is longer than {MAX_MESSAGE_LENGTH} characters")
            return

        message = Message.objects.create(
            content=content, room=self.room, user=self.user
        )
        message.visible_for.add(*self.room.members.all())

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": WSChatType.CHAT_RESPONSE.value,
                "data": {
                    "type": WSChatType.SAVE_MESSAGE.value,
                    **message_data(message),
                },
            },
        )

    def handle_clear_room(self, payload):
        # Clearing only hides messages for the requesting user, so only that
        # user's socket is told about it.
        self.user.visible_for.remove(*self.room.messages.all())
        self.send_json(
            {
                "type": WSChatType.CLEAR_ROOM.value,
                "cleared": True,
                "for": self.user.username,
            }
        )

    # Channel layer events

    def chat_response(self, event):
        self.send_json(event["data"])

    # Helpers

    def send_json(self, data):
        self.send(text_data=json.dumps(data, default=str))

    def send_error(self, message, code=400):
        self.send_json(
            {
                "type": WSChatType.ERROR.value,
                "code": code,
                "message": message,
                "ts": timezone.now().isoformat(),
            }
        )

    def reject(self, code, message, close_code):
        """Accept briefly so the client receives the reason, then close."""
        self.accept()
        self.send_error(message, code=code)
        self.close(code=close_code)

    @staticmethod
    def get_room(room_id):
        try:
            return Room.objects.get(id=uuid.UUID(str(room_id)))
        except (Room.DoesNotExist, ValueError, TypeError):
            return None
