from django.shortcuts import render

from chat.models import Message, Room


def chat(request):
    rooms = request.user.rooms.all()
    room_messages = []
    current_room = request.GET.get("room", None)
    if current_room and Room.objects.get(id=current_room):
        room_messages = Message.objects.filter(room=current_room)
    template = "chat/chat.html"
    context = {
        "title": "Home",
        "rooms": rooms,
        "room_messages": room_messages,
    }
    return render(request, template, context)
