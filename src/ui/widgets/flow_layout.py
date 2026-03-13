"""
FlowLayout class to layout child widgets in a wrapping flow, moving to next line when needed.
Also provides ScrollableFlowWidget for scrollable flow layouts, and SearchableTagFlowWidget
for searchable, toggleable tag displays.
"""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QLayout, QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, 
    QSizePolicy, QLineEdit, QPushButton
)
from src.ui.config import ELEMENT_HEIGHT, TAG_BUTTON_HEIGHT


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=5, spacing=5, min_height: int = ELEMENT_HEIGHT):
        """Flow layout with an optional minimum height.

        Args:
            parent: parent widget
            margin: contents margin to use on all sides
            spacing: spacing between items
            min_height: minimum height (in pixels) that the layout should report
        """
        super().__init__(parent)
        self.itemList = []
        # Always set contents margins so default margin applies even when no parent is provided
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        # Minimum height for the layout (pixels)
        self._min_height = int(min_height)

    def addItem(self, item):
        self.itemList.append(item)


    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):  # type: ignore[override]
        # Return and remove item at index, or None
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None  # type: ignore[return]

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        # Compute layout, ignoring deleted items inside _doLayout
        return self._doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        # Layout, ignoring deleted items inside _doLayout
        self._doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        # Build new list excluding deleted items
        valid_items = []
        for item in self.itemList:
            try:
                size = size.expandedTo(item.minimumSize())
                valid_items.append(item)
            except RuntimeError:
                # Skip items whose internal C++ object was deleted
                continue
        self.itemList = valid_items
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        # Enforce configured minimum height
        if size.height() < self._min_height:
            size.setHeight(self._min_height)
        return size

    def _doLayout(self, rect, testOnly):
        # apply layout margins
        left, top, right, bottom = self.getContentsMargins()
        effectiveRect = rect.adjusted(left, top, -right, -bottom)
        x = effectiveRect.x()
        y = effectiveRect.y()
        lineHeight = 0
        valid_items = []
        for item in self.itemList:
            try:
                size = item.sizeHint()
                spaceX = self.spacing()
                spaceY = self.spacing()
                # wrap to next line if needed
                if x + size.width() > effectiveRect.right() and lineHeight > 0:
                    x = effectiveRect.x()
                    y += lineHeight + spaceY
                    lineHeight = 0
                if not testOnly:
                    item.setGeometry(QRect(QPoint(x, y), size))
                x += size.width() + spaceX
                lineHeight = max(lineHeight, size.height())
                valid_items.append(item)
            except RuntimeError:
                # skip items whose C++ object was deleted
                continue
        self.itemList = valid_items
        # Calculate total height: from rect top to bottom of last item + bottom margin
        total_height = (y - rect.y()) + lineHeight + bottom
        # Respect minimum height when returning computed total
        if total_height < self._min_height:
            total_height = self._min_height
        return total_height


