"""
Create UI elements with consistent styles and fixed sizes.

OPTIMIZED: Uses shared _wrap_with_label_button helper to reduce code duplication.
"""

from PySide6.QtWidgets import ( 
    QPushButton, QLineEdit, QComboBox, QWidget, QVBoxLayout, 
    QGroupBox, QSpinBox, QSizePolicy, QLabel, QHBoxLayout, QDateTimeEdit,
    QScrollArea,
)
from PySide6.QtCore import QDateTime
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.widgets.section_groupbox import SectionGroupBox
from src.ui.config import ELEMENT_HEIGHT, TAG_BUTTON_HEIGHT
from src.ui.ui_factory import UIFactory


# =============================================================================
# Shared Helper Functions
# =============================================================================

def _wrap_with_label_button(widget, label=None, button_text=None, on_button_clicked=None, add_stretch=True):
    """
    Shared wrapper logic for widgets that can have labels and action buttons.
    
    Returns:
      - widget alone if neither label nor button_text provided
      - (container, widget) if only label is provided
      - (container, widget, button) if button_text is provided
    """
    if not label and not button_text:
        return widget
    
    container = QWidget(objectName="Transparent")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    
    if label:
        layout.addWidget(QLabel(label))
    layout.addWidget(widget)
    
    btn = None
    if button_text:
        btn = create_push_button(button_text)
        if callable(on_button_clicked):
            btn.clicked.connect(on_button_clicked)
        layout.addWidget(btn)
    
    if add_stretch:
        layout.addStretch(1)
    
    if btn is not None:
        return container, widget, btn
    return container, widget


# =============================================================================
# Widget Creation Functions
# =============================================================================

def create_push_button(text: str = "", object_name: str = None, height: int = ELEMENT_HEIGHT) -> QPushButton:
    """
    Create a QPushButton with a fixed height and optional object name.
    """
    btn = QPushButton(text)
    if object_name:
        btn.setObjectName(object_name)
    btn.setFixedHeight(height)
    return btn

def create_toggle_button(
    text: str = "",
    *,
    object_name: str = "toggle_button",
    height: int = ELEMENT_HEIGHT,
    tooltip: str | None = None,
    checked: bool | None = None,
    settings_manager = None,
    setting_key: str | None = None,
    force_unchecked: bool = False,
) -> QPushButton:
    """
    Create a theme-styled checkable QPushButton with an obvious on/off visual state.

    Parameters:
      - object_name: defaults to 'toggle_button' to pick up theme styles.
      - tooltip: optional tooltip to set.
      - checked: explicit initial checked state (overrides settings/force if provided).
      - settings_manager + setting_key: if provided, restores initial state from settings.
      - force_unchecked: if True, starts unchecked regardless of saved settings.
    """
    btn = QPushButton(text)
    if object_name:
        btn.setObjectName(object_name)
    btn.setFixedHeight(height)
    btn.setCheckable(True)
    # Restore from settings if available
    if settings_manager is not None and setting_key:
        try:
            if bool(settings_manager.get(setting_key, False)):
                btn.setChecked(True)
        except Exception:
            pass
    # Enforce unchecked start if requested
    if force_unchecked:
        try:
            btn.setChecked(False)
        except Exception:
            pass
    # Explicit checked param wins
    if checked is not None:
        try:
            btn.setChecked(bool(checked))
        except Exception:
            pass
    if tooltip:
        btn.setToolTip(tooltip)
    return btn

def create_tag_buttons(layout, items, text_func, on_click, suffix: str | None = None, objname: str = "tag_button"):
        """
        Populate a layout with tag buttons for each item.
            * layout: Qt layout or flow layout
            * items: iterable of items
            * text_func: function(item) -> label string
            * on_click: function(item) -> called on click
            * suffix: optional text to append to label (e.g. '✕' or '＋'); pass None to omit
            * objname: Qt objectName for styling

        This single function replaces the older split helpers and keeps a simple,
        backward-compatible API. Button height and objectName follow the tag
        styling constants.
        """
        for item in items:
                label = text_func(item)
                text = f"{label}  {suffix}" if suffix is not None else label
                btn = create_push_button(text, object_name=objname, height=TAG_BUTTON_HEIGHT)
                # Bind the current item to the click handler to avoid late-binding traps
                btn.clicked.connect(lambda checked=False, obj=item: on_click(obj))
                layout.addWidget(btn)
        return layout

