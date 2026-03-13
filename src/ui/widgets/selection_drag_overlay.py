"""Compact selection drag overlay: same features, clearer code.

Features preserved:
- cursor-following head
- tapered tail based on speed
- fade-in/out animation
- outlines and fills with theme's accent color
"""

from __future__ import annotations

from time import perf_counter
from typing import Deque, Tuple
from collections import deque
from math import hypot

from PySide6.QtCore import QPoint, QRect, Qt, Property, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget

# Tunables
MIN_TAIL = 0.0
MAX_TAIL = 45.0
BASE_TAIL = 25.0
SPEED_FACTOR = 0.1
BUBBLE_R = 8.0
OUTLINE_W = 2.0
TAIL_MIN_R = 4.0
TAIL_MAX_R = BUBBLE_R
MAX_STEP = 6.0
MAX_POINTS = 8
APPEAR_MS = 450
FADE_MS = 150

# When cursor is stationary for this many seconds, begin retracting the tail
STATIONARY_DELAY = 0.01  # seconds
# If cursor speed drops below this threshold (pixels/sec) we start retracting immediately
SPEED_THRESHOLD = 4.0  # pixels/sec
# Speed at which the target tail length retracts toward MIN_TAIL (pixels/sec)
TAIL_SHRINK_SPEED = 160.0
# Small epsilon to decide when to clear remaining points
SHRINK_EPS = 0.5


