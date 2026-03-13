"""Database export functionality for SteamKM2.

Provides various export formats:
- Plaintext list (title and key)
- Encrypted database
- Decrypted database (SQLite)
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.database_manager import DatabaseManager


class DatabaseExporter:
    """Handles exporting database to various formats."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize the exporter.
        
        Args:
            db_manager: The database manager instance
        """
        self.db_manager = db_manager
    
    def export_to_plaintext(self, output_path: str) -> tuple[bool, str]:
        """Export database as plaintext list (title and key per row).
        
        Args:
            output_path: Path where to save the text file
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self.db_manager.requires_password():
                return False, "Database is locked. Unlock it first."
            
            # Get all games from database
            games = self.db_manager.get_games()
            
            # Create simple text file with title and key per row
            with open(output_path, 'w', encoding='utf-8') as f:
                for game in games:
                    title = game['title']
                    key = game['game_key']
                    f.write(f'{title} | {key}\n')
            
            return True, f"Database exported to text file: {Path(output_path).name}"
        
        except Exception as e:
            return False, f"Export to text file failed: {str(e)}"
    
    def export_to_encrypted_db(self, output_path: str) -> tuple[bool, str]:
        """Export database as encrypted database file.
        
        Args:
            output_path: Path where to save the encrypted database
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self.db_manager.requires_password():
                return False, "Database is locked. Unlock it first."
            
            if not self.db_manager.is_encrypted():
                return False, "Database is not encrypted. Use 'Export as Decrypted DB' instead."
            
            # Ensure all changes are committed
            if self.db_manager.connection:
                self.db_manager.connection.commit()
            
            # Re-encrypt to ensure latest changes
            if self.db_manager._is_unlocked:
                self.db_manager.encryption.reencrypt_from_plain(
                    self.db_manager._temp_plain_path,
                    self.db_manager._encryption_key
                )
            
            # Get paths
            enc_source = Path(f"{self.db_manager.db_path}.enc")

            output_path_obj = Path(output_path)
            output_path_str = str(output_path_obj)
            if not output_path_str.lower().endswith(".enc"):
                output_path_str = f"{output_path_str}.enc"
            output_path_obj = Path(output_path_str)

            # Copy encrypted file (single-file format contains metadata header)
            if not enc_source.exists():
                return False, "Encrypted database file not found"

            shutil.copy2(enc_source, output_path_obj)

            return True, f"Encrypted database exported: {output_path_obj.name}"
        
        except Exception as e:
            return False, f"Export to encrypted DB failed: {str(e)}"
    
    def export_to_decrypted_db(self, output_path: str) -> tuple[bool, str]:
        """Export database as decrypted SQLite database.
        
        Args:
            output_path: Path where to save the decrypted database
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self.db_manager.requires_password():
                return False, "Database is locked. Unlock it first."
            
            # Ensure all changes are committed
            if self.db_manager.connection:
                self.db_manager.connection.commit()
            
            # Get the working database path (plaintext)
            if self.db_manager.is_encrypted() and self.db_manager._is_unlocked:
                source_path = self.db_manager._temp_plain_path
            else:
                source_path = self.db_manager.db_path
            
            # Copy using SQLite backup API for consistency
            src_conn = sqlite3.connect(source_path)
            dst_conn = sqlite3.connect(output_path)
            
            with dst_conn:
                src_conn.backup(dst_conn)
            
            src_conn.close()
            dst_conn.close()
            
            return True, f"Database exported as decrypted SQLite: {Path(output_path).name}"
        
        except Exception as e:
            return False, f"Export to decrypted DB failed: {str(e)}"
