from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QObject


class BaseController(QObject):
    """Base class for main window controllers with common utilities."""

    def __init__(self, settings_manager, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings_manager

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Safely retrieve a setting value with a default."""
        try:
            return self._settings.get(key, default)
        except Exception:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        """Safely save a setting value."""
        try:
            self._settings.set(key, value)
        except Exception:
            pass

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Retrieve a boolean setting."""
        try:
            return self._settings.get_bool(key, default)
        except Exception:
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        """Retrieve an integer setting."""
        try:
            return self._settings.get_int(key, default)
        except Exception:
            return default
