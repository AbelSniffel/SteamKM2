"""Database backup manager for SteamKM2.

Provides automatic and manual database backup functionality with:
- Versioned backups with timestamps
- Configurable backup retention (max count)
- Restore from backup capability
- Backup integrity verification
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


class DatabaseBackupManager:
    """Manages database backups with versioning and restoration."""

    def __init__(self, db_path: str, backup_dir: str | None = None, max_backups: int = 10):
        """Initialize the backup manager.

        Args:
            db_path: Path to the main database file
            backup_dir: Directory to store backups (defaults to db_path/../backups)
            max_backups: Maximum number of backups to retain (0 = unlimited)
        """
        self.db_path = Path(db_path)
        
        if backup_dir is None:
            # Default to a 'backups' subdirectory next to the database
            backup_dir = self.db_path.parent / "backups"
        self.backup_dir = Path(backup_dir)
        
        self.max_backups = max(0, max_backups)
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, label: str = "auto", is_encrypted: bool = False) -> Tuple[bool, str, str]:
        """Create a backup of the database.

        Args:
            label: Label for the backup (e.g., 'auto', 'manual', 'pre-migration')
            is_encrypted: Whether the database is encrypted (will backup .enc file)

        Returns:
            Tuple of (success: bool, backup_path: str, message: str)
        """
        try:
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_name = self.db_path.stem
            backup_name = f"{db_name}_{label}_{timestamp}.db"
            backup_path = self.backup_dir / backup_name
            
            if is_encrypted:
                # For encrypted databases, backup the single .enc file which now
                # contains metadata in its header.
                enc_source = Path(f"{self.db_path}.enc")

                if not enc_source.exists():
                    return False, "", "Encrypted database file (.enc) not found"

                # Copy encrypted file
                enc_dest = Path(f"{backup_path}.enc")
                shutil.copy2(enc_source, enc_dest)
                backup_path = enc_dest
                
            else:
                # For non-encrypted databases
                if not self.db_path.exists():
                    return False, "", "Database file does not exist"
                
                # Use SQLite's backup API for a consistent copy
                success = self._backup_database(str(self.db_path), str(backup_path))
                
                if not success:
                    return False, "", "Failed to create database backup"

            # Clean up old backups if we exceed max_backups
            if self.max_backups > 0:
                self._cleanup_old_backups()

            backup_name = backup_path.name

            return True, str(backup_path), f"Backup created: {backup_name}"

        except Exception as e:
            return False, "", f"Backup error: {str(e)}"

    def _backup_database(self, source: str, destination: str) -> bool:
        """Perform the actual database backup using SQLite's backup API.

        Args:
            source: Source database path
            destination: Destination backup path

        Returns:
            True if successful, False otherwise
        """
        try:
            # First check if source exists and is accessible
            if not Path(source).exists():
                return False
            
            # Try to detect if source is a valid SQLite database
            # If not, fall back to simple file copy (for encrypted/binary files)
            try:
                test_conn = sqlite3.connect(source)
                test_conn.execute("SELECT name FROM sqlite_master LIMIT 1")
                test_conn.close()
                is_sqlite = True
            except (sqlite3.DatabaseError, sqlite3.OperationalError):
                # Not a standard SQLite database, use file copy instead
                is_sqlite = False
            
            if is_sqlite:
                # Use SQLite's backup API for a consistent snapshot
                src_conn = sqlite3.connect(source)
                dst_conn = sqlite3.connect(destination)
                
                with dst_conn:
                    src_conn.backup(dst_conn)
                
                src_conn.close()
                dst_conn.close()
            else:
                # Fallback: simple file copy for encrypted or binary databases
                shutil.copy2(source, destination)

            return True
        except Exception as e:
            # Clean up partial backup on failure
            try:
                Path(destination).unlink(missing_ok=True)
            except Exception:
                pass
            return False

    def restore_backup(self, backup_path: str, create_backup_before: bool = True) -> Tuple[bool, str]:
        """Restore database from a backup file.

        Args:
            backup_path: Path to the backup file to restore
            create_backup_before: Whether to backup current DB before restoring

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            backup_file = Path(backup_path)
            
            if not backup_file.exists():
                return False, "Backup file does not exist"

            # Verify the backup file is a valid SQLite database
            if not self._verify_backup(str(backup_file)):
                return False, "Backup file is not a valid SQLite database"

            # Create a safety backup of current database if requested
            if create_backup_before and self.db_path.exists():
                success, _, msg = self.create_backup("pre-restore")
                if not success:
                    return False, f"Failed to create safety backup: {msg}"

            # Restore the backup
            shutil.copy2(backup_file, self.db_path)

            return True, f"Database restored from {backup_file.name}"

        except Exception as e:
            return False, f"Restore error: {str(e)}"

    def _verify_backup(self, backup_path: str) -> bool:
        """Verify that a backup file is a valid SQLite database.

        Args:
            backup_path: Path to the backup file

        Returns:
            True if valid, False otherwise
        """
        try:
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            # Try to query sqlite_master to verify it's a valid database
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            cursor.fetchall()
            conn.close()
            return True
        except Exception:
            return False

    def list_backups(self, label: str | None = None) -> List[dict]:
        """List available backups.

        Args:
            label: Filter by label (e.g., 'auto', 'manual'), None for all

        Returns:
            List of backup info dicts with keys: name, path, size, created, label
        """
        backups = []
        
        try:
            # Find all .db and .db.enc files in backup directory
            backup_files = list(self.backup_dir.glob("*.db")) + list(self.backup_dir.glob("*.db.enc"))
            for backup_file in sorted(backup_files, reverse=True):
                # Parse backup filename: dbname_label_timestamp.db
                name_parts = backup_file.stem.split('_')
                
                # Extract label if possible (format: dbname_label_YYYYMMDD_HHMMSS)
                backup_label = None
                if len(name_parts) >= 3:
                    # Try to find the label (between dbname and timestamp)
                    for i in range(1, len(name_parts) - 1):
                        # Check if next part looks like a date
                        if name_parts[i + 1].isdigit() and len(name_parts[i + 1]) == 8:
                            backup_label = name_parts[i]
                            break
                
                # Skip if filtering by label and doesn't match
                if label and backup_label != label:
                    continue

                # Get file stats
                stats = backup_file.stat()
                created = datetime.fromtimestamp(stats.st_mtime)
                size_mb = stats.st_size / (1024 * 1024)

                backups.append({
                    'name': backup_file.name,
                    'path': str(backup_file),
                    'size': f"{size_mb:.2f} MB",
                    'size_bytes': stats.st_size,
                    'created': created.strftime("%Y-%m-%d %H:%M:%S"),
                    'created_timestamp': stats.st_mtime,
                    'label': backup_label or 'unknown',
                })

        except Exception:
            pass

        return backups

    def _cleanup_old_backups(self):
        """Remove old backups if we exceed max_backups limit."""
        try:
            if self.max_backups <= 0:
                return

            backups = self.list_backups()
            
            # Keep only the most recent max_backups
            if len(backups) > self.max_backups:
                # Sort by creation time (newest first)
                backups.sort(key=lambda x: x['created_timestamp'], reverse=True)
                
                # Delete old backups
                for backup in backups[self.max_backups:]:
                    try:
                        backup_path = Path(backup['path'])
                        backup_path.unlink()
                            # No separate .meta file in new single-file format
                    except Exception:
                        pass

        except Exception:
            pass

    def delete_backup(self, backup_path: str) -> Tuple[bool, str]:
        """Delete a specific backup file.

        Args:
            backup_path: Path to the backup file to delete

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            backup_file = Path(backup_path)
            
            if not backup_file.exists():
                return False, "Backup file does not exist"

            # Ensure it's in our backup directory for safety
            if self.backup_dir not in backup_file.parents:
                return False, "Backup file is not in the backup directory"

            # Delete the main backup file
            backup_file.unlink()
            
            # Single-file .enc format - no separate .meta file to delete
            
            return True, f"Deleted backup: {backup_file.name}"

        except Exception as e:
            return False, f"Delete error: {str(e)}"

    def get_backup_info(self) -> dict:
        """Get information about the backup system.

        Returns:
            Dict with keys: backup_dir, max_backups, backup_count, total_size
        """
        backups = self.list_backups()
        total_size = sum(b['size_bytes'] for b in backups)
        
        return {
            'backup_dir': str(self.backup_dir),
            'max_backups': self.max_backups,
            'backup_count': len(backups),
            'total_size': f"{total_size / (1024 * 1024):.2f} MB",
            'total_size_bytes': total_size,
        }
