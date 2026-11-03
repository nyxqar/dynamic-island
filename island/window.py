import ctypes
import math
import random
from ctypes import wintypes

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QLayout, QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from config import DEFAULTS, save_config, tr
from modules.clock import ClockWidget
from modules.theme import DIAGONAL, SHOOTING_STAR_TAIL, ShootingStars, ThemeSource

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0002, 0x0010, 0x0200
WAVE_HEIGHT = 22
# Per-frame smoothing of the bottom wave: bars jump up quickly and fall back slowly.
WAVE_RISE, WAVE_FALL = 0.5, 0.12
ICON_NOTES = ""
PANEL_WIDTH, PANEL_WIDTH_LYRICS, PANEL_HEIGHT = 360, 680, 150
# While dragging, the island snaps to the screen's horizontal center when this close (px).
SNAP_PX = 12

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t

_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
]
_user32.SetWindowPos.restype = wintypes.BOOL


def set_no_activate(hwnd):
    style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


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


class Pill(QWidget):
    entered = Signal()
    left = Signal()

    def __init__(self, parent, max_radius, scale, stars, shooting_stars):
        super().__init__(parent)
        self.max_radius = max_radius
        self.scale = scale
        self.stars = stars
        self.shooting_stars = shooting_stars
        self.palette_colors = None

    def set_palette(self, palette):
        self.palette_colors = palette
        self.update()

    def enterEvent(self, event):
        self.entered.emit()

    def leaveEvent(self, event):
        self.left.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window().start_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.window().drag_to(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window().end_drag()
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        radius = min(self.height() / 2, self.max_radius)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()), radius, radius)
        colors = self.palette_colors
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, colors["top"])
        gradient.setColorAt(1, colors["bottom"])
        painter.fillPath(shape, gradient)

        painter.setClipPath(shape)
        # Everything in the sky is placed in window coordinates, so the expanding pill reveals it instead of stretching it.
        painter.translate(-self.x(), -self.y())
        painter.setBrush(colors["star"])
        for x, y, size, opacity in self.stars:
            painter.setOpacity(opacity)
            painter.drawEllipse(QRectF(x, y, size, size))
        if self.shooting_stars:
            for head in self.shooting_stars.heads():
                self._paint_shooting_star(painter, *head)

    def _paint_shooting_star(self, painter, x, y, opacity):
        s = self.scale
        tail = SHOOTING_STAR_TAIL * s
        painter.setOpacity(opacity)
        gradient = QLinearGradient(x, y, x + tail * DIAGONAL, y - tail * DIAGONAL)
        gradient.setColorAt(0, colors_with_alpha(self.palette_colors["shooting_star"], 255))
        gradient.setColorAt(1, colors_with_alpha(self.palette_colors["shooting_star"], 0))
        painter.setPen(QPen(gradient, max(1.0, s)))
        painter.drawLine(QPointF(x, y), QPointF(x + tail * DIAGONAL, y - tail * DIAGONAL))
        painter.setPen(Qt.NoPen)
        # The theme's box-shadow: two 4 px glow rings at 10 % opacity around a 4 px head.
        painter.setBrush(colors_with_alpha(self.palette_colors["shooting_glow"], 26))
        for ring in (6 * s, 10 * s):
            painter.drawEllipse(QPointF(x, y), ring, ring)
        painter.setBrush(self.palette_colors["shooting_star"])
        painter.drawEllipse(QPointF(x, y), 2 * s, 2 * s)


