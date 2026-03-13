"""
Theme manager for SteamKM2
Handles theme application and color calculations using file-based themes
"""

import os
import json
from time import perf_counter

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QColor
from typing import Dict, Any, List, Tuple
# Config values are used inside the extracted stylesheet module, not here.
from .theme import (
    adjust_color as _adjust_color,
    to_hex_rgb as _to_hex_rgb,
    get_contrasting_text_color as _get_contrasting_text_color,
    compute_palette as _compute_palette,
    generate_stylesheet as _generate_stylesheet,
)
        
# (clear_layout moved to src/ui/utils.py)

class ThemeManager(QObject):
    """Manages application themes and color calculations"""

    theme_changed = Signal()
    theme_applied = Signal(float)
    
    # Built-in theme names that are protected from deletion
    BUILT_IN_THEMES = ['Dark', 'Light', 'Nebula', 'Sunset', 'Ocean']

    def __init__(self, settings_manager):
        super().__init__()
        self.settings_manager = settings_manager
        self.themes_dir = settings_manager.get_themes_dir()
        # Theme storage
        self.available_themes: Dict[str, Dict[str, Any]] = {}
        self.current_theme: Dict[str, Any] = {}
        # Stylesheet cache
        self._cached_stylesheet: str | None = None
        self._cached_signature: Tuple[Tuple[str, str], ...] = ()
        self._cached_palette: Dict[str, str] | None = None
        self._palette_signature: Tuple[Tuple[str, str], ...] = ()
        self._pending_app: QApplication | None = None
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.timeout.connect(self._flush_pending_apply)
        self._is_applying = False
        self._apply_start_time = None
        # Initialize themes
        self._ensure_default_themes()
        self._load_available_themes()
        self._load_current_theme()
    
    def _ensure_default_themes(self):
        """Create default theme files if they don't exist.
        Simplified: store only base inputs and structural radii; derived fields are computed at load time.
        """
        # Ensure themes directory exists
        try:
            os.makedirs(self.themes_dir, exist_ok=True)
        except Exception:
            pass
        default_themes = {
            'Dark': {
                'name': 'Dark',
                'base_background': '#141414',
                'base_primary': '#3f5485',
                'base_accent': '#5f92ff',
                'corner_radius': 8,
                'scrollbar_radius': 8,
            },
            'Light': {
                'name': 'Light',
                'base_background': '#e6e6e6',
                'base_primary': '#8787ff',
                'base_accent': '#ba82ff',
                'corner_radius': 8,
                'scrollbar_radius': 8,
            },
            'Nebula': {
                'name': 'Nebula',
                'base_background': '#0b0b1a',
                'base_primary': '#7b61ff',
                'base_accent': '#00aaff',
                'corner_radius': 8,
                'scrollbar_radius': 8,
            },
            'Sunset': {
                'name': 'Sunset',
                'base_background': '#2d1b1b',
                'base_primary': '#ff7f3f',
                'base_accent': '#ff9f3f',
                'corner_radius': 8,
                'scrollbar_radius': 8,
            },
            'Ocean': {
                'name': 'Ocean',
                'base_background': '#0a1a2a',
                'base_primary': '#1e90ff',
                'base_accent': '#20b2aa',
                'corner_radius': 8,
                'scrollbar_radius': 8,
            }
        }
        
        for theme_name, theme_data in default_themes.items():
            theme_file = os.path.join(self.themes_dir, f"{theme_name}.json")
            if not os.path.exists(theme_file):
                try:
                    with open(theme_file, 'w', encoding='utf-8') as f:
                        json.dump(theme_data, f, indent=2)
                except Exception:
                    pass  # Fail silently if we can't create the file
    
    def _load_available_themes(self):
        """Load all available themes from the themes directory"""
        self.available_themes = {}
        
        if not os.path.exists(self.themes_dir):
            return
        
        for filename in os.listdir(self.themes_dir):
            if filename.endswith('.json'):
                theme_file = os.path.join(self.themes_dir, filename)
                try:
                    with open(theme_file, 'r', encoding='utf-8') as f:
                        theme_data = json.load(f)
                        theme_name = theme_data.get('name', filename[:-5])  # Remove .json
                        self.available_themes[theme_name] = theme_data
                except Exception:
                    continue  # Skip invalid theme files
    
    def _load_current_theme(self):
        """Load the current theme from settings"""
        current_theme_name = self.settings_manager.get('current_theme', 'Dark')
        
        if current_theme_name in self.available_themes:
            self.current_theme = self.available_themes[current_theme_name].copy()
            # Ensure derived values exist even if theme file only has base colors
            self._recompute_from_base()
        else:
            # Fallback to default theme
            self.current_theme = self._get_fallback_theme()
            self.settings_manager.set('current_theme', 'Dark')
    
    def _get_fallback_theme(self) -> Dict[str, Any]:
        """Get fallback theme when no valid theme is found"""
        return {
            'name': 'Dark',
            'base_background': '#252524',
            'base_primary': '#0078d4',
            'base_accent': '#1db954',
            'corner_radius': 4,
            'scrollbar_radius': 4,
            'description': 'Fallback theme'
        }
    
    
    def get_available_themes(self) -> List[str]:
        """Get list of available theme names"""
        return list(self.available_themes.keys())
    
    def get_theme_info(self, theme_name: str) -> Dict[str, Any]:
        """Get theme information by name"""
        return self.available_themes.get(theme_name, {})
    
    def get_built_in_themes(self) -> List[str]:
        """Get list of built-in theme names that are protected from deletion"""
        return self.BUILT_IN_THEMES.copy()
    
    def get_custom_themes(self) -> List[str]:
        """Get list of custom (non-built-in) theme names"""
        return [name for name in self.get_available_themes() if name not in self.BUILT_IN_THEMES]
    
    def set_theme(self, theme_name: str, theme_data: Dict[str, Any] | None = None):
        """Set the current theme by name or data. For live edits, apply instantly."""
        if theme_data is not None:
            # Use provided theme data (for real-time editing)
            self.current_theme = theme_data.copy()
            # Always derive the palette from base if present/inferable
            self._recompute_from_base()
            self._invalidate_stylesheet()
            self._mark_palette_dirty()
            try:
                app = QApplication.instance()
                if app:
                    self.apply_theme(app)
            except Exception:
                pass
            self.theme_changed.emit()  # Instant update
        elif theme_name in self.available_themes:
            # Load theme from file
            self.current_theme = self.available_themes[theme_name].copy()
            self._recompute_from_base()
            self.settings_manager.set('current_theme', theme_name)
            # Invalidate cache and apply so colors update without needing a radius change
            self._invalidate_stylesheet()
            self._mark_palette_dirty()
            try:
                app = QApplication.instance()
                if app:
                    self.apply_theme(app)
            except Exception:
                pass
            self.theme_changed.emit()
        else:
            # Fallback
            self.current_theme = self._get_fallback_theme()
            self._mark_palette_dirty()
    
    def set_corner_radius(self, radius: int, *, silent: bool = False):
        """Update base corner radius. If silent, don't emit theme_changed (used for live preview)."""
        try:
            radius_val = max(0, int(radius))
        except Exception:
            return
        # If scrollbar_radius is not explicitly set in the theme, make it explicit
        # using the current effective scrollbar radius so that changing the
        # global corner radius won't implicitly alter scrollbars or sliders.
        if 'scrollbar_radius' not in self.current_theme:
            # Determine the effective current radius (fallback to 4 if missing)
            try:
                current_sb = int(self.current_theme.get('scrollbar_radius', self.current_theme.get('corner_radius', 4)))
            except Exception:
                current_sb = 4
            # Set explicit scrollbar radius to preserve independence
            self.current_theme['scrollbar_radius'] = current_sb

        if self.current_theme.get('corner_radius') == radius_val:
            return
        self.current_theme['corner_radius'] = radius_val
        self._invalidate_stylesheet()
        if not silent:
            self.theme_changed.emit()

    def set_scrollbar_radius(self, radius: int, *, silent: bool = False):
        """Update scrollbar corner radius independently of base radius."""
        try:
            radius_val = max(0, int(radius))
        except Exception:
            return
        if self.current_theme.get('scrollbar_radius') == radius_val:
            return
        self.current_theme['scrollbar_radius'] = radius_val
        self._invalidate_stylesheet()
        if not silent:
            self.theme_changed.emit()
    
    
    def save_theme(self, theme_name: str, theme_data: Dict[str, Any]) -> bool:
        """Save a theme to file"""
        try:
            os.makedirs(self.themes_dir, exist_ok=True)
            theme_file = os.path.join(self.themes_dir, f"{theme_name}.json")
            theme_data_copy = theme_data.copy()
            theme_data_copy['name'] = theme_name
            
            with open(theme_file, 'w', encoding='utf-8') as f:
                json.dump(theme_data_copy, f, indent=2)
            
            # Reload available themes
            self._load_available_themes()
            return True
        except Exception:
            return False
        
    def apply_theme(self, app: QApplication | None, *, immediate: bool = False):
        """Apply theme to QApplication using coalesced updates."""
        if app is None:
            return
        self._ensure_apply_start_time()
        if immediate:
            self._pending_app = app
            self._flush_pending_apply()
            return
        self._pending_app = app
        if not self._apply_timer.isActive():
            try:
                self._apply_timer.start(0)
            except Exception:
                self._flush_pending_apply()

    def _flush_pending_apply(self):
        if self._is_applying:
            return
        app = self._pending_app or QApplication.instance()
        self._apply_timer.stop()
        self._pending_app = None
        if app is None:
            return
        self._perform_apply(app)

    def _perform_apply(self, app: QApplication):
        if self._is_applying:
            return
        self._is_applying = True
        top_levels = list(app.topLevelWidgets())
        for w in top_levels:
            try:
                w.setUpdatesEnabled(False)
            except Exception:
                pass
        try:
            self._ensure_stylesheet()
            self._clear_top_level_widget_styles(app, top_levels)
            app.setStyleSheet(self._cached_stylesheet or "")
        finally:
            for w in top_levels:
                try:
                    w.setUpdatesEnabled(True)
                    w.update()
                except Exception:
                    pass
            self._is_applying = False
        self._emit_apply_duration()

    def _build_signature(self, theme: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
        """Create a compact cache signature based only on inputs that affect CSS.

        This keeps caching simple and stable while avoiding noise from
        unrelated keys that may be present in the theme dict.
        """
        keys = (
            'base_background',
            'base_primary',
            'base_accent',
            'corner_radius',
            'scrollbar_radius',
        )
        return tuple((k, str(theme.get(k))) for k in keys)

    def _ensure_stylesheet(self):
        theme = self.current_theme
        signature = self._build_signature(theme)
        if signature != self._cached_signature or not self._cached_stylesheet:
            try:
                text_color = _get_contrasting_text_color(theme.get('base_background', '#252524'))
                self.settings_manager._create_arrow_svg(text_color)
            except Exception:
                pass
            self._cached_stylesheet = _generate_stylesheet(
                theme, app_data_dir=self.settings_manager.get_app_data_dir()
            )
            self._cached_signature = signature

    def _clear_top_level_widget_styles(self, app: QApplication, widgets: List[Any] | None = None):
        """Clear widget-level style sheets applied during preview so global app stylesheet updates all widgets.
        We only clear top-level widgets to avoid removing intentional per-control overrides (e.g., color buttons)."""
        targets = widgets if widgets is not None else app.topLevelWidgets()
        for w in targets:
            # Skip if widget explicitly opts out
            try:
                if getattr(w, '_preserve_stylesheet', False):
                    continue
            except Exception:
                pass
            if w.styleSheet():
                w.setStyleSheet("")
    
    def delete_theme(self, theme_name: str) -> bool:
        """Delete a custom theme (built-in themes are protected)"""
        if theme_name in self.BUILT_IN_THEMES:
            return False  # Protect built-in themes

        try:
            theme_file = os.path.join(self.themes_dir, f"{theme_name}.json")
            if os.path.exists(theme_file):
                os.remove(theme_file)
                self._load_available_themes()
                return True
        except Exception:
            pass
        return False
    
    def get_stylesheet(self) -> str:
        """Return (and cache) current stylesheet string without applying to QApplication."""
        self._ensure_stylesheet()
        return self._cached_stylesheet

    def apply_stylesheet_to(self, widget):
        """Apply current stylesheet only to a specific widget (for lightweight previews)."""
        if widget is None:
            return
        widget.setStyleSheet(self.get_stylesheet())
    
    def invalidate_cache(self):
        """Force cache invalidation for next stylesheet generation."""
        self._invalidate_stylesheet()
    
    # --- Simplified theming API: three base colors -> full palette ---
    def set_base_colors(self, background: str | None = None, primary: str | None = None, accent: str | None = None, *, silent: bool = False):
        """Update base colors (background, primary, accent) and recompute derived palette.
        Accepts any subset; unspecified values keep current ones."""
        t = self.current_theme
        if background:
            t['base_background'] = background
        if primary:
            t['base_primary'] = primary
        if accent:
            t['base_accent'] = accent
        self._recompute_from_base()
        self._invalidate_stylesheet()
        # Apply and notify
        try:
            app = QApplication.instance()
            if app:
                self.apply_theme(app)
        except Exception:
            pass
        if not silent:
            self.theme_changed.emit()

    def _recompute_from_base(self):
        """Derive full palette fields from three base inputs, preserving backward compatibility."""
        t = self.current_theme
        bg = t.get('base_background') or '#252524'
        primary = t.get('base_primary') or '#0078d4'
        accent = t.get('base_accent') or '#1db954'
        # Persist base keys
        t['base_background'] = bg
        t['base_primary'] = primary
        t['base_accent'] = accent
        self._mark_palette_dirty()
    # No legacy-derived keys stored. Widgets/stylesheet compute from base_* on the fly.

    def get_hover_color(self, base_color: str) -> str:
        """Get hover color for a button"""
        return _adjust_color(base_color, 0.1)
    
    def get_palette(self) -> Dict[str, str]:
        """Compute the full derived color palette from current theme base colors.
        
        Returns a dict with all computed colors used by widgets and stylesheet.
        Uses the shared compute_palette() function to ensure consistency.
        
        Keys include:
        - bg_color, text_color, primary_color, accent_color
        - primary_off_color, border_color, hover_color, pressed_color
        - input_bg_color, disabled_primary_color, disabled_text_color
        - toggle_bg_off, toggle_bg_on, toggle_handle
        - ... and many more (see colors.compute_palette() for full list)
        """
        signature = self._build_signature(self.current_theme)
        if self._cached_palette is None or signature != self._palette_signature:
            self._cached_palette = _compute_palette(self.current_theme)
            self._palette_signature = signature
        return self._cached_palette

    def _mark_palette_dirty(self):
        self._cached_palette = None
        self._palette_signature = ()

    def _invalidate_stylesheet(self):
        self._cached_stylesheet = None
        self._cached_signature = ()

    def _ensure_apply_start_time(self):
        if self._apply_start_time is None:
            self._apply_start_time = perf_counter()

    def _emit_apply_duration(self):
        if self._apply_start_time is None:
            return
        elapsed_ms = (perf_counter() - self._apply_start_time) * 1000.0
        self._apply_start_time = None
        try:
            self.theme_applied.emit(elapsed_ms)
        except Exception:
            pass

