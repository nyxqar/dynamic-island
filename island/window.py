import ctypes
import math
import random
from ctypes import wintypes

import numpy as np
from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion,
)
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from config import DEFAULTS, save_config, tr
from modules.clock import ClockWidget
from modules.theme import DIAGONAL, SHOOTING_STAR_TAIL, ShootingStars, ThemeSource
from ui import effects
from ui.liquid_shape import POINTS, LiquidShape, Spring

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0002, 0x0010, 0x0200
WAVE_HEIGHT = 24
# The bottom edge turns into a wave while music plays: amplitude, wavelength (px) and drift (rad/s).
WAVE_AMPLITUDE, WAVE_PERIOD, WAVE_SPEED = 8, 46, 2.6
# How far the whole bottom edge drops on a bass hit (px).
BEAT_DROP = 9
# Closer than this to the top edge the island sticks to it; it lets go again past UNSTICK_PX.
# While stuck it follows the cursor only by RUBBER of the distance, like stretched rubber.
STICK_PX, UNSTICK_PX, RUBBER = 24, 56, 0.2
ICON_NOTES = ""
PANEL_WIDTH, PANEL_WIDTH_LYRICS, PANEL_HEIGHT = 360, 680, 150
MAX_RADIUS = 28
# While dragging, the island snaps to the screen's horizontal center when this close (px).
SNAP_PX = 12
DRAG_THRESHOLD = 3
COLLAPSE_DELAY_MS = 600

PHYSICS_DT = 1 / 120
# After a long stall, drop the backlog instead of simulating seconds of physics in one frame.
MAX_STEPS = 8
POLL_MS = 50
SHADOW_BLUR, SHADOW_OFFSET = 24, 4
IDLE_AFTER_S = 60
IDLE_AMPLITUDE, IDLE_PERIOD = 2.5, 4.0
PULL_RADIUS, PULL_MAX = 120, 10
# Content transitions (seconds): the old page fades out, the new one slides in band by band.
APPEAR_DELAY, APPEAR, STAGGER, FADE_OUT, SLIDE = 0.09, 0.22, 0.03, 0.10, 6

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32")
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
]
_user32.SetWindowPos.restype = wintypes.BOOL


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    info = _LastInput(ctypes.sizeof(_LastInput))
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((_kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def set_ex_style(hwnd, add=0, remove=0):
    style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, (style | add) & ~remove)


def bring_to_top(hwnd):
    # Fullscreen windows and the taskbar can end up above other topmost windows, so this is re-applied periodically.
    _user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    )


def colors_with_alpha(color, alpha):
    result = QColor(color)
    result.setAlpha(alpha)
    return result


def make_stars(width, height, scale):
    # Same parameters as the StarryNight Spicetify theme: one star per 4000 px²,
    # 1 or 2 px in size, opacity 0.5–1. Fixed seed so the sky does not change between launches.
    rng = random.Random(1)
    count = round(width * height / (4000 * scale * scale))
    return [
        (rng.uniform(0, width), rng.uniform(0, height), rng.choice((1, 2)) * scale, rng.uniform(0.5, 1))
        for _ in range(count)
    ]