class IslandWindow(QWidget):
    def __init__(self, config, media=None, lyrics=None, spectrum=None):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.config = config
        scale = config["scale"]

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
        # The window always has the largest pill size; only the pill inside is animated.
        # Fully transparent pixels of a translucent window are click-through on Windows,
        # so the empty area does not block whatever is underneath.
        # Below the pill there is room for the audio wave hanging down from its bottom edge.
        self.wave_room = round(WAVE_HEIGHT * scale) if spectrum else 0
        self.setFixedSize(
            max(s.width() for s in self.sizes.values()),
            max(s.height() for s in self.sizes.values()) + self.wave_room,
        )

        background = config["background"]
        stars = make_stars(self.width(), self.height(), scale) if background["stars"] else []
        self.shooting_stars = None
        if background["shooting_stars"]:
            self.shooting_stars = ShootingStars(self.width(), self.height(), scale)
        self.pill = Pill(self, 28 * scale, scale, stars, self.shooting_stars)
        if self.shooting_stars:
            self.shooting_stars.updated.connect(self.pill.update)
        self.theme = ThemeSource(background)
        self.pill.set_palette(self.theme.palette)
        self.theme.changed.connect(self.pill.set_palette)
        layout = QVBoxLayout(self.pill)
        # Without this the layout would force the pill's minimum size to the largest page,
        # and the geometry animation could never shrink it.
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        margin = round(12 * scale)
        layout.setContentsMargins(margin, round(4 * scale), margin, round(4 * scale))
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.clock = ClockWidget(config, scale) if config["modules"]["clock"] else None
        self.pages = {"clock": self.clock or QWidget()}

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
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.notes_button = self._make_notes_button(scale)

        self.expanded = False
        self.open = False
        self.user_hidden = False
        self._shown = None
        self._drag_offset = None
        self._drag_start = None
        self._menu_open = False

        self.anim = QPropertyAnimation(self.pill, b"geometry", self)
        self.anim.setDuration(250)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(self._on_anim_finished)

        self.collapse_timer = QTimer(self, singleShot=True, interval=600, timeout=self.collapse)
        self.pill.entered.connect(self._on_enter)
        self.pill.left.connect(self.collapse_timer.start)

        self.spectrum = spectrum
        self.wave_levels = []
        self.wave = None
        self.wave_pulse = 0.0
        self.wave_accent = QColor(config["accent"]) if config["accent"] != "cover" else QColor("#ff4d6d")
        self.wave_timer = QTimer(self, interval=16, timeout=self._update_wave)

        self.topmost_timer = QTimer(self, interval=500, timeout=self._keep_on_top)
        self.topmost_timer.start()

        self.pill.setGeometry(self._pill_rect(self.sizes["clock", False]))
        self._refresh()
        set_no_activate(int(self.winId()))
        app = QGuiApplication.instance()
        for screen in app.screens():
            screen.geometryChanged.connect(self._reposition)
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._reposition)
        app.primaryScreenChanged.connect(self._reposition)
        self._reposition()
        self._update_visibility()

    def _make_notes_button(self, scale):
        button = QPushButton(ICON_NOTES, self.pill)
        font = QFont()
        font.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
        font.setPixelSize(round(15 * scale))
        button.setFont(font)
        button.setFocusPolicy(Qt.NoFocus)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tr(self.config, "notes"))
        button.setStyleSheet(
            "QPushButton { color: white; background: transparent; border: none; padding: 4px; }"
            "QPushButton:hover { color: #bbbbbb; }"
        )
        button.adjustSize()
        button.clicked.connect(self.toggle_notes)
        button.hide()
        return button

    def _show_notes_button(self):
        # Only on the expanded clock; the media panel has its own button among the controls.
        visible = self._shown == ("clock", True) and self.anim.state() != QAbstractAnimation.Running
        if visible:
            margin = round(14 * self.config["scale"])
            b = self.notes_button
            b.move(self.pill.width() - b.width() - margin, (self.pill.height() - b.height()) // 2)
            b.raise_()
        self.notes_button.setVisible(visible)

    def _pill_rect(self, size):
        x = (self.width() - size.width()) // 2
        geo = (QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()).geometry()
        if self.x() <= geo.left():
            x = geo.left() - self.x()
        elif self.x() + self.width() >= geo.right() + 1:
            x = geo.right() + 1 - self.x() - size.width()
        return QRect(x, 0, size.width(), size.height())

    def _place_pill(self):
        if self._shown is None:
            return
        rect = self._pill_rect(self.sizes[self._shown])
        if self.anim.state() == QAbstractAnimation.Running:
            self.anim.setEndValue(rect)
        else:
            self.pill.setGeometry(rect)

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
        x = geo.x() + (geo.width() - self.width()) // 2 + pos["offset_x"]
        self.move(x, geo.y() + pos["offset_y"])
        self._place_pill()

    def start_drag(self, global_pos):
        self._drag_offset = global_pos - self.pos()
        self._drag_start = self.pos()

    def drag_to(self, global_pos):
        if self._drag_offset is None or self.config["position"]["locked"]:
            return
        geo = (QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()).geometry()
        target = global_pos - self._drag_offset
        pad = (self.width() - self.pill.width()) // 2
        x = min(max(target.x(), geo.left() - pad), geo.right() + 1 - pad - self.pill.width())
        y = min(max(target.y(), geo.top()), geo.bottom() - self.height() + 1)
        if abs(x + self.width() // 2 - (geo.x() + geo.width() // 2)) <= SNAP_PX:
            x = geo.x() + (geo.width() - self.width()) // 2
        self.move(x, y)
        self._place_pill()

    def end_drag(self):
        if self._drag_offset is None:
            return
        self._drag_offset = None
        if self.pos() == self._drag_start:
            self.toggle_open()
            return
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        pos = self.pos()
        self.config["position"].update({
            "offset_x": pos.x() - (geo.x() + (geo.width() - self.width()) // 2),
            "offset_y": pos.y() - geo.y(),
            "screen": screen.name(),
        })
        save_config(self.config)

    def toggle_open(self):
        self.open = not self.open
        self.collapse_timer.stop()
        self.expanded = self.open or self.pill.underMouse()
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
        if not self.pill.underMouse():
            self.collapse_timer.start()

    def toggle_notes(self):
        if self.notes is None:
            from modules.notes import NotesWindow

            self.notes = NotesWindow(self.config)
        pill = self.pill.geometry().translated(self.pos())
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
        if self.shooting_stars:
            if should_show:
                self.shooting_stars.start()
            else:
                self.shooting_stars.stop()
        if self.spectrum:
            if should_show:
                self.wave_timer.start()
            else:
                self.wave_timer.stop()

    def _keep_on_top(self):
        # Raising the island above its own context menu would put it under the cursor and swallow the click.
        if self.isVisible() and QApplication.activePopupWidget() is None:
            bring_to_top(int(self.winId()))

    def _current_page(self):
        if self.media_state:
            if self.expanded:
                return "panel"
            if self.media_state.playing:
                return "compact"
        return "clock"

    def _refresh(self):
        page = self._current_page()
        shown = (page, self.expanded)
        if shown == self._shown:
            return
        self._shown = shown
        self.notes_button.hide()
        self.stack.setCurrentWidget(self.pages[page])
        if self.clock:
            self.clock.set_expanded(False)
        self.anim.stop()
        self.anim.setStartValue(self.pill.geometry())
        self.anim.setEndValue(self._pill_rect(self.sizes[shown]))
        self.anim.start()

    def _on_anim_finished(self):
        if self.clock and self._shown == ("clock", True):
            self.clock.set_expanded(True)
        self._show_notes_button()

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
        self.media_state = state
        self.compact.set_state(state)
        self.panel.set_state(state)
        self._refresh()

    def _on_lyrics_toggled(self, visible, animate=True):
        scale = self.config["scale"]
        width = PANEL_WIDTH_LYRICS if visible else PANEL_WIDTH
        self.sizes["panel", True] = QSize(round(width * scale), round(self.panel_height * scale))
        if animate:
            self._shown = None
            self._refresh()

    def _on_accent_changed(self, color):
        self.wave_accent = color

    def _update_wave(self):
        playing = self.media_state is not None and self.media_state.playing
        snapshot = self.spectrum.snapshot() if playing else None
        if snapshot is None:
            target, pulse = [0.0] * len(self.wave_levels), 0.0
        else:
            levels, since_beat = snapshot
            target, pulse = levels.tolist(), math.exp(-since_beat * 7)
        if len(self.wave_levels) != len(target):
            self.wave_levels = [0.0] * len(target)
        self.wave_levels = [
            value + (goal - value) * (WAVE_RISE if goal > value else WAVE_FALL)
            for value, goal in zip(self.wave_levels, target)
        ]
        if snapshot is None and max(self.wave_levels, default=0.0) < 0.003:
            if self.wave:
                self.wave = None
                self.update()
            return
        self.wave = self.wave_levels
        self.wave_pulse = pulse
        self.update()

    def paintEvent(self, event):
        if not self.wave:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pill = self.pill.geometry()
        # Inset by the corner radius, so the wave starts where the pill's bottom edge is straight.
        inset = min(pill.height() / 2, self.pill.max_radius)
        left, right = pill.x() + inset, pill.x() + pill.width() - inset
        top = pill.y() + pill.height()
        # Bass in the middle, highs towards both edges, so the wave is symmetric like the pill.
        levels = self.wave[::-1] + self.wave
        peak = self.wave_room * (0.6 + 0.4 * self.wave_pulse)
        last = len(levels) - 1
        points = [QPointF(left + (right - left) * i / last, top + peak * value) for i, value in enumerate(levels)]
        path = QPainterPath(QPointF(left, top))
        path.lineTo(points[0])
        for a, b in zip(points, points[1:]):
            path.quadTo(a, QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
        path.lineTo(points[-1])
        path.lineTo(right, top)
        path.closeSubpath()
        gradient = QLinearGradient(0, top, 0, top + peak)
        gradient.setColorAt(0, colors_with_alpha(self.wave_accent, 220))
        gradient.setColorAt(1, colors_with_alpha(self.wave_accent, 0))
        painter.fillPath(path, gradient)
