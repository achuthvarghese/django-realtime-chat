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
