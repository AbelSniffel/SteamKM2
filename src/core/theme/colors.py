"""Color helper utilities used by theming and stylesheet generation."""
from __future__ import annotations

from typing import Dict, Any
from PySide6.QtGui import QColor


def adjust_color(color_str: str, light_delta: float = 0.0, sat_delta: float = 0.0, alpha_delta: float = 0.0) -> str:
    """Adjust a color by changing lightness, saturation and alpha.
    
    This function uses a hybrid approach to avoid color space conversion artifacts:
    - Short-circuits when no changes are needed (preserves exact input)
    - Uses HSL space for lightness/saturation adjustments to maintain hue
    - Directly modifies alpha without conversion
    
    Parameters:
        color_str: Any QColor-compatible color string (#RRGGBB, #AARRGGBB, named colors, etc.)
        light_delta: Change in lightness (-1.0 to 1.0, where 0.0 = no change)
        sat_delta: Change in saturation (-1.0 to 1.0, where 0.0 = no change)
        alpha_delta: Change in alpha/opacity (-1.0 to 1.0, where 0.0 = no change)
    
    Returns:
        Hex color string: #RRGGBB for opaque colors, #AARRGGBB for transparent colors
    """
    # Short-circuit: if no adjustments needed, return original to avoid conversion artifacts
    if light_delta == 0.0 and sat_delta == 0.0 and alpha_delta == 0.0:
        color = QColor(color_str)
        # Normalize to hex format
        if color.alphaF() >= 1.0:
            return color.name(QColor.NameFormat.HexRgb)
        else:
            return color.name(QColor.NameFormat.HexArgb)
    
    color = QColor(color_str)
    
    # Handle alpha separately if it's the only change (avoids HSL conversion)
    if light_delta == 0.0 and sat_delta == 0.0 and alpha_delta != 0.0:
        a_new = max(0.0, min(1.0, color.alphaF() + alpha_delta))
        color.setAlphaF(a_new)
        if a_new >= 1.0:
            return color.name(QColor.NameFormat.HexRgb)
        else:
            return color.name(QColor.NameFormat.HexArgb)
    
    # Need to adjust lightness/saturation: use HSL space
    h = color.hueF()
    s = color.saturationF()
    l = color.lightnessF()
    a = color.alphaF()

    l = max(0.0, min(1.0, l + light_delta))
    s = max(0.0, min(1.0, s + sat_delta))
    a_new = max(0.0, min(1.0, a + alpha_delta))

    new_color = QColor.fromHslF(h, s, l, a_new)
    
    # Return RGB format for opaque colors, ARGB format for transparent colors
    if a_new >= 1.0:
        return new_color.name(QColor.NameFormat.HexRgb)
    else:
        return new_color.name(QColor.NameFormat.HexArgb)


def to_hex_rgb(color_str: str) -> str:
    """Convert any QColor-accepted string to #RRGGBB (drop alpha)."""
    c = QColor(color_str)
    return c.name(QColor.NameFormat.HexRgb)


def get_contrasting_text_color(bg_color_str: str) -> str:
    """Return black or white for good contrast against the background color."""
    color = QColor(bg_color_str)
    r = color.redF()
    g = color.greenF()
    b = color.blueF()
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#ffffff" if luminance < 0.5 else "#000000"


def mix_colors(color1_str: str, color2_str: str, ratio: float = 0.5) -> str:
    """Mix two colors together.
    
    Parameters:
        color1_str: First color (any QColor-compatible string)
        color2_str: Second color (any QColor-compatible string)
        ratio: Blend ratio (0.0 = all color1, 1.0 = all color2, 0.5 = equal mix)
    
    Returns:
        Hex color string (#RRGGBB)
    """
    c1 = QColor(color1_str)
    c2 = QColor(color2_str)
    
    r = int(c1.red() * (1 - ratio) + c2.red() * ratio)
    g = int(c1.green() * (1 - ratio) + c2.green() * ratio)
    b = int(c1.blue() * (1 - ratio) + c2.blue() * ratio)
    
    return QColor(r, g, b).name(QColor.NameFormat.HexRgb)


