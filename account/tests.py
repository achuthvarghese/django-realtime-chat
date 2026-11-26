import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()
PASSWORD = "s3cure-Passw0rd!"


@pytest.fixture
def user(db):
    return User.objects.create_user("maya", "maya@example.com", PASSWORD)


@pytest.mark.django_db
class TestLogin:
    def test_page_renders(self, client):
        response = client.get(reverse("account:login"))
        assert response.status_code == 200

    def test_valid_credentials_log_in(self, client, user):
        response = client.post(
            reverse("account:login"), {"username": "maya", "password": PASSWORD}
        )
        assert response.status_code == 302
        assert response.url == reverse("chat:chat")
        assert "_auth_user_id" in client.session

    def test_wrong_password_is_rejected(self, client, user):
        response = client.post(
            reverse("account:login"), {"username": "maya", "password": "nope"}
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_authenticated_user_is_redirected(self, client, user):
        client.force_login(user)
        response = client.get(reverse("account:login"))
        assert response.status_code == 302


@pytest.mark.django_db
class TestSignup:
    def test_page_renders(self, client):
        response = client.get(reverse("account:signup"))
        assert response.status_code == 200

    def test_creates_user(self, client):
        response = client.post(
            reverse("account:signup"),
            {
                "first_name": "Arjun",
                "last_name": "K",
                "username": "arjun",
                "email": "arjun@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        assert response.status_code == 302
        assert User.objects.filter(username="arjun").exists()

    def test_duplicate_username_is_rejected(self, client, user):
        response = client.post(
            reverse("account:signup"),
            {
                "first_name": "Other",
                "last_name": "Maya",
                "username": "maya",
                "email": "other@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        assert response.status_code == 200
        assert User.objects.filter(username="maya").count() == 1

    def test_mismatched_passwords_are_rejected(self, client):
        client.post(
            reverse("account:signup"),
            {
                "first_name": "Arjun",
                "last_name": "K",
                "username": "arjun",
                "email": "arjun@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD + "x",
            },
        )
        assert not User.objects.filter(username="arjun").exists()


@pytest.mark.django_db
class TestAuthFixes:
    def test_login_follows_safe_next(self, client, user):
        response = client.post(
            reverse("account:login"),
            {"username": "maya", "password": PASSWORD, "next": "/?room=abc"},
        )
        assert response.url == "/?room=abc"

    def test_login_ignores_external_next(self, client, user):
        response = client.post(
            reverse("account:login"),
            {"username": "maya", "password": PASSWORD, "next": "https://evil.example/"},
        )
        assert response.url == reverse("chat:chat")

    def test_unknown_user_gets_generic_error(self, client):
        response = client.post(
            reverse("account:login"), {"username": "ghost", "password": "x"}
        )
        assert "Please check your credentials." in response.content.decode()

    def test_logout_requires_post(self, client, user):
        client.force_login(user)
        assert client.get(reverse("account:logout")).status_code == 405
        response = client.post(reverse("account:logout"))
        assert response.status_code == 302
        assert "_auth_user_id" not in client.session

    def test_signup_logs_in_and_saves_names(self, client):
        response = client.post(
            reverse("account:signup"),
            {
                "first_name": "Arjun",
                "last_name": "Kumar",
                "username": "arjun",
                "email": "arjun@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        assert response.url == reverse("chat:chat")
        assert "_auth_user_id" in client.session
        created = User.objects.get(username="arjun")
        assert (created.first_name, created.last_name) == ("Arjun", "Kumar")

    def test_username_uniqueness_ignores_case(self, client, user):
        client.post(
            reverse("account:signup"),
            {
                "first_name": "M",
                "last_name": "R",
                "username": "MAYA",
                "email": "m@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        assert not User.objects.filter(username="MAYA").exists()


@pytest.mark.django_db
class TestAuthScreens:
    def test_login_uses_design_system(self, client):
        html = client.get(reverse("account:login")).content.decode()
        assert "data-palette=" in html
        assert "bootstrap" not in html.lower()
        assert 'autocomplete="current-password"' in html
        assert "signing in" in html

    def test_signup_shows_field_groups_and_palettes(self, client):
        html = client.get(reverse("account:signup")).content.decode()
        for label in ("Account", "Name", "Password", "Theme"):
            assert f'class="form-spine__label"' in html and label in html
        assert 'autocomplete="new-password"' in html
        assert 'data-axis="palette"' in html
        assert "joining relay" in html

    def test_signup_palette_is_not_submitted_as_palette(self, client):
        # The signup palette radios use their own group name so they do not
        # clash with the theme menu on the same page.
        html = client.get(reverse("account:signup")).content.decode()
        assert 'name="signup_palette"' in html

    def test_invalid_fields_are_marked(self, client):
        response = client.post(reverse("account:signup"), {"username": "x"})
        html = response.content.decode()
        assert 'aria-invalid="true"' in html
        assert 'id="email-error"' in html
        assert "Email is required." in html

    def test_login_error_is_attached_to_password(self, client, user):
        html = client.post(
            reverse("account:login"), {"username": "maya", "password": "no"}
        ).content.decode()
        assert 'id="password-error"' in html
        assert "Please check your credentials." in html

    def test_invalid_username_characters_are_rejected(self, client):
        client.post(
            reverse("account:signup"),
            {
                "first_name": "A",
                "last_name": "B",
                "username": "bad name!",
                "email": "a@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        assert not User.objects.filter(username="bad name!").exists()


@pytest.mark.django_db
class TestSettings:
    def test_requires_login(self, client):
        response = client.get(reverse("account:settings"))
        assert response.status_code == 302

    def test_settings_opens_profile_section(self, client, user):
        client.force_login(user)
        response = client.get(reverse("account:settings"))
        assert response.url == reverse("account:settings_profile")

    @pytest.mark.parametrize(
        "name",
        ["account:settings_profile", "account:appearance", "account:settings_password"],
    )
    def test_each_section_renders_with_nav(self, client, user, name):
        client.force_login(user)
        html = client.get(reverse(name)).content.decode()
        for url in (
            "/account/settings/profile/",
            "/account/settings/appearance/",
            "/account/settings/password/",
        ):
            assert f'href="{url}"' in html
        assert 'aria-current="page"' in html
        assert 'data-theme-save-url="/account/settings/appearance/"' in html
        assert 'name="csrf-token"' in html

    def test_profile_shows_read_only_username(self, client, user):
        client.force_login(user)
        html = client.get(reverse("account:settings_profile")).content.decode()
        assert "@maya" in html
        assert 'name="username"' not in html

    def test_update_profile(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:settings_profile"),
            {
                "first_name": "Maya",
                "last_name": "Rao",
                "email": "maya@new.example",
            },
        )
        assert response.url == reverse("account:settings_profile")
        user.refresh_from_db()
        assert (user.first_name, user.last_name, user.email) == (
            "Maya",
            "Rao",
            "maya@new.example",
        )

    def test_profile_requires_valid_email(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:settings_profile"),
            {"first_name": "M", "last_name": "R", "email": "x"},
        )
        assert response.status_code == 200
        assert 'id="email-error"' in response.content.decode()

    def test_change_password_keeps_session(self, client, user):
        client.force_login(user)
        new = "an0ther-Strong-pass"
        response = client.post(
            reverse("account:settings_password"),
            {
                "old_password": PASSWORD,
                "new_password1": new,
                "new_password2": new,
            },
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.check_password(new)
        assert client.get(reverse("account:settings_password")).status_code == 200

    def test_wrong_old_password_is_rejected(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:settings_password"),
            {
                "old_password": "nope",
                "new_password1": "an0ther-Strong-pass",
                "new_password2": "an0ther-Strong-pass",
            },
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password(PASSWORD)


@pytest.mark.django_db
class TestAppearance:
    def test_json_save_partial(self, client, user):
        from account.models import Preference

        client.force_login(user)
        response = client.post(
            reverse("account:appearance"),
            {"palette": "plum"},
            HTTP_ACCEPT="application/json",
        )
        assert response.json() == {
            "ok": True,
            "palette": "plum",
            "mode": "system",
            "density": "compact",
        }
        client.post(
            reverse("account:appearance"),
            {"mode": "dark"},
            HTTP_ACCEPT="application/json",
        )
        pref = Preference.objects.get(user=user)
        assert (pref.palette, pref.mode) == ("plum", "dark")

    def test_invalid_value_rejected(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:appearance"),
            {"palette": "neon"},
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 400

    def test_form_post_redirects(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:appearance"), {"density": "comfortable"}
        )
        assert response.url == reverse("account:appearance")

    def test_saved_theme_renders_from_server(self, client, user):
        from account.models import Preference

        Preference.objects.create(user=user, palette="moss", mode="light")
        client.force_login(user)
        html = client.get(reverse("chat:chat")).content.decode()
        assert 'data-palette="moss"' in html
        assert 'data-mode="light"' in html
        assert 'data-theme-source="server"' in html

    def test_requires_login_and_get_or_post(self, client, user):
        assert client.post(reverse("account:appearance")).status_code == 302
        client.force_login(user)
        assert client.get(reverse("account:appearance")).status_code == 200
        assert client.put(reverse("account:appearance")).status_code == 405

    def test_signup_saves_chosen_palette(self, client):
        from account.models import Preference

        client.post(
            reverse("account:signup"),
            {
                "first_name": "Neo",
                "last_name": "A",
                "username": "neo",
                "email": "neo@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "signup_palette": "slate",
            },
        )
        assert Preference.objects.get(user__username="neo").palette == "slate"

    def test_signup_ignores_unknown_palette(self, client):
        from account.models import Preference

        client.post(
            reverse("account:signup"),
            {
                "first_name": "Neo",
                "last_name": "A",
                "username": "neo",
                "email": "neo@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "signup_palette": "neon",
            },
        )
        assert not Preference.objects.filter(user__username="neo").exists()


class TestUsernameRules:
    @pytest.mark.parametrize(
        "value", ["lee", "maya_rao", "maya_rao2", "a1b", "x" * 30, "sam_2"]
    )
    def test_valid(self, value):
        from account.usernames import is_valid, validate_username

        validate_username(value)
        assert is_valid(value)

    @pytest.mark.parametrize(
        "value, message",
        [
            ("al", "at least 3"),
            ("x" * 31, "at most 30"),
            ("Lee", "lowercase"),
            ("lee.chen", "lowercase"),
            ("lee-chen", "lowercase"),
            ("lee chen", "lowercase"),
            ("2fast", "Start with a letter"),
            ("_sam", "Start with a letter"),
            ("sam_", "end with _"),
            ("a__b", "two _ in a row"),
        ],
    )
    def test_invalid(self, value, message):
        from django.core.exceptions import ValidationError

        from account.usernames import is_valid, validate_username

        with pytest.raises(ValidationError, match=message):
            validate_username(value)
        assert not is_valid(value)

    @pytest.mark.parametrize(
        "raw, tidied",
        [("Maya Rao", "maya_rao"), ("  Lee   Chen ", "lee_chen"), ("a__b", "a_b")],
    )
    def test_tidy(self, raw, tidied):
        from account.usernames import tidy

        assert tidy(raw) == tidied

    @pytest.mark.parametrize(
        "old, new",
        [
            ("Maya", "maya"),
            ("lee.chen", "lee_chen"),
            ("Anika-Shah", "anika_shah"),
            ("john@example.com", "john_example_com"),
            ("_sam_", "sam"),
            ("al", "al_user"),
            ("2fast", "user_2fast"),
            ("+", "user"),
            ("a" * 40, "a" * 30),
        ],
    )
    def test_conform(self, old, new):
        from account.usernames import conform, is_valid

        assert conform(old) == new
        assert is_valid(conform(old))

    def test_unique_variant(self):
        from account.usernames import unique_variant

        assert unique_variant("lee", set()) == "lee"
        assert unique_variant("lee", {"lee"}) == "lee_2"
        assert unique_variant("lee", {"lee", "lee_2"}) == "lee_3"
        long = "a" * 30
        assert unique_variant(long, {long}) == "a" * 28 + "_2"


@pytest.mark.django_db
class TestUsernameMigration:
    def run_migration(self):
        import importlib

        from django.apps import apps

        module = importlib.import_module("account.migrations.0002_conform_usernames")
        module.conform_usernames(apps, None)

    def test_renames_and_resolves_clashes(self, capsys):
        User = get_user_model()
        for name in ["maya", "Maya", "lee.chen", "Lee-Chen", "ok_name"]:
            User.objects.create_user(name, password="pw")
        self.run_migration()
        names = set(User.objects.values_list("username", flat=True))
        assert names == {"maya", "maya_2", "lee_chen", "lee_chen_2", "ok_name"}
        out = capsys.readouterr().out
        assert "'Maya' -> 'maya_2'" in out
        assert "ok_name" not in out

    def test_valid_names_keep_priority(self):
        User = get_user_model()
        User.objects.create_user("Lee", password="pw")  # created first
        User.objects.create_user("lee", password="pw")
        self.run_migration()
        assert (
            User.objects.get(username="lee").pk != User.objects.get(username="lee_2").pk
        )
        assert User.objects.filter(username="lee").count() == 1


@pytest.mark.django_db
class TestUsernameSignupAndLogin:
    def signup(self, client, username):
        return client.post(
            reverse("account:signup"),
            {
                "first_name": "A",
                "last_name": "B",
                "username": username,
                "email": "a@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

    def test_signup_tidies_username(self, client):
        response = self.signup(client, "  Maya   Rao ")
        assert response.status_code == 302
        assert User.objects.filter(username="maya_rao").exists()

    @pytest.mark.parametrize("bad", ["_sam", "sam_", "2fast", "lee.chen", "al"])
    def test_signup_rejects_bad_usernames(self, client, bad):
        response = self.signup(client, bad)
        assert response.status_code == 200
        assert 'id="username-error"' in response.content.decode()
        assert not User.objects.exists()

    def test_signup_field_has_rules_and_formatting(self, client):
        html = client.get(reverse("account:signup")).content.decode()
        assert "data-username-format" in html
        assert "lowercase letters, numbers and _" in html

    def test_login_ignores_case_and_spaces(self, client):
        User.objects.create_user("maya_rao", password=PASSWORD)
        response = client.post(
            reverse("account:login"), {"username": "Maya Rao", "password": PASSWORD}
        )
        assert response.status_code == 302
        assert "_auth_user_id" in client.session


@pytest.mark.django_db
class TestAccountMenu:
    def test_chat_footer_has_menu_and_gear_not_theme(self, client, user):
        client.force_login(user)
        html = client.get(reverse("chat:chat")).content.decode()
        assert 'class="account-menu"' in html
        assert 'aria-label="Settings"' in html
        assert 'class="theme-menu"' not in html
        assert reverse("account:logout") in html

    def test_signed_out_pages_keep_theme_menu(self, client):
        for name in ("core:home", "account:login", "account:signup"):
            assert 'class="theme-menu"' in client.get(reverse(name)).content.decode()
