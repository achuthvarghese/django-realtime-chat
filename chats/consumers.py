import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q

from chats.models import Message, Room


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.accept()
            await self.send(
                text_data=json.dumps(
                    {
                        "status": 401,
                        "message": "User not Authorized.",
                    }
                )
            )
            await self.close()
        else:
            chat_with = str(self.scope["url_route"]["kwargs"]["chat_with"])
            user = self.scope["user"].id

            self.room = await self.get_or_create_private_room(user, chat_with)
            self.room_name = f"ROOM_{self.room.id}"
            await self.channel_layer.group_add(self.room_name, self.channel_name)

            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        await self.add_message(message, self.scope["user"], self.room)

        data = {
            "type": "messenger",
            "message": message,
            "author": str(self.scope["user"].id),
        }

        await self.channel_layer.group_send(self.room_name, data)

    async def messenger(self, event):
        message = event.get("message")
        author = event.get("author")

        await self.send(
            text_data=json.dumps(
                {
                    "message": message,
                    "author": author,
                    "status": 200,
                }
            )
        )

    @database_sync_to_async
    def get_or_create_private_room(self, author, to):
        room = Room.objects.get_or_create_private_room(author, to)
        return room

    @database_sync_to_async
    def add_message(self, msg, user, room):
        message = Message.objects.create(
            text=msg,
            user=user,
            room=room,
        )
        return message
