"""
Gradient Color Picker Widget

A pill-shaped gradient color customization bar that displays a static preview
of the gradient with color codes visible on both ends. Features include:
- Reflects the current gradient animation pattern (without animation)
- Displays hex color codes on both ends
- Color text positions adjust based on animation type
- Click on colors to open color picker
- Swap button to easily switch colors
- Sync button to sync gradient colors to theme colors
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QColorDialog, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize
from PySide6.QtGui import (
    QPainter, QLinearGradient, QColor, QPainterPath, 
    QFont, QFontMetrics, QCursor
)
from src.ui.config import ELEMENT_HEIGHT, WIDGET_SPACING
from src.core.theme import get_contrasting_text_color
from src.ui.widgets.tooltip import show_tooltip, hide_tooltip


class GradientColorPicker(QWidget):
    """
    A long pill-shaped widget for gradient color customization.
    Shows a static preview of the gradient pattern based on the selected animation.
    """
    
    # Signals
    color_changed = Signal(str, str)  # (color_key, hex_color)
    colors_swapped = Signal()
    colors_synced = Signal()
    
    def __init__(self, theme_manager, settings_manager, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.settings_manager = settings_manager
        
        # Current colors
        self.color1 = self._get_gradient_color('gradient_color1')
        self.color2 = self._get_gradient_color('gradient_color2')
        
        # Current animation type
        self.animation_type = self.settings_manager.get('gradient_animation', 'scroll')
        
        # Styling constants matching multi-step toggle
        self._margin = 2  # Same as multi-step toggle
        self._handle_spacing = WIDGET_SPACING  # Gap between elements
        self._cached_total_width = None
        self._handle_padding = 16
        self._handle_font = QFont("Segoe UI", 9)
        self._fixed_handle_width = self._compute_fixed_handle_width()
        
        # UI state
        self.hover_zone = None  # 'color1', 'color2', 'swap', 'sync', None
        self.pressed_zone = None
        
        # Setup UI
        self._setup_ui()
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        
        # Tooltips for individual zones (shown on hover)
        # Only keep button tooltips here; color tooltips are decided by subzone (left/center/right)
        self._tooltips = {
            'swap': 'Swap the two gradient colors',
            'sync': 'Sync gradient colors to the current theme'
        }
        # Clear widget-level tooltip to avoid confusion
        self.setToolTip("")
    
    def _setup_ui(self):
        """Setup the widget layout and size"""
        # Use same height as multi-step toggle
        self.setFixedHeight(ELEMENT_HEIGHT)
        # Dynamic width - will be calculated based on content
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._calculate_required_width()
    
    def _get_gradient_color(self, key):
        """Get gradient color from theme, with fallback to base colors"""
        theme = self.theme_manager.current_theme
        fallback_key = 'base_primary' if key == 'gradient_color1' else 'base_accent'
        fallback_default = '#ff00ff' if key == 'gradient_color1' else '#00ffff'
        return theme.get(key, theme.get(fallback_key, fallback_default))
    
    def refresh_colors(self):
        """Refresh colors from theme"""
        new_color1 = self._get_gradient_color('gradient_color1')
        new_color2 = self._get_gradient_color('gradient_color2')

        colors_changed = False
        if new_color1 != self.color1:
            self.color1 = new_color1
            colors_changed = True
        if new_color2 != self.color2:
            self.color2 = new_color2
            colors_changed = True

        if colors_changed:
            self._calculate_required_width()

        # Always repaint so palette-dependent elements (e.g., buttons) stay in sync
        self.update()
    
    def set_animation_type(self, animation_type):
        """Update the animation type to adjust gradient pattern and text positions"""
        self.animation_type = animation_type
        self._calculate_required_width()
        self.update()
    
    def _compute_fixed_handle_width(self):
        """Compute a stable handle width that fits any hex color (#AARRGGBB)."""
        metrics = QFontMetrics(self._handle_font)
        return metrics.horizontalAdvance("#FFFFFFFF") + self._handle_padding * 2

    def _calculate_handle_widths(self):
        """Return consistent handle widths to avoid layout churn on theme changes."""
        return self._fixed_handle_width, self._fixed_handle_width
    
    def _calculate_required_width(self):
        """Calculate and set the minimum width needed for all elements"""
        handle_h = ELEMENT_HEIGHT - self._margin * 2
        handle_w1, handle_w2 = self._calculate_handle_widths()
        
        # Calculate gradient pill width
        if self._uses_three_text_layout():
            gradient_pill_width = self._margin * 2 + handle_w1 * 2 + handle_w2 + self._handle_spacing * 2
        else:
            gradient_pill_width = self._margin * 2 + handle_w1 + handle_w2 + self._handle_spacing
        
        # Button pill width (constant)
        button_pill_width = self._margin * 2 + handle_h * 2 + self._handle_spacing
        
        # Total width
        total_width = int(gradient_pill_width + WIDGET_SPACING + button_pill_width)

        if self._cached_total_width != total_width:
            self._cached_total_width = total_width
            self.setMinimumWidth(total_width)
            self.setMaximumWidth(total_width)
            self.updateGeometry()

        return total_width
    
    def _get_gradient_stops(self, rect):
        """
        Get gradient stops based on animation type.
        Returns list of (position, color) tuples for QLinearGradient.
        Position is 0.0 to 1.0
        """
        c1 = QColor(self.color1)
        c2 = QColor(self.color2)
        
        # Map animation types to gradient patterns
        # Patterns reuse color objects instead of creating duplicates
        patterns = {
            'scroll': [(0.0, c1), (0.5, c2), (1.0, c1)],
            'pulse': [(0.0, c2), (0.5, c1), (1.0, c2)],
            'scanner': [(0.0, c2), (0.4, c2), (0.5, c1), (0.6, c2), (1.0, c2)],
            'heart': [(0.0, c2), (0.5, c1), (1.0, c2)]
        }
        
        return patterns.get(self.animation_type, [(0.0, c1), (1.0, c2)])
    
    def _uses_three_text_layout(self):
        """Check if current animation uses 3 text boxes (pulse/heart) or 2 (others)"""
        return self.animation_type in ('pulse', 'heart')
    
    def _get_text_positions(self):
        """
        Get the display positions for color text based on animation type.
        Returns dict with 'color1' and 'color2' keys
        For 3-text layout: values can be 'left', 'center', 'right'
        For 2-text layout: values are 'left', 'right'
        """
        positions = {
            'pulse': {'color2': ['left', 'right'], 'color1': ['center']},
            'heart': {'color1': ['left', 'right'], 'color2': ['center']}
        }
        
        return positions.get(self.animation_type, {'color1': ['left'], 'color2': ['right']})
    
    def _get_all_element_positions(self, rect):
        """
        Calculate positions for all elements (handles and buttons) in order.
        Returns dict with 'color_zones', 'swap', 'sync', 'gradient_pill_width', 'button_container_rect' keys.
        
        Layout:
        - 2-text: [color1, color2] [swap, sync]  (two separate pills)
        - 3-text: [color1_left, color1_or_2_center, color1_or_2_right] [swap, sync]  (two separate pills)
        """
        handle_h = self.height() - self._margin * 2
        button_w = handle_h
        button_h = handle_h
        
        # Calculate handle widths (reuse helper method)
        handle_w1, handle_w2 = self._calculate_handle_widths()
        
        positions = self._get_text_positions()
        color_zones = {'color1': [], 'color2': []}
        
        current_x = self._margin
        y = self._margin
        
        # Gap between gradient pill and button pill
        pill_gap = WIDGET_SPACING
        
        if self._uses_three_text_layout():
            # 3-text layout: [hex, hex, hex] [swap, sync]
            # Determine which color goes where
            if 'left' in positions['color1']:
                # color1 on sides, color2 in center
                # Left color1
                color_zones['color1'].append(QRect(current_x, y, handle_w1, handle_h))
                current_x += handle_w1 + self._handle_spacing
                
                # Center color2
                color_zones['color2'].append(QRect(current_x, y, handle_w2, handle_h))
                current_x += handle_w2 + self._handle_spacing
                
                # Right color1
                color_zones['color1'].append(QRect(current_x, y, handle_w1, handle_h))
                current_x += handle_w1
            else:
                # color2 on sides, color1 in center
                # Left color2
                color_zones['color2'].append(QRect(current_x, y, handle_w2, handle_h))
                current_x += handle_w2 + self._handle_spacing
                
                # Center color1
                color_zones['color1'].append(QRect(current_x, y, handle_w1, handle_h))
                current_x += handle_w1 + self._handle_spacing
                
                # Right color2
                color_zones['color2'].append(QRect(current_x, y, handle_w2, handle_h))
                current_x += handle_w2
        else:
            # 2-text layout: [color1, color2] [swap, sync]
            # Left color1
            color_zones['color1'].append(QRect(current_x, y, handle_w1, handle_h))
            current_x += handle_w1 + self._handle_spacing
            
            # Right color2
            color_zones['color2'].append(QRect(current_x, y, handle_w2, handle_h))
            current_x += handle_w2
        
        # Gradient pill width (up to end of last color handle + margin)
        gradient_pill_width = current_x + self._margin
        
        # Compute button pill width (what we need for buttons)
        button_pill_width = self._margin * 2 + button_w * 2 + self._handle_spacing

        # If the actual widget rect is smaller than required, shrink the gradient pill
        # so the button container fits and nothing is drawn outside the widget.
        required_total = gradient_pill_width + pill_gap + button_pill_width
        available_width = rect.width()
        if available_width < required_total:
            deficit = required_total - available_width
            # minimal gradient width is the sum of left margin + all handles + right margin
            if self._uses_three_text_layout():
                min_gradient_width = self._margin * 2 + handle_w1 * 2 + handle_w2 + self._handle_spacing * 2
            else:
                min_gradient_width = self._margin * 2 + handle_w1 + handle_w2 + self._handle_spacing

            # Try to reduce gradient_pill_width but not below minimal
            gradient_pill_width = max(min_gradient_width, gradient_pill_width - deficit)

        # Start button container after gap
        button_x = gradient_pill_width + pill_gap + self._margin
        
        # Swap button
        swap_rect = QRect(button_x, y, button_w, button_h)
        button_x += button_w + self._handle_spacing
        
        # Sync button
        sync_rect = QRect(button_x, y, button_w, button_h)
        button_x += button_w
        
        # Button container rect
        button_container_width = button_x - (gradient_pill_width + pill_gap) + self._margin
        button_container_rect = QRect(
            gradient_pill_width + pill_gap,
            0,
            button_container_width,
            self.height()
        )
        
        return {
            'color_zones': color_zones,
            'swap': swap_rect,
            'sync': sync_rect,
            'gradient_pill_width': gradient_pill_width,
            'button_container_rect': button_container_rect,
            'pill_gap': pill_gap
        }
    

    
    def _get_zone_at_pos(self, pos):
        """Determine which zone the mouse is over"""
        rect = self.rect()
        
        # Get all element positions
        elements = self._get_all_element_positions(rect)
        
        # Check button zones
        if elements['swap'].contains(pos):
            return 'swap'
        if elements['sync'].contains(pos):
            return 'sync'
        
        # Check color zones and return granular zone ids
        # For 3-text layouts we may have multiple rects per color (left/center/right)
        c1_list = elements['color_zones']['color1']
        c2_list = elements['color_zones']['color2']

        # Helper to determine subzone name based on index and list length
        def subname_for(index, total, default_side):
            if total == 1:
                return 'center' if self._uses_three_text_layout() else default_side
            return 'left' if index == 0 else 'right'

        for idx, zone_rect in enumerate(c1_list):
            if zone_rect.contains(pos):
                sub = subname_for(idx, len(c1_list), 'left')
                return f'color1:{sub}'

        for idx, zone_rect in enumerate(c2_list):
            if zone_rect.contains(pos):
                sub = subname_for(idx, len(c2_list), 'right')
                return f'color2:{sub}'
        
        return None
    
    def _get_tooltip_for_zone(self, zone):
        """Get the appropriate tooltip text for a zone"""
        if not zone:
            return ''
        
        # Parse zone string
        base, sub = zone.split(':', 1) if ':' in zone else (zone, None)
        
        # Button tooltips
        if base in self._tooltips:
            return self._tooltips[base]
        
        # Color zone tooltips
        if base.startswith('color'):
            if self._uses_three_text_layout() and sub in ('left', 'right'):
                return 'Edit left/right gradient color'
            elif sub == 'center' or sub is None:
                return 'Edit center gradient color'
            else:
                return 'Edit left gradient color' if base == 'color1' else 'Edit right gradient color'
        
        return ''
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for hover effects"""
        old_hover = self.hover_zone
        self.hover_zone = self._get_zone_at_pos(event.pos())
        
        if old_hover != self.hover_zone:
            self.update()
            
            # Show or hide per-zone tooltip
            tooltip = self._get_tooltip_for_zone(self.hover_zone)
            if tooltip:
                show_tooltip(tooltip, self)
            else:
                hide_tooltip()
        
        super().mouseMoveEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave"""
        if self.hover_zone is not None:
            self.hover_zone = None
            self.update()
        # Hide any tooltip when leaving widget
        hide_tooltip()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press"""
        if event.button() == Qt.LeftButton:
            self.pressed_zone = self._get_zone_at_pos(event.pos())
            self.update()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release - trigger actions"""
        if event.button() == Qt.LeftButton and self.pressed_zone:
            release_zone = self._get_zone_at_pos(event.pos())
            
            # Only trigger if released in same zone as pressed
            if release_zone == self.pressed_zone:
                # color zones may be granular like 'color1:left' etc.
                if release_zone.startswith('color1'):
                    self._pick_color('gradient_color1', self.color1)
                elif release_zone.startswith('color2'):
                    self._pick_color('gradient_color2', self.color2)
                elif release_zone == 'swap':
                    self._swap_colors()
                elif release_zone == 'sync':
                    self._sync_colors()
            
            self.pressed_zone = None
            self.update()
        
        super().mouseReleaseEvent(event)
    
    def _pick_color(self, color_key, current_color):
        """Open color picker dialog"""
        color = QColorDialog.getColor(QColor(current_color), self, 
                                       f"Pick {color_key.replace('_', ' ').title()}")
        
        if color.isValid():
            hex_color = color.name()
            
            # Update local state
            if color_key == 'gradient_color1':
                self.color1 = hex_color
            else:
                self.color2 = hex_color
            
            self._calculate_required_width()
            self.color_changed.emit(color_key, hex_color)
            self.update()
    
    def _swap_colors(self):
        """Swap the two gradient colors"""
        self.color1, self.color2 = self.color2, self.color1
        self._calculate_required_width()
        self.colors_swapped.emit()
        self.update()
    
    def _sync_colors(self):
        """
        Sync gradient colors to theme primary and accent colors.
        Respects current gradient color positions (doesn't swap them back).
        """
        theme = self.theme_manager.current_theme
        
        # Get theme colors
        theme_primary = theme.get('base_primary', '#ff00ff')
        theme_accent = theme.get('base_accent', '#00ffff')
        
        # Sync colors while maintaining current positions
        is_swapped = theme.get('gradient_color1', theme_primary).lower() == theme_accent.lower()
        self.color1 = theme_accent if is_swapped else theme_primary
        self.color2 = theme_primary if is_swapped else theme_accent
        
        self._calculate_required_width()
        self.colors_synced.emit()
        self.update()
    
    def paintEvent(self, event):
        """Paint the gradient bar with colors and buttons"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        
        rect = self.rect()
        h = self.height()
        radius = h / 2  # Pill shape radius (same as multi-step toggle)
        
        # Get all element positions to know where buttons container ends
        elements = self._get_all_element_positions(rect)
        
        # Calculate gradient pill rect (excludes button container area)
        gradient_pill_width = elements['gradient_pill_width']
        gradient_pill_rect = QRect(rect.x(), rect.y(), gradient_pill_width, h)
        
        # Draw gradient background pill
        gradient = QLinearGradient(gradient_pill_rect.topLeft(), gradient_pill_rect.topRight())
        stops = self._get_gradient_stops(gradient_pill_rect)
        for pos, color in stops:
            gradient.setColorAt(pos, color)
        
        painter.setBrush(gradient)
        painter.drawRoundedRect(gradient_pill_rect, radius, radius)
        
        # Draw buttons container pill
        self._draw_buttons_container(painter, rect, elements)
        
        # Draw color text handles
        self._draw_color_handles(painter, rect)
        
        # Draw buttons
        self._draw_buttons(painter, rect)
    
    def _draw_buttons_container(self, painter, rect, elements):
        """Draw the separate pill container for buttons"""
        button_container_rect = elements['button_container_rect']
        
        # Get theme colors for container background
        palette = self.theme_manager.get_palette() if self.theme_manager else {}
        bg_color = QColor(palette.get('toggle_bg_off', '#394f8c'))
        
        # Draw pill-shaped container
        h = button_container_rect.height()
        radius = h / 2
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(button_container_rect, radius, radius)
    
    def _draw_color_handles(self, painter, rect):
        """Draw the color hex code handles with pill shape"""
        elements = self._get_all_element_positions(rect)
        color_zones = elements['color_zones']
        painter.setFont(self._handle_font)
        
        # Draw color1 handles
        for zone_rect in color_zones['color1']:
            self._draw_single_color_handle(
                painter, zone_rect, self.color1, 'color1'
            )
        
        # Draw color2 handles
        for zone_rect in color_zones['color2']:
            self._draw_single_color_handle(
                painter, zone_rect, self.color2, 'color2'
            )
    
    def _is_zone_active(self, zone_key):
        """Check if a zone is currently hovered or pressed"""
        return ((self.hover_zone and str(self.hover_zone).startswith(zone_key)) or
                (self.pressed_zone and str(self.pressed_zone).startswith(zone_key)))
    
    def _draw_single_color_handle(self, painter, zone_rect, color_hex, color_key):
        """Draw a single color handle with pill shape (matching multi-step toggle handle)"""
        # Use the actual gradient color for the handle background
        handle_color = QColor(color_hex)
        
        # Make handle transparent by default, opaque on hover/press
        handle_color.setAlpha(255 if self._is_zone_active(color_key) else 0)
        
        # Draw pill-shaped handle background
        handle_radius = zone_rect.height() / 2
        painter.setBrush(handle_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(zone_rect, handle_radius, handle_radius)
        
        # Draw text on handle using project's contrast helper
        painter.setPen(QColor(get_contrasting_text_color(color_hex)))
        painter.drawText(zone_rect, Qt.AlignCenter, color_hex.upper())
    
    def _draw_buttons(self, painter, rect):
        """Draw the swap and sync buttons"""
        elements = self._get_all_element_positions(rect)
        
        # Draw swap button
        self._draw_button(
            painter, 
            elements['swap'], 
            "⇄", 
            "Swap Colors",
            'swap'
        )
        
        # Draw sync button
        self._draw_button(
            painter, 
            elements['sync'], 
            "↻", 
            "Sync to Theme",
            'sync'
        )
    
    def _draw_button(self, painter, button_rect, icon, tooltip, zone_key):
        """Draw a single button with icon (pill-shaped like handle)"""
        # Get theme colors for button - use accent color
        palette = self.theme_manager.get_palette() if self.theme_manager else {}
        button_color = QColor(palette.get('accent_color', '#0078d4'))
        
        # Transparent by default, show actual color on hover/press
        is_active = self.hover_zone == zone_key or self.pressed_zone == zone_key
        button_color.setAlpha(255 if is_active else 0)
        
        # Draw pill-shaped button background
        button_radius = button_rect.height() / 2
        painter.setBrush(button_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(button_rect, button_radius, button_radius)
        
        # Draw icon
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.setPen(self.palette().text().color())
        painter.drawText(button_rect, Qt.AlignCenter, icon)
    
    def sizeHint(self):
        """Provide size hint for layout management"""
        if self.minimumWidth() == 0:
            self._calculate_required_width()
        return QSize(self.minimumWidth(), ELEMENT_HEIGHT)
    
    def minimumSizeHint(self):
        """Provide minimum size hint"""
        return self.sizeHint()
