import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

User = get_user_model()


class Message(models.Model):
    class Kinds(models.TextChoices):
        TEXT = "text", "Text"
        # Group events ("Maya added Lee"); written by the server, never edited,
        # never counted as unread.
        SYSTEM = "system", "System"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )
    content = models.TextField()
    kind = models.CharField(max_length=10, choices=Kinds.choices, default=Kinds.TEXT)
    room = models.ForeignKey("Room", on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    visible_for = models.ManyToManyField(User, related_name="visible_for")
    # The message this one answers. Only text messages reply; if the original
    # is removed from the database the reply becomes a plain message.
    reply_to = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies",
    )
    # Current members named with @username when the message was saved or last
    # edited (see chat/mentions.py). Removed when the message is deleted.
    mentions = models.ManyToManyField(
        User, through="Mention", related_name="mentioned_in", blank=True
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["room", "created_at"])]
        constraints = [
            # Only text messages reply, and never to themselves.
            models.CheckConstraint(
                condition=Q(reply_to__isnull=True)
                | (Q(kind="text") & ~Q(reply_to=F("id"))),
                name="message_reply_valid",
            ),
        ]

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    @property
    def is_system(self):
        return self.kind == self.Kinds.SYSTEM


class ReactionEmoji(models.TextChoices):
    """The fixed set of reactions, in display order. The database stores the
    key; the label is the emoji character (names live in presenters)."""

    THUMBS_UP = "thumbs_up", "\N{THUMBS UP SIGN}"
    HEART = "heart", "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}"
    LAUGH = "laugh", "\N{FACE WITH TEARS OF JOY}"
    WOW = "wow", "\N{FACE WITH OPEN MOUTH}"
    SAD = "sad", "\N{CRYING FACE}"
    PARTY = "party", "\N{PARTY POPPER}"


class Reaction(models.Model):
    """One person's emoji on one text message. Several emoji per person, one
    of each. Deleting the message (or the user) removes it."""

    # No separate index: the unique constraint below starts with `message`.
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="reactions", db_index=False
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=16, choices=ReactionEmoji.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"], name="unique_reaction"
            ),
            models.CheckConstraint(
                condition=Q(emoji__in=ReactionEmoji.values),
                name="reaction_emoji_valid",
            ),
        ]

    def __str__(self):
        return f"{self.user} {self.emoji} on {self.message_id}"


class Mention(models.Model):
    """One member named with @username in one text message. Written in the
    same transaction as the message, recomputed on edit, removed on delete."""

    # No separate index: the unique constraint below starts with `message`.
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="mention_rows", db_index=False
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mention_rows"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "user"], name="unique_mention")
        ]

    def __str__(self):
        return f"@{self.user} in {self.message_id}"


class Room(models.Model):
    class RoomTypes(models.TextChoices):
        PRIVATE = "private", "Private"
        GROUP = "group", "Group"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )
    name = models.CharField(max_length=50)
    members = models.ManyToManyField(User, related_name="rooms", through="Membership")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    type = models.CharField(
        max_length=10, default=RoomTypes.PRIVATE, choices=RoomTypes.choices
    )

    def __str__(self):
        return f"{self.type} :: {self.name}"


class Membership(models.Model):
    """A user's place in a room. Uses the table Django originally created for
    Room.members, so existing memberships carried over unchanged."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    is_admin = models.BooleanField(default=False)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "chat_room_members"
        unique_together = [("room", "user")]
        ordering = ["joined_at", "id"]

    def __str__(self):
        return f"{self.user} in {self.room}{' (admin)' if self.is_admin else ''}"


class ReadState(models.Model):
    """When a member last read a room; later messages from others are unread."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="read_states")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="read_states")
    last_read_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "room"], name="unique_read_state")
        ]


class Connection(models.Model):
    """One open inbox socket. A user is online while any of their connections
    has been seen recently (see chat/presence.py)."""

    channel_name = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="connections")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(db_index=True)