def snapshot(widget):
    """The widget's current look on a transparent background, even while it is hidden."""
    dpr = widget.devicePixelRatioF()
    pixmap = QPixmap(max(1, round(widget.width() * dpr)), max(1, round(widget.height() * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.transparent)
    widget.render(pixmap, QPoint(), QRegion(), QWidget.DrawChildren)
    return pixmap


class ClockPage(QWidget):
    """The clock plus the notes button, which only shows on the expanded clock."""

    def __init__(self, clock, config, scale, on_notes):
        super().__init__()
        self.clock = clock
        self.scale = scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if clock:
            layout.addWidget(clock)
        self.notes_button = QPushButton(ICON_NOTES, self)
        font = QFont()
        font.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
        font.setPixelSize(round(15 * scale))
        self.notes_button.setFont(font)
        self.notes_button.setFocusPolicy(Qt.NoFocus)
        self.notes_button.setCursor(Qt.PointingHandCursor)
        self.notes_button.setToolTip(tr(config, "notes"))
        self.notes_button.setStyleSheet(
            "QPushButton { color: white; background: transparent; border: none; padding: 4px; }"
            "QPushButton:hover { color: #bbbbbb; }"
        )
        self.notes_button.adjustSize()
        self.notes_button.clicked.connect(on_notes)
        self.notes_button.hide()

    def set_expanded(self, expanded):
        if self.clock:
            self.clock.set_expanded(expanded)
        self.notes_button.setVisible(expanded)
        self._place_button()

    def resizeEvent(self, event):
        self._place_button()

    def _place_button(self):
        b = self.notes_button
        b.move(self.width() - b.width() - round(2 * self.scale), (self.height() - b.height()) // 2)
        b.raise_()


class IslandWindow(QWidget):
    settings_requested = Signal()

    def __init__(self, config, media=None, lyrics=None, spectrum=None):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.config = config
        scale = config["scale"]
        self.scale = scale

        def size(width, height):
            return QSize(round(width * scale), round(height * scale))

        self.panel_height = PANEL_HEIGHT
        if media and config["dancer"]:
            from modules.dancer import ROOM

            self.panel_height += ROOM
        # (page, expanded) -> pill size
        self.sizes = {
            ("clock", False): size(180, 36),
            ("clock", True): size(360, 96),
            ("compact", False): size(260, 36),
            ("panel", True): size(PANEL_WIDTH_LYRICS if lyrics else PANEL_WIDTH, self.panel_height),
        }
        # The window has room for the largest pill plus its spring overshoot, the wave and the shadow;
        # only the shape inside moves. Clicks outside the shape pass through (see _set_click_through).
        self.shadow_margin = math.ceil(1.5 * SHADOW_BLUR * scale)
        self.wave_room = round(WAVE_HEIGHT * scale) if spectrum else 0
        max_w = max(s.width() for s in self.sizes.values())
        max_h = max(s.height() for s in self.sizes.values())
        # Away from the top edge the shape moves down by shadow_margin inside the window, so the shadow above it fits.
        self.setFixedSize(
            math.ceil(max_w * 1.08) + 2 * self.shadow_margin,
            math.ceil(max_h * 1.08 + max(self.wave_room + 4 * scale, self.shadow_margin + SHADOW_OFFSET * scale))
            + self.shadow_margin,
        )

        background = config["background"]
        self.stars = make_stars(self.width(), self.height(), scale) if background["stars"] else []
        self.shooting_stars = None
        if background["shooting_stars"]:
            self.shooting_stars = ShootingStars(self.width(), self.height(), scale)
            self.shooting_stars.updated.connect(self._repaint_shape)
        self.theme = ThemeSource(background)
        self.palette_colors = self.theme.palette
        self.theme.changed.connect(self._set_palette)
        self._shadow_tile = effects.shadow_tile(18 * scale, SHADOW_BLUR * scale, 0.35)

        self.content_margins = (round(12 * scale), round(4 * scale))
        self.stack = QStackedWidget(self)
        self.clock = ClockWidget(config, scale) if config["modules"]["clock"] else None
        self.clock_page = ClockPage(self.clock, config, scale, self.toggle_notes)
        self.pages = {"clock": self.clock_page}

        self.notes = None
        self.media_state = None
        self.compact = self.panel = None
        if media:
            from modules.media import MediaCompact, MediaPanel

            self.compact = MediaCompact(scale)
            self.panel = MediaPanel(config, scale, media, lyrics)
            self.pages["compact"] = self.compact
            self.pages["panel"] = self.panel
            media.changed.connect(self._on_media_changed)
            self.panel.lyrics_toggled.connect(self._on_lyrics_toggled)
            self._on_lyrics_toggled(self.panel.lyrics_visible, animate=False)
            self.panel.accent_changed.connect(self._on_accent_changed)
            self.panel.notes_requested.connect(self.toggle_notes)
            if self.panel.dancer and spectrum:
                self.panel.dancer.set_tempo_source(spectrum)
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.expanded = False
        self.open = False
        self.user_hidden = False
        self._shown = None
        self._drag_offset = None
        self._drag_start = None
        self._dragged = False
        self._menu_open = False
        self._hovered = False
        self._click_through = None
        self._last_cursor = None
        self._was_near = False
        self._poll_ticks = 0
        self._idle_since = None
        self._incoming = None
        self._outgoing = None

        # gap: distance from the screen's top edge; attach: 1 glued to it, 0 floating.
        # Stiff and nearly critically damped: follows the cursor closely but never jerks.
        self.gap = Spring(0.0, 520.0, 42.0)
        self.attach = Spring(1.0, 260.0, 26.0)
        self._frac_y = 0.0
        self._stuck = True
        self._drag_dy = 0

        self.spectrum = spectrum
        self.eq = None
        self.wave_pulse = 0.0
        self.wave_phase = 0.0
        self.wave_accent = QColor(config["accent"]) if config["accent"] != "cover" else QColor("#ff4d6d")

        first = self.sizes["clock", False]
        self.shape = LiquidShape(first.width(), first.height(), MAX_RADIUS * scale, self.width() / 2)
        # Screen x of the island's center. The window always keeps the island in its middle (it may hang
        # past the screen edge), so the island never jumps inside the window.
        self.sx = Spring(0.0)
        self._frac_x = 0.0
        self._anchor_x = 0.0
        self._side = None
        self._rubber_x = 0.0
        self._drag_dx = 0
        self._path = self.shape.path()
        self._dirty_rect = self.rect()

        self.clock_timer = QElapsedTimer()
        self.clock_timer.start()
        self.frame_timer = QTimer(self, timeout=self._frame)
        self.frame_timer.setTimerType(Qt.PreciseTimer)
        refresh = QGuiApplication.primaryScreen().refreshRate() or 60
        self.frame_timer.setInterval(max(1, int(1000 / min(refresh, 120))))
        self._last = 0.0
        self._acc = 0.0

        self.collapse_timer = QTimer(self, singleShot=True, interval=COLLAPSE_DELAY_MS, timeout=self.collapse)
        self.poll_timer = QTimer(self, interval=POLL_MS, timeout=self._poll)
        self.poll_timer.start()
        self.topmost_timer = QTimer(self, interval=500, timeout=self._keep_on_top)
        self.topmost_timer.start()

        set_ex_style(int(self.winId()), add=WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        app = QGuiApplication.instance()
        for screen in app.screens():
            screen.geometryChanged.connect(self._reposition)
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._reposition)
        app.primaryScreenChanged.connect(self._reposition)
        self._reposition()
        self._refresh(animate=False)
        self._update_visibility()

    # --- Geometry -----------------------------------------------------------------------------------------------

    def _content_rect(self, size):
        mh, mv = self.content_margins
        width = size.width() - 2 * mh
        return QRect(round(self.width() / 2 - width / 2), round(self._inset()) + mv, width, size.height() - 2 * mv)

    def _inset(self):
        """How far the shape sits below the window's top edge (room for the shadow while floating)."""
        return self.shadow_margin * effects.clamp(1 - self.attach.value)

    def _place_window(self):
        geo = self._target_screen().geometry()
        exact_x = self.sx.value - self.width() / 2
        exact_y = geo.top() + self.gap.value - self._inset()
        x, y = round(exact_x), round(exact_y)
        # The window can only move by whole pixels; the remainder shifts the shape inside it,
        # so the island glides instead of stepping.
        self._frac_x, self._frac_y = exact_x - x, exact_y - y
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
        cx = self.width() / 2 + self._frac_x
        if cx != self.shape.cx:
            self.shape.cx = cx
            self.shape.update_base()
        self._apply_float()

    def _x_limits(self, size=None):
        geo = self._target_screen().geometry()
        half = (size or self.sizes[self._shown or ("clock", False)]).width() / 2
        return geo.left() + half, geo.right() + 1 - half

    def _place_pill(self):
        """Point the horizontal spring at where the island should be for its current size."""
        low, high = self._x_limits()
        if self._side == "left":
            # Stuck to the side: the edge stays flush as the island grows, and stretches while dragged.
            target = low + self._rubber_x
        elif self._side == "right":
            target = high - self._rubber_x
        else:
            target = min(max(self._anchor_x, low), high)
        self.sx.target = target
        self.wake()

    def _on_screen_added(self, screen):
        screen.geometryChanged.connect(self._reposition)

    def _target_screen(self):
        name = self.config["position"]["screen"]
        for screen in QGuiApplication.screens():
            if screen.name() == name:
                return screen
        return QGuiApplication.primaryScreen()

    def _reposition(self):
        geo = self._target_screen().geometry()
        pos = self.config["position"]
        self._anchor_x = geo.x() + geo.width() / 2 + pos["offset_x"]
        low, high = self._x_limits(self.sizes["clock", False])
        stick = STICK_PX * self.scale
        self._side = "left" if self._anchor_x - low < stick else "right" if high - self._anchor_x < stick else None
        self._rubber_x = 0.0
        self._place_pill()
        self.sx.snap(self.sx.target)
        # Near the top edge counts as stuck to it, so old configs with a small offset_y stay glued.
        gap = pos["offset_y"] if pos["offset_y"] >= STICK_PX * self.scale else 0
        gap = min(gap, max(0, geo.height() - self.sizes["clock", False].height()))
        self._stuck = gap == 0
        self.gap.snap(gap)
        self.attach.snap(1.0 if self._stuck else 0.0)
        self._apply_float()
        self._place_window()

    def _apply_float(self):
        top = self._inset() + self._frac_y
        amount = effects.clamp(1 - self.attach.value)
        if (top, amount) != (self.shape.top, self.shape.float_amount):
            self.shape.top = top
            self.shape.float_amount = amount
            self.shape.update_base()

    # --- Dragging -----------------------------------------------------------------------------------------------

    def start_drag(self, global_pos):
        self._drag_offset = global_pos - self.pos()
        self._drag_dx = global_pos.x() - self.sx.value
        self._drag_dy = global_pos.y() - (self._target_screen().geometry().top() + self.gap.value)
        self._drag_start = global_pos
        self._dragged = False
        # Stiff while following the cursor; the softer size spring otherwise, so a stuck side stays flush.
        self.sx.stiffness, self.sx.damping = self.gap.stiffness, self.gap.damping

    def _stick_side(self, raw, low, high):
        """Side magnet with the same feel as the top edge; returns the rubber offset for a stuck side."""
        stick, unstick = STICK_PX * self.scale, UNSTICK_PX * self.scale
        to_left, to_right = raw - low, high - raw
        if self._side == "left" and to_left > unstick or self._side == "right" and to_right > unstick:
            self._side = None
        if self._side is None:
            if to_left < stick:
                self._side = "left"
            elif to_right < stick:
                self._side = "right"
        distance = to_left if self._side == "left" else to_right if self._side == "right" else 0.0
        return max(distance, 0.0) * RUBBER

    def drag_to(self, global_pos):
        if self._drag_offset is None:
            return
        if not self._dragged:
            if (global_pos - self._drag_start).manhattanLength() < DRAG_THRESHOLD:
                return
            self._dragged = True
        if self.config["position"]["locked"]:
            return
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen.name() != self.config["position"]["screen"]:
            self.config["position"]["screen"] = screen.name()
        geo = screen.geometry()
        size = self.sizes[self._shown]
        raw = global_pos.x() - self._drag_dx
        centre = geo.x() + geo.width() / 2
        if abs(raw - centre) <= SNAP_PX * self.scale:
            raw = centre
        low, high = self._x_limits(size)
        self._rubber_x = self._stick_side(raw, low, high)
        self._anchor_x = min(max(raw, low), high)

        gap =min(max(global_pos.y() - self._drag_dy - geo.top(), 0), geo.height() - size.height())
        unstick = UNSTICK_PX * self.scale
        if self._stuck and gap > unstick:
            self._stuck = False
        elif not self._stuck and gap < STICK_PX * self.scale:
            self._stuck = True
        if self._stuck:
            # Held by the edge: stretches a little towards the cursor and starts rounding its corners.
            self.gap.target = gap * RUBBER
            self.attach.target = 1.0 - 0.5 * min(gap / unstick, 1.0)
        else:
            self.gap.target = float(gap)
            self.attach.target = 0.0
        self._place_window()
        self._place_pill()

    def end_drag(self):
        if self._drag_offset is None:
            return
        self._drag_offset = None
        self.sx.stiffness, self.sx.damping = self.shape.width.stiffness, self.shape.width.damping
        if not self._dragged:
            self.toggle_open()
            return
        if self.config["position"]["locked"]:
            return
        if self._stuck:
            self.gap.target = 0.0
            self.attach.target = 1.0
        self._rubber_x = 0.0
        if self._side:
            # Saved against the collapsed size, so the next launch recognises the island as stuck to the side.
            low, high = self._x_limits(self.sizes["clock", False])
            self._anchor_x = low if self._side == "left" else high
        self._place_pill()
        screen = self._target_screen()
        geo = screen.geometry()
        self.config["position"].update({
            "offset_x": round(self._anchor_x - (geo.x() + geo.width() / 2)),
            "offset_y": 0 if self._stuck else round(self.gap.target),
            "screen": screen.name(),
        })
        save_config(self.config)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.drag_to(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.end_drag()
            event.accept()

    # --- Menu and visibility ------------------------------------------------------------------------------------

    def toggle_open(self):
        self.open = not self.open
        self.collapse_timer.stop()
        self.expanded = self.open or self._hovered
        self._refresh()

    def center_on_screen(self):
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        self.config["position"].update({"offset_x": 0, "screen": screen.name()})
        save_config(self.config)
        self._reposition()

    def set_locked(self, locked):
        self.config["position"]["locked"] = locked
        save_config(self.config)

    def reset_position(self):
        self.config["position"].update(DEFAULTS["position"])
        save_config(self.config)
        self._reposition()

    def contextMenuEvent(self, event):
        locked = self.config["position"]["locked"]
        menu = QMenu(self)
        menu.addAction(tr(self.config, "notes"), self.toggle_notes)
        menu.addAction(tr(self.config, "settings"), self.settings_requested.emit)
        menu.addAction(tr(self.config, "hide"), self.toggle_user_visibility)
        menu.addSeparator()
        center = menu.addAction(tr(self.config, "center"), self.center_on_screen)
        reset = menu.addAction(tr(self.config, "reset_position"), self.reset_position)
        center.setEnabled(not locked)
        reset.setEnabled(not locked)
        lock = menu.addAction(tr(self.config, "lock"))
        lock.setCheckable(True)
        lock.setChecked(locked)
        lock.toggled.connect(self.set_locked)
        self._menu_open = True
        self.collapse_timer.stop()
        try:
            menu.exec(event.globalPos())
        finally:
            self._menu_open = False
        if not self._hovered:
            self.collapse_timer.start()

    def toggle_notes(self):
        if self.notes is None:
            from modules.notes import NotesWindow

            self.notes = NotesWindow(self.config)
        size = self.sizes[self._shown]
        pill = QRect(round(self.shape.cx - size.width() / 2), round(self._inset()), size.width(), size.height())
        pill.translate(self.pos())
        self.notes.toggle_near(pill, self.screen())

    def toggle_user_visibility(self):
        self.user_hidden = not self.user_hidden
        self._update_visibility()

    def _update_visibility(self):
        should_show = not self.user_hidden
        if should_show != self.isVisible():
            self.setVisible(should_show)
            if should_show:
                self._keep_on_top()
                self.wake()
        if self.shooting_stars:
            if should_show:
                self.shooting_stars.start()
            else:
                self.shooting_stars.stop()

    def _keep_on_top(self):
        # Raising the island above its own context menu would put it under the cursor and swallow the click.
        if self.isVisible() and QApplication.activePopupWidget() is None:
            bring_to_top(int(self.winId()))

    # --- Pages --------------------------------------------------------------------------------------------------

    def _current_page(self):
        if self.media_state:
            if self.expanded:
                return "panel"
            if self.media_state.playing:
                return "compact"
        return "clock"

    def _refresh(self, animate=True):
        page = self._current_page()
        shown = (page, self.expanded)
        if shown == self._shown:
            return
        self._shown = shown
        size = self.sizes[shown]
        self.shape.set_size(size.width(), size.height())
        self._place_pill()
        if not animate:
            self.shape.width.snap(size.width())
            self.shape.height.snap(size.height())
            self.sx.snap(self.sx.target)
            self._place_window()
            self.shape.update_base()
            self._path = self.shape.path()
        self._switch_content(page, shown, size, animate)
        self.wake()

    def _switch_content(self, page, shown, size, animate):
        now = self._now()
        old = None
        if animate:
            if self.stack.isVisible():
                old = (snapshot(self.stack), QRectF(self.stack.geometry()))
            elif self._incoming:
                old = self._incoming[:2]
        self.stack.hide()
        self.stack.setCurrentWidget(self.pages[page])
        self.clock_page.set_expanded(shown == ("clock", True))
        self.stack.setGeometry(self._content_rect(size))
        if not animate:
            self._incoming = self._outgoing = None
            self.stack.show()
            return
        self._outgoing = (*old, now) if old else None
        bands = 1 if size.height() < 60 * self.scale else 3
        self._incoming = (snapshot(self.stack), QRectF(self.stack.geometry()), now + APPEAR_DELAY, bands)

    def _incoming_end(self):
        _, _, start, bands = self._incoming
        return start + (bands - 1) * STAGGER + APPEAR

    def _on_enter(self):
        self.collapse_timer.stop()
        if not self.expanded:
            self.expanded = True
            self._refresh()

    def collapse(self):
        if self._menu_open:
            return
        if QGuiApplication.mouseButtons() != Qt.NoButton:
            self.collapse_timer.start()
            return
        if self.expanded and not self.open:
            self.expanded = False
            self._refresh()

    def _on_media_changed(self, state):
        was_playing = bool(self.media_state and self.media_state.playing)
        self.media_state = state
        self.compact.set_state(state)
        self.panel.set_state(state)
        self._refresh()
        if bool(state and state.playing) != was_playing:
            self.wake()

    def _on_lyrics_toggled(self, visible, animate=True):
        width = PANEL_WIDTH_LYRICS if visible else PANEL_WIDTH
        self.sizes["panel", True] = QSize(round(width * self.scale), round(self.panel_height * self.scale))
        if animate:
            self._shown = None
            self._refresh()

    def _on_accent_changed(self, color):
        self.wave_accent = color

    def _set_palette(self, palette):
        self.palette_colors = palette
        self.update()

    def _repaint_shape(self):
        self.update(self._bounds())

    def _fill_opacity(self):
        """Background opacity, blended from the collapsed to the expanded value as the island grows."""
        opacity = self.config["opacity"]
        low = self.sizes["clock", False].height()
        high = max(size.height() for size in self.sizes.values())
        t = effects.clamp((self.shape.h - low) / max(high - low, 1))
        value = opacity["collapsed"] + (opacity["expanded"] - opacity["collapsed"]) * t
        return min(max(value, 0.2), 1.0)

    # --- Animation loop -----------------------------------------------------------------------------------------

    def _now(self):
        return self.clock_timer.nsecsElapsed() / 1e9

    def wake(self):
        if self.isVisible() and not self.frame_timer.isActive():
            self._last = self._now()
            self._acc = 0.0
            self.frame_timer.start()

    def _playing(self):
        return self.media_state is not None and self.media_state.playing

    def _frame(self):
        now = self._now()
        elapsed = now - self._last
        self._last = now
        self._acc += elapsed
        cursor = QPointF(self.mapFromGlobal(QCursor.pos()))
        steps = 0
        while self._acc >= PHYSICS_DT:
            if steps == MAX_STEPS:
                self._acc = 0.0
                break
            self._step(PHYSICS_DT, cursor, now)
            self._acc -= PHYSICS_DT
            steps += 1
        self._update_wave(elapsed)
        self._place_window()
        self._path = self.shape.path(self._wave if self.eq and self.eq.visible else None)

        if self._outgoing and now - self._outgoing[2] >= FADE_OUT:
            self._outgoing = None
        if self._incoming and now >= self._incoming_end():
            self._incoming = None
            self.stack.show()
        if self.stack.isVisible():
            # The live page follows the shape when it slides sideways or detaches from the top edge.
            x = round(self.shape.cx - self.stack.width() / 2)
            y = round(self._inset()) + self.content_margins[1]
            if (x, y) != (self.stack.x(), self.stack.y()):
                self.stack.move(x, y)

        dirty = self._bounds()
        self.update(dirty.united(self._dirty_rect))
        self._dirty_rect = dirty
        if self._settled():
            self.frame_timer.stop()

    def _step(self, dt, cursor, now):
        shape = self.shape
        s = self.scale
        self.sx.step(dt)
        self.gap.step(dt)
        self.attach.step(dt)
        self._apply_float()
        base, normal = shape.base, shape.normal
        target = np.zeros(POINTS)

        delta = np.array([cursor.x(), cursor.y()]) - base
        sigma = PULL_RADIUS * s / 2.5
        pull = PULL_MAX * s * np.exp(-(delta ** 2).sum(1) / (2 * sigma * sigma))
        # Never pull past the cursor itself.
        toward = np.maximum((delta * normal).sum(1), 0.0)
        target += np.minimum(pull, toward) * (normal[:, 1] > 0)

        if self._idle_since is not None:
            phase = (now - self._idle_since) * 2 * math.pi / IDLE_PERIOD
            sag = IDLE_AMPLITUDE * s * (0.5 - 0.5 * math.cos(phase))
            across = np.clip(1 - ((base[:, 0] - shape.cx) / (shape.w / 2)) ** 2, 0, 1)
            target += sag * np.maximum(normal[:, 1], 0) * across

        shape.target = target
        shape.step(dt)

    def _update_wave(self, elapsed):
        if not self.spectrum:
            return
        snap = self.spectrum.snapshot() if self._playing() else None
        levels = None
        if snap is not None:
            levels, since_beat = snap
            self.wave_pulse = math.exp(-since_beat * 7)
            if self.eq is None or len(self.eq.levels) != len(levels):
                self.eq = effects.Equalizer(len(levels))
        if self.eq is None:
            return
        self.eq.target_amount = 1.0 if levels is not None else 0.0
        self.eq.step(elapsed, levels)
        self.wave_phase = (self.wave_phase + elapsed * WAVE_SPEED) % (2 * math.pi)

    def _wave(self, xs):
        """Bottom-edge offsets: a travelling sine whose height follows the spectrum, bass on the left."""
        s = self.scale
        left, right = self.shape.x0, self.shape.x1
        levels = self.eq.levels
        n = len(levels)
        # Low bands weigh more, so the bass side moves the most.
        weighted = levels * (1 + 1.5 * np.exp(-np.arange(n) / 4))
        bands = np.interp((xs - left) / max(right - left, 1.0) * (n - 1), np.arange(n), weighted)
        loudness = np.minimum(0.3 * float(levels.mean()) + 0.7 * bands, 1.4)
        pulse = self.wave_pulse
        amplitude = WAVE_AMPLITUDE * s * self.eq.amount * loudness * (0.6 + 0.8 * pulse)
        wave = amplitude * np.sin(2 * np.pi * xs / (WAVE_PERIOD * s) - self.wave_phase)
        # Troughs go up only half as far, so they never cut into the controls near the bottom edge.
        wave = np.where(wave < 0, wave * 0.5, wave)
        # On a bass hit the whole edge drops down and springs back as the pulse decays.
        bass = float(levels[: max(1, n // 6)].mean())
        return wave + BEAT_DROP * s * self.eq.amount * pulse * bass

    def _settled(self):
        if not self.isVisible():
            return True
        return (
            self.shape.settled()
            and self.sx.settled()
            and self.gap.settled()
            and self.attach.settled(0.002)
            and self._incoming is None
            and self._outgoing is None
            and self._idle_since is None
            and not (self.spectrum and (self._playing() or (self.eq and self.eq.busy)))
        )

    def _bounds(self):
        margin = self.shadow_margin + 2
        extra = max(self.wave_room, SHADOW_OFFSET * self.scale)
        return self._path.boundingRect().adjusted(-margin, -margin, margin, margin + extra).toAlignedRect()

    # --- Input --------------------------------------------------------------------------------------------------

    def _poll(self):
        if not self.isVisible():
            return
        pos = QCursor.pos()
        local = QPointF(self.mapFromGlobal(pos))
        inside = self._path.contains(local)
        # While a button is held (dragging, seeking) the window keeps its mouse input.
        if QGuiApplication.mouseButtons() == Qt.NoButton or not inside:
            if self._drag_offset is None:
                self._set_click_through(not inside)
        if inside != self._hovered and self._drag_offset is None:
            self._hovered = inside
            if inside:
                self._on_enter()
            elif not self._menu_open:
                self.collapse_timer.start()
        if pos != self._last_cursor:
            reach = PULL_RADIUS * self.scale + 20
            near = self._path.boundingRect().adjusted(-reach, -reach, reach, reach).contains(local)
            if near or self._was_near:
                self.wake()
            self._was_near = near
            self._last_cursor = pos
        self._poll_ticks += 1
        if self._poll_ticks % 20 == 0:
            idle = idle_seconds() >= IDLE_AFTER_S
            if idle and self._idle_since is None:
                self._idle_since = self._now()
                self.wake()
            elif not idle and self._idle_since is not None:
                self._idle_since = None
                self.wake()

    def _set_click_through(self, on):
        # A translucent window only lets clicks through fully transparent pixels; the shadow is not.
        if on != self._click_through:
            self._click_through = on
            hwnd = int(self.winId())
            if on:
                set_ex_style(hwnd, add=WS_EX_TRANSPARENT)
            else:
                set_ex_style(hwnd, remove=WS_EX_TRANSPARENT)

    # --- Painting -----------------------------------------------------------------------------------------------

    def paintEvent(self, event):
        s = self.scale
        shape = self.shape
        path = self._path
        colors = self.palette_colors
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        opacity = self._fill_opacity()

        p.save()
        if opacity < 0.999:
            # Keep the shadow from showing through a translucent island.
            outside = QPainterPath()
            outside.addRect(QRectF(self.rect()))
            outside.addPath(path)
            outside.setFillRule(Qt.OddEvenFill)
            p.setClipPath(outside)
        effects.draw_nine_slice(p, QRectF(shape.x0, shape.top, shape.w, shape.h).translated(0, SHADOW_OFFSET * s),
                                *self._shadow_tile)
        p.restore()

        fill = QLinearGradient(0, shape.top, 0, shape.top + max(shape.h, 1.0))
        fill.setColorAt(0, colors["top"])
        fill.setColorAt(1, colors["bottom"])
        p.setOpacity(opacity)
        p.fillPath(path, fill)

        p.save()
        p.setClipPath(path)
        # The sky is anchored to the island's top, so it moves with the island when it leaves the screen edge.
        p.translate(0, shape.top)
        p.setPen(Qt.NoPen)
        p.setBrush(colors["star"])
        for x, y, size, star_opacity in self.stars:
            p.setOpacity(opacity * star_opacity)
            p.drawEllipse(QRectF(x, y, size, size))
        if self.shooting_stars:
            for x, y, star_opacity in self.shooting_stars.heads():
                self._paint_shooting_star(p, x, y, opacity * star_opacity)
        p.restore()
        p.strokePath(path, QPen(QColor(255, 255, 255, 20), 1))
        p.setOpacity(1)
        if shape.wave_line is not None and self.eq:
            pen = QPen(colors_with_alpha(self.wave_accent, round(235 * self.eq.amount)), 1.6 * s)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(shape.wave_line, pen)

        if self._outgoing or self._incoming:
            p.setClipPath(path)
            self._paint_transition(p)

    def _paint_transition(self, p):
        now = self._now()
        if self._outgoing:
            pixmap, rect, start = self._outgoing
            alpha = 1 - (now - start) / FADE_OUT
            if alpha > 0:
                p.setOpacity(alpha)
                p.drawPixmap(rect.topLeft(), pixmap)
        if self._incoming:
            pixmap, rect, start, bands = self._incoming
            dpr = pixmap.devicePixelRatio()
            band = rect.height() / bands
            for i in range(bands):
                t = effects.clamp((now - start - i * STAGGER) / APPEAR)
                if t <= 0:
                    continue
                a = effects.ease_out_cubic(t)
                top = band * i
                p.setOpacity(a)
                p.drawPixmap(
                    QRectF(rect.x(), rect.y() + top + SLIDE * self.scale * (1 - a), rect.width(), band),
                    pixmap,
                    QRectF(0, top * dpr, rect.width() * dpr, band * dpr),
                )
        p.setOpacity(1)

    def _paint_shooting_star(self, painter, x, y, opacity):
        s = self.scale
        colors = self.palette_colors
        tail = SHOOTING_STAR_TAIL * s
        painter.setOpacity(opacity)
        gradient = QLinearGradient(x, y, x + tail * DIAGONAL, y - tail * DIAGONAL)
        gradient.setColorAt(0, colors_with_alpha(colors["shooting_star"], 255))
        gradient.setColorAt(1, colors_with_alpha(colors["shooting_star"], 0))
        painter.setPen(QPen(gradient, max(1.0, s)))
        painter.drawLine(QPointF(x, y), QPointF(x + tail * DIAGONAL, y - tail * DIAGONAL))
        painter.setPen(Qt.NoPen)
        # The theme's box-shadow: two 4 px glow rings at 10 % opacity around a 4 px head.
        painter.setBrush(colors_with_alpha(colors["shooting_glow"], 26))
        for ring in (6 * s, 10 * s):
            painter.drawEllipse(QPointF(x, y), ring, ring)
        painter.setBrush(colors["shooting_star"])
        painter.drawEllipse(QPointF(x, y), 2 * s, 2 * s)