# =============================================================================
# PALETTE COMPUTATION
# =============================================================================
#
# This function computes ALL derived colors from the 3 base theme colors.
# Each section is clearly labeled so you can easily find and edit colors.
#
# ADJUSTMENT PARAMETERS:
#   adjust_color(base_color, light, sat, alpha)
#     - light: -1.0 (darker) to +1.0 (lighter), 0 = no change
#     - sat:   -1.0 (less saturated) to +1.0 (more saturated), 0 = no change  
#     - alpha: -1.0 (more transparent) to +1.0 (more opaque), 0 = no change
#
# =============================================================================

def compute_palette(theme: Dict[str, Any]) -> Dict[str, str]:
    """Compute the full derived color palette from theme base colors.
    
    This is the SINGLE SOURCE OF TRUTH for all color computations.
    Both stylesheet.py and ThemeManager.get_palette() use this function.
    """
    
    # -------------------------------------------------------------------------
    # BASE COLORS (from theme settings)
    # -------------------------------------------------------------------------
    bg = theme.get('base_background') or '#252524'       # Main background
    primary = theme.get('base_primary') or '#0078d4'     # Primary/brand color
    accent = theme.get('base_accent') or '#1db954'       # Accent/highlight color
    text = get_contrasting_text_color(bg)                # Auto: white or black
    
    # -------------------------------------------------------------------------
    # BUTTON STATES (derived from primary)
    # -------------------------------------------------------------------------
    hover_color = adjust_color(primary, 0, 0, -0.45)           # Button hover (transparent)
    pressed_color = primary #adjust_color(primary, -0.05, 0.02, 0)      # Button pressed (darker)
    subtle_pressed = adjust_color(primary, -0.05, 0.03, -0.55) # Subtle button pressed
    disabled_primary = adjust_color(primary, 0, 0, -0.45)      # Disabled button
    
    # -------------------------------------------------------------------------
    # INPUT FIELDS (backgrounds for text inputs, combos, spinboxes)
    # -------------------------------------------------------------------------
    input_bg = adjust_color(primary, 0, 0, -0.65)              # Default input background
    input_bg_focused = adjust_color(accent, 0, 0, -0.55)       # Focused input background
    
    # -------------------------------------------------------------------------
    # LAYOUT BACKGROUNDS (panels, containers, groupboxes)
    # -------------------------------------------------------------------------
    border = adjust_color(bg, 0.2, 0.1, 0)                     # General border color
    game_card_bg = adjust_color(bg, 0.01, 0, 0)                # Game card background
    page_nav_bar = adjust_color(bg, 0.075, -0.075, 0)          # Page navigation bar
    statusbar_bg = adjust_color(bg, 0.05, 0, 0)                # Status bar background
    groupbox_bg = adjust_color(bg, 0.15, 0, 0)                 # Groupbox background
    inner_groupbox_bg = adjust_color(bg, -0.055, -0.015, -0.45)# Nested groupbox bg
    
    # -------------------------------------------------------------------------
    # SIDEBAR (navigation sidebar)
    # -------------------------------------------------------------------------
    sidebar_bg = adjust_color(bg, 0.035, -0.1, 0)              # Sidebar background
    sidebar_hover = adjust_color(primary, 0, 0, -0.6)          # Sidebar item hover
    sidebar_selected_hover = adjust_color(primary, 0.05, 0, 0) # Selected item hover
    
    # -------------------------------------------------------------------------
    # TAGS (tag buttons, filter chips)
    # -------------------------------------------------------------------------
    tag_color = primary                                        # Tag background
    tag_hover = adjust_color(primary, 0.05, -0.1, 0)           # Tag hover
    tag_pressed = adjust_color(primary, 0.1, 0.5, 0)           # Tag pressed
    tag_disabled = adjust_color(primary, 0, -0.10, 0)           # Tag disabled
    deselected = adjust_color(primary, 0, -0.10, -0.45)        # Deselected tag
    toggle_tag_hover = adjust_color(primary, 0, 0, -0.3)       # Toggle tag hover
    toggle_tag_toggled_hover = adjust_color(primary, 0.035, 0.1, 0)  # Toggled hover
    
    # -------------------------------------------------------------------------
    # SCROLLBARS & HANDLES
    # -------------------------------------------------------------------------
    handle_color = accent                                      # Scrollbar handle
    handle_hover = adjust_color(accent, -0.1, 0.1, 0)          # Handle hover
    scrollbar_bg = groupbox_bg                                 # Scrollbar track
    
    # -------------------------------------------------------------------------
    # TOGGLES & SWITCHES
    # -------------------------------------------------------------------------
    toggle_bg_off = adjust_color(primary, 0, 0, -0.65)         # Toggle off background
    toggle_bg_on = accent                                       # Toggle on background
    toggle_handle = accent                                      # Toggle handle color
    toggle_handle_off = get_contrasting_text_color(toggle_bg_off)
    toggle_handle_on = get_contrasting_text_color(bg)
    toggle_slot_bg = adjust_color(toggle_bg_off, -0.5, 0.0, -0.2)
    
    # -------------------------------------------------------------------------
    # SEARCH & HIGHLIGHTS
    # -------------------------------------------------------------------------
    search_highlight = adjust_color(accent, 0, 0, -0.75)       # Search result highlight
    
    # -------------------------------------------------------------------------
    # NOTIFICATIONS (toast/popup notifications)
    # -------------------------------------------------------------------------
    notification_bg = adjust_color(bg, 0.0, 0.1)
    notification_text = get_contrasting_text_color(notification_bg)
    
    # Notification type colors (fixed colors, not theme-derived)
    notification_success = "#4CAF50"   # Green
    notification_error = "#F44336"     # Red
    notification_warning = "#FF9800"   # Orange
    notification_info = "#2196F3"      # Blue
    
    # -------------------------------------------------------------------------
    # BADGES
    # -------------------------------------------------------------------------
    badge_platform = primary
    badge_deadline = accent
    badge_rating = mix_colors(primary, accent, 0.5)  # Mixed color for rating badge
    
    # -------------------------------------------------------------------------
    # TEXT
    # -------------------------------------------------------------------------
    disabled_text = adjust_color(text, 0.0, 0.0, -0.25)
    
    # =========================================================================
    # RETURN PALETTE (all colors used by stylesheet.py)
    # =========================================================================
    return {
        # Base
        'bg_color': bg,
        'text_color': text,
        'primary_color': primary,
        'accent_color': accent,
        'disabled_text_color': disabled_text,
        
        # Button states
        'hover_color': hover_color,
        'pressed_color': pressed_color,
        'subtle_pressed': subtle_pressed,
        'disabled_primary_color': disabled_primary,
        
        # Inputs
        'input_bg_color': input_bg,
        'input_bg_focused': input_bg_focused,
        
        # Layout
        'border_color': border,
        'game_card_bg': game_card_bg,
        'page_navigation_bar': page_nav_bar,
        'statusbar_bg': statusbar_bg,
        'groupbox_background': groupbox_bg,
        'inner_groupbox_background': inner_groupbox_bg,
        
        # Sidebar
        'sidebar_bg': sidebar_bg,
        'sidebar_hover': sidebar_hover,
        'sidebar_selected_hover': sidebar_selected_hover,
        
        # Tags
        'tag_color': tag_color,
        'tag_hover_color': tag_hover,
        'tag_pressed_color': tag_pressed,
        'tag_disabled_color': tag_disabled,
        'deselected_color': deselected,
        'toggle_tag_hover_color': toggle_tag_hover,
        'toggle_tag_toggled_hover_color': toggle_tag_toggled_hover,
        
        # Scrollbars
        'handle_color': handle_color,
        'handle_hover_color': handle_hover,
        'scrollbar_bg_color': scrollbar_bg,
        
        # Toggles
        'toggle_bg_off': toggle_bg_off,
        'toggle_bg_on': toggle_bg_on,
        'toggle_handle_color': toggle_handle,
        'toggle_handle_off': toggle_handle_off,
        'toggle_handle_on': toggle_handle_on,
        'toggle_slot_bg': toggle_slot_bg,
        
        # Search
        'search_highlight_color': search_highlight,
        
        # Notifications
        'notification_bg': notification_bg,
        'notification_text_color': notification_text,
        'notification_close_button_bg': notification_bg,
        'notification_close_button_hover': accent,
        'notification_success_color': notification_success,
        'notification_error_color': notification_error,
        'notification_warning_color': notification_warning,
        'notification_info_color': notification_info,
        
        # Badges
        'badge_platform_color': badge_platform,
        'badge_deadline_color': badge_deadline,
        'badge_rating_color': badge_rating,
    }
