"""
Section builder for Settings Page.
Handles creation of all settings sections to reduce the main class size.

OPTIMIZED: Uses helper methods to reduce repetitive form row creation patterns.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QListWidget, 
    QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt
from src.ui.widgets.main_widgets import create_push_button, create_line_edit, create_spin_box, create_combo_box
from src.ui.widgets.toggles import MultiStepToggle
from src.ui.widgets.toggles.styleable_toggle import StyleableLabel
from src.ui.widgets.color_picker_button import LinkedColorPickerPair, ColorPickerButton
from src.ui.widgets.section_groupbox import SectionGroupBox
from src.ui.config import ELEMENT_HEIGHT
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.ui_factory import UIFactory


class SettingsSectionBuilder:
    """Handles creation of all settings sections"""
    
    def __init__(self, settings_page):
        """
        Initialize with reference to parent SettingsPage
        
        Args:
            settings_page: The parent SettingsPage instance
        """
        self.page = settings_page
        self.db_manager = settings_page.db_manager
        self.theme_manager = settings_page.theme_manager
        self.settings_manager = settings_page.settings_manager
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to a human-readable string for display (e.g. 1.2 MB)."""
        try:
            size = float(size_bytes)
        except Exception:
            return "Unknown size"
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024 or unit == 'GB':
                return f"{int(size)} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    # =========================================================================
    # Form Row Helpers - Reduce repetitive layout creation
    # =========================================================================
    
    def _create_toggle(self, setting_key, default_value=True, callback=None, label_text=""):
        """Helper to create and configure a toggle with consistent behavior"""
        toggle = UIFactory.create_toggle(
            settings_manager=self.settings_manager,
            theme_manager=self.theme_manager,
            parent=self.page,
            label_text=label_text,
            setting_key=setting_key,
            default_checked=default_value,
            callback=callback
        )
        return toggle
    
    def _add_toggle_row(self, form_layout, label_text: str, toggle, show_label: bool = None):
        """Add a toggle to a form layout with optional label.
        
        Args:
            form_layout: The QFormLayout to add to
            label_text: The label text
            toggle: The toggle widget
            show_label: Deprecated/Ignored - StyleableLabel handles visibility automatically
        """
        # Use StyleableLabel which automatically hides/shows based on toggle style
        label = StyleableLabel(label_text, self.settings_manager, toggle)
        form_layout.addRow(label, toggle)
    
    def _add_widget_row(self, form_layout, label_text: str, widget, width: int = None, 
                        add_stretch: bool = True):
        """Add a widget to a form layout with consistent styling.
        
        Args:
            form_layout: The QFormLayout to add to
            label_text: The label text
            widget: The widget to add
            width: Optional fixed width for the widget
            add_stretch: Whether to add stretch after the widget
            
        Returns:
            The widget (for chaining or further configuration)
        """
        if width:
            widget.setFixedWidth(width)
        
        if add_stretch:
            layout = QHBoxLayout()
            layout.addWidget(widget)
            layout.addStretch()
            form_layout.addRow(QLabel(label_text), layout)
        else:
            form_layout.addRow(QLabel(label_text), widget)
        
        return widget
    
    def _create_button_row(self, *buttons, add_stretch: bool = True) -> QHBoxLayout:
        """Create a horizontal layout with buttons.
        
        Args:
            *buttons: Button widgets to add
            add_stretch: Whether to add stretch at the end
            
        Returns:
            QHBoxLayout containing the buttons
        """
        layout = QHBoxLayout()
        for btn in buttons:
            layout.addWidget(btn)
        if add_stretch:
            layout.addStretch()
        return layout
    
    def create_general_section(self, page_key, parent_layout):
        """General settings and page navigation bar controls."""
        general_settings_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="General Settings",
            inner_orientation=Qt.Horizontal  # Keep horizontal for multi-column layout
        )


        import_export_content = general_settings_group.add_inner_groupbox(title="Settings File")
        ie_layout = QHBoxLayout()
        self.page.btn_import_settings = create_push_button("Import Settings")
        self.page.btn_import_settings.setToolTip("Load settings from a previous export file")
        self.page.btn_import_settings.clicked.connect(self.page._import_settings)
        self.page.btn_export_settings = create_push_button("Export Settings")
        self.page.btn_export_settings.setToolTip("Save the current configuration to a file")
        self.page.btn_export_settings.clicked.connect(self.page._export_settings)
        ie_layout.addWidget(self.page.btn_import_settings)
        ie_layout.addWidget(self.page.btn_export_settings)
        ie_layout.addStretch()
        import_export_content.addLayout(ie_layout)

        self.page._add_section(page_key, parent_layout, general_settings_group)
    
    def create_database_section(self, page_key, parent_layout):
        """Database management including backups and encryption."""
        db_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Database",
            inner_orientation=Qt.Vertical  # Vertical stacking for database sections
        )
        # Store reference for geometry updates
        self.page.db_section_group = db_group

        # Quick Actions
        maintenance_content = db_group.add_inner_groupbox(title="Quick Actions")
        db_layout = QHBoxLayout()
        self.page.btn_backup_db = create_push_button("Backup / Export Database")
        self.page.btn_backup_db.setToolTip("Create a backup of the active database")
        self.page.btn_backup_db.clicked.connect(self.page._backup_database)
        db_layout.addWidget(self.page.btn_backup_db)
        db_layout.addStretch()
        maintenance_content.addLayout(db_layout)

        # Database Switching
        switch_content = db_group.add_inner_groupbox(title="Database File")
        switch_form = QFormLayout()
        
        # Current database path display
        current_db_path = self.settings_manager.get_database_path()
        import os
        self.page.current_db_label = QLabel(os.path.basename(current_db_path))
        self.page.current_db_label.setStyleSheet("font-weight: bold;")
        self.page.current_db_label.setToolTip(current_db_path)
        switch_form.addRow(QLabel("Current:"), self.page.current_db_label)
        
        # Switch database buttons
        switch_row = QHBoxLayout()
        self.page.btn_browse_db = create_push_button("Browse...")
        self.page.btn_browse_db.setToolTip("Select a different database file to switch to")
        self.page.btn_browse_db.clicked.connect(self.page._browse_switch_database)
        switch_row.addWidget(self.page.btn_browse_db)
        
        self.page.btn_default_db = create_push_button("Use Default")
        self.page.btn_default_db.setToolTip("Switch back to the default database location")
        self.page.btn_default_db.clicked.connect(self.page._use_default_database)
        switch_row.addWidget(self.page.btn_default_db)
        
        self.page.btn_new_db = create_push_button("Create New")
        self.page.btn_new_db.setToolTip("Create a new empty database file")
        self.page.btn_new_db.clicked.connect(self.page._create_new_database)
        switch_row.addWidget(self.page.btn_new_db)
        
        self.page.btn_import_db = create_push_button("Import Database")
        self.page.btn_import_db.setToolTip("Restore a database from a backup file")
        self.page.btn_import_db.clicked.connect(self.page._import_database)
        switch_row.addWidget(self.page.btn_import_db)
        
        switch_row.addStretch()
        switch_form.addRow(switch_row)
        
        # Recent databases dropdown
        recent_dbs = self.settings_manager.get_recent_databases()
        if recent_dbs:
            self.page.recent_db_combo = create_combo_box(width=300)
            self.page.recent_db_combo.addItem("Select recent database...")
            for db_path in recent_dbs:
                try:
                    size_bytes = os.path.getsize(db_path)
                    size_str = self._format_size(size_bytes)
                except Exception:
                    size_str = "Unknown size"
                display = f"{os.path.basename(db_path)} ({size_str})"
                self.page.recent_db_combo.addItem(display, db_path)
                # Provide tooltip with full path and size
                idx = self.page.recent_db_combo.count() - 1
                self.page.recent_db_combo.setItemData(idx, f"{db_path}\n{size_str}", Qt.ToolTipRole)
            self.page.recent_db_combo.currentIndexChanged.connect(self.page._on_recent_db_selected)
            switch_form.addRow(self.page.recent_db_combo)
        else:
            self.page.recent_db_combo = None
        
        switch_content.addLayout(switch_form)

        # Encryption
        encryption_content = db_group.add_inner_groupbox(title="Game Encryption")
        enc_layout = QFormLayout()
        encryption_content.addLayout(enc_layout)

        self.page.encryption_status_label = QLabel()
        self.page.encryption_status_label.setWordWrap(True)
        enc_layout.addRow(self.page.encryption_status_label)

        self.page.encryption_toggle = UIFactory.create_toggle(
            settings_manager=self.settings_manager,
            theme_manager=self.theme_manager,
            parent=self.page,
            checked=False,
            label_text="Encrypted Database"
        )

        # Row container holding the toggle and the change-password button
        enc_row = QHBoxLayout()
        enc_row.addWidget(self.page.encryption_toggle)
        self.page.change_password_btn = create_push_button("Change Password")
        self.page.change_password_btn.setToolTip("Update the encryption password for the database")
        self.page.change_password_btn.clicked.connect(self.page._on_change_password_clicked)
        enc_row.addWidget(self.page.change_password_btn)
        enc_row.addStretch()

        # Use StyleableLabel which automatically hides/shows based on toggle style
        label = StyleableLabel("Encrypted Database", self.settings_manager, self.page.encryption_toggle)
        enc_layout.addRow(label, enc_row)

        # Backup Settings
        backup_content = db_group.add_inner_groupbox(title="Backup")
        backup_form = QFormLayout()

        self.page.auto_backup_toggle = self._create_toggle('auto_backup_enabled', True, self.page._on_auto_backup_toggled, label_text="Automatic Backups")
        self._add_toggle_row(backup_form, "Automatic Backups", self.page.auto_backup_toggle)

        self.page.backup_interval_spinbox = create_spin_box(minimum=1, maximum=10080)
        self.page.backup_interval_spinbox.setSuffix(" minutes")
        self.page.backup_interval_spinbox.setValue(self.settings_manager.get_int('auto_backup_interval_minutes', 10))
        self.page.backup_interval_spinbox.valueChanged.connect(self.page._on_backup_interval_changed)
        self.page.backup_interval_spinbox.installEventFilter(self.page)
        self._add_widget_row(backup_form, "Backup Interval:", self.page.backup_interval_spinbox, width=135)

        self.page.max_backup_spinbox = create_spin_box(minimum=1, maximum=20)
        self.page.max_backup_spinbox.setSuffix(" backups")
        self.page.max_backup_spinbox.setValue(self.settings_manager.get_int('backup_max_count', 10))
        self.page.max_backup_spinbox.valueChanged.connect(self.page._on_max_backup_changed)
        self.page.max_backup_spinbox.installEventFilter(self.page)
        self._add_widget_row(backup_form, "Max Backups:", self.page.max_backup_spinbox, width=135)

        backup_content.addLayout(backup_form)

        # Backup Info
        self.page.backup_info_label = QLabel()
        self.page.backup_info_label.setWordWrap(True)
        self.page.backup_info_label.setStyleSheet("QLabel { color: gray; font-size: 11px; }")
        info_row = QHBoxLayout()
        info_row.addWidget(self.page.backup_info_label, 1)
        self.page.backup_refresh_btn = create_push_button("⟲ Refresh", object_name="refresh_button", height=ELEMENT_HEIGHT)
        self.page.backup_refresh_btn.setToolTip("Refresh backup information")
        self.page.backup_refresh_btn.clicked.connect(self.page._on_refresh_backup_info_clicked)
        info_row.addWidget(self.page.backup_refresh_btn)
        info_row.addStretch()
        backup_content.addLayout(info_row)

        self.page._add_section(page_key, parent_layout, db_group)
    
    def create_updates_section(self, page_key, parent_layout):
        """Updates section."""
        updates_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Updates",
            inner_orientation=Qt.Horizontal  # Keep horizontal for multi-column layout
        )

        # Update Checker
        auto_content = updates_group.add_inner_groupbox(title="Update Checker")
        auto_form = QFormLayout()

        self.page.auto_update_toggle = self._create_toggle('auto_update_check', True, label_text="Auto-check for Updates")

        self.page.interval_spin = create_spin_box(minimum=1, maximum=1440)
        self.page.interval_spin.setFixedWidth(85)
        self.page.interval_spin.setValue(self.settings_manager.get_int('update_check_interval_min', 5))
        try:
            self.page.interval_spin.editingFinished.connect(self.page._apply_update_settings)
        except Exception:
            self.page.interval_spin.valueChanged.connect(lambda v: self.page._apply_update_settings())

        self._add_toggle_row(auto_form, "Auto-check for Updates", self.page.auto_update_toggle)
        auto_form.addRow(QLabel("Auto-check interval (min):"), self.page.interval_spin)
        auto_content.addLayout(auto_form)

        # GitHub Repository & API
        github_content = updates_group.add_inner_groupbox(title="GitHub Repository & API")
        github_form = QFormLayout()

        self.page.prerelease_toggle = self._create_toggle('update_include_prereleases', False, label_text="Include prereleases")
        self._add_toggle_row(github_form, "Include prereleases", self.page.prerelease_toggle)

        self.page.repo_input = create_line_edit()
        self.page.repo_input.setPlaceholderText("owner/repo, e.g. AbelSniffel/SteamKM2")
        self.page.repo_input.setText(self.settings_manager.get('update_repo', 'AbelSniffel/SteamKM2'))
        github_form.addRow(QLabel("Repository:"), self.page.repo_input)

        self.page.api_token_input = create_line_edit()
        self.page.api_token_input.setEchoMode(self.page.api_token_input.EchoMode.Password)
        self.page.api_token_input.setPlaceholderText("Optional: GitHub API token for higher rate limits")
        self.page.api_token_input.setText(self.settings_manager.get('github_api_token', ''))
        github_form.addRow(QLabel("GitHub API token:"), self.page.api_token_input)

        self.page.repo_input.editingFinished.connect(self.page._apply_update_settings)
        self.page.api_token_input.editingFinished.connect(self.page._apply_update_settings)
        self.page.prerelease_toggle.toggled.connect(lambda checked: self.page._apply_update_settings())

        github_content.addLayout(github_form)

        unikm_content = updates_group.add_inner_groupbox(title="UniKM")
        unikm_form = QFormLayout()

        self.page.show_unikm_github_button_toggle = self._create_toggle(
            'show_unikm_github_button', True, label_text="Show UniKM Github Button"
        )
        self._add_toggle_row(
            unikm_form,
            "Show UniKM Github Button",
            self.page.show_unikm_github_button_toggle,
        )

        self.page.unikm_repo_input = create_line_edit()
        self.page.unikm_repo_input.setPlaceholderText("owner/repo, e.g. AbelSniffel/UniKM")
        self.page.unikm_repo_input.setText(self.settings_manager.get('unikm_repo', 'AbelSniffel/UniKM'))
        unikm_form.addRow(QLabel("UniKM repository:"), self.page.unikm_repo_input)

        self.page.show_unikm_github_button_toggle.toggled.connect(lambda checked: self.page._apply_update_settings())
        self.page.unikm_repo_input.editingFinished.connect(self.page._apply_update_settings)

        unikm_content.addLayout(unikm_form)

        self.page._add_section(page_key, parent_layout, updates_group)
    
    def create_tags_section(self, page_key, parent_layout):
        """Tag management section."""
        tag_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Tag Management",
            inner_orientation=Qt.Vertical  # Vertical stacking for tag sections
        )

        # Add New Tags
        add_tags_content = tag_group.add_inner_groupbox(title="Tag Creation")

        new_tag_container, self.page.new_tag_input, self.page.save_tag_btn = create_line_edit(
            button_text="Save Tag",
            on_button_clicked=self.page._create_new_tag,
        )
        self.page.save_tag_btn.setToolTip("Add the typed tag to your database")
        self.page.new_tag_input.setFixedWidth(200)
        self.page.new_tag_input.setPlaceholderText("New tag name....")
        new_tag_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        new_tag_row = QHBoxLayout()
        new_tag_row.addWidget(new_tag_container)
        self.page.clear_custom_tags_btn = create_push_button("Remove Custom Tags")
        self.page.clear_custom_tags_btn.setToolTip("Delete all custom tags that you created")
        self.page.clear_custom_tags_btn.clicked.connect(self.page._remove_custom_tags)
        new_tag_row.addWidget(self.page.clear_custom_tags_btn)
        new_tag_row.addStretch()
        add_tags_content.addLayout(new_tag_row)

        # Available Tags
        available_tags_content = tag_group.add_inner_groupbox(title="Available Tags")
        self.page.tags_hbox = FlowLayout(margin=0, spacing=5)
        available_tags_content.addLayout(self.page.tags_hbox)

        self.page._add_section(page_key, parent_layout, tag_group)
    
    def create_platform_info_section(self, page_key, parent_layout, attach_to_group: SectionGroupBox | None = None):
        """Platform detection info section.

        If attach_to_group is provided, the inner groupboxes (Auto-Detected Platforms
        and Key Testing) will be created inside that SectionGroupBox instead of
        a standalone "Platform Detection" section. This lets callers (eg. Debug)
        host the inner content.
        """

        # Create a top-level Platform Detection group only if a target group
        # wasn't provided. If attach_to_group is set, we'll add inner boxes
        # directly to that group instead.
        platform_group = None if attach_to_group is not None else UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Platform Detection",
            size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed),
            inner_orientation=Qt.Vertical  # Vertical stacking for platform sections
        )

        target_group = attach_to_group if attach_to_group is not None else platform_group

        # Detected platforms list
        detected_content = target_group.add_inner_groupbox(title="Auto-Detected Platforms")
        self.page.platform_list = QListWidget()
        self.page.platform_list.setMaximumHeight(120)
        # Make the list non-selectable / non-interactive so clicks do nothing
        # (still visible, not disabled — avoids greying out text)
        self.page.platform_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.page.platform_list.setFocusPolicy(Qt.NoFocus)
        # Keep outline gone and show default cursor so it doesn't appear clickable
        self.page.platform_list.setStyleSheet("outline: none; QListWidget::item { cursor: default; }")
        detected_content.addWidget(self.page.platform_list)

        # Test key input
        test_content = target_group.add_inner_groupbox(title="Key Testing")
        test_layout = QHBoxLayout()
        self.page.test_key_input = create_line_edit()
        self.page.test_key_input.setMaximumWidth(400)
        self.page.test_key_input.setPlaceholderText("Enter a key to test platform detection...")
        self.page.test_key_input.textChanged.connect(self.page._test_platform_detection)
        test_layout.addWidget(self.page.test_key_input)

        self.page.detected_platform_label = QLabel("Waiting for input...")
        test_layout.addWidget(self.page.detected_platform_label)
        test_layout.addStretch()

        test_content.addLayout(test_layout)

        # If we created an explicit Platform Detection top-level group, add it
        # as a section. Otherwise the inner boxes were attached to an existing
        # group (eg. Debug) and that group's section was already added.
        if platform_group is not None:
            self.page._add_section(page_key, parent_layout, platform_group)

    def create_debug_page(self, page_key, parent_layout):
        """Create a dedicated subpage for Debugging."""

        debug_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Debug",
            inner_orientation=Qt.Vertical,
        )

        # Create a dedicated inner groupbox for the debug toggles so they
        # are kept separate from the platform detection inner boxes.
        toggles_content = debug_group.add_inner_groupbox(title="Debug Toggles")
        toggles_layout = QFormLayout()
        self.page.status_bar_toggle = self._create_toggle('show_status_bar', True, self.page._on_status_bar_toggled, label_text="Show Status Bar")
        # Top-level debug mode toggle — replaces the legacy health monitor-only toggle
        # This new toggle controls dev features across the UI (health monitor debug buttons, and Home -> No Pictures filter)
        self.page.debug_mode_toggle = self._create_toggle(
            'debug_mode', False, self.page._on_debug_mode_toggled, label_text="Debug Mode"
        )
        # Present as a single row labelled "Debug Mode"
        self._add_toggle_row(toggles_layout, "Debug Mode", self.page.debug_mode_toggle)
        self._add_toggle_row(toggles_layout, "Show Status Bar", self.page.status_bar_toggle)
        toggles_content.addLayout(toggles_layout)

        # Debug Actions: expose utility buttons intended for developers
        debug_actions = debug_group.add_inner_groupbox(title="Debug Actions")
        dbg_row = QHBoxLayout()
        # Move 'Remove Unused Tags' button into Debug Actions for discoverability
        self.page.clear_unused_tags_btn = create_push_button("Remove Unused Tags")
        self.page.clear_unused_tags_btn.setToolTip("Delete tags that are not assigned to any games (including hidden/ignored tags)")
        self.page.clear_unused_tags_btn.clicked.connect(self.page._remove_unused_tags)
        dbg_row.addWidget(self.page.clear_unused_tags_btn)
        dbg_row.addStretch()
        debug_actions.addLayout(dbg_row)

        self.page._add_section(page_key, parent_layout, debug_group)

        # Move platform inner groupboxes into the Debug section so they are
        # shown inside the Debug groupbox instead of a separate Platform
        # Detection section.
        self.create_platform_info_section(page_key, parent_layout, attach_to_group=debug_group)
    
    def create_theme_customization_section(self, page_key, parent_layout):
        """Theme customization section."""
        # Import shared constants from settings_page
        from src.ui.pages.settings_page import (
            APPEARANCE_MAP, GRADIENT_ANIMATION_MAP,
            get_index_from_value, _APPEARANCE_REVERSE_MAP, _GRADIENT_ANIMATION_REVERSE_MAP
        )
        # UI Layout & Style groupbox
        ui_layout_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="UI Layout & Style",
            inner_orientation=Qt.Horizontal
        )
        ui_layout_content = ui_layout_group.add_inner_groupbox(title="Style Options")
        ui_layout_form = QFormLayout()
        ui_layout_content.addLayout(ui_layout_form)

        # Section GroupBox Title Location toggle
        title_location_options = ["Left", "Top"]
        section_title_location = self.settings_manager.get('section_groupbox_title_location', 'left')
        title_location_index = 0 if section_title_location == 'left' else 1
        
        self.page.section_title_location_toggle = MultiStepToggle(
            options=title_location_options,
            current_index=title_location_index,
            parent=self.page,
            theme_manager=self.theme_manager
        )
        self.page.section_title_location_toggle.position_changed.connect(self.page._on_section_title_location_toggle_changed)
        
        # Toggle Style toggle
        toggle_style_options = ["Regular", "Dot"]
        toggle_style = self.settings_manager.get('toggle_style', 'regular')
        toggle_style_index = {'regular': 0, 'dot': 1}.get(toggle_style, 0)
        
        self.page.toggle_style_toggle = MultiStepToggle(
            options=toggle_style_options,
            current_index=toggle_style_index,
            parent=self.page,
            theme_manager=self.theme_manager
        )
        self.page.toggle_style_toggle.position_changed.connect(self.page._on_toggle_style_toggle_changed)
        
        ui_layout_form.addRow(QLabel("Groupbox Title:"), self.page.section_title_location_toggle)
        ui_layout_form.addRow(QLabel("Toggle Style:"), self.page.toggle_style_toggle)

        # Game Card Style: control which chips are shown on game cards
        game_card_content = ui_layout_group.add_inner_groupbox(title="Game Card")
        game_card_form = QFormLayout()
        
        # Title chip toggle
        self.page.show_title_chip_toggle = self._create_toggle(
            'show_title_chip', True, label_text="Show Title"
        )
        self.page.show_title_chip_toggle.toggled.connect(
            lambda checked: self.page._update_game_card_chips('show_title_chip', checked)
        )
        self._add_toggle_row(game_card_form, "Show Title", self.page.show_title_chip_toggle)
        
        # Platform chip toggle
        self.page.show_platform_chip_toggle = self._create_toggle(
            'show_platform_chip', True, label_text="Show Platform"
        )
        self.page.show_platform_chip_toggle.toggled.connect(
            lambda checked: self.page._update_game_card_chips('show_platform_chip', checked)
        )
        self._add_toggle_row(game_card_form, "Show Platform", self.page.show_platform_chip_toggle)
        
        # Tags chip toggle
        self.page.show_tags_chip_toggle = self._create_toggle(
            'show_tags_chip', True, label_text="Show Tags"
        )
        self.page.show_tags_chip_toggle.toggled.connect(
            lambda checked: self.page._update_game_card_chips('show_tags_chip', checked)
        )
        self._add_toggle_row(game_card_form, "Show Tags", self.page.show_tags_chip_toggle)
        
        # Deadline chip toggle
        self.page.show_deadline_chip_toggle = self._create_toggle(
            'show_deadline_chip', True, label_text="Show Deadline"
        )
        self.page.show_deadline_chip_toggle.toggled.connect(
            lambda checked: self.page._update_game_card_chips('show_deadline_chip', checked)
        )
        self._add_toggle_row(game_card_form, "Show Deadline", self.page.show_deadline_chip_toggle)
        
        game_card_content.addLayout(game_card_form)

        # Page Navigation Bar: make it an inner groupbox inside the UI Layout & Style section
        page_navigation_bar_content = ui_layout_group.add_inner_groupbox(title="Page Navigation Bar")
        page_form = QFormLayout()
        page_navigation_bar_content.addLayout(page_form)

        # Position toggle
        position_options = ["Left", "Top", "Bottom", "Right"]
        pos = self.settings_manager.get('page_navigation_bar_position', 'left').capitalize()
        try:
            pos_index = position_options.index(pos)
        except ValueError:
            pos_index = 0
        
        self.page.page_navigation_bar_position_toggle = MultiStepToggle(
            options=position_options,
            current_index=pos_index,
            parent=self.page,
            theme_manager=self.theme_manager
        )
        self.page.page_navigation_bar_position_toggle.position_changed.connect(self.page._on_page_navigation_bar_position_toggle_changed)
        
        # Appearance toggle
        appearance_options = list(APPEARANCE_MAP.keys())
        app_val = self.settings_manager.get('page_navigation_bar_appearance', 'icon_and_text')
        app_index = get_index_from_value(app_val, APPEARANCE_MAP, _APPEARANCE_REVERSE_MAP)
        
        self.page.page_navigation_bar_appearance_toggle = MultiStepToggle(
            options=appearance_options,
            current_index=app_index,
            parent=self.page,
            theme_manager=self.theme_manager
        )
        self.page.page_navigation_bar_appearance_toggle.position_changed.connect(self.page._on_page_navigation_bar_appearance_toggle_changed)

        page_form.addRow(QLabel("Position:"), self.page.page_navigation_bar_position_toggle)
        page_form.addRow(QLabel("Appearance:"), self.page.page_navigation_bar_appearance_toggle)

        # Tooltips: move tooltip settings from General to UI Layout & Style
        tooltips_content = ui_layout_group.add_inner_groupbox(title="Tooltips")
        tooltips_layout = QFormLayout()

        # Animation Type
        self.page.tooltip_animation_combo = create_combo_box()
        self.page.tooltip_animation_combo.addItems(["Fade", "Slide"])
        current_anim = self.settings_manager.get('tooltip_animation', 'Fade')
        self.page.tooltip_animation_combo.setCurrentText(current_anim)
        self.page.tooltip_animation_combo.currentTextChanged.connect(self.page._on_tooltip_animation_changed)
        self._add_widget_row(tooltips_layout, "Animation:", self.page.tooltip_animation_combo)

        # Show Delay
        self.page.tooltip_show_delay_spinbox = create_spin_box(minimum=0, maximum=2000, single_step=50)
        self.page.tooltip_show_delay_spinbox.setSuffix(" ms")
        self.page.tooltip_show_delay_spinbox.setValue(self.settings_manager.get_int('tooltip_show_delay', 500))
        self.page.tooltip_show_delay_spinbox.valueChanged.connect(self.page._on_tooltip_show_delay_changed)
        self._add_widget_row(tooltips_layout, "Show Delay:", self.page.tooltip_show_delay_spinbox)

        tooltips_content.addLayout(tooltips_layout)

        # Now that all inner groupboxes for the UI Layout & Style section
        # have been created, register the section so the search handler
        # caches all the content (including inner groupbox titles).
        self.page._add_section(page_key, parent_layout, ui_layout_group)

    # Note: page navigation bar is an inner groupbox of the UI Layout & Style section

        # Theme Management groupbox
        save_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Theme Management",
            inner_orientation=Qt.Horizontal
        )

        # Save theme
        save_content = save_group.add_inner_groupbox(title="Save Theme")
        save_form = QFormLayout()
        name_container, self.page.new_theme_name_input, self.page.save_theme_btn = create_line_edit(
            label="Name:",
            button_text="Save",
            on_button_clicked=self.page._save_theme,
        )
        self.page.save_theme_btn.setToolTip("Save the current theme customizations")
        self.page.new_theme_name_input.setPlaceholderText("New theme name...")
        self.page.new_theme_name_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        save_form.addRow(name_container)
        save_content.addLayout(save_form)

        # Remove Custom Themes
        delete_content = save_group.add_inner_groupbox(title="Remove Custom Themes")
        combo_container, self.page.delete_theme_combo, self.page.delete_theme_btn = create_combo_box(
            label="Theme:",
            button_text="Delete",
            on_button_clicked=self.page._delete_theme,
            width=190
        )
        self.page.delete_theme_btn.setToolTip("Remove the selected custom theme")
        custom_themes = self.theme_manager.get_custom_themes()
        self.page.delete_theme_combo.addItems(custom_themes)
        self.page.delete_theme_combo.installEventFilter(self.page)
        delete_form = QFormLayout()
        delete_form.addRow(combo_container)
        delete_content.addLayout(delete_form)

        self.page.new_theme_name_input.textChanged.connect(self.page._update_save_button_label)

        # Color Customization groupbox
        base_colors_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Color Customization",
            inner_orientation=Qt.Horizontal
        )

        # Base Colors
        base_colors_content = base_colors_group.add_inner_groupbox(title="Theme Colors")
        main_layout = QFormLayout()

        # Gradient Bar
        gradient_content = base_colors_group.add_inner_groupbox(title="Gradient Bar")
        gradient_layout = QFormLayout()

        # Gradient animation selector
        animation_options = list(GRADIENT_ANIMATION_MAP.keys())
        current_anim = self.settings_manager.get('gradient_animation', 'scroll')
        anim_index = get_index_from_value(current_anim, GRADIENT_ANIMATION_MAP, _GRADIENT_ANIMATION_REVERSE_MAP)
        
        self.page.gradient_animation_toggle = MultiStepToggle(
            options=animation_options,
            current_index=anim_index,
            parent=self.page,
            theme_manager=self.theme_manager
        )
        self.page.gradient_animation_toggle.position_changed.connect(self.page._on_gradient_animation_toggle_changed)
        
        gradient_layout.addRow(QLabel("Gradient Animation:"), self.page.gradient_animation_toggle)

        # Gradient Color Picker Widget - using LinkedColorPickerPair
        # Get current gradient colors from theme
        color1 = self.theme_manager.current_theme.get(
            'gradient_color1',
            self.theme_manager.current_theme.get('base_primary', '#ff7f3f')
        )
        color2 = self.theme_manager.current_theme.get(
            'gradient_color2',
            self.theme_manager.current_theme.get('base_accent', '#ff9f3f')
        )
        
        self.page.gradient_color_picker = LinkedColorPickerPair(
            color1=color1,
            color2=color2,
            label1="Primary",
            label2="Accent",
            parent=self.page,
            theme_manager=self.theme_manager
        )
        
        # Connect signals
        self.page.gradient_color_picker.color1_changed.connect(
            lambda c: self.page._on_gradient_color_changed('gradient_color1', c)
        )
        self.page.gradient_color_picker.color2_changed.connect(
            lambda c: self.page._on_gradient_color_changed('gradient_color2', c)
        )
        self.page.gradient_color_picker.colors_swapped.connect(self.page._on_gradient_colors_swapped)
        
        # Add widget to layout
        gradient_layout.addRow(QLabel("Gradient Colors:"), self.page.gradient_color_picker)

        # Base colors - use linked color pickers for Primary and Accent
        self.page.theme_color_buttons = {}
        
        # Background color (separate)
        bg_color = self.theme_manager.current_theme.get('base_background', '#2d1b1b')
        self.page.background_color_picker = ColorPickerButton(
            initial_color=bg_color,
            label="Background",
            parent=self.page
        )
        self.page.background_color_picker.color_changed.connect(
            lambda c: self.page._on_base_color_changed('base_background', c)
        )
        main_layout.addRow(QLabel("Background:"), self.page.background_color_picker)
        self.page.theme_color_buttons['base_background'] = self.page.background_color_picker
        
        # Primary and Accent (linked pair)
        primary_color = self.theme_manager.current_theme.get('base_primary', '#ff7f3f')
        accent_color = self.theme_manager.current_theme.get('base_accent', '#ff9f3f')
        
        self.page.base_color_picker_pair = LinkedColorPickerPair(
            color1=primary_color,
            color2=accent_color,
            label1="Primary",
            label2="Accent",
            parent=self.page,
            theme_manager=self.theme_manager
        )
        self.page.base_color_picker_pair.color1_changed.connect(
            lambda c: self.page._on_base_color_changed('base_primary', c)
        )
        self.page.base_color_picker_pair.color2_changed.connect(
            lambda c: self.page._on_base_color_changed('base_accent', c)
        )
        self.page.base_color_picker_pair.colors_swapped.connect(
            lambda: self.page._on_base_colors_swapped()
        )
        main_layout.addRow(QLabel("Primary & Accent:"), self.page.base_color_picker_pair)
        self.page.theme_color_buttons['base_primary'] = self.page.base_color_picker_pair.button1
        self.page.theme_color_buttons['base_accent'] = self.page.base_color_picker_pair.button2

        base_colors_content.addLayout(main_layout)

        gradient_content.addLayout(gradient_layout)

        # Radii
        radii_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Radii",
            inner_orientation=Qt.Vertical  # Vertical stacking for radii settings
        )
        radii_row = QVBoxLayout()

        # Corner Radius
        corner_col = QVBoxLayout()
        corner_col.addWidget(QLabel("Corner Radius:"))
        corner_row = QHBoxLayout()
        from PySide6.QtWidgets import QSlider
        self.page.radius_slider = QSlider(Qt.Orientation.Horizontal)
        current_radius = int(self.theme_manager.current_theme.get('corner_radius', 4))
        self.page.radius_spin = create_spin_box(minimum=0, maximum=ELEMENT_HEIGHT // 2)
        
        # Set up preview callback for gradient bar update
        def corner_preview_cb(value):
            from PySide6.QtWidgets import QApplication
            mw = QApplication.instance().activeWindow() if QApplication.instance() else None
            if mw and hasattr(mw, 'gradient_bar') and mw.gradient_bar:
                mw.gradient_bar.set_radius(value)
        self.page._radius_timers['corner']['preview_callback'] = corner_preview_cb
        
        self.page._bind_slider_spin(
            self.page.radius_slider,
            self.page.radius_spin,
            minimum=0,
            maximum=ELEMENT_HEIGHT // 2,
            value=current_radius,
            on_preview=lambda v: self.page._on_radius_preview(v, 'corner'),
            on_commit=lambda: self.page._on_radius_commit('corner'),
        )
        corner_row.addWidget(self.page.radius_slider, 1)
        corner_row.addWidget(self.page.radius_spin, 0)
        corner_col.addLayout(corner_row)

        # Scrollbar Radius
        from src.ui.config import SCROLLBAR_WIDTH
        sb_col = QVBoxLayout()
        sb_col.addWidget(QLabel("Scrollbar Radius:"))
        sb_row = QHBoxLayout()
        self.page.sb_radius_slider = QSlider(Qt.Orientation.Horizontal)
        current_sb_radius = int(self.theme_manager.current_theme.get('scrollbar_radius', current_radius))
        self.page.sb_radius_spin = create_spin_box(minimum=0, maximum=SCROLLBAR_WIDTH // 2)
        self.page._bind_slider_spin(
            self.page.sb_radius_slider,
            self.page.sb_radius_spin,
            minimum=0,
            maximum=SCROLLBAR_WIDTH // 2,
            value=current_sb_radius,
            on_preview=lambda v: self.page._on_radius_preview(v, 'scrollbar'),
            on_commit=lambda: self.page._on_radius_commit('scrollbar'),
        )
        sb_row.addWidget(self.page.sb_radius_slider, 1)
        sb_row.addWidget(self.page.sb_radius_spin, 0)
        sb_col.addLayout(sb_row)

        radii_row.addLayout(corner_col)
        radii_row.addLayout(sb_col)
        radii_group.content_layout.addLayout(radii_row)

        # Add all sections
        for grp in (save_group, base_colors_group, radii_group):
            self.page._add_section(page_key, parent_layout, grp)
