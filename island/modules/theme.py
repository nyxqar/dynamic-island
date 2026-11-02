import configparser
import math
import os
import random
import re
import time
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtGui import QColor

HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
RELOAD_DELAY_MS = 500

SHOOTING_STAR_COUNT = 4
SHOOTING_STAR_TRAVEL = 1500
SHOOTING_STAR_TAIL = 300
SHOOTING_STAR_FPS = 30
DIAGONAL = math.sqrt(0.5)


def _color(value, fallback):
    color = QColor(value) if isinstance(value, str) else QColor()
    return color if color.isValid() else QColor(fallback)


def manual_palette(background):
    return {
        "top": _color(background["top"], "#000000"),
        "bottom": _color(background["bottom"], "#000000"),
        "star": _color(background["star"], "#ffffff"),
        "shooting_star": _color(background["shooting_star"], "#ffffff"),
        "shooting_glow": _color(background["shooting_star"], "#ffffff"),
    }


def _spicetify_roots():
    roots = [Path(os.environ[var]) / "spicetify" for var in ("APPDATA", "LOCALAPPDATA") if os.environ.get(var)]
    roots.append(Path.home() / ".spicetify")
    return roots


def _read_ini(path):
    parser = configparser.ConfigParser(inline_comment_prefixes=(";",), interpolation=None, strict=False)
    parser.optionxform = str
    with path.open(encoding="utf-8-sig") as f:
        parser.read_file(f)
    return parser


def find_spicetify_theme():
    """Returns (files to watch, palette as '#rrggbb' strings or None). Only reads files, never writes."""
    roots = _spicetify_roots()
    config_path = next((root / "config-xpui.ini" for root in roots if (root / "config-xpui.ini").is_file()), None)
    if config_path is None:
        return [], None
    watch = [config_path]
    try:
        setting = _read_ini(config_path)["Setting"]
        theme = setting.get("current_theme", "").strip()
        scheme = setting.get("color_scheme", "").strip()
    except (OSError, UnicodeDecodeError, configparser.Error, KeyError):
        return watch, None
    # The theme name becomes part of a path; reject anything that could leave the Themes folder.
    if not theme or theme in (".", "..") or Path(theme).name != theme:
        return watch, None

    color_path = next(
        (root / "Themes" / theme / "color.ini" for root in roots if (root / "Themes" / theme / "color.ini").is_file()),
        None,
    )
    if color_path is None:
        return watch, None
    watch.append(color_path)
    try:
        schemes = _read_ini(color_path)
    except (OSError, UnicodeDecodeError, configparser.Error):
        return watch, None
    if not schemes.sections():
        return watch, None
    section = schemes[scheme] if schemes.has_section(scheme) else schemes[schemes.sections()[0]]

    def pick(*keys):
        for key in keys:
            value = section.get(key, "").strip().lstrip("#")
            if HEX_COLOR.match(value):
                return "#" + value
        return None

    main = pick("main") or "#000000"
    # Starry themes paint the window as a sky gradient (sidebar-alt -> sidebar); others use the flat main color.
    starry = "star" in section
    return watch, {
        "top": (pick("sidebar-alt") if starry else None) or main,
        "bottom": (pick("sidebar") if starry else None) or main,
        "star": pick("star", "text") or "#ffffff",
        "shooting_star": pick("shooting-star", "star", "text") or "#ffffff",
        "shooting_glow": pick("shooting-star-glow", "shooting-star", "star", "text") or "#ffffff",
    }


class ThemeSource(QObject):
    changed = Signal(object)

    def __init__(self, background):
        super().__init__()
        self.background = background
        self.watcher = QFileSystemWatcher(self)
        # Spicetify rewrites its files in several steps; reload once after they settle.
        self.reload_timer = QTimer(self, singleShot=True, interval=RELOAD_DELAY_MS, timeout=self.reload)
        self.watcher.fileChanged.connect(lambda _path: self.reload_timer.start())
        self.palette = manual_palette(background)
        self.reload()

    def reload(self):
        palette = manual_palette(self.background)
        if self.background["source"] == "spicetify":
            files, colors = find_spicetify_theme()
            if self.watcher.files():
                self.watcher.removePaths(self.watcher.files())
            if files:
                self.watcher.addPaths([str(path) for path in files])
            if colors:
                palette = {key: QColor(value) for key, value in colors.items()}
        self.palette = palette
        self.changed.emit(palette)


class ShootingStars(QObject):
    """Shooting stars of the StarryNight theme: fly down-left at 45° over 1500 px in 3–6 s,
    fade out over the last 30 %, then wait 0–7 s before the next flight."""

    updated = Signal()

    def __init__(self, width, height, scale):
        super().__init__()
        self.width, self.height, self.scale = width, height, scale
        self.rng = random.Random()
        now = time.monotonic()
        self.flights = [self._new_flight(now) for _ in range(SHOOTING_STAR_COUNT)]
        self.was_visible = False
        self.timer = QTimer(self, interval=1000 // SHOOTING_STAR_FPS, timeout=self._tick)

    def _new_flight(self, now):
        if self.rng.random() < 0.75:
            x, y = self.width * (1 - self.rng.uniform(0, 0.9)), -4 * self.scale
        else:
            x, y = self.width + 4 * self.scale, self.height * self.rng.uniform(0, 0.5)
        return x, y, now + self.rng.randint(0, 6), self.rng.randint(3, 6)

    def start(self):
        if not self.timer.isActive():
            self.timer.start()

    def stop(self):
        self.timer.stop()

    def _tick(self):
        now = time.monotonic()
        self.flights = [
            self._new_flight(now) if now > start + duration else (x, y, start, duration)
            for x, y, start, duration in self.flights
        ]
        visible = any(self._is_on_screen(head) for head in self.heads(now))
        # Repaint only while a star crosses the window, plus one frame to erase the last one.
        if visible or self.was_visible:
            self.updated.emit()
        self.was_visible = visible

    def _is_on_screen(self, head):
        x, y, _ = head
        tail = SHOOTING_STAR_TAIL * self.scale
        return -tail < x < self.width + tail and -tail < y < self.height + tail

    def heads(self, now=None):
        now = time.monotonic() if now is None else now
        for x, y, start, duration in self.flights:
            progress = (now - start) / duration
            if 0 <= progress <= 1:
                distance = SHOOTING_STAR_TRAVEL * self.scale * progress
                opacity = 1.0 if progress < 0.7 else (1 - progress) / 0.3
                yield x - distance * DIAGONAL, y + distance * DIAGONAL, opacity
