"""Stylesheet generation for the application.

This isolates the large QSS template so the ThemeManager remains focused on
state, IO, and signaling.

OPTIMIZED: Uses template helpers to reduce repetitive QSS patterns.
"""

from __future__ import annotations
import os
from typing import Any, Dict
from .colors import compute_palette
from src.ui.config import (
    ELEMENT_HEIGHT,
    PNB_HEIGHT,
    TAG_BUTTON_HEIGHT,
    BORDER_SIZE,
    SCROLLBAR_WIDTH,
    PADDING,
    TAG_PADDING,
    NONE_TAG_PADDING,
    PLATFORM_PADDING,
)


# =============================================================================
# QSS Template Helpers - Reduce repetitive patterns
# =============================================================================

def _arrow_button_styles(widget: str, radius: float, arrow_up: str, arrow_down: str, 
                         accent: str) -> str:
    """Generate up/down arrow button styles for SpinBox, DateEdit, etc."""
    corner_radius = radius / 1.5
    return f"""
        {widget}::up-button, {widget}::down-button {{
            width: 24px;
            /* Add a transparent border to hide fractional-pixel seams when moving between displays with different DPRs */
            border-left: 1px solid transparent;
        }}

        {widget}::up-button {{
            border-top-right-radius: {corner_radius}px;
        }}

        {widget}::down-button {{
            border-bottom-right-radius: {corner_radius}px;
        }}

        {widget}::up-button:hover, {widget}::down-button:hover {{
            background: {accent};
        }}

        {widget}::up-arrow {{
            image: url("{arrow_up}");
            width: 12px;
            height: 12px;
        }}

        {widget}::down-arrow {{
            image: url("{arrow_down}");
            width: 12px;
            height: 12px;
        }}"""


def _popup_menu_styles(widget: str, p: dict, radius: float, menu_item_radius: float) -> str:
    """Generate popup/dropdown menu styles (used by ComboBox and QMenu)."""
    return f"""
        {widget} {{
            background: {p['bg_color']};
            color: {p['text_color']};
            border: 1px solid {p['border_color']};
            border-radius: {radius}px;
            padding: 4px;
            selection-background-color: {p['primary_color']};
            outline: none;
        }}

        {widget}::item {{
            background: transparent;
            color: {p['text_color']};
            border-radius: {menu_item_radius}px;
            padding: 4px 4px;
            margin: 2px 0;
            border: none;
            outline: none;
        }}

        {widget}::item:hover {{
            background: {p['bg_color']};
            color: {p['text_color']};
            outline: none;
        }}

        {widget}::item:selected {{
            background: {p['accent_color']};
            color: white;
            outline: none;
        }}"""


def _scrollbar_slider_styles(p: dict, scrollbar_radius: int, handle_radius: int, 
                              scrollbar_width: int) -> str:
    """Generate scrollbar and slider styles."""
    return f"""
        /* Scrollbars */
        QScrollBar {{
            background-color: {p['scrollbar_bg_color']};
            border-radius: {scrollbar_radius}px;
        }}

        QScrollBar#Health_Monitor {{
            border-radius: 0px;
        }}

        QScrollBar:vertical {{
            width: {scrollbar_width}px;
            margin-top: 0; margin-bottom: 0;
        }}

        QScrollBar:horizontal {{
            height: {scrollbar_width}px;
            margin-left: 0; margin-right: 0;
        }}

        QScrollBar::handle {{
            background-color: {p['handle_color']};
            margin: 2px;
            border-radius: {handle_radius}px;
        }}
        
        QScrollBar::handle:vertical {{
            min-height: 30px;
        }}
        
        QScrollBar::handle:horizontal {{
            min-width: 30px;
        }}
        
        QScrollBar::handle:hover {{
            background-color: {p['handle_hover_color']};
        }}

        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0px; height: 0px;
            background: transparent;
        }}

        QScrollBar::add-page, QScrollBar::sub-page {{
            background: transparent;
        }}
        
        /* Sliders */
        QSlider {{
            border-radius: {scrollbar_radius}px;
            background: {p['scrollbar_bg_color']};
        }}

        QSlider::groove {{
            background: transparent;
        }}

        QSlider:vertical {{
            width: {scrollbar_width + 3}px;
        }}

        QSlider:horizontal {{
            height: {scrollbar_width + 3}px;
        }}

        QSlider::groove:horizontal {{
            margin-left: 3px; margin-right: 3px;
        }}

        QSlider::groove:vertical {{
            margin-top: 3px; margin-bottom: 3px;
        }}

        QSlider::handle {{
            background: {p['handle_color']};
            border-radius: {handle_radius}px;
        }}
        
        QSlider::handle:horizontal {{
            height: {scrollbar_width}px;
            width: 30px;
            margin: 2px 0;
        }}
        
        QSlider::handle:vertical {{
            width: {scrollbar_width}px;
            height: 30px;
            margin: 0 2px;
        }}
        
        QSlider::handle:horizontal:hover, QSlider::handle:vertical:hover {{
            background: {p['handle_hover_color']};
        }}
        
        /* Progress Bars */
        QProgressBar {{
            border-radius: {handle_radius}px;
            background: {p['scrollbar_bg_color']};
            color: {p['text_color']};
            border: none;
            text-align: center;
            max-height: {scrollbar_width}px;
        }}

        QProgressBar::chunk {{
            background: {p['handle_color']};
            border-radius: {handle_radius}px;
        }}"""


