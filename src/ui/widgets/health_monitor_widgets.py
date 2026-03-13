"""Reusable health-monitor widgets in the main widgets package.

This file is the new location for `GraphWidget` and `MetricCard`. It keeps
APIs the same but moves the components into the top-level widgets package
so other modules can import them as `src.ui.widgets.health_monitor_widgets`.
"""

from typing import Optional
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QGridLayout,
    QScrollArea, QSizePolicy, QToolTip, QGroupBox
)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush

from src.ui.config import HEALTH_MONITOR_GRAPH_HEIGHT
from src.ui.widgets.main_widgets import create_push_button
from src.ui.widgets.tooltip import get_tooltip_manager


class GraphWidget(QWidget):
    """Widget for displaying time-series graph data"""

    def __init__(self, title: str, unit: str = "", color: str = "#5f92ff", parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.color = QColor(color)
        self.data_points = []
        self.max_points = 50
        self.auto_scale = True
        self._cached_range = (0.0, 100.0)
        self._graph_rect = QRect()
        self._hover_index: Optional[int] = None
        self._point_positions = []
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        
        # Custom tooltip manager
        self._custom_tooltip = None

        self.setFixedHeight(HEALTH_MONITOR_GRAPH_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.theme_manager = None
        self._bg_color = QColor(35, 35, 35, 180)
        self._setup_theme_manager(parent)

    def set_data(self, data):
        trimmed = list(data)[-self.max_points:]
        converted = []
        for item in trimmed:
            if hasattr(item, 'timestamp') and hasattr(item, 'value'):
                ts = float(item.timestamp) if item.timestamp is not None else None
                val = float(item.value)
            elif isinstance(item, dict) and 'timestamp' in item and 'value' in item:
                ts = float(item.get('timestamp')) if item.get('timestamp') is not None else None
                val = float(item.get('value'))
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                ts = float(item[0]) if item[0] is not None else None
                val = float(item[1])
            else:
                ts = None
                val = float(item)
            converted.append((ts, val))
        if converted == self.data_points:
            return
        self.data_points = converted
        if self.auto_scale and self.data_points:
            values = [p[1] for p in self.data_points]
            min_val = min(values)
            max_val = max(values)
            if max_val == min_val:
                if max_val == 0:
                    max_val = 1.0
                    min_val = 0.0
                else:
                    spread = abs(max_val) * 0.15
                    min_val = max(0.0, min_val - spread)
                    max_val = max_val + spread
            else:
                spread = (max_val - min_val) * 0.1
                min_val = max(0.0, min_val - spread)
                max_val = max_val + spread
            self._cached_range = (min_val, max_val)
        self.update()

    def set_range(self, min_val: float, max_val: float):
        self.auto_scale = False
        self._cached_range = (min_val, max_val)

    def _get_theme_manager_from_parent(self, parent):
        current = parent
        while current:
            if hasattr(current, 'theme_manager'):
                return current.theme_manager
            try:
                current = current.parent()
            except Exception:
                current = None
        return None

    def _setup_theme_manager(self, parent):
        tm = None
        try:
            tm = getattr(parent, 'theme_manager', None) if parent is not None else None
        except Exception:
            tm = None
        if tm is None:
            tm = self._get_theme_manager_from_parent(parent)
        self.theme_manager = tm

        if self.theme_manager and hasattr(self.theme_manager, 'theme_changed'):
            try:
                self.theme_manager.theme_changed.connect(self._apply_theme, Qt.ConnectionType.UniqueConnection)
            except Exception:
                pass

        self._apply_theme()

    def _is_inside_section_groupbox(self) -> bool:
        """Return True if this widget is inside a SectionGroupBox inner group.

        We look for an ancestor with objectName 'SectionGroupBox', which is
        how SectionGroupBox marks the inner card created in
        `SectionGroupBox._build_group_card`.
        """
        cur = self.parent()
        while cur is not None:
            try:
                if hasattr(cur, 'objectName') and cur.objectName() == 'SectionGroupBox':
                    return True
            except Exception:
                pass
            try:
                cur = cur.parent()
            except Exception:
                cur = None
        return False

    def _apply_theme(self):
        if not self.theme_manager:
            return
        try:
            palette = self.theme_manager.get_palette()
            bg_str = palette.get('inner_groupbox_background')
            if bg_str:
                self._bg_color = QColor(bg_str)
            else:
                self._bg_color = QColor(35, 35, 35, 180)
            self.update()
        except Exception:
            pass

    def showEvent(self, event):
        if not self.theme_manager:
            try:
                self._setup_theme_manager(self.parent())
            except Exception:
                pass
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        title_height = 24
        top_padding = 6
        # If we're inside a SectionGroupBox inner card, remove the default
        # graph padding so the plotted area "touches" the card edges.
        side_padding = 0 if self._is_inside_section_groupbox() else 12
        bottom_padding = 0 if self._is_inside_section_groupbox() else 12
        graph_width = max(10, width - 2 * side_padding)
        graph_top = title_height + top_padding
        graph_height = max(10, height - graph_top - bottom_padding)
        graph_rect = QRect(side_padding, graph_top, graph_width, graph_height)
        self._graph_rect = graph_rect

        painter.setPen(self.palette().text().color())
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        # Match title text width to the graph area so the right-aligned
        # value lines up with the graph's right edge (respect inner margins)
        title_rect = QRect(side_padding, 0, graph_width, title_height)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)

        if self.data_points:
            value_text = f"{self.data_points[-1][1]:.1f}{self.unit}"
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value_text)

        try:
            bg = self._bg_color
            if bg.alpha() >= 255:
                bg.setAlpha(180)
        except Exception:
            bg = QColor(35, 35, 35, 180)
        painter.fillRect(graph_rect, bg)

        if not self.data_points:
            return

        min_val, max_val = self._cached_range
        value_range = max(max_val - min_val, 1.0)
        count = len(self.data_points)
        denominator = max(1, count - 1)

        points = []
        for index, sample in enumerate(self.data_points):
            value = sample[1]
            x = graph_rect.left() + int(graph_rect.width() * index / denominator)
            normalized = max(0.0, min(1.0, (value - min_val) / value_range))
            y = graph_rect.top() + int(graph_rect.height() * (1 - normalized))
            points.append(QPoint(int(x), int(y)))

        if len(points) >= 2:
            from PySide6.QtGui import QPolygon
            # Extend polygon bottom by 1 pixel to ensure the fill reaches the
            # bottom edge — this prevents a 1px gap introduced by antialiasing
            # or inclusive coordinate rounding when using QRect.bottom().
            polygon = QPolygon(points + [
                QPoint(points[-1].x(), graph_rect.bottom() + 1),
                QPoint(points[0].x(), graph_rect.bottom() + 1)
            ])
            fill_brush = QBrush(QColor(self.color.red(), self.color.green(), self.color.blue(), 50))
            painter.setBrush(fill_brush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(polygon)
            line_pen = QPen(self.color, 2)
            painter.setPen(line_pen)
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])
        elif points:
            painter.setPen(QPen(self.color, 2))
            painter.drawPoint(points[0])

        painter.setBrush(self.color)
        point_pen = QPen(self.color, 2)
        painter.setPen(point_pen)
        for point in points:
            painter.drawEllipse(point, 3, 3)

        if self._hover_index is not None and 0 <= self._hover_index < len(points):
            hover_point = points[self._hover_index]
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(hover_point, 5, 5)

        self._point_positions = points

    def _get_custom_tooltip(self):
        """Get or create the custom tooltip manager."""
        if self._custom_tooltip is None:
            self._custom_tooltip = get_tooltip_manager(self.theme_manager)
        return self._custom_tooltip

    def mouseMoveEvent(self, event):
        if not self.data_points or self._graph_rect.isNull():
            return super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        if not self._graph_rect.contains(pos):
            if self._hover_index is not None:
                self._hover_index = None
                tooltip = self._get_custom_tooltip()
                if tooltip:
                    tooltip.hide_tooltip()
                self.update()
            return
        if len(self.data_points) == 1:
            index = 0
        else:
            ratio = (pos.x() - self._graph_rect.left()) / max(1, self._graph_rect.width())
            ratio = max(0.0, min(1.0, ratio))
            index = int(round(ratio * (len(self.data_points) - 1)))
        if index != self._hover_index:
            self._hover_index = index
            sample = self.data_points[index]
            tooltip_text = f"{sample[1]:.2f}{self.unit}" if self.unit else f"{sample[1]:.2f}"
            if sample[0] is not None:
                ts_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sample[0]))
                tooltip_text = f"{tooltip_text}\n{ts_text}"
            # Use custom tooltip with forced "below" direction for graph widgets
            tooltip = self._get_custom_tooltip()
            if tooltip:
                tooltip.show_tooltip(tooltip_text, self, delay=0, force_direction="below")
            self.update()

    def leaveEvent(self, event):
        if self._hover_index is not None:
            self._hover_index = None
            tooltip = self._get_custom_tooltip()
            if tooltip:
                tooltip.hide_tooltip()
            self.update()
        super().leaveEvent(event)


class MetricCard(QFrame):
    """Card widget for displaying a single metric"""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.label_widget)

        self.value_widget = QLabel("--")
        self.value_widget.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.value_widget)

        self.setFixedHeight(50)

    def set_value(self, value: str):
        if self.value_widget.text() != value:
            self.value_widget.setText(value)