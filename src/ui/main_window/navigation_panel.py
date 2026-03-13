from __future__ import annotations

from contextlib import suppress
from functools import partial
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from src.ui.main_window.base_controller import BaseController
from src.ui.widgets.animated_gradient_bar import AnimatedGradientBar
from src.ui.widgets.badge import BadgeManager, BadgePosition
from src.ui.widgets.main_widgets import create_push_button


class NavigationPanel(BaseController):
    """Manage the navigation panel, including badges and theme selector."""

    page_requested = Signal(str)
    theme_requested = Signal(str)

    def __init__(
        self,
        page_definitions: Sequence[Tuple[str, str, str]],
        settings_manager,
        theme_manager,
        badge_manager: BadgeManager,
        parent=None,
    ) -> None:
        super().__init__(settings_manager, parent)
        self._page_defs: List[Tuple[str, str, str]] = list(page_definitions)
        self._theme_manager = theme_manager
        self._badge_manager = badge_manager

        self.widget: Optional[QFrame] = None
        self.page_navigation_buttons: Dict[str, QWidget] = {}
        self.gradient_bar: Optional[AnimatedGradientBar] = None
        self.theme_selector_combo = None
        self.theme_selector_button = None
        self._theme_selector_layout = None
        self._current_position: Optional[str] = None
        # _user_appearance stores the user's saved preference from settings
        self._user_appearance: Optional[str] = None
        # _appearance is the currently applied (effective) appearance and may
        # be overridden when the nav bar is placed vertically (left/right).
        self._appearance: Optional[str] = None
        # Whether we forced icon-only due to a vertical position
        self._forced_icon_mode: bool = False
        self.title_label = None
        self._theme_menu = None
        self._has_update = False  # Track update badge state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, position: Optional[str] = None) -> QFrame:
        """Create (or rebuild) the navigation widget for the requested position."""
        self._cleanup()

        position = position or self.get_setting("page_navigation_bar_position", "left")
        # Keep the user's saved preference separate from the effective
        # appearance. When the bar is vertical (left/right) we force
        # icon-only mode for a consistent compact layout.
        self._user_appearance = self.get_setting("page_navigation_bar_appearance", "icon_and_text")
        self._current_position = position

        if position in ("left", "right"):
            self._appearance = "icon_only"
            self._forced_icon_mode = True
        else:
            self._appearance = self._user_appearance
            self._forced_icon_mode = False

        # Local alias used by helper methods below
        appearance = self._appearance

        frame = QFrame()
        frame.setObjectName("page_navigation_bar")
        self.widget = frame

        self.title_label = self._create_title_label(position)

        layout_cls = QVBoxLayout if position in ("left", "right") else QHBoxLayout
        layout = layout_cls(frame)
        layout.setSpacing(0)

        if position in ("left", "right"):
            layout.setContentsMargins(4, 8, 4, 8)
        else:
            layout.setContentsMargins(8, 4, 8, 4)

        #layout.addWidget(self.title_label) # Currently Disabled

        main_group = self._make_group(self._page_defs[:2], position, appearance)
        utilities_group = self._make_group(self._page_defs[2:], position, appearance)
        self._theme_selector_layout = utilities_group.layout()

        self._inject_theme_selector(position, appearance)

        layout.addWidget(main_group)
        layout.addSpacing(6)

        self.gradient_bar = self._create_gradient_bar(position)
        layout.addWidget(self.gradient_bar, 1)
        layout.addSpacing(6)

        layout.addWidget(utilities_group)

        self._apply_appearance_rules()
        return frame

    def _create_title_label(self, position: str) -> QLabel:
        """Create and configure the title label."""
        label = QLabel("SteamKM2")
        label.setObjectName("app_title")

        if position in ("left", "right"):
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        else:
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        return label

    def _create_gradient_bar(self, position: str) -> AnimatedGradientBar:
        """Create and configure the gradient bar."""
        orientation = (
            Qt.Orientation.Vertical if position in ("left", "right") else Qt.Orientation.Horizontal
        )
        bar = AnimatedGradientBar(self._theme_manager, orientation)
        self._theme_manager.theme_changed.connect(
            bar.refresh_colors, 
            Qt.ConnectionType.UniqueConnection
        )

        effect = self.get_setting("gradient_animation", "scroll")
        if effect:
            bar.set_effect(effect)

        return bar

    def update_selection(self, current_page: Optional[str]) -> None:
        """Reflect the selected page in the toggle buttons."""
        for name, button in self.page_navigation_buttons.items():
            is_current = name == current_page
            button.setChecked(is_current)
            button.setEnabled(not is_current)

    def refresh_theme_selector(self) -> None:
        """Refresh theme selector entries to reflect latest theme list."""
        # We always use a push-button now. Refresh the menu entries and update
        # the button text to reflect the current theme and appearance.
        if self.theme_selector_button is None:
            return

        menu = self._theme_menu
        if menu is not None:
            menu.clear()
            self._populate_theme_menu(menu)

        current = self._theme_manager.current_theme.get("name", "")
        appearance = self._appearance or "icon_and_text"

        if appearance == "icon_only":
            self.theme_selector_button.setText("🖌️")
            tooltip = f"Select theme (current: {current})" if current else "Select theme"
            self.theme_selector_button.setToolTip(tooltip)
        elif appearance == "text_only":
            self.theme_selector_button.setText(current or "Select theme")
            self.theme_selector_button.setToolTip("Select theme")
        else:
            # icon_and_text
            display = f"🖌️ {current}" if current else "🖌️ Select theme"
            self.theme_selector_button.setText(display)
            self.theme_selector_button.setToolTip(f"Select theme (current: {current})" if current else "Select theme")

    def refresh_gradient(self) -> None:
        """Refresh gradient bar colors."""
        if self.gradient_bar is not None:
            self.gradient_bar.refresh_colors()

    # ------------------------------------------------------------------
    # Badge management
    # ------------------------------------------------------------------
    def _get_button(self, page_name: str) -> Optional[QWidget]:
        """Get page button by name, return None if not found."""
        return self.page_navigation_buttons.get(page_name)

    def set_update_badge(self, has_update: bool) -> None:
        """Show or hide the update notification badge."""
        self._has_update = has_update  # Store state
        button = self._get_button("Update")
        if button is not None:
            self._badge_manager.set_dot_visible(button, has_update)

    def set_page_locked(self, page_name: str, locked: bool) -> None:
        """Lock/unlock a page button with lock icon. Stores/restores original text and tooltip."""
        button = self._get_button(page_name)
        if button is None:
            return
        
        if locked:
            # Store originals only once
            if not button.property("_locked"):
                button.setProperty("_original_text", button.text())
                button.setProperty("_original_tooltip", button.toolTip())
                button.setProperty("_locked", True)
            button.setEnabled(False)
            button.setText("🔒")
            button.setToolTip(f"{button.property('_original_tooltip')} (Locked - Steam fetch in progress)")
        elif button.property("_locked"):
            button.setEnabled(True)
            button.setText(button.property("_original_text") or "")
            button.setToolTip(button.property("_original_tooltip") or "")
            button.setProperty("_locked", None)

    def update_badge_count(self, page_name: str, count: int) -> None:
        """Update badge with a count value."""
        button = self._get_button(page_name)
        if button is None:
            return
        badge = self._badge_manager.get_badge(button)
        if badge is None:
            self._badge_manager.add_badge(button, count=0, position=BadgePosition.TOP_RIGHT)
        self._badge_manager.update_count(button, count)

    def set_badge_text(self, page_name: str, text: str) -> None:
        """Update badge with text value."""
        button = self._get_button(page_name)
        if button is None:
            return
        badge = self._badge_manager.get_badge(button)
        if badge is None:
            self._badge_manager.add_badge(button, text="", position=BadgePosition.TOP_RIGHT)
        self._badge_manager.update_text(button, text)

    def clear_badge(self, page_name: str) -> None:
        """Remove badge from a page button."""
        button = self._get_button(page_name)
        if button is not None:
            self._badge_manager.remove_badge(button)

    @property
    def position(self) -> Optional[str]:
        return self._current_position

    # ------------------------------------------------------------------
    # Widget creation helpers
    # ------------------------------------------------------------------
    def _cleanup(self) -> None:
        with suppress(Exception):
            if self.gradient_bar is not None:
                self._theme_manager.theme_changed.disconnect(self.gradient_bar.refresh_colors)
        if self.widget is not None:
            self.widget.deleteLater()
        self.widget = None
        self.page_navigation_buttons.clear()
        self.gradient_bar = None
        self.theme_selector_combo = None
        self.theme_selector_button = None
        self._theme_selector_layout = None
        self.title_label = None
        self._theme_menu = None

    def _make_group(
        self,
        page_defs: Sequence[Tuple[str, str, str]],
        position: str,
        appearance: str,
    ) -> QGroupBox:
        group = QGroupBox()
        group.setObjectName("page_navigation_button_groupbox")
        layout_cls = QVBoxLayout if position in ("left", "right") else QHBoxLayout
        layout = layout_cls()
        layout.setContentsMargins(5, 5, 5, 5)

        for page_name, icon, tooltip in page_defs:
            button = self._make_page_navigation_button(page_name, icon, tooltip, appearance)
            layout.addWidget(button)

        group.setLayout(layout)
        return group

    def _make_page_navigation_button(
        self,
        page_name: str,
        icon: str,
        tooltip: str,
        appearance: str,
    ):
        if appearance == "icon_only":
            label = icon
        elif appearance == "text_only":
            label = page_name
        else:
            label = f"{icon} {page_name}"

        button = create_push_button(label)
        if appearance == "icon_only":
            button.setProperty("centerText", True)
        button.setObjectName("page_navigation_button")
        button.setCheckable(True)
        button.setToolTip(tooltip)
        button.clicked.connect(partial(self.page_requested.emit, page_name))
        self.page_navigation_buttons[page_name] = button

        if page_name == "Update":
            # Create badge and set initial state from stored value
            self._badge_manager.add_badge(button, show_dot=self._has_update, position=BadgePosition.TOP_RIGHT)

        return button

    def _inject_theme_selector(self, position: str, appearance: str) -> None:
        if self._theme_selector_layout is None:
            return

        current_theme = self._theme_manager.current_theme.get("name", "Dark")

        # Always use a push button for the theme selector. We show different
        # content on the button depending on the appearance:
        # - icon_only: show paint icon only
        # - text_only: show the theme name
        # - icon_and_text: show paint icon + theme name
        button = create_push_button("")
        button.setObjectName("page_navigation_button")

        # centerText for icon-only so it matches other icon-only page buttons
        if appearance == "icon_only":
            button.setProperty("centerText", True)

        # Build the menu and attach actions for theme choices
        menu = QMenu(button)
        self._populate_theme_menu(menu)
        self._theme_menu = menu

        def _open_theme_menu(checked=False, _btn=button, _menu=menu, _pos=position):
            rect = _btn.rect()
            if _pos == "right":
                # top-left corner of button in global coords
                anchor = _btn.mapToGlobal(rect.topLeft())
                # offset by menu width to the left so it appears inside
                menu_w = _menu.sizeHint().width()
                pos = QPoint(anchor.x() - menu_w + rect.width(), anchor.y())
            else:
                # left side (default): top-right corner so menu grows rightwards
                anchor = _btn.mapToGlobal(rect.topRight())
                pos = QPoint(anchor.x(), anchor.y())
            _menu.exec(pos)

        button.clicked.connect(_open_theme_menu)

        # Set initial button text based on appearance
        if appearance == "icon_only":
            button.setText("🖌️")
            button.setToolTip(f"Select theme (current: {current_theme})")
        elif appearance == "text_only":
            button.setText(current_theme)
            button.setToolTip("Select theme")
        else:
            # icon_and_text
            button.setText(f"🖌️ {current_theme}")
            button.setToolTip(f"Select theme (current: {current_theme})")

        self._theme_selector_layout.addWidget(button)
        self.theme_selector_button = button
        self.theme_selector_combo = None

    def _populate_theme_selector(self) -> None:
        if self.theme_selector_combo is None:
            return

        combo = self.theme_selector_combo
        current_text = combo.currentText()
        combo.blockSignals(True)
        combo.clear()

        custom = list(self._theme_manager.get_custom_themes())
        built_in = list(self._theme_manager.get_built_in_themes())

        if custom:
            combo.addItems(custom)
            combo.insertSeparator(combo.count())

        combo.addItems(built_in)

        current_theme = self._theme_manager.current_theme.get("name", "Dark")
        index = combo.findText(current_theme)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif current_text:
            index = combo.findText(current_text)
            if index >= 0:
                combo.setCurrentIndex(index)

        combo.blockSignals(False)

    def _populate_theme_menu(self, menu: QMenu) -> None:
        custom = list(self._theme_manager.get_custom_themes())
        built_in = list(self._theme_manager.get_built_in_themes())

        for theme in custom:
            menu.addAction(theme, partial(self.theme_requested.emit, theme))
        if custom:
            menu.addSeparator()
        for theme in built_in:
            menu.addAction(theme, partial(self.theme_requested.emit, theme))

    def _apply_appearance_rules(self) -> None:
        if self.widget is None:
            return

        position = self._current_position or "left"
        appearance = self._appearance or "icon_and_text"

        if position in ("left", "right"):
            if appearance == "icon_only":
                bar_width = 60
                label_text = "SKM2"
            elif appearance == "text_only":
                bar_width = 105
                label_text = "SteamKM2"
            else:
                bar_width = 110
                label_text = "SteamKM2"
            self.widget.setFixedWidth(bar_width)
        else:
            label_text = "SteamKM2"

        if getattr(self, "title_label", None) is not None:
            self.title_label.setText(label_text)
            if position in ("left", "right"):
                self.title_label.setStyleSheet("margin-bottom: 5px; font-size: 16px;")
            else:
                self.title_label.setStyleSheet("margin-right: 5px; font-size: 16px;")