class ScrollableFlowWidget(QScrollArea):
    """A scrollable widget containing a FlowLayout.
    
    Use this when you need a flow layout that can scroll vertically
    when content exceeds the available height.
    
    Example:
        flow = ScrollableFlowWidget(parent, margin=5, spacing=5)
        flow.addWidget(button1)
        flow.addWidget(button2)
        flow.setMaximumHeight(150)  # Optional height constraint
    """
    
    def __init__(self, parent=None, margin=5, spacing=5, min_height: int = ELEMENT_HEIGHT, object_name: str = None):
        """Create a scrollable flow widget.
        
        Args:
            parent: Parent widget
            margin: Contents margin for the flow layout
            spacing: Spacing between items
            min_height: Minimum height for the flow layout
            object_name: Optional object name for styling (applied to scroll area)
        """
        super().__init__(parent)
        
        # Apply object name to the scroll area itself for CSS styling
        if object_name:
            self.setObjectName(object_name)
        
        # Configure scroll area
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # Create inner container widget
        self._container = QWidget()
        self._container.setObjectName("ScrollableFlowContainer")
        self._container.setContentsMargins(0, 0, 0, 0)
        self._container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Create flow layout on container
        self._flow_layout = FlowLayout(self._container, margin=margin, spacing=spacing, min_height=min_height)
        
        # Set the container as the scroll area's widget
        self.setWidget(self._container)
    
    @property
    def flow_layout(self) -> FlowLayout:
        """Access the underlying FlowLayout."""
        return self._flow_layout
    
    @property
    def container(self) -> QWidget:
        """Access the container widget (for styling)."""
        return self._container
    
    def addWidget(self, widget: QWidget):
        """Add a widget to the flow layout."""
        self._flow_layout.addWidget(widget)
    
    def clear(self):
        """Remove all widgets from the flow layout."""
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
    
    def count(self) -> int:
        """Return the number of items in the flow layout."""
        return self._flow_layout.count()
    
    def setContainerObjectName(self, name: str):
        """Set object name on the container for CSS styling."""
        self._container.setObjectName(name)
    
    def resizeEvent(self, event):
        """Handle resize to update flow layout width."""
        super().resizeEvent(event)
        # Update container width to match scroll area (minus scrollbar if visible)
        scrollbar_width = self.verticalScrollBar().width() if self.verticalScrollBar().isVisible() else 0
        new_width = self.viewport().width()
        self._container.setFixedWidth(new_width)