def _tag_button_styles(p: dict, tag_radius: int) -> str:
    """Generate all tag button variants."""
    return f"""
        /* Tag Buttons */
        QPushButton#tag_button, QPushButton#gc_tag_button, QPushButton#gc_tag_button:disabled {{
            border-radius: {tag_radius}px;
            background-color: {p['tag_color']};
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            padding: {TAG_PADDING};
        }}

        QPushButton#tag_button:hover {{
            background-color: {p['tag_hover_color']};
        }}

        QPushButton#tag_button:pressed {{
            background-color: {p['tag_pressed_color']};
        }}
        
        QPushButton#tag_button:disabled {{
            background-color: {p['tag_disabled_color']};
        }}

        QPushButton#tag_button:checked, QPushButton#gc_tag_button:checked {{
            background-color: {p['tag_color']};
            color: #ffffff;
        }}

        QPushButton#tag_button:checked:hover, QPushButton#gc_tag_button:checked:hover {{
            background-color: {p['tag_color']};
        }}

        /* Toggleable Tag Buttons */
        QPushButton#toggle_tag_button {{
            border-radius: {tag_radius}px;
            background-color: transparent;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            padding: {TAG_PADDING};
        }}

        QPushButton#toggle_tag_button:hover {{
            background-color: {p['toggle_tag_hover_color']};
        }}
        
        QPushButton#toggle_tag_button:pressed {{
            background-color: {p['accent_color']};
        }}
        
        QPushButton#toggle_tag_button:checked {{
            background-color: {p['accent_color']};
        }}

        QPushButton#toggle_tag_button:checked:hover {{
            background-color: {p['accent_color']};
        }}

        /* None placeholder buttons */
        QPushButton#none_placeholder, QPushButton#fetching_placeholder {{
            background-color: {p['tag_disabled_color']};
            color: {p['disabled_text_color']};
            border-radius: {tag_radius}px;
            font-size: 11px; 
            font-weight: bold;
            padding: {NONE_TAG_PADDING};
        }}
"""


