from django.urls import path

from core.views import home, styleguide

app_name = "core"

urlpatterns = [
    path("", home, name="home"),
    path("styleguide/", styleguide, name="styleguide"),
]
