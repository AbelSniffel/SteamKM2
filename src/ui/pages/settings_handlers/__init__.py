"""
Settings page handlers for modular organization.

This package splits the SettingsPage functionality into separate modules:
- section_builder: Creates all UI sections
- search_handler: Handles search filtering and animations
- event_handlers: General event callbacks (mixin)
- theme_handlers: Theme customization callbacks (mixin)
- data_handlers: Tag, platform, and data-related callbacks (mixin)
"""

from .section_builder import SettingsSectionBuilder
from .search_handler import SearchAnimationHandler
from .event_handlers import SettingsEventHandlers
from .theme_handlers import ThemeHandlers
from .data_handlers import DataHandlers

__all__ = [
    'SettingsSectionBuilder',
    'SearchAnimationHandler',
    'SettingsEventHandlers',
    'ThemeHandlers',
    'DataHandlers',
]