def _calendar_styles(p: dict, radius: int) -> str:
    """Generate calendar widget styles."""
    return f"""
        QCalendarWidget {{
            background-color: {p['bg_color']};
            color: {p['text_color']};
            border: 1px solid {p['border_color']};
            border-radius: {radius}px;
        }}

        QCalendarWidget QWidget {{
            alternate-background-color: {p['input_bg_color']};
        }}

        QCalendarWidget QAbstractItemView {{
            outline: none;
        }}

        QCalendarWidget QAbstractItemView::item {{
            background: transparent;
            color: {p['text_color']};
            border-radius: {int(radius/2)}px;
        }}

        QCalendarWidget QAbstractItemView::item:hover {{
            background: {p['hover_color']};
            color: {p['text_color']};
        }}

        QCalendarWidget QAbstractItemView::item:selected {{
            background: {p['primary_color']};
            color: white;
        }}

        QCalendarWidget QAbstractItemView:disabled {{
            color: {p['disabled_text_color']};
        }}

        QCalendarWidget QToolButton {{
            background-color: transparent;
            color: {p['text_color']};
            border: none;
            border-radius: {radius}px;
            padding: 6px;
            min-width: 30px;
        }}

        QCalendarWidget QToolButton:hover {{
            background-color: {p['hover_color']};
        }}

        QCalendarWidget QToolButton:pressed {{
            background-color: {p['pressed_color']};
        }}

        QCalendarWidget QToolButton::menu-indicator {{
            image: none;
        }}

        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {p['groupbox_background']};
            border-radius: 0;
        }}

        QCalendarWidget QWidget#qt_calendar_prevmonth,
        QCalendarWidget QWidget#qt_calendar_nextmonth {{
            qproperty-icon: none;
            min-width: 30px;
        }}

        QCalendarWidget QWidget#qt_calendar_prevmonth {{
            qproperty-text: "◀";
            border-top-left-radius: 0; border-bottom-left-radius: 0;
        }}

        QCalendarWidget QWidget#qt_calendar_nextmonth {{
            qproperty-text: "▶";
            border-top-right-radius: 0; border-bottom-right-radius: 0;
        }}"""


def _sidebar_styles(p: dict, radius: int) -> str:
    """Generate all sidebar-related styles."""
    return f"""
        /* Modern Sidebar Styling */
        #Sidebar {{
            background-color: transparent;
            border: none;
            padding: 8px 4px;
        }}

        #page_sidebar {{
            border: none;
            border-radius: 0;
        }}

        #page_sidebar QScrollArea {{
            background-color: transparent;
            border: none;
        }}

        #page_sidebar QWidget#sidebar_content {{
            background-color: {p['sidebar_bg']};
            border-radius: 0;
            padding: 12px 10px;
        }}

        #sidebar_header,
        #sidebar_search_container,
        #sidebar_nav_container,
        #sidebar_sections_container {{
            background-color: transparent;
        }}

        #sidebar_header {{
            padding-top: 14px;
            padding-bottom: 8px;
        }}

        #sidebar_nav_container {{
            padding: 8px;
        }}

        #sidebar_sections_container {{
            padding: 12px;
        }}
        
        #settings_sidebar {{
            background-color: {p['sidebar_bg']};
            border: none;
            border-radius: {radius * 1.5}px;
            padding: 6px 6px;
            outline: none;
        }}
        
        #settings_sidebar::item {{
            background-color: transparent;
            color: {p['text_color']};
            border: none;
            border-radius: {radius}px;
            padding: {PADDING};
            margin: 2px 0px;
            font-weight: 500;
        }}
        
        #settings_sidebar::item:hover {{
            background-color: {p['sidebar_hover']};
            color: white;
        }}
        
        #settings_sidebar::item:selected {{
            background-color: {p['primary_color']};
            color: white;
            font-weight: 600;
        }}
        
        #settings_sidebar::item:selected:hover {{
            background-color: {p['sidebar_selected_hover']};
        }}

        /* Game Details Dialog - Game Tabs Sidebar */
        #MultiGameEditSidebar {{
            background-color: {p['page_navigation_bar']};
            border: none;
            border-radius: 0px;
        }}

        #MultiGameEditSidebar QPushButton {{
            background-color: transparent;
            text-align: left;
            border: none;
        }}

        #MultiGameEditSidebar QPushButton:hover {{
            background-color: {p['hover_color']};
            color: white;
        }}

        #MultiGameEditSidebar QPushButton:checked {{
            background-color: {p['accent_color']};
            color: white;
        }}

        #MultiGameEditSidebar QPushButton:checked:hover {{
            background-color: {p['accent_color']};
        }}

        #MultiGameEditSidebar QScrollArea {{
            background-color: transparent;
            border: none;
        }}"""


