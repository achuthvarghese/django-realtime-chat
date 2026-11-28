import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import reverse

from core import theme

CORE_DIR = Path(__file__).resolve().parent


class TestThemeResolve:
    def test_defaults(self):
        assert theme.resolve() == ("graphite", "system", "compact")

    def test_valid_values_pass_through(self):
        assert theme.resolve("plum", "dark", "comfortable") == (
            "plum",
            "dark",
            "comfortable",
        )

    def test_invalid_values_fall_back(self):
        assert theme.resolve("neon", "sepia", "huge") == (
            "graphite",
            "system",
            "compact",
        )


class TestThemeKeysStayInSync:
    """Palette keys live in Python, CSS and the inline head script."""

    def test_every_palette_has_css(self):
        css = (CORE_DIR / "static/core/css/tokens.css").read_text()
        for palette in theme.PALETTES:
            if palette.key == theme.DEFAULT_PALETTE:
                continue  # the default palette is defined on bare :root
            assert f'[data-palette="{palette.key}"]' in css

    def test_inline_script_allows_every_option(self):
        html = (CORE_DIR / "templates/core/base.html").read_text()
        allowed = re.search(r"palette: \[(.*?)\]", html).group(1)
        assert {k.strip(' "') for k in allowed.split(",")} == theme.PALETTE_KEYS


@pytest.mark.django_db
class TestBaseTemplate:
    @override_settings(DEBUG=True)
    def test_styleguide_renders_theme_attributes(self, client):
        response = client.get(reverse("core:styleguide"))
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-palette="graphite"' in html
        assert 'data-mode="system"' in html
        assert 'data-density="compact"' in html
        for palette in theme.PALETTES:
            assert f'value="{palette.key}"' in html

    def test_styleguide_hidden_without_debug(self, client):
        assert client.get(reverse("core:styleguide")).status_code == 404


@pytest.mark.django_db
class TestErrorPages:
    def test_404_uses_site_template(self, client):
        response = client.get("/no-such-page/")
        assert response.status_code == 404
        html = response.content.decode()
        assert "This page or room isn" in html
        assert "/no-such-page/" in html
        assert "data-palette=" in html

    def test_404_escapes_the_path(self, client):
        response = client.get("/<script>x</script>/")
        assert b"<script>x</script>" not in response.content

    def test_room_outside_membership_shows_site_404(self, client):
        # The chat page itself redirects with a notice instead (chat/tests.py).
        import uuid

        user = get_user_model().objects.create_user("eve", password="pw")
        client.force_login(user)
        response = client.get(reverse("chat:details", args=[uuid.uuid4()]))
        assert response.status_code == 404
        assert "This page or room isn" in response.content.decode()

    @pytest.mark.parametrize(
        "template, text",
        [
            ("500.html", "Something broke on our end"),
            ("400.html", "Something in that request was off"),
            ("403.html", "have access to this"),
        ],
    )
    def test_templates_render_without_context(self, template, text):
        # Django renders 500 pages without context processors.
        html = render_to_string(template)
        assert text in html
        assert 'data-palette="graphite"' in html

    def test_csrf_failure_uses_site_template(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("account:login"), {"username": "a", "password": "b"}
        )
        assert response.status_code == 403
        assert "That form has expired" in response.content.decode()


@pytest.mark.django_db
class TestHome:
    def test_anonymous_sees_landing_page(self, client):
        response = client.get(reverse("core:home"))
        assert response.status_code == 200
        html = response.content.decode()
        assert "on one line" in html
        assert reverse("account:signup") in html
        assert reverse("account:login") in html

    def test_signed_in_user_goes_to_chat(self, client):
        user = get_user_model().objects.create_user("maya", password="pw")
        client.force_login(user)
        response = client.get(reverse("core:home"))
        assert response.status_code == 302
        assert response.url == reverse("chat:chat")

    def test_chat_lives_under_chat_path(self):
        assert reverse("chat:chat") == "/chat/"


