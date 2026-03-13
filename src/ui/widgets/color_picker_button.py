"""
Color Picker Button Widget

A rounded rectangular button widget for color selection with link functionality.
Features include:
- Displays color preview with hex code
- Click to open color picker dialog
- Link function to pair two color pickers with a swap button
- Swap button overlays between linked pickers
- Clean, modern design with hover/press states
"""

from PySide6.QtWidgets import QWidget, QColorDialog, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QFont, QFontMetrics, QCursor, QPen
)
from src.ui.config import ELEMENT_HEIGHT, WIDGET_SPACING
from src.core.theme import get_contrasting_text_color
from src.ui.widgets.tooltip import show_tooltip, hide_tooltip


class ColorPickerButton(QWidget):
    """
    A rounded rectangular button for color selection.
    Displays color preview with hex code and opens color picker on click.
    """
    
    # Signals
    color_changed = Signal(str)  # hex_color
    
    def __init__(self, initial_color="#ff7f3f", label="", parent=None, theme_manager=None):
        super().__init__(parent)
        self.color = initial_color
        self.label = label
        self.theme_manager = theme_manager
        
        # Styling constants
        self._border_radius = 8  # Rounded corners
        self._padding = 1
        self._font = QFont("Segoe UI", 8, QFont.Bold)
        self._label_font = QFont("Segoe UI", 8)
        
        # UI state
        self.is_hovered = False
        self.is_pressed = False
        self.linked_button = None  # Reference to linked button
        self.swap_button = None  # Reference to swap button overlay
        self._base_width = None  # Store base width for calculations
        
        # Setup UI
        self._setup_ui()
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
    
    def _setup_ui(self):
        """Setup the widget layout and size"""
        self.setFixedHeight(34)  # Slightly taller than standard ELEMENT_HEIGHT for better visibility
        
        # Calculate base width based on text
        metrics = QFontMetrics(self._font)
        label_metrics = QFontMetrics(self._label_font)
        
        # Width to fit hex code (#FFFFFFFF) plus padding
        hex_width = metrics.horizontalAdvance("#FFFFFFFF") + self._padding * 2
        label_width = label_metrics.horizontalAdvance(self.label) + self._padding * 2 if self.label else 0
        
        self._base_width = max(hex_width, label_width, 120)  # Minimum 120px width for each button
        
        self._update_width()
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        # Tooltip
        self.setToolTip("Click to change color")
    
    def _update_width(self):
        """Update the button width based on linked state"""
        if self._base_width is None:
            return
        
        # If not linked, make width equal to two linked buttons combined
        width = self._base_width * 2 if self.linked_button is None else self._base_width
        self.setFixedWidth(width)
    
    def set_color(self, color_hex):
        """Set the button color"""
        self.color = color_hex
        self.update()
    
    def get_color(self):
        """Get the current color"""
        return self.color
    
    def set_label(self, label):
        """Set the button label"""
        self.label = label
        self._setup_ui()
        self.update()
    
    def link_to(self, other_button, theme_manager=None):
        """Link this button to another button for swapping colors.
        
        Args:
            other_button: The ColorPickerButton to link with
            theme_manager: Optional theme manager for swap button theming
        """
        if self.linked_button == other_button:
            return  # Already linked
        
        # Remove existing swap button if any
        if self.swap_button:
            self.swap_button.deleteLater()
            self.swap_button = None
        
        # Link buttons
        self.linked_button = other_button
        other_button.linked_button = self
        
        # Update widths for linked state
        self._update_width()
        other_button._update_width()
        
        # Get theme_manager from arguments or from either button
        tm = theme_manager or self.theme_manager or other_button.theme_manager
        
        # Create swap button overlay if parent exists
        if parent := self.parent():
            self.swap_button = SwapButton(self, other_button, parent, theme_manager=tm)
            other_button.swap_button = self.swap_button
            self.swap_button.show()
            self.swap_button.raise_()
    
    def unlink(self):
        """Unlink from any linked button"""
        if self.swap_button:
            self.swap_button.deleteLater()
            self.swap_button = None
        
        if other := self.linked_button:
            other.swap_button = None
            other.linked_button = None
            self.linked_button = None
            
            # Update widths for unlinked state
            self._update_width()
            other._update_width()
    
    def enterEvent(self, event):
        """Handle mouse enter"""
        self.is_hovered = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave"""
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press"""
        if event.button() == Qt.LeftButton:
            self.is_pressed = True
            self.update()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release - open color picker"""
        if event.button() == Qt.LeftButton and self.is_pressed:
            self.is_pressed = False
            if self.rect().contains(event.pos()):
                self._pick_color()
            self.update()
        super().mouseReleaseEvent(event)
    
    def _pick_color(self):
        """Open color picker dialog"""
        title = f"Pick Color - {self.label}" if self.label else "Pick Color"
        color = QColorDialog.getColor(QColor(self.color), self, title)
        
        if color.isValid():
            hex_color = color.name()
            self.color = hex_color
            self.color_changed.emit(hex_color)
            self.update()
    
    def paintEvent(self, event):
        """Paint the color picker button"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        bg_color = QColor(self.color)
        
        # Apply state-based color adjustment
        if self.is_pressed:
            bg_color = bg_color.darker(110)
        elif self.is_hovered:
            bg_color = bg_color.lighter(110)
        
        # Draw background with custom corner radii for linked buttons
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        
        if self.linked_button:
            # Determine which corners to keep rounded
            # If this is the left button, square the right corners
            # If this is the right button, square the left corners
            path = QPainterPath()
            is_left_button = self.linked_button.x() > self.x()
            
            if is_left_button:
                # Left button - square top-right and bottom-right corners
                path.moveTo(rect.topLeft() + QPoint(self._border_radius, 0))
                path.arcTo(rect.x(), rect.y(), self._border_radius * 2, self._border_radius * 2, 90, 90)  # Top-left
                path.lineTo(rect.x(), rect.bottom() - self._border_radius)
                path.arcTo(rect.x(), rect.bottom() - self._border_radius * 2, self._border_radius * 2, self._border_radius * 2, 180, 90)  # Bottom-left
                path.lineTo(rect.right(), rect.bottom())  # Square bottom-right
                path.lineTo(rect.right(), rect.top())  # Square top-right
                path.closeSubpath()
            else:
                # Right button - square top-left and bottom-left corners
                path.moveTo(rect.left(), rect.top())  # Square top-left
                path.lineTo(rect.right() - self._border_radius, rect.top())
                path.arcTo(rect.right() - self._border_radius * 2, rect.y(), self._border_radius * 2, self._border_radius * 2, 90, -90)  # Top-right
                path.lineTo(rect.right(), rect.bottom() - self._border_radius)
                path.arcTo(rect.right() - self._border_radius * 2, rect.bottom() - self._border_radius * 2, self._border_radius * 2, self._border_radius * 2, 0, -90)  # Bottom-right
                path.lineTo(rect.left(), rect.bottom())  # Square bottom-left
                path.closeSubpath()
            
            painter.drawPath(path)
        else:
            # Not linked - use normal rounded rect
            painter.drawRoundedRect(rect, self._border_radius, self._border_radius)
        
        # Setup text color once
        text_color = QColor(get_contrasting_text_color(self.color))
        painter.setPen(text_color)
        hex_upper = self.color.upper()
        
        # Draw label and hex code
        if self.label:
            painter.setFont(self._label_font)
            painter.drawText(rect.x(), rect.y() + 4, rect.width(), rect.height() // 3, Qt.AlignCenter, self.label)
            painter.setFont(self._font)
            painter.drawText(rect.x(), rect.y() + rect.height() // 3, rect.width(), 2 * rect.height() // 3 - 4, Qt.AlignCenter, hex_upper)
        else:
            painter.setFont(self._font)
            painter.drawText(rect, Qt.AlignCenter, hex_upper)
        
        # Draw border if hovered or pressed
        if self.is_hovered or self.is_pressed:
            painter.setPen(QColor(255, 255, 255, 150 if self.is_pressed else 100))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            adjusted_rect = rect.adjusted(1, 1, -1, -1)
            if self.linked_button:
                # Use custom path for border on linked buttons
                path = QPainterPath()
                is_left_button = self.linked_button.x() > self.x()
                r = self._border_radius
                
                if is_left_button:
                    path.moveTo(adjusted_rect.topLeft() + QPoint(r, 0))
                    path.arcTo(adjusted_rect.x(), adjusted_rect.y(), r * 2, r * 2, 90, 90)
                    path.lineTo(adjusted_rect.x(), adjusted_rect.bottom() - r)
                    path.arcTo(adjusted_rect.x(), adjusted_rect.bottom() - r * 2, r * 2, r * 2, 180, 90)
                    path.lineTo(adjusted_rect.right(), adjusted_rect.bottom())
                    path.lineTo(adjusted_rect.right(), adjusted_rect.top())
                    path.closeSubpath()
                else:
                    path.moveTo(adjusted_rect.left(), adjusted_rect.top())
                    path.lineTo(adjusted_rect.right() - r, adjusted_rect.top())
                    path.arcTo(adjusted_rect.right() - r * 2, adjusted_rect.y(), r * 2, r * 2, 90, -90)
                    path.lineTo(adjusted_rect.right(), adjusted_rect.bottom() - r)
                    path.arcTo(adjusted_rect.right() - r * 2, adjusted_rect.bottom() - r * 2, r * 2, r * 2, 0, -90)
                    path.lineTo(adjusted_rect.left(), adjusted_rect.bottom())
                    path.closeSubpath()
                
                painter.drawPath(path)
            else:
                painter.drawRoundedRect(adjusted_rect, self._border_radius, self._border_radius)
    
    def sizeHint(self):
        """Provide size hint for layout management"""
        return QSize(self.minimumWidth(), 36)
    
    def minimumSizeHint(self):
        """Provide minimum size hint"""
        return self.sizeHint()


class SwapButton(QWidget):
    """
    An overlay button that appears between two linked ColorPickerButtons
    to allow swapping their colors. The button covers both pickers equally.
    Supports theming when a theme_manager is provided.
    """
    
    # Signal
    colors_swapped = Signal()
    
    def __init__(self, button1, button2, parent=None, theme_manager=None):
        super().__init__(parent)
        self.button1 = button1
        self.button2 = button2
        self.theme_manager = theme_manager
        
        # Styling
        self._size = 26  # Button size
        self._icon_font = QFont("Segoe UI", 12, QFont.Bold)
        
        # Default colors (used when no theme_manager)
        self._default_bg_color = QColor("#2d1b1b")
        self._default_hover_color = QColor("#ff7f3f")
        self._default_pressed_color = QColor("#ff9f3f")
        
        # Current colors (updated from theme)
        self._bg_color = self._default_bg_color
        self._hover_color = self._default_hover_color
        self._pressed_color = self._default_pressed_color

        # Foreground/border colors (updated from theme)
        self._fg_color = QColor(255, 255, 255)
        
        # UI state
        self.is_hovered = False
        self.is_pressed = False
        
        # Setup
        self.setFixedSize(self._size, self._size)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setToolTip("Swap colors")
        
        # Connect to theme changes
        if self.theme_manager:
            self.theme_manager.theme_changed.connect(self._update_theme_colors)
            self._update_theme_colors()
        
        # Position the button
        self._update_position()
    
    def _update_theme_colors(self):
        """Update colors from theme manager."""
        if not self.theme_manager:
            return

        theme = self.theme_manager.current_theme
        # Use theme colors
        bg = theme.get('base_background', '#2d1b1b')
        primary = theme.get('base_primary', '#ff7f3f')
        accent = theme.get('base_accent', '#ff9f3f')

        self._bg_color = QColor(bg)
        self._hover_color = QColor(primary)
        self._pressed_color = QColor(accent)

        # Use palette text color for icon/border so it stays visible on light themes
        try:
            palette = self.theme_manager.get_palette() if hasattr(self.theme_manager, 'get_palette') else {}
            self._fg_color = QColor(palette.get('text_color', '#ffffff'))
        except Exception:
            self._fg_color = QColor(255, 255, 255)
        
        self.update()
    
    def set_theme_manager(self, theme_manager):
        """Set or update the theme manager for dynamic theming."""
        # Disconnect from old theme manager
        if self.theme_manager:
            try:
                self.theme_manager.theme_changed.disconnect(self._update_theme_colors)
            except Exception:
                pass
        
        self.theme_manager = theme_manager
        
        if self.theme_manager:
            self.theme_manager.theme_changed.connect(self._update_theme_colors)
            self._update_theme_colors()
    
    def _update_position(self):
        """Update the button position to be centered between the two color pickers"""
        if not self.button1 or not self.button2:
            return
        
        # Convert button positions to parent coordinates
        parent = self.parent()
        button1_pos = parent.mapFromGlobal(self.button1.mapToGlobal(QPoint(0, 0)))
        button2_pos = parent.mapFromGlobal(self.button2.mapToGlobal(QPoint(0, 0)))
        
        # Calculate center between buttons
        center_x = (button1_pos.x() + self.button1.width() + button2_pos.x()) // 2
        center_y = button1_pos.y() + self.button1.height() // 2
        
        # Position the swap button centered
        self.move(center_x - self._size // 2, center_y - self._size // 2)
    
    def enterEvent(self, event):
        """Handle mouse enter"""
        self.is_hovered = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave"""
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press"""
        if event.button() == Qt.LeftButton:
            self.is_pressed = True
            self.update()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release - swap colors"""
        if event.button() == Qt.LeftButton and self.is_pressed:
            self.is_pressed = False
            if self.rect().contains(event.pos()):
                self._swap_colors()
            self.update()
        super().mouseReleaseEvent(event)
    
    def _swap_colors(self):
        """Swap the colors of the two linked buttons"""
        if not self.button1 or not self.button2:
            return
        
        # Swap colors
        color1, color2 = self.button1.get_color(), self.button2.get_color()
        self.button1.set_color(color2)
        self.button2.set_color(color1)
        
        # Emit signals
        self.button1.color_changed.emit(color2)
        self.button2.color_changed.emit(color1)
        self.colors_swapped.emit()
    
    def paintEvent(self, event):
        """Paint the swap button"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        
        # Determine colors based on state
        bg_color = self._pressed_color if self.is_pressed else (self._hover_color if self.is_hovered else self._bg_color)
        border_alpha = 160 if self.is_hovered else 110
        
        # Draw circular button background and border inset by half the pen
        border_color = QColor(self._fg_color)
        border_color.setAlpha(border_alpha)
        pen = QPen(border_color, 2)
        half_pen = pen.width() // 2

        # Inset the rect so the pen stroke doesn't get clipped at widget edges
        draw_rect = rect.adjusted(half_pen, half_pen, -half_pen, -half_pen)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(draw_rect)

        # Draw white border for differentiation using inset rect
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(draw_rect)
        
        # Draw swap icon - adjust rect upward slightly for better visual centering
        # The swap arrows icon has visual weight lower than center, so we compensate
        painter.setFont(self._icon_font)
        painter.setPen(self._fg_color)
        icon_rect = rect.adjusted(0, -1, 0, 0)  # Shift icon up by 2px for visual balance
        painter.drawText(icon_rect, Qt.AlignCenter, "⇄")
    

class LinkedColorPickerPair(QWidget):
    """
    A convenience widget that creates two linked color picker buttons
    with a swap button between them. Supports theming when a theme_manager
    is provided for the swap button.
    """
    
    # Signals
    color1_changed = Signal(str)
    color2_changed = Signal(str)
    colors_swapped = Signal()
    
    def __init__(self, color1="#ff7f3f", color2="#2d1b1b", 
                 label1="Primary", label2="Accent", parent=None, theme_manager=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        
        # Create the two buttons with theme_manager
        self.button1 = ColorPickerButton(color1, label1, self, theme_manager=theme_manager)
        self.button2 = ColorPickerButton(color2, label2, self, theme_manager=theme_manager)
        
        # Link the buttons first (this updates their widths and creates swap button with theme)
        self.button1.link_to(self.button2, theme_manager=theme_manager)
        
        # Setup layout after linking
        self._setup_ui()
        
        # Connect signals
        self.button1.color_changed.connect(self.color1_changed.emit)
        self.button2.color_changed.connect(self.color2_changed.emit)
        if self.button1.swap_button:
            self.button1.swap_button.colors_swapped.connect(self.colors_swapped.emit)
    
    def _setup_ui(self):
        """Setup the widget layout"""
        self.setFixedHeight(36)
        
        # Calculate width: button1 + button2 (buttons touch).
        total_width = self.button1.width() + self.button2.width()
        self.setMinimumWidth(total_width)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        
        # Position buttons directly adjacent with no gap
        self.button1.move(0, 0)
        self.button2.move(self.button1.width(), 0)
    
    def get_colors(self):
        """Get both colors as a tuple (color1, color2)"""
        return (self.button1.get_color(), self.button2.get_color())
    
    def set_colors(self, color1, color2):
        """Set both colors"""
        self.button1.set_color(color1)
        self.button2.set_color(color2)
    
    def resizeEvent(self, event):
        """Handle resize to reposition swap button"""
        super().resizeEvent(event)
        if self.button1.swap_button:
            self.button1.swap_button._update_position()
