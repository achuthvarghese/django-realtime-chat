from django.urls import path

from chat.channels import consumers

websocket_urlpatterns = [
    path("chat/<str:room_id>", consumers.ChatConsumer.as_asgi()),
]
