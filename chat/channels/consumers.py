import json
import time
import uuid
from enum import Enum

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.utils import timezone

from chat import presence
from chat.models import Message, Room
from chat.presenters import display_name, message_data
from chat.realtime import inbox_group, room_group

MAX_MESSAGE_LENGTH = 4000


class WSChatType(str, Enum):
    CLEAR_ROOM = "clear_room"
    CHAT_RESPONSE = "chat_response"
    SAVE_MESSAGE = "save_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    MESSAGE_UPDATED = "message_updated"
    READ = "read"
    TYPING = "typing"
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
    last_typing = 0.0

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

        self.room_group_name = room_group(self.room.id)
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

        # Membership can change while the socket is open (removed, left, group
        # deleted); check it on every frame rather than trusting connect().
        if not self.room.members.filter(pk=self.user.pk).exists():
            self.reject_open(403, "You're no longer in this chat", CloseCode.FORBIDDEN)
            return

        handlers = {
            WSChatType.SAVE_MESSAGE.value: self.handle_save_message,
            WSChatType.CLEAR_ROOM.value: self.handle_clear_room,
            WSChatType.EDIT_MESSAGE.value: self.handle_edit_message,
            WSChatType.DELETE_MESSAGE.value: self.handle_delete_message,
            WSChatType.READ.value: self.handle_read,
            WSChatType.TYPING.value: self.handle_typing,
        }
        handler = handlers.get(payload.get("type"))
        if handler is None:
            self.send_error("Invalid type")
            return
        handler(payload)

    # Handlers

    def clean_content(self, payload):
        """Trimmed message text, or None after sending the sender an error."""
        content = payload.get("message")
        if not isinstance(content, str) or not content.strip():
            self.send_error("Message cannot be empty")
            return None
        content = content.strip()
        if len(content) > MAX_MESSAGE_LENGTH:
            self.send_error(f"Message is longer than {MAX_MESSAGE_LENGTH} characters")
            return None
        return content

    def own_message(self, payload):
        """The sender's own, not deleted, message in this room named by `id`."""
        try:
            message_id = uuid.UUID(str(payload.get("id")))
        except ValueError:
            message_id = None
        message = (
            Message.objects.filter(
                id=message_id,
                room=self.room,
                user=self.user,
                deleted_at__isnull=True,
                kind=Message.Kinds.TEXT,
                visible_for=self.user,
            )
            .select_related("user")
            .first()
            if message_id
            else None
        )
        if message is None:
            self.send_error("You can only change your own messages", code=403)
        return message

    def broadcast_update(self, message):
        """Send the edit or delete only to people who can see the message
        (not those who cleared it or joined after it)."""
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": WSChatType.CHAT_RESPONSE.value,
                "data": {
                    "type": WSChatType.MESSAGE_UPDATED.value,
                    **message_data(message),
                },
                "visible_to": list(message.visible_for.values_list("pk", flat=True)),
            },
        )

    def handle_edit_message(self, payload):
        content = self.clean_content(payload)
        if content is None:
            return
        message = self.own_message(payload)
        if message is None:
            return
        if content != message.content:
            message.content = content
            message.edited_at = timezone.now()
            message.save(update_fields=["content", "edited_at"])
        self.broadcast_update(message)

    def handle_delete_message(self, payload):
        message = self.own_message(payload)
        if message is None:
            return
        message.deleted_at = timezone.now()
        message.content = ""
        message.save(update_fields=["deleted_at", "content"])
        self.broadcast_update(message)

    def handle_save_message(self, payload):
        content = self.clean_content(payload)
        if content is None:
            return

        message = Message.objects.create(
            content=content, room=self.room, user=self.user
        )
        members = list(self.room.members.all())
        message.visible_for.add(*members)
        presence.mark_read(self.user, self.room, message.created_at)

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": WSChatType.CHAT_RESPONSE.value,
                "data": {
                    "type": WSChatType.SAVE_MESSAGE.value,
                    **message_data(message),
                },
                "visible_to": [m.pk for m in members],
            },
        )
        self.notify_inboxes(message, members)

    def notify_inboxes(self, message, members):
        """Tell every member's inbox socket about new activity in this room."""
        data = message_data(message)
        for member in members:
            async_to_sync(self.channel_layer.group_send)(
                inbox_group(member.pk),
                {"type": "inbox.message", "room": str(self.room.id), "data": data},
            )

    def handle_read(self, payload):
        presence.mark_read(self.user, self.room)

    def handle_typing(self, payload):
        # At most one typing event per second per socket.
        now = time.monotonic()
        if now - self.last_typing < 1.0:
            return
        self.last_typing = now
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": WSChatType.CHAT_RESPONSE.value,
                "data": {
                    "type": WSChatType.TYPING.value,
                    "user": self.user.username,
                    "name": display_name(self.user),
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
        # Events about one message carry the pks of the people who may see it
        # (never sent on to the client); everything else goes to every socket.
        visible_to = event.get("visible_to")
        if visible_to is not None and self.user.pk not in visible_to:
            return
        self.send_json(event["data"])

    def membership_revoked(self, event):
        """Sent when someone is removed or leaves; only their sockets close."""
        if event["user_id"] == self.user.pk:
            self.reject_open(403, "You're no longer in this chat", CloseCode.FORBIDDEN)

    def room_deleted(self, event):
        self.reject_open(404, "This chat was deleted", CloseCode.NOT_FOUND)

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

    def reject_open(self, code, message, close_code):
        """Tell an open socket why, then close it."""
        self.send_error(message, code=code)
        self.close(code=close_code)

    @staticmethod
    def get_room(room_id):
        try:
            return Room.objects.get(id=uuid.UUID(str(room_id)))
        except (Room.DoesNotExist, ValueError, TypeError):
            return None


class InboxConsumer(WebsocketConsumer):
    """One socket per signed-in page: presence for the people you share rooms
    with, and activity (new messages, unread counts) in all your rooms.

    Client frames: {"type": "ping"} every 30 seconds keeps you online and
    returns a fresh presence snapshot. See docs/websocket-protocol.md.
    """

    group_name = None

    def connect(self):
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            self.close(code=CloseCode.UNAUTHENTICATED)
            return
        self.group_name = inbox_group(self.user.pk)
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        came_online = presence.open_connection(self.user, self.channel_name)
        if came_online:
            self.broadcast_presence(True)
        self.send_snapshot()

    def disconnect(self, close_code):
        if not self.group_name:
            return
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )
        if presence.close_connection(self.user, self.channel_name):
            self.broadcast_presence(False)

    def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "")
        except (TypeError, ValueError):
            return
        if isinstance(payload, dict) and payload.get("type") == "ping":
            presence.touch_connection(self.channel_name)
            self.send_snapshot()

    def broadcast_presence(self, online):
        for contact in presence.contacts_of(self.user):
            async_to_sync(self.channel_layer.group_send)(
                inbox_group(contact.pk),
                {
                    "type": "inbox.presence",
                    "user": self.user.username,
                    "online": online,
                },
            )

    def send_snapshot(self):
        online = presence.online_usernames(presence.contacts_of(self.user))
        self.send(
            text_data=json.dumps(
                {"type": "presence_snapshot", "online": sorted(online)}
            )
        )

    # Channel layer events

    def inbox_presence(self, event):
        self.send(
            text_data=json.dumps(
                {"type": "presence", "user": event["user"], "online": event["online"]}
            )
        )

    def inbox_room(self, event):
        """A room was added to or changed in this user's list."""
        self.send(text_data=json.dumps({"type": event["frame"], "room": event["room"]}))

    def inbox_room_removed(self, event):
        self.send(text_data=json.dumps({"type": "room_removed", "room": event["room"]}))

    def inbox_message(self, event):
        data = event["data"]
        room = Room.objects.filter(id=event["room"]).first()
        unread = presence.unread_count(self.user, room) if room else 0
        self.send(
            text_data=json.dumps(
                {
                    "type": "room_activity",
                    "room": event["room"],
                    "unread": unread,
                    "message": data,
                }
            )
        )
