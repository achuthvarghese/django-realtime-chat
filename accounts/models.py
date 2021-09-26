import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    id = models.UUIDField(
        _("ID"), primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )

    class Meta:
        db_table = "auth_user"
