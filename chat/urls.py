from django.urls import path

from chat.views import chat, people, start_direct, start_group

app_name = "chat"

urlpatterns = [
    path("chat/", chat, name="chat"),
    path("chat/people/", people, name="people"),
    path("chat/new/direct/", start_direct, name="start_direct"),
    path("chat/new/group/", start_group, name="start_group"),
]
