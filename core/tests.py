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
        user = get_user_model().objects.create_user("eve", password="pw")
        client.force_login(user)
        response = client.get(reverse("chat:chat"), {"room": "not-a-uuid"})
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
