"""Theme options shared by templates, JavaScript and (later) user settings.

The values here must match the `data-palette`, `data-mode` and
`data-density` selectors in core/static/core/css/tokens.css.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    key: str
    name: str
    sidebar: str
    accent: str
    mine: str


PALETTES = (
    Palette("graphite", "Graphite + Coral", "#16181d", "#ff5a36", "#2ec4a6"),
    Palette("midnight", "Midnight + Saffron", "#121a2b", "#f5a524", "#7c9cff"),
    Palette("slate", "Slate + Electric", "#1c2430", "#3d7bff", "#22c3a6"),
    Palette("plum", "Plum + Rose", "#2a1630", "#ff4f8b", "#ffb547"),
    Palette("moss", "Moss + Tangerine", "#17241e", "#ff7a2f", "#7bd88f"),
    Palette("paper", "Paper + Red", "#eceef2", "#e5484d", "#2f6fde"),
)

MODES = (("light", "Light"), ("dark", "Dark"), ("system", "System"))
DENSITIES = (("compact", "Compact"), ("comfortable", "Comfortable"))

DEFAULT_PALETTE = "graphite"
DEFAULT_MODE = "system"
DEFAULT_DENSITY = "compact"

PALETTE_KEYS = frozenset(p.key for p in PALETTES)
MODE_KEYS = frozenset(key for key, _ in MODES)
DENSITY_KEYS = frozenset(key for key, _ in DENSITIES)


def resolve(palette=None, mode=None, density=None):
    """Return a valid (palette, mode, density), falling back to defaults."""
    return (
        palette if palette in PALETTE_KEYS else DEFAULT_PALETTE,
        mode if mode in MODE_KEYS else DEFAULT_MODE,
        density if density in DENSITY_KEYS else DEFAULT_DENSITY,
    )
