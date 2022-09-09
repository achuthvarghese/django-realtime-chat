import json
from enum import Enum

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.utils import timezone

from chat.models import Message, Room


class WSChatType(Enum):
    CLEAR_ROOM = "clear_room"
    CHAT_RESPONSE = "chat_response"
    SAVE_MESSAGE = "save_message"

    @classmethod
    def has_value(cls, value):
        return value in [member.value for member in cls]


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        print("WS Connection: Accept")
        self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
        self.room = None

        if self.room_id:
            self.room = self.get_room()
            if self.room:
                self.room_name = f"room_{self.room.id}"
                self.room_group_name = f"chat_{self.room_name}"

                async_to_sync(self.channel_layer.group_add)(
                    self.room_group_name, self.channel_name
                )
                self.groups.append(self.room_group_name)
                self.accept()
            else:
                now = str(timezone.now())
                self.accept()
                self.send(
                    text_data=json.dumps(
                        {"code": 404, "message": "Room not found", "ts": now}
                    )
                )
                self.close()
        # else:
        #     now = str(timezone.now())
        #     self.accept()
        #     self.send(text_data=json.dumps({"code":"RIDNF", "message": "Provide Room ID", "ts": now}))
        #     self.close()

    def disconnect(self, close_code):
        print("WS Connection: Disconnect")
        if self.room and self.channel_layer:
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name, self.channel_name
            )

    def __call_method(self, method="", *args, **kwargs):
        if not method:
            return False

        try:
            method_to_call = self.__getattribute__(method)
            result = method_to_call(*args, **kwargs)
            return result
        except AttributeError as ex:
            return False

    def receive(self, text_data):
        print("WS Connection: Receive")

        text_data_json = json.loads(text_data)
        type = text_data_json.get("type")

        self.user = self.scope["user"]

        response_data = {"type": type}

        # Check if type is valid else respond
        if WSChatType.has_value(type):

            data = self.__call_method(type, **text_data_json)

            if type == WSChatType.SAVE_MESSAGE.value:
                response_data["message"] = data.content
                response_data["user"] = data.user.username
                response_data["created_at"] = data.created_at
            elif type == WSChatType.CLEAR_ROOM.value:
                response_data["cleared"] = data
                response_data["for"] = self.user.username
            else:
                pass

        else:
            response_data["message"] = "Invalid type"

        # Send message to room group
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {"type": WSChatType.CHAT_RESPONSE.value, "data": response_data},
        )

    def chat_response(self, event):
        response_data = event["data"]

        # Send message to WebSocket
        self.send(
            text_data=json.dumps(
                response_data,
                default=str,
            )
        )

    def save_message(self, *args, message, **kwargs):
        room_members = self.room.members.all()
        message_obj = Message.objects.create(
            content=message, room=self.room, user=self.user
        )
        message_obj.visible_for.add(*[member.id for member in room_members])
        message_obj.save()
        return message_obj

    def clear_room(self, *args, **kwargs):
        room = self.get_room()
        messages = room.messages.all()
        for message in messages:
            message.visible_for.remove(self.user)
        return True

    def get_room(self):
        try:
            room_obj = Room.objects.get(id=self.room_id)
            return room_obj
        except Room.DoesNotExist as ex:
            return False
