from django import template
from django.utils.safestring import mark_safe

from chat.models import Room

register = template.Library()


@register.simple_tag(takes_context=True)
def get_room_title(context, room):
    room_title = "Messages".upper()
    if room is not None:
        if room.type == Room.RoomTypes.PRIVATE:
            other_room_user = room.members.exclude(username=context.request.user).get()
            room_title = (
                other_room_user.get_full_name() or f"@{other_room_user.username}"
            )
        else:
            room_title = room.name
    return mark_safe(room_title)
