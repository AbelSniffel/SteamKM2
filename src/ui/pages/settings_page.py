"""
Settings Page - Refactored version with mixin pattern.

This module provides the main settings interface, using mixin classes
to organize event handlers into separate modules for maintainability.
"""

import os
import subprocess
import platform
from dataclasses import dataclass
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QColorDialog, QMessageBox, QApplication,
    QSlider, QComboBox, QSpinBox, QStackedWidget, QFileDialog, QDialog
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QColor, QCursor

from src.ui.pages.base_page import BasePage
from src.ui.widgets.main_widgets import create_push_button, create_scroll_area
from src.ui.widgets.sidebar import Sidebar
from src.ui.pages.settings_handlers import (
    SettingsSectionBuilder,
    SearchAnimationHandler,
    SettingsEventHandlers,
    ThemeHandlers,
    DataHandlers,
)


# Display-to-value mappings (shared between SettingsPage and SettingsSectionBuilder)
APPEARANCE_MAP = {
    'Icon & Text': 'icon_and_text',
    'Icon': 'icon_only',
    'Text': 'text_only',
}

GRADIENT_ANIMATION_MAP = {
    'Scroll': 'scroll',
    'Pulse': 'pulse',
    'Scanner': 'scanner',
    'Heart': 'heart',
}

# Pre-computed reverse maps for faster lookups
_APPEARANCE_REVERSE_MAP = {v: k for k, v in APPEARANCE_MAP.items()}
_GRADIENT_ANIMATION_REVERSE_MAP = {v: k for k, v in GRADIENT_ANIMATION_MAP.items()}


def get_index_from_value(value, mapping, reverse_map):
    """Get index in mapping options from value using pre-computed reverse map."""
    display = reverse_map.get(value, next(iter(mapping.keys())))
    try:
        return list(mapping.keys()).index(display)
    except ValueError:
        return 0


@dataclass
class _SectionRecord:
    page_key: str
    widget: QWidget
    home_layout: QVBoxLayout
    order: int
    current_owner: str
    current_layout: QVBoxLayout


