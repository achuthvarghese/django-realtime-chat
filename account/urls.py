from django.urls import path

from account.views import (
    appearance,
    settings_password,
    settings_profile,
    user_login,
    user_logout,
    user_settings,
    user_signup,
)

app_name = "account"

urlpatterns = [
    path("login/", user_login, name="login"),
    path("logout/", user_logout, name="logout"),
    path("signup/", user_signup, name="signup"),
    path("settings/", user_settings, name="settings"),
    path("settings/profile/", settings_profile, name="settings_profile"),
    path("settings/appearance/", appearance, name="appearance"),
    path("settings/password/", settings_password, name="settings_password"),
]
