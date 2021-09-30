import json

from channels.generic.websocket import WebsocketConsumer


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        print("ACCEPTED")

    def disconnect(self, close_code):
        print("DISCONNECTED", close_code)

    def receive(self, text_data):
        print("RECEIVED", text_data)
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        self.send(text_data=json.dumps({"message": message, "ack": True}))