def _groupbox_styles(p: dict, radius: int) -> str:
    """Generate groupbox styles."""
    return f"""
        /* Group Boxes */
        QGroupBox {{
            background-color: {p['groupbox_background']};
            border: 0px solid {p['border_color']};
            font-weight: bold;
            border-radius: {radius * 1.25}px;
            color: {p['text_color']};
        }}
        
        #SectionGroupBox {{
            background-color: {p['inner_groupbox_background']};
            border: 0px solid {p['border_color']};
            border-radius: {radius * 1.25}px;
            color: {p['text_color']};
        }}

        #sidebar_groupbox {{
            background-color: {p['groupbox_background']};
            border: 0px solid {p['border_color']};
            border-radius: {radius}px;
            color: {p['text_color']};
        }}

        #SectionOuterGroupLabel {{
            font-size: 14px;
            font-weight: bold;
            padding: 3px 0;
        }}

        #SectionInnerGroupLabel {{
            font-weight: bold;
            font-size: 13px;
            padding: 0px 4px;
            border-left: 2px solid {p['text_color']};
            border-radius: 0;
        }}

        #TagBox {{
            border-radius: {radius}px;
            background-color: {p['deselected_color']};
            padding: 5px;
            margin: 0;
            margin-top: 12px;
        }}

        QWidget#ScrollableFlowContainer {{
            background-color: transparent;
            border-radius: {radius}px;
        }}

        #TagFlowScroll {{
            border-radius: {radius}px;
            background-color: {p['deselected_color']};
            padding: 4px;
            margin: 0px;
        }}

        #TagBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0px 8px;
            color: {p['text_color']};
            font-weight: bold;
            font-size: 12px;
            background-color: none;
            border-top-left-radius: {radius}px;
            border-top-right-radius: {radius}px;
        }}

        #page_navigation_button_groupbox {{
            background-color: {p['bg_color']};
            border: 0px;
            border-radius: {radius * 1.5}px;
            margin: 0px; 
            padding: 0px;
        }}"""


# =============================================================================
# Main Stylesheet Generator
# =============================================================================

