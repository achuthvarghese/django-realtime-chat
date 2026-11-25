from core import theme


def ui(request):
    """Theme settings for the <html> element.

    Signed-out visitors get the defaults; the browser then applies any choice
    saved on that device (see core/static/core/js/theme.js). Per-user
    preferences stored on the server arrive in the settings phase.
    """
    palette, mode, density = theme.resolve()
    return {
        "ui": {
            "palette": palette,
            "mode": mode,
            "density": density,
            "from_server": False,
            "palettes": theme.PALETTES,
            "modes": theme.MODES,
            "densities": theme.DENSITIES,
        }
    }
