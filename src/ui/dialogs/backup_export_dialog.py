"""Backup and Export Dialog for SteamKM2.

Provides options for backing up/exporting the database in various formats.
"""

from typing import Optional, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from pathlib import Path
from datetime import datetime
from src.core.database.db_export import DatabaseExporter


class BackupExportDialog(QDialog):
    """Dialog for choosing backup/export format and location."""
    
    def __init__(self, parent, db_manager, settings_manager):
        super().__init__(parent)
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.setWindowTitle("Backup / Export Database")
        self.setMinimumWidth(500)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Choose how to backup/export your database:")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Format selection group
        format_group = QGroupBox()
        format_layout = QVBoxLayout(format_group)
        
        self.button_group = QButtonGroup(self)
        
        # Standard backup option
        self.rb_standard = QRadioButton("Standard Backup (keeps current format)")
        self.rb_standard.setChecked(True)
        info_standard = QLabel("  Creates a backup in the backups folder. Preserves encryption if enabled.")
        info_standard.setStyleSheet("color: gray; font-size: 11px;")
        self.button_group.addButton(self.rb_standard, 0)
        format_layout.addWidget(self.rb_standard)
        format_layout.addWidget(info_standard)
        
        # Plaintext list option
        self.rb_plaintext = QRadioButton("Text File (decrypted)")
        info_plaintext = QLabel("  Exports a simple list of game titles and keys (unencrypted).")
        info_plaintext.setStyleSheet("color: gray; font-size: 11px;")
        self.button_group.addButton(self.rb_plaintext, 1)
        format_layout.addWidget(self.rb_plaintext)
        format_layout.addWidget(info_plaintext)
        
        # Encrypted DB option (only if encrypted)
        if self.db_manager.is_encrypted():
            self.rb_encrypted_db = QRadioButton("Full Database (encrypted)")
            info_encrypted = QLabel("  Exports the complete encrypted database file.")
            info_encrypted.setStyleSheet("color: gray; font-size: 11px;")
            self.button_group.addButton(self.rb_encrypted_db, 2)
            format_layout.addWidget(self.rb_encrypted_db)
            format_layout.addWidget(info_encrypted)
        else:
            self.rb_encrypted_db = None
        
        # Decrypted DB option
        self.rb_decrypted_db = QRadioButton("Full Database (decrypted)")
        info_decrypted = QLabel("  Exports the complete database as a standard SQLite file (unencrypted).")
        info_decrypted.setStyleSheet("color: gray; font-size: 11px;")
        self.button_group.addButton(self.rb_decrypted_db, 3)
        format_layout.addWidget(self.rb_decrypted_db)
        format_layout.addWidget(info_decrypted)
        
        layout.addWidget(format_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._do_export)
        export_btn.setDefault(True)
        button_layout.addWidget(export_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _do_export(self):
        """Perform the export based on selection."""
        selected_id = self.button_group.checkedId()
        
        if selected_id == 0:
            # Standard backup
            self._standard_backup()
        elif selected_id == 1:
            # Plaintext list
            self._export_plaintext()
        elif selected_id == 2:
            # Encrypted DB
            self._export_encrypted_db()
        elif selected_id == 3:
            # Decrypted DB
            self._export_decrypted_db()
    
    def _standard_backup(self):
        """Create a standard backup."""
        try:
            success, backup_path, message = self.db_manager.create_backup('manual')
            if success:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Backup Created")
                msg.setText(f"Database backup created:\n{backup_path}")
                open_btn = msg.addButton("Open Location", QMessageBox.ActionRole)
                msg.addButton(QMessageBox.Ok)
                msg.exec()
                if msg.clickedButton() == open_btn:
                    folder = Path(backup_path).parent
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Backup Failed",
                    message or "Unknown error during backup"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Backup Error",
                f"Failed to create backup: {str(e)}"
            )

    # Helper utilities to reduce repetition -------------------------------------------------
    def _get_timestamped_name(self, prefix: str, ext: str) -> str:
        """Return a timestamped default filename like '{prefix}_{YYYYmmdd_HHMMSS}.{ext}'."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{ts}.{ext}"

    def _ensure_extension(self, file_path: str, extension: str) -> str:
        """Ensure the returned path ends with the provided extension."""
        normalized = extension if extension.startswith('.') else f".{extension}"
        if file_path.lower().endswith(normalized.lower()):
            return file_path
        return f"{file_path}{normalized}"

    def _show_export_result(self, success: bool, message: Optional[str], file_path: Optional[str], extra: Optional[str] = None) -> None:
        """Show a standardized result dialog for export operations.

        If success is True, allows opening the file location. On failure shows critical message.
        """
        if success:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Export Successful")
            text = (message or "Export completed successfully.")
            if file_path:
                text = f"{text}\n\nSaved to: {file_path}"
            if extra:
                text = f"{text}\n\n{extra}"
            msg.setText(text)
            open_btn = msg.addButton("Open Location", QMessageBox.ActionRole)
            msg.addButton(QMessageBox.Ok)
            msg.exec()
            if msg.clickedButton() == open_btn and file_path:
                folder = Path(file_path).parent
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
            self.accept()
        else:
            QMessageBox.critical(self, "Export Failed", message or "Unknown export error")

    def _choose_save_file(self, title: str, default_name: str, filter_str: str) -> Optional[str]:
        """Show save file dialog and return chosen path or None if canceled."""
        file_path, _ = QFileDialog.getSaveFileName(self, title, default_name, filter_str)
        return file_path or None
    
    def _export_plaintext(self):
        """Export as plaintext list."""
        default_name = self._get_timestamped_name("steamkm2_games", "txt")
        file_path = self._choose_save_file("Export Game List", default_name, "Text Files (*.txt);;All Files (*.*)")
        if not file_path:
            return

        exporter = DatabaseExporter(self.db_manager)
        success, message = exporter.export_to_plaintext(file_path)
        self._show_export_result(success, message, file_path)
    
    def _export_encrypted_db(self):
        """Export as encrypted database."""
        default_name = self._get_timestamped_name("steamkm2_encrypted", "db.enc")
        file_path = self._choose_save_file("Export Full Database (Encrypted)", default_name, "Encrypted Database Files (*.enc);;All Files (*.*)")
        if not file_path:
            return
        
        final_path = self._ensure_extension(file_path, ".enc")
        exporter = DatabaseExporter(self.db_manager)
        success, message = exporter.export_to_encrypted_db(final_path)
        extra = "Remember: You need the single .enc file (contains metadata) to import this database." if success else None
        self._show_export_result(success, message, final_path, extra=extra)
    
    def _export_decrypted_db(self):
        """Export as decrypted SQLite database."""
        default_name = self._get_timestamped_name("steamkm2_decrypted", "db")
        file_path = self._choose_save_file("Export Full Database (Decrypted)", default_name, "Database Files (*.db);;All Files (*.*)")
        if not file_path:
            return

        exporter = DatabaseExporter(self.db_manager)
        success, message = exporter.export_to_decrypted_db(file_path)
        self._show_export_result(success, message, file_path)
