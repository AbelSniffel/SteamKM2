from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget

from src.ui.main_window.base_controller import BaseController
from src.ui.page_manager import PageManager
from src.ui.pages.add_games_page import AddGamesPage
from src.ui.pages.home_page import HomePage
from src.ui.pages.settings_page import SettingsPage
from src.ui.pages.update_page import UpdatePage


class PageController(BaseController):
    """Handle lazy page instantiation, switching, and navigation history."""

    page_created = Signal(str, object)
    page_changed = Signal(str, QWidget)
    history_changed = Signal(bool, bool)

    def __init__(self, db_manager, theme_manager, settings_manager, parent=None) -> None:
        super().__init__(settings_manager, parent)
        self.stack = QStackedWidget()
        self.page_manager = PageManager(self.stack)
        self.page_manager.page_created.connect(self.page_created)

        self._db_manager = db_manager
        self._theme_manager = theme_manager
        self._settings_manager = settings_manager

        self.current_page_name: Optional[str] = None
        self._history_back: List[str] = []
        self._history_forward: List[str] = []
        self._anim_in: Optional[QPropertyAnimation] = None
        self._anim_out: Optional[QPropertyAnimation] = None

        self._register_pages()
        self._prewarm_home()

    # ------------------------------------------------------------------
    def _register_pages(self) -> None:
        self.page_manager.register(
            "Home",
            lambda: HomePage(self._db_manager, self._theme_manager, self._settings_manager),
        )
        self.page_manager.register(
            "Add",
            lambda: AddGamesPage(self._db_manager, self._theme_manager, self._settings_manager),
        )
        self.page_manager.register(
            "Settings",
            lambda: SettingsPage(self._db_manager, self._theme_manager, self._settings_manager),
        )
        self.page_manager.register(
            "Update",
            lambda: UpdatePage(self._db_manager, self._theme_manager, self._settings_manager),
        )

    def _prewarm_home(self) -> None:
        try:
            self.page_manager.prewarm("Home")
            home = self.page_manager.get_instance("Home")
            if home and hasattr(home, "on_show"):
                try:
                    home.on_show()
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    def ensure_page(self, name: str) -> QWidget:
        return self.page_manager.ensure_page(name)

    def ensure_and_call(self, page_name: str, method: str, *args, **kwargs):
        try:
            page = self.ensure_page(page_name)
        except Exception:
            return None
        if hasattr(page, method):
            try:
                return getattr(page, method)(*args, **kwargs)
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    def switch_to(self, page_name: str, *, record_history: bool = True) -> Optional[QWidget]:
        try:
            new_page = self.ensure_page(page_name)
        except KeyError:
            return None

        old_page = self.stack.currentWidget()
        if self.current_page_name is None:
            self.current_page_name = page_name
            self.stack.setCurrentWidget(new_page)
            self._emit_history()
            self._refresh_page(new_page, page_name)
            self.page_changed.emit(page_name, new_page)
            return new_page

        if old_page is new_page:
            return new_page

        if record_history and self.current_page_name:
            if not self._history_back or self._history_back[-1] != self.current_page_name:
                self._history_back.append(self.current_page_name)
            self._history_forward.clear()

        self.current_page_name = page_name
        if old_page is None:
            self._complete_switch(new_page, page_name)
        else:
            self._fade_between(old_page, new_page, page_name)

        return new_page

    def _fade_between(self, old_page: QWidget, new_page: QWidget, page_name: str) -> None:
        """Fade out old page then switch to new page."""
        effect = QGraphicsOpacityEffect(old_page)
        old_page.setGraphicsEffect(effect)

        anim_out = self._create_fade_animation(effect, 1.0, 0.0, 50)
        anim_out.finished.connect(
            lambda: (old_page.setGraphicsEffect(None), self._complete_switch(new_page, page_name))
        )
        anim_out.start()
        self._anim_out = anim_out

    def _complete_switch(self, new_page: QWidget, page_name: str) -> None:
        """Complete page switch with fade-in animation."""
        self.stack.setCurrentWidget(new_page)
        effect = QGraphicsOpacityEffect(new_page)
        new_page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        anim_in = self._create_fade_animation(effect, 0.0, 1.0, 350)
        anim_in.finished.connect(lambda: new_page.setGraphicsEffect(None))
        anim_in.start()
        self._anim_in = anim_in

        self._emit_history()
        self._refresh_page(new_page, page_name)
        self.page_changed.emit(page_name, new_page)

    def _create_fade_animation(
        self, effect: QGraphicsOpacityEffect, start: float, end: float, duration: int
    ) -> QPropertyAnimation:
        """Create a fade animation with given parameters."""
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        return anim

    def _refresh_page(self, page: QWidget, page_name: str) -> None:
        if page_name != "Home" and hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Navigation history
    # ------------------------------------------------------------------
    def go_back(self) -> None:
        """Navigate to previous page in history."""
        if not self._history_back:
            return
        self._navigate_history(self._history_back, self._history_forward)

    def go_forward(self) -> None:
        """Navigate to next page in history."""
        if not self._history_forward:
            return
        self._navigate_history(self._history_forward, self._history_back)

    def _navigate_history(self, source: List[str], dest: List[str]) -> None:
        """Navigate between pages using history stacks."""
        target = source.pop()
        if self.current_page_name:
            dest.append(self.current_page_name)
        self.switch_to(target, record_history=False)
        self._emit_history()

    def clear_history(self) -> None:
        self._history_back.clear()
        self._history_forward.clear()
        self._emit_history()

    def _emit_history(self) -> None:
        self.history_changed.emit(bool(self._history_back), bool(self._history_forward))

    # ------------------------------------------------------------------
    @property
    def can_go_back(self) -> bool:
        return bool(self._history_back)

    @property
    def can_go_forward(self) -> bool:
        return bool(self._history_forward)
