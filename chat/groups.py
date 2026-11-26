"""Group membership and admin rules.

| Action                         | Who                |
| ------------------------------ | ------------------ |
| Add people                     | Any member         |
| Rename, remove members, delete | Admins             |
| Make or remove admins          | Admins             |
| Leave                          | Any member         |

- The creator is the first admin; a group can have several.
- The only admin can't remove their own admin role: they make someone else
  admin first.
- When the last admin leaves, the longest-standing member becomes admin.
- When the last member leaves, the group is deleted.

Every change writes a system message ("Maya added Lee") and notifies open
sockets. See docs/screens.md#group-details and docs/websocket-protocol.md.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from chat import realtime
from chat.models import Membership, Message, Room
from chat.presenters import display_name, message_data
from chat.services import MAX_GROUP_MEMBERS, MAX_GROUP_NAME

User = get_user_model()


# What people see when a group change isn't allowed. Views look the sentence
# up by code from this fixed table; exception text never reaches a response.
GROUP_ERROR_MESSAGES = {
    "not_group": "Only group chats have members to manage.",
    "not_member": "You're not in this group.",
    "not_admin": "Only admins can do that.",
    "nobody_new": "Pick at least one person who isn't in the group yet.",
    "too_many": f"Groups can have at most {MAX_GROUP_MEMBERS} members.",
    "unknown_people": "Some of those people couldn't be found.",
    "remove_self": "Use Leave group to remove yourself.",
    "target_not_member": "That person isn't in this group.",
    "name_missing": "Give the group a name.",
    "name_too_long": f"Group names can be at most {MAX_GROUP_NAME} characters.",
    "last_admin": "A group needs at least one admin. Make someone else an admin first.",
}
UNKNOWN_ERROR_MESSAGE = "That change couldn't be made."


def error_message(code):
    """The sentence to show for a GroupError code."""
    return GROUP_ERROR_MESSAGES.get(code, UNKNOWN_ERROR_MESSAGE)


class GroupError(ValueError):
    """A group change that isn't allowed. Carries only a `code`; see
    GROUP_ERROR_MESSAGES for the matching sentence."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


# Queries


def membership(room, user):
    return Membership.objects.filter(room=room, user=user).first()


def is_admin(room, user):
    return Membership.objects.filter(room=room, user=user, is_admin=True).exists()


def admin_count(room):
    return Membership.objects.filter(room=room, is_admin=True).count()


def require_group(room):
    if room.type != Room.RoomTypes.GROUP:
        raise GroupError("not_group")


def require_member(room, user):
    if membership(room, user) is None:
        raise GroupError("not_member")


def require_admin(room, user):
    if not is_admin(room, user):
        raise GroupError("not_admin")


# Events


def system_message(room, actor, text):
    """Record a group event and send it to everyone in the room."""
    message = Message.objects.create(
        content=text, room=room, user=actor, kind=Message.Kinds.SYSTEM
    )
    message.visible_for.add(*room.members.all())
    realtime.broadcast_frame(room.id, {"type": "save_message", **message_data(message)})
    return message


def announce_room_changed(room):
    """Tell open sockets to refresh the header and details panel."""
    room.refresh_from_db()
    realtime.broadcast_frame(
        room.id,
        {
            "type": "room_updated",
            "room": str(room.id),
            "name": room.name,
            "member_count": room.members.count(),
        },
    )


def revoke_access(room, user):
    """Close the user's sockets for this room (they're no longer a member)."""
    realtime.send_to_room(room.id, {"type": "membership.revoked", "user_id": user.pk})


# Changes


def name_list(users):
    names = [display_name(u) for u in users]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


@transaction.atomic
def add_members(room, actor, usernames):
    require_group(room)
    require_member(room, actor)
    wanted = {u.strip().lstrip("@") for u in usernames if u and u.strip()}
    current = set(room.members.values_list("username", flat=True))
    wanted -= current
    if not wanted:
        raise GroupError("nobody_new")
    if len(current) + len(wanted) > MAX_GROUP_MEMBERS:
        raise GroupError("too_many")
    users = list(User.objects.filter(username__in=wanted, is_active=True))
    missing = wanted - {u.username for u in users}
    if missing:
        raise GroupError("unknown_people")
    users.sort(key=lambda u: display_name(u).lower())
    now = timezone.now()
    Membership.objects.bulk_create(
        [Membership(room=room, user=u, joined_at=now) for u in users]
    )
    system_message(room, actor, f"{display_name(actor)} added {name_list(users)}")
    announce_room_changed(room)
    return users


@transaction.atomic
def remove_member(room, actor, target):
    require_group(room)
    require_admin(room, actor)
    if target.pk == actor.pk:
        raise GroupError("remove_self")
    entry = membership(room, target)
    if entry is None:
        raise GroupError("target_not_member")
    entry.delete()
    system_message(room, actor, f"{display_name(actor)} removed {display_name(target)}")
    revoke_access(room, target)
    announce_room_changed(room)


@transaction.atomic
def rename(room, actor, name):
    require_group(room)
    require_admin(room, actor)
    name = (name or "").strip()
    if not name:
        raise GroupError("name_missing")
    if len(name) > MAX_GROUP_NAME:
        raise GroupError("name_too_long")
    if name == room.name:
        return
    room.name = name
    room.save(update_fields=["name"])
    system_message(room, actor, f'{display_name(actor)} renamed the group to "{name}"')
    announce_room_changed(room)


@transaction.atomic
def set_admin(room, actor, target, make_admin):
    require_group(room)
    require_admin(room, actor)
    entry = membership(room, target)
    if entry is None:
        raise GroupError("target_not_member")
    if entry.is_admin == make_admin:
        return
    if not make_admin and admin_count(room) == 1:
        raise GroupError("last_admin")
    entry.is_admin = make_admin
    entry.save(update_fields=["is_admin"])
    if make_admin:
        text = f"{display_name(actor)} made {display_name(target)} an admin"
    elif target.pk == actor.pk:
        text = f"{display_name(actor)} is no longer an admin"
    else:
        text = f"{display_name(actor)} removed {display_name(target)} as admin"
    system_message(room, actor, text)
    announce_room_changed(room)


@transaction.atomic
def leave(room, user):
    """Leave a group. Returns False if the group was deleted (last member)."""
    require_group(room)
    entry = membership(room, user)
    if entry is None:
        raise GroupError("not_member")
    was_admin = entry.is_admin
    entry.delete()
    remaining = Membership.objects.filter(room=room).order_by("joined_at", "id")
    if not remaining.exists():
        room_id = room.id
        room.delete()
        realtime.send_to_room(room_id, {"type": "room.deleted"})
        return False
    system_message(room, user, f"{display_name(user)} left")
    if was_admin and not remaining.filter(is_admin=True).exists():
        successor = remaining.first()
        successor.is_admin = True
        successor.save(update_fields=["is_admin"])
        system_message(
            room, successor.user, f"{display_name(successor.user)} is now an admin"
        )
    revoke_access(room, user)
    announce_room_changed(room)
    return True


@transaction.atomic
def delete_group(room, actor):
    require_group(room)
    require_admin(room, actor)
    room_id = room.id
    room.delete()
    realtime.send_to_room(room_id, {"type": "room.deleted"})
