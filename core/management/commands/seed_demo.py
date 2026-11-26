"""Load the demo dataset from core/demo_data.py.

    python manage.py seed_demo            # seed once; skip if already seeded
    python manage.py seed_demo --reset    # remove demo data and seed again
    python manage.py seed_demo --if-debug # no-op unless DEBUG and DJANGO_SEED_DEMO

Refuses to run when DEBUG is off: demo accounts share a published password.
"""

import os
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from account.models import Preference
from chat.models import Membership, Message, ReadState, Room
from core import demo_data as data

User = get_user_model()


def demo_usernames():
    return [u[0] for u in data.USERS]


class Command(BaseCommand):
    help = "Seed demo users, rooms and messages for local development (debug only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete existing demo data first."
        )
        parser.add_argument(
            "--if-debug",
            action="store_true",
            help=(
                "Exit quietly instead of failing when DEBUG is off or "
                "DJANGO_SEED_DEMO is false. Used by the Docker image."
            ),
        )

    def handle(self, *args, reset=False, if_debug=False, **options):
        enabled = os.environ.get("DJANGO_SEED_DEMO", "true").lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        if not settings.DEBUG or not enabled:
            reason = "DEBUG is off" if not settings.DEBUG else "DJANGO_SEED_DEMO is off"
            if if_debug:
                self.stdout.write(f"Demo data skipped: {reason}.")
                return
            raise CommandError(f"Refusing to seed demo data: {reason}.")

        existing = User.objects.filter(username__in=demo_usernames())
        if existing.exists() and not reset:
            self.stdout.write(
                "Demo data already present; skipping. Use --reset to rebuild."
            )
            return

        with transaction.atomic():
            if reset:
                self.remove()
            self.seed()

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(data.USERS)} users, {len(data.ROOMS)} rooms and "
                f"{Message.objects.filter(user__username__in=demo_usernames()).count()} "
                f"messages. Password for every account: {data.DEMO_PASSWORD}"
            )
        )

    def remove(self):
        users = User.objects.filter(username__in=demo_usernames())
        # Rooms whose members are all demo users go too.
        for room in Room.objects.filter(members__in=users).distinct():
            if not room.members.exclude(pk__in=users).exists():
                room.delete()
        users.delete()

    def seed(self):
        now = timezone.now()
        users = {}
        for username, first, last, active, pref in data.USERS:
            user = User(
                username=username,
                first_name=first,
                last_name=last,
                email=f"{username}@example.com",
                is_active=active,
            )
            user.set_password(data.DEMO_PASSWORD)
            user.save()
            users[username] = user
            if pref:
                palette, mode, density = pref
                Preference.objects.create(
                    user=user, palette=palette, mode=mode, density=density
                )

        rooms = {}
        history_start = now - timedelta(days=14)
        for key, name, kind, members in data.ROOMS:
            is_group = kind == Room.RoomTypes.GROUP
            room = Room.objects.create(
                name=name or "-".join(sorted(members)),
                type=kind,
                created_by=users[members[0]] if is_group else None,
            )
            admins = {members[0], *data.ADMINS.get(key, [])} if is_group else set()
            for order, username in enumerate(members):
                Membership.objects.create(
                    room=room,
                    user=users[username],
                    is_admin=username in admins,
                    joined_at=history_start + timedelta(minutes=order),
                )
            rooms[key] = room

        rng = random.Random(7)  # deterministic filler
        filler_start = now - timedelta(minutes=4320 + 60 * 24 * 7)
        rows = [
            (
                data.FILLER_ROOM,
                rng.choice(data.FILLER_SENDERS),
                rng.choice(data.FILLER_LINES),
                filler_start + timedelta(minutes=i * 80 + rng.randint(0, 30)),
            )
            for i in range(data.FILLER_COUNT)
        ]
        rows += [
            (room, sender, text, now - timedelta(minutes=minutes))
            for room, sender, text, minutes in data.SCRIPT
        ]
        system_rows = [
            (room, actor, text, now - timedelta(minutes=minutes))
            for room, actor, text, minutes in data.SYSTEM
        ]

        for room_key, sender, text, when in sorted(rows, key=lambda r: r[3]):
            room = rooms[room_key]
            message = Message.objects.create(
                content=text, room=room, user=users[sender]
            )
            Message.objects.filter(pk=message.pk).update(created_at=when)
            message.visible_for.add(*room.members.all())

        for room_key, actor, text, when in system_rows:
            room = rooms[room_key]
            message = Message.objects.create(
                content=text, room=room, user=users[actor], kind=Message.Kinds.SYSTEM
            )
            Message.objects.filter(pk=message.pk).update(created_at=when)
            message.visible_for.add(*room.members.all())

        for room_key, old, new in data.EDITED:
            Message.objects.filter(room=rooms[room_key], content=old).update(
                content=new, edited_at=now
            )
        for room_key, text in data.DELETED:
            Message.objects.filter(room=rooms[room_key], content=text).update(
                content="", deleted_at=now
            )

        for username, per_room in data.READ.items():
            for room_key, minutes in per_room.items():
                ReadState.objects.create(
                    user=users[username],
                    room=rooms[room_key],
                    last_read_at=now - timedelta(minutes=minutes),
                )

        for username, room_key, minutes in data.CLEARED:
            older = Message.objects.filter(
                room=rooms[room_key], created_at__lt=now - timedelta(minutes=minutes)
            )
            users[username].visible_for.remove(*older)
