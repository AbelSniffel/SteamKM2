from __future__ import annotations

from PySide6.QtCore import Signal

from src.core.update_manager import UpdateManager
from src.ui.main_window.base_controller import BaseController


class UpdateCoordinator(BaseController):
    """Wrapper around UpdateManager to expose signals safely."""

    update_available = Signal(object)
    no_update = Signal()
    update_error = Signal(str)

    def __init__(self, settings_manager, parent=None) -> None:
        super().__init__(settings_manager, parent)
        self.manager = UpdateManager(settings_manager, parent)
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect internal manager signals to coordinator signals."""
        try:
            self.manager.update_available.connect(self._on_manager_update_available)
            self.manager.no_update.connect(self._on_manager_no_update)
            self.manager.update_error.connect(self._on_manager_update_error)
        except Exception:
            pass

    def start(self) -> None:
        """Start the update manager."""
        self.manager.start()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic update checks."""
        self.manager.set_enabled(enabled)

    # ------------------------------------------------------------------
    # Internal signal forwarders
    # ------------------------------------------------------------------
    def _on_manager_update_available(self, info) -> None:
        """Forward update-available events from the manager."""
        self.update_available.emit(info)

    def _on_manager_no_update(self) -> None:
        """Forward no-update events from the manager."""
        self.no_update.emit()

    def _on_manager_update_error(self, message: str) -> None:
        """Forward update-error events from the manager."""
        self.update_error.emit(message)

    # ------------------------------------------------------------------
    # Developer helpers
    # ------------------------------------------------------------------
    def trigger_test_update(self, info=None) -> None:
        """Proxy the manager test-update helper so signals stay consistent."""
        self.manager.trigger_test_update(info)
