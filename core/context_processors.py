from django.urls import reverse

from core import theme


def ui(request):
    """Theme settings for the <html> element.

    Signed-in users get their saved preference, rendered by the server and
    saved back when they change it. Signed-out visitors get the defaults; the
    browser then applies any choice saved on that device (see
    core/static/core/js/theme.js).
    """
    user = getattr(request, "user", None)
    from_server = bool(user and user.is_authenticated)
    if from_server:
        from account.models import Preference

        pref = Preference.for_user(user)
        palette, mode, density = theme.resolve(pref.palette, pref.mode, pref.density)
    else:
        palette, mode, density = theme.resolve()
    return {
        "ui": {
            "palette": palette,
            "mode": mode,
            "density": density,
            "from_server": from_server,
            "save_url": reverse("account:appearance") if from_server else "",
            "palettes": theme.PALETTES,
            "modes": theme.MODES,
            "densities": theme.DENSITIES,
        }
    }
