"""
Tooltip Helper - Mixin and utility functions for easily adding custom tooltips to widgets

This module provides:
- TooltipMixin: A mixin class for widgets to easily add custom tooltips
- Helper functions for widget tooltip management
"""

from PySide6.QtCore import QTimer, QPoint, QEvent
from PySide6.QtGui import QCursor, QEnterEvent
from PySide6.QtWidgets import QWidget
from typing import Optional, Callable

from .custom_tooltip import (
    CustomTooltip,
    TooltipAnimation,
    get_tooltip_manager
)


class TooltipMixin:
    """
    Mixin class to add custom tooltip functionality to any QWidget.
    
    Usage:
        class MyWidget(QWidget, TooltipMixin):
            def __init__(self):
                super().__init__()
                self.setup_custom_tooltip(theme_manager)
                self.set_custom_tooltip("My tooltip text")
    """
    
    def setup_custom_tooltip(
        self,
        theme_manager=None,
        animation: TooltipAnimation = TooltipAnimation.FADE,
        show_delay: int = 500
    ):
        """
        Initialize custom tooltip for this widget.
        
        Args:
            theme_manager: Optional theme manager for styling
            animation: Default animation type (FADE or SLIDE)
            show_delay: Delay before showing tooltip (ms)
        """
        # Get or create tooltip instance
        self._custom_tooltip = get_tooltip_manager(theme_manager)
        
        # Store default settings
        self._tooltip_text: Optional[str] = None
        self._tooltip_animation = animation
        self._tooltip_show_delay = show_delay
        self._tooltip_enabled = True
        self._tooltip_callback: Optional[Callable] = None
        
        # Install event filter for tooltip handling
        if isinstance(self, QWidget):
            self.installEventFilter(self)
    
    def set_custom_tooltip(
        self, 
        text: str,
        animation: Optional[TooltipAnimation] = None
    ):
        """
        Set the tooltip text for this widget.
        
        Args:
            text: The tooltip text to display
            animation: Override default animation (optional)
        """
        self._tooltip_text = text
        if animation is not None:
            self._tooltip_animation = animation
    
    def set_tooltip_callback(self, callback: Callable[[], str]):
        """
        Set a callback function that returns dynamic tooltip text.
        The callback will be called each time the tooltip is about to be shown.
        
        Args:
            callback: Function that returns the tooltip text
        """
        self._tooltip_callback = callback
    
    def enable_custom_tooltip(self, enabled: bool = True):
        """Enable or disable the custom tooltip"""
        self._tooltip_enabled = enabled
    
    def disable_custom_tooltip(self):
        """Disable the custom tooltip"""
        self._tooltip_enabled = False
    
    def eventFilter(self, obj, event: QEvent) -> bool:
        """Handle events for tooltip display"""
        if not self._tooltip_enabled or not hasattr(self, '_custom_tooltip'):
            return super().eventFilter(obj, event) if hasattr(super(), 'eventFilter') else False
        
        if obj == self:
            if event.type() == QEvent.Type.Enter:
                self._on_tooltip_enter()
            elif event.type() == QEvent.Type.Leave:
                self._on_tooltip_leave()
        
        return super().eventFilter(obj, event) if hasattr(super(), 'eventFilter') else False
    
    def _on_tooltip_enter(self):
        """Handle mouse enter for tooltip"""
        # Get tooltip text (from callback or stored text)
        tooltip_text = self._tooltip_text
        if self._tooltip_callback:
            try:
                tooltip_text = self._tooltip_callback()
            except Exception:
                pass
        
        if not tooltip_text:
            return
        
        # Configure tooltip
        self._custom_tooltip.set_animation_type(self._tooltip_animation)
        self._custom_tooltip.set_show_delay(self._tooltip_show_delay)
        
        # Show tooltip positioned relative to widget
        self._custom_tooltip.show_tooltip(tooltip_text, self)
    
    def _on_tooltip_leave(self):
        """Handle mouse leave for tooltip"""
        if hasattr(self, '_custom_tooltip'):
            self._custom_tooltip.hide_tooltip()


def attach_tooltip(
    widget: QWidget,
    text: str,
    theme_manager=None,
    animation: TooltipAnimation = TooltipAnimation.FADE,
    show_delay: int = 500
):
    """
    Attach a custom tooltip to any widget without using the mixin.
    
    This is useful for adding tooltips to existing widgets that you can't modify.
    Tooltips are positioned relative to the widget center and oriented towards
    the window center.
    
    Args:
        widget: The widget to attach tooltip to
        text: The tooltip text
        theme_manager: Optional theme manager for styling
        animation: Animation type (FADE or SLIDE)
        show_delay: Delay before showing (ms)
    
    Example:
        button = QPushButton("Click me")
        attach_tooltip(button, "This button does something cool!")
    """
    tooltip_manager = get_tooltip_manager(theme_manager)
    
    # Store settings on the widget
    widget._custom_tooltip_text = text
    widget._custom_tooltip_animation = animation
    widget._custom_tooltip_show_delay = show_delay
    widget._custom_tooltip_manager = tooltip_manager
    
    # Create event handlers
    def on_enter(event):
        tooltip_manager.set_animation_type(widget._custom_tooltip_animation)
        tooltip_manager.set_show_delay(widget._custom_tooltip_show_delay)
        tooltip_manager.show_tooltip(widget._custom_tooltip_text, widget)
        
        # Call original handler if it exists
        if hasattr(widget, '_original_enter_event'):
            widget._original_enter_event(event)
    
    def on_leave(event):
        tooltip_manager.hide_tooltip()
        
        # Call original handler if it exists
        if hasattr(widget, '_original_leave_event'):
            widget._original_leave_event(event)
    
    # Store original handlers
    if hasattr(widget, 'enterEvent'):
        widget._original_enter_event = widget.enterEvent
    if hasattr(widget, 'leaveEvent'):
        widget._original_leave_event = widget.leaveEvent
    
    # Override handlers
    widget.enterEvent = on_enter
    widget.leaveEvent = on_leave


def update_tooltip_text(widget: QWidget, text: str):
    """
    Update the tooltip text for a widget that has an attached custom tooltip.
    
    Args:
        widget: The widget with attached tooltip
        text: New tooltip text
    """
    if hasattr(widget, '_custom_tooltip_text'):
        widget._custom_tooltip_text = text


def remove_tooltip(widget: QWidget):
    """
    Remove custom tooltip from a widget.
    
    Args:
        widget: The widget to remove tooltip from
    """
    # Restore original handlers if they exist
    if hasattr(widget, '_original_enter_event'):
        widget.enterEvent = widget._original_enter_event
        delattr(widget, '_original_enter_event')
    
    if hasattr(widget, '_original_leave_event'):
        widget.leaveEvent = widget._original_leave_event
        delattr(widget, '_original_leave_event')
    
    # Clean up stored attributes
    for attr in ['_custom_tooltip_text', '_custom_tooltip_animation', 
                 '_custom_tooltip_show_delay', '_custom_tooltip_manager']:
        if hasattr(widget, attr):
            delattr(widget, attr)
