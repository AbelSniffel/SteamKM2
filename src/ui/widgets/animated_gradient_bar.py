import math
import time
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPointF
import math
import time
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QGradient, QPainterPath
from src.ui.config import CORNER_RADIUS_MULTIPLIER


class _EffectBase:
    def __init__(self, widget):
        self.w = widget

    def advance(self, dt=0.0):
        pass

    def get_gradient(self, rect, orientation):
        return None


class ScrollEffect(_EffectBase):
    def __init__(self, widget):
        super().__init__(widget)
        self.pos = 0.0
        self.speed = 0.4

    def advance(self, dt):
        if dt > 0:
            self.pos = (self.pos + self.speed * dt) % 1.0

    def get_gradient(self, rect, orientation):
        length = rect.height() if orientation == Qt.Orientation.Vertical else rect.width()
        off = int(self.pos * length)
        if orientation == Qt.Orientation.Vertical:
            start, end = QPointF(0, -length + off), QPointF(0, off)
        else:
            start, end = QPointF(-length + off, 0), QPointF(off, 0)
        c0, c1 = self.w.colors[0], self.w.colors[1]
        return start, end, [(0.0, c0), (0.5, c1), (1.0, c0)], QGradient.Spread.RepeatSpread


class PulseEffect(_EffectBase):
    def __init__(self, widget):
        super().__init__(widget)
        self.phase = 0.0
        self.phase_speed = 2.4

    def advance(self, dt):
        if dt > 0:
            self.phase += self.phase_speed * dt
    def get_gradient(self, rect, orientation):
        length = rect.height() if orientation == Qt.Orientation.Vertical else rect.width()
        start = QPointF(0, -length) if orientation == Qt.Orientation.Vertical else QPointF(-length, 0)
        end = QPointF(0, 0)
        phase = (1.0 + math.sin(self.phase)) / 2.0
        a = int(150 + phase * 105)
        c0 = QColor(self.w.colors[1]); c0.setAlpha(a)
        c1 = QColor(self.w.colors[0]); c1.setAlpha(a)
        return start, end, [(0.0, c0), (0.5, c1), (1.0, c0)], QGradient.Spread.ReflectSpread


class ScannerEffect(_EffectBase):
    def __init__(self, widget):
        super().__init__(widget)
        self.pos = 0.0
        self.dir = 1.0
        self.speed = 0.6
        self.width = 0.12

    def advance(self, dt):
        if dt <= 0:
            return
        self.pos += self.dir * self.speed * dt
        if self.pos <= 0.0:
            self.pos, self.dir = 0.0, 1.0
        elif self.pos >= 1.0:
            self.pos, self.dir = 1.0, -1.0

    def get_gradient(self, rect, orientation):
        length = rect.height() if orientation == Qt.Orientation.Vertical else rect.width()
        if length <= 0:
            return None
        base0, base1 = self.w.colors[1], self.w.colors[0]
        highlight = self.w._mix_colors(base0, base1, 0.5)
        center = self.pos * length
        stops = []
        samples = 8
        for i in range(samples + 1):
            t = i / samples
            px = t * length
            d = abs(px - center) / max(1.0, self.width * length)
            intensity = max(0.0, 1.0 - d)
            col = self.w._mix_colors(base0, highlight, intensity)
            stops.append((t, col))
        if orientation == Qt.Orientation.Vertical:
            start, end = QPointF(0, 0), QPointF(0, length)
        else:
            start, end = QPointF(0, 0), QPointF(length, 0)
        return start, end, stops, QGradient.Spread.PadSpread


