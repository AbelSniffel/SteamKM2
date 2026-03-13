"""Import Dialog for SteamKM2.

Provides options for importing game keys from various sources:
- Text files
- Legacy SteamKM1 JSON files
- SteamKM2 database files
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
    QLineEdit, QTextEdit, QWidget
)
from PySide6.QtCore import Qt
from pathlib import Path

from src.core.database.db_import import DatabaseImporter
from src.ui.dialogs.password_dialogs import PasswordInputDialog, VerifyDatabasePasswordDialog
from src.ui.widgets.section_groupbox import SectionGroupBox
from src.ui.ui_factory import UIFactory


class ImportDialog(QDialog):
    """Dialog for importing game keys from various sources."""
    
    def __init__(self, parent, db_manager, settings_manager=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.settings_manager = settings_manager or (parent.settings_manager if hasattr(parent, 'settings_manager') else None)
        self.importer = DatabaseImporter(db_manager)
        self.selected_file = None
        self.file_type = None
        self.is_encrypted = False
        self.added_game_ids = []  # Track IDs of imported games
        
        self.setWindowTitle("Import Game Keys")
        self.setMinimumWidth(600)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Import game keys from various sources:")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Import type selection
        type_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Select Import Type"
        ) if self.settings_manager else SectionGroupBox(title="Select Import Type")
        
        self.type_button_group = QButtonGroup(self)
        
        # Text file option
        self.rb_text = QRadioButton("Text File (.txt)")
        self.rb_text.setChecked(True)
        info_text = QLabel("  Import from plain text file with game titles and keys")
        info_text.setStyleSheet("color: gray; font-size: 11px;")
        self.type_button_group.addButton(self.rb_text, 0)
        type_group.content_layout.addWidget(self.rb_text)
        type_group.content_layout.addWidget(info_text)
        
        # Legacy JSON option
        self.rb_legacy_json = QRadioButton("Legacy SteamKM1 File (.json / .enc)")
        info_legacy = QLabel("  Import from previous SteamKM1 app database (JSON or encrypted .enc)")
        info_legacy.setStyleSheet("color: gray; font-size: 11px;")
        self.type_button_group.addButton(self.rb_legacy_json, 1)
        type_group.content_layout.addWidget(self.rb_legacy_json)
        type_group.content_layout.addWidget(info_legacy)
        
        # Database option
        self.rb_database = QRadioButton("SteamKM2 Database (.db / .db.enc)")
        info_db = QLabel("  Import/restore from SteamKM2 database backup")
        info_db.setStyleSheet("color: gray; font-size: 11px;")
        self.type_button_group.addButton(self.rb_database, 2)
        type_group.content_layout.addWidget(self.rb_database)
        type_group.content_layout.addWidget(info_db)
        
        # Database import mode (merge vs replace) - visible only for database imports
        self.db_mode_container = QWidget()
        self.db_mode_container.setObjectName("Transparent")
        db_mode_layout = QHBoxLayout(self.db_mode_container)
        db_mode_layout.setContentsMargins(20, 5, 0, 0)
        
        self.db_mode_group = QButtonGroup(self)
        self.rb_replace = QRadioButton("Replace current database")
        self.rb_replace.setChecked(True)
        self.rb_merge = QRadioButton("Merge with current database")
        self.db_mode_group.addButton(self.rb_replace, 0)
        self.db_mode_group.addButton(self.rb_merge, 1)
        db_mode_layout.addWidget(self.rb_replace)
        db_mode_layout.addWidget(self.rb_merge)
        db_mode_layout.addStretch()
        
        type_group.content_layout.addWidget(self.db_mode_container)
        self.db_mode_container.setVisible(False)  # Hidden until database type selected
        
        # Connect to show/hide merge option based on import type
        self.type_button_group.buttonClicked.connect(self._on_import_type_changed)
        
        layout.addWidget(type_group)
        
        # File selection area
        file_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Selected File"
        ) if self.settings_manager else SectionGroupBox(title="Selected File")
        
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        file_group.content_layout.addWidget(self.file_label)
        
        select_btn = QPushButton("Browse...")
        select_btn.clicked.connect(self._browse_file)
        file_group.content_layout.addWidget(select_btn)
        
        layout.addWidget(file_group)
        
        # Preview area (for text files)
        self.preview_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Preview"
        ) if self.settings_manager else SectionGroupBox(title="Preview")
        
        # Game counter label
        self.game_count_label = QLabel("No games detected")
        self.game_count_label.setStyleSheet("font-weight: bold; color: #0078d4; font-size: 12px;")
        self.preview_group.content_layout.addWidget(self.game_count_label)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(200)
        self.preview_text.setMaximumHeight(300)
        self.preview_group.content_layout.addWidget(self.preview_text)
        
        layout.addWidget(self.preview_group)
        self.preview_group.setVisible(False)
        
        # Format help text
        format_help = QLabel(
            "<b>Supported text file formats:</b><br>"
            "• Title | Key<br>"
            "• Title: Key<br>"
            "• Title - Key<br>"
            "• Key only (one per line)<br>"
            "• Lines starting with # are ignored"
        )
        format_help.setStyleSheet("color: gray; font-size: 11px; padding: 10px;")
        layout.addWidget(format_help)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._do_import)
        import_btn.setDefault(True)
        button_layout.addWidget(import_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _browse_file(self):
        """Browse for a file to import."""
        import os
        import platform
        
        selected_type = self.type_button_group.checkedId()
        
        # Set file filter and default directory based on selection
        default_dir = ""
        if selected_type == 0:  # Text file
            filter_str = "Text Files (*.txt *.text);;All Files (*.*)"
            title = "Select Text File"
        elif selected_type == 1:  # Legacy JSON
            filter_str = "Legacy Files (*.json *.enc *.json.enc);;JSON Files (*.json);;Encrypted Files (*.enc);;All Files (*.*)"
            title = "Select Legacy SteamKM1 File"
            # Set default directory to legacy SteamKM folder (same as SteamKM2 but without the "2")
            default_dir = self._get_legacy_steamkm_path()
        else:  # Database
            filter_str = "Database Files (*.db *.db.enc);;All Files (*.*)"
            title = "Select Database File"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            default_dir,
            filter_str
        )
        
        if file_path:
            self.selected_file = file_path
            self.file_label.setText(f"Selected: {Path(file_path).name}")
            
            # Detect file type
            self.file_type, self.is_encrypted = self.importer.detect_file_type(file_path)
            
            # Show preview for text files
            if self.file_type == 'text':
                self._show_preview(file_path)
            else:
                self.preview_group.setVisible(False)
    
    def _show_preview(self, file_path: str):
        """Show preview of text file (all lines) and count games."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Count valid game lines (non-empty, non-comment)
            game_count = 0
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    game_count += 1
            
            # Update counter label
            if game_count == 0:
                self.game_count_label.setText("⚠️ No games detected")
                self.game_count_label.setStyleSheet("font-weight: bold; color: #d9534f; font-size: 12px;")
            elif game_count == 1:
                self.game_count_label.setText("✓ 1 game detected")
                self.game_count_label.setStyleSheet("font-weight: bold; color: #5cb85c; font-size: 12px;")
            else:
                self.game_count_label.setText(f"✓ {game_count} games detected")
                self.game_count_label.setStyleSheet("font-weight: bold; color: #5cb85c; font-size: 12px;")
            
            # Show preview
            content = ''.join(lines)
            self.preview_text.setPlainText(content)
            self.preview_group.setVisible(True)
        except Exception as e:
            self.preview_text.setPlainText(f"Error reading file: {str(e)}")
            self.game_count_label.setText("⚠️ Error reading file")
            self.game_count_label.setStyleSheet("font-weight: bold; color: #d9534f; font-size: 12px;")
            self.preview_group.setVisible(True)
    
    def _do_import(self):
        """Perform the import based on selection."""
        if not self.selected_file:
            QMessageBox.warning(
                self,
                "No File Selected",
                "Please select a file to import."
            )
            return
        
        selected_type = self.type_button_group.checkedId()
        
        if selected_type == 2:  # Database import
            self._import_database()
        else:  # Text or Legacy JSON import
            self._import_games()
    
    def _import_games(self):
        """Import games from text file or legacy JSON."""
        try:
            # Get password if encrypted (using the unified password dialog)
            password = None
            if self.is_encrypted:
                # Use VerifyDatabasePasswordDialog with built-in retry and verification
                dialog = VerifyDatabasePasswordDialog(
                    self,
                    file_path=self.selected_file,
                    db_manager=self.db_manager,
                    max_attempts=3
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                password = dialog.get_password()
            
            # Parse the file based on type (password already verified if encrypted)
            if self.file_type == 'text':
                success, message, games = self.importer.import_from_text_file(self.selected_file)
            elif self.file_type == 'steamkm1_json':
                success, message, games = self.importer.import_from_legacy_json(self.selected_file, password)
            else:
                QMessageBox.critical(
                    self,
                    "Invalid File Type",
                    f"Unsupported file type. Please select a valid text, JSON, or database file."
                )
                return
            
            if not success:
                QMessageBox.critical(
                    self,
                    "Import Failed",
                    message
                )
                return
            
            # Show preview and confirm
            preview_text = f"{message}\n\nFirst few games:\n\n"
            for i, game in enumerate(games[:5]):
                preview_text += f"• {game['title']} ({game['platform']})\n"
            
            if len(games) > 5:
                preview_text += f"... and {len(games) - 5} more\n"
            
            preview_text += "\nDo you want to add these games to your database?"
            
            reply = QMessageBox.question(
                self,
                "Confirm Import",
                preview_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Check for duplicates before importing
            game_keys = [g.get('key', '') for g in games if g.get('key')]
            existing_games = self.db_manager.get_games_by_keys(game_keys)
            
            duplicates = []
            games_to_skip = set()
            games_to_overwrite = set()
            
            if existing_games:
                # Build list of duplicates for the resolution dialog
                for game in games:
                    key = game.get('key', '')
                    if key in existing_games:
                        duplicates.append((existing_games[key], game))
                
                if duplicates:
                    # Show duplicate resolution dialog
                    from src.ui.dialogs.duplicate_resolution_dialog import DuplicateResolutionDialog
                    dialog = DuplicateResolutionDialog(self, duplicates, self.settings_manager)
                    if dialog.exec() != QDialog.DialogCode.Accepted:
                        return
                    
                    games_to_skip = dialog.get_games_to_skip()
                    games_to_overwrite = dialog.get_games_to_overwrite()
            
            # Import games to database with duplicate handling
            success, message, added_ids = self.importer.import_games_to_database(
                games, 
                skip_keys=games_to_skip,
                overwrite_keys=games_to_overwrite
            )
            
            if success:
                QMessageBox.information(
                    self,
                    "Import Successful",
                    message
                )
                # Store the added IDs so parent can access them
                self.added_game_ids = added_ids
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Import Failed",
                    message
                )
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"An error occurred during import: {str(e)}"
            )
    
    def _on_import_type_changed(self, button):
        """Handle import type selection change."""
        selected_type = self.type_button_group.checkedId()
        # Show merge option only for database imports
        self.db_mode_container.setVisible(selected_type == 2)
    
    def _import_database(self):
        """Import a complete database file."""
        try:
            # Get password if encrypted (using the unified password dialog)
            password = None
            if self.is_encrypted:
                # Use VerifyDatabasePasswordDialog with built-in retry and verification
                dialog = VerifyDatabasePasswordDialog(
                    self,
                    file_path=self.selected_file,
                    db_manager=self.db_manager,
                    max_attempts=3
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                password = dialog.get_password()
            
            # Check if merge or replace mode
            is_merge_mode = self.db_mode_group.checkedId() == 1
            
            if is_merge_mode:
                # Merge mode: extract games and import with duplicate handling
                self._import_database_merge(password)
            else:
                # Replace mode: full database replacement
                self._import_database_replace(password)
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"An error occurred during database import: {str(e)}"
            )
    
    def _import_database_merge(self, password: str | None):
        """Import database in merge mode - adds games to existing database."""
        # Extract games from source database
        success, message, games = self.importer.merge_database(self.selected_file, password)
        
        if not success:
            QMessageBox.critical(self, "Merge Failed", message)
            return
        
        if not games:
            QMessageBox.information(self, "No Games", "No games found in the source database.")
            return
        
        # Check for duplicates
        game_keys = [g.get('key', '') for g in games if g.get('key')]
        existing_games = self.db_manager.get_games_by_keys(game_keys)
        
        duplicates = []
        games_to_skip = set()
        games_to_overwrite = set()
        
        if existing_games:
            for game in games:
                key = game.get('key', '')
                if key in existing_games:
                    duplicates.append((existing_games[key], game))
            
            if duplicates:
                from src.ui.dialogs.duplicate_resolution_dialog import DuplicateResolutionDialog
                dialog = DuplicateResolutionDialog(self, duplicates, self.settings_manager)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                
                games_to_skip = dialog.get_games_to_skip()
                games_to_overwrite = dialog.get_games_to_overwrite()
        
        # Import games with duplicate handling
        success, message, added_ids = self.importer.import_games_to_database(
            games,
            skip_keys=games_to_skip,
            overwrite_keys=games_to_overwrite
        )
        
        if success:
            QMessageBox.information(self, "Merge Successful", message)
            self.added_game_ids = added_ids
            self.accept()
        else:
            QMessageBox.critical(self, "Merge Failed", message)
    
    def _import_database_replace(self, password: str | None):
        """Import database in replace mode - replaces entire database."""
        # Warn about overwriting
        reply = QMessageBox.warning(
            self,
            "Import Database",
            "Importing this database will replace your current database.\n\n"
            "A backup of your current database will be created automatically.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Create backup of current database
        success, backup_path, message = self.db_manager.create_backup('pre-import')
        if not success:
            reply = QMessageBox.warning(
                self,
                "Backup Failed",
                f"Failed to create backup: {message}\n\n"
                "Do you want to continue without backup?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Import database
        success, message = self.importer.import_database(self.selected_file, password)
        
        if success:
            QMessageBox.information(
                self,
                "Import Successful",
                f"{message}\n\n"
                f"Backup of previous database: {backup_path if backup_path else 'None'}"
            )
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Import Failed",
                message
            )
    
    def _get_legacy_steamkm_path(self) -> str:
        """Get the path to the legacy SteamKM folder (without the '2').
        
        This mirrors the SteamKM2 app data location but uses 'SteamKM' instead.
        """
        import os
        import platform
        
        system = platform.system()
        home = os.path.expanduser("~")
        
        if system == "Windows":
            # Windows: %APPDATA%\SteamKM
            app_data = os.environ.get('APPDATA', os.path.join(home, 'AppData', 'Roaming'))
            legacy_path = os.path.join(app_data, 'SteamKM')
        elif system == "Darwin":  # macOS
            # macOS: ~/Library/Application Support/SteamKM
            legacy_path = os.path.join(home, 'Library', 'Application Support', 'SteamKM')
        else:  # Linux and other Unix-like systems
            # Linux: ~/.config/SteamKM or $XDG_CONFIG_HOME/SteamKM
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.join(home, '.config'))
            legacy_path = os.path.join(config_home, 'SteamKM')
        
        # Return the path if it exists, otherwise return empty string
        if os.path.exists(legacy_path):
            return legacy_path
        return ""
