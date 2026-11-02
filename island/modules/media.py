import asyncio
import math
import threading
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import winrt.windows.foundation  # noqa: F401  registers IAsyncOperation so WinRT calls can be awaited
import winrt.windows.foundation.collections  # noqa: F401  registers IVectorView returned by get_sessions()
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import Buffer, InputStreamOptions

from config import save_config
from modules.lyrics import ElidedLabel, LyricsView

POLL_INTERVAL = 0.5
MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
THUMBNAIL_RETRY_POLLS = 6
SEEK_HOLD_SECONDS = 1.5
ICON_LYRICS = ""
DEFAULT_ACCENT = QColor("#ff4d6d")
LEFT_COLUMN_WIDTH = 330
ICON_PREV, ICON_PLAY, ICON_PAUSE, ICON_NEXT, ICON_SWITCH = "", "", "", "", ""


@dataclass(frozen=True)
class MediaState:
    sessions: tuple
    app_id: str
    title: str
    artist: str
    album: str
    playing: bool
    position: float
    duration: float
    captured: float
    thumbnail: bytes | None

    def estimated_position(self):
        position = self.position + (time.monotonic() - self.captured if self.playing else 0)
        return min(position, self.duration) if self.duration > 0 else position


def app_name(app_id):
    name = app_id.split("!")[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.split(".")[-1] or app_id


def _seconds_since(moment):
    if moment.year < 2000:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - moment).total_seconds())


class MediaController(QObject):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self._loop = asyncio.new_event_loop()
        self._manager = None
        self._selected = None
        self._thumb_key = None
        self._thumb = None
        self._thumb_polls = 0
        self._last_error = None
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._poll())

    async def _poll(self):
        # Polling instead of WinRT change events: players differ in which events they fire
        # (browsers barely report timeline changes), polling behaves the same for all of them.
        while self._running:
            try:
                if self._manager is None:
                    self._manager = await SessionManager.request_async()
                state = await self._snapshot()
                self._last_error = None
            except Exception as error:
                # A session can vanish mid-call; one failed poll must not kill the worker thread.
                if repr(error) != self._last_error:
                    self._last_error = repr(error)
                    traceback.print_exc()
                state = None
            self.changed.emit(state)
            await asyncio.sleep(POLL_INTERVAL)

    def _find_session(self, sessions):
        for session in sessions:
            if session.source_app_user_model_id == self._selected:
                return session
        return self._manager.get_current_session() or sessions[0]

    async def _snapshot(self):
        sessions = list(self._manager.get_sessions())
        if not sessions:
            return None
        session = self._find_session(sessions)
        props = await session.try_get_media_properties_async()
        if props is None:
            return None
        playing = session.get_playback_info().playback_status == PlaybackStatus.PLAYING
        timeline = session.get_timeline_properties()
        position = timeline.position.total_seconds()
        if playing:
            position += _seconds_since(timeline.last_updated_time)
        duration = max(0.0, (timeline.end_time - timeline.start_time).total_seconds())
        app_id = session.source_app_user_model_id

        key = (app_id, props.title, props.artist)
        if key != self._thumb_key:
            self._thumb_key, self._thumb, self._thumb_polls = key, None, 0
        # Browsers often publish the title first and the artwork a moment later,
        # so the artwork is re-read for a few polls after a track change.
        if self._thumb_polls < THUMBNAIL_RETRY_POLLS:
            self._thumb_polls += 1
            data = await self._read_thumbnail(props.thumbnail)
            if data and data != self._thumb:
                self._thumb = data

        return MediaState(
            sessions=tuple(s.source_app_user_model_id for s in sessions),
            app_id=app_id,
            title=props.title,
            artist=props.artist,
            album=props.album_title,
            playing=playing,
            position=position,
            duration=duration,
            captured=time.monotonic(),
            thumbnail=self._thumb,
        )

    @staticmethod
    async def _read_thumbnail(reference):
        if reference is None:
            return None
        stream = await reference.open_read_async()
        size = stream.size
        if not 0 < size <= MAX_THUMBNAIL_BYTES:
            return None
        buffer = Buffer(size)
        await stream.read_async(buffer, size, InputStreamOptions.READ_AHEAD)
        return bytes(buffer)

    def _command(self, method_name, *args):
        async def run():
            if self._manager is None:
                return
            sessions = list(self._manager.get_sessions())
            if sessions:
                try:
                    await getattr(self._find_session(sessions), method_name)(*args)
                except OSError:
                    pass

        asyncio.run_coroutine_threadsafe(run(), self._loop)

    def toggle_play(self):
        self._command("try_toggle_play_pause_async")

    def next_track(self):
        self._command("try_skip_next_async")

    def previous_track(self):
        self._command("try_skip_previous_async")

    def seek(self, seconds):
        self._command("try_change_playback_position_async", round(seconds * 10_000_000))

    def next_session(self, state):
        if state and len(state.sessions) > 1 and state.app_id in state.sessions:
            index = state.sessions.index(state.app_id)
            self._selected = state.sessions[(index + 1) % len(state.sessions)]


