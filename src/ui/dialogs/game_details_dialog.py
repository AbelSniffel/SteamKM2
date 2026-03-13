"""
Game details dialog for viewing and editing entry information
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTextEdit, 
                               QLabel, QDialogButtonBox, QMessageBox, QSizePolicy, QScrollArea, QPushButton, QGroupBox)
from PySide6.QtWidgets import QFileDialog, QWidget, QApplication
from PySide6.QtCore import Signal, QTimer, QDateTime, Qt
from src.ui.utils import clear_layout
from src.core.platform_detector import PlatformDetector
from src.core.steam_integration import SteamIntegration, SteamFetchWorker, DatabaseSaveWorker
from src.ui.config import WIDGET_SPACING, TOGGLE_SPACING, ELEMENT_HEIGHT
from src.ui.widgets.section_groupbox import SectionGroupBox
from src.ui.widgets.main_widgets import create_combo_box, create_line_edit, create_push_button, create_tags_section, create_date_selector, create_scroll_area
from src.ui.ui_factory import UIFactory

# Check for Qt threading support
try:
    from PySide6.QtCore import QThread
    HAS_QTHREAD = True
except ImportError:
    HAS_QTHREAD = False

class GameDetailsDialog(QDialog):
    """Dialog for viewing and editing game details"""
    
    game_updated = Signal(int, list)  # Signal emitted when game is updated, passes count and list of titles
    
    def __init__(self, game_data, db_manager, theme_manager, parent=None, settings_manager=None):
        """
        Initialize the dialog with one or more games.
        
        Args:
            game_data: Either a single game dict or a list of game dicts
            db_manager: Database manager instance
            theme_manager: Theme manager instance
            parent: Parent widget
            settings_manager: Settings manager instance (optional)
        """
        super().__init__(parent)
        self.settings_manager = settings_manager or (parent.settings_manager if hasattr(parent, 'settings_manager') else None)
        
        # Normalize to list format
        self.games_data = [g.copy() for g in game_data] if isinstance(game_data, list) else [game_data.copy()]
        self.original_games_data = [g.copy() for g in self.games_data]
        self.current_game_index = 0
        self.game_data = self.games_data[0]
        
        self.db_manager = db_manager
        self.theme_manager = theme_manager
        self.modified = {}  # Track modifications per game ID
        
        # Configure dialog based on mode
        is_multi = len(self.games_data) > 1
        self.setWindowTitle(f"Game Details - {'Editing ' + str(len(self.games_data)) + ' Games' if is_multi else self.games_data[0]['title']}")
        self.setModal(True)
        self.setMinimumSize(1060 if is_multi else 760, 600)
        
        # Ensure dialog is deleted when closed to prevent memory leaks
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self._setup_ui()
        self._load_data()
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup the dialog UI"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create game tabs sidebar (only if multiple games)
        if len(self.games_data) > 1:
            self._create_game_tabs_sidebar(main_layout)
        
        # Create main content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(WIDGET_SPACING)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # Game info section
        self._create_details_section(content_layout)
        
        # Tags section
        self._create_tags_section(content_layout)
        
        # Additional info section
        self._create_additional_info_section(content_layout)
        # Add stretch to push buttons to bottom and prevent groupboxes from expanding vertically
        content_layout.addStretch()
        # Dialog buttons
        self._create_dialog_buttons(content_layout)
        
        main_layout.addWidget(content_widget)
    
    def _create_game_tabs_sidebar(self, parent_layout):
        """Create a vertical sidebar with game selection buttons"""
        
        sidebar_widget = QWidget()
        sidebar_widget.setObjectName("MultiGameEditSidebar")
        sidebar_widget.setFixedWidth(300)
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(5, 5, 5, 5)
        sidebar_layout.setSpacing(WIDGET_SPACING)
        
        # Title label
        title_label = QLabel("Games")
        title_label.setStyleSheet("font-weight: bold; font-size: 12pt; padding: 1px;")
        sidebar_layout.addWidget(title_label)
        
        # Scroll area for game buttons
        scroll_area = create_scroll_area(widget_resizable=True, horizontal_policy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        self.game_buttons_layout = QVBoxLayout(scroll_content)
        self.game_buttons_layout.setSpacing(2)
        
        # Create button for each game with same height as settings sidebar items
        self.game_buttons = []
        button_height = ELEMENT_HEIGHT + 4  # Same as settings sidebar
        for idx, game in enumerate(self.games_data):
            btn = QPushButton(game.get('title', f'Game {idx+1}'))
            btn.setCheckable(True)
            btn.setChecked(idx == self.current_game_index)
            btn.setFixedHeight(button_height)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setProperty("gameIndex", idx)
            btn.clicked.connect(lambda checked, i=idx: self._switch_to_game(i))
            self.game_buttons.append(btn)
            self.game_buttons_layout.addWidget(btn)
        
        self.game_buttons_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        sidebar_layout.addWidget(scroll_area)
        
        parent_layout.addWidget(sidebar_widget)
    
    def _switch_to_game(self, index):
        """Switch to a different game in the multi-game editor"""
        if index == self.current_game_index:
            return
        
        # Save current form data to games_data before switching (keeping changes pending)
        self._save_form_data_to_game_data()
        
        # Update current index and game data
        self.current_game_index = index
        self.game_data = self.games_data[index]
        
        # Update button states
        for i, btn in enumerate(self.game_buttons):
            btn.setChecked(i == index)
        
        # Reload form with new game data
        self._load_data()
    
    def _create_details_section(self, parent_layout):
        """Create game information section"""
        # Details section
        info_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Details",
            size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ) if self.settings_manager else SectionGroupBox(title="Details", size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        # Create first inner groupbox for the main fields
        fields_content = info_group.add_inner_groupbox()
        info_layout = QFormLayout()
        fields_content.addLayout(info_layout)

        # Title
        self.title_edit = create_line_edit()
        info_layout.addRow("Title:", self.title_edit)

        # Game key, Steam AppID, and platform on same row
        key_platform_widget = QWidget(objectName="Transparent")
        key_platform_layout = QHBoxLayout(key_platform_widget)
        key_platform_layout.setContentsMargins(0, 0, 0, 0)
        key_platform_layout.setSpacing(WIDGET_SPACING)
        
        self.key_edit = create_line_edit()
        self.key_edit.setFont(self.font())  # Monospace would be better
        self.key_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        key_platform_layout.addWidget(self.key_edit, 1)  # Stretch factor 1 to expand
        
        # Steam AppID container (visible only when Steam is selected)
        self.steam_app_id_container = QWidget(objectName="Transparent")
        steam_app_id_layout = QHBoxLayout(self.steam_app_id_container)
        steam_app_id_layout.setContentsMargins(0, 0, 0, 0)
        steam_app_id_layout.setSpacing(WIDGET_SPACING)
        self.steam_app_id_label = QLabel("AppID:")
        self.steam_app_id_edit = create_line_edit()
        self.steam_app_id_edit.setPlaceholderText("Steam AppID")
        self.steam_app_id_edit.setFixedWidth(75)
        steam_app_id_layout.addWidget(self.steam_app_id_label)
        steam_app_id_layout.addWidget(self.steam_app_id_edit)
        key_platform_layout.addWidget(self.steam_app_id_container, 0)  # No stretch
        
        platform_label = QLabel("Platform:")
        key_platform_layout.addWidget(platform_label, 0)  # No stretch
        
        self.platform_combo = create_combo_box()
        self.platform_combo.setEditable(False)  # Make it non-editable for consistency
        key_platform_layout.addWidget(self.platform_combo, 0)  # No stretch
        
        info_layout.addRow("Key:", key_platform_widget)

        # Notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(100)
        info_layout.addRow("Notes:", self.notes_edit)

        # Image path (kept with main fields)
        self.image_input = create_line_edit()
        self.image_input.setPlaceholderText("Path to cover image...")
        browse_btn = create_push_button("Browse")
        browse_btn.setToolTip("Choose a cover image from disk")
        browse_btn.clicked.connect(self._browse_image)
        img_widget = QWidget(objectName="Transparent")
        img_layout = QHBoxLayout(img_widget)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.addWidget(self.image_input)
        img_layout.addWidget(browse_btn)
        info_layout.addRow("Image:", img_widget)

        # Create second inner groupbox for options (toggles + deadline)
        options_content = info_group.add_inner_groupbox()
        options_layout = QFormLayout()
        options_content.addLayout(options_layout)

        # Row 3: Auto Tag button + Toggles (DLC emoji, Used, Deadline + date)
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(TOGGLE_SPACING)

        # Auto Tag button (visible only for Steam) - positioned first before toggles
        self.auto_tag_btn = create_push_button("Use Cached Data")
        self.auto_tag_btn.setToolTip("Fetch data from local cache if available, or Steam if missing")
        toggles_row.addWidget(self.auto_tag_btn)
        
        # Fetch New Data button (force fresh)
        self.fetch_new_btn = create_push_button("Fetch New Data")
        self.fetch_new_btn.setToolTip("Force a fresh search from Steam (ignores cache)")
        self.fetch_new_btn.clicked.connect(self._on_fetch_new_clicked)
        self.fetch_new_btn.setVisible(False)
        toggles_row.addWidget(self.fetch_new_btn)

        # DLC emoji label (visible only for Steam games when DLC)
        self.dlc_label = QLabel("📦 DLC")
        self.dlc_label.setToolTip("This is downloadable content (DLC status controlled by Steam fetch)")
        self.dlc_label.setVisible(False)  # Hidden by default, shown only when Steam + DLC
        toggles_row.addWidget(self.dlc_label)

        # DLC toggle (composite with label) - for non-Steam platforms
        dlc_comp = UIFactory.create_toggle_with_label(
            label_text="DLC", 
            parent=self, 
            checked=False, 
            theme_manager=self.theme_manager,
            settings_manager=self.settings_manager
        )
        # Extract the actual toggle widget (handle both container and direct widget)
        self.dlc_toggle = dlc_comp.toggle if (hasattr(dlc_comp, 'toggle') and not callable(dlc_comp.toggle)) else dlc_comp
        dlc_comp.setToolTip("Flag this entry as downloadable content")
        toggles_row.addWidget(dlc_comp)

        # Used toggle (composite with label)
        used_comp = UIFactory.create_toggle_with_label(
            label_text="Used", 
            parent=self, 
            checked=False, 
            theme_manager=self.theme_manager,
            settings_manager=self.settings_manager
        )
        # Extract the actual toggle widget (handle both container and direct widget)
        # Check if toggle is a property (container) vs a method (direct widget)
        self.used_toggle = used_comp.toggle if (hasattr(used_comp, 'toggle') and not callable(used_comp.toggle)) else used_comp
        used_comp.setToolTip("Mark the game as already redeemed")
        toggles_row.addWidget(used_comp)

        # Deadline toggle with date picker (composite with label)
        deadline_comp = UIFactory.create_toggle_with_label(
            label_text="Deadline", 
            parent=self, 
            checked=False, 
            theme_manager=self.theme_manager,
            settings_manager=self.settings_manager
        )
        # Extract the actual toggle widget (handle both container and direct widget)
        self.deadline_toggle = deadline_comp.toggle if (hasattr(deadline_comp, 'toggle') and not callable(deadline_comp.toggle)) else deadline_comp
        deadline_comp.setToolTip("Enable a reminder deadline for this game")
        toggles_row.addWidget(deadline_comp)

        self.deadline_inline_label = QLabel("Redeem By:")
        self.deadline_inline_label.setVisible(False)
        self.deadline_input = create_date_selector(self)
        self.deadline_input.setToolTip("Pick the redeem-by date once enabled")

        toggles_row.addWidget(self.deadline_inline_label)
        toggles_row.addWidget(self.deadline_input)
        toggles_row.addStretch()

        # Connect deadline toggle
        self.deadline_toggle.toggled.connect(self._on_deadline_toggled)

        # Add toggles row to options content
        options_content.addLayout(toggles_row)

        parent_layout.addWidget(info_group)
    
    def _create_tags_section(self, parent_layout):
        """Create tags section with dual groupboxes: Steam auto-tags (left) and custom tags (right)"""
        from src.ui.widgets.flow_layout import FlowLayout
        from src.ui.widgets.section_groupbox import SectionGroupBox
        
        # Create outer section groupbox
        if self.settings_manager:
            tags_section = UIFactory.create_section_groupbox(
                settings_manager=self.settings_manager,
                object_name="tags_section",
                title="Tags",
                add_inner_box=False,
                size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            )
        else:
            tags_section = SectionGroupBox("tags_section", title="Tags", add_inner_box=False)
            tags_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # Horizontal layout for the two tag groupboxes
        tags_container = QWidget(objectName="Transparent")
        tags_container_layout = QHBoxLayout(tags_container)
        tags_container_layout.setContentsMargins(0, 0, 0, 0)
        tags_container_layout.setSpacing(WIDGET_SPACING)
        
        # Left groupbox: Steam Auto Tags (read-only, only shows active/assigned tags)
        steam_tags_group = QGroupBox("Steam Tags", objectName="TagBox")
        steam_tags_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        steam_tags_layout = QVBoxLayout(steam_tags_group)
        steam_tags_layout.setContentsMargins(5, 5, 5, 5)
        steam_tags_layout.setSpacing(WIDGET_SPACING)
        self.steam_tags_flow = FlowLayout(margin=0, spacing=WIDGET_SPACING)
        steam_tags_layout.addLayout(self.steam_tags_flow)
        tags_container_layout.addWidget(steam_tags_group)
        
        # Right groupbox: Custom Tags (interactive, can be toggled on/off)
        custom_tags_group = QGroupBox("Custom Tags", objectName="TagBox")
        custom_tags_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        custom_tags_layout = QVBoxLayout(custom_tags_group)
        custom_tags_layout.setContentsMargins(5, 5, 5, 5)
        self.custom_tags_flow = FlowLayout(margin=0, spacing=WIDGET_SPACING)
        custom_tags_layout.addLayout(self.custom_tags_flow)
        tags_container_layout.addWidget(custom_tags_group)
        
        tags_section.content_layout.addWidget(tags_container)
        parent_layout.addWidget(tags_section)
        
        # Keep backwards compatibility - point tags_hbox to custom_tags_flow
        self.tags_hbox = self.custom_tags_flow

    def _get_current_tag_names(self):
        """Extract current tag names from game data"""
        tags_str = self.game_data.get('tags') or ''
        return [tag.strip() for tag in tags_str.split(',') if tag.strip()]
    
    def _set_current_tag_names(self, tag_names):
        """Update game data tags and refresh UI"""
        self.game_data['tags'] = ', '.join(tag_names)
        self._update_tags_lists()
        self._mark_modified()

    def _update_tags_lists(self):
        """Update the dual tag layouts: Steam tags (read-only) and custom tags (interactive)"""
        # Clear existing buttons
        clear_layout(self.steam_tags_flow)
        clear_layout(self.custom_tags_flow)
        
        all_tags = self.db_manager.get_tags()
        current_tag_names = self._get_current_tag_names()
        
        # Get Steam-provided tag names from database and ignored tags
        steam_tag_names = {t['name'] for t in all_tags if t.get('is_builtin', False)}
        ignored_tags = SteamIntegration.IGNORED_TAGS
        
        # Steam Tags (left side): Only show ACTIVE Steam-provided tags - non-interactable
        for tag in all_tags:
            tag_name = tag['name']
            # Skip ignored tags (Steam platform features)
            if tag_name.lower() in ignored_tags:
                continue
            if tag.get('is_builtin', False) and tag_name in current_tag_names:
                # Create a read-only button for active Steam-provided tags
                btn = create_push_button(tag_name, object_name="toggle_tag_button")
                btn.setCheckable(True)
                btn.setChecked(True)
                btn.setEnabled(False)  # Non-interactable - controlled by auto-tagging
                btn.setToolTip(f"Steam tag '{tag_name}' (auto-managed)")
                self.steam_tags_flow.addWidget(btn)
        
        # Custom Tags (right side): Show ALL custom (non-Steam) tags - fully interactable
        for tag in all_tags:
            tag_name = tag['name']
            # Skip ignored tags (Steam platform features)
            if tag_name.lower() in ignored_tags:
                continue
            if not tag.get('is_builtin', False):
                btn = create_push_button(tag_name, object_name="toggle_tag_button")
                btn.setCheckable(True)
                btn.setChecked(tag_name in current_tag_names)
                btn.toggled.connect(lambda checked, name=tag_name: self._on_tag_toggled(name, checked))
                btn.setToolTip(f"Toggle the '{tag_name}' tag for this game")
                self.custom_tags_flow.addWidget(btn)
                self.custom_tags_flow.addWidget(btn)
        # If no Steam tags or no custom tags were added, show a disabled "None" placeholder
        try:
            from src.ui.widgets.main_widgets import create_no_tags_placeholder
            if getattr(self.steam_tags_flow, 'count', lambda: 0)() == 0:
                create_no_tags_placeholder(self.steam_tags_flow)
            if getattr(self.custom_tags_flow, 'count', lambda: 0)() == 0:
                create_no_tags_placeholder(self.custom_tags_flow)
        except Exception:
            pass
    
    def _on_tag_toggled(self, tag_name, checked):
        """Handle toggling of tags in details dialog"""
        names = self._get_current_tag_names()
        
        if checked and tag_name not in names:
            names.append(tag_name)
        elif not checked and tag_name in names:
            names.remove(tag_name)
        
        self._set_current_tag_names(names)
    
    def _get_review_description(self, score: int) -> str:
        """Get the Steam review description text based on percentage score."""
        if score is None:
            return "No Reviews"
        if score >= 95:
            return "Overwhelmingly Positive"
        elif score >= 80:
            return "Very Positive"
        elif score >= 70:
            return "Mostly Positive"
        elif score >= 40:
            return "Mixed"
        elif score >= 20:
            return "Mostly Negative"
        else:
            return "Overwhelmingly Negative"
    
    def _create_additional_info_section(self, parent_layout):
        """Create additional information section"""
        # Additional information section
        info_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            object_name="additional_info_section",
            title="Additional Information",
            size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ) if self.settings_manager else SectionGroupBox(
            "additional_info_section",
            title="Additional Information",
            size_policy=QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        )
        info_layout = QFormLayout()
        info_group.content_layout.addLayout(info_layout)
        
        # Steam Reviews (read-only, only visible for Steam games)
        self.reviews_container = QWidget(objectName="Transparent")
        reviews_layout = QHBoxLayout(self.reviews_container)
        reviews_layout.setContentsMargins(0, 0, 0, 0)
        reviews_layout.setSpacing(WIDGET_SPACING)
        self.reviews_label = QLabel()
        reviews_layout.addWidget(self.reviews_label)
        reviews_layout.addStretch()
        self.reviews_row_label = QLabel("Steam Reviews:")
        info_layout.addRow(self.reviews_row_label, self.reviews_container)
        
        # Cache Updated (read-only, only visible for Steam games)
        self.cache_updated_container = QWidget(objectName="Transparent")
        cache_layout = QHBoxLayout(self.cache_updated_container)
        cache_layout.setContentsMargins(0, 0, 0, 0)
        cache_layout.setSpacing(WIDGET_SPACING)
        self.cache_updated_label = QLabel()
        cache_layout.addWidget(self.cache_updated_label)
        cache_layout.addStretch()
        self.cache_row_label = QLabel("Cache Updated:")
        info_layout.addRow(self.cache_row_label, self.cache_updated_container)
        
        # Date added (read-only)
        self.date_label = QLabel()
        info_layout.addRow("Date Added:", self.date_label)
        
        # Game ID (read-only)
        self.id_label = QLabel()
        info_layout.addRow("Game ID:", self.id_label)
        
        parent_layout.addWidget(info_group)
    
    def _create_dialog_buttons(self, parent_layout):
        """Create dialog action buttons"""
        button_layout = QHBoxLayout()
        
        # Revert/Reset visible button (was previously Copy Key)
        # Use a clearer label and wire it to the existing reset logic
        self.revert_btn = create_push_button("Revert Changes")
        self.revert_btn.setToolTip("Undo edits and restore the original values")
        self.revert_btn.clicked.connect(self._reset_form)
        button_layout.addWidget(self.revert_btn)
        
        button_layout.addStretch()
        
        # Standard dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        
        button_layout.addWidget(self.button_box)
        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setToolTip("Save changes to the selected games")
        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setToolTip("Discard changes and close the dialog")
        parent_layout.addLayout(button_layout)
    
    def _connect_signals(self):
        """Connect signals"""
        # Track modifications
        self.title_edit.textChanged.connect(self._mark_modified)
        self.key_edit.textChanged.connect(self._mark_modified)
        self.steam_app_id_edit.textChanged.connect(self._mark_modified)
        self.platform_combo.currentTextChanged.connect(self._mark_modified)
        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)
        self.used_toggle.toggled.connect(self._mark_modified)
        self.dlc_toggle.toggled.connect(self._mark_modified)
        self.auto_tag_btn.clicked.connect(self._on_auto_tag_clicked)
        self.notes_edit.textChanged.connect(self._mark_modified)
        self.image_input.textChanged.connect(self._mark_modified)
        self.deadline_input.dateTimeChanged.connect(self._mark_modified)
        
        # Dialog buttons
        self.button_box.accepted.connect(self._save_changes)
        self.button_box.rejected.connect(self.reject)
    
    def _on_fetch_new_clicked(self):
        """Handle Fetch New Data button - force fresh search."""
        self._handle_steam_fetch_request(force_fresh=True)
    
    def _on_auto_tag_clicked(self):
        """Handle Use Cached Data button - standard fetch."""
        self._handle_steam_fetch_request(force_fresh=False)
        
    def _handle_steam_fetch_request(self, force_fresh: bool):
        """Common handler for Steam fetch requests."""
        # Only proceed if platform is Steam and we have a title
        platform = self.platform_combo.currentText()
        if platform.lower() != 'steam':
            return
        
        title = self.title_edit.text().strip()
        if not title:
            print("[Steam] Fetch clicked but no title entered yet")
            return
        
        if not self.settings_manager:
            return
        
        print(f"[Steam] Fetch triggered for '{title}' (force_fresh={force_fresh})")
        
        # Show fetching placeholder
        self._show_fetching_placeholder()
        
        self._start_steam_fetch(title, force_fresh_search=force_fresh, force_image=force_fresh)
    
    def _show_fetching_placeholder(self):
        """Clear steam tags and show fetching placeholder."""
        from src.ui.widgets.main_widgets import create_fetching_placeholder
        # Clear existing Steam tag buttons
        clear_layout(self.steam_tags_flow)
        # Add fetching placeholder
        create_fetching_placeholder(self.steam_tags_flow)
    
    def _start_steam_fetch(self, title: str, force_fresh_search: bool = False, force_image: bool = False):
        """Start a threaded Steam data fetch."""
        if not HAS_QTHREAD:
            self._sync_steam_fetch(title, force_fresh_search, force_image)
            return
        
        try:
            steam = SteamIntegration(self.settings_manager.get_app_data_dir())
        except Exception as e:
            print(f"[Steam] Failed to initialize: {e}")
            return
        
        # Get current values
        current_app_id = self.steam_app_id_edit.text().strip() or None
        # If forcing fresh search, ignore current AppID to ensure we search by title
        if force_fresh_search:
            current_app_id = None
            
        current_image = self.image_input.text().strip() or None
        current_tags = self._get_current_tag_names()
        
        # Get list of custom (non-Steam) tags to preserve
        all_tags = self.db_manager.get_tags()
        ignored_tags = SteamIntegration.IGNORED_TAGS
        custom_tags = [
            t['name'] for t in all_tags 
            if not t.get('is_builtin', False) and t['name'].lower() not in ignored_tags
        ]
        
        # Create worker
        self._fetch_thread = QThread()
        self._fetch_worker = steam.create_fetch_worker(
            title=title,
            current_app_id=current_app_id,
            current_tags=current_tags,
            current_image_path=current_image,
            fetch_appid=True,
            fetch_tags=True,
            fetch_image=True,
            force_tags=True,
            custom_tags=custom_tags,
            force_fresh_search=force_fresh_search,
            force_image=force_image
        )
        
        # Move worker to thread
        self._fetch_worker.moveToThread(self._fetch_thread)
        
        # Connect signals
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_steam_fetch_complete)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_worker.error.connect(self._on_steam_fetch_error)
        self._fetch_worker.error.connect(self._fetch_thread.quit)
        self._fetch_thread.finished.connect(self._cleanup_fetch_thread)
        
        # Start the thread
        self._fetch_thread.start()
        print(f"[Steam] Started background fetch for '{title}' (force_fresh={force_fresh_search})")
    
    def _sync_steam_fetch(self, title: str, force_fresh_search: bool = False, force_image: bool = False):
        """Synchronous Steam data fetch (fallback when threading unavailable)."""
        try:
            steam = SteamIntegration(self.settings_manager.get_app_data_dir())
            
            current_app_id = self.steam_app_id_edit.text().strip() or None
            # If forcing fresh search, ignore current AppID to ensure we search by title
            if force_fresh_search:
                current_app_id = None
                
            current_image = self.image_input.text().strip() or None
            current_tags = self._get_current_tag_names()
            
            # Get list of custom (non-Steam) tags to preserve
            all_tags = self.db_manager.get_tags()
            ignored_tags = SteamIntegration.IGNORED_TAGS
            custom_tags = [
                t['name'] for t in all_tags 
                if not t.get('is_builtin', False) and t['name'].lower() not in ignored_tags
            ]
            
            result = steam.fetch_missing_data(
                title=title,
                current_app_id=current_app_id,
                current_tags=current_tags,
                current_image_path=current_image,
                fetch_appid=True,
                fetch_tags=True,
                fetch_image=True,
                force_tags=True,
                custom_tags=custom_tags,
                force_fresh_search=force_fresh_search,
                force_image=force_image
            )
            
            self._on_steam_fetch_complete(result)
        except Exception as e:
            print(f"[Steam] Sync fetch error: {e}")
            # Clear fetching placeholder on error
            self._update_tags_lists()
    
    def _on_steam_fetch_complete(self, result: dict):
        """Handle completed Steam data fetch."""
        print(f"[Steam] Fetch complete: {result}")
        
        fetched = result.get('fetched', {})
        
        # Update AppID
        if fetched.get('app_id') and result.get('app_id'):
            self.steam_app_id_edit.setText(str(result['app_id']))
        
        # Update image
        if fetched.get('image') and result.get('image_path'):
            self.image_input.setText(result['image_path'])
        
        # Update DLC status
        if fetched.get('is_dlc'):
            is_dlc = result.get('is_dlc', False)
            self.game_data['dlc_enabled'] = is_dlc
            # For Steam: show emoji label, hide toggle
            self.dlc_label.setVisible(is_dlc)
            self.dlc_toggle.setCheckedNoAnimation(is_dlc)
            if is_dlc:
                print(f"[Steam] DLC status: This is a DLC")
        
        # Update review data
        if fetched.get('reviews'):
            review_score = result.get('review_score')
            review_count = result.get('review_count')
            if review_score is not None:
                self.game_data['steam_review_score'] = review_score
                self.game_data['steam_review_count'] = review_count
                # Update the reviews label
                review_desc = self._get_review_description(review_score)
                if review_count is not None:
                    self.reviews_label.setText(f"{review_desc} ({review_score}% of {review_count:,} reviews)")
                else:
                    self.reviews_label.setText(f"{review_desc} ({review_score}%)")
                print(f"[Steam] Review data: {review_score}% from {review_count} reviews")
        
        # Update tags (or just refresh UI to clear fetching placeholder)
        if fetched.get('tags') and result.get('tags'):
            new_tags = result['tags']
            self._set_current_tag_names(new_tags)
        else:
            # No tags fetched, but still refresh UI to clear fetching placeholder
            self._update_tags_lists()
    
    def _on_steam_fetch_error(self, error_msg: str):
        """Handle Steam fetch error - clear fetching placeholder."""
        print(f"[Steam] Fetch error: {error_msg}")
        # Refresh UI to clear fetching placeholder
        self._update_tags_lists()
    
    def _cleanup_fetch_thread(self):
        """Clean up the fetch thread after completion."""
        if hasattr(self, '_fetch_worker'):
            self._fetch_worker.deleteLater()
            del self._fetch_worker
        if hasattr(self, '_fetch_thread'):
            self._fetch_thread.deleteLater()
            del self._fetch_thread
    
    def _on_platform_changed(self, platform: str):
        """Handle platform change - show/hide Steam-specific fields."""
        is_steam = platform.lower() == 'steam'
        self.steam_app_id_container.setVisible(is_steam)
        self.auto_tag_btn.setVisible(is_steam)
        self.fetch_new_btn.setVisible(is_steam)
        # Hide/show Steam Reviews row
        self.reviews_row_label.setVisible(is_steam)
        self.reviews_container.setVisible(is_steam)
        # Hide/show Cache Updated row
        self.cache_row_label.setVisible(is_steam)
        self.cache_updated_container.setVisible(is_steam)
        # For Steam: show DLC emoji if DLC, hide toggle; For others: hide emoji, show toggle
        is_dlc = self.game_data.get('dlc_enabled', False)
        self.dlc_label.setVisible(is_steam and is_dlc)
        self.dlc_toggle.parent().setVisible(not is_steam)

    def _on_deadline_toggled(self, checked: bool):
        """Handle deadline toggle: show/hide row, enable input and set default date when enabled"""
        self.deadline_input.setEnabled(checked)
        self.deadline_input.setVisible(checked)
        self.deadline_inline_label.setVisible(checked)
        
        # If enabling and no stored deadline, set to current date
        if checked and not self.game_data.get('deadline_at'):
            self.deadline_input.setDateTime(QDateTime.currentDateTime())
        
        self._mark_modified()
    
    def _load_data(self):
        """Load game data into form"""
        # Basic info
        self.title_edit.setText(self.game_data.get('title', ''))
        self.key_edit.setText(self.game_data.get('game_key', ''))
        self.steam_app_id_edit.setText(self.game_data.get('steam_app_id', '') or '')
        self.used_toggle.setCheckedNoAnimation(bool(self.game_data.get('is_used', False)))
        self.notes_edit.setPlainText(self.game_data.get('notes', ''))
        self.dlc_toggle.setCheckedNoAnimation(bool(self.game_data.get('dlc_enabled', False)))
        
        # Auto Tag button state (button text indicates action)
        # No state to restore for button
        
        # Platform
        self._load_platforms()
        current_platform = self.game_data.get('platform_type', '')
        if current_platform:
            index = self.platform_combo.findText(current_platform)
            self.platform_combo.setCurrentIndex(index if index >= 0 else 0)
            if index < 0:
                self.platform_combo.setCurrentText(current_platform)
        
        # Update Steam field visibility based on platform
        is_steam = current_platform.lower() == 'steam' if current_platform else False
        self.steam_app_id_container.setVisible(is_steam)
        self.auto_tag_btn.setVisible(is_steam)
        self.fetch_new_btn.setVisible(is_steam)
        # For Steam: show DLC emoji if DLC, hide toggle; For others: hide emoji, show toggle
        is_dlc = bool(self.game_data.get('dlc_enabled', False))
        self.dlc_label.setVisible(is_steam and is_dlc)
        self.dlc_toggle.parent().setVisible(not is_steam)
        
        # Steam Reviews (only visible for Steam games)
        self.reviews_row_label.setVisible(is_steam)
        self.reviews_container.setVisible(is_steam)
        if is_steam:
            review_score = self.game_data.get('steam_review_score')
            review_count = self.game_data.get('steam_review_count')
            if review_score is not None and review_count is not None:
                review_desc = self._get_review_description(review_score)
                self.reviews_label.setText(f"{review_desc} ({review_score}% of {review_count:,} reviews)")
            elif review_score is not None:
                review_desc = self._get_review_description(review_score)
                self.reviews_label.setText(f"{review_desc} ({review_score}%)")
            else:
                self.reviews_label.setText("No review data available")
        
        # Cache Updated (only visible for Steam games with AppID)
        self.cache_row_label.setVisible(is_steam)
        self.cache_updated_container.setVisible(is_steam)
        if is_steam and self.settings_manager:
            steam_app_id = self.game_data.get('steam_app_id')
            if steam_app_id:
                try:
                    steam = SteamIntegration(self.settings_manager.get_app_data_dir())
                    cache_timestamp = steam.cache.get_cache_timestamp(steam_app_id)
                    if cache_timestamp:
                        from datetime import datetime
                        cache_date = datetime.fromtimestamp(cache_timestamp)
                        self.cache_updated_label.setText(cache_date.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        self.cache_updated_label.setText("Not cached")
                except Exception as e:
                    self.cache_updated_label.setText(f"Error: {str(e)}")
            else:
                self.cache_updated_label.setText("No AppID")
        
        # Additional info
        self.date_label.setText(self.game_data.get('date_added', 'Unknown'))
        self.id_label.setText(str(self.game_data.get('id', 'Unknown')))
        
        # Image path
        self.image_input.setText(self.game_data.get('image_path', '') or '')
        
        # Deadline
        deadline_enabled = bool(self.game_data.get('deadline_enabled', False))
        self.deadline_toggle.setCheckedNoAnimation(deadline_enabled)
        self.deadline_input.setEnabled(deadline_enabled)
        self.deadline_input.setVisible(deadline_enabled)
        self.deadline_inline_label.setVisible(deadline_enabled)
        
        deadline_str = self.game_data.get('deadline_at') or ''
        if deadline_str:
            dt = QDateTime.fromString(deadline_str, Qt.ISODate)
            if dt.isValid():
                self.deadline_input.setDateTime(dt)
        elif deadline_enabled:
            self.deadline_input.setDateTime(QDateTime.currentDateTime())
        
        # Tags
        self._update_tags_lists()
        
        # Reset modified flag for current game
        self.modified[self.game_data['id']] = False
    
    def _load_platforms(self):
        """Load platform options"""
        # Get platforms from database and add all known platforms
        platforms = set(self.db_manager.get_platforms())
        platforms.update(PlatformDetector.get_all_platforms())
        
        self.platform_combo.clear()
        self.platform_combo.addItems(sorted(platforms))
    
    def _mark_modified(self):
        """Mark the form as modified for the current game"""
        current_game_id = self.game_data['id']
        self.modified[current_game_id] = True
    
    def _save_form_data_to_game_data(self):
        """Save current form data back to self.game_data (without saving to DB)"""
        platform = self.platform_combo.currentText().strip()
        self.game_data.update({
            'title': self.title_edit.text().strip(),
            'game_key': self.key_edit.text().strip(),
            'steam_app_id': self.steam_app_id_edit.text().strip() or None,
            'platform_type': platform,
            'is_used': self.used_toggle.isChecked(),
            'notes': self.notes_edit.toPlainText(),
            'image_path': self.image_input.text().strip() or None,
            'deadline_enabled': self.deadline_toggle.isChecked(),
            'deadline_at': self.deadline_input.dateTime().toString(Qt.ISODate) if self.deadline_toggle.isChecked() else None,
            'dlc_enabled': self.dlc_toggle.isChecked(),
        })
        self.games_data[self.current_game_index] = self.game_data.copy()
    
    def _validate_game_data(self, game):
        """Validate game data. Returns (is_valid, error_message)"""
        title = game.get('title', '').strip()
        key = game.get('game_key', '').strip()
        platform = game.get('platform_type', '').strip()
        
        if not title:
            return False, "Game title cannot be empty."
        if not key:
            return False, "Game key cannot be empty."
        if not platform:
            return False, "Platform type cannot be empty."
        
        return True, None
    
    def _get_tag_ids_for_game(self, game):
        """Convert tag names to tag IDs for a game"""
        tags_str = game.get('tags') or ''
        tag_names = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
        
        all_tags = self.db_manager.get_tags()
        tag_name_to_id = {tag['name']: tag['id'] for tag in all_tags}
        
        return [tag_name_to_id[name] for name in tag_names if name in tag_name_to_id]
    
    def _browse_image(self):
        """Open file dialog to select image file"""
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Image File", "",
                                                   "Images (*.png *.xpm *.jpg *.jpeg);;All Files (*)",
                                                   options=options)
        if file_name:
            self.image_input.setText(file_name)
            self._mark_modified()
    
    def _save_changes(self):
        """Save changes to database for current or all modified games"""
        self._save_form_data_to_game_data()
        
        if len(self.games_data) > 1:
            self._save_all_games()
        elif self._save_current_game_to_db():
            self.accept()
    
    def _save_current_game_to_db(self):
        """Save the current game's changes to database. Returns True if successful."""
        is_valid, error_msg = self._validate_game_data(self.game_data)
        if not is_valid:
            QMessageBox.warning(self, "Invalid Input", error_msg)
            return False

        try:
            # Process auto-tagging for Steam games
            game = self.game_data
            auto_tag = game.pop('auto_tag', False)
            if auto_tag and game['platform_type'].lower() == 'steam' and self.settings_manager:
                steam = SteamIntegration(self.settings_manager.get_app_data_dir())
                title = game['title']
                current_app_id = game.get('steam_app_id')
                current_image = game.get('image_path')
                current_tags = self._get_current_tag_names()
                
                # Fetch missing Steam data
                steam_data = steam.fetch_missing_data(
                    title=title,
                    current_app_id=current_app_id,
                    current_tags=current_tags,
                    current_image_path=current_image,
                    fetch_appid=not current_app_id,
                    fetch_tags=not current_tags,
                    fetch_image=not current_image or not self._file_exists(current_image)
                )
                
                # Update game data with fetched values
                if steam_data.get('fetched', {}).get('app_id') and steam_data.get('app_id'):
                    game['steam_app_id'] = steam_data['app_id']
                
                if steam_data.get('fetched', {}).get('image') and steam_data.get('image_path'):
                    game['image_path'] = steam_data['image_path']
                
                if steam_data.get('fetched', {}).get('tags') and steam_data.get('tags'):
                    # Merge fetched tags with existing tags
                    fetched_tags = steam_data['tags']
                    existing_tags = set(current_tags)
                    for tag_name in fetched_tags:
                        existing_tags.add(tag_name)
                    game['tags'] = ', '.join(sorted(existing_tags))
            
            tag_ids = self._get_tag_ids_for_game(game)
            
            success = self.db_manager.update_game(
                game_id=game['id'],
                title=game['title'],
                game_key=game['game_key'],
                platform_type=game['platform_type'],
                notes=game.get('notes', ''),
                is_used=game.get('is_used', False),
                tag_ids=tag_ids,
                image_path=game.get('image_path'),
                deadline_enabled=game.get('deadline_enabled', False),
                deadline_at=game.get('deadline_at'),
                dlc_enabled=game.get('dlc_enabled', False),
                steam_app_id=game.get('steam_app_id')
            )

            if success:
                # Update button text if in multi-game mode
                if len(self.games_data) > 1:
                    self.game_buttons[self.current_game_index].setText(game['title'])
                
                self.modified[game['id']] = False
                self.game_updated.emit(1, [game['title']])
                return True
            else:
                QMessageBox.critical(self, "Error", "Failed to save changes to database.")
                return False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save changes: {str(e)}")
            return False
    
    def _file_exists(self, path):
        """Check if a file exists at the given path."""
        import os
        return path and os.path.exists(path)
    
    def _save_all_games(self):
        """Save all modified games in multi-game mode"""
        self._save_form_data_to_game_data()
        
        modified_game_ids = [game_id for game_id, modified in self.modified.items() if modified]
        if not modified_game_ids:
            self.accept()
            return
        
        # Initialize Steam integration if any game needs auto-tagging
        steam = None
        games_needing_fetch = [g for g in self.games_data if g.get('auto_tag') and g['id'] in modified_game_ids]
        if games_needing_fetch and self.settings_manager:
            try:
                steam = SteamIntegration(self.settings_manager.get_app_data_dir())
            except Exception:
                pass
        
        failed_games = []
        saved_count = 0
        saved_titles = []
        
        for game in self.games_data:
            game_id = game['id']
            if game_id not in modified_game_ids:
                continue
            
            is_valid, error_msg = self._validate_game_data(game)
            if not is_valid:
                failed_games.append(game.get('title', 'Unknown'))
                continue
            
            try:
                # Process auto-tagging for Steam games
                auto_tag = game.pop('auto_tag', False)
                if auto_tag and steam and game['platform_type'].lower() == 'steam':
                    title = game['title']
                    current_app_id = game.get('steam_app_id')
                    current_image = game.get('image_path')
                    tags_str = game.get('tags') or ''
                    current_tags = [t.strip() for t in tags_str.split(',') if t.strip()]
                    
                    # Fetch missing Steam data
                    steam_data = steam.fetch_missing_data(
                        title=title,
                        current_app_id=current_app_id,
                        current_tags=current_tags,
                        current_image_path=current_image,
                        fetch_appid=not current_app_id,
                        fetch_tags=not current_tags,
                        fetch_image=not current_image or not self._file_exists(current_image)
                    )
                    
                    # Update game data with fetched values
                    if steam_data.get('fetched', {}).get('app_id') and steam_data.get('app_id'):
                        game['steam_app_id'] = steam_data['app_id']
                    
                    if steam_data.get('fetched', {}).get('image') and steam_data.get('image_path'):
                        game['image_path'] = steam_data['image_path']
                    
                    if steam_data.get('fetched', {}).get('tags') and steam_data.get('tags'):
                        # Merge fetched tags with existing tags
                        existing_tags = set(current_tags)
                        for tag_name in steam_data['tags']:
                            existing_tags.add(tag_name)
                        game['tags'] = ', '.join(sorted(existing_tags))
                
                tag_ids = self._get_tag_ids_for_game(game)
                
                success = self.db_manager.update_game(
                    game_id=game_id,
                    title=game['title'],
                    game_key=game['game_key'],
                    platform_type=game['platform_type'],
                    notes=game.get('notes', ''),
                    is_used=game.get('is_used', False),
                    tag_ids=tag_ids,
                    image_path=game.get('image_path'),
                    deadline_enabled=game.get('deadline_enabled', False),
                    deadline_at=game.get('deadline_at'),
                    dlc_enabled=game.get('dlc_enabled', False),
                    steam_app_id=game.get('steam_app_id')
                )
                
                if success:
                    saved_count += 1
                    saved_titles.append(game['title'])
                    self.modified[game_id] = False
                else:
                    failed_games.append(game['title'])
                    
            except Exception as e:
                failed_games.append(f"{game['title']} ({str(e)})")
        
        if saved_count > 0:
            self.game_updated.emit(saved_count, saved_titles)
        
        if failed_games:
            QMessageBox.warning(
                self, "Save Incomplete",
                f"Saved {saved_count} game(s) successfully.\n\nFailed to save:\n" + "\n".join(failed_games)
            )
        
        if saved_count > 0:
            self.accept()
    
    def _reset_form(self):
        """Reset current game to original values (per-game revert)"""
        reply = QMessageBox.question(
            self, "Revert Changes",
            f"Are you sure you want to revert all changes to '{self.game_data.get('title', 'this game')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Restore original data
            original_game = self.original_games_data[self.current_game_index].copy()
            self.games_data[self.current_game_index] = original_game
            self.game_data = original_game
            self.modified[self.game_data['id']] = False
            self._load_data()
    
    def closeEvent(self, event):
        """Handle dialog close"""
        self._save_form_data_to_game_data()
        
        has_unsaved = any(self.modified.values())
        if not has_unsaved:
            self._cleanup_connections()
            event.accept()
            return
        
        unsaved_count = sum(1 for modified in self.modified.values() if modified)
        message = f"You have unsaved changes in {unsaved_count} game(s). Do you want to save them?" if len(self.games_data) > 1 else "You have unsaved changes. Do you want to save them?"
        
        reply = QMessageBox.question(
            self, "Unsaved Changes", message,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )
        
        if reply == QMessageBox.StandardButton.Save:
            if len(self.games_data) > 1:
                self._save_all_games()
                # Check if save failed (still have modified items)
                if any(self.modified.values()):
                    event.ignore()
                    return
            else:
                if not self._save_current_game_to_db():
                    event.ignore()
                    return
        elif reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return
        
        self._cleanup_connections()
        event.accept()
    
    def _cleanup_connections(self):
        """Disconnect theme_changed signal connections from dialog widgets to prevent memory leaks"""
        # Find all child widgets that might have connected to theme_changed
        for widget in self.findChildren(QWidget):
            try:
                # Try to disconnect if the widget has connected to theme_changed
                if hasattr(widget, '_apply_theme'):
                    self.theme_manager.theme_changed.disconnect(widget._apply_theme)
                elif hasattr(widget, '_load_theme'):
                    self.theme_manager.theme_changed.disconnect(widget._load_theme)
            except (TypeError, RuntimeError):
                # Ignore if not connected or already disconnected
                pass