class SearchableTagFlowWidget(QWidget):
    """A complete tag management widget with search, scrollable flow layout, and clear button.
    
    This widget bundles:
    - A search bar to filter visible tags (with clear button next to it)
    - A scrollable flow layout displaying tag buttons
    - A "Clear All Selected Tags" button to deselect all tags
    
    Features:
    - Tags can be toggled on/off (checkable buttons)
    - Search filters which tags are visible (case-insensitive)
    - Hidden tags don't take up space in the flow layout
    - Emits signals when tags are toggled or cleared
    - Tracks active (checked) tags internally
    
    Example:
        tag_widget = SearchableTagFlowWidget(parent)
        tag_widget.set_tags(["Action", "Adventure", "RPG", "Simulation"])
        tag_widget.tag_toggled.connect(lambda tag, checked: print(f"{tag}: {checked}"))
        tag_widget.tags_cleared.connect(lambda: print("All tags cleared"))
        
        # Get active tags
        active = tag_widget.get_active_tags()
        
        # Programmatically set active tags
        tag_widget.set_active_tags({"Action", "RPG"})
    """
    
    # Signals
    tag_toggled = Signal(str, bool)  # Emitted when a tag is toggled (tag_name, is_checked)
    tags_cleared = Signal()  # Emitted when all tags are cleared
    active_tags_changed = Signal(set)  # Emitted when active tags change (new active set)
    
    def __init__(
        self, 
        parent=None, 
        margin=0, 
        spacing=5, 
        max_height=92,
        search_placeholder="Search tags...",
        clear_button_text="Clear All Selected Tags",
        object_name=None
    ):
        """Create a searchable tag flow widget.
        
        Args:
            parent: Parent widget
            margin: Contents margin for the flow layout
            spacing: Spacing between items in the flow layout
            max_height: Maximum height for the scrollable tag area
            search_placeholder: Placeholder text for the search input
            clear_button_text: Text for the clear button
            object_name: Optional object name for the container widget
        """
        super().__init__(parent)
        
        if object_name:
            self.setObjectName(object_name)
        
        # Internal state
        self._all_tags: list[str] = []
        self._active_tags: set[str] = set()
        self._tag_buttons: dict[str, QPushButton] = {}
        self._current_filter: str = ""
        self._margin = margin
        self._spacing = spacing
        
        # Debounce timer for search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(50)  # 50ms debounce
        self._search_timer.timeout.connect(self._apply_search_filter)
        
        # Main layout (vertical)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)
        
        # Top row: search bar + clear button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(spacing)
        
        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(search_placeholder)
        self._search_input.setFixedHeight(ELEMENT_HEIGHT)
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_changed)
        top_row.addWidget(self._search_input, 1)
        
        # Clear All button (next to search)
        self._clear_button = QPushButton(clear_button_text)
        self._clear_button.setFixedHeight(ELEMENT_HEIGHT)
        self._clear_button.setToolTip("Deselect all active tags")
        self._clear_button.clicked.connect(self._on_clear_clicked)
        top_row.addWidget(self._clear_button)
        
        self._layout.addLayout(top_row)
        
        # Scrollable tags flow (below search bar)
        self._tags_flow_widget = ScrollableFlowWidget(
            margin=margin, 
            spacing=spacing,
            object_name="TagFlowScroll"  # Avoid TagBox styling (has margin-top for QGroupBox)
        )
        self._tags_flow_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._tags_flow_widget.setMaximumHeight(max_height)
        self._layout.addWidget(self._tags_flow_widget)
    
    @property
    def flow_layout(self) -> FlowLayout:
        """Access the underlying FlowLayout for compatibility."""
        return self._tags_flow_widget.flow_layout
    
    @property
    def search_input(self) -> QLineEdit:
        """Access the search input widget."""
        return self._search_input
    
    @property
    def clear_button(self) -> QPushButton:
        """Access the clear button widget."""
        return self._clear_button
    
    @property
    def tag_buttons(self) -> dict[str, QPushButton]:
        """Access the dictionary of tag buttons (tag_name -> button)."""
        return self._tag_buttons
    
    def set_tags(self, tags: list[str], preserve_active: bool = True):
        """Set the list of available tags and create buttons for them.
        
        Args:
            tags: List of tag names to display
            preserve_active: If True, keeps currently active tags checked (if they still exist)
        """
        # Store previous active tags if preserving
        previous_active = self._active_tags.copy() if preserve_active else set()
        
        # Clear existing buttons from flow (but don't delete yet)
        self._tags_flow_widget.clear()
        
        # Delete old buttons
        for btn in self._tag_buttons.values():
            btn.deleteLater()
        self._tag_buttons.clear()
        self._all_tags = list(tags)
        
        # Update active tags to only include tags that still exist
        if preserve_active:
            self._active_tags = previous_active & set(self._all_tags)
        else:
            self._active_tags.clear()
        
        # Create buttons (but don't add to flow yet - _rebuild_flow will do that)
        for tag in self._all_tags:
            btn = QPushButton(tag)
            btn.setObjectName("toggle_tag_button")
            btn.setFixedHeight(TAG_BUTTON_HEIGHT)
            btn.setCheckable(True)
            btn.setChecked(tag in self._active_tags)
            btn.toggled.connect(lambda checked, t=tag: self._on_tag_toggled(t, checked))
            self._tag_buttons[tag] = btn
        
        # Build the flow with current filter
        self._rebuild_flow()
    
    def get_tags(self) -> list[str]:
        """Get all available tags."""
        return self._all_tags.copy()
    
    def get_active_tags(self) -> set[str]:
        """Get the set of currently active (checked) tags."""
        return self._active_tags.copy()
    
    def set_active_tags(self, tags: set[str], emit_signal: bool = True):
        """Programmatically set which tags are active.
        
        Args:
            tags: Set of tag names to activate
            emit_signal: If True, emits active_tags_changed signal
        """
        # Block signals during bulk update
        for tag_name, btn in self._tag_buttons.items():
            btn.blockSignals(True)
            should_check = tag_name in tags
            btn.setChecked(should_check)
            btn.blockSignals(False)
        
        self._active_tags = tags & set(self._all_tags)
        
        if emit_signal:
            self.active_tags_changed.emit(self._active_tags.copy())
    
    def clear_active_tags(self):
        """Deselect all tags and emit signals."""
        self._on_clear_clicked()
    
    def add_tag(self, tag: str, checked: bool = False):
        """Add a single tag to the flow.
        
        Args:
            tag: Tag name to add
            checked: Initial checked state
        """
        if tag in self._tag_buttons:
            return  # Already exists
        
        self._all_tags.append(tag)
        
        btn = QPushButton(tag)
        btn.setObjectName("toggle_tag_button")
        btn.setFixedHeight(TAG_BUTTON_HEIGHT)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.toggled.connect(lambda c, t=tag: self._on_tag_toggled(t, c))
        self._tag_buttons[tag] = btn
        
        if checked:
            self._active_tags.add(tag)
        
        # Rebuild flow with new tag
        self._rebuild_flow()
    
    def remove_tag(self, tag: str):
        """Remove a tag from the flow.
        
        Args:
            tag: Tag name to remove
        """
        if tag not in self._tag_buttons:
            return
        
        btn = self._tag_buttons.pop(tag)
        btn.deleteLater()
        
        if tag in self._all_tags:
            self._all_tags.remove(tag)
        
        self._active_tags.discard(tag)
        
        # Rebuild flow without the removed tag
        self._rebuild_flow()
    
    def set_search_text(self, text: str):
        """Programmatically set the search text."""
        self._search_input.setText(text)
    
    def clear_search(self):
        """Clear the search input."""
        self._search_input.clear()
    
    def set_max_height(self, height: int):
        """Set the maximum height of the scrollable tag area."""
        self._tags_flow_widget.setMaximumHeight(height)
    
    def _on_search_changed(self, text: str):
        """Handle search input changes - debounce and filter visible tags."""
        # Use debounce timer to avoid rebuilding on every keystroke
        self._search_timer.start()
    
    def _apply_search_filter(self):
        """Rebuild the flow layout with only matching tags."""
        new_filter = self._search_input.text().lower().strip()
        
        # Skip if filter hasn't changed
        if new_filter == self._current_filter:
            return
        
        self._current_filter = new_filter
        self._rebuild_flow()
    
    def _rebuild_flow(self):
        """Rebuild the flow layout with only tags matching the current filter."""
        # Clear flow layout, deleting any placeholder widgets we previously added
        flow = self._tags_flow_widget.flow_layout
        # Remove items from layout. If the item is a placeholder (not one of our
        # tracked tag buttons), delete its widget so it doesn't remain parented
        # to the container and overlap later content.
        while flow.count():
            item = flow.takeAt(0)
            try:
                w = item.widget()
            except Exception:
                w = None
            if w is not None:
                # Our tag buttons are stored in self._tag_buttons values and have
                # objectName 'toggle_tag_button'. Placeholders use other objectNames
                # like 'none_placeholder' or 'fetching_placeholder' so delete them.
                objname = w.objectName() if hasattr(w, 'objectName') else None
                if objname not in ("toggle_tag_button",):
                    w.deleteLater()
        
        search_text = self._current_filter
        
        # Add only matching buttons back to the flow
        for tag in self._all_tags:
            btn = self._tag_buttons.get(tag)
            if btn is None:
                continue
            
            # Check if tag matches filter
            if not search_text or search_text in tag.lower():
                flow.addWidget(btn)
                btn.show()
            else:
                btn.hide()
        
        # Force layout update
        self._tags_flow_widget.container.updateGeometry()
        flow.update()
        # If nothing matched the filter (or there are no tags), show a disabled "None" placeholder
        try:
            if flow.count() == 0:
                from src.ui.widgets.main_widgets import create_no_tags_placeholder
                create_no_tags_placeholder(flow)
        except Exception:
            # Be permissive; don't crash UI if placeholder creation fails
            pass
    
    def _on_tag_toggled(self, tag: str, checked: bool):
        """Handle individual tag toggle."""
        if checked:
            self._active_tags.add(tag)
        else:
            self._active_tags.discard(tag)
        
        self.tag_toggled.emit(tag, checked)
        self.active_tags_changed.emit(self._active_tags.copy())
    
    def _on_clear_clicked(self):
        """Handle clear button click - deselect all tags."""
        # Block signals during bulk update
        for btn in self._tag_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        
        self._active_tags.clear()
        self.tags_cleared.emit()
        self.active_tags_changed.emit(self._active_tags.copy())
