from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Message(models.Model):
    content = models.TextField()
    room = models.ForeignKey(
        "Room", on_delete=models.CASCADE, related_name="messages"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Room(models.Model):
    name = models.CharField(max_length=50)
    members = models.ManyToManyField(User, related_name="rooms")
    created_at = models.DateTimeField(auto_now_add=True)
