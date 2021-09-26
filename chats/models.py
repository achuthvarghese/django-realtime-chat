import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

ROOM_TYPES = [
    ("private", "Private"),
    ("group", "Group"),
]

User = get_user_model()


class Room(models.Model):
    id = models.UUIDField(
        _("ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    type = models.CharField(
        _("type"),
        choices=ROOM_TYPES,
        default="private",
        max_length=10,
    )
    members = models.ManyToManyField(User)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    def __str__(self):
        return f"{self.type}: {self.id}"


class Message(models.Model):
    id = models.UUIDField(
        _("ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    text = models.CharField(_("message"), max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    def __str__(self):
        return f"{self.id}"