@pytest.mark.django_db
class TestSeedDemo:
    def run(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("seed_demo", *args, stdout=out)
        return out.getvalue()

    @override_settings(DEBUG=True)
    def test_seeds_users_rooms_and_messages(self):
        from account.models import Preference
        from chat.models import Message, Room
        from core import demo_data

        output = self.run()
        User = get_user_model()
        assert User.objects.count() == len(demo_data.USERS)
        assert Room.objects.count() == len(demo_data.ROOMS)
        assert Message.objects.count() == (
            len(demo_data.SCRIPT) + demo_data.FILLER_COUNT + len(demo_data.SYSTEM)
        )
        design = Room.objects.get(name="Design team")
        admins = set(
            design.memberships.filter(is_admin=True).values_list(
                "user__username", flat=True
            )
        )
        assert admins == {"maya", "arjun"}
        assert design.created_by.username == "maya"
        assert Room.objects.get(name="Ops").created_by.username == "lee"
        assert demo_data.DEMO_PASSWORD in output
        maya = User.objects.get(username="maya")
        assert maya.check_password(demo_data.DEMO_PASSWORD)
        assert not User.objects.get(username="noah").is_active
        assert Preference.objects.get(user__username="arjun").palette == "slate"
        assert Message.objects.exclude(edited_at=None).count() == 1
        assert Message.objects.exclude(deleted_at=None).get().content == ""

    @override_settings(DEBUG=True)
    def test_scenarios_match_the_docs(self):
        from chat.models import Message
        from chat.presence import unread_counts

        self.run()
        User = get_user_model()
        maya = User.objects.get(username="maya")
        by_name = {r.name: r.pk for r in maya.rooms.all()}
        unread = unread_counts(maya, list(by_name.values()))
        assert unread[by_name["Design team"]] == 5
        assert unread[by_name["Ops"]] == 6
        assert unread[by_name["Book club"]] == 0
        assert not User.objects.get(username="sam").rooms.exists()
        priya = User.objects.get(username="priya")
        books = Message.objects.filter(room__name="Book club")
        assert books.filter(visible_for=priya).count() < books.count()

    @override_settings(DEBUG=True)
    def test_mentions_seeded(self):
        from chat.models import Mention
        from chat.presence import unread_and_mentions
        from chat.presenters import room_summaries
        from chat.views import history_page

        self.run()
        User = get_user_model()
        maya = User.objects.get(username="maya")
        priya = User.objects.get(username="priya")
        # 7 in the script. Priya cleared the one before her clear point, but
        # the row stays (it records the text); she just can't see it.
        assert Mention.objects.count() == 7
        # Every mention names a member other than the sender.
        for mention in Mention.objects.select_related("message__room"):
            assert mention.user_id != mention.message.user_id
            assert mention.message.room.members.filter(pk=mention.user_id).exists()

        rows = {r["title"]: r for r in room_summaries(maya)}
        # Design: arjun's @maya and lee's reply to her, both after her read.
        assert rows["Design team"]["mentions"] == 2
        assert rows["Ops"]["mentions"] == 1
        assert rows["Book club"]["mentions"] == 0
        assert all(r["mentions"] == 0 for r in rows.values() if r["type"] == "private")

        # Priya sees the mention after her clear point, not the one before.
        books = next(r for r in maya.rooms.all() if r.name == "Book club")
        assert unread_and_mentions(priya, [books.pk])[books.pk][1] == 1
        page, _ = history_page(books, priya, limit=100)
        mentioned = [m for m in page if m["mentions"]]
        assert [m["message"] for m in mentioned] == ["@Priya same, it made me cry"]
        assert mentioned[0]["mentions"] == [{"user": "priya", "name": "Priya Nair"}]

    @override_settings(DEBUG=True)
    def test_reactions_seeded(self):
        from chat.models import Reaction, Room
        from chat.views import history_page
        from core import demo_data

        self.run()
        User = get_user_model()
        assert Reaction.objects.count() == sum(
            len(people) for *_rest, people in demo_data.REACTIONS
        )
        design = Room.objects.get(name="Design team")
        maya = User.objects.get(username="maya")
        page, _ = history_page(design, maya, limit=100)
        palette = next(
            m for m in page if m["message"] == "Palette cards are in, six of them"
        )
        assert [r["emoji"] for r in palette["reactions"]] == [
            "thumbs_up",
            "heart",
            "party",
        ]
        party = palette["reactions"][2]
        assert party["count"] == 3
        assert [u["user"] for u in party["users"]] == ["arjun", "maya", "lee"]
        assert party["users"][0]["name"] == "Arjun Kumar"
        # Anika reacted to her own message.
        assert palette["user"] == "anika"
        assert palette["reactions"][1]["users"][0]["user"] == "anika"

        # A direct chat has one.
        dm = Room.objects.get(type="private", members=maya, name="arjun-maya")
        page, _ = history_page(dm, maya)
        assert sum(len(m["reactions"]) for m in page) == 1

        # Book club: Maya sees the reactions on the old message; Priya cleared
        # it, so none of her messages carry any.
        books = Room.objects.get(name="Book club")
        page, _ = history_page(books, maya)
        assert any(m["reactions"] for m in page)
        page, _ = history_page(books, User.objects.get(username="priya"))
        assert page and not any(m["reactions"] for m in page)

    @override_settings(DEBUG=True)
    def test_second_run_skips(self):
        from chat.models import Message

        self.run()
        count = Message.objects.count()
        assert "already present" in self.run()
        assert Message.objects.count() == count

    @override_settings(DEBUG=True)
    def test_reset_rebuilds_without_duplicates_and_keeps_other_users(self):
        from chat.models import Message, Room

        self.run()
        real = get_user_model().objects.create_user("real", password="pw")
        self.run("--reset")
        assert get_user_model().objects.filter(username="maya").count() == 1
        assert get_user_model().objects.filter(pk=real.pk).exists()
        assert Room.objects.count() == 7
        assert Message.objects.count() > 0

    def test_refuses_without_debug(self):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="DEBUG is off"):
            self.run()
        assert get_user_model().objects.count() == 0

    def test_if_debug_is_quiet_without_debug(self):
        assert "skipped" in self.run("--if-debug")
        assert get_user_model().objects.count() == 0

    @override_settings(DEBUG=True)
    def test_env_flag_can_disable(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SEED_DEMO", "false")
        assert "DJANGO_SEED_DEMO is off" in self.run("--if-debug")
        assert get_user_model().objects.count() == 0
