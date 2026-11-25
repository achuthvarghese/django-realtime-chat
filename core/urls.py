from django.urls import path

from core.views import styleguide

app_name = "core"

urlpatterns = [
    path("styleguide/", styleguide, name="styleguide"),
]
