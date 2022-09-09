from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Message(models.Model):
    content = models.TextField()
    room = models.ForeignKey("Room", on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    visible_for = models.ManyToManyField(User, related_name="visible_for")

    class Meta:
        ordering = ["created_at"]


class Room(models.Model):
    class RoomTypes(models.TextChoices):
        PRIVATE = "private", "Private"
        GROUP = "group", "Group"

    name = models.CharField(max_length=50)
    members = models.ManyToManyField(User, related_name="rooms")
    created_at = models.DateTimeField(auto_now_add=True)
    type = models.CharField(
        max_length=10, default=RoomTypes.PRIVATE, choices=RoomTypes.choices
    )

    def __str__(self):
        return f"{self.type} :: {self.name}"
