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
TEMPO = 2.2  # dance moves per second
CELL = 2.5
# Extra height the media panel gets so the dancer can stand on top of the album art.
ROOM = 10


class Dancer(QWidget):
    def __init__(self, parent, side):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.cell = max(1.0, side / GRID_W)
        self.setFixedSize(round(self.cell * GRID_W), round(self.cell * GRID_H))
        self.playing = False
        self.timer = QTimer(self, interval=33, timeout=self.update)

    def set_playing(self, playing):
        if playing == self.playing:
            return
        self.playing = playing
        if playing:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def hideEvent(self, event):
        self.timer.stop()

    def showEvent(self, event):
        if self.playing:
            self.timer.start()

    def _cells(self):
        """(x, y, color) of every filled cell for the current moment."""
        phase = time.monotonic() * TEMPO * math.pi if self.playing else 0.0
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
