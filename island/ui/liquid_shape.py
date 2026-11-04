import math

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath

POINTS = 48
EDGE_STIFFNESS, EDGE_DAMPING = 180.0, 14.0
# Damping ratio ≈ 0.68: about 5 % overshoot, settles in ~350 ms.
SIZE_STIFFNESS, SIZE_DAMPING = 280.0, 23.0


class Spring:
    __slots__ = ("value", "velocity", "target", "stiffness", "damping")

    def __init__(self, value, stiffness=SIZE_STIFFNESS, damping=SIZE_DAMPING):
        self.value = self.target = float(value)
        self.velocity = 0.0
        self.stiffness, self.damping = stiffness, damping

    def step(self, dt):
        accel = self.stiffness * (self.target - self.value) - self.damping * self.velocity
        self.velocity += accel * dt
        self.value += self.velocity * dt

    def snap(self, value):
        self.value = self.target = float(value)
        self.velocity = 0.0

    def settled(self, eps=0.05):
        return abs(self.target - self.value) < eps and abs(self.velocity) < eps * 4


class LiquidShape:
    """Flat top glued to the screen edge; the sides and rounded bottom are POINTS spring-loaded points.

    Each point sits on the ideal contour for the current width/height springs and is pushed
    along its normal by its own offset spring. The caller sets `target` (offsets) every step.
    """

    def __init__(self, width, height, max_radius, cx=0.0):
        self.width = Spring(width)
        self.height = Spring(height)
        self.max_radius = max_radius
        self.cx = cx
        # y of the top edge inside the window.
        self.top = 0.0
        # 0 — glued to the screen edge (flat top), 1 — away from it, with the top corners rounded too.
        self.float_amount = 0.0
        self.offset = np.zeros(POINTS)
        self.velocity = np.zeros(POINTS)
        self.target = np.zeros(POINTS)
        self.wave_line = None
        self.update_base()

    def set_size(self, width, height):
        self.width.target, self.height.target = float(width), float(height)

    def update_base(self):
        w = max(self.width.value, 2.0)
        h = max(self.height.value, 2.0)
        r = max(0.5, min(h / 2, w / 2, self.max_radius))
        rt = min(max(self.float_amount, 0.0), 1.0) * r
        rt = max(min(rt, h - r), 1e-3)
        top = self.top
        x0, x1 = self.cx - w / 2, self.cx + w / 2
        side = max(h - r - rt, 0.0)
        arc = math.pi * r / 2
        arc_top = math.pi * rt / 2
        bottom = max(w - 2 * r, 0.0)
        bounds = np.cumsum([arc_top, side, arc, bottom, arc, side])
        b0, b1, b2, b3, b4, b5 = bounds
        s = np.linspace(0.0, b5 + arc_top, POINTS)
        seg = np.searchsorted(bounds, s, side="right")

        px = np.empty(POINTS)
        py = np.empty(POINTS)
        nx = np.zeros(POINTS)
        ny = np.zeros(POINTS)

        def arc_points(m, cx, cy, radius, start, offset):
            a = start + (s[m] - offset) / radius
            px[m], py[m] = cx + radius * np.cos(a), cy + radius * np.sin(a)
            nx[m], ny[m] = np.cos(a), np.sin(a)

        # Clockwise: top-right arc, right side, bottom-right arc, bottom, bottom-left arc, left side,
        # top-left arc. The top arcs shrink to nothing while the island is glued to the screen edge.
        arc_points(seg == 0, x1 - rt, top + rt, rt, -math.pi / 2, 0.0)
        m = seg == 1
        px[m], py[m], nx[m] = x1, top + rt + (s[m] - b0), 1.0
        arc_points(seg == 2, x1 - r, top + h - r, r, 0.0, b1)
        m = seg == 3
        px[m], py[m], ny[m] = x1 - r - (s[m] - b2), top + h, 1.0
        self.flat = m
        arc_points(seg == 4, x0 + r, top + h - r, r, math.pi / 2, b3)
        m = seg == 5
        px[m], py[m], nx[m] = x0, top + h - r - (s[m] - b4), -1.0
        arc_points(seg >= 6, x0 + rt, top + rt, rt, math.pi, b5)

        self.base = np.column_stack([px, py])
        self.normal = np.column_stack([nx, ny])
        # Points near the top stay pinned so the top corners never leave the screen edge.
        self.weight = np.clip((py - top) / h, 0.0, 1.0) ** 2
        self.x0, self.x1, self.w, self.h, self.r = x0, x1, w, h, r

    def step(self, dt):
        self.width.step(dt)
        self.height.step(dt)
        accel = EDGE_STIFFNESS * (self.target - self.offset) - EDGE_DAMPING * self.velocity
        self.velocity += accel * dt
        self.offset += self.velocity * dt
        self.update_base()

    def points(self):
        return self.base + self.normal * (self.offset * self.weight)[:, None]

    def path(self, wave=None):
        """The closed contour. `wave(xs)` (optional) adds vertical offsets to the flat bottom edge;
        the wavy part is also kept in `wave_line` for stroking."""
        pts = self.points()
        ext = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
        # Catmull-Rom through every point, as cubic Bézier segments.
        c1 = ext[1:-2] + (ext[2:-1] - ext[:-3]) / 6
        c2 = ext[2:-1] - (ext[3:] - ext[1:-2]) / 6
        segments = np.hstack([c1, c2, ext[2:-1]]).tolist()
        first = pts[0].tolist()
        top = self.top
        glued = self.float_amount * self.r < 0.5
        if glued:
            # The top edge sits one pixel past the window edge so antialiasing leaves no seam at the screen edge.
            path = QPainterPath(QPointF(self.x0, top - 1))
            path.lineTo(self.x1, top - 1)
            path.lineTo(first[0], first[1])
        else:
            path = QPainterPath(QPointF(first[0], first[1]))

        self.wave_line = None
        flat = np.flatnonzero(self.flat)
        start = end = -1
        if wave is not None and len(flat) >= 2:
            start, end = int(flat[0]), int(flat[-1])
        for i, (ax, ay, bx, by, x, y) in enumerate(segments):
            if start <= i < end:
                if i == start:
                    self._wave_edge(path, pts[start:end + 1], wave)
                continue
            path.cubicTo(ax, ay, bx, by, x, y)
        if glued:
            path.lineTo(self.x0, top - 1)
        path.closeSubpath()
        return path

    def _wave_edge(self, path, bottom, wave):
        right, left = bottom[0, 0], bottom[-1, 0]
        count = max(8, int((right - left) / 2.5))
        xs = np.linspace(right, left, count)
        base = np.interp(xs, bottom[::-1, 0], bottom[::-1, 1])
        # Fades out towards the corners so the wave meets the rounded ends smoothly.
        taper = np.sin(np.pi * np.clip((xs - left) / max(right - left, 1e-6), 0, 1)) ** 0.6
        ys = base + wave(xs) * taper
        line = QPainterPath(QPointF(xs[0], ys[0]))
        for x, y in zip(xs[1:].tolist(), ys[1:].tolist()):
            path.lineTo(x, y)
            line.lineTo(x, y)
        self.wave_line = line

    def settled(self):
        return (
            self.width.settled()
            and self.height.settled()
            and float(np.max(np.abs(self.target - self.offset))) < 0.02
            and float(np.max(np.abs(self.velocity))) < 0.08
        )
