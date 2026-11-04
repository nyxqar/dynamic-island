"""A floating dark card window in the island's style: soft shadow, hairline rim, fade-in, drag to move."""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ui import effects

SHOW_MS, HIDE_MS = 180, 120


class CardWindow(QWidget):
    def __init__(self, scale, width, height):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.scale = scale
        # The card sits inside a transparent margin that holds its shadow.
        self.margin = round(26 * scale)
        self.radius = 18 * scale
        self.resize(round(width * scale) + 2 * self.margin, round(height * scale) + 2 * self.margin)
        self._shadow = effects.shadow_tile(self.radius, 28 * scale, 0.5)
        self._drag_offset = None
        self._anchor_y = 0
        self._hiding = False
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._on_anim_finished)

    def card_rect(self):
        return QRectF(self.rect()).adjusted(self.margin, self.margin, -self.margin, -self.margin)

    def on_shown(self):
        """Called after the card has been shown (e.g. to focus a field)."""

    def show_near(self, anchor, screen):
        if not self.isVisible() or self._hiding:
            area = screen.availableGeometry()
            x = anchor.x() + (anchor.width() - self.width()) // 2
            # The card, not the shadow margin, goes right under the anchor.
            y = anchor.y() + anchor.height() + 6 - self.margin
            x = min(max(x, area.left() - self.margin), area.right() + self.margin - self.width())
            y = min(max(y, area.top() - self.margin), area.bottom() + self.margin - self.height())
            self._anchor_y = y
            self.move(x, y)
            self._hiding = False
            self._anim.stop()
            self._anim.setDuration(SHOW_MS)
            self._anim.setDirection(QVariantAnimation.Forward)
            self.setWindowOpacity(0.0)
            self.show()
            self._anim.start()
        self.raise_()
        self.activateWindow()
        self.on_shown()

    def animated_hide(self):
        if not self.isVisible() or self._hiding:
            return
        self._hiding = True
        self._anchor_y = self.y()
        self._anim.stop()
        self._anim.setDuration(HIDE_MS)
        self._anim.setDirection(QVariantAnimation.Backward)
        self._anim.start()

    def toggle_near(self, anchor, screen):
        if self.isVisible() and not self._hiding:
            self.animated_hide()
        else:
            self.show_near(anchor, screen)

    def _on_anim(self, value):
        self.setWindowOpacity(value)
        if self._hiding:
            self.move(self.x(), self._anchor_y + round(6 * self.scale * (1 - value)))
        else:
            self.move(self.x(), round(self._anchor_y - 8 * self.scale * (1 - value)))

    def _on_anim_finished(self):
        if self._hiding:
            self._hiding = False
            self.hide()
            self.move(self.x(), self._anchor_y)
            self.setWindowOpacity(1.0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.animated_hide()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def paint_card(self, p):
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        card = self.card_rect()
        effects.draw_nine_slice(p, card.translated(0, 6 * self.scale), *self._shadow)
        path = QPainterPath()
        path.addRoundedRect(card, self.radius, self.radius)
        fill = QLinearGradient(0, card.top(), 0, card.bottom())
        fill.setColorAt(0, QColor(14, 14, 16))
        fill.setColorAt(1, QColor(8, 8, 9))
        p.fillPath(path, fill)
        p.strokePath(path, QPen(QColor(255, 255, 255, 22), 1))

    def paintEvent(self, event):
        self.paint_card(QPainter(self))
