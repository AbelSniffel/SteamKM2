from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListView,
    QStyledItemDelegate,
    QStyle,
    QLabel,
    QScrollArea,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPainter, QColor, QPen, QPainterPath

from src.ui.widgets.main_widgets import create_line_edit, create_scroll_area
from src.ui.config import ELEMENT_HEIGHT


class SidebarItemDelegate(QStyledItemDelegate):
    """Custom delegate for sidebar items with smooth animations and modern styling."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_progress = {}
    
    def paint(self, painter, option, index):
        """Custom paint with chevron indicator on the right for selected items."""
        # Let the default drawing handle text and background first
        super().paint(painter, option, index)
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        is_selected = option.state & QStyle.StateFlag.State_Selected
        
        # Draw chevron arrow on the right side for selected items
        if is_selected:
            # Create chevron path (right-pointing arrow)
            chevron_size = 4
            chevron_x = rect.right() - 20  # Position from right edge
            # Use a fractional center (top + height*0.5) and a small 0.5 offset
            # to avoid integer rounding that can make the chevron appear slightly off-center.
            chevron_y = rect.top() + rect.height() * 0.5 + 0.5

            path = QPainterPath()
            # Right-pointing chevron (>) using float positions for better centering
            path.moveTo(chevron_x, chevron_y - chevron_size)
            path.lineTo(chevron_x + chevron_size, chevron_y)
            path.lineTo(chevron_x, chevron_y + chevron_size)
            
            # Draw the chevron
            pen = QPen(QColor("white"), 1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)
        
        painter.restore()


class Sidebar(QWidget):
    """Adaptive sidebar with header, navigation list, search and custom sections."""

    currentIndexChanged = Signal(int)
    searchTextChanged = Signal(str)

    def __init__(self, items: Sequence[Any] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.prefers_edge_to_edge = True  # Hint for BasePage margin handling
        self.supports_page_header = True  # Allows BasePage to move its title label inside

        self._header_label: QLabel | None = None
        self._sections_stretch_active = False
        self._nav_items: list[dict[str, Any]] = []
        self._search_visibility_override: bool | None = None

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(0)

        self._scroll_area = create_scroll_area(parent=self, widget_resizable=True, frame_shape=QFrame.NoFrame)
        self._outer_layout.addWidget(self._scroll_area)

        self._content = QWidget()
        self._content.setObjectName("sidebar_content")
        self._scroll_area.setWidget(self._content)

        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 11, 12, 12)
        self._content_layout.setSpacing(12)

        # Header area -----------------------------------------------------
        self._header_container = QWidget()
        self._header_container.setObjectName("sidebar_header")
        self._header_layout = QVBoxLayout(self._header_container)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(8)
        self._header_container.setVisible(False)
        self._content_layout.addWidget(self._header_container)

        # Search -----------------------------------------------------------
        self._search_container = QWidget()
        self._search_container.setObjectName("sidebar_search_container")
        search_layout = QVBoxLayout(self._search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)

        line_edit = create_line_edit(object_name="sidebar_search")
        if isinstance(line_edit, tuple):  # Defensive: create_line_edit can return a tuple when decorated
            raise TypeError("Expected QLineEdit from create_line_edit for sidebar search input")
        self.search_input = line_edit
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_input)
        self._content_layout.addWidget(self._search_container)

        # Navigation list -------------------------------------------------
        self._nav_container = QWidget()
        self._nav_container.setObjectName("sidebar_nav_container")
        # Prefer natural height for the nav container so it doesn't force extra vertical space
        self._nav_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        nav_layout = QVBoxLayout(self._nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        self.view = QListView()
        self.view.setObjectName("settings_sidebar")
        self.view.setUniformItemSizes(True)
        self.view.setSpacing(2)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        # Do not force the view to expand vertically; allow it to use its natural size
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.delegate = SidebarItemDelegate(self.view)
        self.view.setItemDelegate(self.delegate)

        self.model = QStandardItemModel(self.view)
        self.view.setModel(self.model)
        self.view.selectionModel().currentChanged.connect(self._on_current_changed)

        nav_layout.addWidget(self.view)
        self._content_layout.addWidget(self._nav_container, 1)

        # Custom sections -------------------------------------------------
        self._sections_container = QWidget()
        self._sections_container.setObjectName("sidebar_sections_container")
        # Allow the sections container to expand vertically so child sections can fill
        # the remaining sidebar height (so things like batch inputs can stretch).
        self._sections_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._sections_layout = QVBoxLayout(self._sections_container)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(16)
        self._sections_container.setVisible(False)
        # Add with stretch to let the sections container take available space in the sidebar
        self._content_layout.addWidget(self._sections_container, 1)

        self.set_navigation_items(items or [])

    # ------------------------------------------------------------------
    # Header helpers
    # ------------------------------------------------------------------
    def embed_page_header(self, label: QLabel | None, *, title: str | None = None) -> None:
        """Adopt the page title label or create one from text."""

        if label is not None:
            if self._header_label and self._header_label is not label:
                self._header_layout.removeWidget(self._header_label)
                self._header_label.setParent(None)
            self._header_label = label
            label.setParent(self._header_container)
            label.setVisible(True)
            if self._header_layout.indexOf(label) == -1:
                self._header_layout.insertWidget(0, label)
        elif title:
            if not self._header_label:
                self._header_label = QLabel(title, self._header_container)
                self._header_label.setObjectName("page_title")
                self._header_layout.insertWidget(0, self._header_label)
            else:
                self._header_label.setText(title)
                if self._header_layout.indexOf(self._header_label) == -1:
                    self._header_layout.insertWidget(0, self._header_label)
        else:
            if self._header_label:
                self._header_layout.removeWidget(self._header_label)
                self._header_label.setParent(None)
                self._header_label = None

        self._update_header_visibility()

    def add_header_widget(self, widget: QWidget) -> None:
        if widget is None:
            return
        widget.setParent(self._header_container)
        self._header_layout.addWidget(widget)
        self._update_header_visibility()

    def clear_header_widgets(self) -> None:
        for index in reversed(range(self._header_layout.count())):
            item = self._header_layout.itemAt(index)
            widget = item.widget()
            if widget is None:
                continue
            if widget is self._header_label:
                continue
            self._header_layout.takeAt(index)
            widget.setParent(None)
        self._update_header_visibility()

    def _update_header_visibility(self) -> None:
        has_label = self._header_label is not None
        other_widgets = self._header_layout.count() > (1 if has_label else 0)
        self._header_container.setVisible(has_label or other_widgets)

    # ------------------------------------------------------------------
    # Navigation + search helpers
    # ------------------------------------------------------------------
    def set_navigation_items(self, items: Sequence[Any]) -> None:
        self.model.clear()
        self._nav_items.clear()

        for raw in items:
            label, payload, tooltip = self._normalize_item(raw)
            item = QStandardItem(label)
            item.setEditable(False)
            item.setSizeHint(QSize(0, ELEMENT_HEIGHT + 4))
            if payload is not None:
                item.setData(payload, Qt.ItemDataRole.UserRole)
            if tooltip:
                item.setToolTip(tooltip)
            self.model.appendRow(item)
            self._nav_items.append({
                "label": label,
                "data": payload,
                "tooltip": tooltip,
            })

        has_items = self.model.rowCount() > 0
        self._nav_container.setVisible(has_items)
        self._update_search_visibility()

    def navigation_items(self) -> list[dict[str, Any]]:
        return list(self._nav_items)

    def item_payload(self, index: int) -> Any:
        if not (0 <= index < self.model.rowCount()):
            return None
        item = self.model.item(index)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _normalize_item(self, raw: Any) -> tuple[str, Any, str | None]:
        if isinstance(raw, dict):
            label = str(raw.get("label") or raw.get("text") or "")
            payload = raw.get("data", raw.get("payload"))
            tooltip = raw.get("tooltip")
        elif isinstance(raw, (tuple, list)):
            label = str(raw[0]) if raw else ""
            payload = raw[1] if len(raw) > 1 else None
            tooltip = raw[2] if len(raw) > 2 else None
        else:
            label = str(raw)
            payload = None
            tooltip = None
        return label, payload, tooltip

    def set_search_placeholder(self, text: str) -> None:
        self.search_input.setPlaceholderText(text or "")

    def set_search_text(self, text: str) -> None:
        target = text or ""
        if self.search_input.text() == target:
            return
        self.search_input.setText(target)

    def search_text(self) -> str:
        return self.search_input.text()

    def set_search_visible(self, visible: bool) -> None:
        self._search_visibility_override = bool(visible)
        self._update_search_visibility()

    def _update_search_visibility(self) -> None:
        if self._search_visibility_override is None:
            self._search_container.setVisible(self.model.rowCount() > 0)
        else:
            self._search_container.setVisible(self._search_visibility_override)

    def _on_search_text_changed(self, text: str) -> None:
        try:
            self.searchTextChanged.emit(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def add_section(self, widget: QWidget, *, stretch: bool = False) -> QWidget:
        if widget is None:
            return widget
        widget.setParent(self._sections_container)
        self._remove_sections_stretch()
        self._sections_layout.addWidget(widget, 1 if stretch else 0)
        self._sections_container.setVisible(True)
        self._ensure_sections_stretch()
        return widget

    def clear_sections(self) -> None:
        self._remove_sections_stretch()
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._sections_container.setVisible(False)
        self._sections_stretch_active = False

    def _remove_sections_stretch(self) -> None:
        if not self._sections_stretch_active:
            return
        last_index = self._sections_layout.count() - 1
        if last_index < 0:
            self._sections_stretch_active = False
            return
        item = self._sections_layout.itemAt(last_index)
        if item and item.spacerItem():
            self._sections_layout.takeAt(last_index)
        self._sections_stretch_active = False

    def _ensure_sections_stretch(self) -> None:
        if self._sections_layout.count() == 0:
            return
        last_index = self._sections_layout.count() - 1
        item = self._sections_layout.itemAt(last_index)
        if not item or not item.spacerItem():
            self._sections_layout.addStretch()
            self._sections_stretch_active = True

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------
    def _on_current_changed(self, current, previous) -> None:
        try:
            self.currentIndexChanged.emit(current.row())
        except Exception:
            pass

    def select_index(self, idx: int) -> None:
        if not (0 <= idx < self.model.rowCount()):
            return
        try:
            self.view.setCurrentIndex(self.model.index(idx, 0))
        except Exception:
            pass

    def current_index(self) -> int:
        try:
            return self.view.currentIndex().row()
        except Exception:
            return -1