class HeartEffect(_EffectBase):
    def __init__(self, widget):
        super().__init__(widget)
        self.phase = 0.0

    def advance(self, dt):
        if dt <= 0:
            return
        # Animation speed, higher is faster
        base_delta = 2.5

        # linger near trough to keep the bar dim longer
        cur_val = (math.sin(self.phase) + 1.0) / 2.0
        if cur_val < 0.18:
            self.phase += base_delta * 0.25 * dt
        else:
            self.phase += base_delta * dt

    def get_gradient(self, rect, orientation):
        length = rect.height() if orientation == Qt.Orientation.Vertical else rect.width()
        if orientation == Qt.Orientation.Vertical:
            start = QPointF(0, -length)
            end = QPointF(0, 0)
        else:
            start = QPointF(-length, 0)
            end = QPointF(0, 0)

        # phase 0..1 where 0 is trough (dim) and 1 is peak (bright)
        p = (math.sin(self.phase) + 1.0) / 2.0

        # Use the "other" theme color as the uniform background/ends color
        base_end = QColor(self.w.colors[1])

        # compute solid blend factor for smooth fade to solid in trough
        solid_thresh = 0.08
        if p < solid_thresh:
            solid_blend = max(0.0, min(1.0, (solid_thresh - p) / solid_thresh))
        else:
            solid_blend = 0.0

        # Middle color should remain the theme's first color (no brightening)
        mid = QColor(self.w.colors[0])

        # Dim the side color gradually during the beat so the middle appears to pop
        # reduced multiplier for a gentler dimming at peak
        side_factor = 1.0 - 0.55 * p  # at peak make it 55% transparent

        def scale_color(c: QColor, f: float) -> QColor:
            # Scale the alpha to make the color more transparent
            a = max(0, min(255, int(c.alpha() * f)))
            return QColor(c.red(), c.green(), c.blue(), a)

        base_end_dim = scale_color(base_end, side_factor)

        # radius grows with phase: slightly larger expansion at peak
        radius = max(0.01, min(1.5, 0.02 + p * 1.35))
        center = 0.5
        stops = []
        samples = 32
        for i in range(samples + 1):
            t = i / float(samples)
            # uniform background (the dimmed ends color)
            bg = base_end_dim
            # normalized distance from center (0..1)
            dist = abs(t - center) / 0.5
            if radius <= 0:
                intensity = 0.0
            else:
                raw = 1.0 - (dist / radius)
                intensity = max(0.0, min(1.0, raw))
                # smoothstep for softer falloff
                intensity = intensity * intensity * (3 - 2 * intensity)
                # scale by phase so highlight only appears near peak
                intensity *= p
            # mix background toward the mid color by intensity
            col = self.w._mix_colors(bg, mid, intensity)
            # if near trough, blend the stop toward the uniform end color for a smooth fade
            if solid_blend > 0.0:
                col = self.w._mix_colors(col, base_end, solid_blend)
            stops.append((t, col))

        return start, end, stops, QGradient.Spread.ReflectSpread


class AnimatedGradientBar(QWidget):
    def __init__(self, theme_manager, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.orientation = orientation
        self.corner_radius = 4
        self.refresh_colors()
        self.effect_impl = ScrollEffect(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(25)
        self._last_time = time.monotonic()
        if orientation == Qt.Orientation.Vertical:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def refresh_colors(self):
        theme = self.theme_manager.current_theme
        # Default gradient colors to primary/accent if overrides absent
        c1 = theme.get('gradient_color1', theme.get('base_primary', '#ff00ff'))
        c2 = theme.get('gradient_color2', theme.get('base_accent', '#00ffff'))
        self.colors = [QColor(c1), QColor(c2)]
        self.corner_radius = theme.get('corner_radius', 4)
        self.update()

    def set_radius(self, radius):
        self.corner_radius = radius
        self.update()

    def set_effect(self, effect_name):
        mapping = {'scroll': ScrollEffect, 'pulse': PulseEffect, 'scanner': ScannerEffect, 'heart': HeartEffect}
        cls = mapping.get(effect_name, ScrollEffect)
        self.effect_impl = cls(self)
        self.update()

    def _mix_colors(self, c1: QColor, c2: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(int(c1.red() + (c2.red() - c1.red()) * t),
                      int(c1.green() + (c2.green() - c1.green()) * t),
                      int(c1.blue() + (c2.blue() - c1.blue()) * t),
                      int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))

    def advance(self):
        now = time.monotonic()
        dt = max(0.0, now - getattr(self, '_last_time', now))
        self._last_time = now
        try:
            self.effect_impl.advance(dt)
        except TypeError:
            try:
                self.effect_impl.advance()
            except Exception:
                pass
        except Exception:
            pass
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        radius = self.corner_radius * CORNER_RADIUS_MULTIPLIER
        path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
        res = None
        try:
            res = self.effect_impl.get_gradient(rect, self.orientation)
        except Exception:
            return
        if not res:
            return
        start, end, stops, spread = res
        gradient = QLinearGradient(start, end)
        if spread is not None:
            gradient.setSpread(spread)
        for pos, col in stops:
            gradient.setColorAt(pos, col)
        painter.setClipPath(path)
        painter.fillRect(rect, gradient)
