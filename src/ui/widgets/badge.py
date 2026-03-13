"""
Badge widget for displaying small notifications, counts, and status indicators.
Can be attached to buttons and other UI elements.

Usage Examples:
    # Simple one-liner to add a badge to any widget
    add_badge(button, text="NEW")
    add_badge(button, count=5)
    add_badge(button, show_dot=True)
    
    # Or use the Badge class directly
    badge = Badge(parent=button, text="BETA")
    
    # Update badge content
    badge.set_text("UPDATED")
    badge.set_count(10)
"""

from PySide6.QtWidgets import QLabel, QWidget, QSizePolicy
from PySide6.QtCore import Qt, QEvent, QSize, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QColor, QFontMetrics
from enum import Enum
from typing import Optional, Union
import weakref


class BadgePosition(Enum):
    """Position of badge relative to parent widget"""
    TOP_RIGHT = "top_right"
    TOP_LEFT = "top_left"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_LEFT = "bottom_left"
    CENTER_RIGHT = "center_right"


class Badge(QLabel):
    """
    A versatile badge widget that can display counts, dots, or custom text.
    Automatically sizes itself based on content.
    
    Args:
        parent: Parent widget to attach badge to
        text: Custom text to display (e.g., "NEW", "BETA", "UPDATED")
        count: Numeric count to display (0-99+)
        show_dot: Show as a simple notification dot
        position: Position relative to parent (BadgePosition enum)
        bg_color: Background color (defaults to theme accent color)
        text_color: Text color (defaults to contrasting color)
        theme_manager: Theme manager for automatic color updates
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        text: str = "",
        count: int = 0,
        show_dot: bool = False,
        position: BadgePosition = BadgePosition.TOP_RIGHT,
        bg_color: Optional[QColor] = None,
        text_color: Optional[QColor] = None,
        theme_manager = None,
        animate_dot: bool = True
    ):
        super().__init__(parent)
        
        # State
        self._text = text
        self._count = max(0, count) if count else 0
        self._show_dot = show_dot
        self.position = position
        self._animate_dot = animate_dot
        
        # Visual properties
        self._bg_color = bg_color or QColor("#ff4444")
        self._text_color = text_color or QColor("#ffffff")
        self._min_size = 14  # Minimum size for count/text badges
        self._dot_size = 8   # Size for dot badges
        self._padding = 4    # Horizontal padding around text
        self._vertical_padding = 0  # Vertical padding (smaller for tighter fit)
        self._offset = -4    # Offset from parent edge (negative = inward)
        
        # Theme management
        self.theme_manager = theme_manager
        self._setup_theme()
        
        # Animation properties (for dot mode)
        self._primary_color = None
        self._accent_color = None
        self._current_color = self._bg_color
        self._animation = None
        self._hold_timer = None
        self._animation_connected = False
        
        # Setup widget
        self._setup_ui()
        self._update_content()
        
        # Install event filter on parent
        if parent:
            parent.installEventFilter(self)
    
    def _setup_theme(self):
        """Setup theme manager and connect to theme changes."""
        if self.theme_manager is None and self.parent():
            self.theme_manager = getattr(self.parent(), 'theme_manager', None)
        
        if self.theme_manager and hasattr(self.theme_manager, 'theme_changed'):
            self.theme_manager.theme_changed.connect(
                self._apply_theme, 
                Qt.ConnectionType.UniqueConnection
            )
            self._apply_theme()
    
    def _apply_theme(self):
        """Apply theme colors to the badge."""
        if not self.theme_manager:
            return
        
        palette = self.theme_manager.get_palette()
        accent_color = palette.get('accent_color', '#ff4444')
        primary_color = palette.get('primary_color', '#3498db')
        
        self._bg_color = QColor(accent_color)
        self._accent_color = QColor(accent_color)
        self._primary_color = QColor(primary_color)
        
        # Get contrasting text color
        try:
            from src.core.theme.colors import get_contrasting_text_color
            self._text_color = QColor(get_contrasting_text_color(accent_color))
        except (ImportError, Exception):
            self._text_color = QColor("#ffffff")
        
        # If animating, update the current color to accent
        if self._show_dot and self._animate_dot:
            self._current_color = self._accent_color
        
        self._update_style()
    
    def _setup_ui(self):
        """Initialize widget properties."""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Font setup
        font = self.font()
        font.setPointSize(7)
        font.setBold(True)
        self.setFont(font)
    
    def _update_content(self):
        """Update badge content and visibility based on current state."""
        # Stop any existing animation
        self._stop_dot_animation()
        
        # Determine what to show
        if self._show_dot:
            self.setText("")
            self.setFixedSize(self._dot_size, self._dot_size)
            if self._animate_dot:
                self._setup_dot_animation()
        elif self._count > 0:
            self.setText(str(self._count) if self._count <= 99 else "99+")
            self._update_size_for_text()
        elif self._text:
            self.setText(self._text)
            self._update_size_for_text()
        else:
            self.hide()
            return
        
        self._update_style()
        self._update_position()
        self.show()
    
    def _update_size_for_text(self):
        """Calculate and set size based on text content."""
        if not self.text():
            self.setFixedSize(self._min_size, self._min_size)
            return
        
        # Measure text
        metrics = QFontMetrics(self.font())
        width = max(self._min_size, metrics.horizontalAdvance(self.text()) + 2 * self._padding)
        height = max(self._min_size, metrics.height() + 2 * self._vertical_padding)
        
        # For single-digit counts, make it circular
        if self._count > 0 and self._count < 10:
            size = max(width, height)
            width = height = size
        
        self.setFixedSize(int(width), int(height))
    
    def _update_style(self):
        """Update stylesheet with current colors and border radius."""
        radius = self._dot_size // 2 if self._show_dot else min(self.width(), self.height()) // 2
        
        # Use RGBA format for semi-transparent background on count badges
        # Dot badges stay fully opaque for better visibility
        if self._show_dot:
            bg_color_str = self._bg_color.name()
        else:
            # Make count/text badges slightly transparent (50% opacity)
            bg_color_str = f"rgba({self._bg_color.red()}, {self._bg_color.green()}, {self._bg_color.blue()}, 0.50)"
        
        self.setStyleSheet(
            f"QLabel {{ background-color: {bg_color_str}; color: {self._text_color.name()}; "
            f"border: none; border-radius: {radius}px; padding: 0px; font-weight: bold; }}"
        )
    
    def _update_position(self):
        """Update badge position relative to parent."""
        parent = self.parentWidget()
        if not parent:
            return
        
        parent_w, parent_h = parent.width(), parent.height()
        badge_w, badge_h = self.width(), self.height()
        offset = self._offset
        
        # Position mapping: (x_calculation, y_calculation)
        positions = {
            BadgePosition.TOP_RIGHT: (parent_w - badge_w + offset, -offset),
            BadgePosition.TOP_LEFT: (-offset, -offset),
            BadgePosition.BOTTOM_RIGHT: (parent_w - badge_w + offset, parent_h - badge_h + offset),
            BadgePosition.BOTTOM_LEFT: (-offset, parent_h - badge_h + offset),
            BadgePosition.CENTER_RIGHT: (parent_w - badge_w + offset, (parent_h - badge_h) // 2),
        }
        
        x, y = positions.get(self.position, (0, 0))
        self.move(int(x), int(y))
    
    # Public API methods
    
    def set_text(self, text: str):
        """Set custom text for the badge."""
        self._text = text
        self._count = 0
        self._show_dot = False
        self._update_content()
    
    def set_count(self, count: int):
        """Set numeric count for the badge."""
        self._count = max(0, count)
        self._text = ""
        self._show_dot = False
        self._update_content()
    
    def set_dot(self, visible: bool):
        """Show or hide dot badge."""
        self._show_dot = visible
        if visible:
            self._count = 0
            self._text = ""
        self._update_content()
    
    def set_position(self, position: BadgePosition):
        """Set badge position relative to parent."""
        self.position = position
        self._update_position()
    
    def set_offset(self, offset: int):
        """Set offset from parent edge."""
        self._offset = offset
        self._update_position()
    
    def set_colors(self, bg_color: QColor, text_color: Optional[QColor] = None):
        """Set badge colors."""
        self._bg_color = bg_color
        if text_color:
            self._text_color = text_color
        self._update_style()
    
    def get_text(self) -> str:
        """Get current text value."""
        return self._text
    
    def get_count(self) -> int:
        """Get current count value."""
        return self._count
    
    def is_dot_visible(self) -> bool:
        """Check if dot is visible."""
        return self._show_dot
    
    def is_visible_badge(self) -> bool:
        """Check if badge should be visible based on content."""
        return self._show_dot or self._count > 0 or bool(self._text.strip())
    
    # Event handlers
    
    def showEvent(self, event):
        """Reposition on show."""
        super().showEvent(event)
        self._update_position()
    
    def resizeEvent(self, event):
        """Update style when resized."""
        super().resizeEvent(event)
        self._update_style()
        self._update_position()
    
    def eventFilter(self, obj, event):
        """Track parent changes to keep badge positioned."""
        if obj is self.parentWidget():
            event_type = event.type()
            if event_type in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
                self._update_position()
                if event_type == QEvent.Type.Show and self.is_visible_badge():
                    self.show()
            elif event_type == QEvent.Type.Hide:
                self.hide()
        return super().eventFilter(obj, event)
    
    # Dot animation methods
    
    def _setup_dot_animation(self):
        """Setup color animation for dot badges."""
        # Ensure colors are set from theme or use defaults
        if self._accent_color is None:
            if self.theme_manager:
                palette = self.theme_manager.get_palette()
                self._accent_color = QColor(palette.get('accent_color', '#ff4444'))
                self._primary_color = QColor(palette.get('primary_color', '#3498db'))
            else:
                self._accent_color = self._bg_color
                self._primary_color = QColor("#3498db")
        
        if self._primary_color is None:
            if self.theme_manager:
                palette = self.theme_manager.get_palette()
                self._primary_color = QColor(palette.get('primary_color', '#3498db'))
            else:
                self._primary_color = QColor("#3498db")
        
        self._current_color = self._accent_color
        self._bg_color = self._accent_color
        
        # Create animation
        self._animation = QPropertyAnimation(self, b"animatedColor")
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.setDuration(1000)  # 1 second total fade
        
        # Create hold timer
        self._hold_timer = QTimer(self)
        self._hold_timer.setInterval(3000)  # 3 seconds hold
        self._hold_timer.timeout.connect(self._start_dot_flash)
        
        # Start the cycle
        self._hold_timer.start()
    
    def _start_dot_flash(self):
        """Start the color flash animation."""
        if not self._animation or not self._show_dot:
            return
        
        # Stop hold timer
        self._hold_timer.stop()
        
        # Setup animation to flash to primary color and back
        self._animation.setStartValue(self._accent_color)
        self._animation.setKeyValueAt(0.5, self._primary_color)
        self._animation.setEndValue(self._accent_color)
        
        # Restart hold timer when animation finishes
        if self._animation_connected:
            self._animation.finished.disconnect(self._on_dot_animation_finished)
        self._animation.finished.connect(self._on_dot_animation_finished)
        self._animation_connected = True
        self._animation.start()
    
    def _on_dot_animation_finished(self):
        """Called when dot animation completes."""
        if self._hold_timer:
            self._hold_timer.start()
    
    def _stop_dot_animation(self):
        """Stop dot animation if running."""
        if self._hold_timer:
            self._hold_timer.stop()
        if self._animation:
            self._animation.stop()
            if self._animation_connected:
                try:
                    self._animation.finished.disconnect(self._on_dot_animation_finished)
                    self._animation_connected = False
                except (RuntimeError, TypeError):
                    pass
    
    def _get_animated_color(self):
        """Get current animated color."""
        return self._current_color
    
    def _set_animated_color(self, color):
        """Set current animated color and update display."""
        self._current_color = color
        self._bg_color = color
        self._update_style()
    
    # Property for animation
    animatedColor = Property(QColor, _get_animated_color, _set_animated_color)


# Global badge manager for easy badge management
_global_badge_manager = None


class BadgeManager:
    """
    Utility class to manage badges attached to widgets.
    Uses weak references to avoid memory leaks.
    """
    
    def __init__(self, theme_manager=None):
        self._badges = weakref.WeakKeyDictionary()
        self.theme_manager = theme_manager
    
    def add_badge(
        self,
        widget: QWidget,
        text: str = "",
        count: int = 0,
        show_dot: bool = False,
        position: BadgePosition = BadgePosition.TOP_RIGHT
    ) -> Badge:
        """
        Add a badge to a widget.
        
        Args:
            widget: Widget to attach badge to
            text: Custom text (e.g., "NEW", "BETA")
            count: Numeric count (0-99+)
            show_dot: Show as notification dot
            position: Badge position
        
        Returns:
            Badge instance
        """
        # Remove existing badge if any
        self.remove_badge(widget)
        
        # Create new badge
        badge = Badge(
            parent=widget,
            text=text,
            count=count,
            show_dot=show_dot,
            position=position,
            theme_manager=self.theme_manager
        )
        
        self._badges[widget] = badge
        return badge
    
    def remove_badge(self, widget: QWidget):
        """Remove badge from a widget."""
        badge = self._badges.pop(widget, None)
        if badge:
            badge.deleteLater()
    
    def get_badge(self, widget: QWidget) -> Optional[Badge]:
        """Get badge attached to a widget."""
        return self._badges.get(widget)
    
    def update_text(self, widget: QWidget, text: str):
        """Update text on a widget's badge."""
        badge = self.get_badge(widget)
        if badge:
            badge.set_text(text)
    
    def update_count(self, widget: QWidget, count: int):
        """Update count on a widget's badge."""
        badge = self.get_badge(widget)
        if badge:
            badge.set_count(count)
    
    def set_dot_visible(self, widget: QWidget, visible: bool):
        """Update dot visibility on a widget's badge."""
        badge = self.get_badge(widget)
        if badge:
            badge.set_dot(visible)
    
    def clear_all(self):
        """Remove all badges."""
        for badge in list(self._badges.values()):
            badge.deleteLater()
        self._badges.clear()


