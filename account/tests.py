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

    def test_page_renders_sections(self, client, user):
        client.force_login(user)
        html = client.get(reverse("account:settings")).content.decode()
        for anchor in ('id="profile"', 'id="appearance"', 'id="security"'):
            assert anchor in html
        assert 'data-theme-save-url="/account/settings/appearance/"' in html
        assert 'name="csrf-token"' in html

    def test_update_profile(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:settings"),
            {
                "section": "profile",
                "first_name": "Maya",
                "last_name": "Rao",
                "email": "maya@new.example",
            },
        )
        assert response.url == reverse("account:settings")
        user.refresh_from_db()
        assert (user.first_name, user.last_name, user.email) == (
            "Maya",
            "Rao",
            "maya@new.example",
        )

    def test_profile_requires_valid_email(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:settings"),
            {"section": "profile", "first_name": "M", "last_name": "R", "email": "x"},
        )
        assert response.status_code == 200
        assert 'id="email-error"' in response.content.decode()

    def test_change_password_keeps_session(self, client, user):
        client.force_login(user)
        new = "an0ther-Strong-pass"
        response = client.post(
            reverse("account:settings"),
            {
                "section": "password",
                "old_password": PASSWORD,
                "new_password1": new,
                "new_password2": new,
            },
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.check_password(new)
        assert client.get(reverse("account:settings")).status_code == 200

    def test_wrong_old_password_is_rejected(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account:settings"),
            {
                "section": "password",
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
        assert response.url == reverse("account:settings")

    def test_saved_theme_renders_from_server(self, client, user):
        from account.models import Preference

        Preference.objects.create(user=user, palette="moss", mode="light")
        client.force_login(user)
        html = client.get(reverse("chat:chat")).content.decode()
        assert 'data-palette="moss"' in html
        assert 'data-mode="light"' in html
        assert 'data-theme-source="server"' in html

    def test_requires_login_and_post(self, client, user):
        assert client.post(reverse("account:appearance")).status_code == 302
        client.force_login(user)
        assert client.get(reverse("account:appearance")).status_code == 405

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
