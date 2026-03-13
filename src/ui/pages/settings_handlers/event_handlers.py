"""
Event handlers for Settings Page.
Contains all callback methods for UI events to reduce main settings_page.py size.
"""

import os
import subprocess
import platform
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog, QApplication
from PySide6.QtCore import QTimer

from src.core.encryption_manager import InvalidPasswordError
from src.ui.dialogs.password_dialogs import (
    SetDatabasePasswordDialog,
    ChangeDatabasePasswordDialog,
    VerifyDatabasePasswordDialog,
)
from src.ui.widgets.section_groupbox import SectionGroupBox


class SettingsEventHandlers:
    """Mixin class containing event handlers for SettingsPage.
    
    This class is designed to be used as a mixin with SettingsPage to reduce
    the main file size while keeping all functionality intact.
    """
    
    # =========================================================================
    # Import/Export Settings Handlers
    # =========================================================================
    
    def _export_settings(self):
        """Export settings to INI file."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Settings (INI)", "settings.ini", "INI Files (*.ini)")
        if not path:
            return
        if self.settings_manager.export_settings(path):
            self.status_message.emit(f"Settings exported to {os.path.basename(path)}")
        else:
            self._notify('error', "Failed to export settings")

    def _import_settings(self):
        """Import settings from INI file."""
        path, _ = QFileDialog.getOpenFileName(self, "Import Settings (INI)", "", "INI Files (*.ini)")
        if not path:
            return
        if self.settings_manager.import_settings(path):
            self.refresh()
            self.status_message.emit("Settings imported")
        else:
            self._notify('error', "Failed to import settings")

    def _reset_defaults_and_reload(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self, "Reset Settings", "Reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings_manager.reset_to_defaults()
            try:
                if app := QApplication.instance():
                    self.theme_manager.set_theme(self.settings_manager.get('current_theme', 'Dark'))
            except Exception:
                pass
            self.refresh()

    # =========================================================================
    # Encryption Handlers
    # =========================================================================
    
    def _on_encryption_toggle_requested(self, checked: bool):
        """Handle encryption toggle request."""
        if self._is_initializing:
            return
        if checked:
            self._prompt_enable_encryption()
        else:
            self._prompt_disable_encryption()

    def _prompt_enable_encryption(self):
        """Prompt user to enable encryption."""
        dialog = SetDatabasePasswordDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            try:
                self.encryption_toggle.setCheckedAnimated(False)
            except Exception:
                self._update_encryption_controls()
            return
        
        password = dialog.get_password()
        if not password:
            try:
                self.encryption_toggle.setCheckedAnimated(False)
            except Exception:
                self._update_encryption_controls()
            return
        
        try:
            self.db_manager.enable_encryption(password)
            self._notify('success', "Database encryption enabled")
            self.status_message.emit("Database encryption enabled")
            self.encryption_status_changed.emit(True)
            self._update_encryption_controls()
        except Exception as exc:
            self._notify('error', f"Failed to enable encryption: {exc}")
            try:
                self.encryption_toggle.setCheckedAnimated(False)
            except Exception:
                self._update_encryption_controls()

    def _prompt_disable_encryption(self):
        """Prompt user to disable encryption."""
        dialog = VerifyDatabasePasswordDialog(self, db_manager=self.db_manager)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            try:
                self.encryption_toggle.setCheckedAnimated(True)
            except Exception:
                self._update_encryption_controls()
            return
        
        password = dialog.get_password()
        try:
            self.db_manager.disable_encryption(password)
            self._notify('success', "Database encryption disabled")
            self.status_message.emit("Database encryption disabled")
            self.encryption_status_changed.emit(False)
            self._update_encryption_controls()
        except InvalidPasswordError:
            self._notify('error', "Incorrect password — encryption unchanged")
            try:
                self.encryption_toggle.setCheckedAnimated(True)
            except Exception:
                self._update_encryption_controls()
        except Exception as exc:
            self._notify('error', f"Failed to disable encryption: {exc}")
            try:
                self.encryption_toggle.setCheckedAnimated(True)
            except Exception:
                self._update_encryption_controls()

    def _on_change_password_clicked(self):
        """Handle password change request."""
        if not self.db_manager.is_encrypted():
            self._notify('warning', "Enable encryption first")
            return
        
        dialog = ChangeDatabasePasswordDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        current_pw, new_pw = dialog.get_passwords()
        try:
            self.db_manager.change_password(current_pw, new_pw)
            self._notify('success', "Database password updated")
            self.status_message.emit("Database password updated")
            self.encryption_status_changed.emit(True)
            self._update_encryption_controls()
        except InvalidPasswordError:
            self._notify('error', "Incorrect current password")
        except Exception as exc:
            self._notify('error', f"Failed to change password: {exc}")

    # =========================================================================
    # Toggle Handlers
    # =========================================================================
    
    def _on_auto_update_toggled(self, checked):
        """Handle auto-update toggle."""
        self.settings_manager.set('auto_update_check', checked)
        self.status_message.emit(f"Auto-update check {'enabled' if checked else 'disabled'}")
    
    def _on_auto_backup_toggled(self, checked):
        """Handle auto-backup toggle."""
        self.settings_manager.set('auto_backup_enabled', checked)
        self.status_message.emit(f"Auto-backup {'enabled' if checked else 'disabled'}")
        try:
            if mw := self.window():
                if hasattr(mw, 'restart_backup_timer'):
                    mw.restart_backup_timer()
        except Exception:
            pass
    
    def _on_status_bar_toggled(self, checked: bool):
        """Handle status bar visibility toggle."""
        self.settings_manager.set('show_status_bar', checked)
        self.status_bar_visibility_changed.emit(checked)
        self.status_message.emit(f"Status bar {'shown' if checked else 'hidden'}")

    def _on_debug_mode_toggled(self, checked: bool):
        """Handle toggling of the global debug mode."""
        self.settings_manager.set('debug_mode', checked)
        self.status_message.emit(f"Debug Mode {'enabled' if checked else 'disabled'}")

        # Update health monitor dialog
        try:
            if mw := self.window():
                if hmw := getattr(mw, 'health_monitor_window', None):
                    try:
                        hmw.set_debug_controls_visible(checked)
                    except Exception:
                        if dbg := getattr(hmw, 'debug_group', None):
                            dbg.setVisible(checked)
        except Exception:
            pass

        # Update Home page debug filter button
        try:
            if mw := self.window():
                try:
                    mw.page_controller.ensure_and_call('Home', 'set_debug_mode_visible', checked)
                except Exception:
                    try:
                        mw._ensure_and_call('Home', 'set_debug_mode_visible', checked)
                    except Exception:
                        pass
        except Exception:
            pass
    
    # =========================================================================
    # Value Change Handlers
    # =========================================================================
    
    def _on_backup_interval_changed(self, value):
        """Handle backup interval change."""
        self.settings_manager.set('auto_backup_interval_minutes', value)
        self.status_message.emit(f"Auto-backup interval set to {value} minutes")
        try:
            if mw := self.window():
                if hasattr(mw, 'restart_backup_timer'):
                    mw.restart_backup_timer()
        except Exception:
            pass
    
    def _on_max_backup_changed(self, value):
        """Handle max backup count change."""
        self.settings_manager.set('backup_max_count', value)
        self.status_message.emit(f"Max backup count set to {value}")
        try:
            if hasattr(self.db_manager, 'backup_manager'):
                self.db_manager.backup_manager.max_backups = value
        except Exception:
            pass
    
    def _on_tooltip_animation_changed(self, text: str):
        """Handle tooltip animation type change."""
        self.settings_manager.set('tooltip_animation', text)
        self.status_message.emit(f"Tooltip animation set to {text}")
    
    def _on_tooltip_show_delay_changed(self, value: int):
        """Handle tooltip show delay change."""
        self.settings_manager.set('tooltip_show_delay', value)
        self.status_message.emit(f"Tooltip show delay set to {value}ms")
    
    # =========================================================================
    # Multi-Step Toggle Handlers
    # =========================================================================
    
    def _on_section_title_location_toggle_changed(self, index: int):
        """Handle change of section groupbox title location."""
        options = ["left", "top"]
        if 0 <= index < len(options):
            location = options[index]
            self.settings_manager.set('section_groupbox_title_location', location)
            SectionGroupBox.update_all_instances(location)
            self.status_message.emit(f"Section title location set to {location}.")
            self._notify('info', f"Section titles moved to {location}.")
    
    def _on_toggle_style_toggle_changed(self, index: int):
        """Handle change of toggle style."""
        options = ["regular", "dot"]
        if 0 <= index < len(options):
            style = options[index]
            self.settings_manager.set('toggle_style', style)
            from src.ui.widgets.toggles.styleable_toggle import StyleableToggle, StyleableLabel
            StyleableToggle.update_all_instances()
            StyleableLabel.update_all_instances()
            self.status_message.emit(f"Toggle style set to {style}.")
            self._notify('info', f"Toggle style changed to {style}.")
    
    def _on_page_navigation_bar_position_toggle_changed(self, index: int):
        """Handle change of page navigation bar position."""
        options = ["left", "top", "bottom", "right"]
        if 0 <= index < len(options):
            pos = options[index]
            self.settings_manager.set('page_navigation_bar_position', pos)
            self.page_navigation_bar_position_changed.emit(pos)
            self.status_message.emit(f"Page navigation bar position set to {pos}")
    
    def _on_page_navigation_bar_appearance_toggle_changed(self, index: int):
        """Handle change of page navigation bar appearance."""
        from src.ui.pages.settings_page import APPEARANCE_MAP
        options = list(APPEARANCE_MAP.keys())
        if 0 <= index < len(options):
            text = options[index]
            val = APPEARANCE_MAP.get(text, 'icon_and_text')
            self.settings_manager.set('page_navigation_bar_appearance', val)
            self.page_navigation_bar_appearance_changed.emit(val)
            self.status_message.emit(f"Page navigation bar appearance set to {text}")

    def _on_gradient_animation_toggle_changed(self, index: int):
        """Handle change of gradient animation type."""
        from src.ui.pages.settings_page import GRADIENT_ANIMATION_MAP
        options = list(GRADIENT_ANIMATION_MAP.keys())
        if 0 <= index < len(options):
            text = options[index]
            val = GRADIENT_ANIMATION_MAP.get(text, 'scroll')
            self.settings_manager.set('gradient_animation', val)
            if mw := self._get_active_window():
                if gb := getattr(mw, 'gradient_bar', None):
                    try:
                        gb.set_effect(val)
                    except Exception:
                        pass
            self.status_message.emit(f"Gradient animation set to {text}")
    
    # =========================================================================
    # Database Handlers
    # =========================================================================
    
    def _backup_database(self):
        """Show backup options dialog and export database."""
        from src.ui.dialogs.backup_export_dialog import BackupExportDialog
        dialog = BackupExportDialog(self, self.db_manager, self.settings_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._update_backup_info()
            self.status_message.emit("Database backup/export completed")
    
    def _update_backup_info(self):
        """Update the backup info label with current backup statistics."""
        try:
            info = self.db_manager.get_backup_info()
            backups = self.db_manager.list_backups()
            auto_count = len([b for b in backups if b.get('label') == 'auto'])
            manual_count = len([b for b in backups if b.get('label') == 'manual'])
            
            info_text = f"Backup Location: {info['backup_dir']}\n"
            info_text += f"Total Backups: {info['backup_count']} ({auto_count} auto, {manual_count} manual)\n"
            info_text += f"Total Size: {info['total_size']}"
            self.backup_info_label.setText(info_text)
        except Exception as e:
            self.backup_info_label.setText(f"Unable to retrieve backup info: {str(e)}")

    def _on_refresh_backup_info_clicked(self):
        """Manual handler for the refresh button."""
        try:
            self._update_backup_info()
            self.status_message.emit("Backup information refreshed")
        except Exception as e:
            self._notify('error', f"Failed to refresh backup info: {e}")
    
    def _import_database(self):
        """Import game keys from various sources."""
        from src.ui.dialogs import ImportDialog
        dialog = ImportDialog(self, self.db_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.status_message.emit("Import completed successfully")
            QTimer.singleShot(100, self.tags_updated.emit)
    
    # =========================================================================
    # Folder/File Handlers
    # =========================================================================
    
    def _open_config_folder(self):
        """Open the application data folder."""
        try:
            app_dir = self.settings_manager.get_app_data_dir()
            os.makedirs(app_dir, exist_ok=True)
            
            system = platform.system()
            if system == "Windows":
                os.startfile(app_dir)
            elif system == "Darwin":
                subprocess.run(["open", app_dir])
            else:
                subprocess.run(["xdg-open", app_dir])
            
            self.status_message.emit("Application data folder opened")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open app data folder: {str(e)}")
    
    # =========================================================================
    # Update Settings Handler
    # =========================================================================
    
    def _apply_update_settings(self):
        """Persist update-related settings and apply timer interval."""
        repo = self.repo_input.text().strip()
        token = self.api_token_input.text().strip()
        include_pre = bool(self.prerelease_toggle.isChecked())
        interval_min = int(self.interval_spin.value())
        show_unikm_button = bool(self.show_unikm_github_button_toggle.isChecked())
        unikm_repo = self.unikm_repo_input.text().strip()
        
        if '/' not in repo:
            self._notify('warning', "Please enter the repository in the format owner/repo")
            return
        if '/' not in unikm_repo:
            self._notify('warning', "Please enter the UniKM repository in the format owner/repo")
            return
        
        self.settings_manager.set('update_repo', repo)
        self.settings_manager.set('github_api_token', token)
        self.settings_manager.set('update_include_prereleases', include_pre)
        self.settings_manager.set('update_check_interval_min', interval_min)
        self.settings_manager.set('show_unikm_github_button', show_unikm_button)
        self.settings_manager.set('unikm_repo', unikm_repo)
        
        if mw := self.window():
            if hasattr(mw, 'update_manager'):
                try:
                    mw.update_manager.set_interval_min(interval_min)
                except Exception:
                    pass
            if hasattr(mw, 'page_controller'):
                try:
                    mw.page_controller.ensure_and_call('Update', 'update_unikm_button_state')
                except Exception:
                    pass
        
        self.status_message.emit("Update settings applied")
    
    # =========================================================================
    # Game Card Handlers
    # =========================================================================
    
    def _update_game_card_chips(self, setting_key: str, value: bool):
        """Update game card chip visibility and refresh the home page view."""
        self.settings_manager.set(setting_key, value)
        try:
            if mw := self.window():
                if hasattr(mw, 'page_controller'):
                    home = mw.page_controller.page_manager.get_instance('Home')
                    if home and hasattr(home, '_delegate'):
                        home._delegate._load_chip_visibility()
                        if hasattr(home, 'list_view'):
                            home.list_view.viewport().update()
        except Exception:
            pass
