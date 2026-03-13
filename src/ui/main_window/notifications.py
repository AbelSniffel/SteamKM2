from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import QWidget

from src.ui.widgets.notification_system import (
    NotificationManager,
    NotificationPosition,
    NotificationType,
    DownloadNotificationWidget,
)


class NotificationController:
    """Wrap the notification manager with higher-level helpers."""

    def __init__(
        self,
        parent_window,
        position: NotificationPosition = NotificationPosition.TOP_RIGHT,
    ) -> None:
        self.manager = NotificationManager(parent_window, position)
        self._active_update_notification = None
        self._update_click_handler = None

    def set_update_click_handler(self, callback) -> None:
        """Register a callback triggered when an update notification is clicked."""
        self._update_click_handler = callback
        widget = self._active_update_notification
        if widget is not None and hasattr(widget, "clicked"):
            try:
                widget.clicked.disconnect()
            except Exception:
                pass
            widget.clicked.connect(callback)

    def attach_to(self, widget: QWidget) -> None:
        self.manager.setParent(widget)
        self.manager.move(0, 0)
        self.manager.show()

    def handle_resize(self) -> None:
        self.manager.handle_parent_resize()

    def clear_all(self) -> None:
        self.manager.clear_all()

    def show_notification(
        self,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        duration: int = 4000,
        closable: bool = True,
    ):
        return self.manager.show_notification(message, notification_type, duration, closable)

    def show_success(self, message: str, duration: int = 4000):
        return self.manager.show_success(message, duration)

    def show_error(self, message: str, duration: int = 6000):
        return self.manager.show_error(message, duration)

    def show_warning(self, message: str, duration: int = 5000):
        return self.manager.show_warning(message, duration)

    def show_info(self, message: str, duration: int = 4000):
        return self.manager.show_info(message, duration)

    def show_update_notification(self, message: str, duration: int = 0):
        if self._active_update_notification is not None:
            return self._active_update_notification
        widget = self.manager.show_update(message, duration)
        self._active_update_notification = widget
        try:
            widget.closed.connect(lambda: setattr(self, "_active_update_notification", None))
            if hasattr(widget, "clicked") and self._update_click_handler is not None:
                widget.clicked.connect(self._update_click_handler)
        except Exception:
            pass
        return widget

    def clear_update_notification(self) -> None:
        widget = self._active_update_notification
        if widget is not None:
            try:
                widget.close_notification()
            except Exception:
                pass
            self._active_update_notification = None

    def show_download(self, message: str = "Downloading update...") -> DownloadNotificationWidget:
        """Show a download progress notification.
        
        Returns the DownloadNotificationWidget for progress updates.
        """
        return self.manager.show_download(message)
    
    def get_download_notification(self) -> Optional[DownloadNotificationWidget]:
        """Get the active download notification if one exists."""
        return self.manager.get_download_notification()
