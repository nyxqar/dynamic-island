from PySide6.QtCore import QDateTime, QLocale, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.theme import base_font


def _label(pixel_size, weight):
    label = QLabel(alignment=Qt.AlignCenter)
    font = base_font()
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    label.setFont(font)
    label.setStyleSheet("color: white; background: transparent;")
    return label


class ClockWidget(QWidget):
    def __init__(self, config, scale, parent=None):
        super().__init__(parent)
        self.time_format = config["clock"]["time_format"]
        self.date_format = config["clock"]["date_format"]
        self.locale = QLocale(config["language"])

        self.time_label = _label(round(16 * scale), QFont.DemiBold)
        self.date_label = _label(round(12 * scale), QFont.Normal)
        self.date_label.setStyleSheet("color: #b0b0b0; background: transparent;")
        self.date_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(2 * scale))
        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)

        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self.timer.start()
        self._tick()

    def _tick(self):
        now = QDateTime.currentDateTime()
        self.time_label.setText(self.locale.toString(now.time(), self.time_format))
        self.date_label.setText(self.locale.toString(now.date(), self.date_format))

    def set_expanded(self, expanded):
        self.date_label.setVisible(expanded)