def create_no_tags_placeholder(layout, text: str = "None"):
    """Add a disabled placeholder button when no tags are present."""
    btn = create_push_button(text, object_name="none_placeholder", height=TAG_BUTTON_HEIGHT)
    btn.setEnabled(False)
    layout.addWidget(btn)
    return layout

def create_fetching_placeholder(layout, text: str = "Fetching..."):
    """Add a disabled placeholder button to indicate fetching is in progress."""
    btn = create_push_button(text, object_name="fetching_placeholder", height=TAG_BUTTON_HEIGHT)
    btn.setEnabled(False)
    layout.addWidget(btn)
    return layout

def create_line_edit(
    object_name: str | None = None,
    height: int = ELEMENT_HEIGHT,
    *,
    label: str | None = None,
    button_text: str | None = None,
    on_button_clicked=None,
):
    """
    Create a QLineEdit with a fixed height and optional object name.

    Extras:
      - label: if provided, include a QLabel at the start.
      - button_text: if provided, include a trailing QPushButton with this text.
      - on_button_clicked: optional slot/callable to connect to the button's clicked signal.

    Returns:
      - QLineEdit if neither label nor button_text provided (backward compatible)
      - (container QWidget, QLineEdit) if only label is provided
      - (container QWidget, QLineEdit, QPushButton) if button is provided (label optional)
    """
    le = QLineEdit()
    if object_name:
        le.setObjectName(object_name)
    le.setFixedHeight(height)
    return _wrap_with_label_button(le, label, button_text, on_button_clicked, add_stretch=False)


def create_combo_box(
    object_name: str | None = None,
    height: int = ELEMENT_HEIGHT,
    *,
    width: int | None = 120,
    label: str | None = None,
    button_text: str | None = None,
    on_button_clicked=None,
) -> QComboBox | tuple[QWidget, QComboBox] | tuple[QWidget, QComboBox, QPushButton]:
    """
    Create a QComboBox with a fixed height and an optional fixed width.

    Parameters:
      - object_name: optional Qt `objectName` for styling
      - height: fixed height in pixels (defaults to `ELEMENT_HEIGHT`)
      - width: fixed width in pixels; if omitted (or `None`) no fixed width is applied.
      - label: optional leading label text (returns a container when provided)
      - button_text: optional trailing button text (returns container, combo, button)
      - on_button_clicked: optional callback for the trailing button

    Returns:
      - QComboBox when no label/button provided
      - (container_widget, QComboBox) when only `label` provided
      - (container_widget, QComboBox, QPushButton) when `button_text` provided
    """
    cb = QComboBox()
    if object_name:
        cb.setObjectName(object_name)
    cb.setFixedHeight(height)
    if width is not None:
        try:
            cb.setFixedWidth(int(width))
        except Exception:
            pass
    return _wrap_with_label_button(cb, label, button_text, on_button_clicked)


def create_spin_box(
    object_name: str | None = None,
    height: int = ELEMENT_HEIGHT,
    *,
    width: int | None = 120,
    minimum: int = 0,
    maximum: int = 100,
    single_step: int = 1,
    label: str | None = None,
) -> QSpinBox | tuple[QWidget, QSpinBox]:
    """
    Create a QSpinBox with a fixed height and optional fixed width.

    Parameters:
        - object_name: optional Qt objectName for styling
        - height: fixed height in pixels
        - width: fixed width in pixels (defaults to 120); set to None to leave width flexible
        - minimum: minimum value
        - maximum: maximum value
        - single_step: step for arrows and keyboard
        - label: optional text to create and attach a QLabel to the left of the spin box

    If `label` is provided, returns a tuple (container_widget, spin_box) where the container is a QWidget
    with a horizontal layout containing a QLabel and the spin box. Otherwise, returns the QSpinBox.
    """
    sb = QSpinBox()
    if object_name:
        sb.setObjectName(object_name)
    sb.setFixedHeight(height)
    # Apply fixed width when requested (default: 120)
    if width is not None:
        try:
            sb.setFixedWidth(int(width))
        except Exception:
            pass
    sb.setRange(minimum, maximum)
    sb.setSingleStep(single_step)
    sb.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
    return _wrap_with_label_button(sb, label)

