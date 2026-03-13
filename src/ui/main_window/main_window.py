from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from src.ui.main_window.backup_scheduler import BackupScheduler
from src.ui.main_window.navigation_panel import NavigationPanel
from src.ui.main_window.notifications import NotificationController
from src.ui.main_window.page_controller import PageController
from src.ui.main_window.status_bar import StatusBarController
from src.ui.main_window.update_coordinator import UpdateCoordinator
from src.ui.widgets.badge import BadgeManager
from src.ui.widgets.notification_system import NotificationPosition, NotificationType
from src.ui.widgets.tooltip import get_tooltip_manager, TooltipAnimation
from src.core.health_monitor import HealthMonitor
from src.ui.dialogs.health_monitor_dialog import HealthMonitorDialog


class MainWindow(QMainWindow):
    """Top-level application window orchestrating UI sub-components."""

    def __init__(self, db_manager, theme_manager, settings_manager) -> None:
        super().__init__()

        self.db_manager = db_manager
        self.theme_manager = theme_manager
        self.settings_manager = settings_manager

        app = QApplication.instance()
        app_name = app.applicationName()
        version = app.applicationVersion()
        title = f"{app_name} V{version} - Time to big manage"
        self.setWindowTitle(title)
        self.resize(1300, 800)
        
        # Initialize global tooltip manager with settings
        self.tooltip_manager = get_tooltip_manager(theme_manager)
        self._update_tooltip_settings()

        self.page_defs: Sequence[Tuple[str, str, str]] = (
            ("Home", "🕹️", "View your game library"),
            ("Add", "➕", "Add new games to your collection"),
            ("Update", "🔄", "Check for updates"),
            ("Settings", "⚙️", "Configure application settings"),
        )

        self.badge_manager = BadgeManager(theme_manager=theme_manager)
        self.notification_controller = NotificationController(self, NotificationPosition.TOP_RIGHT)
        self.notification_manager = self.notification_controller.manager
        self.notification_controller.set_update_click_handler(lambda: self._switch_to_page("Update"))

        self.navigation_panel = NavigationPanel(
            self.page_defs,
            self.settings_manager,
            self.theme_manager,
            self.badge_manager,
        )
        self.navigation_panel.page_requested.connect(self._switch_to_page)
        self.navigation_panel.theme_requested.connect(self._on_theme_selector_changed)
        self.page_controller = PageController(db_manager, theme_manager, settings_manager, self)
        self.page_manager = self.page_controller.page_manager
        self.content_area = self.page_controller.stack

        self.status_controller = StatusBarController(self, self.settings_manager, self.go_back, self.go_forward)
        self.status_bar = self.status_controller.status_bar
        self.theme_label = self.status_controller.theme_label
        self.back_button = self.status_controller.back_button
        self.forward_button = self.status_controller.forward_button

        self.backup_scheduler = BackupScheduler(self, self.settings_manager, self.db_manager, self.status_controller.show_message)
        self._backup_timer = self.backup_scheduler.timer

        self.update_coordinator = UpdateCoordinator(self.settings_manager, self)
        self.update_manager = self.update_coordinator.manager
        self._history_back = self.page_controller._history_back
        self._history_forward = self.page_controller._history_forward

        # Initialize health monitor
        self.health_monitor = HealthMonitor(
            settings_manager=self.settings_manager,
            db_manager=self.db_manager,
            theme_manager=self.theme_manager
        )
        self.health_monitor.start()
        self.health_monitor_window: Optional[HealthMonitorDialog] = None

        central_widget = self._configure_central_layout()
        self.notification_controller.attach_to(central_widget)

        self.page_controller.page_changed.connect(self._on_page_changed)
        self.page_controller.page_created.connect(self._on_page_created)
        self.page_controller.history_changed.connect(self._on_history_changed)

        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self.theme_manager.theme_applied.connect(self._on_theme_applied)

        self._connect_signals()
        self._setup_shortcuts()

        self._switch_to_page("Home", record_history=False)
        self.status_controller.update_theme_label(self.theme_manager.current_theme.get("name", "Unknown"))

        self.backup_scheduler.start()
        self.update_coordinator.update_available.connect(self._handle_update_available)
        self.update_coordinator.no_update.connect(lambda: self.set_update_notification(False))
        self.update_coordinator.update_error.connect(lambda _msg: None)
        self.update_coordinator.start()
        
        # Install event filter globally to catch all tooltip events
        QApplication.instance().installEventFilter(self)

        # If relaunched by the updater, show a success toast and bring the
        # window forward once the event loop starts.
        if os.environ.pop("SKM2_POST_UPDATE", ""):
            QTimer.singleShot(0, self._handle_post_update_launch)

    def _handle_post_update_launch(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

        # Simple force-focus for Windows using standard library
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.SwitchToThisWindow(int(self.winId()), True)

        try:
            self.notification_controller.show_success("Update installed successfully", duration=6000)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _configure_central_layout(self) -> QWidget:
        """Configure the central widget and main layout."""
        central = QWidget()
        self.setCentralWidget(central)

        pos = self.settings_manager.get("page_navigation_bar_position", "left")
        self.page_navigation_bar = self.navigation_panel.build(pos)
        self._sync_navigation_widgets()
        self._apply_main_layout(central, pos)
        return central

    def _sync_navigation_widgets(self) -> None:
        """Synchronize references to navigation panel widgets."""
        self.page_navigation_buttons = self.navigation_panel.page_navigation_buttons
        self.gradient_bar = self.navigation_panel.gradient_bar
        self.theme_selector_combo = self.navigation_panel.theme_selector_combo
        self.theme_selector_button = self.navigation_panel.theme_selector_button

    def _apply_main_layout(self, central: QWidget, pos: str) -> None:
        existing_layout = central.layout()
        if existing_layout is not None:
            while existing_layout.count():
                item = existing_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
            QWidget().setLayout(existing_layout)

        layout_cls = QHBoxLayout if pos in ("left", "right") else QVBoxLayout
        layout = layout_cls(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if pos in ("left", "top"):
            layout.addWidget(self.page_navigation_bar, 0)
            layout.addWidget(self.content_area, 1)
        else:
            layout.addWidget(self.content_area, 1)
            layout.addWidget(self.page_navigation_bar, 0)

        self.main_layout = layout

    # ------------------------------------------------------------------
    # Navigation / page handling
    # ------------------------------------------------------------------
    def _switch_to_page(self, page_name: str, *, record_history: bool = True) -> Optional[QWidget]:
        return self.page_controller.switch_to(page_name, record_history=record_history)

    def go_back(self) -> None:
        self.page_controller.go_back()

    def go_forward(self) -> None:
        self.page_controller.go_forward()

    def _on_page_changed(self, page_name: str, widget) -> None:
        """Handle page change events."""
        self.navigation_panel.update_selection(page_name)
        self._sync_navigation_widgets()
        self.navigation_panel.refresh_gradient()
        self._update_status_bar()
        if page_name == "Update":
            self.notification_controller.clear_update_notification()

    def _on_history_changed(self, can_go_back: bool, can_go_forward: bool) -> None:
        """Update navigation button states based on history."""
        self.status_controller.update_navigation(can_go_back, can_go_forward)

    def _ensure_and_call(self, page_name: str, method: str, *args, **kwargs):
        """Ensure page exists and call a method on it."""
        return self.page_controller.ensure_and_call(page_name, method, *args, **kwargs)

    # ------------------------------------------------------------------
    # Settings-driven layout changes
    # ------------------------------------------------------------------
    def _on_page_navigation_bar_position_changed(self, pos: str) -> None:
        """Rebuild navigation panel when position changes."""
        self.page_navigation_bar = self.navigation_panel.build(pos)
        self._sync_navigation_widgets()
        self._apply_main_layout(self.centralWidget(), pos)
        if self.page_controller.current_page_name:
            self.navigation_panel.update_selection(self.page_controller.current_page_name)

    def _on_page_navigation_bar_appearance_changed(self, _appearance: str) -> None:
        pos = self.settings_manager.get("page_navigation_bar_position", "left")
        self._on_page_navigation_bar_position_changed(pos)

    # ------------------------------------------------------------------
    # Status bar / notifications
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Status bar / notifications
    # ------------------------------------------------------------------
    def _update_status_bar(self) -> None:
        """Update status bar with current theme and status."""
        current_theme = self.theme_manager.current_theme.get("name", "Unknown")
        self.status_controller.update_theme_label(current_theme)
        self.status_controller.show_message("Ready", 2000)

    # Notification convenience methods - delegate to notification controller
    def show_notification(
        self,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        duration: int = 4000,
        closable: bool = True,
    ):
        """Show a notification with specified type and duration."""
        return self.notification_controller.show_notification(message, notification_type, duration, closable)

    def show_success(self, message: str, duration: int = 4000):
        """Show a success notification."""
        return self.notification_controller.show_success(message, duration)

    def show_error(self, message: str, duration: int = 6000):
        """Show an error notification."""
        return self.notification_controller.show_error(message, duration)

    def show_warning(self, message: str, duration: int = 5000):
        """Show a warning notification."""
        return self.notification_controller.show_warning(message, duration)

    def show_info(self, message: str, duration: int = 4000):
        """Show an info notification."""
        return self.notification_controller.show_info(message, duration)

    def show_update_notification(self, message: str, duration: int = 0):
        """Show an update notification (persistent by default)."""
        return self.notification_controller.show_update_notification(message, duration)

    def show_download_notification(self, message: str = "Downloading update..."):
        """Show a download progress notification."""
        return self.notification_controller.show_download(message)

    def clear_all_notifications(self) -> None:
        """Clear all active notifications."""
        self.notification_controller.clear_all()

    # Badge management - delegate to navigation panel
    def set_update_notification(self, has_update: bool) -> None:
        """Show/hide update badge on Update page button."""
        self.navigation_panel.set_update_badge(has_update)

    def update_page_badge_count(self, page_name: str, count: int) -> None:
        """Update page button badge with count."""
        self.navigation_panel.update_badge_count(page_name, count)

    def set_page_badge_text(self, page_name: str, text: str) -> None:
        """Update page button badge with text."""
        self.navigation_panel.set_badge_text(page_name, text)

    def clear_page_badge(self, page_name: str) -> None:
        """Clear badge from page button."""
        self.navigation_panel.clear_badge(page_name)

    def set_page_locked(self, page_name: str, locked: bool) -> None:
        """Lock or unlock a page button (e.g., during Steam fetch operations)."""
        self.navigation_panel.set_page_locked(page_name, locked)

    # ------------------------------------------------------------------
    # Property delegation for cleaner API
    # ------------------------------------------------------------------
    @property
    def current_page_name(self) -> Optional[str]:
        """Get current page name from page controller."""
        return self.page_controller.current_page_name

    @current_page_name.setter
    def current_page_name(self, value: Optional[str]) -> None:
        """Set current page name in page controller."""
        self.page_controller.current_page_name = value

    @property
    def can_go_back(self) -> bool:
        """Check if backward navigation is possible."""
        return self.page_controller.can_go_back

    @property
    def can_go_forward(self) -> bool:
        """Check if forward navigation is possible."""
        return self.page_controller.can_go_forward

    @property
    def _active_update_notification(self):
        """Get active update notification widget."""
        return self.notification_controller._active_update_notification

    @_active_update_notification.setter
    def _active_update_notification(self, value) -> None:
        """Set active update notification widget."""
        self.notification_controller._active_update_notification = value

    # ------------------------------------------------------------------
    # Theme handling
    # ------------------------------------------------------------------
    def _on_theme_changed(self) -> None:
        app = QApplication.instance()
        self.theme_manager.apply_theme(app)
        self.navigation_panel.refresh_theme_selector()
        self.navigation_panel.refresh_gradient()
        self._update_status_bar()

    def _on_theme_selector_changed(self, theme_name: str) -> None:
        self.theme_manager.set_theme(theme_name)
        self.navigation_panel.refresh_theme_selector()

    def _on_theme_applied(self, duration_ms: float) -> None:
        self.status_controller.update_theme_timer(duration_ms)

    # ------------------------------------------------------------------
    # Notifications from update manager
    # ------------------------------------------------------------------
    def _handle_update_available(self, info) -> None:
        version = info.get("version", "") if isinstance(info, dict) else ""
        self.set_update_notification(True)
        # Don't show popup notification if user is already on the Update page
        if self.current_page_name == "Update":
            return
        message = f"Update v{version} is available".strip()
        self.notification_controller.show_update_notification(message, duration=5000)

    # ------------------------------------------------------------------
    # Backup scheduling convenience methods
    # ------------------------------------------------------------------
    def restart_backup_timer(self) -> None:
        """Restart the backup timer with current settings."""
        self.backup_scheduler.restart()

    def _start_backup_timer(self) -> None:
        """Start the backup timer."""
        self.backup_scheduler.start()

    def _perform_auto_backup(self) -> None:
        """Execute backup immediately."""
        self.backup_scheduler.run_now()

    # ------------------------------------------------------------------
    # Signal wiring and shortcuts
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        """Connect signals between pages and main window."""
        self._pending_connects: Dict[str, List] = {}

        def wire_common(page_obj) -> None:
            """Wire common signals for any page."""
            if hasattr(page_obj, "status_message"):
                page_obj.status_message.connect(self.status_bar.showMessage)
            if hasattr(page_obj, "theme_changed"):
                page_obj.theme_changed.connect(self._on_theme_changed)
            if hasattr(page_obj, "page_navigation_bar_position_changed"):
                page_obj.page_navigation_bar_position_changed.connect(self._on_page_navigation_bar_position_changed)
            if hasattr(page_obj, "page_navigation_bar_appearance_changed"):
                page_obj.page_navigation_bar_appearance_changed.connect(self._on_page_navigation_bar_appearance_changed)
            if hasattr(page_obj, "status_bar_visibility_changed"):
                page_obj.status_bar_visibility_changed.connect(self.status_bar.setVisible)
            # Connect Steam fetch signals to lock/unlock Add page button
            if hasattr(page_obj, "steam_fetch_started"):
                page_obj.steam_fetch_started.connect(lambda: self.set_page_locked("Add", True))
            if hasattr(page_obj, "steam_fetch_finished"):
                page_obj.steam_fetch_finished.connect(lambda: self.set_page_locked("Add", False))

        self._wire_common = wire_common

        for name, instance in list(self.page_manager._instances.items()):
            if instance:
                wire_common(instance)

        def connect_add_to_home(add_page):
            if hasattr(add_page, "game_added"):
                add_page.game_added.connect(
                    lambda ids=None: (
                        self._ensure_and_call("Home", "add_games_by_ids", ids or []),
						self._ensure_and_call("Home", "refresh", True) if not ids else None,
                    )
                )

        def connect_settings_to_home(settings_page):
            if hasattr(settings_page, "tags_updated"):
                settings_page.tags_updated.connect(
                    lambda: (
                        self._ensure_and_call("Home", "reload_tags"),
                        self._ensure_and_call("Home", "refresh", True),
                    )
                )
            try:
                if hasattr(settings_page, "auto_update_toggle"):
                    settings_page.auto_update_toggle.toggled.connect(self.update_coordinator.set_enabled)
            except Exception:
                pass

            if hasattr(settings_page, "encryption_status_changed"):
                def _handle_encryption_change(enabled: bool) -> None:
                    self._ensure_and_call("Home", "on_encryption_status_changed", enabled)
                    self._ensure_and_call("Add", "on_encryption_status_changed", enabled)

                settings_page.encryption_status_changed.connect(_handle_encryption_change)
            
            # Connect tooltip settings changes
            if hasattr(settings_page, "tooltip_animation_combo"):
                settings_page.tooltip_animation_combo.currentTextChanged.connect(lambda _: self._update_tooltip_settings())
            if hasattr(settings_page, "tooltip_show_delay_spinbox"):
                settings_page.tooltip_show_delay_spinbox.valueChanged.connect(lambda _: self._update_tooltip_settings())

        def connect_update_page(update_page):
            if hasattr(update_page, "update_available"):
                update_page.update_available.connect(self.set_update_notification)

            try:
                self.update_coordinator.update_available.connect(
                    lambda info: getattr(update_page, "_on_update_found", lambda *_: None)(info, True)
                )
                self.update_coordinator.no_update.connect(
                    lambda: getattr(update_page, "_on_no_update", lambda *_: None)(True)
                )
                self.update_coordinator.update_error.connect(
                    lambda msg: getattr(update_page, "_on_update_error", lambda *_: None)(msg, True)
                )
            except Exception:
                pass

        self._queue_or_connect("Add", connect_add_to_home)
        self._queue_or_connect("Settings", connect_settings_to_home)
        self._queue_or_connect("Update", connect_update_page)

    def _queue_or_connect(self, page_name: str, fn) -> None:
        instance = self.page_manager.get_instance(page_name)
        if instance is not None:
            try:
                fn(instance)
            except Exception:
                pass
        else:
            self._pending_connects.setdefault(page_name, []).append(fn)

    def _on_page_created(self, name: str, widget) -> None:
        try:
            if hasattr(self, "_wire_common"):
                self._wire_common(widget)
        except Exception:
            pass
        for fn in self._pending_connects.pop(name, []):
            try:
                fn(widget)
            except Exception:
                pass

    def _setup_shortcuts(self) -> None:
        try:
            self._sc_back = QShortcut(QKeySequence("Alt+Left"), self)
            self._sc_back.activated.connect(self.go_back)
            self._sc_forward = QShortcut(QKeySequence("Alt+Right"), self)
            self._sc_forward.activated.connect(self.go_forward)
            self._sc_help = QShortcut(QKeySequence("F1"), self)
            self._sc_help.activated.connect(self._show_shortcuts_help)
            self._sc_health = QShortcut(QKeySequence("F12"), self)
            self._sc_health.activated.connect(self.toggle_health_monitor)
        except Exception:
            pass

        try:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        """Combined global event filter.

        Handles:
          - Mouse back/forward XButton presses to trigger navigation.
          - Tooltip events: suppress default Qt tooltips and use custom tooltip manager.
        """
        try:
            # Mouse back/forward buttons (often XButton1 / XButton2 on mice)
            if event.type() == QEvent.Type.MouseButtonPress:
                button = getattr(event, "button", lambda: None)()
                if button == Qt.MouseButton.XButton1:
                    self.go_back()
                    return True
                if button == Qt.MouseButton.XButton2:
                    self.go_forward()
                    return True

            # Tooltip handling (suppress Qt's built-in tooltip and show custom tooltip)
            if event.type() == QEvent.Type.ToolTip:
                # Suppress Qt's built-in tooltip
                return True
            elif event.type() == QEvent.Type.Enter:
                # Show custom tooltip when entering widget with tooltip
                tooltip_text = obj.toolTip() if hasattr(obj, "toolTip") else None
                if tooltip_text and isinstance(obj, QWidget):
                    self.tooltip_manager.show_tooltip(tooltip_text, obj)
            elif event.type() == QEvent.Type.Leave:
                # Hide tooltip when leaving widget
                self.tooltip_manager.hide_tooltip()
        except Exception:
            # Swallow errors to avoid breaking global event filtering
            pass

        return super().eventFilter(obj, event)

    def _show_shortcuts_help(self) -> None:
        """Show a persistent notification listing available keyboard shortcuts."""
        try:
            # Build a concise, user-friendly list of known shortcuts.
            lines = [
                "Keyboard Shortcuts:",
                "F1 — Show this help",
                "F12 — Toggle Health Monitor",
                "Delete — Delete selected game cards",
                "Ctrl+C — Copy selected game card keys",
                "Ctrl+Enter — Create entries from Batch (Add page)",
                "Alt+Left — Navigate Back",
                "Alt+Right — Navigate Forward",
                "Mouse Back/Forward buttons — Navigate Back/Forward",
            ]
            message = "\n".join(lines)
            # duration=0 makes the notification persistent until closed; closable=True shows a close button
            self.notification_controller.show_notification(message, NotificationType.INFO, duration=0, closable=True)
        except Exception:
            # Fallback: show simple message box if notification system fails
            try:
                QMessageBox.information(self, "Keyboard Shortcuts", "\n".join(lines))
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.notification_controller.handle_resize()

    def closeEvent(self, event):
        # Stop health monitor
        if hasattr(self, 'health_monitor'):
            self.health_monitor.stop()
        
        # Close health monitor window if open
        if hasattr(self, 'health_monitor_window') and self.health_monitor_window:
            self.health_monitor_window.close()
            self.health_monitor_window = None
        
        if self.db_manager:
            self.db_manager.close()
        self.backup_scheduler.stop()
        event.accept()
    
    # NOTE: eventFilter was consolidated above to ensure mouse navigation and
    # tooltip suppression both work. Leave this note in place to explain why
    # there is only a single eventFilter implementation.
    
    def toggle_health_monitor(self):
        """Toggle the health monitor window visibility"""
        # Check if window exists and is visible
        if self.health_monitor_window and self.health_monitor_window.isVisible():
            # Hide the window
            self.health_monitor_window.close()
            # Note: closeEvent will set health_monitor_window to None
        else:
            # Create a new window
            self.health_monitor_window = HealthMonitorDialog(self.health_monitor, self)
            self.health_monitor_window.show()
            self.health_monitor_window.raise_()
            self.health_monitor_window.activateWindow()
    
    def _update_tooltip_settings(self):
        """Update tooltip manager with current settings"""
        # Animation type
        anim_text = self.settings_manager.get('tooltip_animation', 'Fade')
        if anim_text == 'Fade':
            self.tooltip_manager.set_animation_type(TooltipAnimation.FADE)
        else:
            self.tooltip_manager.set_animation_type(TooltipAnimation.SLIDE)
        
        # Show delay
        show_delay = self.settings_manager.get_int('tooltip_show_delay', 500)
        self.tooltip_manager.set_show_delay(show_delay)

    # ------------------------------------------------------------------
    # Dialog helpers
    # ------------------------------------------------------------------
    def show_error_message(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    def show_info_message(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def show_warning_message(self, title: str, message: str):
        QMessageBox.warning(self, title, message)
