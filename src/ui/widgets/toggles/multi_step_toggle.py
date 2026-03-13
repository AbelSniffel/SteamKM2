from PySide6.QtWidgets import QAbstractButton, QSizePolicy
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, QSize, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QBrush, QCursor, QFontMetrics, QPen, QFont
from src.ui.config import ELEMENT_HEIGHT, WIDGET_SPACING


class MultiStepToggle(QAbstractButton):
    """A multi-position toggle switch with dynamic handle sizing and smooth animations.
    
    This toggle supports any number of positions (steps) and automatically sizes itself
    based on the text labels. The handle slides smoothly between positions with rounded
    corners and proper visual feedback.
    
    Features:
    - Draggable handle: Hold and drag to slide between positions with live updates
    - Click to cycle: Quick click on handle cycles to next option (loops to first after last)
    - Snaps to closest option when released after dragging
    - Visual feedback: Hover effect on handle, smooth animations
    - Works with any number of options (minimum 2)
    
    Signals:
        position_changed(int): Emitted when the toggle position changes (0-based index)
    """
    
    position_changed = Signal(int)
    
    def __init__(self, options: list[str], parent=None, current_index: int = 0, 
                 animation_duration: int = 200, theme_manager=None):
        """Initialize the multi-step toggle.
        
        Args:
            options: List of text labels for each position
            parent: Parent widget
            current_index: Initial selected position (0-based)
            animation_duration: Animation duration in milliseconds
            theme_manager: Optional theme manager for color management
        """
        super().__init__(parent)
        
        if not options or len(options) < 2:
            raise ValueError("MultiStepToggle requires at least 2 options")
        
        self._options = options
        self._current_index = current_index
        self._handle_position = float(current_index)  # Smooth interpolation value
        
        # Dragging state
        self._is_dragging = False
        self._drag_start_pos = None
        self._drag_start_handle_pos = None
        self._is_hovering_handle = False
        
        # Animation setup
        self._anim = QPropertyAnimation(self, b"handle_position")
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.setDuration(animation_duration)
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        
        # Theme management
        self.theme_manager = theme_manager or self._get_theme_manager_from_parent(parent)
        if self.theme_manager and hasattr(self.theme_manager, 'theme_changed'):
            try:
                self.theme_manager.theme_changed.connect(
                    self._apply_theme, 
                    Qt.ConnectionType.UniqueConnection
                )
            except Exception:
                pass
        
        # Colors
        self._bg_color = QColor('#394f8c')
        self._handle_color = QColor('#78a0dc')
        
        # Apply theme colors if available
        self._apply_theme()
        
        # UI setup
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        
        # Spacing/margin configuration for the option items
        # Reduced spacing between items to make the multi-selection tighter
        self._item_spacing = -3
        self._margin = 2

        # Calculate sizes
        self._calculate_sizes()
        
        # Set fixed height, but let width be dynamic
        self.setFixedHeight(ELEMENT_HEIGHT)
    
    def _get_theme_manager_from_parent(self, parent):
        """Try to get theme manager from parent hierarchy."""
        current = parent
        while current:
            if hasattr(current, 'theme_manager'):
                return current.theme_manager
            current = current.parent() if hasattr(current, 'parent') else None
        return None
    
    def _apply_theme(self):
        """Apply theme colors from theme manager."""
        if self.theme_manager:
            try:
                palette = self.theme_manager.get_palette()
                self._bg_color = QColor(palette.get('toggle_bg_off', '#394f8c'))
                self._handle_color = QColor(palette.get('toggle_handle_color', '#78a0dc'))
                self.update()
            except Exception:
                pass
    
    def _calculate_sizes(self):
        """Calculate the required sizes for the toggle based on text content."""
        fm = QFontMetrics(self.font())
        padding = 12  # Horizontal padding inside each handle position
        
        # Calculate width needed for each option's text
        self._option_widths = [fm.horizontalAdvance(opt) + padding * 2 for opt in self._options]
        
        # Total width includes margins on both sides, option widths, and spacing between them
        self._total_width = (self._margin * 2 + sum(self._option_widths) + 
                            self._item_spacing * (len(self._options) - 1))
        self.setFixedWidth(self._total_width)
    
    def _get_x_positions(self):
        """Cache and return x positions for each option."""
        if not hasattr(self, '_cached_x_positions'):
            self._cached_x_positions = []
            current_x = self._margin
            for width in self._option_widths:
                self._cached_x_positions.append(current_x)
                current_x += width + self._item_spacing
        return self._cached_x_positions
    
    def _invalidate_position_cache(self):
        """Clear cached x positions when options change."""
        if hasattr(self, '_cached_x_positions'):
            delattr(self, '_cached_x_positions')
    
    def _get_handle_rect(self, position: float):
        """Get the handle rectangle for a given interpolated position.
        
        Args:
            position: Float position (e.g., 0.0, 0.5, 1.0, 2.0, etc.)
        
        Returns:
            Tuple of (x, y, width, height) for the handle
        """
        handle_h = self.height() - self._margin * 2
        
        # Determine which two positions we're interpolating between
        index = min(int(position), len(self._options) - 1)
        fraction = position - index if index < len(self._options) - 1 else 0.0
        
        # Get cached x positions
        x_positions = self._get_x_positions()
        
        # Interpolate position and width
        x = x_positions[index]
        width = self._option_widths[index]
        
        if fraction > 0.0 and index < len(self._options) - 1:
            next_x = x_positions[index + 1]
            next_width = self._option_widths[index + 1]
            
            x += (next_x - x) * fraction
            width += (next_width - width) * fraction
        
        return x, self._margin, width, handle_h
    
    def paintEvent(self, event):
        """Paint the multi-step toggle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        
        h = self.height()
        radius = h / 2
        
        # Draw rounded background
        painter.setBrush(QBrush(self._bg_color))
        painter.drawRoundedRect(0, 0, self.width(), h, radius, radius)
        
        # Draw handle with hover effect
        handle_x, handle_y, handle_w, handle_h = self._get_handle_rect(self._handle_position)
        handle_color = self._handle_color.lighter(110) if self._is_hovering_handle else self._handle_color
        painter.setBrush(QBrush(handle_color))
        painter.drawRoundedRect(int(handle_x), int(handle_y), int(handle_w), 
                              int(handle_h), handle_h / 2, handle_h / 2)
        
        # Draw text labels
        painter.setPen(self.palette().text().color())
        base_font = self.font()
        bold_font = QFont(base_font)
        bold_font.setBold(True)
        
        fm_normal = QFontMetrics(base_font)
        fm_bold = QFontMetrics(bold_font)
        text_baseline = (h + fm_normal.height()) / 2 - fm_normal.descent()
        
        # Get cached x positions
        x_positions = self._get_x_positions()

        for i, option in enumerate(self._options):
            # Use bold font for active/near-active position
            is_active = abs(self._handle_position - i) < 0.5
            if is_active:
                painter.setFont(bold_font)
                text_width = fm_bold.horizontalAdvance(option)
            else:
                painter.setFont(base_font)
                text_width = fm_normal.horizontalAdvance(option)
            
            # Center text in this option's space
            text_x = x_positions[i] + (self._option_widths[i] - text_width) / 2
            painter.drawText(int(text_x), int(text_baseline), option)
    
    def mousePressEvent(self, event):
        """Handle mouse press - start dragging or prepare for click-to-cycle."""
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().x()
            handle_x, _, handle_w, _ = self._get_handle_rect(self._handle_position)
            
            if handle_x <= x <= handle_x + handle_w:
                # Clicking on handle - start dragging
                self._is_dragging = True
                self._drag_start_pos = x
                self._drag_start_handle_pos = self._handle_position
                self._anim.stop()
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            else:
                # Clicking outside handle - jump to that position
                x_positions = self._get_x_positions()
                for i, (x_pos, width) in enumerate(zip(x_positions, self._option_widths)):
                    if x_pos <= x < x_pos + width:
                        self.set_position(i, animated=True)
                        break
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse movement - drag the handle or update hover state."""
        x = event.position().x()
        
        if self._is_dragging:
            # Convert drag delta to position units
            position_unit_width = self._total_width / len(self._options)
            delta_position = (x - self._drag_start_pos) / position_unit_width
            new_position = max(0.0, min(float(len(self._options) - 1), 
                                       self._drag_start_handle_pos + delta_position))
            
            self._handle_position = new_position
            
            # Emit signal if position changed
            closest_index = round(new_position)
            if closest_index != self._current_index:
                self._current_index = closest_index
                self.position_changed.emit(closest_index)
            
            self.update()
        else:
            # Update hover state
            handle_x, _, handle_w, _ = self._get_handle_rect(self._handle_position)
            was_hovering = self._is_hovering_handle
            self._is_hovering_handle = handle_x <= x <= handle_x + handle_w
            
            # Update cursor and repaint if hover state changed
            if self._is_hovering_handle != was_hovering:
                cursor = Qt.CursorShape.OpenHandCursor if self._is_hovering_handle else Qt.CursorShape.PointingHandCursor
                self.setCursor(QCursor(cursor))
                self.update()
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release - snap to closest option or cycle on click."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            
            # Check if this was a click (minimal movement) or a drag
            drag_distance = abs(event.position().x() - self._drag_start_pos)
            
            if drag_distance < 5:  # Click threshold in pixels
                # Click - cycle to next option
                new_index = (self._current_index + 1) % len(self._options)
                self.set_position(new_index, animated=True)
            else:
                # Drag - snap to closest option
                closest_index = max(0, min(len(self._options) - 1, round(self._handle_position)))
                self._current_index = closest_index
                
                self._anim.stop()
                self._anim.setStartValue(self._handle_position)
                self._anim.setEndValue(float(closest_index))
                self._anim.start()
                
                self.position_changed.emit(closest_index)
        
        super().mouseReleaseEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leaving the widget - clear hover state."""
        if self._is_hovering_handle:
            self._is_hovering_handle = False
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.update()
        super().leaveEvent(event)
    
    def set_position(self, index: int, animated: bool = True):
        """Set the current position of the toggle.
        
        Args:
            index: The position index (0-based)
            animated: Whether to animate the transition
        """
        if not (0 <= index < len(self._options)) or index == self._current_index:
            return
        
        self._current_index = index
        
        if animated:
            self._anim.stop()
            self._anim.setStartValue(self._handle_position)
            self._anim.setEndValue(float(index))
            self._anim.start()
        else:
            self._handle_position = float(index)
            self.update()
        
        self.position_changed.emit(index)
    
    def get_position(self) -> int:
        """Get the current position index."""
        return self._current_index
    
    def get_current_option(self) -> str:
        """Get the text of the currently selected option."""
        return self._options[self._current_index]
    
    def set_options(self, options: list[str], current_index: int = 0):
        """Update the options list and recalculate sizes.
        
        Args:
            options: New list of option labels
            current_index: New current position (defaults to 0)
        """
        if not options or len(options) < 2:
            raise ValueError("MultiStepToggle requires at least 2 options")
        
        self._options = options
        self._current_index = current_index
        self._handle_position = float(current_index)
        
        self._invalidate_position_cache()
        self._calculate_sizes()
        self.update()
        self.position_changed.emit(current_index)
    
    # Property for smooth animation
    def get_handle_position(self) -> float:
        return self._handle_position
    
    def set_handle_position(self, value: float):
        self._handle_position = value
        self.update()
    
    handle_position = Property(float, get_handle_position, set_handle_position)
    
    def sizeHint(self) -> QSize:
        """Provide size hint for layout management."""
        size = QSize(self._total_width, ELEMENT_HEIGHT)
        return size
    
    minimumSizeHint = sizeHint  # Both return the same fixed size
