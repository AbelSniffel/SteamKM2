"""
Custom Tooltip Widget with Smart Positioning and Animations

Features:
- Automatic positioning towards window center
- Widget-based origin positioning
- Multiple animation styles (fade, slide)
- Theme-sensitive styling
- Configurable appearance and behavior
"""

from PySide6.QtWidgets import QLabel, QWidget, QApplication, QGraphicsOpacityEffect
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation, 
    QEasingCurve, QParallelAnimationGroup, Signal, QEvent
)
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen
from enum import Enum, auto
from typing import Optional, Union
from ...config import TOOLTIP_OFFSET, TOOLTIP_SHOW_DELAY, TOOLTIP_HIDE_DELAY


class TooltipAnimation(Enum):
    """Enum for tooltip animation styles"""
    FADE = auto()      # Simple fade in/out
    SLIDE = auto()     # Slide in from edge


class CustomTooltip(QLabel):
    """
    A custom tooltip widget with smart positioning and animations.
    
    Features:
    - Automatically positions towards window center
    - Widget-based origin positioning
    - Supports multiple animation styles
    - Theme-sensitive styling via theme_manager
    - Configurable via config.py
    """
    
    shown = Signal()  # Emitted when tooltip is shown
    hidden = Signal()  # Emitted when tooltip is hidden
    
    def __init__(self, parent: Optional[QWidget] = None, theme_manager=None):
        super().__init__(parent)
        
        self.theme_manager = theme_manager
        
        # Animation settings
        self._animation_type = TooltipAnimation.FADE
        
        # Tooltip configuration (from config.py)
        self._offset = TOOLTIP_OFFSET
        self._padding = 8
        self._border_radius = 6
        self._max_width = 300
        self._show_delay = TOOLTIP_SHOW_DELAY
        self._hide_delay = TOOLTIP_HIDE_DELAY
        
        # State tracking
        self._pending_show = None  # Stores (text, widget, force_direction) for delayed show
        self._target_widget = None  # Widget to position relative to
        self._tooltip_direction = "below"  # Direction tooltip appears relative to widget
        self._force_direction = None  # If set, forces tooltip to specific direction
        
        # Theme colors (set by _apply_theme)
        self._bg_color = QColor(45, 45, 48, 220)
        self._text_color = QColor(255, 255, 255)
        self._border_color = QColor(100, 100, 100, 180)
        
        # Setup widget properties
        self.setWindowFlags(
            Qt.WindowType.ToolTip | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.NoDropShadowWindowHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWordWrap(True)
        self.setMaximumWidth(self._max_width)
        self.setMargin(self._padding)
        
        # Opacity effect for animations
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        
        # Timers
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._do_show)
        
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)
        
        # Animation group (reused)
        self._animation_group = None
        
        # Apply initial theme
        self._apply_theme()
        
        # Connect to theme changes (UniqueConnection prevents duplicate signals)
        if self.theme_manager:
            try:
                self.theme_manager.theme_changed.connect(
                    self._apply_theme, 
                    Qt.ConnectionType.UniqueConnection
                )
            except Exception:
                pass
    
    def _apply_theme(self):
        """Apply theme-based styling with semi-translucent background"""
        if self.theme_manager:
            try:
                palette = self.theme_manager.get_palette()
                self._bg_color = QColor(palette.get('bg_color', '#252524'))
                self._bg_color.setAlpha(240)
                
                self._text_color = QColor(palette.get('text_color', '#ffffff'))
                
                self._border_color = QColor(palette.get('border_color', '#3f3f3f'))
                self._border_color.setAlpha(240)
                
                self._border_radius = max(4, self.theme_manager.current_theme.get('corner_radius', 6) - 2)
            except Exception:
                self._set_fallback_colors()
        else:
            self._set_fallback_colors()
        
        # Update label text color
        palette = self.palette()
        palette.setColor(self.foregroundRole(), self._text_color)
        self.setPalette(palette)
        self.update()
    
    def _set_fallback_colors(self):
        """Set fallback colors when theme is unavailable"""
        self._bg_color = QColor(45, 45, 48, 220)
        self._text_color = QColor(255, 255, 255)
        self._border_color = QColor(100, 100, 100, 180)
        self._border_radius = 6
    
    # Configuration methods
    def set_animation_type(self, animation_type: TooltipAnimation):
        """Set the animation style (FADE or SLIDE)"""
        self._animation_type = animation_type
    
    def set_show_delay(self, delay_ms: int):
        """Set delay before showing tooltip (milliseconds)"""
        self._show_delay = max(0, delay_ms)
    
    def set_max_width(self, width: int):
        """Set maximum tooltip width (pixels)"""
        self._max_width = max(100, width)
        self.setMaximumWidth(self._max_width)
    
    def paintEvent(self, event):
        """Custom paint event to draw semi-translucent themed background"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get widget rect
        rect = self.rect()
        
        # Draw background with rounded corners
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 
                           self._border_radius, self._border_radius)
        
        # Fill background
        painter.fillPath(path, self._bg_color)
        
        # Draw border
        painter.setPen(QPen(self._border_color, 1))
        painter.drawPath(path)
        
        # Call parent to draw text
        painter.end()
        super().paintEvent(event)
    
    def show_tooltip(
        self, 
        text: str, 
        widget: Optional[QWidget] = None, 
        delay: Optional[int] = None,
        force_direction: Optional[str] = None
    ):
        """
        Show tooltip with given text positioned relative to widget.
        
        Args:
            text: The tooltip text to display
            widget: QWidget to position relative to (required)
            delay: Override default show delay (milliseconds)
            force_direction: Force tooltip direction ("above", "below", "left", "right")
                            If set, skips dynamic positioning for this tooltip
        """
        if not text or not widget:
            self.hide_tooltip()
            return
        
        # Store forced direction for _calculate_position
        self._force_direction = force_direction
        
        # If tooltip showing for same widget with different text, update in-place without animation
        if self.isVisible() and self._target_widget is widget and self.text() != text:
            self.setText(text)
            self.adjustSize()
            # Reposition with new size
            origin = self._get_origin_point()
            final_pos = self._calculate_position(origin)
            self.move(final_pos)
            return
        
        # If tooltip showing different content for different widget, hide and re-show
        if self.isVisible() and self.text() != text:
            self._pending_show = (text, widget, force_direction)
            self._do_hide()
            return
        
        # If same tooltip already visible, do nothing
        if self.isVisible() and self.text() == text:
            return
        
        # Cancel any pending operations
        self._show_timer.stop()
        self._hide_timer.stop()
        
        # Detach old target and attach new one
        if self._target_widget is not widget:
            self._detach_target_listeners()
            self._target_widget = widget
            self._attach_target_listeners(widget)
        
        self.setText(text)
        self.adjustSize()
        
        # Schedule show with delay
        delay_time = delay if delay is not None else self._show_delay
        if delay_time > 0:
            self._show_timer.start(delay_time)
        else:
            self._do_show()
    
    def hide_tooltip(self):
        """Hide the tooltip."""
        self._pending_show = None
        self._show_timer.stop()
        
        if self._hide_delay > 0:
            self._hide_timer.start(self._hide_delay)
        else:
            self._do_hide()

    def _attach_target_listeners(self, widget: Optional[QWidget]):
        """Install event filter and connect destroyed signal on the target widget."""
        if not widget:
            return

        try:
            widget.installEventFilter(self)
            widget.destroyed.connect(self._on_target_destroyed, Qt.ConnectionType.UniqueConnection)
        except Exception:
            pass

    def _detach_target_listeners(self):
        """Remove event filter and disconnect signals from the target widget."""
        if not self._target_widget:
            return
        try:
            self._target_widget.removeEventFilter(self)
            self._target_widget.destroyed.disconnect(self._on_target_destroyed)
        except Exception:
            pass

    def _on_target_destroyed(self, obj=None):
        """Called when the target widget is destroyed; hide tooltip immediately."""
        self._pending_show = None
        self._show_timer.stop()
        self._hide_timer.stop()
        self._do_hide()

    def eventFilter(self, obj, event):
        """Event filter to detect when target widget is hidden/closed."""
        if obj is self._target_widget and event.type() in (QEvent.Hide, QEvent.Close):
            self._pending_show = None
            self._show_timer.stop()
            self._hide_timer.stop()
            self._do_hide()
        return super().eventFilter(obj, event)
    
    def _do_show(self):
        """Show tooltip with animation"""
        # Get origin point
        origin = self._get_origin_point()
        
        # Calculate final position
        final_pos = self._calculate_position(origin)
        
        # Stop any existing animations
        self._stop_animations()
        
        # Create animation group
        self._animation_group = QParallelAnimationGroup(self)
        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation_group.addAnimation(opacity_anim)
        
        # Add position animation for slide
        if self._animation_type == TooltipAnimation.SLIDE:
            start_pos = self._get_slide_start_position(final_pos, origin)
            pos_anim = QPropertyAnimation(self, b"pos", self)
            pos_anim.setDuration(250)
            pos_anim.setStartValue(start_pos)
            pos_anim.setEndValue(final_pos)
            pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._animation_group.addAnimation(pos_anim)
            self.move(start_pos)
        else:
            self.move(final_pos)
        
        self._animation_group.finished.connect(lambda: self.shown.emit())
        self.show()
        self._animation_group.start()
    
    def _do_hide(self):
        """Hide tooltip with animation"""
        if not self.isVisible():
            return
        
        self._stop_animations()
        
        self._animation_group = QParallelAnimationGroup(self)
        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        opacity_anim.setDuration(150)
        opacity_anim.setStartValue(self._opacity_effect.opacity())
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._animation_group.addAnimation(opacity_anim)
        self._animation_group.finished.connect(self._finish_hide)
        self._animation_group.start()
    
    def _finish_hide(self):
        """Complete hide and show pending tooltip if any"""
        self.hide()
        self.hidden.emit()
        self._detach_target_listeners()
        self._target_widget = None
        
        # Show pending tooltip if exists
        if self._pending_show:
            if len(self._pending_show) == 3:
                text, widget, force_dir = self._pending_show
            else:
                text, widget = self._pending_show
                force_dir = None
            self._pending_show = None
            self.show_tooltip(text, widget, delay=0, force_direction=force_dir)
    
    def _stop_animations(self):
        """Stop all animations safely"""
        if self._animation_group:
            try:
                self._animation_group.stop()
            except RuntimeError:
                pass
            self._animation_group = None
    
    def _get_origin_point(self) -> QPoint:
        """Get the origin point for tooltip positioning (widget center)"""
        if self._target_widget:
            widget_rect = self._target_widget.rect()
            center = widget_rect.center()
            return self._target_widget.mapToGlobal(center)
        return QPoint(0, 0)
    
    def _get_widget_bounds(self) -> QRect:
        """Get the global bounding rectangle of the target widget"""
        if self._target_widget:
            widget_rect = self._target_widget.rect()
            top_left = self._target_widget.mapToGlobal(widget_rect.topLeft())
            return QRect(top_left, widget_rect.size())
        return QRect(0, 0, 0, 0)
    
    def _get_window_center(self) -> QPoint:
        """Get the center point of the window"""
        if self._target_widget:
            window = self._target_widget.window()
            if window and window.isVisible():
                window_rect = window.geometry()
                return window_rect.center()
        
        # Fallback to screen center
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            return screen_rect.center()
        
        return QPoint(0, 0)
    
    def _get_boundary_rect(self) -> QRect:
        """Get the boundary rectangle to constrain tooltip within"""
        if self._target_widget:
            window = self._target_widget.window()
            if window and window.isVisible():
                return window.geometry()
        
        # Fallback to screen boundary
        screen = QApplication.primaryScreen()
        if screen:
            return screen.availableGeometry()
        
        return QRect(0, 0, 800, 600)
    
    def _calculate_position(self, origin: QPoint) -> QPoint:
        """
        Calculate tooltip position using a quadrant-based approach.
        Prioritizes vertical placement (Above/Below) based on vertical position in window.
        Falls back to horizontal placement (Left/Right) if vertical doesn't fit.
        
        If _force_direction is set, uses that direction instead of dynamic calculation.
        """
        tooltip_size = self.sizeHint()
        boundary = self._get_boundary_rect()
        window_center = self._get_window_center()
        widget_bounds = self._get_widget_bounds()
        
        # Define candidate positions
        margin = 5
        half_width = tooltip_size.width() // 2
        half_height = tooltip_size.height() // 2
        
        # Candidates map: name -> (position, is_vertical)
        candidates = {
            "above": (QPoint(origin.x() - half_width, widget_bounds.top() - tooltip_size.height() - self._offset), True),
            "below": (QPoint(origin.x() - half_width, widget_bounds.bottom() + self._offset), True),
            "left": (QPoint(widget_bounds.left() - tooltip_size.width() - self._offset, origin.y() - half_height), False),
            "right": (QPoint(widget_bounds.right() + self._offset, origin.y() - half_height), False),
        }

        def check_fit(pos):
            rect = QRect(pos, tooltip_size)
            # Check if fully contained in boundary (with margin)
            return boundary.contains(rect.adjusted(-margin, -margin, margin, margin))
        
        # If forced direction is set, use it directly (skip dynamic positioning)
        if self._force_direction and self._force_direction in candidates:
            best_pos = candidates[self._force_direction][0]
            self._tooltip_direction = self._force_direction
            # Constrain to boundary
            x = max(boundary.left() + margin, 
                    min(best_pos.x(), boundary.right() - tooltip_size.width() - margin))
            y = max(boundary.top() + margin, 
                    min(best_pos.y(), boundary.bottom() - tooltip_size.height() - margin))
            return QPoint(x, y)

        # Decision logic based on quadrants (2 lines: vertical and horizontal)
        # 1. Determine vertical preference
        if origin.y() < window_center.y():
            # Top half -> prefer Below
            primary_v, secondary_v = "below", "above"
        else:
            # Bottom half -> prefer Above
            primary_v, secondary_v = "above", "below"
            
        # 2. Determine horizontal preference
        if origin.x() < window_center.x():
            # Left half -> prefer Right
            primary_h, secondary_h = "right", "left"
        else:
            # Right half -> prefer Left
            primary_h, secondary_h = "left", "right"

        # 3. Try to find a fitting position in order of preference
        # Order: Primary Vertical -> Secondary Vertical -> Primary Horizontal -> Secondary Horizontal
        preference_order = [primary_v, secondary_v, primary_h, secondary_h]
        
        best_pos = candidates[primary_v][0] # Default to primary vertical
        self._tooltip_direction = primary_v
        
        found_fit = False
        for direction in preference_order:
            pos, is_vertical = candidates[direction]
            if check_fit(pos):
                best_pos = pos
                self._tooltip_direction = direction
                found_fit = True
                break
        
        # Constrain to boundary (clamping)
        x = max(boundary.left() + margin, 
                min(best_pos.x(), boundary.right() - tooltip_size.width() - margin))
        y = max(boundary.top() + margin, 
                min(best_pos.y(), boundary.bottom() - tooltip_size.height() - margin))
        
        return QPoint(x, y)
    
    def _get_slide_start_position(self, final_pos: QPoint, origin: QPoint) -> QPoint:
        """Get starting position for slide animation based on tooltip direction."""
        slide_distance = 20
        direction = self._tooltip_direction
        
        offsets = {
            "above": (0, slide_distance),
            "below": (0, -slide_distance),
            "left": (slide_distance, 0),
            "right": (-slide_distance, 0)
        }
        
        dx, dy = offsets.get(direction, (0, -slide_distance))
        return QPoint(final_pos.x() + dx, final_pos.y() + dy)


# Global tooltip manager for convenient access
_global_tooltip_instance: Optional[CustomTooltip] = None


def get_tooltip_manager(theme_manager=None) -> CustomTooltip:
    """
    Get or create the global tooltip instance.
    
    Args:
        theme_manager: Optional theme manager for theme-sensitive styling
        
    Returns:
        CustomTooltip instance
    """
    global _global_tooltip_instance
    
    if _global_tooltip_instance is None:
        _global_tooltip_instance = CustomTooltip(theme_manager=theme_manager)
    elif theme_manager and not _global_tooltip_instance.theme_manager:
        # Update theme manager if not set
        _global_tooltip_instance.theme_manager = theme_manager
        _global_tooltip_instance._apply_theme()
        try:
            theme_manager.theme_changed.connect(
                _global_tooltip_instance._apply_theme, 
                Qt.ConnectionType.UniqueConnection
            )
        except Exception:
            pass
    
    return _global_tooltip_instance


def show_tooltip(
    text: str,
    widget: QWidget,
    animation: TooltipAnimation = TooltipAnimation.FADE,
    delay: Optional[int] = None,
    theme_manager=None,
    force_direction: Optional[str] = None
):
    """
    Convenience function to show a tooltip positioned relative to a widget.
    
    Args:
        text: The tooltip text to display
        widget: QWidget to position relative to
        animation: Animation style (FADE or SLIDE)
        delay: Override default show delay (milliseconds)
        theme_manager: Optional theme manager for styling
        force_direction: Force tooltip direction ("above", "below", "left", "right")
    """
    tooltip = get_tooltip_manager(theme_manager)
    tooltip.set_animation_type(animation)
    tooltip.show_tooltip(text, widget, delay, force_direction=force_direction)


def hide_tooltip():
    """Convenience function to hide the tooltip."""
    global _global_tooltip_instance
    if _global_tooltip_instance:
        _global_tooltip_instance.hide_tooltip()
