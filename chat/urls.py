from django.urls import path

from chat.views import (
    chat,
    group_action,
    people,
    room_details,
    room_history,
    start_direct,
    start_group,
)

app_name = "chat"

urlpatterns = [
    path("chat/", chat, name="chat"),
    path("chat/people/", people, name="people"),
    path("chat/rooms/<uuid:room_id>/messages/", room_history, name="history"),
    path("chat/rooms/<uuid:room_id>/details/", room_details, name="details"),
    path(
        "chat/rooms/<uuid:room_id>/group/<slug:action>/",
        group_action,
        name="group_action",
    ),
    path("chat/new/direct/", start_direct, name="start_direct"),
    path("chat/new/group/", start_group, name="start_group"),
]