def cover_pixmap(data, side, radius):
    ratio = 2
    result = QPixmap(side * ratio, side * ratio)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(result.rect()), radius * ratio, radius * ratio)
    painter.setClipPath(path)
    source = QPixmap()
    if data and source.loadFromData(data):
        scaled = source.scaled(result.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        painter.drawPixmap((result.width() - scaled.width()) // 2, (result.height() - scaled.height()) // 2, scaled)
    else:
        painter.fillRect(result.rect(), QColor(50, 50, 50))
        painter.setPen(QColor(160, 160, 160))
        font = QFont("Segoe UI")
        font.setPixelSize(result.height() // 2)
        painter.setFont(font)
        painter.drawText(result.rect(), Qt.AlignCenter, "♪")
    painter.end()
    result.setDevicePixelRatio(ratio)
    return result


class Cover(QLabel):
    def __init__(self, side, radius):
        super().__init__()
        self.side, self.radius = side, radius
        self.setFixedSize(side, side)
        self._data = object()
        self.set_data(None)

    def set_data(self, data):
        if data is not self._data:
            self._data = data
            self.setPixmap(cover_pixmap(data, self.side, self.radius))


def icon_button(glyph, pixel_size, callback):
    button = QPushButton(glyph)
    font = QFont()
    font.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
    font.setPixelSize(pixel_size)
    button.setFont(font)
    button.setFocusPolicy(Qt.NoFocus)
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet(
        "QPushButton { color: white; background: transparent; border: none; padding: 4px; }"
        "QPushButton:hover { color: #bbbbbb; }"
    )
    button.clicked.connect(callback)
    return button


def accent_from_cover(data):
    image = QImage()
    if not data or not image.loadFromData(data):
        return QColor(DEFAULT_ACCENT)
    image = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    best, best_score = None, 0.0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            score = color.hsvSaturationF() * color.valueF()
            if color.valueF() > 0.3 and score > best_score:
                best, best_score = color, score
    if best is None or best_score < 0.2:
        return QColor(DEFAULT_ACCENT)
    # Brightened so the accent stays readable on the dark pill even for dark covers.
    return QColor.fromHsvF(max(best.hsvHueF(), 0.0), max(best.hsvSaturationF(), 0.55), max(best.valueF(), 0.9))


def play_button(pixel_size, side, callback):
    button = icon_button(ICON_PLAY, pixel_size, callback)
    button.setFixedSize(side, side)
    button.setStyleSheet(
        f"QPushButton {{ color: black; background: white; border: none; border-radius: {side // 2}px; }}"
        "QPushButton:hover { background: #dddddd; }"
    )
    return button


class ProgressBar(QWidget):
    seek_requested = Signal(float)

    def __init__(self, bar_height, hit_height, scale):
        super().__init__()
        self.bar_height = bar_height
        self.scale = scale
        self.setFixedHeight(hit_height)
        self.setCursor(Qt.PointingHandCursor)
        self.value = 0.0
        self.drag_value = None
        self.accent = QColor(DEFAULT_ACCENT)

    def set_value(self, value):
        self.value = min(max(value, 0.0), 1.0)

    def set_accent(self, color):
        self.accent = color

    def _fraction(self, event):
        return min(max(event.position().x() / max(self.width(), 1), 0.0), 1.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_value = self._fraction(event)
            self.update()

    def mouseMoveEvent(self, event):
        if self.drag_value is not None:
            self.drag_value = self._fraction(event)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_value is not None and event.button() == Qt.LeftButton:
            fraction, self.drag_value = self.drag_value, None
            self.value = fraction
            self.update()
            self.seek_requested.emit(fraction)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        s = self.scale
        mid = self.height() / 2
        value = self.drag_value if self.drag_value is not None else self.value
        head = self.width() * value
        painter.setPen(QPen(QColor(255, 255, 255, 60), self.bar_height, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(head, mid), QPointF(self.width(), mid))
        if head > 0:
            painter.setPen(QPen(self.accent, self.bar_height, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(0, mid), QPointF(head, mid))
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent)
        thumb_w, thumb_h = 4 * s, 12 * s
        painter.drawRoundedRect(QRectF(head - thumb_w / 2, mid - thumb_h / 2, thumb_w, thumb_h), thumb_w / 2, thumb_w / 2)


class Equalizer(QWidget):
    def __init__(self, scale):
        super().__init__()
        self.setFixedSize(round(16 * scale), round(14 * scale))
        self.accent = QColor(DEFAULT_ACCENT)
        self.playing = False
        self._levels = [0.25] * 4

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent)
        now = time.monotonic()
        bar = self.width() / 6.5
        for i in range(4):
            goal = 0.3 + 0.7 * abs(math.sin(now * (2.1 + i * 0.7) + i * 1.3)) if self.playing else 0.22
            self._levels[i] += (goal - self._levels[i]) * 0.25
            height = self.height() * self._levels[i]
            x = i * bar * 1.8
            painter.drawRoundedRect(QRectF(x, self.height() - height, bar, height), bar / 2, bar / 2)


def format_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


class MediaCompact(QWidget):
    def __init__(self, scale):
        super().__init__()
        self.cover = Cover(round(24 * scale), round(6 * scale))
        self.title = ElidedLabel(round(13 * scale), QFont.DemiBold)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(8 * scale))
        layout.addWidget(self.cover)
        layout.addWidget(self.title, 1)

    def set_state(self, state):
        if state:
            self.title.set_full_text(state.title or app_name(state.app_id))
            self.cover.set_data(state.thumbnail)


class MediaPanel(QWidget):
    lyrics_toggled = Signal(bool)
    accent_changed = Signal(object)

    def __init__(self, config, scale, controller, lyrics_provider):
        super().__init__()
        self.config = config
        self.controller = controller
        self.lyrics_provider = lyrics_provider
        self.state = None
        self._track = None
        self._lyrics_key = None
        self._thumbnail = object()

        self.cover = Cover(round(56 * scale), round(10 * scale))
        self.title = ElidedLabel(round(14 * scale), QFont.DemiBold)
        self.artist = ElidedLabel(round(12 * scale), color="#cccccc")
        self.album = ElidedLabel(round(11 * scale), color="#888888")
        info = QVBoxLayout()
        info.setSpacing(0)
        info.addStretch(1)
        info.addWidget(self.title)
        info.addWidget(self.artist)
        info.addWidget(self.album)
        info.addStretch(1)

        self.equalizer = Equalizer(scale)
        self.time = ElidedLabel(round(14 * scale), QFont.DemiBold, alignment=Qt.AlignRight | Qt.AlignVCenter)
        self.weather = ElidedLabel(round(12 * scale), alignment=Qt.AlignRight | Qt.AlignVCenter)
        self.weather.setTextFormat(Qt.PlainText)
        side = QVBoxLayout()
        side.setSpacing(0)
        side.addWidget(self.equalizer, 0, Qt.AlignRight)
        side.addWidget(self.time)
        side.addWidget(self.weather)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(round(52 * scale))
        side.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setSpacing(round(10 * scale))
        top.addWidget(self.cover)
        top.addLayout(info, 1)
        top.addWidget(side_widget)

        self.elapsed = ElidedLabel(round(10 * scale), color="#999999")
        self.total = ElidedLabel(round(10 * scale), color="#999999", alignment=Qt.AlignRight | Qt.AlignVCenter)
        for label in (self.elapsed, self.total):
            label.setFixedWidth(round(30 * scale))
            label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.progress = ProgressBar(max(2, round(3 * scale)), round(14 * scale), scale)
        self.progress.seek_requested.connect(self._seek)
        progress_row = QHBoxLayout()
        progress_row.setSpacing(round(6 * scale))
        progress_row.addWidget(self.elapsed)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.total)

        small = round(13 * scale)
        icon_size = round(16 * scale)
        self.lyrics_button = icon_button(ICON_LYRICS, small, self._toggle_lyrics)
        self.romaja_button = icon_button("가あ", small, self._toggle_romaja)
        self.romaja_button.setToolTip("Romaja / Romaji")
        self.switch = icon_button(ICON_SWITCH, small, lambda: controller.next_session(self.state))
        self.play = play_button(round(16 * scale), round(32 * scale), controller.toggle_play)
        controls = QHBoxLayout()
        controls.setSpacing(round(14 * scale))
        controls.addWidget(self.lyrics_button)
        controls.addWidget(self.romaja_button)
        controls.addStretch(1)
        controls.addWidget(icon_button(ICON_PREV, icon_size, controller.previous_track))
        controls.addWidget(self.play)
        controls.addWidget(icon_button(ICON_NEXT, icon_size, controller.next_track))
        controls.addStretch(1)
        controls.addWidget(self.switch)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(round(6 * scale))
        left.addLayout(top)
        left.addLayout(progress_row)
        left.addLayout(controls)
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(round(LEFT_COLUMN_WIDTH * scale))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(round(2 * scale), round(8 * scale), round(2 * scale), round(4 * scale))
        layout.setSpacing(round(18 * scale))
        layout.addWidget(left_widget)
        self.lyrics_view = None
        if lyrics_provider:
            self.lyrics_view = LyricsView(scale, config["lyrics"]["offset_ms"], centered=False)
            self.lyrics_view.setVisible(config["lyrics"]["visible"])
            self.lyrics_view.set_romaja(config["lyrics"]["romaja"])
            self._paint_romaja_button()
            layout.addWidget(self.lyrics_view, 1)
            lyrics_provider.loaded.connect(self._on_lyrics_loaded)
        else:
            self.lyrics_button.hide()
            self.romaja_button.hide()
            layout.addStretch(1)

        if config["weather"]["city"]:
            from modules.weather import WeatherProvider

            self.weather_provider = WeatherProvider(config["weather"]["city"], config["language"])
            self.weather_provider.changed.connect(lambda glyph, temp: self.weather.set_full_text(f"{glyph} {temp}"))

        self._seek_target = None
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        self.timer.start()

    @property
    def lyrics_visible(self):
        return self.lyrics_view is not None and self.config["lyrics"]["visible"]

    def _toggle_lyrics(self):
        visible = not self.config["lyrics"]["visible"]
        self.config["lyrics"]["visible"] = visible
        try:
            save_config(self.config)
        except OSError:
            pass
        self.lyrics_view.setVisible(visible)
        self.lyrics_toggled.emit(visible)

    def _toggle_romaja(self):
        enabled = not self.config["lyrics"]["romaja"]
        self.config["lyrics"]["romaja"] = enabled
        try:
            save_config(self.config)
        except OSError:
            pass
        self.lyrics_view.set_romaja(enabled)
        self._paint_romaja_button()

    def _paint_romaja_button(self):
        color = "white" if self.config["lyrics"]["romaja"] else "#666666"
        self.romaja_button.setStyleSheet(
            f"QPushButton {{ color: {color}; background: transparent; border: none; padding: 4px; }}"
            "QPushButton:hover { color: #bbbbbb; }"
        )

    def set_state(self, state):
        if state and self._seek_target and time.monotonic() - self._seek_target[1] < SEEK_HOLD_SECONDS:
            # Players report the new position with a delay; without this the bar jumps back for a moment.
            state = replace(state, position=self._seek_target[0], captured=self._seek_target[1])
        self.state = state
        if state is None:
            return
        self.progress.setEnabled(state.duration > 0)
        self.title.set_full_text(state.title or app_name(state.app_id))
        self.artist.set_full_text(state.artist)
        self.album.set_full_text(state.album)
        self.switch.setVisible(len(state.sessions) > 1)
        self.switch.setToolTip(app_name(state.app_id))
        self.play.setText(ICON_PAUSE if state.playing else ICON_PLAY)
        self.equalizer.playing = state.playing
        self.cover.set_data(state.thumbnail)
        if state.thumbnail is not self._thumbnail:
            self._thumbnail = state.thumbnail
            accent = accent_from_cover(state.thumbnail) if self.config["accent"] == "cover" else QColor(self.config["accent"])
            if not accent.isValid():
                accent = QColor(DEFAULT_ACCENT)
            self.progress.set_accent(accent)
            self.equalizer.accent = accent
            self.accent_changed.emit(accent)
        self.total.set_full_text(format_time(state.duration) if state.duration > 0 else "")

        track = (state.app_id, state.title, state.artist, state.album)
        if track != self._track:
            self._track = track
            if self.lyrics_view:
                self.lyrics_view.set_lines([], state.title)
                self._lyrics_key = None
                if state.title:
                    self._lyrics_key = self.lyrics_provider.request(
                        state.title, state.artist, state.album, state.duration
                    )
        self._tick()

    def _on_lyrics_loaded(self, key, lines):
        if key == self._lyrics_key and self.state:
            self.lyrics_view.set_lines(lines, self.state.title)
            self._tick()

    def _seek(self, fraction):
        if self.state is None or self.state.duration <= 0:
            return
        seconds = fraction * self.state.duration
        self._seek_target = (seconds, time.monotonic())
        self.state = replace(self.state, position=seconds, captured=self._seek_target[1])
        self.controller.seek(seconds)
        self._tick()

    def _tick(self):
        if self.state is None or not self.isVisible():
            return
        self.time.set_full_text(QTime.currentTime().toString(self.config["clock"]["time_format"]))
        self.equalizer.update()
        if self.progress.drag_value is not None:
            self.elapsed.set_full_text(format_time(self.progress.drag_value * self.state.duration))
            self.progress.update()
            return
        position = self.state.estimated_position()
        self.elapsed.set_full_text(format_time(position))
        self.progress.set_value(position / self.state.duration if self.state.duration > 0 else 0)
        self.progress.update()
        if self.lyrics_view:
            self.lyrics_view.update_position(position, self.state.playing)
