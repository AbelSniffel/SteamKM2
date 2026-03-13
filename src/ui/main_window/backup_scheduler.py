from __future__ import annotations

from PySide6.QtCore import QTimer

from src.ui.main_window.base_controller import BaseController


class BackupScheduler(BaseController):
    """Manage automatic database backups based on user settings."""

    def __init__(self, parent, settings_manager, db_manager, status_callback) -> None:
        super().__init__(settings_manager, parent)
        self._db_manager = db_manager
        self._status_callback = status_callback

        self.timer = QTimer(parent)
        self.timer.timeout.connect(self._perform_backup)

    def start(self) -> None:
        interval_minutes = self.get_int("auto_backup_interval_minutes", 1440)
        enabled = self.get_bool("auto_backup_enabled", True)

        if enabled and interval_minutes > 0:
            self.timer.start(interval_minutes * 60 * 1000)
        else:
            self.timer.stop()

    def restart(self) -> None:
        self.timer.stop()
        self.start()

    def stop(self) -> None:
        self.timer.stop()

    def run_now(self) -> None:
        self._perform_backup()

    def _perform_backup(self) -> None:
        try:
            if self._db_manager.requires_password():
                return
            success, _path, message = self._db_manager.create_backup("auto")
            if success:
                self._status_callback(f"Automatic backup created: {message}", 3000)
            else:
                print(f"Auto-backup failed: {message}")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Auto-backup error: {exc}")