class SettingsPage(SettingsEventHandlers, ThemeHandlers, DataHandlers, BasePage):
    """
    Settings page with all configuration options.
    
    Uses mixin pattern to delegate handler methods to separate modules:
    - SettingsEventHandlers: Import/export, encryption, toggles, database handlers
    - ThemeHandlers: Theme colors, radius, save/delete themes
    - DataHandlers: Tags, platforms, encryption controls, health status
    """
    
    status_message = Signal(str)
    page_navigation_bar_position_changed = Signal(str)
    page_navigation_bar_appearance_changed = Signal(str)
    status_bar_visibility_changed = Signal(bool)
    tags_updated = Signal()
    encryption_status_changed = Signal(bool)

    def __init__(self, db_manager, theme_manager, settings_manager):
        super().__init__(db_manager, theme_manager, settings_manager, title="Settings Menu")
        
        self._customizing = False
        self._is_initializing = True
        
        # Initialize handlers
        self.section_builder = SettingsSectionBuilder(self)
        self.search_handler = SearchAnimationHandler(self)
        
        # Caches
        self._button_color_cache = {}
        
        # Section tracking
        self._page_layouts = {}
        self._sections_by_page = {}
        self._section_records = []
        self._page_key_by_index = []
        self._page_sequence = []
        self._suppress_sidebar_signal = False
        self._suppress_stack_signal = False
        self._current_page_key = None
        self._previous_page_key = None
        self._search_active = False
        
        # Radius preview timers
        self._radius_timers = {
            'corner': {
                'timer': QTimer(),
                'active': False,
                'theme_key': 'corner_radius',
                'apply_method': lambda v: self.theme_manager.set_corner_radius(v, silent=False),
                'preview_callback': None
            },
            'scrollbar': {
                'timer': QTimer(),
                'active': False,
                'theme_key': 'scrollbar_radius',
                'apply_method': lambda v: self.theme_manager.set_scrollbar_radius(v, silent=False),
                'preview_callback': None
            }
        }
        
        for key, data in self._radius_timers.items():
            data['timer'].setSingleShot(True)
            data['timer'].setInterval(4)
            data['timer'].timeout.connect(lambda k=key: self._regenerate_radius_stylesheet(k))
        
        self._setup_ui()
        self._connect_signals()
        self.refresh()
        self._is_initializing = False
    
    # =========================================================================
    # UI Setup
    # =========================================================================
    
    def _setup_ui(self):
        """Build the settings page UI."""
        self._build_header_actions()

        self._page_sequence = [
            ('all', 'All', None),
            ('general', 'General', self.section_builder.create_general_section),
            ('database', 'Database', self.section_builder.create_database_section),
            ('updates', 'Updates', self.section_builder.create_updates_section),
            ('theme', 'Theme & UI', self.section_builder.create_theme_customization_section),
            ('tags', 'Tags', self.section_builder.create_tags_section),
            ('debug', 'Debug', self.section_builder.create_debug_page),
        ]

        self.sidebar = Sidebar(items=[label for _, label, _ in self._page_sequence])
        self.sidebar.set_search_placeholder("Search settings...")

        self.stack = QStackedWidget()

        def make_page(page_key, build_fn):
            page_widget = QWidget()
            v = QVBoxLayout(page_widget)
            v.setAlignment(Qt.AlignTop)
            self._page_layouts[page_key] = v
            if build_fn is not None:
                build_fn(page_key, v)
            return create_scroll_area(
                widget=page_widget,
                widget_resizable=True,
                horizontal_policy=Qt.ScrollBarPolicy.ScrollBarAsNeeded,
                alignment=Qt.AlignTop
            )

        for key, _, builder in self._page_sequence:
            self._page_key_by_index.append(key)
            self.stack.addWidget(make_page(key, builder))

        self.body_layout.addWidget(self.stack)
        self.set_sidebar(self.sidebar)

        try:
            self.stack.currentChanged.connect(self._on_stack_index_changed)
            self.sidebar.currentIndexChanged.connect(self._on_sidebar_index_changed)
            self.sidebar.searchTextChanged.connect(self._on_sidebar_search_changed)
        except Exception:
            pass

        self._set_current_page('all')
        QTimer.singleShot(0, self._update_color_buttons)

    def _build_header_actions(self):
        """Add quick actions to the header bar."""
        try:
            self.header_layout.setSpacing(6)
        except Exception:
            pass

        self.health_status_label = QLabel("Loading...")
        self.health_status_label.setStyleSheet("color: #666;")

        self.health_monitor_btn = create_push_button("Health Monitor", object_name="page_header_button")
        self.health_monitor_btn.setToolTip("Open the health monitoring window (F12)")
        self.health_monitor_btn.clicked.connect(
            lambda: (self.window().toggle_health_monitor() 
                    if self.window() and hasattr(self.window(), 'toggle_health_monitor') else None)
        )

        self.open_config_btn = create_push_button("Open Data Folder", object_name="page_header_button")
        self.open_config_btn.setToolTip("Open the folder containing your SteamKM2 data")
        self.open_config_btn.clicked.connect(self._open_config_folder)

        self.btn_reset = create_push_button("Reset to Defaults", object_name="page_header_button")
        self.btn_reset.setToolTip("Restore all settings to their default values")
        self.btn_reset.clicked.connect(self._reset_defaults_and_reload)

        self.header_layout.addStretch()
        self.header_layout.addWidget(self.health_status_label)
        self.header_layout.addWidget(self.health_monitor_btn)
        self.header_layout.addWidget(self.open_config_btn)
        self.header_layout.addWidget(self.btn_reset)

        try:
            self._health_timer = QTimer(self)
            self._health_timer.timeout.connect(self._update_health_status)
            self._health_timer.start(2000)
        except Exception:
            pass

    def _connect_signals(self):
        """Connect UI signals."""
        self.auto_update_toggle.toggled.connect(self._on_auto_update_toggled)
        self.theme_manager.theme_changed.connect(
            self._update_color_buttons, 
            Qt.ConnectionType.UniqueConnection
        )
        self.encryption_toggle.toggled.connect(self._on_encryption_toggle_requested)

    # =========================================================================
    # Section Management
    # =========================================================================

    def _register_section(self, page_key, layout, widget):
        """Register a section widget for page management."""
        records = self._sections_by_page.setdefault(page_key, [])
        record = _SectionRecord(
            page_key=page_key,
            widget=widget,
            home_layout=layout,
            order=len(records),
            current_owner=page_key,
            current_layout=layout,
        )
        records.append(record)
        self._section_records.append(record)
        self.search_handler.cache_widget_text(record)
        return record

    def _add_section(self, page_key, layout, widget):
        """Add a section widget to a page layout."""
        layout.addWidget(widget)
        self._register_section(page_key, layout, widget)

    # =========================================================================
    # Page Navigation
    # =========================================================================

    def _set_current_page(self, page_key: str):
        """Set the current page by key."""
        try:
            index = self._page_key_by_index.index(page_key)
        except ValueError:
            return
        if self.stack.currentIndex() != index:
            self._suppress_stack_signal = True
            self.stack.setCurrentIndex(index)
            self._suppress_stack_signal = False
        self._handle_page_change(index)

    def _handle_page_change(self, index: int):
        """Handle page change logic."""
        if not (0 <= index < len(self._page_key_by_index)):
            return
        page_key = self._page_key_by_index[index]
        self._current_page_key = page_key
        if not self._search_active:
            self._move_sections_for_page(page_key)
            for record in self._section_records:
                record.widget.setVisible(True)
        self._suppress_sidebar_signal = True
        try:
            if self.sidebar.current_index() != index:
                self.sidebar.select_index(index)
        finally:
            self._suppress_sidebar_signal = False

    def _on_sidebar_index_changed(self, index: int):
        """Handle sidebar index change."""
        if self._suppress_sidebar_signal:
            return
        if not (0 <= index < len(self._page_key_by_index)):
            return
        page_key = self._page_key_by_index[index]
        if self._search_active and page_key != 'all':
            self._set_current_page('all')
            return
        self._set_current_page(page_key)

    def _on_stack_index_changed(self, index: int):
        """Handle stack widget index change."""
        if self._suppress_stack_signal:
            return
        if not (0 <= index < len(self._page_key_by_index)):
            return
        page_key = self._page_key_by_index[index]
        if self._search_active and page_key != 'all':
            self._set_current_page('all')
            return
        self._handle_page_change(index)

    # =========================================================================
    # Search Handling
    # =========================================================================

    def _on_sidebar_search_changed(self, text: str):
        """Handle search text changes."""
        query = (text or '').strip()
        if not query:
            if not self._search_active:
                return
            self._search_active = False
            self.search_handler.cleanup_all_animations()
            for record in self._section_records:
                record.widget.setVisible(True)
            for key, _, _ in self._page_sequence:
                if key == 'all':
                    continue
                self._move_sections_for_page(key)
            target = self._previous_page_key or self._current_page_key or 'all'
            self._previous_page_key = None
            self._set_current_page(target)
            return

        normalized = query.lower()
        if not self._search_active:
            self._previous_page_key = self._current_page_key or 'all'
        self._search_active = True
        self._set_current_page('all')
        self._move_sections_for_page('all')

        self.search_handler.cleanup_all_animations()
        self.search_handler.reset_animation_counter()

        for record in self._section_records:
            matches = self.search_handler.section_matches(record, normalized)
            record.widget.setVisible(matches)
            if matches:
                matching_widgets = self.search_handler.find_matching_widgets(record.widget, normalized)
                if matching_widgets:
                    for match_widget in matching_widgets:
                        self.search_handler.apply_fade_highlight(match_widget)
                        self.search_handler.increment_animation_counter()
                else:
                    self.search_handler.apply_fade_highlight(record.widget)
                    self.search_handler.increment_animation_counter()

    # =========================================================================
    # Section Movement
    # =========================================================================

    def _move_sections_for_page(self, page_key: str):
        """Move sections to appropriate layouts for the given page."""
        if not self._page_layouts:
            return
        if page_key == 'all':
            position = 0
            for key, _, _ in self._page_sequence:
                if key == 'all':
                    continue
                for record in self._sections_by_page.get(key, []):
                    self._move_section(record, 'all', insert_at=position)
                    position += 1
            return

        for record in self._sections_by_page.get(page_key, []):
            self._move_section(record, page_key, insert_at=record.order)

    def _move_section(self, record: _SectionRecord, target_key: str, insert_at=None):
        """Move a section widget to a target layout."""
        target_layout = self._page_layouts.get('all') if target_key == 'all' else record.home_layout
        if target_layout is None:
            return

        if insert_at is None or insert_at < 0:
            insert_at = target_layout.count()
        else:
            insert_at = min(insert_at, target_layout.count())

        if record.current_layout is target_layout:
            current_index = target_layout.indexOf(record.widget)
            if current_index == -1:
                target_layout.insertWidget(insert_at, record.widget)
            elif current_index != insert_at:
                self._remove_widget_from_layout(target_layout, record.widget)
                target_layout.insertWidget(insert_at, record.widget)
            return

        if record.current_layout is not None:
            self._remove_widget_from_layout(record.current_layout, record.widget)

        target_layout.insertWidget(insert_at, record.widget)
        record.current_owner = target_key
        record.current_layout = target_layout

    def _remove_widget_from_layout(self, layout, widget):
        """Remove a widget from a layout without destroying it."""
        if layout is None or widget is None:
            return
        index = layout.indexOf(widget)
        if index != -1:
            layout.takeAt(index)

    # =========================================================================
    # Refresh & State
    # =========================================================================

    def refresh(self):
        """Refresh the page data and UI controls."""
        _, locked = self._update_encryption_controls()
        if locked:
            self._notify('warning', "Failed to get available tags, please unlock the database.")
            self.status_message.emit("Database locked — unlock from Home to manage data settings")
            return
        self._load_tags()
        self._load_platforms()
        self._update_backup_info()
        self._refresh_ui_controls()
        self.status_message.emit("Settings loaded")
    
    def _refresh_ui_controls(self):
        """Refresh all UI control states from settings."""
        try:
            sm = self.settings_manager
            
            # Toggle refreshes
            toggles = [
                ('status_bar_toggle', 'show_status_bar', False),
                ('debug_mode_toggle', 'debug_mode', False),
                ('auto_update_toggle', 'auto_update_check', True),
                ('auto_backup_toggle', 'auto_backup_enabled', True),
                ('prerelease_toggle', 'update_include_prereleases', False),
                ('show_unikm_github_button_toggle', 'show_unikm_github_button', True),
            ]
            for attr, key, default in toggles:
                if toggle := getattr(self, attr, None):
                    checked = sm.get_bool(key, default)
                    if toggle.isChecked() != checked:
                        toggle.setCheckedAnimated(checked)
            
            # Spinbox refreshes
            spinboxes = [
                ('backup_interval_spinbox', 'auto_backup_interval_minutes', 5),
                ('max_backup_spinbox', 'backup_max_count', 10),
                ('interval_spin', 'update_check_interval_min', 5),
                ('tooltip_show_delay_spinbox', 'tooltip_show_delay', 500),
            ]
            for attr, key, default in spinboxes:
                if spinbox := getattr(self, attr, None):
                    spinbox.setValue(sm.get_int(key, default))
            
            # Combo boxes
            if combo := getattr(self, 'tooltip_animation_combo', None):
                combo.setCurrentText(sm.get('tooltip_animation', 'Fade'))
            
            # Multi-step toggles
            multisteps = [
                ('section_title_location_toggle', 'section_groupbox_title_location', 'left', {'left': 0, 'top': 1}),
                ('toggle_style_toggle', 'toggle_style', 'regular', {'regular': 0, 'dot': 1}),
            ]
            for attr, key, default, index_map in multisteps:
                if toggle := getattr(self, attr, None):
                    value = sm.get(key, default)
                    index = index_map.get(value, 0)
                    if toggle.get_position() != index:
                        toggle.set_position(index, animated=True)
            
            # Page navigation toggles
            if nav_pos := getattr(self, 'page_navigation_bar_position_toggle', None):
                pos = sm.get('page_navigation_bar_position', 'left').capitalize()
                options = ["Left", "Top", "Bottom", "Right"]
                try:
                    index = options.index(pos)
                    if nav_pos.get_position() != index:
                        nav_pos.set_position(index, animated=True)
                except ValueError:
                    pass
            
            if nav_app := getattr(self, 'page_navigation_bar_appearance_toggle', None):
                app_val = sm.get('page_navigation_bar_appearance', 'icon_and_text')
                app_index = get_index_from_value(app_val, APPEARANCE_MAP, _APPEARANCE_REVERSE_MAP)
                if nav_app.get_position() != app_index:
                    nav_app.set_position(app_index, animated=True)
                
                pos = sm.get('page_navigation_bar_position', 'left')
                tooltip = ("Note: while nav bar is Left/Right, appearance will be ignored (Icon Only). "
                          "Setting is still saved.") if pos in ('left', 'right') else ""
                nav_app.setToolTip(tooltip)
            
            # Gradient animation toggle
            if grad := getattr(self, 'gradient_animation_toggle', None):
                current_anim = sm.get('gradient_animation', 'scroll')
                anim_index = get_index_from_value(current_anim, GRADIENT_ANIMATION_MAP, _GRADIENT_ANIMATION_REVERSE_MAP)
                if grad.get_position() != anim_index:
                    grad.set_position(anim_index, animated=True)
            
            # Text inputs
            if repo := getattr(self, 'repo_input', None):
                repo.setText(sm.get('update_repo', 'AbelSniffel/SteamKM2'))
            if api := getattr(self, 'api_token_input', None):
                api.setText(sm.get('github_api_token', ''))
            if unikm_repo := getattr(self, 'unikm_repo_input', None):
                unikm_repo.setText(sm.get('unikm_repo', 'AbelSniffel/UniKM'))
                
        except Exception as e:
            print(f"Error refreshing UI controls: {e}")

    def get_status_message(self):
        """Get status message for this page."""
        return "Configure application settings"

    # =========================================================================
    # Event Filter
    # =========================================================================

    def eventFilter(self, obj, event):
        """Filter events for custom handling."""
        if self._customizing and event.type() == QEvent.MouseButtonPress:
            if isinstance(obj, QPushButton) and not obj.objectName():
                initial = self.theme_manager.current_theme.get('base_primary', '#000000')
                color = QColorDialog.getColor(QColor(initial), self)
                if color.isValid():
                    self.theme_manager.set_base_colors(primary=color.name())
                    self._safe_theme_changed()
                    self.status_message.emit(f"Primary color set to {color.name()}")
                return True

        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QComboBox, QSlider, QSpinBox)):
                return True

        return super().eventFilter(obj, event)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_active_window(self):
        """Get the currently active window."""
        if app := QApplication.instance():
            return app.activeWindow()
        return None

    def _safe_theme_changed(self):
        """Safely emit theme changed signal."""
        try:
            self.theme_manager.theme_changed.emit()
        except Exception:
            pass

    def _set_primary_color(self, btn: QPushButton, color: str):
        """Set button color with hover effect."""
        hover_color = self.theme_manager.get_hover_color(color)
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; }} "
            f"QPushButton:hover {{ background-color: {hover_color}; }}"
        )
        btn.setText(color)

    def _bind_slider_spin(self, slider: QSlider, spin: QSpinBox, *, minimum: int, maximum: int, 
                          value: int, on_preview, on_commit):
        """Bind a slider and spinbox together with preview and commit callbacks."""
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setSingleStep(1)
        slider.setPageStep(2)
        slider.setTracking(True)
        slider.setValue(value)
        spin.setMinimum(minimum)
        spin.setMaximum(maximum)
        spin.setValue(value)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        slider.valueChanged.connect(on_preview)
        spin.valueChanged.connect(on_preview)
        slider.sliderReleased.connect(on_commit)
        spin.editingFinished.connect(on_commit)
        slider.installEventFilter(self)
        spin.installEventFilter(self)
        spin.setFixedWidth(75)
        return slider, spin

    def _notify(self, kind: str, message: str, duration=None):
        """Show a notification to the user."""
        try:
            return super()._notify(kind, message, duration)
        except Exception:
            if kind == 'error':
                QMessageBox.critical(self, "Error", message)
            elif kind == 'warning':
                QMessageBox.warning(self, "Warning", message)
            else:
                self.status_message.emit(message)

    def _clickable_label_for(self, text: str, toggle) -> QLabel:
        """Create a clickable label that toggles the given toggle widget."""
        lbl = QLabel(text)
        lbl.setCursor(QCursor(Qt.PointingHandCursor))

        def _on_click(event=None):
            for method in ('toggle', 'setCheckedNoAnimation', 'setChecked'):
                try:
                    if method == 'toggle':
                        toggle.toggle()
                    else:
                        getattr(toggle, method)(not toggle.isChecked())
                    return
                except Exception:
                    continue

        lbl.mouseReleaseEvent = _on_click
        return lbl
    
    def _add_toggle_row(self, form_layout, label_text: str, toggle, show_label: bool = None):
        """Add a toggle to a form layout with optional label."""
        if show_label is None:
            show_label = True
        
        if show_label:
            form_layout.addRow(self._clickable_label_for(label_text, toggle), toggle)
        else:
            form_layout.addRow(toggle)