class SelectionDragOverlay(QWidget):
    """Lightweight overlay used by the game list for drag selection visuals."""

    def __init__(self, parent: QWidget, theme_manager=None):
        super().__init__(parent)
        self._theme = theme_manager
        self._viewport = QRect(0, 0, 0, 0)
        self._drag = False
        self._fading = False
        self._cursor_x = 0.0
        self._cursor_y = 0.0
        self._tail: Deque[Tuple[float, float]] = deque(maxlen=MAX_POINTS)
        self._last_t = perf_counter()
        self._target_len = MIN_TAIL
        self._fade = 1.0

        # Idle/shrink tracking
        self._last_move_time = self._last_t
        self._last_speed = 0.0
        self._idle_last = self._last_t
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(16)  # ~60Hz
        self._idle_timer.timeout.connect(self._on_idle_tick)


        self._anim = QPropertyAnimation(self, b"fadeAlpha")
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_fade_finished)

        # Make overlay transparent to events and painting
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

        if self._theme and hasattr(self._theme, "theme_changed"):
            try:
                self._theme.theme_changed.connect(self.update)
            except Exception:
                pass

    # --- alpha property used by QPropertyAnimation ---
    def _get_fade(self) -> float:
        return self._fade

    def _set_fade(self, v: float) -> None:
        v = max(0.0, min(1.0, v))
        if v != self._fade:
            self._fade = v
            self.update()

    fadeAlpha = Property(float, _get_fade, _set_fade)

    # --- Public API ---
    def start_drag(self, pos: QPoint) -> None:
        self._drag = True
        self._fading = False
        self._safe_stop_anim()

        self._fade = 0.0
        self._cursor_x, self._cursor_y = float(pos.x()), float(pos.y())
        self._tail.clear()
        self._last_t = perf_counter()
        self._target_len = MIN_TAIL

        geom = self._viewport if self._viewport.width() > 0 else self.parentWidget().rect()
        self.setGeometry(geom)
        self.show()

        # start idle timer to detect stationary cursor and retract tail
        self._last_move_time = perf_counter()
        self._idle_last = self._last_move_time
        try:
            self._idle_timer.start()
        except Exception:
            pass

        # Animate fade-in (fallback to immediate visible on failure)
        try:
            self._anim.setDuration(APPEAR_MS)
            self._anim.setStartValue(self._fade)
            self._anim.setEndValue(1.0)
            self._anim.start()
        except Exception:
            self._fade = 1.0

        self.update()

    def is_drag_active(self) -> bool:
        """Compatibility shim for original API."""
        return bool(self._drag)

    def stop_drag(self) -> None:
        self._drag = False
        self._fading = True
        self._safe_stop_anim()

        self._anim.setDuration(FADE_MS)
        self._anim.setStartValue(self._fade)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def reposition(self, rect: QRect) -> None:
        self._viewport = rect
        if self.isVisible():
            self.setGeometry(rect)
            self.update()

    # --- Internal helpers ---
    def _safe_stop_anim(self) -> None:
        try:
            self._anim.stop()
        except Exception:
            # defensively ignore animation stop failures on some platforms
            pass

    def _on_idle_tick(self) -> None:
        """Timer callback: shrink tail smoothly when cursor stops moving."""
        # Only do work while dragging or fading (we also want tail to retract during drag)
        if not (self._drag or self._fading):
            return
        now = perf_counter()
        dt = max(1e-4, now - self._idle_last)
        self._idle_last = now

        idle_time = now - getattr(self, "_last_move_time", 0.0)
        if idle_time < STATIONARY_DELAY and getattr(self, "_last_speed", 0.0) > SPEED_THRESHOLD:
            return

        # If already essentially retracted and no points, skip
        if self._target_len <= MIN_TAIL + SHRINK_EPS and not self._tail:
            return

        # Smoothly move target length toward MIN_TAIL
        new_len = max(MIN_TAIL, self._target_len - TAIL_SHRINK_SPEED * dt)
        if new_len != self._target_len:
            self._target_len = new_len
            self._trim_tail()
            # If effectively retracted, clear any leftover points so only the bubble remains
            if self._target_len <= MIN_TAIL + SHRINK_EPS:
                self._tail.clear()
            self.update()

    def _accent(self) -> QColor:
        try:
            if self._theme:
                pal = self._theme.get_palette()
                return QColor(pal.get("primary_color", "#5f92ff"))
        except Exception:
            pass
        return QColor("#5f92ff")

    def _on_fade_finished(self) -> None:
        if not self._fading:
            return
        # If invisible after fade, clear the tail and hide
        if self._fade <= 0.001 and not self._drag:
            self._tail.clear()
            try:
                self._idle_timer.stop()
            except Exception:
                pass
            self.hide()
        self._fading = False

    def step_drag(self, pos: QPoint) -> None:
        if not self._drag:
            return
        now = perf_counter()
        dt = max(1e-4, now - self._last_t)
        self._last_t = now

        cx, cy = float(pos.x()), float(pos.y())
        dx, dy = cx - self._cursor_x, cy - self._cursor_y
        dist = hypot(dx, dy)

        # Tail length adapts to cursor speed
        speed = dist / dt
        tgt = BASE_TAIL + speed * SPEED_FACTOR
        self._target_len = max(MIN_TAIL, min(MAX_TAIL, tgt))
        # update movement tracking so the idle timer can tell when cursor stops
        self._last_speed = speed
        self._last_move_time = now

        if not self._tail:
            self._tail.append((self._cursor_x, self._cursor_y))

        if dist > 0.5:
            steps = int(dist / MAX_STEP)
            if steps > 0:
                inv = 1.0 / (steps + 1)
                for i in range(1, steps + 1):
                    t = i * inv
                    self._tail.append((self._cursor_x + dx * t, self._cursor_y + dy * t))
            self._tail.append((cx, cy))

        self._cursor_x, self._cursor_y = cx, cy
        self._trim_tail()
        self.update()

    def _trim_tail(self) -> None:
        """Keep tail length (approx L1) under _target_len while preserving newer points."""
        if len(self._tail) < 2:
            return
        pts = list(self._tail)
        total = 0.0
        for i in range(len(pts) - 1, 0, -1):
            ax, ay = pts[i]
            bx, by = pts[i - 1]
            total += abs(ax - bx) + abs(ay - by)
            if total > self._target_len:
                # keep only the last segment that fits
                self._tail = deque(pts[i:], maxlen=MAX_POINTS)
                return

    # --- Painting ---
    def paintEvent(self, event) -> None:
        if not (self._drag or self._fading) or self._fade < 0.01:
            return

        accent = self._accent()
        fill = QColor(accent)
        fill.setAlpha(int(210 * self._fade))
        outline_col = QColor(accent)
        outline_col.setAlpha(int(255 * self._fade))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Build list of circle centers + radii (tail tapers, head uses BUBBLE_R)
        pts = list(self._tail)
        circles = []
        for i, (x, y) in enumerate(pts):
            t = (i + 1) / max(1, len(pts))
            r = TAIL_MIN_R + (TAIL_MAX_R - TAIL_MIN_R) * t
            circles.append((x, y, r))
        circles.append((self._cursor_x, self._cursor_y, BUBBLE_R))

        # Fast rendering: draw thick rounded lines between centers and overlay circles.
        # This avoids repeated path stroking/unions and costly simplification while
        # still producing a smooth tapered tail and rounded head.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Fill (thick lines + circles)
        if len(circles) == 1:
            x, y, r = circles[0]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill))
            painter.drawEllipse(x - r, y - r, r * 2.0, r * 2.0)
        else:
            # Draw filled segments as thick rounded lines
            fill_pen = QPen(fill)
            fill_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            fill_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            for (x0, y0, r0), (x1, y1, r1) in zip(circles, circles[1:]):
                w = max(2.0 * max(r0, r1), 1.0)
                fill_pen.setWidthF(w)
                painter.setPen(fill_pen)
                painter.drawLine(x0, y0, x1, y1)

            # Draw filled circles to keep smooth joints and head
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill))
            for x, y, r in circles:
                painter.drawEllipse(x - r, y - r, r * 2.0, r * 2.0)

        # Outline pass (thin rounded stroke)
        outline_pen = QPen(outline_col, OUTLINE_W)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(outline_pen)

        if len(circles) == 1:
            x, y, r = circles[0]
            painter.drawEllipse(x - r, y - r, r * 2.0, r * 2.0)
        else:
            for (x0, y0, _), (x1, y1, _) in zip(circles, circles[1:]):
                painter.drawLine(x0, y0, x1, y1)
            # outline head last to ensure crisp cap
            xh, yh, rh = circles[-1]
            painter.drawEllipse(xh - rh, yh - rh, rh * 2.0, rh * 2.0)

        painter.end()
