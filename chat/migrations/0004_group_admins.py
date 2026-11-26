"""Group admins.

1. Adopt the auto-created Room.members table as the explicit Membership model
   (state only: the table, its rows and its unique index stay as they are).
2. Add Membership.is_admin and Membership.joined_at, Room.created_by and
   Message.kind.
3. Backfill: memberships take their room's creation time as joined_at, and in
   each group the earliest-added member becomes admin and creator.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill(apps, schema_editor):
    Room = apps.get_model("chat", "Room")
    Membership = apps.get_model("chat", "Membership")
    for room in Room.objects.all():
        memberships = Membership.objects.filter(room=room).order_by("id")
        memberships.update(joined_at=room.created_at)
        if room.type == "group":
            first = memberships.first()
            if first is not None:
                Membership.objects.filter(pk=first.pk).update(is_admin=True)
                Room.objects.filter(pk=room.pk).update(created_by_id=first.user_id)


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0003_presence_and_read_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Membership",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "room",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="memberships",
                                to="chat.room",
                            ),
                        ),
                        (
                            "user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="memberships",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "chat_room_members",
                        "unique_together": {("room", "user")},
                    },
                ),
                migrations.AlterField(
                    model_name="room",
                    name="members",
                    field=models.ManyToManyField(
                        related_name="rooms",
                        through="chat.Membership",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name="membership",
            name="is_admin",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="membership",
            name="joined_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterModelOptions(
            name="membership",
            options={"ordering": ["joined_at", "id"]},
        ),
        migrations.AddField(
            model_name="room",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="kind",
            field=models.CharField(
                choices=[("text", "Text"), ("system", "System")],
                default="text",
                max_length=10,
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
