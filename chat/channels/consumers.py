import json
import logging
import time
import uuid
from enum import Enum

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from chat import live_rooms, mentions, presence, reactions
from chat.models import Message, Reaction, Room
from chat.presenters import (
    display_name,
    mentions_data,
    mentions_for_messages,
    message_data,
    reactions_for_message,
)
from chat.realtime import inbox_group, room_group

MAX_MESSAGE_LENGTH = 4000

# One answer for every reason a reply target is refused (unknown, another
# room, hidden from the sender, deleted, a system event), so the error says
# nothing about messages the sender can't see.
CANT_REPLY = "You can't reply to that message"

logger = logging.getLogger(__name__)


class CantReply(Exception):
    """The frame's `reply_to` names a message the sender can't reply to."""


class WSChatType(str, Enum):
    CLEAR_ROOM = "clear_room"
    CHAT_RESPONSE = "chat_response"
    SAVE_MESSAGE = "save_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    MESSAGE_UPDATED = "message_updated"
    READ = "read"
    TYPING = "typing"
    REACT = "react"
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
    # The type of the client frame being handled; error frames echo it as
    # "for" so the client can tell which request failed.
    current_frame = None

    def connect(self):
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            self.close(code=CloseCode.UNAUTHENTICATED)
            return

        self.room = self.get_room(self.scope["url_route"]["kwargs"].get("room_id"))
        if self.room is None:
            self.reject(404, "Room not found", CloseCode.NOT_FOUND)
            return

        # Join the group before checking membership: if the user is removed
        # in between, the revoke event reaches this socket. Checking first
        # would leave a window where the revoke is missed for good.
        group_name = room_group(self.room.id)
        async_to_sync(self.channel_layer.group_add)(group_name, self.channel_name)
        if not self.room.members.filter(pk=self.user.pk).exists():
            async_to_sync(self.channel_layer.group_discard)(
                group_name, self.channel_name
            )
            self.reject(403, "You are not a member of this room", CloseCode.FORBIDDEN)
            return
        self.room_group_name = group_name
        self.accept()

    def disconnect(self, close_code):
        if self.room_group_name:
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name, self.channel_name
            )

    def receive(self, text_data=None, bytes_data=None):
        if self.room_group_name is None:
            # Refused in connect() (unknown room or not a member) and closing:
            # ignore frames the client sent before it saw the close.
            return
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
            WSChatType.REACT.value: self.handle_react,
        }
        handler = handlers.get(payload.get("type"))
        if handler is None:
            self.send_error("Invalid type")
            return
        self.current_frame = payload["type"]
        try:
            handler(payload)
        finally:
            self.current_frame = None

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
            .select_related("user", "reply_to__user")
            .first()
            if message_id
            else None
        )
        if message is None:
            self.send_error("You can only change your own messages", code=403)
        return message

    def send_message_frame(
        self, frame_type, message, visible_to, reactions=None, mention_list=None
    ):
        """Send `message` as a `frame_type` frame to the room sockets of the
        users in `visible_to`. For a reply, those who can also see the
        original get its quote; the rest get only {"id", "available": false}
        (one extra query). `reactions` and `mention_list` are the message's
        `reactions` and `mentions` for message_data. Returns the pks in
        `visible_to` who can see the original (all of them for non-replies)."""
        visible_to = list(visible_to)
        # Deleted replies carry no quote (see presenters.reply_data).
        if message.reply_to_id is not None and not message.is_deleted:
            sees_original = set(
                Message.visible_for.through.objects.filter(
                    message_id=message.reply_to_id,
                    message__room_id=message.room_id,  # never quote across rooms
                    user_id__in=visible_to,
                ).values_list("user_id", flat=True)
            )
        else:
            sees_original = set(visible_to)
        groups = [
            (True, [pk for pk in visible_to if pk in sees_original]),
            (False, [pk for pk in visible_to if pk not in sees_original]),
        ]
        for reply_visible, pks in groups:
            if not pks:
                continue
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    "type": WSChatType.CHAT_RESPONSE.value,
                    "data": {
                        "type": frame_type,
                        **message_data(
                            message,
                            reply_visible=reply_visible,
                            reactions=reactions,
                            mentions=mention_list,
                        ),
                    },
                    "visible_to": pks,
                },
            )
        return sees_original

    def current_members(self):
        """The room's current members (enough of each for mentions)."""
        return list(self.room.members.only("pk", "username", "first_name", "last_name"))

    def current_viewers(self, message):
        """Current members who can still see `message`: not those who
        cleared it, joined after it, or left (even if their socket missed
        the revoke)."""
        return list(
            message.visible_for.filter(memberships__room=self.room).only(
                "pk", "username", "first_name", "last_name"
            )
        )

    def broadcast_update(self, message, mention_list=None):
        """Send the edit or delete only to people who can see the message
        (current_viewers), and ask the same people's room lists to refresh
        this room's preview (the counts may have changed too).
        `mention_list` is the message's `mentions` list; None loads it."""
        visible_to = [user.pk for user in self.current_viewers(message)]
        if mention_list is None:
            mention_list = mentions_for_messages([message]).get(message.pk, [])
        self.send_message_frame(
            WSChatType.MESSAGE_UPDATED.value,
            message,
            visible_to,
            reactions=reactions_for_message(message),
            mention_list=mention_list,
        )
        live_rooms.room_refresh(self.room.id, visible_to)

    def handle_edit_message(self, payload):
        content = self.clean_content(payload)
        if content is None:
            return
        message = self.own_message(payload)
        if message is None:
            return
        mentioned = None
        if content != message.content:
            # Mentions follow the new text, matched against current members
            # other than the author, exactly as for a new message. Who can
            # still see it isn't consulted, so the author's frame can't tell
            # who cleared their history; counts and frames filter by
            # visibility on their own.
            candidates = [u for u in self.current_members() if u.pk != self.user.pk]
            now = timezone.now()
            with transaction.atomic():
                # Only while it isn't deleted: an edit racing a delete from
                # another tab mustn't bring back text or mentions.
                saved = Message.objects.filter(
                    pk=message.pk, deleted_at__isnull=True
                ).update(content=content, edited_at=now)
                if not saved:
                    return
                message.content = content
                message.edited_at = now
                mentioned = mentions.sync_mentions(
                    message, mentions.find_mentions(content, candidates)
                )
        self.broadcast_update(
            message,
            mention_list=None if mentioned is None else mentions_data(mentioned),
        )

    def handle_delete_message(self, payload):
        message = self.own_message(payload)
        if message is None:
            return
        # A deleted message keeps no reactions.
        with transaction.atomic():
            message.deleted_at = timezone.now()
            message.content = ""
            message.save(update_fields=["deleted_at", "content"])
            Reaction.objects.filter(message=message).delete()
            mentions.clear_mentions(message)
        self.broadcast_update(message, mention_list=[])

    def reply_target(self, payload):
        """The message named by `reply_to` (locked to this room, a text
        message the sender can see and that isn't deleted), or None when the
        frame isn't a reply. Raises CantReply for anything else."""
        value = payload.get("reply_to")
        if value is None:
            return None
        try:
            original_id = uuid.UUID(value) if isinstance(value, str) else None
        except ValueError:
            original_id = None
        if original_id is None:
            raise CantReply
        original = (
            Message.objects.filter(
                id=original_id,
                room=self.room,
                kind=Message.Kinds.TEXT,
                deleted_at__isnull=True,
                visible_for=self.user,
            )
            .select_related("user")
            .first()
        )
        if original is None:
            raise CantReply
        return original

    def handle_save_message(self, payload):
        content = self.clean_content(payload)
        if content is None:
            return

        members = list(self.room.members.all())
        original = None
        try:
            # Check the target and insert together; if the original is
            # removed from the database in between, the foreign key fails at
            # commit and nothing is saved.
            with transaction.atomic():
                original = self.reply_target(payload)
                message = Message.objects.create(
                    content=content, room=self.room, user=self.user, reply_to=original
                )
                message.visible_for.add(*members)
                mentioned = mentions.sync_mentions(
                    message,
                    mentions.find_mentions(
                        content, [m for m in members if m.pk != self.user.pk]
                    ),
                    new=True,
                )
        except CantReply:
            self.send_error(CANT_REPLY)
            return
        except IntegrityError:
            if original is None:
                raise
            logger.info("Reply target vanished in room %s", self.room.id)
            self.send_error(CANT_REPLY)
            return
        presence.mark_read(self.user, self.room, message.created_at)

        mention_list = mentions_data(mentioned)
        sees_original = self.send_message_frame(
            WSChatType.SAVE_MESSAGE.value,
            message,
            [m.pk for m in members],
            mention_list=mention_list,
        )
        # A reply is "for" the original's author only while they can still
        # see the original (as in the room counts).
        reply_to_author = None
        if original is not None and original.user_id in sees_original:
            reply_to_author = original.user_id
        self.notify_inboxes(message, members, mentioned, reply_to_author, mention_list)

    def notify_inboxes(
        self, message, members, mentioned, reply_to_author, mention_list
    ):
        """Tell every member's inbox socket about new activity in this room.
        The room list never shows quotes, so `reply_to` is always null here
        (and the original's text can't reach anyone who can't see it).

        The event carries what each inbox needs to work out its own counts
        and `for_you` without loading the room: the room type, who was
        mentioned and whose message this replies to, if they can see it
        (server-side only)."""
        data = {**message_data(message, mentions=mention_list), "reply_to": None}
        event = {
            "type": "inbox.message",
            "room": str(self.room.id),
            "group": self.room.type == Room.RoomTypes.GROUP,
            "author": self.user.pk,
            "mentioned": [user.pk for user in mentioned],
            "reply_to_author": reply_to_author,
            "data": data,
        }
        for member in members:
            async_to_sync(self.channel_layer.group_send)(inbox_group(member.pk), event)

    def handle_read(self, payload):
        # A busy database (SQLite locked) shouldn't close the socket: the
        # next read frame or page load marks the room read anyway.
        try:
            presence.mark_read(self.user, self.room)
        except OperationalError as error:
            logger.warning(
                "Couldn't mark room %s read for user %s (%s)",
                self.room.id,
                self.user.pk,
                type(error).__name__,
            )

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

    def handle_react(self, payload):
        if reactions.rate_limited(self.user.pk):
            self.send_error("Slow down", code=429)
            return
        try:
            frame, changed = reactions.set_reaction(
                self.user,
                self.room,
                payload.get("id"),
                payload.get("emoji"),
                payload.get("on"),
            )
        except reactions.CantReact:
            self.send_error(reactions.CANT_REACT)
            return
        except OperationalError as error:
            # A busy database (SQLite locked) shouldn't close the socket; the
            # client may try again.
            logger.warning(
                "Couldn't save a reaction in room %s for user %s (%s)",
                self.room.id,
                self.user.pk,
                type(error).__name__,
            )
            self.send_error("Try again", code=503)
            return
        if not changed:
            # Already as asked: nobody else needs to hear, but this socket
            # gets the current state so it can settle its chips.
            self.send_json(frame)

    def handle_clear_room(self, payload):
        # Clearing only hides messages for the requesting user, so only that
        # user's socket is told about it.
        with transaction.atomic():
            self.user.visible_for.remove(*self.room.messages.all())
            # Their mentions in what they cleared go too, so nothing can
            # surface those messages for them later.
            mentions.forget_cleared(self.user, self.room.messages.all())
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
        if self.room_group_name is None:
            return  # refused in connect(); events queued before the discard
        visible_to = event.get("visible_to")
        if visible_to is not None and self.user.pk not in visible_to:
            return
        self.send_json(event["data"])

    def membership_revoked(self, event):
        """Sent when someone is removed or leaves; only their sockets close."""
        if self.room_group_name is None:
            return  # already refused and closing
        if event["user_id"] == self.user.pk:
            self.reject_open(403, "You're no longer in this chat", CloseCode.FORBIDDEN)

    def room_deleted(self, event):
        if self.room_group_name is None:
            return  # already refused and closing
        self.reject_open(404, "This chat was deleted", CloseCode.NOT_FOUND)

    # Helpers

    def send_json(self, data):
        self.send(text_data=json.dumps(data, default=str))

    def send_error(self, message, code=400):
        frame = {
            "type": WSChatType.ERROR.value,
            "code": code,
            "message": message,
            "ts": timezone.now().isoformat(),
        }
        if self.current_frame is not None:
            frame["for"] = self.current_frame
        self.send_json(frame)

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

    def inbox_room_refresh(self, event):
        """A message in the room was edited or deleted: refetch its row."""
        self.send(text_data=json.dumps({"type": "room_refresh", "room": event["room"]}))

    def inbox_message(self, event):
        """New message in one of this user's rooms: their capped counts for
        it (at most three small queries; the room isn't loaded) and whether
        it's for them."""
        unread, mention_count = presence.room_counts(
            self.user, uuid.UUID(event["room"]), bool(event.get("group"))
        )
        self.send(
            text_data=json.dumps(
                {
                    "type": "room_activity",
                    "room": event["room"],
                    "unread": unread,
                    "mentions": mention_count,
                    "for_you": self.for_you(event),
                    "message": event["data"],
                }
            )
        )

    def for_you(self, event):
        """ "mention" if the message names this user, "reply" if it answers
        one of their messages, else None (always None in direct chats and
        for the author)."""
        if not event.get("group") or event.get("author") == self.user.pk:
            return None
        if self.user.pk in event.get("mentioned", ()):
            return "mention"
        if event.get("reply_to_author") == self.user.pk:
            return "reply"
        return None
