from django.conf import settings
from django.db import models

from core import theme


class Preference(models.Model):
    """Per-user appearance settings. Rows are created on first save; until
    then the defaults in core/theme.py apply."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preference"
    )
    palette = models.CharField(
        max_length=20,
        choices=[(p.key, p.name) for p in theme.PALETTES],
        default=theme.DEFAULT_PALETTE,
    )
    mode = models.CharField(
        max_length=10, choices=theme.MODES, default=theme.DEFAULT_MODE
    )
    density = models.CharField(
        max_length=12, choices=theme.DENSITIES, default=theme.DEFAULT_DENSITY
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} · {self.palette}/{self.mode}/{self.density}"

    @classmethod
    def for_user(cls, user):
        """The saved preference, or an unsaved one holding the defaults."""
        try:
            return user.preference
        except cls.DoesNotExist:
            return cls(user=user)
