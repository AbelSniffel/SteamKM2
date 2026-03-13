"""
Settings manager for SteamKM2
Handles application settings and configuration
"""

import json
import os
import platform
import base64
from typing import Any
from PySide6.QtCore import QSettings
from .theme import get_contrasting_text_color

class SettingsManager:
    """Manages application settings"""
    
    def __init__(self):
        # Ensure AppData directory exists
        app_data_dir = self.get_app_data_dir()
        os.makedirs(app_data_dir, exist_ok=True)
        
        # Use QSettings for cross-platform settings storage in AppData folder
        settings_path = os.path.join(app_data_dir, "settings.ini")
        self.settings = QSettings(settings_path, QSettings.Format.IniFormat)
        # Initialize default settings
        self._init_default_settings()
        # Create arrow.svg
        self._create_arrow_svg()
    
    def _init_default_settings(self):
        """Initialize default settings if they don't exist"""
        defaults = {
            'auto_update_check': True,
            'update_repo': 'AbelSniffel/SteamKM2',
            'update_include_prereleases': False,
            'update_check_interval_min': 5,
            'github_api_token': '',
            'show_unikm_github_button': True,
            'unikm_repo': 'AbelSniffel/UniKM',
            'show_status_bar': False,
            'current_theme': 'Dark',
            'game_list_view_mode': 'list',  # grid or list
            'page_navigation_bar_position': 'bottom',  # left, right, top, bottom
            'page_navigation_bar_appearance': 'icon_and_text',  # icon_and_text, icon_only, text_only
            'gradient_animation': 'scroll',  # scroll, pulse, scanner, heart
            'auto_backup_enabled': True,
            'auto_backup_interval_minutes': 5,  # 5 minutes
            'backup_max_count': 10,
            'tooltip_animation': 'Slide',  # Fade, Slide
            'tooltip_show_delay': 600,  # milliseconds
            'section_groupbox_title_location': 'left',  # left, top
            'toggle_style': 'regular',  # regular, dot
            # Game card display visibility settings
            'show_title_chip': True,
            'show_platform_chip': True,
            'show_tags_chip': True,
            'show_deadline_chip': True,
            # New top-level debug mode: controls developer features across the UI
            'debug_mode': False,
        }
        
        for key, value in defaults.items():
            if not self.settings.contains(key):
                self.settings.setValue(key, value)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self.settings.value(key, default)
    
    def set(self, key: str, value: Any):
        """Set a setting value"""
        self.settings.setValue(key, value)
        self.settings.sync()
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean setting"""
        value = self.settings.value(key, default)
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer setting"""
        try:
            value = self.settings.value(key, default)
            if isinstance(value, int):
                return value
            elif isinstance(value, str):
                return int(value)
            else:
                return default
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a float setting"""
        try:
            value = self.settings.value(key, default)
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str):
                return float(value)
            else:
                return default
        except (ValueError, TypeError):
            return default
    
    def export_settings(self, file_path: str) -> bool:
        """Export settings to an INI file using QSettings.

        This writes all current keys into a new INI file at file_path so the
        exported file is a native .ini suitable for re-import via QSettings.
        """
        try:
            target = QSettings(file_path, QSettings.Format.IniFormat)
            # Clear any existing contents in target
            try:
                target.clear()
            except Exception:
                pass
            for key in self.settings.allKeys():
                # Use the same value types via self.get
                target.setValue(key, self.get(key))
            target.sync()
            return True
        except Exception:
            return False
    
    def import_settings(self, file_path: str) -> bool:
        """Import settings from an INI file produced by export_settings.

        This reads the INI via QSettings and copies keys into the current
        settings instance.
        """
        try:
            src = QSettings(file_path, QSettings.Format.IniFormat)
            for key in src.allKeys():
                try:
                    val = src.value(key)
                    self.set(key, val)
                except Exception:
                    # Continue on individual key failure
                    pass
            return True
        except Exception:
            return False
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        self.settings.clear()
        self._init_default_settings()
    
    # --- Skipped Updates Management ---
    
    def get_skipped_versions(self) -> list:
        """Get list of skipped update versions."""
        try:
            raw = self.get('skipped_update_versions', '[]')
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def add_skipped_version(self, version: str):
        """Add a version to the skipped list."""
        if not version:
            return
        skipped = self.get_skipped_versions()
        # Normalize version (strip 'v' prefix if present)
        normalized = version.lstrip('vV')
        if normalized not in skipped:
            skipped.append(normalized)
            self.set('skipped_update_versions', json.dumps(skipped))
    
    def clear_skipped_versions(self):
        """Clear all skipped versions (should be called on successful update)."""
        self.set('skipped_update_versions', '[]')
    
    def is_version_skipped(self, version: str) -> bool:
        """Check if a version is in the skipped list."""
        if not version:
            return False
        normalized = version.lstrip('vV')
        return normalized in self.get_skipped_versions()
    
    def get_app_data_dir(self) -> str:
        """Get the application data directory for the current platform"""
        system = platform.system()
        home = os.path.expanduser("~")
        
        if system == "Windows":
            # Windows: %APPDATA%\SteamKM2
            app_data = os.environ.get('APPDATA', os.path.join(home, 'AppData', 'Roaming'))
            return os.path.join(app_data, 'SteamKM2')
        elif system == "Darwin":  # macOS
            # macOS: ~/Library/Application Support/SteamKM2
            return os.path.join(home, 'Library', 'Application Support', 'SteamKM2')
        else:  # Linux and other Unix-like systems
            # Linux: ~/.config/SteamKM2 or $XDG_CONFIG_HOME/SteamKM2
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.join(home, '.config'))
            return os.path.join(config_home, 'SteamKM2')
    
    def get_database_path(self) -> str:
        """Get the database file path.
        
        Returns the custom database path if set, otherwise the default path.
        """
        custom_path = self.get('custom_database_path', '')
        if custom_path and os.path.exists(custom_path):
            return custom_path
        # Default path
        app_dir = self.get_app_data_dir()
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, 'keys.db')
    
    def set_database_path(self, path: str):
        """Set a custom database path.
        
        Args:
            path: Path to the database file, or empty string to use default
        """
        if path:
            self.set('custom_database_path', path)
            # Add to recent databases
            self._add_recent_database(path)
        else:
            self.set('custom_database_path', '')
    
    def _add_recent_database(self, path: str):
        """Add a database path to the recent list."""
        recent = self.get_recent_databases()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        # Keep only last 5
        recent = recent[:5]
        self.set('recent_databases', json.dumps(recent))
    
    def get_recent_databases(self) -> list[str]:
        """Get list of recently used database paths."""
        try:
            raw = self.get('recent_databases', '[]')
            paths = json.loads(raw) if raw else []
            # Filter out non-existent paths
            return [p for p in paths if os.path.exists(p)]
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_default_database_path(self) -> str:
        """Get the default database path (ignoring custom setting)."""
        app_dir = self.get_app_data_dir()
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, 'keys.db')
    
    def get_themes_dir(self) -> str:
        """Get the themes directory path"""
        app_dir = self.get_app_data_dir()
        themes_dir = os.path.join(app_dir, 'Themes')
        os.makedirs(themes_dir, exist_ok=True)
        return themes_dir
    
    def _create_arrow_svg(self, color: str = 'currentColor'):
        """Creates down/up/right/left arrow SVG files with the given fill color in the app data Icons directory."""
        # Ensure icons directory
        icons_dir = os.path.join(self.get_app_data_dir(), 'Icons')
        os.makedirs(icons_dir, exist_ok=True)

        # File paths
        down_path = os.path.join(icons_dir, 'arrow_down.svg')
        up_path = os.path.join(icons_dir, 'arrow_up.svg')
        right_path = os.path.join(icons_dir, 'arrow_right.svg')
        left_path = os.path.join(icons_dir, 'arrow_left.svg')

        # Down arrow SVG content
        arrow_down_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="{color}" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M1.646 5.646a.5.5 0 0 1 .708 0L8 11.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                </svg>'''

        # Up arrow SVG content
        arrow_up_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="{color}" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M1.646 10.354a.5.5 0 0 1 .708 0L8 4.707l5.646 5.647a.5.5 0 0 1-.708.708L8 6.207l-4.646 4.647a.5.5 0 0 1-.708 0z"/>
                </svg>'''

        # Right arrow SVG content (simple chevron pointing right)
        arrow_right_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="{color}" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M5.646 3.646a.5.5 0 0 1 .708 0L11.293 9l-4.939 5.354a.5.5 0 1 1-.762-.648L9.793 9 5.592 4.294a.5.5 0 0 1 .054-.648z"/>
                </svg>'''

        # Left arrow SVG content (chevron pointing left)
        arrow_left_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="{color}" viewBox="0 0 16 16">
                <path fill-rule="evenodd" d="M10.354 12.354a.5.5 0 0 1-.708 0L4.707 8l4.939-4.354a.5.5 0 1 1 .762.648L6.207 8l4.147 3.706a.5.5 0 0 1 0 .648z"/>
                </svg>'''

        # Write SVG files (best-effort)
        for path, svg in (
            (down_path, arrow_down_svg),
            (up_path, arrow_up_svg),
            (right_path, arrow_right_svg),
            (left_path, arrow_left_svg),
        ):
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(svg)
            except Exception:
                # ignore write failures
                pass
    
