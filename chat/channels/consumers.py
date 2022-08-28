import json
from pprint import pprint

from asgiref.sync import async_to_sync
from chat.models import Message, Room
from django.utils import timezone

from channels.generic.websocket import WebsocketConsumer


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        print("WS Connection: Accept")
        self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
        self.room = None

        if self.room_id:
            self.room = self.get_room(self.room_id)
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

    def receive(self, text_data):
        print("WS Connection: Receive")
        text_data_json = json.loads(text_data)
        print(text_data_json)

        pprint(self.__dict__)

        self.user = self.scope["user"]
        message = self.save_message(message=text_data_json["message"])

        # Send message to room group
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name, {"type": "chat_response", "message": message.content}
        )

    def chat_response(self, event):
        message = event["message"]
        now = str(timezone.now())

        # Send message to WebSocket
        self.send(text_data=json.dumps({"message": message, "ts": now}))

    def save_message(self, message):
        obj = Message.objects.create(content=message, room=self.room, user=self.user)
        obj.save()
        return obj

    def get_room(self, room_id):
        try:
            obj = Room.objects.get(id=room_id)
            return obj
        except Room.DoesNotExist as ex:
            return False
