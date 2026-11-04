from functools import lru_cache

from PySide6.QtGui import QFont

DEFAULT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI"]
FONT_FAMILIES = list(DEFAULT_FAMILIES)


def set_family(name):
    """Make `name` the interface font everywhere; an empty name restores the default."""
    FONT_FAMILIES[:] = ([name] if name else []) + DEFAULT_FAMILIES
    font.cache_clear()


def base_font():
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    return f


@lru_cache(maxsize=64)
def font(px, weight=400, tabular=False):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(max(1, round(px)))
    f.setWeight(QFont.Weight(weight))
    # Hinting snaps glyphs to whole pixels, which makes sliding text jitter.
    f.setHintingPreference(QFont.PreferNoHinting)
    if tabular:
        f.setFeature(QFont.Tag("tnum"), 1)
    return f
