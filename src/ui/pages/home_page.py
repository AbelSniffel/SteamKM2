"""Home page for SteamKM2 - Displays the game library with filtering and search capabilities."""

import webbrowser
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QMessageBox,
    QMenu, QApplication, QAbstractItemView, QStackedWidget,
    QLineEdit, QWidget, QSizePolicy, QFrame
)

from PySide6.QtCore import Qt, Signal, QTimer, Slot, QSize, QDate, QPropertyAnimation, QEasingCurve, QThread, QEvent

# Custom QListView that toggles selection on click: clicking a selected item clears it
from PySide6.QtWidgets import QListView
from PySide6.QtCore import QPoint, QModelIndex
from PySide6.QtCore import QItemSelectionModel

from src.ui.widgets.selection_drag_overlay import SelectionDragOverlay
from src.ui.widgets.selection_count_notification import SelectionCountNotification

class ToggleDeselectListView(QListView):
    """QListView subclass which deselects an already-selected item when clicked.
    Behavior:
    - Left click on an item with no modifier keys will toggle the item's selection.
    - If the clicked item is currently selected and no modifiers are held, the selection
      will be cleared for that item (and selection() will be cleared if it was the only one).
    - Other click behaviors (with Ctrl/Shift) are left to the default implementation.
    """
    def __init__(self, theme_manager=None, parent=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._drag_start_pos: QPoint | None = None
        self._drag_active = False
        self._drag_threshold = 6
        self._drag_overlay = SelectionDragOverlay(self, theme_manager=self._theme_manager)
        # Parent the counter to the scroll-area itself (NOT the viewport) so it doesn't
        # get scrolled/blitted with the viewport contents.
        self._selection_counter = SelectionCountNotification(self, theme_manager=self._theme_manager)
        self._selection_counter.reposition(self.viewport().geometry())
        self._drag_overlay.reposition(self.viewport().geometry())

        try:
            self.verticalScrollBar().valueChanged.connect(self._on_scrolled)
            self.horizontalScrollBar().valueChanged.connect(self._on_scrolled)
        except Exception:
            pass

    def _on_scrolled(self, *args):
        try:
            if self._selection_counter:
                self._selection_counter.reposition(self.viewport().geometry())
            if self._drag_overlay:
                self._drag_overlay.reposition(self.viewport().geometry())
            # If the user scrolls while dragging, keep the bubble pinned to the cursor.
            if self._drag_active and self._drag_overlay and self._drag_overlay.is_drag_active():
                from PySide6.QtGui import QCursor
                pos = self._drag_overlay.mapFromGlobal(QCursor.pos())
                self._drag_overlay.step_drag(pos)
        except Exception:
            pass

    def setModel(self, model):
        super().setModel(model)
        try:
            sel = self.selectionModel()
            if sel:
                sel.selectionChanged.connect(self._on_selection_changed)
                self._on_selection_changed()
        except Exception:
            pass

    def _on_selection_changed(self, *args):
        try:
            if self._selection_counter:
                self._selection_counter.set_count(self._selected_count())
        except Exception:
            pass

    def viewportEvent(self, event):
        # Keep the overlay synced to viewport size.
        try:
            if event.type() == QEvent.Type.Resize and self._drag_overlay:
                self._drag_overlay.reposition(self.viewport().geometry())
            if event.type() == QEvent.Type.Resize and self._selection_counter:
                self._selection_counter.reposition(self.viewport().geometry())
        except Exception:
            pass
        return super().viewportEvent(event)

    def _selected_count(self) -> int:
        try:
            sel = self.selectionModel()
            if not sel:
                return 0
            rows = sel.selectedRows()
            if rows:
                return len(rows)
            # Fallback: count unique rows from selected indexes.
            return len({idx.row() for idx in sel.selectedIndexes()})
        except Exception:
            return 0

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                # position() returns QPointF in Qt6; convert if needed
                if not isinstance(pos, QPoint):
                    pos = QPoint(int(pos.x()), int(pos.y()))
                idx = self.indexAt(pos)
                # Prime drag tracking when starting on a valid game card (works with Ctrl/Shift too)
                self._drag_start_pos = pos if idx.isValid() else None
                self._drag_active = False
                
                # Handle plain left-clicks (no Ctrl/Shift/Meta modifiers) with special selection logic
                if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier | Qt.MetaModifier)):
                    if idx.isValid():
                        sel = self.selectionModel()
                        selected_indexes = sel.selectedIndexes()
                        # If the clicked item is selected and it's the only selected item, clear selection
                        if idx in selected_indexes and len(selected_indexes) == 1:
                            sel.clearSelection()
                            # also clear current index
                            self.setCurrentIndex(QModelIndex())
                            return
                        # If the clicked item is selected and multiple are selected, make it the only selection
                        if idx in selected_indexes and len(selected_indexes) > 1:
                            sel.clearSelection()
                            sel.select(idx, QItemSelectionModel.Select)
                            # IMPORTANT: Call super() so Qt updates its internal drag selection anchor.
                            # Without this, dragging from this item would re-select the old selection
                            # because Qt's anchor was still pointing to the old selection start.
                            super().mousePressEvent(event)
                            # Re-apply our desired selection after super() potentially modified it.
                            # The ClearAndSelect ensures only this item is selected as the new anchor.
                            sel.select(idx, QItemSelectionModel.ClearAndSelect)
                            self.setCurrentIndex(idx)
                            return
        except Exception:
            # Fall back to default behavior on any error
            pass
        # Default behavior for all other cases
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        try:
            if event.buttons() & Qt.MouseButton.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                if not isinstance(pos, QPoint):
                    pos = QPoint(int(pos.x()), int(pos.y()))

                # Activate overlay once user meaningfully drags starting on a card.
                if (not self._drag_active) and self._drag_start_pos is not None:
                    if (pos - self._drag_start_pos).manhattanLength() >= self._drag_threshold:
                        self._drag_active = True
                        if self._drag_overlay:
                            self._drag_overlay.start_drag(pos)

                if self._drag_active and self._drag_overlay and self._drag_overlay.is_drag_active():
                    self._drag_overlay.step_drag(pos)
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        super().wheelEvent(event)
        # Wheel scrolling can happen without a mouseMove; keep bubble locked to cursor.
        try:
            if self._drag_active and self._drag_overlay and self._drag_overlay.is_drag_active():
                from PySide6.QtGui import QCursor
                pos = self._drag_overlay.mapFromGlobal(QCursor.pos())
                self._drag_overlay.step_drag(pos)
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = None
                self._drag_active = False
                if self._drag_overlay:
                    self._drag_overlay.stop_drag()
        except Exception:
            pass
        super().mouseReleaseEvent(event)
from PySide6.QtGui import QKeySequence, QShortcut

from src.ui.config import WIDGET_SPACING, LIST_CARD_RIGHT_MARGIN
from src.ui.widgets.main_widgets import (
    create_push_button, create_line_edit, create_combo_box, create_toggle_button
)
from src.ui.widgets.game_list import GameListModel, GameListFilterProxy, SortMode
from src.ui.widgets.game_card import GameCard
from src.ui.widgets.toggles import MultiStepToggle
from src.ui.widgets.flow_layout import SearchableTagFlowWidget
from src.ui.dialogs.game_details_dialog import GameDetailsDialog
from src.ui.pages.base_page import BasePage
from src.ui.pages.data_loader import DataLoader
from src.ui.widgets.badge import BadgeManager, BadgePosition
from src.core.database_manager import DatabaseLockedError
from src.core.encryption_manager import InvalidPasswordError
from src.core.steam_integration import SteamIntegration, SteamCacheRefreshWorker

