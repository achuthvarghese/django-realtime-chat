from chat.channels import consumers
from django.urls import path

websocket_urlpatterns = [
    path("chat/<str:room_id>", consumers.ChatConsumer.as_asgi()),
]
