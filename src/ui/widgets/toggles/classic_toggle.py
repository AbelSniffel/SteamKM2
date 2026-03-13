from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QBrush

from src.ui.config import TOGGLE_SWITCH_HEIGHT, TOGGLE_SWITCH_WIDTH
from .toggle_base import ToggleBase


class ClassicToggle(ToggleBase):
    """Classic rounded toggle switch with animated handle."""

    def __init__(
        self,
        parent=None,
        checked=False,
        animation_duration=120,
        theme_manager=None,
        bg_color_off=QColor("#cccccc"),
        bg_color_on=QColor("#4cd964"),
        handle_color_off=QColor("#ffffff"),
        handle_color_on=QColor("#ffffff"),
    ):
        super().__init__(parent, checked, animation_duration, theme_manager)
        self.setFixedSize(TOGGLE_SWITCH_WIDTH, TOGGLE_SWITCH_HEIGHT)

        self._bg_off = QColor(bg_color_off)
        self._bg_on = QColor(bg_color_on)
        self._handle_off = QColor(handle_color_off)
        self._handle_on = QColor(handle_color_on)
        self._slot_bg = QColor("#333333")

        if self.theme_manager:
            try:
                self._apply_theme()
            except Exception:
                pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()

        self._draw_toggle(painter, width, height)
        painter.end()

    def _draw_toggle(self, painter, width, height):
        bg_color = self.interpolate_color(self._bg_off, self._bg_on, self._handle_position)
        handle_color = self.interpolate_color(self._handle_off, self._handle_on, self._handle_position)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(0, 0, width, height, height / 2, height / 2)

        margin = 3
        handle_diameter = height - margin * 2
        x_offset = margin + self._handle_position * (width - margin * 2 - handle_diameter)

        shadow_color = QColor(0, 0, 0, 30)
        painter.setBrush(QBrush(shadow_color))
        painter.drawEllipse(int(x_offset + 1), margin + 1, int(handle_diameter), int(handle_diameter))

        painter.setBrush(QBrush(handle_color))
        painter.drawEllipse(int(x_offset), margin, int(handle_diameter), int(handle_diameter))

    def set_colors(self, bg_off, bg_on, handle_color_off, handle_color_on):
        self._bg_off = QColor(bg_off)
        self._bg_on = QColor(bg_on)
        self._handle_off = QColor(handle_color_off)
        self._handle_on = QColor(handle_color_on)
        self.update()

    def get_colors(self):
        return self._bg_off, self._bg_on, self._handle_off, self._handle_on

    def _apply_theme(self):
        if not self.theme_manager:
            return

        try:
            palette = self.theme_manager.get_palette()
            self._bg_off = QColor(palette["toggle_bg_off"])
            self._bg_on = QColor(palette["toggle_bg_on"])
            self._handle_off = QColor(palette["toggle_handle_off"])
            self._handle_on = QColor(palette["toggle_handle_on"])
            self._slot_bg = QColor(palette.get("toggle_slot_bg", "#333333"))
            self.update()
        except Exception:
            pass


