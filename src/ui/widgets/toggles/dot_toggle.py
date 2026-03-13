from PySide6.QtGui import QPainter, QBrush, QColor
from PySide6.QtCore import Qt, QRectF, Property, QPropertyAnimation, QEasingCurve

from src.ui.config import TOGGLE_SWITCH_HEIGHT
from .toggle_base import ToggleBase


class DotToggle(ToggleBase):
    """Circular toggle whose inner dot expands as it switches on."""

    def __init__(
        self,
        parent=None,
        checked=False,
        animation_duration=120,
        theme_manager=None,
        bg_color_off=QColor("#333333"),
        bg_color_on=QColor("#333333"),
        handle_color_off=QColor("#000000"),
        handle_color_on=QColor("#ffffff"),
    ):
        super().__init__(parent, checked, animation_duration, theme_manager)

        self.setMouseTracking(True)
        self.setFixedSize(TOGGLE_SWITCH_HEIGHT, TOGGLE_SWITCH_HEIGHT)

        self._bg_off = QColor(bg_color_off)
        self._bg_on = QColor(bg_color_on)
        self._handle_off = QColor(handle_color_off)
        self._handle_on = QColor(handle_color_on)

        self._hover_scale = 1.0
        self._hover_max_scale = 1.12
        self._hover_anim = QPropertyAnimation(self, b"hover_scale")
        self._hover_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._hover_anim.setDuration(160)

        if self.theme_manager:
            try:
                self._apply_theme()
            except Exception:
                pass

    def get_hover_scale(self) -> float:
        return self._hover_scale

    def set_hover_scale(self, value: float):
        self._hover_scale = value
        self.update()

    hover_scale = Property(float, get_hover_scale, set_hover_scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width, height = self.width(), self.height()
        self._draw_slot(painter, width, height)
        self._draw_dot_handle(painter, width, height)

        painter.end()

    def _draw_slot(self, painter, width, height):
        bg_color = self.interpolate_color(self._bg_off, self._bg_on, self._handle_position)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawEllipse(0, 0, width, height)

    def _draw_dot_handle(self, painter, width, height):
        margin = 3
        diameter = height - margin * 2
        radius = diameter / 2
        center_x = width / 2
        center_y = height / 2

        scale = max(0.0, float(self._hover_scale))
        shrink_factor = 0.3
        base_diameter = max(1.0, diameter * (1.0 - (shrink_factor * self._handle_position)) * scale)
        base_x = center_x - base_diameter / 2
        base_y = center_y - base_diameter / 2

        painter.setBrush(QBrush(self._handle_off))
        painter.drawEllipse(QRectF(base_x, base_y, base_diameter, base_diameter))

        expand_radius = radius * self._handle_position * scale
        if expand_radius <= 0:
            return

        painter.setBrush(QBrush(self._handle_on))
        painter.drawEllipse(
            QRectF(
                center_x - expand_radius,
                center_y - expand_radius,
                expand_radius * 2,
                expand_radius * 2,
            )
        )

    def enterEvent(self, event):
        try:
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_scale)
            self._hover_anim.setEndValue(self._hover_max_scale)
            self._hover_anim.start()
        except Exception:
            pass

        super().enterEvent(event)

    def leaveEvent(self, event):
        try:
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_scale)
            self._hover_anim.setEndValue(1.0)
            self._hover_anim.start()
        except Exception:
            pass

        super().leaveEvent(event)

    def _apply_theme(self):
        if not self.theme_manager:
            return

        try:
            palette = self.theme_manager.get_palette()
            self._handle_off = QColor("#000000")
            self._handle_on = QColor(palette.get("toggle_bg_on", "#4cd964"))
            self._bg_off = QColor(palette.get("toggle_bg_off", "#333333"))
            self._bg_on = QColor(palette.get("toggle_bg_off", "#333333"))
            self.update()
        except Exception:
            pass