def get_badge_manager(theme_manager=None) -> BadgeManager:
    """
    Get the global badge manager instance.
    
    Args:
        theme_manager: Optional theme manager for theme-aware badges
    
    Returns:
        Global BadgeManager instance
    """
    global _global_badge_manager
    if _global_badge_manager is None:
        _global_badge_manager = BadgeManager(theme_manager)
    return _global_badge_manager


# Convenience function for easy one-liner badge addition
def add_badge(
    widget: QWidget,
    text: str = "",
    count: int = 0,
    show_dot: bool = False,
    position: BadgePosition = BadgePosition.TOP_RIGHT,
    theme_manager=None,
    animate_dot: bool = True
) -> Badge:
    """
    Convenience function to add a badge to any widget with a one-liner.
    
    Examples:
        add_badge(button, text="NEW")
        add_badge(button, count=5)
        add_badge(button, show_dot=True)
        add_badge(button, show_dot=True, animate_dot=False)  # Static dot
        add_badge(button, text="BETA", position=BadgePosition.TOP_LEFT)
    
    Args:
        widget: Widget to attach badge to
        text: Custom text to display
        count: Numeric count to display
        show_dot: Show as notification dot
        position: Badge position relative to parent
        theme_manager: Optional theme manager
        animate_dot: Enable color animation for dot badges (default: True)
    
    Returns:
        Badge instance
    """
    badge = Badge(
        parent=widget,
        text=text,
        count=count,
        show_dot=show_dot,
        position=position,
        theme_manager=theme_manager,
        animate_dot=animate_dot
    )
    return badge


def get_badge(widget: QWidget) -> Optional[Badge]:
    """
    Get the badge attached to a widget.
    
    Args:
        widget: Widget to get badge from
    
    Returns:
        Badge instance or None
    """
    # Look for Badge child widget
    for child in widget.children():
        if isinstance(child, Badge):
            return child
    return None


def remove_badge(widget: QWidget):
    """
    Remove badge from a widget.
    
    Args:
        widget: Widget to remove badge from
    """
    badge = get_badge(widget)
    if badge:
        badge.deleteLater()
