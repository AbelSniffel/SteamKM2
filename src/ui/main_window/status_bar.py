from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QLabel, QStatusBar, QToolButton

from src.ui.main_window.base_controller import BaseController


class StatusBarController(BaseController):
    """Encapsulate status bar widgets and navigation controls."""

    def __init__(
        self,
        window,
        settings_manager,
        back_callback: Callable[[], None],
        forward_callback: Callable[[], None],
    ) -> None:
        super().__init__(settings_manager, window)
        
        self.status_bar = QStatusBar()
        window.setStatusBar(self.status_bar)

        self.theme_label = QLabel()
        self.status_bar.addPermanentWidget(self.theme_label)

        self.theme_timer_label = QLabel()
        self.status_bar.addPermanentWidget(self.theme_timer_label)
        self.update_theme_timer(None)

        self.back_button = self._create_nav_button("<", "Back", back_callback)
        self.forward_button = self._create_nav_button(">", "Forward", forward_callback)
        self.status_bar.addPermanentWidget(self.back_button)
        self.status_bar.addPermanentWidget(self.forward_button)

        self._initialize_state()

    def _initialize_state(self) -> None:
        """Initialize the status bar state."""
        self.status_bar.setVisible(self.get_bool("show_status_bar", True))
        self.show_message("Ready", 2000)
        self.update_navigation(False, False)

    def _create_nav_button(
        self, text: str, tooltip: str, callback: Callable[[], None]
    ) -> QToolButton:
        """Create a navigation button with consistent settings."""
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setEnabled(False)
        button.clicked.connect(callback)
        return button
    def update_theme_label(self, theme_name: str) -> None:
        self.theme_label.setText(f"Theme: {theme_name}")

    def update_theme_timer(self, duration_ms: Optional[float]) -> None:
        if duration_ms is None:
            text = "Theme change: --"
        elif duration_ms >= 1000.0:
            text = f"Theme change: {duration_ms / 1000.0:.2f} s"
        else:
            text = f"Theme change: {duration_ms:.0f} ms"
        self.theme_timer_label.setText(text)

    def update_navigation(self, can_go_back: bool, can_go_forward: bool) -> None:
        self.back_button.setEnabled(can_go_back)
        self.forward_button.setEnabled(can_go_forward)

    def show_message(self, message: str, timeout: int = 2000) -> None:
        self.status_bar.showMessage(message, timeout)
