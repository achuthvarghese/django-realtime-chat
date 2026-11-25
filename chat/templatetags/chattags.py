from django import template

from chat.models import Room

register = template.Library()


@register.simple_tag(takes_context=True)
def get_room_title(context, room):
    """Title for a room: the other person's name for private chats.

    The result is plain text; Django's autoescaping applies when rendered.
    """
    if room is None:
        return "MESSAGES"
    if room.type == Room.RoomTypes.PRIVATE:
        user = context["request"].user
        other = next((m for m in room.members.all() if m.pk != user.pk), None)
        if other is not None:
            return other.get_full_name() or f"@{other.username}"
    return room.name