class HomePage(BasePage):
    """Home page displaying game library with filtering and search."""
    
    status_message = Signal(str)
    steam_fetch_started = Signal()  # Emitted when a Steam fetch operation starts
    steam_fetch_finished = Signal()  # Emitted when all Steam fetch operations are complete
    
    def __init__(self, db_manager, theme_manager, settings_manager):
        super().__init__(db_manager, theme_manager, settings_manager, title="Game Library")
        self._base_title = "Game Library"
        
        # Steam fetch operation tracking
        self._active_steam_ops = set()  # Track active Steam operation names
        
        # Cached game data
        self.games_data = []
        self._cache_valid = False
        
        # Tag state
        self.active_tags = set()
        self.all_tags = []
        
        # Badge manager for tag count
        self.badge_manager = BadgeManager(theme_manager=theme_manager)
        
        # Cached notification manager (lazy-loaded)
        self._notification_manager = None
        
        # Real-time sort timer for deadlines (updates order as deadlines approach/expire)
        self.sort_timer = QTimer(self)
        self.sort_timer.timeout.connect(lambda: self._proxy_model.sort(0))
        self.sort_timer.start(60000)  # Check every minute
        
        self._setup_ui()
        self._connect_signals()
    
    @property
    def tag_buttons(self) -> dict:
        """Access tag buttons dict from the SearchableTagFlowWidget (backwards compatibility)."""
        return self.tag_widget.tag_buttons if hasattr(self, 'tag_widget') else {}
    
    @property
    def notification_manager(self):
        """Get the notification manager from main window (cached)."""
        if self._notification_manager is None:
            try:
                mw = self.window()
                if mw and hasattr(mw, 'notification_manager'):
                    self._notification_manager = mw.notification_manager
            except Exception:
                pass
        return self._notification_manager

    # ============================================================
    # Helper Methods
    # ============================================================

    def _ensure_tags_cached(self, game: dict) -> None:
        """Cache parsed tag set on a game dict for faster filter checks."""
        if game and '_tags' not in game:
            tags_str = game.get('tags') or ''
            game['_tags'] = {t.strip() for t in tags_str.split(',') if t.strip()}

    def _get_filter_state(self) -> dict:
        """Collect current filter values from the UI."""
        return {
            'term': self.search_input.text().strip().lower(),
            'platform': self.platform_combo.currentText(),
            'deadline_only': getattr(self.deadline_toggle, 'isChecked', lambda: False)(),
            'dlc_only': getattr(self.dlc_toggle, 'isChecked', lambda: False)(),
            'used_only': getattr(self.used_toggle, 'isChecked', lambda: False)() if hasattr(self, 'used_toggle') else False,
            'no_pictures_only': getattr(self.no_pictures_toggle, 'isChecked', lambda: False)() if hasattr(self, 'no_pictures_toggle') else False,
            'active_tags': set(self.active_tags),
        }

    def _copy_keys_to_clipboard(self, keys: list[str], status_text: str = None):
        """Copy keys to clipboard and show notification."""
        QApplication.clipboard().setText('\n'.join(keys))
        msg = status_text or f"{len(keys)} keys copied to clipboard"
        self.status_message.emit(msg)
        self.notify_success(msg)

    def _exec_db_update(self, sql: str, params: list) -> bool:
        """Execute a parameterized update in a transaction. Returns success status."""
        try:
            conn = self.db_manager._require_conn()
            cur = conn.cursor()
            cur.execute('BEGIN')
            cur.executemany(sql, params)
            conn.commit()
            self.db_manager._sync_encrypted_db()
            return True
        except Exception:
            if conn:
                try: conn.rollback()
                except Exception: pass
            return False

    def _fetch_and_update_game(self, game_id: int) -> bool:
        """Fetch updated game from DB and apply incremental update."""
        if updated := self.db_manager.get_game_by_id(game_id):
            self._apply_incremental_update(updated)
            return True
        return False
    
    def _get_fresh_game(self, game_id: int) -> dict | None:
        """Get fresh game data from DB by ID. Use for context menu actions after fetch."""
        return self.db_manager.get_game_by_id(game_id)
    
    def _get_fresh_games(self, game_ids: list[int]) -> list[dict]:
        """Get fresh game data from DB for multiple IDs. Filters out None results."""
        return [g for gid in game_ids if (g := self.db_manager.get_game_by_id(gid))]
    
    def _get_steam_ctx(self, name: str) -> dict:
        """Get Steam operation context dict."""
        return getattr(self, f'_steam_{name}_context', {})
    
    @Slot(str, int, int)
    def _on_batch_progress(self, title: str, current: int, total: int):
        """Handle batch fetch progress updates (slot for cross-thread signal)."""
        self._update_steam_progress('batch', title, current, total)
    
    @Slot(str, int, int)
    def _on_reviews_progress(self, title: str, current: int, total: int):
        """Handle reviews refresh progress updates (slot for cross-thread signal)."""
        self._update_steam_progress('reviews', title, current, total)
    
    def _update_steam_progress(self, name: str, title: str, current: int, total: int):
        """Update Steam fetch progress notification."""
        if (notif := self._get_steam_ctx(name).get('notification')) and hasattr(notif, 'update_progress'):
            notif.update_progress(current, total, title)
        self.status_message.emit(f"Fetching {current}/{total}: {title}")
    
    def _complete_steam_op(self, name: str, summary: dict, success_msg: str, count_key: str = 'fetched_count'):
        """Handle Steam operation completion."""
        count, failed, cancelled = summary.get(count_key, 0), summary.get('failed_count', 0), summary.get('cancelled', False)
        if (notif := self._get_steam_ctx(name).get('notification')) and hasattr(notif, 'set_completed') and not cancelled:
            notif.set_completed(count, failed)
        self.status_message.emit(f"{success_msg} {'cancelled' if cancelled else f'for {count} game(s)' if count > 0 else ''}")
        self.reload_tags()

    # ============================================================
    # Filtering
    # ============================================================

    def add_games_by_ids(self, ids: list[int]):
        """Incrementally add newly inserted games to the view without full reload."""
        if not ids:
            return
        
        added_any = False
        existing_ids = {g.get('id') for g in self.games_data}
        
        for gid in ids:
            try:
                game = self.db_manager.get_game_by_id(int(gid))
            except Exception:
                continue
            
            if not game or game.get('id') in existing_ids:
                continue
            
            self._ensure_tags_cached(game)
            self.games_data.insert(0, game)
            
            try:
                self._list_model.add_game(game, 0)
            except Exception:
                self._display_games()
            
            added_any = True
        
        if added_any:
            self._update_title_count(len(self.games_data))
            self._refresh_platforms()
            self._update_empty_state()
            # Reload tags in case new games brought new tags
            self.reload_tags()

    # ============================================================
    # UI Setup
    # ============================================================

    def _setup_ui(self):
        """Setup the user interface."""
        # Remove margins - filter bar goes edge-to-edge
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Hide default BasePage containers
        if hasattr(self, 'content_container'):
            self.content_container.hide()
        if hasattr(self, 'header_widget'):
            self.header_widget.hide()
        
        # Filter bar (full width)
        self._create_filter_bar(self.main_layout)
        
        # Content container with margins
        self.home_content = QWidget()
        self.home_content_layout = QVBoxLayout(self.home_content)
        self.home_content_layout.setContentsMargins(10, 10, 10, 5)
        self.home_content_layout.setSpacing(WIDGET_SPACING)
        
        # Games display area
        self._create_games_area(self.home_content_layout)
        self.main_layout.addWidget(self.home_content, 1)
        
        # Apply saved view mode
        saved_mode = self.settings_manager.get('game_list_view_mode', 'grid')
        self._toggle_view_mode(1 if saved_mode == 'list' else 0)
    
    def _create_filter_bar(self, parent_layout):
        """Create full-width filter bar at the top of the page."""
        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("home_filter_bar")
        # Fixed height - never changes regardless of tags visibility
        self.filter_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        filter_bar_layout = QHBoxLayout(self.filter_bar)
        filter_bar_layout.setContentsMargins(12, 8, 12, 8)
        filter_bar_layout.setSpacing(WIDGET_SPACING)
        
        # Title
        self.header_label = QLabel(self._base_title)
        self.header_label.setObjectName("page_title")
        filter_bar_layout.addWidget(self.header_label)
        self._update_title_count(0)
        
        # Search input
        self.search_input = create_line_edit()
        self.search_input.setPlaceholderText("Search by title or key...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(200)
        filter_bar_layout.addWidget(self.search_input, 1)
        
        # Platform filter
        self.platform_combo = create_combo_box()
        self.platform_combo.setFixedWidth(110)
        filter_bar_layout.addWidget(self.platform_combo)
        
        # Sort order combo box
        self.sort_combo = create_combo_box()
        self.sort_combo.setFixedWidth(140)
        self.sort_combo.setToolTip("Sort games by...")
        self._setup_sort_combo()
        filter_bar_layout.addWidget(self.sort_combo)
        
        # Filters toggle button (opens collapsible filters panel)
        self.filters_toggle_btn = create_toggle_button(
            "Filters", force_unchecked=True, object_name="toggle_button",
            tooltip="Show/hide filters panel"
        )
        self.filters_toggle_btn.toggled.connect(self._on_filters_toggled)
        self.badge_manager.add_badge(self.filters_toggle_btn, count=0, position=BadgePosition.TOP_RIGHT)
        # Add context menu for clearing filters
        self.filters_toggle_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.filters_toggle_btn.customContextMenuRequested.connect(self._show_filters_context_menu)
        filter_bar_layout.addWidget(self.filters_toggle_btn)
        
        # Tags toggle
        self.tags_toggle_btn = create_toggle_button(
            "Tags", force_unchecked=True, object_name="toggle_button",
            tooltip="Show/hide tags panel"
        )
        self.tags_toggle_btn.toggled.connect(self._on_tags_toggled)
        self.badge_manager.add_badge(self.tags_toggle_btn, count=0, position=BadgePosition.TOP_RIGHT)
        # Add context menu for clearing tags
        self.tags_toggle_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tags_toggle_btn.customContextMenuRequested.connect(self._show_tags_context_menu)
        filter_bar_layout.addWidget(self.tags_toggle_btn)
        
        # View toggle
        saved_mode = self.settings_manager.get('game_list_view_mode', 'grid')
        self.view_toggle = MultiStepToggle(
            options=["Grid", "List"], parent=self,
            current_index=1 if saved_mode == 'list' else 0,
            theme_manager=self.theme_manager
        )
        self.view_toggle.position_changed.connect(self._toggle_view_mode)
        filter_bar_layout.addWidget(self.view_toggle)
        
        parent_layout.addWidget(self.filter_bar)
        
        # === Secondary Filters Bar (collapsible panel for filter toggles) ===
        self._create_filters_bar(parent_layout)
        
        # === Secondary Tags Bar (separate from main filter bar to prevent flickering) ===
        self._create_tags_bar(parent_layout)
    
    def _create_filters_bar(self, parent_layout):
        """Create the collapsible filters bar with filter toggles."""
        self.filters_bar = QFrame()
        self.filters_bar.setObjectName("home_filters_bar")
        self.filters_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        
        filters_bar_layout = QHBoxLayout(self.filters_bar)
        filters_bar_layout.setContentsMargins(12, 4, 12, 8)
        filters_bar_layout.setSpacing(WIDGET_SPACING)
        
        # Filter toggles - moved from main filter bar
        self.deadline_toggle = self._create_filter_toggle(
            "⏳Deadline", 'filter_deadline_only',
            "Show only games with a redemption deadline"
        )
        filters_bar_layout.addWidget(self.deadline_toggle)
        
        self.dlc_toggle = self._create_filter_toggle(
            "📦DLC", 'filter_dlc_only',
            "Show only games marked as DLC"
        )
        filters_bar_layout.addWidget(self.dlc_toggle)

        # Used toggle - filter to only games marked used
        self.used_toggle = self._create_filter_toggle(
            "✔️Used", 'filter_used_only',
            "Show only games marked as used"
        )
        filters_bar_layout.addWidget(self.used_toggle)

        # Debug-only filter: show games without a picture. Hidden by default;
        # only shown when Debug Mode is enabled in settings.
        self.no_pictures_toggle = self._create_filter_toggle(
            "📷No Pics", 'filter_no_pictures_only',
            "Show only games that don't have a cover image"
        )
        # Decide visibility robustly: handle boolean or string stored values
        try:
            visible_val = False
            if self.settings_manager is not None:
                raw = self.settings_manager.get('debug_mode', False)
                # Normalize common truthy string values as True
                if isinstance(raw, str):
                    visible_val = raw.strip().lower() in ('1', 'true', 'yes', 'on')
                else:
                    visible_val = bool(raw)
            # Apply visibility
            self.no_pictures_toggle.setVisible(bool(visible_val))
        except Exception:
            # On error, hide the toggle
            try:
                self.no_pictures_toggle.setVisible(False)
            except Exception:
                pass
        filters_bar_layout.addWidget(self.no_pictures_toggle)
        
        # Add stretch to push toggles to the left
        filters_bar_layout.addStretch()
        
        # Hide the filters bar by default
        self.filters_bar.hide()
        parent_layout.addWidget(self.filters_bar)
    
    def _create_filter_toggle(self, label: str, setting_key: str, tooltip: str):
        """Create a filter toggle button with consistent wiring."""
        toggle = create_toggle_button(
            label, settings_manager=self.settings_manager,
            setting_key=setting_key, force_unchecked=True,
            object_name="toggle_button", tooltip=tooltip
        )
        toggle.toggled.connect(lambda checked: self._on_filter_toggle_changed(toggle, setting_key, tooltip, checked))
        return toggle

    def _setup_sort_combo(self):
        """Setup the sort order combo box with all available sort modes."""
        # Define sort options with display names
        self._sort_mode_map = {
            "⏳ Deadline First": SortMode.DEADLINE_FIRST,
            "🔤 Title A-Z": SortMode.TITLE_ASC,
            "🔤 Title Z-A": SortMode.TITLE_DESC,
            "🎮 Platform A-Z": SortMode.PLATFORM_ASC,
            "🎮 Platform Z-A": SortMode.PLATFORM_DESC,
            "📅 Newest First": SortMode.DATE_ADDED_NEWEST,
            "📅 Oldest First": SortMode.DATE_ADDED_OLDEST,
            "👍 Rating High": SortMode.RATING_HIGH,
            "👎 Rating Low": SortMode.RATING_LOW,
        }
        
        for display_name in self._sort_mode_map.keys():
            self.sort_combo.addItem(display_name)
        
        # Load saved sort mode
        saved_sort = self.settings_manager.get('game_list_sort_mode', 'deadline_first')
        # Find the index for the saved sort mode
        for idx, (_, mode) in enumerate(self._sort_mode_map.items()):
            if mode.value == saved_sort:
                self.sort_combo.setCurrentIndex(idx)
                break
        
        # Connect signal
        self.sort_combo.currentIndexChanged.connect(self._on_sort_mode_changed)
    
    def _on_sort_mode_changed(self, index: int):
        """Handle sort mode combo box change."""
        display_name = self.sort_combo.currentText()
        sort_mode = self._sort_mode_map.get(display_name, SortMode.DEADLINE_FIRST)
        
        # Save preference
        self.settings_manager.set('game_list_sort_mode', sort_mode.value)
        
        # Apply to proxy model
        if hasattr(self, '_proxy_model'):
            self._proxy_model.set_sort_mode(sort_mode)
            self._proxy_model.sort(0)

    def set_debug_mode_visible(self, visible: bool):
        """Called by Settings to show/hide debug-only controls on the Home page.

        When hiding debug controls we also clear any debug-only filter state to avoid
        a hidden active filter from confusing the user.
        """
        try:
            if hasattr(self, 'no_pictures_toggle'):
                self.no_pictures_toggle.setVisible(bool(visible))
                if not visible:
                    # disable cleared filter state
                    try:
                        self.no_pictures_toggle.setChecked(False)
                    except Exception:
                        pass
                    try:
                        self.settings_manager.set('filter_no_pictures_only', False)
                    except Exception:
                        pass
                # Reapply filters in case the toggle state changed
                try:
                    self._apply_filters()
                except Exception:
                    pass
        except Exception:
            pass
    
    def _on_filter_toggle_changed(self, widget, setting_key: str, tooltip_base: str, checked: bool):
        """Handle filter toggle state change."""
        widget.setToolTip(tooltip_base)

        self.settings_manager.set(setting_key, checked)
        self._update_filters_badge()
        self._apply_filters()
    
    def _create_tags_bar(self, parent_layout):
        """Create the secondary tags bar (separate from main filter bar to prevent flickering)."""
        # Secondary bar container - completely separate from main filter bar
        self.tags_bar = QFrame()
        self.tags_bar.setObjectName("home_tags_bar")
        self.tags_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        
        tags_bar_layout = QVBoxLayout(self.tags_bar)
        tags_bar_layout.setContentsMargins(12, 4, 12, 8)
        tags_bar_layout.setSpacing(0)
        
        # Use SearchableTagFlowWidget which bundles search, tags flow, and clear button
        self.tag_widget = SearchableTagFlowWidget(
            search_placeholder="Search tags...",
            clear_button_text="Clear All Selected Tags",
            object_name="Transparent"
        )
        self.tag_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Connect signals
        self.tag_widget.tag_toggled.connect(self._on_tag_toggled)
        self.tag_widget.tags_cleared.connect(self._on_tags_cleared)
        
        # Keep references for compatibility
        self.tag_layout = self.tag_widget.flow_layout
        self.clear_tags_btn = self.tag_widget.clear_button
        
        tags_bar_layout.addWidget(self.tag_widget)
        
        # Hide the entire tags bar by default
        self.tags_bar.hide()
        parent_layout.addWidget(self.tags_bar)

    def _create_games_area(self, parent_layout):
        """Create games display area with list view and empty state."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Create list view
        self.list_view = self._create_list_view()
        
        # Apply edge-fade overlays
        try:
            from src.ui.widgets.main_widgets import apply_edge_fade_to_widget
            apply_edge_fade_to_widget(self.list_view.viewport(), theme_manager=self.theme_manager)
        except Exception:
            pass

        # Empty state label
        self.empty_label = QLabel("No games found\nHow about we go add some?")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("font-size: 16px; color: #666; margin: 50px;")
        self.empty_label.hide()

        container_layout.addWidget(self.list_view, 1)
        container_layout.addWidget(self.empty_label, 0)

        # Login widget for encrypted databases
        self.login_widget = self._build_login_widget()

        # Stack for switching between games view and login
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(container)
        self.content_stack.addWidget(self.login_widget)

        parent_layout.addWidget(self.content_stack, 1)
    
    def _create_list_view(self) -> QListView:
        """Create and configure the game list view."""
        list_view = ToggleDeselectListView(theme_manager=self.theme_manager)
        list_view.setUniformItemSizes(True)
        list_view.setViewMode(QListView.IconMode)
        list_view.setMovement(QListView.Static)
        list_view.setResizeMode(QListView.Adjust)
        list_view.setSpacing(0)
        list_view.setWrapping(True)
        list_view.setMouseTracking(True)
        list_view.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        list_view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        list_view.setContentsMargins(10, 10, 10, 10)
        list_view.setViewportMargins(0, 0, 0, 0)
        list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        list_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_view.verticalScrollBar().setSingleStep(20)
        try:
            # Use MinimalViewportUpdate for better scroll performance
            # FullViewportUpdate repaints everything on each scroll which is very slow
            list_view.setViewportUpdateMode(QAbstractItemView.ViewportUpdateMode.MinimalViewportUpdate)
        except AttributeError:
            pass  # Not available in all PySide6 versions

        # Setup model/delegate
        self._list_model = GameListModel([])
        self._proxy_model = GameListFilterProxy()
        self._proxy_model.setSourceModel(self._list_model)
        self._delegate = GameCard(self.theme_manager, settings_manager=self.settings_manager)
        list_view.setModel(self._proxy_model)
        list_view.setItemDelegate(self._delegate)
        
        # Connect signals
        list_view.doubleClicked.connect(self._on_list_item_clicked)
        list_view.customContextMenuRequested.connect(self._on_list_context_menu)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence.Copy, list_view).activated.connect(self._copy_selected_keys)
        QShortcut(QKeySequence("Delete"), list_view).activated.connect(self._delete_selected_games)
        QShortcut(QKeySequence(Qt.Key_Return), list_view).activated.connect(self._edit_selected_games)
        
        return list_view

    def _build_login_widget(self) -> QGroupBox:
        """Build the password entry widget for encrypted databases."""
        box = QGroupBox()
        layout = QVBoxLayout(box)
        layout.addStretch()
        
        container = QWidget(objectName="Transparent")
        container_layout = QVBoxLayout(container)

        # Title
        title = QLabel("Encrypted Database")
        font = title.font()
        font.setPointSize(max(10, font.pointSize() + 2))
        font.setBold(True)
        title.setFont(font)
        container_layout.addWidget(title)

        # Info text
        container_layout.addWidget(QLabel("Please enter your password to unlock and load your games."))

        # Input row
        input_row = QHBoxLayout()
        self.login_password_input = create_line_edit()
        if isinstance(self.login_password_input, QLineEdit):
            self.login_password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.login_password_input.returnPressed.connect(self._attempt_unlock)
        input_row.addWidget(self.login_password_input, 1)

        self.login_button = create_push_button("Unlock")
        self.login_button.setFixedWidth(80)
        self.login_button.clicked.connect(self._attempt_unlock)
        input_row.addWidget(self.login_button)
        container_layout.addLayout(input_row)

        # Feedback label
        self.login_message_label = QLabel()
        self.login_message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.login_message_label)

        layout.addWidget(container, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return box

    # ============================================================
    # Encryption/Lock State Management
    # ============================================================

    def _set_filters_enabled(self, enabled: bool):
        """Enable or disable filter controls."""
        widgets = [
            self.search_input, self.platform_combo, 
            getattr(self, 'filters_toggle_btn', None), self.tags_toggle_btn, self.view_toggle
        ]
        for widget in widgets:
            if widget:
                widget.setEnabled(enabled)
        
        # Enable/disable the filters bar (contains filter toggles)
        if hasattr(self, 'filters_bar'):
            self.filters_bar.setEnabled(enabled)
            if not enabled:
                self.filters_bar.hide()
            elif hasattr(self, 'filters_toggle_btn') and self.filters_toggle_btn.isChecked():
                self.filters_bar.show()
        
        # Enable/disable the tags bar (contains search, tags, and clear button)
        self.tags_bar.setEnabled(enabled)
        
        if not enabled:
            self.tags_bar.hide()
        elif self.tags_toggle_btn.isChecked():
            self.tags_bar.show()

    def _show_locked_state(self):
        """Show the password entry UI for encrypted database."""
        self.content_stack.setCurrentWidget(self.login_widget)
        self._set_filters_enabled(False)
        self._list_model.set_games([])
        self.games_data = []
        self._cache_valid = False
        self._update_title_count(0)
        self.empty_label.hide()
        self.login_message_label.clear()
        self.login_password_input.clear()
        self.login_password_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _show_unlocked_state(self):
        """Show the normal games view."""
        self.content_stack.setCurrentIndex(0)
        self._set_filters_enabled(True)
        self.login_message_label.clear()
        self.login_password_input.clear()

    def _set_login_feedback(self, message: str, error: bool = True):
        """Set feedback message on login widget."""
        color = "#d9534f" if error else "#5cb85c"
        self.login_message_label.setStyleSheet(f"color: {color};")
        self.login_message_label.setText(message)

    def _attempt_unlock(self):
        """Attempt to unlock the encrypted database."""
        password = self.login_password_input.text() if isinstance(self.login_password_input, QLineEdit) else ""
        
        if not password:
            self._set_login_feedback("Enter your password to continue.")
            return
        
        try:
            self.db_manager.unlock(password)
            self.db_manager.initialize(password)
        except InvalidPasswordError:
            self._set_login_feedback("Incorrect password. Try again.")
            self.login_password_input.selectAll()
            self.login_password_input.setFocus()
            return
        except Exception as e:
            self._set_login_feedback(f"Unlock failed: {e}")
            return
        
        self._set_login_feedback("Unlocked successfully.", error=False)
        self.status_message.emit("Database unlocked")
        self._show_unlocked_state()
        self._cache_valid = False
        self.refresh(force_reload=True)

    def _enforcement_check(self) -> bool:
        """Check if database is locked and show appropriate UI."""
        if getattr(self.db_manager, 'requires_password', None) and self.db_manager.requires_password():
            self._show_locked_state()
            self.status_message.emit("Database locked — enter password to load games")
            return False
        self._show_unlocked_state()
        return True

    def on_encryption_status_changed(self, enabled: bool):
        """Handle encryption status changes."""
        if not self._enforcement_check():
            return
        self._cache_valid = False
        self.refresh(force_reload=True)
    
    # ============================================================
    # Signal Connections
    # ============================================================
    
    def _connect_signals(self):
        """Connect UI signals."""
        self.search_input.textChanged.connect(self._on_filter_changed)
        self.platform_combo.currentTextChanged.connect(self._on_filter_changed)
        self.view_toggle.toggled.connect(self._toggle_view_mode)
        
        # Debounced search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(lambda: self.search_timer.start(80))
        
    # ============================================================
    # Data Loading
    # ============================================================
        
    def _start_data_load(self):
        """Start background thread to load games and filters."""
        # Cancel any previous loader that might still be running
        if hasattr(self, '_loader') and self._loader is not None:
            try:
                self._loader.data_loaded.disconnect()
            except Exception:
                pass
            if self._loader.isRunning():
                self._loader.quit()
                self._loader.wait(500)  # Wait up to 500ms
        
        try:
            db_path = self.db_manager.get_working_path()
        except DatabaseLockedError:
            self._show_locked_state()
            return
        
        self._show_unlocked_state()
        self._loader = DataLoader(db_path)
        self._loader.data_loaded.connect(self._on_data_loaded, Qt.ConnectionType.QueuedConnection)
        self._loader.start()

    @Slot(list, list, list)
    def _on_data_loaded(self, games: list, platforms: list, categories: list):
        """Handle loaded data: populate cache, filters, and display."""
        if not self._enforcement_check():
            return
        
        # Cache tags for all games
        for g in games:
            self._ensure_tags_cached(g)
        
        self.games_data = games
        self._cache_valid = True
        self._update_title_count(len(games))
        
        # Populate platform filter
        self.platform_combo.clear()
        self.platform_combo.addItems(platforms)
        
        # Populate tags (exclude 'All Categories' placeholder)
        tags = categories[1:] if categories and categories[0].startswith('All') else categories
        current_active = set(self.active_tags)
        self.all_tags = tags
        self._populate_tags()
        
        # Restore active tag selection
        if current_active:
            valid_tags = current_active & set(self.all_tags)
            self.active_tags = valid_tags
            self.tag_widget.set_active_tags(valid_tags, emit_signal=False)
            self._update_tags_badge()
        
        # Update filters badge to reflect saved filter states
        self._update_filters_badge()
        
        self._display_games()
        self.status_message.emit("Game library refreshed")
    
    # ============================================================
    # Tag Management
    # ============================================================
    
    def _populate_tags(self):
        """Create tag buttons from loaded tags."""
        # Use SearchableTagFlowWidget's set_tags method
        self.tag_widget.set_tags(self.all_tags, preserve_active=True)
        # Sync active_tags with the widget's state
        self.active_tags = self.tag_widget.get_active_tags()

    def _on_tags_toggled(self, checked: bool):
        """Show or hide the tags bar with smooth animation."""
        if hasattr(self, '_tag_anim') and self._tag_anim:
            self._tag_anim.stop()
        
        MAX_HEIGHT = 16777215  # Qt's QWIDGETSIZE_MAX
        
        if checked:
            # Show: set height to 0, show bar, then animate to target height
            self.tags_bar.setMaximumHeight(0)
            self.tags_bar.show()
            self.tags_bar.setMaximumHeight(MAX_HEIGHT)
            self.tags_bar.adjustSize()
            target_height = self.tags_bar.sizeHint().height()
            self.tags_bar.setMaximumHeight(0)
            self._animate_tag_panel(0, target_height, lambda: self.tags_bar.setMaximumHeight(MAX_HEIGHT))
        else:
            # Hide: animate from current height to 0, then hide
            current_height = self.tags_bar.height()
            if current_height > 0:
                self.tags_bar.setMinimumHeight(0)
                self.tags_bar.setMaximumHeight(current_height)
                def on_hide():
                    self.tags_bar.hide()
                    self.tags_bar.setMaximumHeight(MAX_HEIGHT)
                self._animate_tag_panel(current_height, 0, on_hide)
            else:
                self.tags_bar.hide()
        self.status_message.emit("Tags panel opened" if checked else "Tags panel closed")
    
    def _animate_tag_panel(self, start: int, end: int, on_finish: Callable):
        """Create and run tags bar height animation."""
        self._tag_anim = QPropertyAnimation(self.tags_bar, b"maximumHeight", self)
        self._tag_anim.setDuration(100)
        self._tag_anim.setStartValue(start)
        self._tag_anim.setEndValue(end)
        self._tag_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._tag_anim.finished.connect(on_finish)
        self._tag_anim.start()

    def _on_tag_toggled(self, tag: str, checked: bool):
        """Handle tag selection toggle."""
        # Update internal state from widget
        self.active_tags = self.tag_widget.get_active_tags()
        
        action = "applied" if checked else "removed"
        self.status_message.emit(f"Tag '{tag}' {action} ({len(self.active_tags)} active)")
        self._update_tags_badge()
        self._apply_filters()

    def _on_tags_cleared(self):
        """Handle when all tags are cleared via the widget."""
        self.active_tags.clear()
        self._update_tags_badge()
        self._apply_filters()
        self.status_message.emit("All tags cleared")

    def _clear_all_tags(self):
        """Deselect all tag buttons."""
        self.tag_widget.clear_active_tags()
        # Note: _on_tags_cleared will be called via signal
    
    def _update_tags_badge(self):
        """Update the badge count on tags toggle button."""
        self.badge_manager.update_count(self.tags_toggle_btn, len(self.active_tags))

    # ============================================================
    # Filters Panel Management
    # ============================================================
    
    def _on_filters_toggled(self, checked: bool):
        """Show or hide the filters bar with smooth animation."""
        if hasattr(self, '_filters_anim') and self._filters_anim:
            self._filters_anim.stop()
        
        MAX_HEIGHT = 16777215  # Qt's QWIDGETSIZE_MAX
        
        if checked:
            # Show: set height to 0, show bar, then animate to target height
            self.filters_bar.setMaximumHeight(0)
            self.filters_bar.show()
            self.filters_bar.setMaximumHeight(MAX_HEIGHT)
            self.filters_bar.adjustSize()
            target_height = self.filters_bar.sizeHint().height()
            self.filters_bar.setMaximumHeight(0)
            self._animate_filters_panel(0, target_height, lambda: self.filters_bar.setMaximumHeight(MAX_HEIGHT))
        else:
            # Hide: animate from current height to 0, then hide
            current_height = self.filters_bar.height()
            if current_height > 0:
                self.filters_bar.setMinimumHeight(0)
                self.filters_bar.setMaximumHeight(current_height)
                def on_hide():
                    self.filters_bar.hide()
                    self.filters_bar.setMaximumHeight(MAX_HEIGHT)
                self._animate_filters_panel(current_height, 0, on_hide)
            else:
                self.filters_bar.hide()
        self.status_message.emit("Filters panel opened" if checked else "Filters panel closed")
    
    def _animate_filters_panel(self, start: int, end: int, on_finish: Callable):
        """Create and run filters bar height animation."""
        self._filters_anim = QPropertyAnimation(self.filters_bar, b"maximumHeight", self)
        self._filters_anim.setDuration(100)
        self._filters_anim.setStartValue(start)
        self._filters_anim.setEndValue(end)
        self._filters_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._filters_anim.finished.connect(on_finish)
        self._filters_anim.start()
    
    def _get_active_filters_count(self) -> int:
        """Count the number of currently active filter toggles."""
        count = 0
        if hasattr(self, 'deadline_toggle') and self.deadline_toggle.isChecked():
            count += 1
        if hasattr(self, 'dlc_toggle') and self.dlc_toggle.isChecked():
            count += 1
        if hasattr(self, 'used_toggle') and self.used_toggle.isChecked():
            count += 1
        if hasattr(self, 'no_pictures_toggle') and self.no_pictures_toggle.isVisible() and self.no_pictures_toggle.isChecked():
            count += 1
        return count
    
    def _update_filters_badge(self):
        """Update the badge count on filters toggle button."""
        if hasattr(self, 'filters_toggle_btn'):
            self.badge_manager.update_count(self.filters_toggle_btn, self._get_active_filters_count())

    def _add_clear_menu_items(self, menu: QMenu, *, clear_label: str, active_count: int, on_clear) -> None:
        """Add the standard 'clear' vs 'nothing to clear' items to a context menu."""
        # Two mutually-exclusive actions:
        # - If there are active items: show "Clear ..."
        # - If none are active: show a disabled "Nothing to clear"
        clear_action = menu.addAction(clear_label)
        nothing_action = menu.addAction("Nothing to clear")

        clear_action.triggered.connect(on_clear)
        nothing_action.setEnabled(False)

        clear_action.setVisible(active_count > 0)
        nothing_action.setVisible(active_count == 0)
    
    def _show_filters_context_menu(self, pos):
        """Show context menu for the filters toggle button."""
        menu = QMenu(self)

        self._add_clear_menu_items(
            menu,
            clear_label="Clear All Filters",
            active_count=self._get_active_filters_count(),
            on_clear=self._clear_all_filters,
        )
        
        menu.exec(self.filters_toggle_btn.mapToGlobal(pos))
    
    def _clear_all_filters(self):
        """Clear all active filter toggles."""
        # Uncheck all filter toggles
        if hasattr(self, 'deadline_toggle'):
            self.deadline_toggle.setChecked(False)
        if hasattr(self, 'dlc_toggle'):
            self.dlc_toggle.setChecked(False)
        if hasattr(self, 'used_toggle'):
            self.used_toggle.setChecked(False)
        if hasattr(self, 'no_pictures_toggle'):
            self.no_pictures_toggle.setChecked(False)
        
        # Update badge and apply filters
        self._update_filters_badge()
        self._apply_filters()
        self.status_message.emit("All filters cleared")
    
    def _show_tags_context_menu(self, pos):
        """Show context menu for the tags toggle button."""
        menu = QMenu(self)

        self._add_clear_menu_items(
            menu,
            clear_label="Clear All Tags",
            active_count=len(self.active_tags),
            on_clear=self._clear_all_tags,
        )
        
        menu.exec(self.tags_toggle_btn.mapToGlobal(pos))
    
    def reload_tags(self):
        """Reload tags from database and update UI.
        
        Only shows tags that are currently in use (assigned to at least one game).
        Also filters out Steam platform feature tags (like 'Steam Achievements',
        'Steam Cloud', etc.) to keep the tag list focused on gameplay descriptors.
        """
        try:
            # Only get tags that are actually in use (assigned to games)
            tags = self.db_manager.get_tags_in_use()
            platform_names = self.db_manager.get_platforms() or []
            
            # Get the ignored tags set from SteamIntegration
            ignored_tags = SteamIntegration.IGNORED_TAGS
            
            # Filter out platform names and ignored Steam feature tags
            self.all_tags = [
                t['name'] for t in tags 
                if t['name'] not in platform_names 
                and t['name'].lower() not in ignored_tags
            ]
            self.active_tags &= set(self.all_tags)
            self._update_tags_badge()
            self._populate_tags()
            self._apply_filters()
        except Exception:
            pass

    # ============================================================
    # Refresh and Display
    # ============================================================

    def refresh(self, force_reload: bool = False):
        """Refresh page: reload data if needed, then update display."""
        # Invalidate cache first if force reload requested
        if force_reload:
            self._cache_valid = False
        
        if not self._enforcement_check():
            return
        
        if not self._cache_valid:
            self._start_data_load()
        else:
            self._apply_filters()
            self.status_message.emit("Game library refreshed")

    def on_show(self, params=None):
        """Lifecycle hook when page becomes visible."""
        if not self._enforcement_check():
            return
        
        if not self._cache_valid:
            self._start_data_load()
        else:
            self._apply_filters()
    
    def _refresh_platforms(self):
        """Refresh platform filter combobox from database."""
        try:
            current = self.platform_combo.currentText()
            platforms = ['All Platforms'] + list(self.db_manager.get_platforms())
            
            self.platform_combo.blockSignals(True)
            self.platform_combo.clear()
            self.platform_combo.addItems(platforms)
            
            # Restore selection if still valid
            idx = self.platform_combo.findText(current)
            self.platform_combo.setCurrentIndex(max(0, idx))
            self.platform_combo.blockSignals(False)
            
            # Apply filters if selection changed
            if idx < 0:
                self._apply_filters()
        except Exception:
            pass
    
    def _update_title_count(self, count: int = 0):
        """Update page title with game count.

        If a proxy model exists, prefer showing the number of visible (filtered) games.
        Falls back to provided count if the proxy model isn't available yet.
        """
        try:
            if hasattr(self, '_proxy_model') and self._proxy_model is not None:
                visible_count = self._proxy_model.rowCount()
            else:
                visible_count = count
        except Exception:
            visible_count = count
        suffix = "1 game" if visible_count == 1 else f"{visible_count} games"
        self.header_label.setText(f"{self._base_title} - {suffix}")
    
    def _on_filter_changed(self):
        """Handle filter changes (non-search)."""
        if self.sender() != self.search_input:
            self._apply_filters()
    
    def _apply_filters(self):
        """Apply current filters via proxy model."""
        state = self._get_filter_state()
        self._proxy_model.set_search_term(state['term'])
        self._proxy_model.set_platform_filter(state['platform'])
        self._proxy_model.set_tag_filter(state['active_tags'])
        self._proxy_model.set_deadline_filter(state['deadline_only'])
        self._proxy_model.set_dlc_filter(state['dlc_only'])
        self._proxy_model.set_used_filter(state.get('used_only', False))
        # If debug-only 'no pictures' filter is available, apply it
        try:
            self._proxy_model.set_no_pictures_filter(state.get('no_pictures_only', False))
        except Exception:
            pass
        
        # Update delegate with active tags so it only shows matching tags on cards
        self._delegate.set_active_tag_filter(state['active_tags'])
        
        self._update_empty_state()
        # Keep title reactive to current filters (show visible count)
        try:
            self._update_title_count(self._proxy_model.rowCount())
        except Exception:
            # Fallback: leave title as-is on error
            pass

    def _display_games(self):
        """Display all games (proxy handles filtering and sorting)."""
        self._list_model.set_games(self.games_data)
        
        # Apply saved sort mode
        if hasattr(self, '_sort_mode_map') and hasattr(self, 'sort_combo'):
            display_name = self.sort_combo.currentText()
            sort_mode = self._sort_mode_map.get(display_name, SortMode.DEADLINE_FIRST)
            self._proxy_model.set_sort_mode(sort_mode)
        
        # Enable sorting - this activates lessThan() for sorting
        self._proxy_model.sort(0)
        self._apply_filters()
    
    def _update_empty_state(self):
        """Toggle empty state visibility based on filtered results."""
        has_items = self._proxy_model.rowCount() > 0
        self.empty_label.setVisible(not has_items)
        self.list_view.setVisible(has_items)
    
    # ============================================================
    # Incremental Updates
    # ============================================================
    
    def _apply_incremental_update(self, updated: dict):
        """Update caches and model for a single game."""
        if not updated:
            return
        
        uid = updated.get('id')
        self._ensure_tags_cached(updated)
        
        # Update cache
        for i, g in enumerate(self.games_data):
            if g.get('id') == uid:
                self.games_data[i] = updated
                break
        
        # Update model
        try:
            self._list_model.update_game_by_id(updated)
            self._proxy_model.invalidate_tag_cache_for_game(uid)
            self._proxy_model.invalidateFilter()
            # Update empty state and title after filter invalidation so counts reflect current filters
            try:
                self._update_empty_state()
                self._update_title_count(self._proxy_model.rowCount())
            except Exception:
                pass
            self._refresh_platforms()
        except Exception:
            self._display_games()

    def _apply_batch_update(self, updated_games: list[dict]):
        """Update caches and model for multiple games efficiently."""
        if not updated_games:
            return
            
        # Update local cache
        updated_map = {g['id']: g for g in updated_games}
        for i, g in enumerate(self.games_data):
            if g.get('id') in updated_map:
                self.games_data[i] = updated_map[g['id']]
        
        # Pause hover animations during batch update to prevent repaint conflicts
        delegate_timer_was_active = False
        if hasattr(self, '_delegate') and hasattr(self._delegate, '_zoom_timer'):
            delegate_timer_was_active = self._delegate._zoom_timer.isActive()
            if delegate_timer_was_active:
                self._delegate._zoom_timer.stop()
        
        # Update model
        try:
            # Collect updated rows without emitting dataChanged for each
            updated_rows = []
            for game in updated_games:
                self._ensure_tags_cached(game)
                row = self._list_model.update_game_by_id(game, emit=False)
                if row >= 0:
                    updated_rows.append(row)
                self._proxy_model.invalidate_tag_cache_for_game(game['id'])
            
            # Emit single batched dataChanged for all updated rows
            if updated_rows:
                self._list_model.emit_batch_changed(updated_rows)
            
            # Single expensive call
            self._proxy_model.invalidateFilter()
            # Update empty state and title now that filtering has been invalidated
            try:
                self._update_empty_state()
                self._update_title_count(self._proxy_model.rowCount())
            except Exception:
                pass
            self._refresh_platforms()
        except Exception:
            self._display_games()
        finally:
            # Resume hover animations if they were active
            if delegate_timer_was_active and hasattr(self, '_delegate') and hasattr(self._delegate, '_zoom_timer'):
                if self._delegate._hover_targets:
                    self._delegate._zoom_timer.start()

    def _fetch_and_update_games_batch(self, game_ids: list[int]):
        """Fetch multiple games from DB and update UI in batch."""
        updated_games = []
        for gid in game_ids:
            if game := self.db_manager.get_game_by_id(gid):
                updated_games.append(game)
        
        if updated_games:
            self._apply_batch_update(updated_games)

    def _remove_game_by_id(self, gid: int, update_empty_state: bool = True):
        """Remove game from cache and model."""
        self.games_data = [g for g in self.games_data if g.get('id') != gid]
        self._list_model.remove_game_by_id(gid)
        self._refresh_platforms()
        
        if update_empty_state:
            self._update_empty_state()
            try:
                self._update_title_count(self._proxy_model.rowCount())
            except Exception:
                pass
    
    # ============================================================
    # View Mode
    # ============================================================
    
    def _toggle_view_mode(self, position_index: int):
        """Toggle between grid (0) and list (1) view."""
        is_list = position_index == 1
        view_mode = 'list' if is_list else 'grid'
        self.settings_manager.set('game_list_view_mode', view_mode)
        
        if is_list:
            self.list_view.setViewMode(QListView.ListMode)
            self.list_view.setFlow(QListView.TopToBottom)
            self.list_view.setWrapping(False)
            self.list_view.setViewportMargins(0, 0, LIST_CARD_RIGHT_MARGIN, 0)
            self.list_view.setGridSize(QSize())
        else:
            self.list_view.setViewMode(QListView.IconMode)
            self.list_view.setFlow(QListView.LeftToRight)
            self.list_view.setWrapping(True)
            self.list_view.setViewportMargins(0, 0, 0, 0)
            try:
                self.list_view.setGridSize(self._delegate.sizeHint(None, None))
            except Exception:
                pass
        
        self.list_view.setSpacing(0)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.updateGeometries()
        self.list_view.viewport().update()
        self.list_view.verticalScrollBar().setSingleStep(20)

    # ============================================================
    # Context Menu and Interactions
    # ============================================================

    def _on_list_context_menu(self, pos):
        """Show context menu for list view."""
        idx = self.list_view.indexAt(pos)
        global_pos = self.list_view.viewport().mapToGlobal(pos)
        selected = self.list_view.selectionModel().selectedRows()

        # Multiple selection -> batch menu
        if len(selected) > 1:
            games = [g for i in selected if (g := self._get_game_at_proxy_index(i))]
            if games:
                self._show_batch_context_menu(games, global_pos)
            return

        # Single selection or click on item
        if len(selected) == 1 and idx.isValid() and idx.row() == selected[0].row():
            if game := self._get_game_at_proxy_index(selected[0]):
                self._show_single_context_menu(game, global_pos)
            return

        # Click on specific item
        if idx.isValid():
            if game := self._get_game_at_proxy_index(idx):
                self._show_single_context_menu(game, global_pos)

    def _get_game_at_proxy_index(self, proxy_index):
        """Get game dict from proxy model index."""
        source_index = self._proxy_model.mapToSource(proxy_index)
        return self._list_model.game_at(source_index.row()) if source_index.isValid() else None

    def _on_list_item_clicked(self, index):
        """Handle double-click to show game details."""
        # Block double-click while Steam fetch is in progress
        if self.is_steam_fetch_active():
            self.notify_warning("Game details page disabled while fetch is in progress.")
            return
        
        if game := self._get_game_at_proxy_index(index):
            self._show_game_details(game)
    
    def _show_game_details(self, game):
        """Show game details dialog."""
        dialog = GameDetailsDialog(game, self.db_manager, self.theme_manager, self)
        
        def on_updated(saved_count, saved_titles):
            games = game if isinstance(game, list) else [game]
            
            for g in games:
                if not self._fetch_and_update_game(g['id']):
                    self.refresh(force_reload=True)
                    return
            
            # Reload tags in case tags were added/removed
            self.reload_tags()
            
            # Status message
            if saved_count > 1:
                self.status_message.emit(f'Updated {saved_count} games')
                msg = ", ".join(saved_titles[:3]) if len(saved_titles) <= 3 else f"{saved_count} games"
                self.notify_success(f"Saved changes to {msg}")
            elif saved_count == 1:
                self.status_message.emit('Game updated')
                self.notify_success(f"Saved changes to {saved_titles[0] if saved_titles else 'game'}")
        
        dialog.game_updated.connect(on_updated)
        dialog.exec_()
    
    def _add_debug_cache_menu(self, menu: QMenu, games: list[dict]):
        """Add debug-only cache management submenu."""
        # Check if debug mode is enabled
        try:
            debug_mode = self.settings_manager.get('debug_mode', False)
            if isinstance(debug_mode, str):
                debug_mode = debug_mode.strip().lower() in ('1', 'true', 'yes', 'on')
            if not debug_mode:
                return
        except Exception:
            return

        debug_menu = menu.addMenu("Debug Cache")
        count = len(games)
        
        # Do All
        debug_menu.addAction(f"Do All ({count})", lambda: self._debug_do_all(games))
        debug_menu.addSeparator()
        
        # Clear Images
        debug_menu.addAction(f"Clear Images ({count})", lambda: self._clear_game_images(games))
        
        # Clear AppID
        debug_menu.addAction(f"Clear AppIDs ({count})", lambda: self._clear_game_appids(games))
        
        # Clear Cache Data
        games_with_appid = [g for g in games if g.get('steam_app_id')]
        if games_with_appid:
            unique_appids = set(g['steam_app_id'] for g in games_with_appid)
            debug_menu.addAction(f"Clear Cache Data ({len(unique_appids)} unique AppIDs)", 
                               lambda: self._clear_game_cache_data(games_with_appid))

    def _debug_do_all(self, games: list[dict]):
        """Debug: Perform all clear operations."""
        self._clear_game_images(games)
        self._clear_game_appids(games)
        games_with_appid = [g for g in games if g.get('steam_app_id')]
        if games_with_appid:
            self._clear_game_cache_data(games_with_appid)

    def _clear_game_images(self, games: list[dict]):
        """Debug: Clear local images for selected games."""
        ids = [g['id'] for g in games]
        import os
        
        # Delete files
        deleted_count = 0
        for game in games:
            if path := game.get('image_path'):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete image {path}: {e}")

        # Update DB
        if self._exec_db_update('UPDATE games SET image_path = NULL WHERE id = ?', [(i,) for i in ids]):
            self._fetch_and_update_games_batch(ids)
            self.status_message.emit(f"Cleared images for {len(games)} games (deleted {deleted_count} files)")

    def _clear_game_appids(self, games: list[dict]):
        """Debug: Clear AppIDs for selected games."""
        ids = [g['id'] for g in games]
        if self._exec_db_update('UPDATE games SET steam_app_id = NULL WHERE id = ?', [(i,) for i in ids]):
            self._fetch_and_update_games_batch(ids)
            self.status_message.emit(f"Cleared AppIDs for {len(games)} games")

    def _clear_game_cache_data(self, games: list[dict]):
        """Debug: Clear cache data for selected games' AppIDs."""
        steam = self._init_steam_integration()
        if not steam:
            return
            
        unique_appids = set(g['steam_app_id'] for g in games if g.get('steam_app_id'))
        cleared_count = 0
        
        for app_id in unique_appids:
            try:
                steam.cache.clear_by_appid(app_id)
                cleared_count += 1
            except Exception as e:
                print(f"Failed to clear cache for {app_id}: {e}")
                
        self.status_message.emit(f"Cleared cache data for {cleared_count} AppIDs")

    def _show_single_context_menu(self, game: dict, position):
        """Show context menu for a single game."""
        menu = QMenu(self)
        game_id = game['id']  # Store ID for fresh data lookup
        
        # Check if Steam fetch is active to lock edit actions
        fetch_active = self.is_steam_fetch_active()
        lock_prefix = "🔒 " if fetch_active else ""

        # Copy submenu with multiple format options
        self._add_copy_submenu(menu, [game])

        menu.addSeparator()

        # Steam submenu (group other Steam-related actions together)
        if game.get('platform_type', '').lower() == 'steam':
            steam_menu = menu.addMenu("Steam")
            steam_menu.addAction("Open Steam Store Page", lambda: self._open_game_website(game))
            steam_menu.addSeparator()
            steam_menu.addAction("Fetch Data", lambda: self._fetch_steam_data([game]))
            steam_menu.addAction("Refresh Reviews", lambda: self._refresh_steam_reviews([game]))
            steam_menu.addAction("Refresh Cache", lambda: self._fetch_steam_data([game], force_refresh=True))

        # Quick Edit submenu comes after Steam in the grouped section
        # Show lock icon prefix when Steam fetch is active
        quick_menu = menu.addMenu(f"{lock_prefix}Quick Edit")
        if fetch_active:
            quick_menu.setEnabled(False)
            quick_menu.setToolTip("Locked - Steam fetch in progress")
        else:
            self._add_quick_edit_actions(quick_menu, game_id)

        # Advanced Edit - uses fresh data via game_id lookup
        advanced_action = menu.addAction(
            f"{lock_prefix}Advanced Edit",
            lambda gid=game_id: self._show_game_details(self._get_fresh_game(gid) or game)
        )
        if fetch_active:
            advanced_action.setEnabled(False)
            advanced_action.setToolTip("Locked - Steam fetch in progress")
        
        # Group separator before debug options
        menu.addSeparator()
        
        # Debug Cache
        self._add_debug_cache_menu(menu, [game])
        
        # Delete - uses fresh data via game_id lookup
        delete_action = menu.addAction(
            f"{lock_prefix}Delete Game",
            lambda gid=game_id: self._delete_game(self._get_fresh_game(gid) or game)
        )
        if fetch_active:
            delete_action.setEnabled(False)
            delete_action.setToolTip("Locked - Steam fetch in progress")
        
        # Connect dynamic unlock when fetch finishes while menu is open
        self._connect_menu_unlock(menu, quick_menu, advanced_action, delete_action, game_id=game_id)
        menu.exec_(position or self.cursor().pos())
    
    def _add_quick_edit_actions(self, menu: QMenu, game_or_id):
        """Add quick edit actions to menu for a single game.
        
        Args:
            menu: The QMenu to add actions to
            game_or_id: Either a game dict or game ID (int). If ID, fetches fresh data.
        """
        # Support both dict and ID for fresh data lookup
        if isinstance(game_or_id, int):
            game = self._get_fresh_game(game_or_id)
            if not game:
                return
            game_id = game_or_id
        else:
            game = game_or_id
            game_id = game['id']
        
        # Toggle used status - uses fresh data
        used_text = "Set as Unused" if game['is_used'] else "Set as Used"
        menu.addAction(used_text, lambda gid=game_id: self._toggle_used_status(self._get_fresh_game(gid)))
        
        # Toggle DLC - uses fresh data
        dlc_text = "Disable DLC" if game.get('dlc_enabled') else "Enable DLC"
        menu.addAction(dlc_text, lambda gid=game_id: self._toggle_game_field(self._get_fresh_game(gid), 'dlc_enabled'))
        
        # Toggle Deadline - uses fresh data
        deadline_text = "Disable Deadline" if game.get('deadline_enabled') else "Enable Deadline"
        menu.addAction(deadline_text, lambda gid=game_id: self._toggle_game_field(self._get_fresh_game(gid), 'deadline_enabled'))
        
        # Set Deadline Date
        menu.addSeparator()
        menu.addAction("Set Deadline Date...", lambda gid=game_id: self._set_deadline_date([self._get_fresh_game(gid)]))
    
    def _add_batch_quick_edit_actions(self, menu: QMenu, games_or_ids):
        """Add quick edit actions to menu for multiple games (batch mode).
        
        Args:
            menu: The QMenu to add actions to
            games_or_ids: Either a list of game dicts or a list of game IDs
        """
        # Support both list of dicts and list of IDs
        if games_or_ids and isinstance(games_or_ids[0], int):
            ids = games_or_ids
        else:
            ids = [g['id'] for g in games_or_ids]
        
        # Used submenu
        used_menu = menu.addMenu("Used")
        used_menu.addAction("Flip Used/Unused", lambda: self._batch_update_field(
            ids, 'UPDATE games SET is_used = NOT is_used WHERE id = ?', "Toggled used status"
        ))
        used_menu.addAction("Set All to Used", lambda: self._batch_update_field(
            ids, 'UPDATE games SET is_used = 1 WHERE id = ?', "Marked as used"
        ))
        used_menu.addAction("Set All to Unused", lambda: self._batch_update_field(
            ids, 'UPDATE games SET is_used = 0 WHERE id = ?', "Marked as unused"
        ))

        # DLC submenu
        dlc_menu = menu.addMenu("DLC")
        dlc_menu.addAction("Flip DLC Status", lambda: self._batch_update_field(
            ids, 'UPDATE games SET dlc_enabled = NOT dlc_enabled WHERE id = ?', "Toggled DLC status"
        ))
        dlc_menu.addAction("Enable DLC for All", lambda: self._batch_update_field(
            ids, 'UPDATE games SET dlc_enabled = 1 WHERE id = ?', "Enabled DLC"
        ))
        dlc_menu.addAction("Disable DLC for All", lambda: self._batch_update_field(
            ids, 'UPDATE games SET dlc_enabled = 0 WHERE id = ?', "Disabled DLC"
        ))

        # Deadline submenu
        deadline_menu = menu.addMenu("Deadline")
        deadline_menu.addAction("Flip Deadline Status", lambda: self._batch_update_field(
            ids, 'UPDATE games SET deadline_enabled = NOT deadline_enabled WHERE id = ?', "Toggled deadline status"
        ))
        deadline_menu.addAction("Enable Deadline for All", lambda: self._batch_update_field(
            ids, 'UPDATE games SET deadline_enabled = 1 WHERE id = ?', "Enabled deadline"
        ))
        deadline_menu.addAction("Disable Deadline for All", lambda: self._batch_update_field(
            ids, 'UPDATE games SET deadline_enabled = 0 WHERE id = ?', "Disabled deadline"
        ))
        deadline_menu.addSeparator()
        deadline_menu.addAction("Set Deadline Date...", lambda i=ids: self._set_deadline_date(self._get_fresh_games(i)))
    
    def _toggle_game_field(self, game: dict, field: str):
        """Toggle a boolean field on a game."""
        try:
            new_value = 0 if game.get(field) else 1
            self.db_manager._require_conn().cursor().execute(
                f'UPDATE games SET {field} = ? WHERE id = ?', (new_value, game['id'])
            )
            self.db_manager._require_conn().commit()
            self.db_manager._sync_encrypted_db()
            
            if self._fetch_and_update_game(game['id']):
                status = "enabled" if new_value else "disabled"
                field_name = field.replace('_enabled', '').replace('_', ' ').title()
                self.status_message.emit(f"{field_name} {status} for {game['title']}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update: {e}")
    
    def _set_deadline_date(self, games: list[dict]):
        """Set deadline date for one or more games."""
        from src.ui.dialogs.password_dialogs import DeadlineDateDialog
        
        dialog = DeadlineDateDialog(self)
        
        # Pre-populate if single game has deadline
        if len(games) == 1 and games[0].get('deadline_at'):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(str(games[0]['deadline_at']).replace('Z', '+00:00'))
                dialog._date_edit.setDate(QDate(dt.year, dt.month, dt.day))
            except Exception:
                pass
        
        if not dialog.exec_():
            return
        
        deadline_date = dialog.get_deadline_date()
        if not deadline_date:
            return
        
        deadline_str = deadline_date.toString("yyyy-MM-dd")
        ids = [g['id'] for g in games]
        
        if self._exec_db_update(
            'UPDATE games SET deadline_at = ?, deadline_enabled = 1 WHERE id = ?',
            [(deadline_str, gid) for gid in ids]
        ):
            self._fetch_and_update_games_batch(ids)
            self.status_message.emit(f"Set deadline to {deadline_str} for {len(games)} game(s)")

    def _show_batch_context_menu(self, games: list[dict], position):
        """Show context menu for multiple selected games."""
        menu = QMenu(self)
        count = len(games)
        game_ids = [g['id'] for g in games]  # Store IDs for fresh data lookup
        
        # Check if Steam fetch is active to lock edit actions
        fetch_active = self.is_steam_fetch_active()
        lock_prefix = "🔒 " if fetch_active else ""

        # Copy submenu with multiple format options
        self._add_copy_submenu(menu, games)

        # Open Steam Store Pages (only for Steam games) - moved into Steam submenu
        steam_games = [g for g in games if g.get('platform_type', '').lower() == 'steam']

        # Grouped section (separator) — Steam menu should be the first item here
        menu.addSeparator()

        # Fetch Steam Data (group Steam-related actions into a Steam submenu)
        if steam_games:
            steam_count = len(steam_games)
            steam_menu = menu.addMenu("Steam")
            # Store pages moved into Steam submenu
            steam_menu.addAction(f"Open Steam Store Pages ({steam_count})", lambda: self._open_batch_steam_pages(steam_games))
            steam_menu.addSeparator()
            steam_menu.addAction(f"Fetch Data ({steam_count})", lambda: self._fetch_steam_data(steam_games))
            steam_menu.addAction(f"Refresh Reviews ({steam_count})", lambda: self._refresh_steam_reviews(steam_games))
            steam_menu.addAction(f"Refresh Cache ({steam_count})", lambda: self._fetch_steam_data(steam_games, force_refresh=True))
        
        # Quick Edit submenu - show lock icon prefix when Steam fetch is active
        quick_menu = menu.addMenu(f"{lock_prefix}Quick Edit")
        if fetch_active:
            quick_menu.setEnabled(False)
            quick_menu.setToolTip("Locked - Steam fetch in progress")
        else:
            self._add_batch_quick_edit_actions(quick_menu, game_ids)

        # Advanced Edit - uses fresh data via game_ids lookup
        advanced_action = menu.addAction(
            f"{lock_prefix}Advanced Edit",
            lambda ids=game_ids: self._show_game_details(self._get_fresh_games(ids) or games)
        )
        if fetch_active:
            advanced_action.setEnabled(False)
            advanced_action.setToolTip("Locked - Steam fetch in progress")
        
        # Group separator before debug options
        menu.addSeparator()
        
        # Debug Cache
        self._add_debug_cache_menu(menu, games)

        # Delete - uses fresh data via game_ids lookup
        delete_action = menu.addAction(
            f"{lock_prefix}Delete {count} Games",
            lambda ids=game_ids: self._delete_games_batch(self._get_fresh_games(ids) or games)
        )
        if fetch_active:
            delete_action.setEnabled(False)
            delete_action.setToolTip("Locked - Steam fetch in progress")

        # Connect dynamic unlock when fetch finishes while menu is open
        self._connect_menu_unlock(menu, quick_menu, advanced_action, delete_action, game_ids=game_ids)
        menu.exec_(position or self.cursor().pos())
    
    def _batch_update_field(self, ids: list[int], sql: str, status_prefix: str):
        """Execute batch update and refresh affected games."""
        if self._exec_db_update(sql, [(i,) for i in ids]):
            self._fetch_and_update_games_batch(ids)
            self._update_title_count(len(self.games_data))
            self.status_message.emit(f"{status_prefix} for {len(ids)} games")
    
    def _delete_games_batch(self, games: list[dict]):
        """Delete multiple games with confirmation."""
        count = len(games)
        reply = QMessageBox.question(
            self, "Delete Selected Games",
            f"Are you sure you want to delete {count} selected games?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        ids = [g['id'] for g in games]
        if self._exec_db_update('DELETE FROM games WHERE id = ?', [(i,) for i in ids]):
            # Batch remove from cache and model
            self.games_data = [g for g in self.games_data if g['id'] not in ids]
            for gid in ids:
                self._list_model.remove_game_by_id(gid)
            
            self._refresh_platforms()
            self._update_empty_state()
            self._update_title_count(len(self.games_data))
            # Reload tags in case the last games with certain tags were deleted
            self.reload_tags()
            self.status_message.emit(f"Deleted {count} games")
            self.notify_success(f"Removed {count} games")

    # ============================================================
    # Keyboard Shortcuts
    # ============================================================

    def _get_selected_games(self) -> list[dict]:
        """Get list of games from current selection."""
        selected = self.list_view.selectionModel().selectedRows()
        return [g for idx in selected if (g := self._get_game_at_proxy_index(idx))]

    def _copy_selected_keys(self):
        """Copy keys of selected games to clipboard (Ctrl+C)."""
        if games := self._get_selected_games():
            self._copy_keys_to_clipboard([g.get('game_key', '') for g in games])

    def _edit_selected_games(self):
        """Edit selected games (Enter key)."""
        if games := self._get_selected_games():
            self._show_game_details(games if len(games) > 1 else games[0])

    def _delete_selected_games(self):
        """Delete selected games (Delete key)."""
        if games := self._get_selected_games():
            self._delete_games_batch(games)
    
    # ============================================================
    # Steam Integration
    # ============================================================
    
    def _init_steam_integration(self):
        """Initialize Steam integration instance."""
        try:
            return SteamIntegration(self.settings_manager.get_app_data_dir())
        except Exception as e:
            self.notify_error(f"Failed to initialize Steam integration: {e}")
            return None
    
    def _get_tag_mappings(self):
        """Get tag name to ID mapping and custom (non-Steam) tags list.

        Custom tags are tags with is_builtin=False in the database (i.e. tags
        that are not provided by Steam). Tags fetched from Steam sources are
        automatically marked as Steam tags (is_builtin = 1 in the DB).
        """
        all_tags = self.db_manager.get_tags()
        tag_name_to_id = {tag['name']: tag['id'] for tag in all_tags}
        # Custom tags are those that are NOT Steam-provided (user-created)
        custom_tags = [t['name'] for t in all_tags if not t.get('is_builtin', False)]
        return tag_name_to_id, custom_tags
    
    def is_steam_fetch_active(self) -> bool:
        """Check if any Steam fetch operation is currently active."""
        return len(self._active_steam_ops) > 0
    
    def _unlock_menu_items(self, items: dict) -> None:
        """Unlock menu items when Steam fetch finishes while menu is open."""
        try:
            if (qm := items.get('quick_menu')) and not qm.isEnabled():
                qm.setEnabled(True)
                qm.setTitle("Quick Edit")
                if qm.isEmpty():
                    if gid := items.get('game_id'):
                        self._add_quick_edit_actions(qm, gid)
                    elif gids := items.get('game_ids'):
                        self._add_batch_quick_edit_actions(qm, gids)
            if (aa := items.get('advanced_action')) and not aa.isEnabled():
                aa.setEnabled(True)
                aa.setText("Advanced Edit")
            if (da := items.get('delete_action')) and not da.isEnabled():
                da.setEnabled(True)
                da.setText(f"Delete {len(items['game_ids'])} Games" if items.get('game_ids') else "Delete Game")
        except RuntimeError:
            pass
    
    def _connect_menu_unlock(self, menu, quick_menu, advanced_action, delete_action, game_id=None, game_ids=None):
        """Connect signal to unlock menu items when fetch finishes, auto-disconnect on menu close."""
        items = {'quick_menu': quick_menu, 'advanced_action': advanced_action, 
                 'delete_action': delete_action, 'game_id': game_id, 'game_ids': game_ids}
        handler = lambda: self._unlock_menu_items(items)
        self.steam_fetch_finished.connect(handler)
        menu.aboutToHide.connect(lambda: self.steam_fetch_finished.disconnect(handler) if handler else None)
    
    def _setup_steam_op(self, name: str, worker, thread, on_game_updated, on_complete, on_error, on_progress):
        """Setup Steam worker with signal connections and start thread."""
        # Track this operation as active
        was_empty = len(self._active_steam_ops) == 0
        self._active_steam_ops.add(name)
        if was_empty:
            self.steam_fetch_started.emit()
        
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # Use QueuedConnection for all cross-thread signals to ensure they run in main thread event loop
        # This prevents recursive repaint issues when UI updates are triggered during scroll
        if hasattr(worker, 'games_updated'):
            worker.games_updated.connect(on_game_updated, Qt.ConnectionType.QueuedConnection)
        elif hasattr(worker, 'game_updated'):
            worker.game_updated.connect(on_game_updated, Qt.ConnectionType.QueuedConnection)
        if hasattr(worker, 'game_refreshed'):
            worker.game_refreshed.connect(on_game_updated, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(on_complete, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(thread.quit)
        worker.progress.connect(on_progress, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(lambda: self._cleanup_steam_op(name))
    
    def _cleanup_steam_op(self, name: str):
        """Clean up Steam operation thread and context."""
        for suffix in ('_worker', '_thread', '_context'):
            attr = f'_steam_{name}{suffix}'
            if obj := getattr(self, attr, None):
                if suffix != '_context':
                    obj.deleteLater()
                delattr(self, attr)
        
        # Remove from active operations tracking
        self._active_steam_ops.discard(name)
        if len(self._active_steam_ops) == 0:
            self.steam_fetch_finished.emit()
    
    def _start_steam_batch_op(self, games: list[dict], op_name: str, worker_factory, msg: str, 
                                on_updated, on_complete, on_error, on_progress, cancel_method):
        """Generic Steam batch operation starter."""
        steam_games = [g for g in games if g.get('platform_type', '').lower() == 'steam']
        if not steam_games:
            self.notify_warning("No Steam games selected")
            return
        steam = self._init_steam_integration()
        if not steam:
            return
        
        tag_name_to_id, custom_tags = self._get_tag_mappings()
        ctx = {'tag_name_to_id': tag_name_to_id, 'steam': steam, 'custom_tags': custom_tags}
        setattr(self, f'_steam_{op_name}_context', ctx)
        
        thread = QThread()
        worker = worker_factory(steam, steam_games, custom_tags)
        setattr(self, f'_steam_{op_name}_thread', thread)
        setattr(self, f'_steam_{op_name}_worker', worker)
        
        self._setup_steam_op(op_name, worker, thread, on_updated, on_complete, on_error, on_progress)
        
        count = len(steam_games)
        if nm := self.notification_manager:
            notif = nm.show_steam_fetch(msg, total_games=count)
            notif.cancel_requested.connect(cancel_method)
            ctx['notification'] = notif
        
        thread.start()
        self.status_message.emit(f"{msg} for {count} game{'s' if count > 1 else ''}...")
    
    def _fetch_steam_data(self, games: list[dict], force_refresh: bool = False):
        """Fetch missing Steam data (AppID, tags, images) for selected games in background."""
        msg = "Refreshing Steam cache" if force_refresh else "Fetching Steam data"
        self._start_steam_batch_op(
            games, 'batch',
            lambda s, g, t: s.create_batch_fetch_worker(games=g, fetch_appid=True, fetch_tags=True, 
                fetch_image=True, fetch_reviews=True, force_tags=True, custom_tags=t, force_fresh_search=force_refresh),
            msg,
            self._on_steam_game_updated, self._on_batch_fetch_complete,
            lambda m: self._handle_steam_error('batch', f"Steam fetch failed: {m}"),
            self._on_batch_progress,  # Use proper slot method instead of lambda
            self._cancel_steam_op
        )
    
    def _cancel_steam_op(self):
        """Cancel active Steam batch operation."""
        for name in ('batch', 'reviews', 'batch_refresh'):
            if worker := getattr(self, f'_steam_{name}_worker', None):
                worker.cancel()
                self.status_message.emit("Cancelling Steam operation...")
                return
    
    def _merge_tags(self, game: dict, result: dict, tag_name_to_id: dict) -> list[int]:
        """Merge fetched and existing tags, preserving custom tags. Returns tag IDs."""
        fetched = result.get('fetched', {})
        current_tags = [t.strip() for t in (game.get('tags') or '').split(',') if t.strip()]
        ignored = SteamIntegration.IGNORED_TAGS
        
        if fetched.get('tags') and (fetched_tags := result.get('tags')):
            tag_name_to_id.update(self.db_manager.get_or_create_tags(fetched_tags, is_builtin=True))
            all_tags = {t['name']: t for t in self.db_manager.get_tags()}
            merged = set(fetched_tags)
            merged.update(t for t in current_tags if t in all_tags and not all_tags[t].get('is_builtin', False) and t.lower() not in ignored)
        else:
            merged = {t for t in current_tags if t.lower() not in ignored}
        return [tag_name_to_id[n] for n in merged if n in tag_name_to_id]
    
    def _on_steam_game_updated(self, results):
        """Handle game updates from Steam worker (single or batch)."""
        # Normalize to list
        if isinstance(results, dict):
            results = [results]
            
        updated_ids = []
        
        for result in results:
            game = result.get('game') or (result.get('affected_games') or [None])[0]
            if not game:
                continue
            
            # Find the active context
            for name in ('batch', 'reviews', 'batch_refresh'):
                if ctx := self._get_steam_ctx(name):
                    break
            else:
                ctx = {}
            
            tag_name_to_id = ctx.get('tag_name_to_id', {})
            fetched = result.get('fetched', {})
            
            # Determine DLC status: use fetched is_dlc if available, otherwise keep current
            if fetched.get('is_dlc'):
                dlc_enabled = result.get('is_dlc', False)
            else:
                dlc_enabled = game.get('dlc_enabled', False)
            
            try:
                new_tag_ids = self._merge_tags(game, result, tag_name_to_id)
                self.db_manager.update_game(
                    game_id=game['id'], title=game['title'], game_key=game['game_key'],
                    platform_type=game['platform_type'], notes=game.get('notes', ''),
                    is_used=game.get('is_used', False), tag_ids=new_tag_ids,
                    image_path=result.get('image_path') if fetched.get('image') else game.get('image_path'),
                    deadline_enabled=game.get('deadline_enabled', False), deadline_at=game.get('deadline_at'),
                    dlc_enabled=dlc_enabled,
                    steam_app_id=result.get('app_id') if fetched.get('app_id') else game.get('steam_app_id'),
                    steam_review_score=result.get('review_score') if fetched.get('reviews') else game.get('steam_review_score'),
                    steam_review_count=result.get('review_count') if fetched.get('reviews') else game.get('steam_review_count')
                )
                updated_ids.append(game['id'])
            except Exception as e:
                print(f"[Steam] Error updating game {game.get('title')}: {e}")
        
        if updated_ids:
            self._fetch_and_update_games_batch(updated_ids)
    
    def _on_batch_fetch_complete(self, summary: dict):
        """Handle batch fetch completion."""
        self._complete_steam_op('batch', summary, "Fetched Steam data")
        if not summary.get('cancelled') and summary.get('fetched_count', 0) == 0 and summary.get('failed_count', 0) == 0:
            self.status_message.emit("All selected games already have complete data")
    
    def _open_game_website(self, game: dict):
        """Open the Steam store page for a game in the default browser."""
        app_id, title = game.get('steam_app_id'), game.get('title', '')
        
        if steam := self._init_steam_integration():
            if url := steam.get_steam_store_url(app_id=app_id, title=title):
                webbrowser.open(url)
                self.status_message.emit(f"Opened Steam store page for {title}")
            else:
                self.notify_warning("Could not determine Steam store URL")

    def _open_batch_steam_pages(self, games: list[dict]):
        """Open Steam store pages for multiple games."""
        if len(games) > 10:
            reply = QMessageBox.question(
                self, "Open Multiple Pages",
                f"You are about to open {len(games)} browser tabs. Are you sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        for game in games:
            self._open_game_website(game)
    
    def _refresh_steam_reviews(self, games: list[dict]):
        """Refresh Steam review data for selected games (always fetches fresh, deduplicates by AppID)."""
        steam_games = [g for g in games if g.get('platform_type', '').lower() == 'steam']
        if not steam_games:
            self.notify_warning("No Steam games selected")
            return
        steam = self._init_steam_integration()
        if not steam:
            return
        
        tag_name_to_id, _ = self._get_tag_mappings()
        self._steam_reviews_context = {'tag_name_to_id': tag_name_to_id}
        self._steam_reviews_thread = QThread()
        self._steam_reviews_worker = steam.create_batch_reviews_worker(games=steam_games)
        
        self._setup_steam_op('reviews', self._steam_reviews_worker, self._steam_reviews_thread,
            self._on_reviews_game_refreshed, self._on_reviews_complete,
            lambda m: self._handle_steam_error('reviews', f"Review fetch failed: {m}"),
            self._on_reviews_progress)  # Use proper slot method instead of lambda
        
        # Count unique AppIDs for accurate progress
        unique_appids = len(set(g.get('steam_app_id') for g in steam_games if g.get('steam_app_id')))
        
        if nm := self.notification_manager:
            notif = nm.show_steam_fetch(f"Refreshing reviews...", total_games=unique_appids or len(steam_games))
            notif.cancel_requested.connect(self._cancel_steam_op)
            self._steam_reviews_context['notification'] = notif
        
        self._steam_reviews_thread.start()
        self.status_message.emit(f"Refreshing reviews for {len(steam_games)} game(s)...")
    
    def _on_reviews_game_refreshed(self, result: dict):
        """Handle individual AppID review refresh - updates ALL games in DB with that AppID."""
        ctx = self._get_steam_ctx('reviews')
        tag_name_to_id = ctx.get('tag_name_to_id', {})
        app_id = result.get('app_id')
        
        if not app_id:
            return
        
        # Get ALL games with this AppID from the database, not just selected ones
        all_games_with_appid = self.db_manager.get_games_by_steam_app_id(app_id)
        updated_ids = []
        
        for game in all_games_with_appid:
            try:
                # Keep existing tags
                current_tags = [t.strip() for t in (game.get('tags') or '').split(',') if t.strip()]
                tag_ids = [tag_name_to_id[n] for n in current_tags if n in tag_name_to_id]
                
                self.db_manager.update_game(
                    game_id=game['id'], title=game['title'], game_key=game['game_key'],
                    platform_type=game['platform_type'], notes=game.get('notes', ''),
                    is_used=game.get('is_used', False), tag_ids=tag_ids,
                    image_path=game.get('image_path'),
                    deadline_enabled=game.get('deadline_enabled', False), deadline_at=game.get('deadline_at'),
                    dlc_enabled=game.get('dlc_enabled', False),
                    steam_app_id=app_id,
                    steam_review_score=result.get('review_score'),
                    steam_review_count=result.get('review_count')
                )
                updated_ids.append(game['id'])
            except Exception as e:
                print(f"[Steam] Error updating reviews for {game.get('title')}: {e}")
        
        if updated_ids:
            self._fetch_and_update_games_batch(updated_ids)
    
    def _on_reviews_complete(self, summary: dict):
        """Handle reviews refresh completion."""
        self._complete_steam_op('reviews', summary, "Refreshed reviews", count_key='refreshed_count')
    
    def _refresh_steam_cache(self, game: dict):
        """Force refresh Steam cache for a game and update all games with same AppID."""
        app_id = game.get('steam_app_id')
        if not app_id:
            self.notify_warning("Game has no Steam AppID")
            return
        steam = self._init_steam_integration()
        if not steam:
            return
        
        tag_name_to_id, custom_tags = self._get_tag_mappings()
        self._steam_refresh_context = {'tag_name_to_id': tag_name_to_id, 'app_id': app_id}
        self._steam_refresh_thread = QThread()
        self._steam_refresh_worker = steam.create_cache_refresh_worker(app_id=app_id, title=game.get('title'), custom_tags=custom_tags)
        self._steam_refresh_worker.moveToThread(self._steam_refresh_thread)
        self._steam_refresh_thread.started.connect(self._steam_refresh_worker.run)
        # Use QueuedConnection for cross-thread signals to prevent recursive repaint
        self._steam_refresh_worker.finished.connect(self._on_single_cache_refresh_complete, Qt.ConnectionType.QueuedConnection)
        self._steam_refresh_worker.finished.connect(self._steam_refresh_thread.quit)
        self._steam_refresh_worker.error.connect(lambda m: self._handle_steam_error('refresh', f"Cache refresh failed: {m}"), Qt.ConnectionType.QueuedConnection)
        self._steam_refresh_worker.error.connect(self._steam_refresh_thread.quit)
        self._steam_refresh_thread.finished.connect(lambda: self._cleanup_steam_op('refresh'))
        
        if nm := self.notification_manager:
            self._steam_refresh_context['notification'] = nm.show_steam_fetch(f"Refreshing cache for {game.get('title', 'game')}...", total_games=1)
        self._steam_refresh_thread.start()
        self.status_message.emit(f"Refreshing Steam cache for AppID {app_id}...")
    
    def _on_single_cache_refresh_complete(self, result: dict):
        """Handle single cache refresh completion."""
        ctx = self._get_steam_ctx('refresh')
        tag_name_to_id, app_id = ctx.get('tag_name_to_id', {}), ctx.get('app_id')
        if not app_id:
            return
        updated = 0
        fetched = result.get('fetched', {})
        
        # Determine DLC status: use fetched is_dlc if available
        dlc_enabled = result.get('is_dlc', False) if fetched.get('is_dlc') else None
        
        updated_ids = []
        for game in self.db_manager.get_games_by_steam_app_id(app_id):
            try:
                # Add fetched flag wrapper to reuse _merge_tags
                wrapped = {'tags': result.get('tags', []), 'fetched': {'tags': bool(result.get('tags'))}}
                new_tag_ids = self._merge_tags(game, wrapped, tag_name_to_id)
                
                # Use fetched DLC status if available, otherwise keep existing
                game_dlc_enabled = dlc_enabled if dlc_enabled is not None else game.get('dlc_enabled', False)
                
                self.db_manager.update_game(
                    game_id=game['id'], title=game['title'], game_key=game['game_key'],
                    platform_type=game['platform_type'], notes=game.get('notes', ''),
                    is_used=game.get('is_used', False), tag_ids=new_tag_ids,
                    image_path=result.get('image_path') or game.get('image_path'),
                    deadline_enabled=game.get('deadline_enabled', False), deadline_at=game.get('deadline_at'),
                    dlc_enabled=game_dlc_enabled, steam_app_id=app_id,
                    steam_review_score=result.get('review_score'), steam_review_count=result.get('review_count')
                )
                updated_ids.append(game['id'])
                updated += 1
            except Exception as e:
                print(f"[Steam] Error updating game {game.get('title')}: {e}")
        
        if updated_ids:
            self._fetch_and_update_games_batch(updated_ids)

        if (notif := ctx.get('notification')) and hasattr(notif, 'set_completed'):
            notif.set_completed(updated, 0)
        self.reload_tags()
        msg = f"Refreshed cache and updated {updated} game(s)" if updated else "Cache refreshed but no games were updated"
        (self.notify_success if updated else self.notify_warning)(msg)
        self.status_message.emit(msg)
    
    def _refresh_steam_cache_batch(self, games: list[dict]):
        """Force refresh Steam cache for multiple games, deduplicating by AppID."""
        games_with_appid = [g for g in games if g.get('steam_app_id')]
        if not games_with_appid:
            self.notify_warning("No games with Steam AppID to refresh")
            return
        
        unique_appids = set(g['steam_app_id'] for g in games_with_appid)
        steam = self._init_steam_integration()
        if not steam:
            return
        
        tag_name_to_id, custom_tags = self._get_tag_mappings()
        self._steam_batch_refresh_context = {'tag_name_to_id': tag_name_to_id, 'custom_tags': custom_tags}
        self._steam_batch_refresh_thread = QThread()
        self._steam_batch_refresh_worker = steam.create_batch_cache_refresh_worker(games=games_with_appid, custom_tags=custom_tags)
        
        self._setup_steam_op('batch_refresh', self._steam_batch_refresh_worker, self._steam_batch_refresh_thread,
            self._on_batch_cache_game_refreshed, self._on_batch_cache_refresh_complete,
            lambda m: self._handle_steam_error('batch_refresh', f"Batch cache refresh failed: {m}"),
            lambda t, c, tot: self._update_steam_progress('batch_refresh', t, c, tot))
        
        if nm := self.notification_manager:
            notif = nm.show_steam_fetch(f"Refreshing cache for {len(unique_appids)} unique game(s)...", total_games=len(unique_appids))
            notif.cancel_requested.connect(self._cancel_steam_op)
            self._steam_batch_refresh_context['notification'] = notif
        
        self._steam_batch_refresh_thread.start()
        self.status_message.emit(f"Refreshing Steam cache for {len(unique_appids)} unique AppID(s) ({len(games_with_appid)} games selected)...")
    
    def _on_batch_cache_game_refreshed(self, result: dict):
        """Handle individual game cache refresh in batch operation."""
        ctx = self._get_steam_ctx('batch_refresh')
        tag_name_to_id = ctx.get('tag_name_to_id', {})
        if not (app_id := result.get('app_id')):
            return
        tags_before = set(tag_name_to_id.keys())
        fetched = result.get('fetched', {})
        
        # Determine DLC status: use fetched is_dlc if available
        dlc_enabled = result.get('is_dlc', False) if fetched.get('is_dlc') else None
        
        for game in result.get('affected_games', []):
            try:
                wrapped = {'tags': result.get('tags', []), 'fetched': {'tags': bool(result.get('tags'))}}
                new_tag_ids = self._merge_tags(game, wrapped, tag_name_to_id)
                
                # Use fetched DLC status if available, otherwise keep existing
                game_dlc_enabled = dlc_enabled if dlc_enabled is not None else game.get('dlc_enabled', False)
                
                self.db_manager.update_game(
                    game_id=game['id'], title=game['title'], game_key=game['game_key'],
                    platform_type=game['platform_type'], notes=game.get('notes', ''),
                    is_used=game.get('is_used', False), tag_ids=new_tag_ids,
                    image_path=result.get('image_path') or game.get('image_path'),
                    deadline_enabled=game.get('deadline_enabled', False), deadline_at=game.get('deadline_at'),
                    dlc_enabled=game_dlc_enabled, steam_app_id=game.get('steam_app_id'),
                    steam_review_score=result.get('review_score'), steam_review_count=result.get('review_count')
                )
                self._fetch_and_update_game(game['id'])
            except Exception as e:
                print(f"[Steam] Error updating game {game.get('title')}: {e}")
        if result.get('tags') and set(tag_name_to_id.keys()) != tags_before:
            self.reload_tags()
    
    def _on_batch_cache_refresh_complete(self, summary: dict):
        """Handle batch cache refresh completion."""
        ctx = self._get_steam_ctx('batch_refresh')
        count, failed, cancelled, total = (summary.get(k, 0) for k in ('refreshed_count', 'failed_count', 'cancelled', 'total_games'))
        if (notif := ctx.get('notification')) and hasattr(notif, 'set_completed'):
            notif.set_completed(count, failed)
        if cancelled:
            self.notify_warning(f"Cache refresh cancelled ({count} completed)")
        elif failed > 0:
            self.notify_warning(f"Refreshed {count} game(s), {failed} failed")
        elif count > 0:
            self.notify_success(f"Refreshed cache for {count} unique game(s) (updated {total} entries)")
        else:
            self.notify_warning("No games were refreshed")
        self.reload_tags()
        self.status_message.emit(f"Batch cache refresh complete: {count} refreshed, {failed} failed")
    
    # ============================================================
    # Game Actions
    # ============================================================
    
    def _handle_steam_error(self, name: str, msg: str):
        """Handle Steam fetch error with notification."""
        if (notif := self._get_steam_ctx(name).get('notification')) and hasattr(notif, 'set_completed'):
            notif.set_completed(0, 1)
        self.notify_error(msg)
    
    # ============================================================
    # Copy Actions (Context Menu)
    # ============================================================
    
    def _add_copy_submenu(self, menu: QMenu, games: list[dict]):
        """Add copy submenu with multiple format options to the context menu."""
        count = len(games)
        is_single = count == 1
        
        copy_menu = menu.addMenu("Copy" if is_single else f"Copy ({count})")
        
        # Key only
        key_label = "Key Only" if is_single else f"Keys Only ({count})"
        copy_menu.addAction(key_label, lambda: self._copy_keys_only(games))
        
        # Title with Key
        title_key_label = "Title with Key" if is_single else f"Titles with Keys ({count})"
        copy_menu.addAction(title_key_label, lambda: self._copy_title_with_key(games))
        
        copy_menu.addSeparator()
        
        # Discord spoiler format
        discord_label = "Discord Spoiler" if is_single else f"Discord Spoilers ({count})"
        copy_menu.addAction(discord_label, lambda: self._copy_discord_spoiler(games))
        
        # Steam Redemption URL (only for Steam platform games) — submenu for link-only or title+link
        steam_games = [g for g in games if g.get('platform_type', '').lower() == 'steam']
        if steam_games:
            steam_count = len(steam_games)
            # Create a submenu so users can choose to copy only the link or the title with the link
            label = "Steam Redemption Link" if is_single else f"Steam Redemption Links ({steam_count})"
            steam_sub = copy_menu.addMenu(label)
            # Link Only
            link_only_label = "Link Only" if is_single else f"Links Only ({steam_count})"
            steam_sub.addAction(link_only_label, lambda: self._copy_steam_redemption_url(steam_games, include_title=False))
            # Title and Link
            title_and_link_label = "Title and Link" if is_single else f"Titles and Links ({steam_count})"
            steam_sub.addAction(title_and_link_label, lambda: self._copy_steam_redemption_url(steam_games, include_title=True))
    
    def _copy_keys_only(self, games: list[dict]):
        """Copy only game keys to clipboard."""
        keys = [g.get('game_key', '') for g in games if g.get('game_key')]
        if not keys:
            self.notify_warning("No keys to copy")
            return
        QApplication.clipboard().setText('\n'.join(keys))
        msg = f"Copied {len(keys)} key{'s' if len(keys) > 1 else ''}"
        self.status_message.emit(msg)
        self.notify_success(msg)
    
    def _copy_title_with_key(self, games: list[dict]):
        """Copy game titles with their keys to clipboard."""
        lines = []
        for g in games:
            title = g.get('title', 'Unknown')
            key = g.get('game_key', '')
            if key:
                lines.append(f"{title}: {key}")
        if not lines:
            self.notify_warning("No keys to copy")
            return
        QApplication.clipboard().setText('\n'.join(lines))
        msg = f"Copied {len(lines)} title{'s' if len(lines) > 1 else ''} with key{'s' if len(lines) > 1 else ''}"
        self.status_message.emit(msg)
        self.notify_success(msg)
    
    def _copy_discord_spoiler(self, games: list[dict]):
        """Copy game titles with keys in Discord spoiler format."""
        lines = []
        for g in games:
            title = g.get('title', 'Unknown')
            key = g.get('game_key', '')
            if key:
                # Discord spoiler format: Title: ||KEY||
                lines.append(f"{title}: ||{key}||")
        if not lines:
            self.notify_warning("No keys to copy")
            return
        QApplication.clipboard().setText('\n'.join(lines))
        msg = f"Copied {len(lines)} Discord spoiler{'s' if len(lines) > 1 else ''}"
        self.status_message.emit(msg)
        self.notify_success(msg)
    
    def _copy_steam_redemption_url(self, games: list[dict], include_title: bool = True):
        """Copy Steam redemption URLs with keys pre-filled.

        include_title: When True, copy "Title: URL" lines; when False, copy only the URL(s).
        """
        lines = []
        for g in games:
            key = g.get('game_key', '')
            title = g.get('title', 'Unknown')
            if key and g.get('platform_type', '').lower() == 'steam':
                # Steam key redemption URL with key pre-filled
                url = f"https://store.steampowered.com/account/registerkey?key={key}"
                if include_title:
                    lines.append(f"{title}: {url}")
                else:
                    lines.append(url)
        if not lines:
            self.notify_warning("No Steam keys to copy")
            return
        QApplication.clipboard().setText('\n'.join(lines))
        if include_title:
            msg = f"Copied {len(lines)} Steam redemption URL{'s' if len(lines) > 1 else ''}"
        else:
            msg = f"Copied {len(lines)} Steam redemption link{'s' if len(lines) > 1 else ''}"
        self.status_message.emit(msg)
        self.notify_success(msg)
    
    def _copy_key(self, game: dict):
        """Copy game key to clipboard (legacy single-game method)."""
        if not game:
            return
        QApplication.clipboard().setText(game.get('game_key', ''))
        self.notify_success(f"Copied key for {game.get('title', 'Game')}")
    
    def _toggle_used_status(self, game: dict):
        """Toggle game used status."""
        try:
            if self.db_manager.toggle_game_used_status(game['id']):
                if self._fetch_and_update_game(game['id']):
                    updated = self.db_manager.get_game_by_id(game['id'])
                    status = "used" if updated and updated.get('is_used') else "unused"
                    self.status_message.emit(f"Game marked as {status}")
            else:
                QMessageBox.critical(self, "Error", "Failed to update game status")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update game status: {e}")
    
    def _delete_game(self, game: dict):
        """Delete a single game with confirmation."""
        reply = QMessageBox.question(
            self, "Delete Game",
            f"Are you sure you want to delete '{game['title']}'?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            if self.db_manager.delete_game(game['id']):
                self.status_message.emit(f"Game '{game['title']}' deleted")
                self.notify_success(f"Removed '{game['title']}'")
                self._remove_game_by_id(game['id'])
                self._update_title_count(len(self.games_data))
                # Reload tags in case the last game with a tag was deleted
                self.reload_tags()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete game")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete game: {e}")
    
    def get_status_message(self) -> str:
        """Get status message for this page."""
        visible = self._proxy_model.rowCount()
        total = len(self.games_data)
        return f"Viewing {visible} of {total} games"
