from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("chat/<uuid:chat_with>", consumers.ChatConsumer.as_asgi()),
]
