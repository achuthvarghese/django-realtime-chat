import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Mentions. The Mention table carries its unique constraint from the
    start, and Message.mentions is a through field with no column of its
    own, so it's added to the model state only: SQLite would otherwise
    rebuild the whole chat_message table for it."""

    dependencies = [
        ("chat", "0006_reaction"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Mention",
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
                    "message",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mention_rows",
                        to="chat.message",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mention_rows",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("message", "user"), name="unique_mention"
                    )
                ],
            },
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="message",
                    name="mentions",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="mentioned_in",
                        through="chat.Mention",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
