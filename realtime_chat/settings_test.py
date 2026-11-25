"""Settings for the test suite: production-like, with safe defaults filled in."""

import os

os.environ.setdefault("DJANGO_DEBUG", "false")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,testserver")
os.environ.pop("REDIS_URL", None)

from realtime_chat.settings import *  # noqa: E402,F401,F403 isort:skip

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
