import json
import sys
from copy import deepcopy
from pathlib import Path

# In the built .exe config.json and the cache live next to the executable, not in the unpacked temp folder.
BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULTS = {
    # screen: name of the monitor the island sits on (empty = primary); offsets are relative to its top center.
    # locked: when true the island cannot be dragged or re-positioned.
    "position": {"offset_x": 0, "offset_y": 8, "screen": "", "locked": False},
    "scale": 1.0,
    "language": "ru",
    # Progress bar, equalizer and the wave: a hex color, or "cover" to take it from the album art.
    "accent": "#a0101e",
    "modules": {"clock": True, "media": True, "lyrics": True, "visualizer": True},
    "clock": {"time_format": "HH:mm", "date_format": "dddd, d MMMM"},
    # env_file: .env with SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET and SPICY_LYRICS_SECRET_KEY;
    # empty = the .env next to the program (see .env.example). Environment variables take precedence.
    # The keys themselves never go into config.json.
    # romaja: Korean lines shown as Revised Romanization (toggled by the button next to the lyrics icon).
    "lyrics": {"offset_ms": 0, "env_file": "", "visible": True, "romaja": False},
    # process: the program whose sound drives the wave (process loopback, Windows 11);
    # empty = everything the default output device plays.
    "visualizer": {"process": "Spotify.exe"},
    # A little pixel Claude dancing in the corner of the album art while music plays.
    "dancer": True,
    # Open-Meteo, no key needed; an empty city hides the weather.
    "weather": {"city": ""},
    "background": {
        "source": "spicetify",
        "top": "#000000",
        "bottom": "#142b44",
        "star": "#ffffff",
        "shooting_star": "#ffffff",
        "stars": True,
        "shooting_stars": True,
    },
}

STRINGS = {
    "ru": {
        "toggle": "Показать/скрыть",
        "notes": "Заметки",
        "quit": "Выход",
        "hide": "Скрыть",
        "center": "По центру экрана",
        "lock": "Закрепить",
        "reset_position": "Сбросить положение",
    },
    "en": {
        "toggle": "Show/hide",
        "notes": "Notes",
        "quit": "Quit",
        "hide": "Hide",
        "center": "Center on screen",
        "lock": "Lock position",
        "reset_position": "Reset position",
    },
}


def _merge(defaults, loaded):
    # Each value is taken from the file only if its type matches the default,
    # so a hand-edited config can never put the app into an unexpected state.
    result = {}
    for key, default in defaults.items():
        value = loaded.get(key, default) if isinstance(loaded, dict) else default
        if isinstance(default, dict):
            result[key] = _merge(default, value)
        elif isinstance(default, float) and isinstance(value, (int, float)) and not isinstance(value, bool):
            result[key] = float(value)
        elif type(value) is type(default):
            result[key] = value
        else:
            result[key] = default
    return result


def _add_missing(defaults, loaded):
    """Insert keys from defaults that the loaded dict lacks; returns True if anything was added."""
    changed = False
    for key, default in defaults.items():
        if key not in loaded:
            loaded[key] = deepcopy(default)
            changed = True
        elif isinstance(default, dict) and isinstance(loaded[key], dict):
            changed |= _add_missing(default, loaded[key])
    return changed


def save_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_config():
    if not CONFIG_PATH.exists():
        config = deepcopy(DEFAULTS)
        try:
            save_config(config)
        except OSError:
            pass
        return config
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return deepcopy(DEFAULTS)
    if isinstance(loaded, dict) and _add_missing(DEFAULTS, loaded):
        # Settings added in newer versions appear in the file; values already there stay untouched.
        try:
            save_config(loaded)
        except OSError:
            pass
    config = _merge(DEFAULTS, loaded)
    config["scale"] = min(max(config["scale"], 0.5), 3.0)
    return config


def tr(config, key):
    return STRINGS.get(config["language"], STRINGS["en"]).get(key, key)
