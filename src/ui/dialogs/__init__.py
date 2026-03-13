# Dialogs module initialization

from .game_details_dialog import GameDetailsDialog
from .backup_export_dialog import BackupExportDialog
from .import_dialog import ImportDialog
from .password_dialogs import (
    SetDatabasePasswordDialog,
    VerifyDatabasePasswordDialog,
    ChangeDatabasePasswordDialog,
    PasswordInputDialog
)
from .health_monitor_dialog import HealthMonitorDialog
from .duplicate_resolution_dialog import DuplicateResolutionDialog

__all__ = [
    'GameDetailsDialog',
    'BackupExportDialog',
    'ImportDialog',
    'SetDatabasePasswordDialog',
    'VerifyDatabasePasswordDialog',
    'ChangeDatabasePasswordDialog',
    'PasswordInputDialog',
    'HealthMonitorDialog',
    'DuplicateResolutionDialog',
]