def create_tags_panel(parent_layout, margin=5, spacing=5):
    """
    Create a tag panel (for filtering) as a QWidget with a FlowLayout.
    Returns a tuple (tag_widget, FlowLayout instance).
    """
    # Backwards-compatible wrapper for the unified create_tags_widget
    widget, layout = create_tags_widget(parent_layout, title=None, margin=margin, spacing=spacing)
    return widget, layout

def create_tags_section(parent_layout, title="Tags", margin=5, spacing=5, settings_manager=None):
    """
    Create a tags section with a SectionGroupBox and a QGroupBox containing a FlowLayout.
    Returns the FlowLayout instance for adding tag widgets.
    """
    # Use the unified create_tags_widget to build a sectioned tags area
    _, layout = create_tags_widget(parent_layout, title=title, margin=margin, spacing=spacing, settings_manager=settings_manager)
    return layout


def create_tags_widget(parent_layout, title: str | None = "Tags", margin=5, spacing=5, settings_manager=None):
    """
    Unified tag creation helper.

    Behaviors:
        - If `title` is None: creates a plain QWidget with a FlowLayout, adds it to parent_layout,
            and returns (widget, FlowLayout).
        - If `title` is a string: creates a SectionGroupBox containing a QGroupBox with a FlowLayout,
            adds the section to parent_layout, and returns the FlowLayout.

    This consolidates `create_tags_panel` and `create_tags_section` into one function while
    preserving backward compatibility via small wrappers above.
    """
    if title is None:
        tag_widget = QWidget()
        tag_widget.setObjectName("TagBox")
        # Prevent the tags widget from taking excess vertical space when empty
        tag_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        tag_layout = FlowLayout(tag_widget, margin=margin, spacing=spacing)
        tag_widget.setLayout(tag_layout)
        parent_layout.addWidget(tag_widget)
        return tag_widget, tag_layout

    # Section variant - use UIFactory if settings_manager is provided
    if settings_manager:
        section = UIFactory.create_section_groupbox(
            settings_manager=settings_manager,
            object_name="tags_section",
            title=title,
            add_inner_box=False,
            size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
    else:
        section = SectionGroupBox("tags_section", title=title, add_inner_box=False)
        # Prevent vertical over-expansion in parent layouts; let content size to its hint
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    
    tags_group = QGroupBox(objectName="TagBox")
    tags_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    tags_layout = QVBoxLayout(tags_group)
    tags_layout.setContentsMargins(0, 0, 0, 0)
    tags_hbox = FlowLayout(margin=margin, spacing=spacing)
    tags_layout.addLayout(tags_hbox)
    section.content_layout.addWidget(tags_group)
    parent_layout.addWidget(section)
    return section, tags_hbox

def create_date_selector(
    parent=None,
    object_name: str | None = None,
    height: int = ELEMENT_HEIGHT,
    width: int = 125,
    *,
    display_format: str = "dd/MM/yyyy",
    calendar_popup: bool = True,
    visible: bool = False,
    enabled: bool = False,
    label: str | None = None,
) -> QDateTimeEdit | tuple[QWidget, QDateTimeEdit]:
    """
    Create a standardized QDateTimeEdit widget for date selection.
    
    This function creates a date selector with consistent configuration across
    the application, ensuring uniform behavior and styling.
    
    Args:
        parent: Parent widget for the date selector
        object_name: Optional Qt objectName for styling
        height: Fixed height in pixels (default: ELEMENT_HEIGHT)
        width: Optional fixed width in pixels (default: None, auto-size)
        display_format: Date display format string (default: "dd/MM/yyyy")
        calendar_popup: Whether to show a calendar popup (default: True)
        visible: Initial visibility state (default: False)
        enabled: Initial enabled state (default: False)
        label: Optional text to create and attach a QLabel to the left of the date selector
        
    Returns:
        QDateTimeEdit: Configured date selector widget if no label
        tuple[QWidget, QDateTimeEdit]: (container_widget, date_selector) if label is provided
        
    Example:
        >>> # Simple date selector
        >>> date_selector = create_date_selector(self, visible=True, enabled=True)
        >>> date_selector.setDateTime(QDateTime.currentDateTime())
        >>> 
        >>> # With label
        >>> container, date_selector = create_date_selector(
        ...     self, label="Redeem By:", visible=True, enabled=True
        ... )
    """
    date_selector = QDateTimeEdit(parent)
    
    if object_name:
        date_selector.setObjectName(object_name)
    
    date_selector.setFixedHeight(height)
    if width is not None:
        date_selector.setFixedWidth(width)
    
    date_selector.setDisplayFormat(display_format)
    date_selector.setCalendarPopup(calendar_popup)
    date_selector.setVisible(visible)
    date_selector.setEnabled(enabled)
    
    # Set default to current date instead of Qt's default (01/01/2000)
    date_selector.setDateTime(QDateTime.currentDateTime())
    
    return _wrap_with_label_button(date_selector, label)


def create_scroll_area(
    parent=None,
    object_name: str | None = None,
    *,
    widget: QWidget | None = None,
    widget_resizable: bool = True,
    horizontal_policy=None,
    vertical_policy=None,
    frame_shape=None,
    alignment=None,
    size_policy=None,
    minimum_width: int | None = None,
    minimum_height: int | None = None,
) -> QScrollArea:
    """
    Create a standardized QScrollArea for consistent app-wide behaviour.

    Args:
        parent: Parent widget (optional)
        object_name: Optional object name for styling
        widget: Optional child widget to set with setWidget()
        widget_resizable: Whether the scroll area should resize its widget (setWidgetResizable)
        horizontal_policy: Horizontal scroll bar policy (Qt.ScrollBarPolicy value)
        vertical_policy: Vertical scroll bar policy (Qt.ScrollBarPolicy value)
        frame_shape: Optional QFrame.Shape to apply via setFrameShape
        alignment: Optional alignment for setAlignment
        size_policy: Optional QSizePolicy to apply to the scroll area
        minimum_width: Optional minimum width in pixels
        minimum_height: Optional minimum height in pixels

    Returns:
        Configured QScrollArea instance
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame

    sa = QScrollArea(parent)
    if object_name:
        sa.setObjectName(object_name)
    sa.setWidgetResizable(bool(widget_resizable))

    if horizontal_policy is None:
        horizontal_policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded
    if vertical_policy is None:
        vertical_policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded

    try:
        sa.setHorizontalScrollBarPolicy(horizontal_policy)
    except Exception:
        pass

    try:
        sa.setVerticalScrollBarPolicy(vertical_policy)
    except Exception:
        pass

    if frame_shape is not None:
        try:
            sa.setFrameShape(frame_shape)
        except Exception:
            pass

    if alignment is not None:
        try:
            sa.setAlignment(alignment)
        except Exception:
            pass

    if size_policy is not None:
        try:
            sa.setSizePolicy(size_policy)
        except Exception:
            pass

    if minimum_width is not None:
        try:
            sa.setMinimumWidth(int(minimum_width))
        except Exception:
            pass

    if minimum_height is not None:
        try:
            sa.setMinimumHeight(int(minimum_height))
        except Exception:
            pass

    if widget is not None:
        try:
            sa.setWidget(widget)
        except Exception:
            pass

    return sa
