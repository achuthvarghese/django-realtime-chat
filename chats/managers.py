from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class RoomManager(models.Manager):
    def get_private_room(self, author, to):
        qs = super().get_queryset()
        try:
            user_private_rooms = qs.filter(type="private", members=author)
            room = user_private_rooms.get(members=to)
            return room
        except Exception:
            return False

    def get_or_create_private_room(self, author_uuid, to_uuid, *args, **kwargs):
        kwargs["type"] = "private"

        room = self.get_private_room(author_uuid, to_uuid)

        if not room:
            room = super(RoomManager, self).create(*args, **kwargs)

            author = User.objects.get(id=author_uuid)
            to = User.objects.get(id=to_uuid)

            room.members.add(author, to)

        return room
