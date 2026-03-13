"""
UI Factory Module

Centralized factory for creating UI components with user-configurable styles.
This allows for easy customization of toggle switches and section groupboxes
throughout the application based on user settings.

Usage:
    from src.ui.ui_factory import UIFactory
    
    # Create a toggle switch (respects user's toggle_style setting)
    toggle = UIFactory.create_toggle(
        settings_manager=settings_manager,
        theme_manager=theme_manager,
        parent=parent,
        checked=True,
        label_text="Enable Feature"
    )
    
    # Create a section groupbox (respects user's section_groupbox_layout setting)
    section = UIFactory.create_section_groupbox(
        settings_manager=settings_manager,
        title="Section Title",
        parent=parent
    )
    
    # Add a badge to any widget (one-liner)
    button = UIFactory.create_button_with_badge(
        parent=parent,
        text="Updates",
        badge_text="NEW"
    )
    # Or add badge to existing widget
    UIFactory.add_badge_to_widget(button, text="BETA")
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget, QHBoxLayout, QSizePolicy
from src.ui.widgets.toggles.styleable_toggle import StyleableToggle, StyleableLabel


class UIFactory:
    """Factory class for creating UI components with configurable styles."""
    
    # Default values if settings_manager is not provided
    DEFAULT_TOGGLE_STYLE = 'regular'
    DEFAULT_SECTION_TITLE_LOCATION = 'left'
    
    @staticmethod
    def create_toggle(
        settings_manager,
        theme_manager,
        parent=None,
        checked=False,
        label_text="",
        animation_duration=120,
        callback=None,
        setting_key=None,
        default_checked=True
    ):
        """
        Create a toggle switch based on user's preferred style.
        
        Args:
            settings_manager: Settings manager instance to get user preferences
            theme_manager: Theme manager instance for styling
            parent: Parent widget
            checked: Initial checked state (used if setting_key is None)
            label_text: Label text for pill/dot styles
            animation_duration: Animation duration in milliseconds
            callback: Optional callback to connect to toggled signal
            setting_key: Optional settings key to load checked state from
            default_checked: Default checked state if setting_key is provided
        
        Returns:
            StyleableToggle instance that updates dynamically
        """
        
        toggle = StyleableToggle(
            settings_manager=settings_manager,
            theme_manager=theme_manager,
            label_text=label_text,
            parent=parent,
            checked=checked,
            animation_duration=animation_duration,
            setting_key=setting_key,
            default_checked=default_checked
        )
        
        # Connect callback if provided
        if callback:
            toggle.toggled.connect(callback)
        
        return toggle
    
    @staticmethod
    def create_toggle_with_label(
        settings_manager,
        theme_manager,
        label_text,
        parent=None,
        checked=False,
        animation_duration=120,
        callback=None,
        setting_key=None,
        default_checked=True
    ):
        """
        Create a toggle switch with label based on user's preferred style.
        
        Returns a container with StyleableLabel and StyleableToggle.
        The label is always shown for the available toggle styles (no integrated "pill" style exists).
        """
        container = QWidget(parent, objectName="Transparent")
        container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        # Use spacing only if label is visible? StyleableLabel handles visibility.
        # We can set spacing and if label is hidden, spacing might remain?
        # QHBoxLayout spacing is between items. If item is hidden, spacing is usually removed or collapsed.
        layout.setSpacing(5) 
        
        toggle = StyleableToggle(
            settings_manager=settings_manager,
            theme_manager=theme_manager,
            label_text=label_text,
            parent=container,
            checked=checked,
            animation_duration=animation_duration,
            setting_key=setting_key,
            default_checked=default_checked
        )
        
        label = StyleableLabel(
            text=label_text,
            settings_manager=settings_manager,
            toggle_widget=toggle,
            parent=container
        )
        
        layout.addWidget(label)
        layout.addWidget(toggle)
        
        # Connect callback if provided
        if callback:
            toggle.toggled.connect(callback)
            
        # Attach convenience references
        container.toggle = toggle
        container.toggled = toggle.toggled
        
        return container
    
    @staticmethod
    def create_section_groupbox(
        settings_manager,
        title=None,
        parent=None,
        object_name=None,
        size_policy=None,
        add_title=True,
        add_inner_box=True,
        margins=None,
        override_title_location=None,
        title_width=None,
        title_vertical_alignment="center",
        inner_orientation=None
    ):
        """
        Create a section groupbox based on user's preferred title location.
        
        Args:
            settings_manager: Settings manager instance to get user preferences
            title: Section title
            parent: Parent widget
            object_name: Object name for styling
            size_policy: Size policy for the groupbox
            add_title: Whether to add title
            add_inner_box: Whether to add inner box
            margins: Margins tuple
            override_title_location: Override the user preference for title location ("left" or "top")
            title_width: Width of title column (for left layout)
            title_vertical_alignment: Vertical alignment of title
            inner_orientation: Inner orientation (Qt.Horizontal or Qt.Vertical) - defaults to Horizontal
        
        Returns:
            SectionGroupBox instance
        """
        from src.ui.widgets.section_groupbox import SectionGroupBox
        
        # Get user's preferred title location
        if override_title_location is not None:
            title_location = override_title_location
        else:
            title_location = settings_manager.get('section_groupbox_title_location', UIFactory.DEFAULT_SECTION_TITLE_LOCATION) if settings_manager else UIFactory.DEFAULT_SECTION_TITLE_LOCATION
        
        # Default to vertical inner orientation if not specified (most sections are vertical)
        if inner_orientation is None:
            inner_orientation = Qt.Vertical
        
        # Create section groupbox with user's preferred title location
        section = SectionGroupBox(
            object_name=object_name,
            title=title,
            size_policy=size_policy,
            add_title=add_title,
            add_inner_box=add_inner_box,
            parent=parent,
            margins=margins,
            inner_orientation=inner_orientation,
            title_location=title_location,
            title_width=title_width,
            title_vertical_alignment=title_vertical_alignment
        )
        
        return section
    
    @staticmethod
    def get_toggle_style(settings_manager):
        """
        Get the current toggle style preference.
        
        Args:
            settings_manager: Settings manager instance
        
        Returns:
            str: Toggle style ('regular' or 'dot')
        """
        return settings_manager.get('toggle_style', UIFactory.DEFAULT_TOGGLE_STYLE) if settings_manager else UIFactory.DEFAULT_TOGGLE_STYLE
    
    @staticmethod
    def get_section_title_location(settings_manager):
        """
        Get the current section title location preference.
        
        Args:
            settings_manager: Settings manager instance
        
        Returns:
            str: Section title location ('left' or 'top')
        """
        return settings_manager.get('section_groupbox_title_location', UIFactory.DEFAULT_SECTION_TITLE_LOCATION) if settings_manager else UIFactory.DEFAULT_SECTION_TITLE_LOCATION
    
    
    
    # Badge methods
    
    @staticmethod
    def add_badge_to_widget(
        widget: QWidget,
        text: str = "",
        count: int = 0,
        show_dot: bool = False,
        position=None,
        theme_manager=None
    ):
        """
        Add a badge to any widget with a one-liner.
        
        Examples:
            UIFactory.add_badge_to_widget(button, text="NEW")
            UIFactory.add_badge_to_widget(button, count=5)
            UIFactory.add_badge_to_widget(button, show_dot=True)
        
        Args:
            widget: Widget to attach badge to
            text: Custom text to display (e.g., "NEW", "BETA", "UPDATED")
            count: Numeric count to display (0-99+)
            show_dot: Show as notification dot
            position: Badge position (BadgePosition enum, defaults to TOP_RIGHT)
            theme_manager: Optional theme manager for theme-aware badges
        
        Returns:
            Badge instance
        """
        from src.ui.widgets.badge import Badge, BadgePosition
        
        if position is None:
            position = BadgePosition.TOP_RIGHT
        
        badge = Badge(
            parent=widget,
            text=text,
            count=count,
            show_dot=show_dot,
            position=position,
            theme_manager=theme_manager
        )
        return badge
    
    @staticmethod
    def create_button_with_badge(
        parent=None,
        text: str = "",
        badge_text: str = "",
        badge_count: int = 0,
        badge_show_dot: bool = False,
        badge_position=None,
        theme_manager=None,
        **button_kwargs
    ):
        """
        Create a QPushButton with a badge attached.
        
        Args:
            parent: Parent widget
            text: Button text
            badge_text: Badge text (e.g., "NEW", "BETA")
            badge_count: Badge count
            badge_show_dot: Show badge as dot
            badge_position: Badge position (BadgePosition enum)
            theme_manager: Theme manager for badge theming
            **button_kwargs: Additional arguments passed to QPushButton
        
        Returns:
            QPushButton with badge attached
        """
        from src.ui.widgets.badge import BadgePosition
        
        button = QPushButton(text, parent, **button_kwargs)
        
        # Only add badge if there's something to show
        if badge_text or badge_count > 0 or badge_show_dot:
            UIFactory.add_badge_to_widget(
                widget=button,
                text=badge_text,
                count=badge_count,
                show_dot=badge_show_dot,
                position=badge_position or BadgePosition.TOP_RIGHT,
                theme_manager=theme_manager
            )
        
        return button
    
    @staticmethod
    def get_widget_badge(widget: QWidget):
        """
        Get the badge attached to a widget.
        
        Args:
            widget: Widget to get badge from
        
        Returns:
            Badge instance or None
        """
        from src.ui.widgets.badge import get_badge
        return get_badge(widget)
    
    @staticmethod
    def remove_widget_badge(widget: QWidget):
        """
        Remove badge from a widget.
        
        Args:
            widget: Widget to remove badge from
        """
        from src.ui.widgets.badge import remove_badge
        remove_badge(widget)
