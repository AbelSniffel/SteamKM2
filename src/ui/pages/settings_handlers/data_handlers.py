"""
Data-related handlers for Settings Page.
Contains tag management, platform detection, and data loading handlers.
"""

from PySide6.QtWidgets import QMessageBox

from src.ui.widgets.main_widgets import create_tag_buttons, create_no_tags_placeholder
from src.ui.utils import clear_layout
from src.core.platform_detector import PlatformDetector
from src.core.database_manager import DatabaseLockedError


class DataHandlers:
    """Mixin class containing data-related handlers for SettingsPage."""
    
    # =========================================================================
    # Tag Handlers
    # =========================================================================
    
    def _load_tags(self):
        """Load tags and update tag button layout - only shows custom (non-Steam) tags."""
        try:
            clear_layout(self.tags_hbox)
            tags = self.db_manager.get_tags()
            custom_tags = [t for t in tags if not t.get('is_builtin')]

            if custom_tags:
                create_tag_buttons(
                    self.tags_hbox,
                    custom_tags,
                    lambda t: t['name'],
                    lambda t: self._delete_tag_confirm(t['id'], t['name']),
                    suffix='✕'
                )
            else:
                create_no_tags_placeholder(self.tags_hbox)
        except DatabaseLockedError:
            self._notify('warning', "Failed to get available tags, please unlock the database.")
        except Exception as e:
            self._notify('error', f"Failed to load tags: {str(e)}")

    def _create_new_tag(self):
        """Create a new custom tag."""
        tag_name = self.new_tag_input.text().strip()
        if not tag_name:
            self._notify('warning', "Please enter a tag name.")
            return
        try:
            self.db_manager.add_tag(tag_name)
            self.new_tag_input.clear()
            self._load_tags()
            self._notify('success', f"Tag '{tag_name}' created")
            self.tags_updated.emit()
        except Exception as e:
            self._notify('error', f"Failed to create tag: {str(e)}")

    def _delete_tag_confirm(self, tag_id, tag_name):
        """Confirm and delete a tag."""
        reply = QMessageBox.question(
            self, "Delete Tag",
            f"Are you sure you want to delete the tag '{tag_name}'?\nThis will remove it from all games.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if hasattr(self.db_manager, 'delete_tag'):
                    if self.db_manager.delete_tag(tag_id):
                        self._load_tags()
                        self._notify('success', f"Tag '{tag_name}' deleted")
                        self.tags_updated.emit()
                    else:
                        self._notify('error', "Failed to delete tag")
            except Exception as e:
                self._notify('error', f"Failed to delete tag: {str(e)}")

    def _remove_custom_tags(self):
        """Remove all custom (non-Steam) tags."""
        reply = QMessageBox.question(
            self, "Remove Custom Tags",
            "Are you sure you want to delete all custom tags?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                deleted = self.db_manager.delete_custom_tags()
                self._load_tags()
                self.status_message.emit(f"Deleted {deleted} custom tags")
                self.tags_updated.emit()
            except Exception as e:
                self._notify('error', f"Failed to delete custom tags: {e}")

    def _remove_unused_tags(self):
        """Remove all tags that are not assigned to any games."""
        reply = QMessageBox.question(
            self, "Remove Unused Tags",
            "Are you sure you want to delete all unused Steam-provided tags?\n\n"
            "This will remove tags that are not assigned to any games (Steam-provided tags only). "
            "Any custom tags you created will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                deleted = self.db_manager.delete_unused_tags()
                self._load_tags()

                if isinstance(deleted, list):
                    count = len(deleted)
                    if count > 0:
                        try:
                            print(f"Deleted {count} unused tag(s): {', '.join(deleted)}")
                        except Exception:
                            pass
                        self._notify('success', f"Deleted {count} unused tag(s)")
                    else:
                        self._notify('info', "No unused tags found")
                else:
                    if deleted > 0:
                        self._notify('success', f"Deleted {deleted} unused tag(s)")
                    else:
                        self._notify('info', "No unused tags found")
                self.tags_updated.emit()
            except Exception as e:
                self._notify('error', f"Failed to delete unused tags: {e}")
    
    # =========================================================================
    # Platform Handlers
    # =========================================================================
    
    def _load_platforms(self):
        """Load detected platforms."""
        try:
            self.platform_list.clear()
            db_platforms = self.db_manager.get_platforms()
            all_platforms = PlatformDetector.get_all_platforms()
            
            for platform in db_platforms:
                self.platform_list.addItem(f"{platform} (in use)")
            
            for platform in all_platforms:
                if platform not in db_platforms:
                    self.platform_list.addItem(f"{platform}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load platforms: {str(e)}")
    
    def _test_platform_detection(self):
        """Test platform detection for the entered key."""
        key = self.test_key_input.text().strip()
        if key:
            try:
                detected = PlatformDetector.detect_platform(key)
                self.detected_platform_label.setText(f"Detected: {detected}")
            except Exception:
                self.detected_platform_label.setText("Detected: Error")
        else:
            self.detected_platform_label.setText("Waiting for input...")
    
    # =========================================================================
    # Encryption Control Updates
    # =========================================================================
    
    def _update_encryption_controls(self):
        """Update encryption-related UI controls based on database state."""
        encrypted = False
        locked = False
        try:
            encrypted = bool(self.db_manager.is_encrypted())
            locked = bool(self.db_manager.requires_password())
        except Exception:
            pass
        
        self.encryption_toggle.setCheckedNoAnimation(encrypted)
        self.change_password_btn.setVisible(encrypted)
        
        if db_group := getattr(self, 'db_section_group', None):
            db_group.updateGeometry()
            if db_group.parent():
                db_group.parent().updateGeometry()
        
        if locked and encrypted:
            status = "Database is encrypted and locked. Unlock from the Home page"
        elif encrypted:
            status = "Database encryption is enabled. Don't forget your password!"
        else:
            status = "Encryption is disabled"
        self.encryption_status_label.setText(status)
        
        return encrypted, locked
    
    # =========================================================================
    # Database Switching Handlers
    # =========================================================================
    
    def _browse_switch_database(self):
        """Open file dialog to select a different database file."""
        from PySide6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Database File",
            "",
            "SteamKM2 Database (*.db *.db.enc);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        self._switch_to_database(file_path)
    
    def _create_new_database(self):
        """Create a new empty database file."""
        from PySide6.QtWidgets import QFileDialog
        import os
        import sqlite3
        
        # Default to the appdata folder where settings are stored
        default_dir = self.settings_manager.get_app_data_dir()
        default_path = os.path.join(default_dir, "games.db")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create New Database",
            default_path,
            "SteamKM2 Database (*.db);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        # Add .db extension if not present
        if not file_path.endswith('.db'):
            file_path += '.db'
        
        # Check if file already exists
        if os.path.exists(file_path):
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"The file {os.path.basename(file_path)} already exists.\n"
                "Do you want to replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Remove existing file
            try:
                os.remove(file_path)
            except Exception as e:
                self._notify('error', f"Cannot remove existing file: {e}")
                return
        
        # Ensure directory exists
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
        except Exception as e:
            self._notify('error', f"Cannot create directory: {e}")
            return
        
        # Create an empty database file with the required schema
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            
            # Create tables using the same schema as database_manager._create_tables()
            cursor.executescript('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    game_key TEXT NOT NULL,
                    platform_type TEXT NOT NULL DEFAULT 'Steam',
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    is_used BOOLEAN DEFAULT FALSE,
                    image_path TEXT,
                    deadline_enabled BOOLEAN DEFAULT FALSE,
                    deadline_at TEXT,
                    dlc_enabled BOOLEAN DEFAULT FALSE,
                    steam_app_id TEXT,
                    steam_review_score INTEGER,
                    steam_review_count INTEGER
                );
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT DEFAULT '#0078d4',
                    is_builtin BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS game_tags (
                    game_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY (game_id, tag_id),
                    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_games_title ON games(title);
                CREATE INDEX IF NOT EXISTS idx_games_key ON games(game_key);
                CREATE INDEX IF NOT EXISTS idx_games_platform ON games(platform_type);
                CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            self._notify('error', f"Failed to create database: {e}")
            # Clean up partial file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            return
        
        # Switch to the new database
        self._switch_to_database(file_path)
    
    def _use_default_database(self):
        """Switch back to the default database location."""
        default_path = self.settings_manager.get_default_database_path()
        
        if self.db_manager.db_path == default_path:
            self._notify('info', "Already using the default database")
            return
        
        self._switch_to_database(default_path, is_default=True)
    
    def _on_recent_db_selected(self, index: int):
        """Handle selection from recent databases dropdown."""
        if index == 0:
            return  # First item is placeholder
        
        combo = getattr(self, 'recent_db_combo', None)
        if not combo:
            return
        
        db_path = combo.itemData(index)
        if db_path:
            self._switch_to_database(db_path)
        
        # Reset combo to placeholder
        combo.setCurrentIndex(0)
    
    def _switch_to_database(self, new_path: str, is_default: bool = False):
        """Perform the actual database switch."""
        import os
        
        if not new_path:
            return
        
        # Check if switching to same database
        if os.path.normpath(new_path) == os.path.normpath(self.db_manager.db_path):
            self._notify('info', "Already using this database")
            return
        
        # Confirm the switch
        reply = QMessageBox.question(
            self,
            "Switch Database",
            f"Switch to database:\n{os.path.basename(new_path)}\n\n"
            f"Full path: {new_path}\n\n"
            "The current database will be closed. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Try password if the database is encrypted
        password = None
        from src.core.encryption_manager import EncryptionManager
        try:
            temp_enc = EncryptionManager(new_path)
            if temp_enc.is_encrypted():
                from src.ui.dialogs.password_dialogs import PasswordInputDialog
                dialog = PasswordInputDialog(self, "Enter database password:")
                if dialog.exec():
                    password = dialog.get_password()
                else:
                    return
        except Exception:
            pass
        
        # Perform the switch
        success, message = self.db_manager.switch_database(new_path, password)
        
        if success:
            # Update settings
            if is_default:
                self.settings_manager.set_database_path('')
            else:
                self.settings_manager.set_database_path(new_path)
            
            # Update UI
            self._update_current_db_display()
            self._update_encryption_controls()
            
            # Notify and refresh
            self._notify('success', message)
            
            # Emit signal if available to refresh main window
            if hasattr(self, 'tags_updated'):
                self.tags_updated.emit()
        else:
            self._notify('error', message)
    
    def _update_current_db_display(self):
        """Update the current database label display."""
        import os
        if label := getattr(self, 'current_db_label', None):
            current_path = self.settings_manager.get_database_path()
            label.setText(os.path.basename(current_path))
            label.setToolTip(current_path)
    
    # =========================================================================
    # Health Status Updates
    # =========================================================================
    
    def update_health_status(self, text: str, color: str) -> None:
        """Public API to update the header health status label."""
        try:
            self.health_status_label.setText(text)
            self.health_status_label.setStyleSheet(f"color: {color};")
        except Exception:
            pass

    def _count_severities(self, issues):
        """Count issues by severity level."""
        counts = {'critical': 0, 'error': 0, 'warning': 0}
        for issue in issues:
            if (sev := getattr(issue, 'severity', None)) in counts:
                counts[sev] += 1
        return counts

    def _update_health_status(self):
        """Internal timer handler to refresh the header health status."""
        if not (mw := self.window()):
            return
        if not (hm := getattr(mw, 'health_monitor', None)):
            return

        try:
            active = getattr(hm, 'get_active_issues', lambda: [])()
            logged = getattr(hm, 'get_issue_log', lambda: [])()
            
            ac = self._count_severities(active)
            lc = self._count_severities(logged)
            
            try:
                from src.ui.pages.update_page import UpdatePage
                text, color = UpdatePage._get_health_display(ac, lc)
            except Exception:
                text, color = "● Status Unknown", "#9e9e9e"
            
            self.update_health_status(text, color)
        except Exception:
            self.update_health_status("● Status Unknown", "#9e9e9e")