def generate_stylesheet(theme: Dict[str, Any], *, app_data_dir: str) -> str:
    """Generate complete application stylesheet (QSS) from a theme dict.

    Parameters:
    - theme: The theme data (expects base_* fields).
    - app_data_dir: Base app data directory containing Icons/arrow_*.svg.
    """
    # Compute the full color palette (SINGLE SOURCE OF TRUTH)
    p = compute_palette(theme)
    
    # Compute radii and other non-color values
    radius = int(theme.get("corner_radius", 4))
    scrollbar_radius = int(theme.get("scrollbar_radius", radius))
    handle_radius = max(0, scrollbar_radius - 2)
    tag_radius = max(0, int(radius - (ELEMENT_HEIGHT - TAG_BUTTON_HEIGHT) / 2))
    menu_item_radius = radius / 1.5

    icons_dir = os.path.join(app_data_dir, "Icons")
    arrow_down_url = os.path.join(icons_dir, "arrow_down.svg").replace("\\", "/")
    arrow_up_url = os.path.join(icons_dir, "arrow_up.svg").replace("\\", "/")
    arrow_right_url = os.path.join(icons_dir, "arrow_right.svg").replace("\\", "/")
    arrow_left_url = os.path.join(icons_dir, "arrow_left.svg").replace("\\", "/")

    # Generate component styles using helpers
    scrollbar_slider_qss = _scrollbar_slider_styles(p, scrollbar_radius, handle_radius, SCROLLBAR_WIDTH)
    tag_button_qss = _tag_button_styles(p, tag_radius)
    calendar_qss = _calendar_styles(p, radius)
    sidebar_qss = _sidebar_styles(p, radius)
    groupbox_qss = _groupbox_styles(p, radius)
    
    # ComboBox popup styles
    combo_popup_qss = _popup_menu_styles("QComboBox QAbstractItemView", p, radius, menu_item_radius)
    
    # Arrow button styles for SpinBox, DateEdit, DateTimeEdit
    spinbox_arrows = _arrow_button_styles("QSpinBox", radius, arrow_up_url, arrow_down_url, p['accent_color'])
    date_arrows = _arrow_button_styles("QDateEdit", radius, arrow_up_url, arrow_down_url, p['accent_color'])
    datetime_arrows = _arrow_button_styles("QDateTimeEdit", radius, arrow_up_url, arrow_down_url, p['accent_color'])

    return f"""
        /* Main Application Style */
        #DEBUG {{
            background-color: rgba(255, 0, 0, 0.3);
        }}

        #CYAN_DEBUG {{
            background-color: rgba(0, 255, 255, 0.3);
        }}

        QMainWindow {{
            background-color: {p['bg_color']};
            color: {p['text_color']};
        }}

        QWidget {{
            background-color: {p['bg_color']};
            color: {p['text_color']};
            border-radius: {radius}px;
        }}

        #Transparent {{
            background-color: transparent;
        }}
        
        /* Page Navigation Bar Color */
        #page_navigation_bar {{
            background-color: {p['page_navigation_bar']};
            border-radius: 0;
        }}

        /* Home Page Filter / Tags Bars */
        #home_filter_bar, #home_filters_bar, #home_tags_bar {{
            background-color: {p['sidebar_bg']};
            border-radius: 0;
        }}

        /* Buttons */
        QPushButton {{
            background-color: {p['primary_color']};
            color: white;
            border-radius: {radius}px;
            padding: {PADDING};
            font-weight: bold;
            outline: none;
            min-height: {ELEMENT_HEIGHT - 4}px;
        }}
        
        QPushButton:hover {{
            background-color: {p['hover_color']};
        }}
        
        QPushButton:pressed {{
            background-color: {p['pressed_color']};
        }}
        
        QPushButton:disabled {{
            background-color: {p['disabled_primary_color']};
            color: {p['disabled_text_color']};
        }}

        QPushButton:checked:hover {{
            background-color: {p['primary_color']};
        }}

        /* Filter Toggle Buttons */
        QPushButton#toggle_button {{
            background-color: transparent;
            color: {p['text_color']};
        }}

        QPushButton#toggle_button:hover {{
            background-color: {p['hover_color']};
        }}

        QPushButton#toggle_button:pressed {{
            background-color: {p['subtle_pressed']};
        }}

        QPushButton#toggle_button:checked {{
            background-color: {p['primary_color']};
            color: white;
            border-color: {p['primary_color']};
        }}

        QPushButton#toggle_button:checked:hover {{
            background-color: {p['primary_color']};
        }}

        QPushButton#toggle_button:checked:pressed {{
            background-color: {p['pressed_color']};
        }}
        
        /* Page Selection Buttons */
        QPushButton#page_navigation_button {{
            background-color: transparent;
            color: {p['text_color']};
            text-align: left;
            font-weight: normal;
            border-radius: {radius * 1.25}px;
            padding: 2px 11px;
            min-height: {PNB_HEIGHT}px;
            max-height: {PNB_HEIGHT}px;
        }}
        
        QPushButton#page_navigation_button:hover {{
            background-color: {p['hover_color']};
        }}
        
        QPushButton#page_navigation_button:checked {{
            background-color: {p['primary_color']};
            color: white;
        }}

        QPushButton#page_navigation_button:checked:hover {{
            background-color: {p['primary_color']};
        }}

        QPushButton#page_navigation_button[centerText="true"] {{
            text-align: center;
        }}
        
        {tag_button_qss}
        
        /* Radio Buttons */
        QRadioButton {{
            color: {p['text_color']};
            background: transparent;
        }}

        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 8px;
            background-color: {p['bg_color']};
        }}

        QRadioButton::indicator:hover {{
            background-color: {p['hover_color']};
        }}

        QRadioButton::indicator:checked {{
            background-color: {p['accent_color']};
        }}

        QRadioButton::indicator:checked:hover {{
            background-color: {p['accent_color']};
        }}

        QRadioButton::indicator:disabled {{
            background-color: {p['disabled_primary_color']};
        }}
        
        /* Input Fields */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox, QDateTimeEdit, QDateEdit {{
            background-color: {p['input_bg_color']};
            border-radius: {radius}px;
            padding: {PADDING};
            color: {p['text_color']};
        }}
        
        QLineEdit:focus, QLineEdit:hover, QTextEdit:focus, QTextEdit:hover, QListWidget:hover,
        QPlainTextEdit:focus, QSpinBox:focus, QSpinBox:hover, QComboBox:focus, QComboBox:hover,
        QDateTimeEdit:hover, QDateEdit:hover, QDateTimeEdit:focus, QDateEdit:focus, 
        QDateTimeEdit::drop-down:hover, QDateEdit::drop-down:hover {{
            background-color: {p['input_bg_focused']};
        }}

        /* QListWidget */
        QListWidget {{
            background-color: {p['deselected_color']};
            border-radius: {radius}px;
            color: {p['text_color']};
            padding: 4px;
            margin: 0px;
        }}

        QListWidget::item {{
            margin: 2px 2px;
            padding: 2px 4px;
            border-radius: {radius / 1.5}px;
        }}

        QListWidget::item:selected {{
            background-color: {p['primary_color']};
            color: white;
        }}

        QListWidget::item:hover {{
            background-color: {p['hover_color']};
        }}

        /* ComboBox */
        QComboBox::drop-down {{
            border: none;
            width: 24px;
            border-top-right-radius: {radius}px;
            border-bottom-right-radius: {radius}px;
        }}

        QComboBox::drop-down:hover {{
            background-color: {p['accent_color']};
        }}
        
        QComboBox::down-arrow {{
            image: url("{arrow_down_url}");
            width: 12px;
            height: 12px;
        }}

        QComboBox::down-arrow:on {{
            image: url("{arrow_up_url}");
            width: 12px;
            height: 12px;
        }}
        
        /* ComboBox popup */
        {combo_popup_qss}
        
        QComboBox QAbstractItemView {{
            margin-top: 5px;
        }}

        QComboBox:focus {{
            outline: none;
        }}

        {spinbox_arrows}

        {date_arrows}
        
        {datetime_arrows}

        QDateTimeEdit::drop-down, QDateEdit::drop-down {{
            border: none;
            width: 24px;
            border-top-right-radius: {radius / 1.5}px;
            border-bottom-right-radius: {radius / 1.5}px;
        }}

        {calendar_qss}
        
        {groupbox_qss}

        /* Menus */
        QMenu {{
            background: {p['bg_color']};
            color: {p['text_color']};
            border: 1px solid {p['border_color']};
            border-radius: {radius}px;
            padding: 4px;
            selection-background-color: {p['primary_color']};
        }}

        QMenu::item, QComboBox QAbstractItemView::item {{
            background: transparent;
            color: {p['text_color']};
            border-radius: {menu_item_radius}px;
            padding: 4px 8px;
            padding-right: 14px;
        }}

        QMenu::item:selected, QComboBox QAbstractItemView::item:selected {{
            background: {p['accent_color']};
            color: white;
        }}

        QMenu::separator {{
            height: 1px;
            background: {p['border_color']};
            margin: 4px 0;
        }}

        QMenu::right-arrow {{
            image: url("{arrow_right_url}");
            width: 12px;
            height: 12px;
        }}

        QMenu::left-arrow {{
            image: url("{arrow_left_url}");
            width: 12px;
            height: 12px;
        }}
        
        /* Labels */
        QLabel {{
            color: {p['text_color']};
            background-color: transparent;
        }}
        
        QLabel#app_title,
        QLabel#page_title {{
            font-size: 16px;
            font-weight: bold;
        }}

        QPushButton#page_header_button {{
            border-top-left-radius: 0;
            border-top-right-radius: 0;
            border-bottom-left-radius: {radius}px;
            border-bottom-right-radius: {radius}px;
        }}

        /* Game Card Labels */
        QLabel#gc_platform_label {{
            background-color: {p['tag_color']};
            color: white;
            border-radius: {tag_radius}px;
            font-size: 12px; 
            font-weight: bold;
            padding: {TAG_PADDING};
        }}

        QLabel#gc_used_label {{
            background-color: #ff4444;
            color: white;
            border-radius: {tag_radius}px;
            font-size: 12px; 
            font-weight: bold;
            padding: {PLATFORM_PADDING};
        }}

        QLabel#gc_key_label {{ /* placeholder */ }}
        
        /* Scroll Areas */
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}

        {sidebar_qss}
        
        {scrollbar_slider_qss}
        
        /* Game Entry Cards */
        QWidget#game_card {{
            background-color: {p['game_card_bg']};
            border: 1px solid {p['border_color']};
            border-radius: {radius}px;
        }}
        
        /* Status Bar */
        QStatusBar {{
            background-color: {p['statusbar_bg']};
            border-radius: 0;
            color: {p['text_color']};
        }}
        """
