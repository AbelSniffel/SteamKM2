"""Database manager for SteamKM2.

Refactored for:
 - Reduced repetition via a lightweight transaction context manager.
 - Safer schema migrations (idempotent checks instead of blind ALTER).
 - Added helpful indices for faster search/filter queries.
 - Consistent connection verification & foreign key enforcement.
 - Batch insertion for default tags (fewer commits).
Public method signatures remain unchanged for backward compatibility.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional
from src.core.database.db_backup import DatabaseBackupManager
from src.core.encryption_manager import EncryptionManager, InvalidPasswordError


class DatabaseLockedError(RuntimeError):
    """Raised when the database is encrypted but not unlocked."""


class DatabaseManager:
    """Manages SQLite database operations for SteamKM2 (SQLite backend)."""

    def __init__(self, db_path: str | None = None, settings_manager=None):
        if db_path is None:
            # Legacy fallback (should normally be supplied by SettingsManager)
            data_dir = os.path.expanduser("~/.steamkm2")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "steamkm2.db")
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None
        self._active_db_path: str | None = None
        self.encryption = EncryptionManager(db_path)
        self._encryption_key: bytes | None = None
        self._temp_plain_path: str | None = None
        self._is_unlocked = False
        # Initialize backup manager with max_backups from settings
        max_backups = 10  # default
        if settings_manager:
            max_backups = settings_manager.get_int('backup_max_count', 10)
        self.backup_manager = DatabaseBackupManager(db_path, max_backups=max_backups)

    # ------------------------------------------------------------------
    # Initialization & schema
    # ------------------------------------------------------------------
    def initialize(self, password: str | None = None):  # noqa: D401
        """Initialize database, unlocking when necessary."""
        if self.is_encrypted() and not self._is_unlocked:
            if password is None:
                return
            self.unlock(password)
        if self.requires_password():
            return
        self._connect()
        self._create_tables()
        self._apply_migrations()
        self._insert_default_data()

    def _connect(self):
        """Establish a connection if not already open."""
        if self.connection is None:
            path = self._get_connection_path()
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            # Enforce foreign keys
            conn.execute("PRAGMA foreign_keys = ON;")
            self.connection = conn
            self._active_db_path = path

    def _require_conn(self) -> sqlite3.Connection:
        if self.connection is None:
            if self.requires_password():
                raise DatabaseLockedError("Database is encrypted and locked.")
            raise RuntimeError("Database connection is not initialized. Call initialize() first.")
        return self.connection

    def _create_tables(self):
        conn = self._require_conn()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                game_key TEXT NOT NULL,
                platform_type TEXT NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                is_used BOOLEAN DEFAULT FALSE,
                image_path TEXT,
                -- Optional limited-time redemption deadline feature
                deadline_enabled BOOLEAN DEFAULT FALSE,
                deadline_at TEXT,
                -- Optional DLC flag
                dlc_enabled BOOLEAN DEFAULT FALSE,
                -- Steam App ID
                steam_app_id TEXT,
                -- Steam review data
                steam_review_score INTEGER,
                steam_review_count INTEGER
            );
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT DEFAULT '#0078d4',
                is_builtin BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS game_tags (
                game_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (game_id, tag_id),
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );
            -- Helpful indices for search/filter performance
            CREATE INDEX IF NOT EXISTS idx_games_title ON games(title);
            CREATE INDEX IF NOT EXISTS idx_games_key ON games(game_key);
            CREATE INDEX IF NOT EXISTS idx_games_platform ON games(platform_type);
            CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
            """
        )
        conn.commit()

    def _apply_migrations(self):
        """Apply idempotent schema migrations (add columns, etc.)."""
        conn = self._require_conn()
        cur = conn.cursor()
        # Get existing columns for games table
        cols = {row[1] for row in cur.execute("PRAGMA table_info(games)").fetchall()}
        # Add deadline_enabled if missing
        if 'deadline_enabled' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN deadline_enabled BOOLEAN DEFAULT FALSE")
        # Add deadline_at if missing
        if 'deadline_at' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN deadline_at TEXT")
        # Add dlc_enabled if missing
        if 'dlc_enabled' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN dlc_enabled BOOLEAN DEFAULT FALSE")
        # Add is_used if missing
        if 'is_used' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN is_used BOOLEAN DEFAULT FALSE")
        # Add steam_app_id if missing
        if 'steam_app_id' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN steam_app_id TEXT")
        # Add steam_review_score if missing
        if 'steam_review_score' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN steam_review_score INTEGER")
        # Add steam_review_count if missing
        if 'steam_review_count' not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN steam_review_count INTEGER")
        conn.commit()

    # ------------------------------------------------------------------
    # Default data
    # ------------------------------------------------------------------
    def _insert_default_data(self):
        conn = self._require_conn()
        cur = conn.cursor()
        default_tags = [
            'RPG', 'Survival', 'Adventure', 'Co-op', 'AAA', 'Indie', 'Action', 'Strategy',
            'Simulation', 'Sports', 'Racing', 'Puzzle', 'Horror', 'First-Person Shooter',
            'Multiplayer', 'Singleplayer', 'VR', 'Open World', 'Sandbox', 'Platformer'
        ]
        # Insert commonly-used default tags as Steam-provided tags
        cur.executemany(
            "INSERT OR IGNORE INTO tags (name, is_builtin) VALUES (?, 1)",
            ((t,) for t in default_tags),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------
    def is_encrypted(self) -> bool:
        return self.encryption.is_encrypted()

    def requires_password(self) -> bool:
        return self.is_encrypted() and not self._is_unlocked

    def get_working_path(self) -> str:
        if self.requires_password():
            raise DatabaseLockedError("Database is encrypted and locked.")
        if self.is_encrypted():
            if not self._temp_plain_path:
                raise RuntimeError("Unlocked database does not have an active plaintext path.")
            return self._temp_plain_path
        return self.db_path

    def unlock(self, password: str) -> bool:
        if not self.is_encrypted():
            raise RuntimeError("Database is not encrypted.")
        if self._is_unlocked:
            return True
        temp_path, key = self.encryption.decrypt_to_temp(password)
        self._temp_plain_path = temp_path
        self._encryption_key = key
        self._is_unlocked = True
        self._connect()
        self._create_tables()
        self._apply_migrations()
        self._insert_default_data()
        return True

    def enable_encryption(self, password: str) -> None:
        if self.is_encrypted():
            raise RuntimeError("Database is already encrypted.")
        self.close()
        self.encryption.enable(password)
        self._reset_encryption_state()
        self.initialize(password)

    def disable_encryption(self, password: str) -> None:
        if not self.is_encrypted():
            return
        self.close()
        self.encryption.disable(password)
        self._reset_encryption_state()
        self.initialize()

    def change_password(self, current_password: str, new_password: str) -> None:
        if not self.is_encrypted():
            raise RuntimeError("Database is not encrypted.")
        if self._is_unlocked and self.connection is not None:
            try:
                self.connection.commit()
            except Exception:
                pass
            if self._temp_plain_path and self._encryption_key:
                self.encryption.reencrypt_from_plain(self._temp_plain_path, self._encryption_key)
        plaintext_path = self._temp_plain_path if self._is_unlocked else None
        new_key = self.encryption.change_password(
            current_password,
            new_password,
            plaintext_path=plaintext_path,
        )
        if self._is_unlocked:
            self._encryption_key = new_key

    def _reset_encryption_state(self):
        self._is_unlocked = False
        self._encryption_key = None
        if self._temp_plain_path:
            self.encryption.cleanup_temp(self._temp_plain_path)
        self._temp_plain_path = None
        self._active_db_path = None

    def _get_connection_path(self) -> str:
        if self.is_encrypted():
            if not self._is_unlocked or not self._temp_plain_path:
                raise DatabaseLockedError("Database is encrypted and locked.")
            return self._temp_plain_path
        return self.db_path

    def _sync_encrypted_db(self):
        """Sync changes from the temp plaintext file back to the encrypted database."""
        if self.is_encrypted() and self._is_unlocked:
            if self._temp_plain_path and self._encryption_key:
                try:
                    self.encryption.reencrypt_from_plain(self._temp_plain_path, self._encryption_key)
                except Exception as e:
                    # Don't raise - we'll try again on next sync or close
                    print(f"Warning: Failed to sync encrypted database: {e}")

    def switch_database(self, new_db_path: str, password: str | None = None) -> tuple[bool, str]:
        """Switch to a different database file.
        
        This closes the current database connection and opens a new one
        to the specified database file.
        
        Args:
            new_db_path: Path to the new database file
            password: Password if the new database is encrypted
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        import os
        
        if not new_db_path:
            return False, "No database path provided"
        
        if not os.path.exists(new_db_path):
            return False, f"Database file not found: {new_db_path}"
        
        try:
            # Close current database
            self.close()
            
            # Update paths
            old_db_path = self.db_path
            self.db_path = new_db_path
            self.encryption = EncryptionManager(new_db_path)
            self.backup_manager = DatabaseBackupManager(new_db_path, max_backups=10)
            
            # Reset encryption state
            self._is_unlocked = False
            self._encryption_key = None
            self._temp_plain_path = None
            self._active_db_path = None
            
            # Initialize the new database
            self.initialize(password)
            
            return True, f"Switched to database: {os.path.basename(new_db_path)}"
            
        except Exception as e:
            # Try to restore the old database
            try:
                self.db_path = old_db_path
                self.encryption = EncryptionManager(old_db_path)
                self.backup_manager = DatabaseBackupManager(old_db_path, max_backups=10)
                self.initialize()
            except Exception:
                pass
            
            return False, f"Failed to switch database: {str(e)}"

    # ------------------------------------------------------------------
    # Transaction helper
    # ------------------------------------------------------------------
    @contextmanager
    def _tx(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._require_conn()
        cur = conn.cursor()
        try:
            yield cur
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
            # Sync to encrypted file after successful commit
            self._sync_encrypted_db()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def add_game(
        self,
        title: str,
        game_key: str,
        platform_type: str,
        notes: str = "",
        tag_ids: Optional[List[int]] = None,
        image_path: str | None = None,
    is_used: bool = False,
    deadline_enabled: bool = False,
    deadline_at: str | None = None,
    dlc_enabled: bool = False,
    steam_app_id: str | None = None,
    steam_review_score: int | None = None,
    steam_review_count: int | None = None,
    ) -> int:
        with self._tx() as cur:
            cur.execute(
                """
        INSERT INTO games (title, game_key, platform_type, notes, is_used, image_path, deadline_enabled, deadline_at, dlc_enabled, steam_app_id, steam_review_score, steam_review_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
        (title, game_key, platform_type, notes, 1 if is_used else 0, image_path, 1 if deadline_enabled else 0, deadline_at, 1 if dlc_enabled else 0, steam_app_id, steam_review_score, steam_review_count),
            )
            game_id = cur.lastrowid or 0
            if tag_ids:
                cur.executemany(
                    "INSERT OR IGNORE INTO game_tags (game_id, tag_id) VALUES (?, ?)",
                    ((game_id, tid) for tid in tag_ids),
                )
            return int(game_id)

    def add_games_batch(self, games: List[Dict]) -> List[int]:
        """Add multiple games in a single transaction for better performance.
        
        Each dict in games should have the same keys as add_game parameters:
        title, game_key, platform_type, notes, tag_ids, image_path, is_used,
        deadline_enabled, deadline_at, dlc_enabled, steam_app_id, etc.
        
        Returns list of inserted game IDs.
        """
        if not games:
            return []
        
        with self._tx() as cur:
            inserted_ids = []
            for game in games:
                cur.execute(
                    """
                    INSERT INTO games (title, game_key, platform_type, notes, is_used, image_path, 
                                       deadline_enabled, deadline_at, dlc_enabled, steam_app_id, 
                                       steam_review_score, steam_review_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        game.get('title', ''),
                        game.get('game_key', ''),
                        game.get('platform_type', 'Unknown'),
                        game.get('notes', ''),
                        1 if game.get('is_used') else 0,
                        game.get('image_path'),
                        1 if game.get('deadline_enabled') else 0,
                        game.get('deadline_at'),
                        1 if game.get('dlc_enabled') else 0,
                        game.get('steam_app_id'),
                        game.get('steam_review_score'),
                        game.get('steam_review_count'),
                    ),
                )
                game_id = cur.lastrowid or 0
                inserted_ids.append(int(game_id))
                
                # Handle tags for this game
                tag_ids = game.get('tag_ids')
                if tag_ids:
                    cur.executemany(
                        "INSERT OR IGNORE INTO game_tags (game_id, tag_id) VALUES (?, ?)",
                        ((game_id, tid) for tid in tag_ids),
                    )
            
            return inserted_ids

    def get_games(
        self,
        search_term: str = "",
        platform_filter: str = "",
        tag_filter: str = "",
    ) -> List[Dict]:
        conn = self._require_conn()
        cur = conn.cursor()
        clauses: List[str] = []
        params: List[str] = []
        if search_term:
            like = f"%{search_term}%"
            clauses.append("(g.title LIKE ? OR g.game_key LIKE ?)")
            params.extend([like, like])
        if platform_filter and platform_filter != "All Platforms":
            clauses.append("g.platform_type = ?")
            params.append(platform_filter)
        if tag_filter and tag_filter != "All Categories":
            clauses.append("t.name = ?")
            params.append(tag_filter)
        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
            FROM games g
            LEFT JOIN game_tags gt ON g.id = gt.game_id
            LEFT JOIN tags t ON gt.tag_id = t.id
            {where_sql}
            GROUP BY g.id
            ORDER BY g.date_added DESC
        """
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def get_game_by_id(self, game_id: int) -> Optional[Dict]:
        """Return a single game row with aggregated tags by id, or None if missing."""
        conn = self._require_conn()
        cur = conn.cursor()
        sql = """
            SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
            FROM games g
            LEFT JOIN game_tags gt ON g.id = gt.game_id
            LEFT JOIN tags t ON gt.tag_id = t.id
            WHERE g.id = ?
            GROUP BY g.id
        """
        row = cur.execute(sql, (game_id,)).fetchone()
        return dict(row) if row else None

    def get_games_by_steam_app_id(self, steam_app_id: str) -> List[Dict]:
        """Return all games with the given Steam AppID."""
        if not steam_app_id:
            return []
        conn = self._require_conn()
        cur = conn.cursor()
        sql = """
            SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
            FROM games g
            LEFT JOIN game_tags gt ON g.id = gt.game_id
            LEFT JOIN tags t ON gt.tag_id = t.id
            WHERE g.steam_app_id = ?
            GROUP BY g.id
        """
        cur.execute(sql, (str(steam_app_id),))
        return [dict(r) for r in cur.fetchall()]

    def get_game_by_key(self, game_key: str) -> Optional[Dict]:
        """Return a game with the given game key, or None if not found.
        
        Used for duplicate detection during imports or adding games.
        
        Args:
            game_key: The game key to search for
            
        Returns:
            Game dictionary if found, None otherwise
        """
        if not game_key:
            return None
        conn = self._require_conn()
        cur = conn.cursor()
        sql = """
            SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
            FROM games g
            LEFT JOIN game_tags gt ON g.id = gt.game_id
            LEFT JOIN tags t ON gt.tag_id = t.id
            WHERE g.game_key = ?
            GROUP BY g.id
            LIMIT 1
        """
        row = cur.execute(sql, (game_key,)).fetchone()
        return dict(row) if row else None

    def get_games_by_keys(self, game_keys: list[str]) -> dict[str, Dict]:
        """Return all games matching any of the given game keys.
        
        Used for batch duplicate detection during imports.
        
        Args:
            game_keys: List of game keys to search for
            
        Returns:
            Dict mapping game_key -> game dict for all found games
        """
        if not game_keys:
            return {}
        conn = self._require_conn()
        cur = conn.cursor()
        placeholders = ','.join('?' * len(game_keys))
        sql = f"""
            SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
            FROM games g
            LEFT JOIN game_tags gt ON g.id = gt.game_id
            LEFT JOIN tags t ON gt.tag_id = t.id
            WHERE g.game_key IN ({placeholders})
            GROUP BY g.id
        """
        cur.execute(sql, game_keys)
        result = {}
        for row in cur.fetchall():
            game = dict(row)
            result[game['game_key']] = game
        return result

    def get_game_count(self) -> int:
        conn = self._require_conn()
        return conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    def get_platforms(self) -> List[str]:
        conn = self._require_conn()
        return [row[0] for row in conn.execute("SELECT DISTINCT platform_type FROM games ORDER BY platform_type").fetchall()]

    def get_tags(self) -> List[Dict]:
        conn = self._require_conn()
        return [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name").fetchall()]

    def get_tags_in_use(self) -> List[Dict]:
        """Get only tags that are assigned to at least one game.
        
        Returns:
            List of tag dictionaries for tags currently in use.
        """
        conn = self._require_conn()
        return [dict(r) for r in conn.execute(
            """
            SELECT DISTINCT t.* FROM tags t
            INNER JOIN game_tags gt ON t.id = gt.tag_id
            ORDER BY t.name
            """
        ).fetchall()]

    def add_tag(self, name: str, color: str = "#0078d4", is_builtin: bool = False) -> int:
        """Add a new tag to the database.
        
        Args:
            name: Tag name
            color: Tag color (hex)
                is_builtin: If True, tag is marked as Steam-provided (e.g., from Steam fetch)
        
        Returns:
            The ID of the newly created tag
        """
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO tags (name, color, is_builtin) VALUES (?, ?, ?)",
                (name, color, 1 if is_builtin else 0),
            )
            return int(cur.lastrowid or 0)

    def get_or_create_tags(self, tag_names: list[str], is_builtin: bool = True) -> dict[str, int]:
        """Get existing tags or create new ones, returning name->id mapping.
        
        This is the preferred method for adding tags fetched from Steam, as it:
        - Returns existing tags if they exist (preserving their is_builtin/Steam flag)
        - Creates new tags and marks them as Steam-provided when requested
        
        Args:
            tag_names: List of tag names to get or create
            is_builtin: Whether new tags should be marked as Steam-provided
        
        Returns:
            Dict mapping tag name -> tag id
        """
        if not tag_names:
            return {}
        
        conn = self._require_conn()
        result = {}
        
        # Get all existing tags
        existing_tags = {t['name'].lower(): (t['name'], t['id']) for t in self.get_tags()}
        
        with self._tx() as cur:
            for name in tag_names:
                name_lower = name.lower()
                if name_lower in existing_tags:
                    # Use existing tag (preserve original casing)
                    orig_name, tag_id = existing_tags[name_lower]
                    result[orig_name] = tag_id
                else:
                    # Create new tag
                    cur.execute(
                        "INSERT INTO tags (name, is_builtin) VALUES (?, ?)",
                        (name, 1 if is_builtin else 0),
                    )
                    tag_id = int(cur.lastrowid or 0)
                    result[name] = tag_id
                    # Add to existing tags cache for subsequent lookups
                    existing_tags[name_lower] = (name, tag_id)
        
        return result

    def update_game(
        self,
        game_id: int,
        title: str,
        game_key: str,
        platform_type: str,
        notes: str = "",
        is_used: bool = False,
        tag_ids: Optional[List[int]] = None,
        image_path: str | None = None,
    deadline_enabled: bool = False,
    deadline_at: str | None = None,
    dlc_enabled: bool = False,
    steam_app_id: str | None = None,
    steam_review_score: int | None = None,
    steam_review_count: int | None = None,
    ) -> bool:
        with self._tx() as cur:
            cur.execute(
                """
                UPDATE games
        SET title = ?, game_key = ?, platform_type = ?, notes = ?, is_used = ?, image_path = ?, deadline_enabled = ?, deadline_at = ?, dlc_enabled = ?, steam_app_id = ?, steam_review_score = ?, steam_review_count = ?
                WHERE id = ?
                """,
        (title, game_key, platform_type, notes, 1 if is_used else 0, image_path, 1 if deadline_enabled else 0, deadline_at, 1 if dlc_enabled else 0, steam_app_id, steam_review_score, steam_review_count, game_id),
            )
            cur.execute("DELETE FROM game_tags WHERE game_id = ?", (game_id,))
            if tag_ids:
                cur.executemany(
                    "INSERT OR IGNORE INTO game_tags (game_id, tag_id) VALUES (?, ?)",
                    ((game_id, tid) for tid in tag_ids),
                )
            return True

    def delete_game(self, game_id: int) -> bool:
        with self._tx() as cur:
            cur.execute("DELETE FROM games WHERE id = ?", (game_id,))
            return cur.rowcount > 0

    def toggle_game_used_status(self, game_id: int) -> bool:
        with self._tx() as cur:
            cur.execute(
                "UPDATE games SET is_used = NOT is_used WHERE id = ?",
                (game_id,),
            )
            return cur.rowcount > 0

    def delete_tag(self, tag_id: int) -> bool:
        with self._tx() as cur:
            # Remove tag references first (CASCADE also handles it, but explicit for clarity & rowcount)
            cur.execute("DELETE FROM game_tags WHERE tag_id = ?", (tag_id,))
            cur.execute("DELETE FROM tags WHERE id = ? AND is_builtin = 0", (tag_id,))
            return cur.rowcount > 0

    def delete_custom_tags(self) -> int:
        with self._tx() as cur:
            cur.execute(
                "DELETE FROM game_tags WHERE tag_id IN (SELECT id FROM tags WHERE is_builtin = 0)"
            )
            cur.execute("DELETE FROM tags WHERE is_builtin = 0")
            return cur.rowcount

    def delete_unused_tags(self) -> list:
        """Delete unused Steam-provided tags that are not assigned to any games.

        Important: user-created custom tags (is_builtin = 0) are preserved
        even if they are not currently assigned to any games. This prevents
        accidentally removing tags created by the user when they are unused.

        Returns:
            Number of tags deleted.
        """
        with self._tx() as cur:
            # Only delete tags which are unused and marked as built-in
            # Fetch the names of unused built-in tags first so we can report them
            cur.execute(
                """
                SELECT id, name FROM tags
                WHERE id NOT IN (SELECT DISTINCT tag_id FROM game_tags)
                  AND is_builtin = 1
                """
            )
            rows = cur.fetchall()
            deleted_names = [r[1] for r in rows]

            if not rows:
                return []

            # Delete the unused built-in tags we just discovered
            cur.execute(
                "DELETE FROM tags WHERE id IN ({})".format(
                    ",".join(str(r[0]) for r in rows)
                )
            )

            # Print the deleted tag names to the terminal so the user sees them
            try:
                # Keep simple and use print so it appears on the app stdout/terminal
                print(f"Deleted {len(deleted_names)} unused tag(s): {', '.join(deleted_names)}")
            except Exception:
                # Never raise from logging
                pass

            return deleted_names

    # ------------------------------------------------------------------
    # Database Backup Management
    # ------------------------------------------------------------------
    def create_backup(self, label: str = "manual"):
        """Create a backup of the database.
        
        Args:
            label: Label for the backup (e.g., 'manual', 'auto', 'pre-migration')
            
        Returns:
            Tuple of (success: bool, backup_path: str, message: str)
        """
        if self.is_encrypted() and not self._is_unlocked:
            return False, "", "Database is locked. Unlock it first to create a backup."
        
        # Ensure all changes are flushed to disk before backing up
        if self.connection:
            try:
                self.connection.commit()
            except Exception:
                pass
        
        # For encrypted databases, we need to re-encrypt before backup
        is_encrypted = self.is_encrypted()
        if is_encrypted and self._is_unlocked:
            # Re-encrypt the current working copy to the main encrypted file
            try:
                self.encryption.reencrypt_from_plain(self._temp_plain_path, self._encryption_key)
            except Exception as e:
                return False, "", f"Failed to re-encrypt database before backup: {str(e)}"
        
        # Backup with encryption flag
        return self.backup_manager.create_backup(label, is_encrypted=is_encrypted)
    
    def restore_backup(self, backup_path: str, create_backup_before: bool = True):
        """Restore database from a backup file.
        
        Args:
            backup_path: Path to the backup file to restore
            create_backup_before: Whether to backup current DB before restoring
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        # Close connection before restore
        self.close()
        success, message = self.backup_manager.restore_backup(backup_path, create_backup_before)
        # Reconnect after restore
        if success:
            self.initialize()
        return success, message
    
    def list_backups(self, label: str | None = None):
        """List available backups.
        
        Args:
            label: Filter by label (e.g., 'auto', 'manual'), None for all
            
        Returns:
            List of backup info dicts
        """
        return self.backup_manager.list_backups(label)
    
    def delete_backup(self, backup_path: str):
        """Delete a specific backup file.
        
        Args:
            backup_path: Path to the backup file to delete
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        return self.backup_manager.delete_backup(backup_path)
    
    def get_backup_info(self):
        """Get information about the backup system.
        
        Returns:
            Dict with backup directory info, count, size, etc.
        """
        return self.backup_manager.get_backup_info()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self):  # noqa: D401
        """Close the database connection."""
        # If encrypted and unlocked, we need to re-encrypt the temp file BEFORE closing
        should_reencrypt = self.is_encrypted() and self._is_unlocked and self._temp_plain_path and self._encryption_key
        
        if self.connection is not None:
            try:
                # Ensure all changes are committed before re-encrypting
                self.connection.commit()
            except Exception:
                pass
            try:
                self.connection.close()
            except Exception:
                pass
            finally:
                self.connection = None
                self._active_db_path = None
        
        # Force garbage collection to release any remaining references
        import gc
        gc.collect()
        
        # Re-encrypt after closing the connection to ensure all changes are flushed
        if should_reencrypt:
            try:
                self.encryption.reencrypt_from_plain(self._temp_plain_path, self._encryption_key)
            except InvalidPasswordError:
                # Should not happen with stored key, ignore to avoid data loss
                pass
            except Exception as e:
                # Log or handle re-encryption errors
                print(f"Warning: Failed to re-encrypt database: {e}")
            finally:
                self._reset_encryption_state()
        elif self.is_encrypted():
            # Still reset state even if not unlocked
            self._reset_encryption_state()

    def __del__(self):  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass
