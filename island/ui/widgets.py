"""Controls in the island's style, painted by hand so they look the same everywhere."""

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ui import effects, icons
from ui.theme import font

DEFAULT_ACCENT = "#ff4d6d"

SCROLLBAR_STYLE = """
QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.18); border-radius: 2px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.32); }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { height: 0; background: none; }
"""

FIELD_STYLE = """
QLineEdit, QSpinBox, QComboBox {
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
    padding: 4px 10px; color: white; selection-background-color: %(accent)s;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid %(accent)s; }
QLineEdit:hover, QSpinBox:hover, QComboBox:hover { background: rgba(255,255,255,0.09); }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #141416; color: white; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
    selection-background-color: rgba(255,255,255,0.12); outline: none; padding: 4px;
}
QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,0.12); border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: white; }
QSlider::handle:horizontal:hover { background: #e8e8e8; }
"""


def accent_of(config):
    color = QColor(config["accent"] if config["accent"] != "cover" else DEFAULT_ACCENT)
    return color if color.isValid() else QColor(DEFAULT_ACCENT)


def _animation(owner, callback, duration=160):
    anim = QVariantAnimation(owner, duration=duration)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(callback)
    return anim


class IconButton(QAbstractButton):
    def __init__(self, icon, scale, tooltip, danger=False):
        super().__init__()
        self.icon_name = icon
        self.scale = scale
        self.danger = danger
        self.setFixedSize(round(30 * scale), round(30 * scale))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tooltip)

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hover = self.underMouse() and self.isEnabled()
        if hover or self.isDown():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 34 if self.isDown() else 20))
            p.drawEllipse(QRectF(self.rect()))
        color = QColor("#ff6b6b") if self.danger and hover else QColor(255, 255, 255, 220 if hover else 170)
        if not self.isEnabled():
            color = QColor(255, 255, 255, 60)
        icons.draw(p, self.icon_name, QPointF(self.width() / 2, self.height() / 2), 18 * self.scale, color,
                   1.6 * self.scale)


class Toggle(QAbstractButton):
    """iOS-style switch; the knob slides when toggled."""

    def __init__(self, scale, accent, checked=False):
        super().__init__()
        self.scale = scale
        self.accent = accent
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(round(40 * scale), round(24 * scale))
        self._pos = 1.0 if checked else 0.0
        self._anim = _animation(self, self._set_pos)
        self.toggled.connect(self._animate)

    def _set_pos(self, value):
        self._pos = value
        self.update()

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off = QColor(255, 255, 255, 40)
        on = QColor(self.accent)
        t = self._pos
        track = QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
            round(off.alpha() + (on.alpha() - off.alpha()) * t),
        )
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        knob = r.height() - 4 * self.scale
        x = r.left() + 2 * self.scale + (r.width() - knob - 4 * self.scale) * t
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(x, r.top() + 2 * self.scale, knob, knob))


class Segmented(QWidget):
    """A row of mutually exclusive options with a highlight that slides to the selected one."""

    changed = Signal(object)

    def __init__(self, scale, options, value):
        super().__init__()
        self.scale = scale
        self.options = options
        self.value = value
        self.setCursor(Qt.PointingHandCursor)
        self._font = font(12 * scale, 600)
        self.setFont(self._font)
        width = sum(self.fontMetrics().horizontalAdvance(label) for _, label in options)
        self.setFixedSize(round(width * 1.15 + len(options) * 28 * scale), round(30 * scale))
        self._index = self._find(value)
        self._pos = float(self._index)
        self._anim = _animation(self, self._set_pos, 200)

    def _find(self, value):
        for i, (option, _) in enumerate(self.options):
            if option == value:
                return i
        return 0

    def _set_pos(self, value):
        self._pos = value
        self.update()

    def set_value(self, value):
        index = self._find(value)
        if index == self._index:
            return
        self._index = index
        self.value = self.options[index][0]
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(index))
        self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = min(int(event.position().x() / (self.width() / len(self.options))), len(self.options) - 1)
            if index != self._index:
                self.set_value(self.options[index][0])
                self.changed.emit(self.value)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 16))
        p.drawRoundedRect(r, radius, radius)
        segment = r.width() / len(self.options)
        inset = 3 * self.scale
        highlight = QRectF(r.left() + segment * self._pos + inset, r.top() + inset, segment - 2 * inset,
                           r.height() - 2 * inset)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(highlight, highlight.height() / 2, highlight.height() / 2)
        p.setFont(self._font)
        for i, (_, label) in enumerate(self.options):
            selected = abs(self._pos - i) < 0.5
            p.setPen(QColor(255, 255, 255, 240 if selected else 140))
            p.drawText(QRectF(r.left() + segment * i, r.top(), segment, r.height()), Qt.AlignCenter, label)


class Swatch(QAbstractButton):
    """A colour circle; `color=None` stands for "take it from the album art"."""

    def __init__(self, scale, color, tooltip=""):
        super().__init__()
        self.scale = scale
        self.color = color
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tooltip)
        self.setFixedSize(round(28 * scale), round(28 * scale))

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.scale
        r = QRectF(self.rect())
        inner = r.adjusted(5 * s, 5 * s, -5 * s, -5 * s)
        if self.color is None:
            gradient = QConicalGradient(inner.center(), 90)
            for stop, hex_color in ((0, "#ff4d6d"), (0.25, "#ffd166"), (0.5, "#3ddc97"), (0.75, "#4cc9f0"),
                                    (1, "#ff4d6d")):
                gradient.setColorAt(stop, QColor(hex_color))
            p.setBrush(gradient)
        else:
            p.setBrush(QColor(self.color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(inner)
        if self.isChecked() or self.underMouse():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 235 if self.isChecked() else 90), 2 * s))
            p.drawEllipse(r.adjusted(1.5 * s, 1.5 * s, -1.5 * s, -1.5 * s))


class ColorButton(QAbstractButton):
    """Shows a colour; a click opens the colour picker."""

    changed = Signal(str)

    def __init__(self, scale, color, title):
        super().__init__()
        self.scale = scale
        self.color = QColor(color)
        self.title = title
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(QSize(round(46 * scale), round(28 * scale)))
        self.clicked.connect(self._pick)

    def set_color(self, color):
        self.color = QColor(color)
        self.update()

    def _pick(self):
        # Our own popup: the system colour dialog opens behind the always-on-top windows.
        self._before = self.color.name()
        popup = ColorPopup(self.scale, self.color, self)
        popup.preview.connect(self.set_color)
        popup.closed.connect(self._on_closed)
        popup.show_below(self)

    def _on_closed(self):
        if self.color.name() != self._before:
            self.changed.emit(self.color.name())

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 70 if self.underMouse() else 30), 1))
        p.setBrush(self.color if self.isEnabled() else QColor(60, 60, 60))
        p.drawRoundedRect(r, 8 * self.scale, 8 * self.scale)


def _handle(p, centre, radius, scale):
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 90), 3 * scale))
    p.drawEllipse(centre, radius, radius)
    p.setPen(QPen(QColor(255, 255, 255), 2 * scale))
    p.drawEllipse(centre, radius, radius)


class _SaturationValue(QWidget):
    """Saturation left to right, brightness top to bottom, for the current hue."""

    changed = Signal()

    def __init__(self, scale, popup):
        super().__init__()
        self.scale = scale
        self.popup = popup
        self.setFixedSize(round(220 * scale), round(150 * scale))
        self.setCursor(Qt.CrossCursor)

    def _pick(self, pos):
        self.popup.s = min(max(pos.x() / self.width(), 0.0), 1.0)
        self.popup.v = 1 - min(max(pos.y() / self.height(), 0.0), 1.0)
        self.changed.emit()

    def mousePressEvent(self, event):
        self._pick(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._pick(event.position())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = 10 * self.scale
        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)
        p.fillRect(r, QColor.fromHsvF(self.popup.h, 1, 1))
        white = QLinearGradient(r.topLeft(), r.topRight())
        white.setColorAt(0, QColor(255, 255, 255))
        white.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, white)
        black = QLinearGradient(r.topLeft(), r.bottomLeft())
        black.setColorAt(0, QColor(0, 0, 0, 0))
        black.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(r, black)
        p.setClipping(False)
        _handle(p, QPointF(self.popup.s * r.width(), (1 - self.popup.v) * r.height()), 6 * self.scale, self.scale)


class _HueBar(QWidget):
    changed = Signal()

    def __init__(self, scale, popup):
        super().__init__()
        self.scale = scale
        self.popup = popup
        self.setFixedSize(round(220 * scale), round(16 * scale))
        self.setCursor(Qt.PointingHandCursor)

    def _pick(self, pos):
        self.popup.h = min(max(pos.x() / self.width(), 0.0), 0.999)
        self.changed.emit()

    def mousePressEvent(self, event):
        self._pick(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._pick(event.position())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 3 * self.scale, 0, -3 * self.scale)
        gradient = QLinearGradient(r.topLeft(), r.topRight())
        for i in range(7):
            gradient.setColorAt(i / 6, QColor.fromHsvF(min(i / 6, 0.999), 1, 1))
        p.setPen(Qt.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        _handle(p, QPointF(self.popup.h * self.width(), self.height() / 2), 6 * self.scale, self.scale)


class ColorPopup(QWidget):
    """A colour picker in the island's style that closes when you click elsewhere."""

    preview = Signal(QColor)
    closed = Signal()

    def __init__(self, scale, color, parent):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.scale = scale
        color = QColor(color)
        self.h = max(color.hsvHueF(), 0.0)
        self.s, self.v = color.hsvSaturationF(), color.valueF()
        self.margin = round(18 * scale)
        self._shadow = effects.shadow_tile(14 * scale, 20 * scale, 0.5)
        self.setStyleSheet("QWidget { color: white; background: transparent; }"
                           + FIELD_STYLE % {"accent": "rgba(255,255,255,0.4)"})

        self.area = _SaturationValue(scale, self)
        self.hue = _HueBar(scale, self)
        self.swatch = QWidget()
        self.swatch.setFixedSize(round(28 * scale), round(28 * scale))
        self.hex = QLineEdit()
        self.hex.setFont(font(13 * scale, 500, True))
        self.hex.setMaxLength(7)
        self.hex.editingFinished.connect(self._from_hex)
        row = QHBoxLayout()
        row.setSpacing(round(10 * scale))
        row.addWidget(self.swatch)
        row.addWidget(self.hex, 1)

        layout = QVBoxLayout(self)
        inner = round(12 * scale)
        layout.setContentsMargins(self.margin + inner, self.margin + inner, self.margin + inner, self.margin + inner)
        layout.setSpacing(round(10 * scale))
        layout.addWidget(self.area)
        layout.addWidget(self.hue)
        layout.addLayout(row)
        self.area.changed.connect(self._changed)
        self.hue.changed.connect(self._changed)
        self._changed(update_hex=True)

    def color(self):
        return QColor.fromHsvF(self.h, self.s, self.v)

    def _changed(self, update_hex=True):
        color = self.color()
        self.swatch.setStyleSheet(f"background: {color.name()}; border-radius: {round(8 * self.scale)}px;")
        if update_hex:
            self.hex.setText(color.name())
        self.area.update()
        self.hue.update()
        self.preview.emit(color)

    def _from_hex(self):
        color = QColor(self.hex.text().strip())
        if color.isValid():
            self.h = max(color.hsvHueF(), 0.0)
            self.s, self.v = color.hsvSaturationF(), color.valueF()
            self._changed()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._from_hex()
            self.close()
        else:
            super().keyPressEvent(event)

    def show_below(self, anchor):
        self.adjustSize()
        below = anchor.mapToGlobal(QPoint(anchor.width() // 2, anchor.height()))
        area = anchor.screen().availableGeometry()
        x = min(max(below.x() - self.width() // 2, area.left()), area.right() - self.width())
        y = below.y() - self.margin + round(6 * self.scale)
        if y + self.height() > area.bottom():
            y = anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() + self.margin - round(6 * self.scale)
        self.move(x, y)
        self.show()

    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(self.rect()).adjusted(self.margin, self.margin, -self.margin, -self.margin)
        effects.draw_nine_slice(p, card.translated(0, 4 * self.scale), *self._shadow)
        path = QPainterPath()
        path.addRoundedRect(card, 14 * self.scale, 14 * self.scale)
        p.fillPath(path, QColor(18, 18, 20))
        p.strokePath(path, QPen(QColor(255, 255, 255, 26), 1))
