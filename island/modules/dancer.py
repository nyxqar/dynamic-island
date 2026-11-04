import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

BODY = QColor("#d97757")
EYES = QColor("#1a1a1a")
SHADOW = QColor(0, 0, 0, 110)
# Sprite grid: body 8x4 cells, arms stick out one cell on each side, legs hang below.
GRID_W, GRID_H = 14, 8
TEMPO = 2.2  # dance moves per second when no beat is detected
CELL = 2.5
# How quickly the dance speed follows a tempo change, and how hard each detected beat pulls the moves onto it.
TEMPO_FOLLOW = 3.0
BEAT_PULL = 0.5
# Extra height the media panel gets so the dancer can stand on top of the album art.
ROOM = 10


class Dancer(QWidget):
    def __init__(self, parent, side):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.cell = max(1.0, side / GRID_W)
        self.setFixedSize(round(self.cell * GRID_W), round(self.cell * GRID_H))
        self.playing = False
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        # One move per beat: the phase advances by π per beat, and a move happens whenever sin(phase) changes sign.
        self.tempo_source = None
        self.rate = TEMPO
        self.phase = 0.0
        self._last_tick = time.monotonic()
        self._last_beat = 0.0

    def set_tempo_source(self, source):
        """Anything with tempo() -> (bpm, last beat time) | None, e.g. AudioSpectrum."""
        self.tempo_source = source

    def _tick(self):
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.1)
        self._last_tick = now
        tempo = self.tempo_source.tempo() if self.tempo_source else None
        target = tempo[0] / 60 if tempo else TEMPO
        self.rate += (target - self.rate) * (1 - math.exp(-dt * TEMPO_FOLLOW))
        self.phase += math.pi * self.rate * dt
        if tempo and tempo[1] != self._last_beat:
            self._last_beat = tempo[1]
            # Nudge the nearest move boundary (a multiple of π) towards the moment the beat was heard.
            late = now - tempo[1]
            error = math.remainder(self.phase - math.pi * self.rate * late, math.pi)
            self.phase -= error * BEAT_PULL
        self.update()

    def set_playing(self, playing):
        if playing == self.playing:
            return
        self.playing = playing
        if playing:
            self._last_tick = time.monotonic()
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def hideEvent(self, event):
        self.timer.stop()

    def showEvent(self, event):
        if self.playing:
            self._last_tick = time.monotonic()
            self.timer.start()

    def _cells(self):
        """(x, y, color) of every filled cell for the current moment."""
        phase = self.phase if self.playing else 0.0
        step = math.sin(phase)
        sway = round(math.sin(phase / 2)) if self.playing else 0
        x0, y0 = 3 + sway, 2
        cells = []
        for dx in range(8):
            for dy in range(4):
                cells.append((x0 + dx, y0 + dy, BODY))
        eye_shift = 1 if self.playing and math.sin(phase / 2) > 0.3 else 0
        cells += [(x0 + 2 + eye_shift, y0 + 1, EYES), (x0 + 5 + eye_shift, y0 + 1, EYES)]
        # Arms: idle they hang at the sides, while dancing they go up and down in turn.
        left_up = self.playing and step > 0
        right_up = self.playing and step <= 0
        cells += [(x0 - 1, y0 + (0 if left_up else 2), BODY), (x0 - 2, y0 + (-1 if left_up else 2), BODY)]
        cells += [(x0 + 8, y0 + (0 if right_up else 2), BODY), (x0 + 9, y0 + (-1 if right_up else 2), BODY)]
        # Legs: two pairs, each pair lifts on its beat.
        for i, dx in enumerate((1, 3, 4, 6)):
            lifted = self.playing and ((i % 2 == 0) == (step > 0))
            cells.append((x0 + dx, y0 + 4, BODY))
            if not lifted:
                cells.append((x0 + dx, y0 + 5, BODY))
        return cells

    def paintEvent(self, event):
        painter = QPainter(self)
        c = self.cell
        cells = self._cells()
        for x, y, color in cells:
            painter.fillRect(QRectF((x + 0.5) * c, (y + 0.5) * c, c, c), SHADOW)
        for x, y, color in cells:
            painter.fillRect(QRectF(x * c, y * c, c + 0.5, c + 0.5), color)
