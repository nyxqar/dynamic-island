import math

import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPixmap

# Per-frame (60 fps) smoothing of the wave levels: they jump up quickly and fall slowly.
ATTACK, RELEASE = 0.5, 0.12


def clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


# --- Shadow -----------------------------------------------------------------------------------------------------

def shadow_tile(radius, blur, alpha):
    """A blurred rounded square for 9-slice drawing. Returns (pixmap, margin, radius)."""
    sigma = blur / 2
    margin = math.ceil(3 * sigma)
    r = math.ceil(radius)
    size = 2 * margin + 2 * r + 2
    ys, xs = np.mgrid[0:size, 0:size] + 0.5
    centre, half = size / 2, r + 1
    qx = np.abs(xs - centre) - (half - r)
    qy = np.abs(ys - centre) - (half - r)
    distance = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    # A logistic curve is close enough to a Gaussian-blurred edge and needs no convolution.
    a = alpha / (1 + np.exp(1.7 * distance / sigma))
    pixels = np.zeros((size, size, 4), np.uint8)
    pixels[..., 3] = np.round(a * 255).astype(np.uint8)
    image = QImage(pixels.data, size, size, size * 4, QImage.Format_ARGB32_Premultiplied).copy()
    return QPixmap.fromImage(image), margin, r


def draw_nine_slice(painter, rect, tile, margin, radius):
    size = tile.width()
    a = margin + radius
    src = [0, a, a + 2, size]

    def cuts(start, end):
        inner = [start + radius, end - radius]
        if inner[1] < inner[0]:
            inner = [(start + end) / 2] * 2
        return [start - margin, inner[0], inner[1], end + margin]

    dx = cuts(rect.left(), rect.right())
    dy = cuts(rect.top(), rect.bottom())
    for i in range(3):
        for j in range(3):
            target = QRectF(dx[i], dy[j], dx[i + 1] - dx[i], dy[j + 1] - dy[j])
            if target.width() > 0 and target.height() > 0:
                painter.drawPixmap(target, tile, QRectF(src[i], src[j], src[i + 1] - src[i], src[j + 1] - src[j]))


# --- Wave levels ------------------------------------------------------------------------------------------------

class Equalizer:
    """Smoothed spectrum levels plus an overall amount that fades the wave in and out."""

    def __init__(self, bands):
        self.levels = np.zeros(bands)
        self.amount = 0.0
        self.target_amount = 0.0

    @property
    def visible(self):
        return self.amount > 0.0

    @property
    def busy(self):
        return self.target_amount > 0 or self.amount > 0

    def step(self, dt, spectrum):
        goal = spectrum if spectrum is not None else np.zeros_like(self.levels)
        rise = 1 - (1 - ATTACK) ** (dt * 60)
        fall = 1 - (1 - RELEASE) ** (dt * 60)
        self.levels += (goal - self.levels) * np.where(goal > self.levels, rise, fall)
        self.amount += (self.target_amount - self.amount) * (1 - math.exp(-dt * 9))
        if abs(self.amount - self.target_amount) < 0.002:
            self.amount = self.target_amount
