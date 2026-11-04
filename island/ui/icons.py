"""Fluent-style stroke icons drawn on a 24×24 grid."""

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath, QPen

STROKE = 1.6


@lru_cache(maxsize=None)
def _path(name):
    p = QPainterPath()
    if name == "plus":
        p.moveTo(12, 5.5)
        p.lineTo(12, 18.5)
        p.moveTo(5.5, 12)
        p.lineTo(18.5, 12)
    elif name == "close":
        p.moveTo(7, 7)
        p.lineTo(17, 17)
        p.moveTo(17, 7)
        p.lineTo(7, 17)
    elif name == "trash":
        p.moveTo(4.5, 6.5)
        p.lineTo(19.5, 6.5)
        p.moveTo(9.5, 6.5)
        p.lineTo(9.5, 4.5)
        p.lineTo(14.5, 4.5)
        p.lineTo(14.5, 6.5)
        p.moveTo(6.5, 6.5)
        p.lineTo(7.5, 19.5)
        p.lineTo(16.5, 19.5)
        p.lineTo(17.5, 6.5)
        p.moveTo(10.5, 10)
        p.lineTo(10.5, 16)
        p.moveTo(13.5, 10)
        p.lineTo(13.5, 16)
    return p


def draw(painter, name, centre, size, color, stroke=STROKE):
    painter.save()
    painter.translate(centre.x() - size / 2, centre.y() - size / 2)
    k = size / 24
    painter.scale(k, k)
    pen = QPen(color, stroke / k)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(_path(name))
    painter.restore()
