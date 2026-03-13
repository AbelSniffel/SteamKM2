"""Dialogs for managing database encryption passwords."""

from __future__ import annotations

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QCheckBox,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)
from src.ui.widgets.main_widgets import create_line_edit, create_date_selector


def _error_label() -> QLabel:
    lbl = QLabel()
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #d9534f;")
    return lbl


class SetDatabasePasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Database Password")
        self.setModal(True)
        self._password: str = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_edit = QLineEdit()
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self._password_edit)
        form.addRow("Confirm", self._confirm_edit)
        layout.addLayout(form)

        self._message = _error_label()
        layout.addWidget(self._message)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._password_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _validate(self):
        password = self._password_edit.text().strip()
        confirm = self._confirm_edit.text().strip()
        if not password:
            self._message.setText("Password cannot be empty.")
            return
        if password != confirm:
            self._message.setText("Passwords do not match.")
            return
        self._password = password
        self.accept()

    def get_password(self) -> str:
        return self._password


class VerifyDatabasePasswordDialog(QDialog):
    def __init__(self, parent=None, *, file_path: str | None = None, db_manager=None, max_attempts: int = 3):
        """Dialog that verifies a password for an encrypted database file.

        Args:
            parent: parent widget
            file_path: path to the database file to verify (required for in-dialog verification)
            db_manager: DatabaseManager instance passed to DatabaseImporter for verification
            max_attempts: how many attempts to allow before aborting
        """
        super().__init__(parent)
        self.setWindowTitle("Enter Database Password")
        self.setModal(True)
        self._password: str = ""
        self._file_path = file_path
        self._db_manager = db_manager
        self._attempts_left = max_attempts

        layout = QVBoxLayout(self)
        # Short explanatory text to make the purpose of this dialog clear
        expl = QLabel(
            "Database file is encrypted. Please enter the password used to encrypt the file to continue."
        )
        expl.setWordWrap(True)
        layout.addWidget(expl)

        form = QFormLayout()

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("I won't look...")
        # Add a 'show password' checkbox to toggle visibility
        self._show_checkbox = QCheckBox("Show password")
        self._show_checkbox.toggled.connect(self._on_show_toggled)
        pw_row_widget = QWidget()
        pw_row_layout = QHBoxLayout(pw_row_widget)
        pw_row_layout.setContentsMargins(0, 0, 0, 0)
        pw_row_layout.addWidget(self._password_edit)
        pw_row_layout.addWidget(self._show_checkbox)
        form.addRow("Password:", pw_row_widget)
        layout.addLayout(form)

        self._message = _error_label()
        # Provide a default neutral help message area; errors will replace it
        self._message.setText(f"Attempts remaining: {self._attempts_left}")
        layout.addWidget(self._message)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._password_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _validate(self):
        password = self._password_edit.text().strip()
        if not password:
            self._message.setText("Password cannot be empty.")
            return

        # If we were provided file_path and db_manager, perform in-dialog verification
        if self._db_manager is not None:
            try:
                # Prefer using DatabaseImporter.verify_password when a file_path is
                # supplied (used during import), otherwise try to verify against
                # the currently opened database using the db_manager/encryption.
                verified = False
                verify_message = ""
                if self._file_path:
                    from src.core.database.db_import import DatabaseImporter

                    importer = DatabaseImporter(self._db_manager)
                    verified, verify_message = importer.verify_password(self._file_path, password)
                else:
                    # No file_path: we're verifying the password for the current
                    # database (e.g., disabling encryption). Use the manager's
                    # EncryptionManager to attempt a decrypt/decrypt_to_temp check.
                    try:
                        # Use the encryption manager directly to validate the password
                        enc = getattr(self._db_manager, 'encryption', None)
                        if enc is None:
                            verified = False
                            verify_message = "No encryption manager available"
                        else:
                            # Attempt a quick decrypt which raises on bad password
                            enc.decrypt(password)
                            verified = True
                            verify_message = "Password verified"
                    except Exception as e:
                        verified = False
                        # Normalize message when InvalidPasswordError
                        verify_message = str(e)
            except Exception as e:
                verified = False
                verify_message = f"Verification error: {e}"

            if verified:
                self._password = password
                self.accept()
                return

            # Not verified: decrement attempts and update message
            self._attempts_left -= 1
            if self._attempts_left <= 0:
                # No attempts left: reject the dialog (abort operation)
                self._message.setText("Incorrect password. No attempts remaining. Aborted.")
                self.reject()
                return

            # Show remaining attempts with the verification message
            self._message.setText(f"{verify_message}. Attempts remaining: {self._attempts_left}")
            # Clear the password field for the next attempt
            self._password_edit.clear()
            self._password_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            return

        # If no verifier provided, just return the entered password
        self._password = password
        self.accept()

    def get_password(self) -> str:
        return self._password

    def _on_show_toggled(self, checked: bool) -> None:
        if checked:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)


class ChangeDatabasePasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Database Password")
        self.setModal(True)
        self._current: str = ""
        self._new: str = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Use the shared factory to create consistent line edits.
        # create_line_edit returns a QLineEdit when called without label/button.
        self._current_edit = create_line_edit(object_name="current_password_edit")
        self._current_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self._new_edit = create_line_edit(object_name="new_password_edit")
        self._new_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self._confirm_edit = create_line_edit(object_name="confirm_password_edit")
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Current", self._current_edit)
        form.addRow("New", self._new_edit)
        form.addRow("Confirm", self._confirm_edit)
        layout.addLayout(form)

        self._message = _error_label()
        layout.addWidget(self._message)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._current_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _validate(self):
        current = self._current_edit.text().strip()
        new = self._new_edit.text().strip()
        confirm = self._confirm_edit.text().strip()
        if not current:
            self._message.setText("Enter your current password.")
            return
        if not new:
            self._message.setText("New password cannot be empty.")
            return
        if new != confirm:
            self._message.setText("New passwords do not match.")
            return
        self._current = current
        self._new = new
        self.accept()

    def get_passwords(self) -> tuple[str, str]:
        return self._current, self._new


class PasswordInputDialog(QDialog):
    """Simple password input dialog for general use."""
    
    def __init__(self, parent=None, title: str = "Password Required", message: str = "Enter password:"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._password: str = ""
        
        layout = QVBoxLayout(self)
        
        # Message label
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)
        
        # Password input
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Enter password...")
        layout.addWidget(self._password_edit)
        
        # Show password checkbox
        self._show_checkbox = QCheckBox("Show password")
        self._show_checkbox.toggled.connect(self._on_show_toggled)
        layout.addWidget(self._show_checkbox)
        
        # Error message
        self._message = _error_label()
        layout.addWidget(self._message)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self._password_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    
    def _validate(self):
        password = self._password_edit.text().strip()
        if not password:
            self._message.setText("Password cannot be empty.")
            return
        self._password = password
        self.accept()
    
    def get_password(self) -> str:
        return self._password
    
    def _on_show_toggled(self, checked: bool) -> None:
        if checked:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)


class DeadlineDateDialog(QDialog):
    """Dialog for selecting a deadline date for batch operations."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Deadline Date")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._deadline_date = None
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Message label
        msg_label = QLabel("Select a deadline date to apply to all selected games:")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)
        
        # Date selector with label
        date_container, self._date_edit = create_date_selector(
            self, 
            label="Deadline Date:",
            visible=True, 
            enabled=True,
            calendar_popup=True
        )
        # Set default to today
        self._date_edit.setDate(QDate.currentDate())
        layout.addWidget(date_container)
        
        # Add some spacing
        layout.addSpacing(10)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self._date_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    
    def get_deadline_date(self):
        """Get the selected deadline date as QDate."""
        return self._date_edit.date()


