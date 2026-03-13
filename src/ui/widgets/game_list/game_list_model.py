from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex, QRunnable, QThreadPool, Signal, QObject, Slot, QTimer
from PySide6.QtGui import QPixmap, QColor, QImage


class _PoolSignals(QObject):
    """Signals object used by QRunnable tasks to notify the model when a pixmap is ready."""
    loaded = Signal(str, object)  # Emits (path, QImage)


# Cache size - store images at a resolution that works well for both grid and list views
# This should be at or above the maximum display size to avoid upscaling artifacts
# Grid cards are 280x320, list card images are 155x110
# Original images are 460x215, so we keep them at that size for quality
CACHE_WIDTH = 460
CACHE_HEIGHT = 215


class _LoadTask(QRunnable):
    def __init__(self, path: str, signals: _PoolSignals):
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        img = None
        try:
            # Use QImage in background thread (QPixmap is not thread-safe)
            i = QImage(self.path)
            if not i.isNull():
                # Keep at original size or cache size - don't downscale too aggressively
                # This preserves quality and avoids expensive upscaling during paint
                if i.width() > CACHE_WIDTH * 1.5 or i.height() > CACHE_HEIGHT * 1.5:
                    # Only downscale if significantly larger than needed
                    img = i.scaled(CACHE_WIDTH, CACHE_HEIGHT, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                else:
                    img = i
        except Exception:
            img = None
        # emit result (queued connection will deliver to model thread)
        try:
            self.signals.loaded.emit(self.path, img)
        except Exception:
            pass


class GameListModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    KeyRole = Qt.UserRole + 2
    PlatformRole = Qt.UserRole + 3
    TagsRole = Qt.UserRole + 4
    PixmapRole = Qt.UserRole + 5
    IsUsedRole = Qt.UserRole + 6
    DeadlineEnabledRole = Qt.UserRole + 7
    DeadlineAtRole = Qt.UserRole + 8
    DlcEnabledRole = Qt.UserRole + 9
    SteamReviewScoreRole = Qt.UserRole + 10

    # Signal used to request loading of an image in the worker thread
    request_load = Signal(str)

    def __init__(self, games=None, parent=None):
        super().__init__(parent)
        self._games = list(games or [])
        self._pix_cache = {}  # path -> QPixmap
        self._loading = set()
        # placeholder pixmap used until image is loaded
        placeholder = QPixmap(160, 90)
        placeholder.fill(QColor(200, 200, 200))
        self._placeholder = placeholder
        # Setup a thread pool and a signals helper for tasks
        self._pool = QThreadPool.globalInstance()
        self._pool_signals = _PoolSignals()
        self._pool_signals.loaded.connect(self._on_pix_loaded)
        
        # Coalescing timer for pixmap updates - batches rapid image loads into single view updates
        # This prevents recursive repaint when scrolling while images are loading
        self._pending_pixmap_paths = set()
        self._pixmap_update_timer = QTimer()
        self._pixmap_update_timer.setInterval(16)  # ~60fps, coalesce updates within one frame
        self._pixmap_update_timer.setSingleShot(True)
        self._pixmap_update_timer.timeout.connect(self._flush_pixmap_updates)

    def rowCount(self, parent=QModelIndex()):
        return len(self._games)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        g = self._games[index.row()]
        if role == GameListModel.TitleRole:
            return g.get('title', '')
        if role == GameListModel.KeyRole:
            return g.get('game_key', '')
        if role == GameListModel.PlatformRole:
            return g.get('platform_type', '')
        if role == GameListModel.TagsRole:
            return g.get('tags', '')
        if role == GameListModel.PixmapRole:
            path = g.get('image_path')
            if not path:
                return None
            pix = self._pix_cache.get(path)
            if pix is None:
                # Request asynchronous load and return placeholder
                if path not in self._loading:
                    self._loading.add(path)
                    try:
                        task = _LoadTask(path, self._pool_signals)
                        self._pool.start(task)
                    except Exception:
                        # fallback synchronous load if pool fails
                        try:
                            p = QPixmap(path)
                            if not p.isNull():
                                # Keep at original size or reasonable cache size
                                if p.width() > CACHE_WIDTH * 1.5 or p.height() > CACHE_HEIGHT * 1.5:
                                    p = p.scaled(CACHE_WIDTH, CACHE_HEIGHT, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                            else:
                                p = None
                        except Exception:
                            p = None
                        self._pix_cache[path] = p
                        if p is None:
                            return self._placeholder
                return self._placeholder
            return pix
        if role == GameListModel.IsUsedRole:
            return bool(g.get('is_used', False))
        if role == GameListModel.DeadlineEnabledRole:
            return bool(g.get('deadline_enabled', False))
        if role == GameListModel.DeadlineAtRole:
            return g.get('deadline_at')
        if role == GameListModel.DlcEnabledRole:
            return bool(g.get('dlc_enabled', False))
        if role == GameListModel.SteamReviewScoreRole:
            return g.get('steam_review_score')
        return None

    def _on_pix_loaded(self, path: str, img: object):
        try:
            # Convert QImage to QPixmap on the main thread
            pix = None
            if isinstance(img, QImage) and not img.isNull():
                pix = QPixmap.fromImage(img)
            
            if pix:
                self._pix_cache[path] = pix
                self._loading.discard(path)
                # Queue path for batched dataChanged emission
                # This prevents recursive repaint when scrolling while images load
                self._pending_pixmap_paths.add(path)
                if not self._pixmap_update_timer.isActive():
                    self._pixmap_update_timer.start()
            else:
                # Failed to load or invalid image
                self._loading.discard(path)
        except Exception:
            self._loading.discard(path)
    
    def _flush_pixmap_updates(self):
        """Emit batched dataChanged for all pending pixmap paths.
        
        This coalesces multiple rapid image loads into a single view update,
        preventing recursive repaint issues during scroll.
        """
        if not self._pending_pixmap_paths:
            return
        
        paths = self._pending_pixmap_paths.copy()
        self._pending_pixmap_paths.clear()
        
        # Find all rows that use any of these paths
        affected_rows = []
        for row, game in enumerate(self._games):
            if game.get('image_path') in paths:
                affected_rows.append(row)
        
        # Emit a single ranged dataChanged for all affected rows
        if affected_rows:
            min_row = min(affected_rows)
            max_row = max(affected_rows)
            self.dataChanged.emit(
                self.index(min_row), 
                self.index(max_row), 
                [GameListModel.PixmapRole]
            )

    def roleNames(self):
        return {
            GameListModel.TitleRole: b"title",
            GameListModel.KeyRole: b"key",
            GameListModel.PlatformRole: b"platform",
            GameListModel.TagsRole: b"tags",
            GameListModel.PixmapRole: b"pixmap",
            GameListModel.IsUsedRole: b"is_used",
            GameListModel.DeadlineEnabledRole: b"deadline_enabled",
            GameListModel.DeadlineAtRole: b"deadline_at",
            GameListModel.DlcEnabledRole: b"dlc_enabled",
            GameListModel.SteamReviewScoreRole: b"steam_review_score",
        }

    def set_games(self, games):
        self.beginResetModel()
        self._games = list(games or [])
        # clear cache for removed/changed images
        self._pix_cache = {}
        self._loading.clear()
        self.endResetModel()

    def game_at(self, row):
        if 0 <= row < len(self._games):
            return self._games[row]
        return None

    # -----------------------------
    # Incremental update helpers
    # -----------------------------
    def find_row_by_id(self, game_id: int) -> int:
        try:
            for i, g in enumerate(self._games):
                if int(g.get('id')) == int(game_id):
                    return i
        except Exception:
            pass
        return -1

    def remove_game_by_id(self, game_id: int) -> int:
        """Remove a single game by id. Returns removed row or -1 if not found."""
        row = self.find_row_by_id(game_id)
        if row < 0:
            return -1
        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._games.pop(row)
        self.endRemoveRows()
        # clean pix cache entry for removed image
        try:
            p = removed.get('image_path')
            if p and p in self._pix_cache:
                self._pix_cache.pop(p, None)
        except Exception:
            pass
        return row

    def add_game(self, game: dict, row: int | None = None) -> int:
        """Insert a single game. If row is None, append to the end. Returns inserted row."""
        if row is None:
            row = len(self._games)
        row = max(0, min(row, len(self._games)))
        self.beginInsertRows(QModelIndex(), row, row)
        self._games.insert(row, dict(game))
        self.endInsertRows()
        return row

    def update_game_by_id(self, updated: dict, emit: bool = True) -> int:
        """Update a game's fields in-place by id and optionally emit dataChanged for affected roles.

        Args:
            updated: Dict with game data including 'id' key
            emit: If True (default), emit dataChanged signal. Set False when batching updates.

        Returns the row index updated, or -1 if not found.
        """
        try:
            gid = int(updated.get('id'))
        except Exception:
            return -1
        row = self.find_row_by_id(gid)
        if row < 0:
            return -1
        old = self._games[row]
        self._games[row] = dict(old | updated)

        # determine changed roles
        changed_roles = []
        def changed(k):
            return (old.get(k) != self._games[row].get(k))
        if changed('title'):
            changed_roles.append(GameListModel.TitleRole)
        if changed('game_key'):
            changed_roles.append(GameListModel.KeyRole)
        if changed('platform_type'):
            changed_roles.append(GameListModel.PlatformRole)
        if changed('tags'):
            changed_roles.append(GameListModel.TagsRole)
        if changed('is_used'):
            changed_roles.append(GameListModel.IsUsedRole)
        if changed('deadline_enabled'):
            changed_roles.append(GameListModel.DeadlineEnabledRole)
        if changed('deadline_at'):
            changed_roles.append(GameListModel.DeadlineAtRole)
        if changed('dlc_enabled'):
            changed_roles.append(GameListModel.DlcEnabledRole)
        if changed('image_path'):
            # clear pix cache so it reloads
            try:
                old_path = old.get('image_path')
                if old_path and old_path in self._pix_cache:
                    self._pix_cache.pop(old_path, None)
            except Exception:
                pass
            changed_roles.append(GameListModel.PixmapRole)

        if emit:
            idx = self.index(row)
            if not changed_roles:
                # emit all custom roles to be safe if we cannot detect
                changed_roles = [
                    GameListModel.TitleRole, GameListModel.KeyRole, GameListModel.PlatformRole,
                    GameListModel.TagsRole, GameListModel.IsUsedRole, GameListModel.DeadlineEnabledRole,
                    GameListModel.DeadlineAtRole, GameListModel.DlcEnabledRole, GameListModel.PixmapRole,
                ]
            self.dataChanged.emit(idx, idx, changed_roles)
        return row
    
    def emit_batch_changed(self, rows: list[int]):
        """Emit a single dataChanged signal covering a range of rows.
        
        Used after batch updates with emit=False to trigger a single view refresh.
        """
        if not rows:
            return
        min_row = min(rows)
        max_row = max(rows)
        if min_row >= 0 and max_row < len(self._games):
            self.dataChanged.emit(self.index(min_row), self.index(max_row))

    def __del__(self):
        try:
            if hasattr(self, '_loader_thread') and self._loader_thread.isRunning():
                self._loader_thread.quit()
                self._loader_thread.wait(1000)
        except Exception:
            pass
