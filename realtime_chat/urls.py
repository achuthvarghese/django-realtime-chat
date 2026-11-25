"""realtime_chat URL Configuration."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("chat.urls")),
    path("account/", include("account.urls")),
    path("", include("core.urls")),
]

if settings.ENABLE_DEBUG_TOOLBAR:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
