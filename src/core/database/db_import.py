"""Database import functionality for SteamKM2.

Provides import from various sources with encryption support.
Supports:
- SteamKM2 databases (.db/.db.enc)
- Text files with game keys (.txt)
- Legacy SteamKM1 JSON files (.json)
- Legacy SteamKM1 encrypted JSON files (.json.enc)
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

if TYPE_CHECKING:
    from src.core.database_manager import DatabaseManager


class DatabaseImporter:
    """Handles importing database from various sources."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize the importer.
        
        Args:
            db_manager: The database manager instance
        """
        self.db_manager = db_manager
    
    def import_database(self, source_path: str, password: str | None = None) -> tuple[bool, str]:
        """Import a database file (supports both encrypted and non-encrypted).
        
        Args:
            source_path: Path to the database file to import (can be .db or .db.enc)
            password: Password for encrypted databases (None for non-encrypted)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            from src.core.encryption_manager import EncryptionManager
            
            # Normalize the source path - if user selected .db.enc, use .db as base
            source_path_obj = Path(source_path)
            if source_path_obj.suffix == '.enc' and source_path_obj.stem.endswith('.db'):
                # User selected "keys.db.enc", use "keys.db" as base path
                source_path = str(source_path_obj.with_suffix(''))  # Remove .enc
            
            # Check if the source is encrypted
            temp_enc = EncryptionManager(source_path)
            is_encrypted = temp_enc.is_encrypted()
            
            if is_encrypted and not password:
                return False, "Password required for encrypted database"
            
            # Verify password if encrypted
            if is_encrypted:
                try:
                    temp_enc.decrypt(password)
                except Exception as e:
                    return False, f"Invalid password or corrupted file: {str(e)}"
            
            # Close current database
            self.db_manager.close()
            
            # Give Windows time to release file handles
            import time
            time.sleep(0.5)
            
            # Get paths
            source_db = Path(source_path)
            dest_db = Path(self.db_manager.db_path)
            
            # Retry removing old database files with multiple attempts
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    dest_db.unlink(missing_ok=True)
                    Path(f"{dest_db}.enc").unlink(missing_ok=True)
                    # Single-file .enc format - no .meta to remove
                    break  # Success
                except PermissionError as e:
                    if attempt == max_retries - 1:
                        raise PermissionError(
                            f"Cannot delete existing database files. Please ensure the application "
                            f"is not running in another window and no other program is accessing the files."
                        ) from e
                    time.sleep(0.5)  # Wait before retry
            
            if is_encrypted:
                # Copy single encrypted database file (.enc) which now contains
                # KDF metadata in its header. No separate .meta file is required.
                enc_source = Path(f"{source_db}.enc")

                if not enc_source.exists():
                    return False, f"Encrypted database file not found: {enc_source}"

                shutil.copy2(enc_source, f"{dest_db}.enc")

                # Reinitialize with password
                self.db_manager.initialize(password)
            else:
                # Copy non-encrypted database
                shutil.copy2(source_db, dest_db)
                
                # Reinitialize without password
                self.db_manager.initialize()
            
            return True, f"Database imported successfully from {source_db.name}"
        
        except Exception as e:
            # Try to restore database connection
            try:
                self.db_manager.initialize()
            except Exception:
                pass
            
            return False, f"Import failed: {str(e)}"
    
    def merge_database(
        self, 
        source_path: str, 
        password: str | None = None
    ) -> tuple[bool, str, list[dict]]:
        """Merge games from another database into the current one.
        
        This extracts all games from the source database and prepares them
        for import with duplicate handling.
        
        Args:
            source_path: Path to the database file to merge (can be .db or .db.enc)
            password: Password for encrypted databases (None for non-encrypted)
            
        Returns:
            Tuple of (success: bool, message: str, games: list[dict])
            The games list can be passed to import_games_to_database after
            duplicate resolution.
        """
        import sqlite3
        import tempfile
        
        try:
            from src.core.encryption_manager import EncryptionManager
            
            # Normalize the source path
            source_path_obj = Path(source_path)
            if source_path_obj.suffix == '.enc' and source_path_obj.stem.endswith('.db'):
                source_path = str(source_path_obj.with_suffix(''))
            
            # Check if the source is encrypted
            temp_enc = EncryptionManager(source_path)
            is_encrypted = temp_enc.is_encrypted()
            
            if is_encrypted and not password:
                return False, "Password required for encrypted database", []
            
            # Get the path to read from
            if is_encrypted:
                # Decrypt to a temp file
                temp_path, _ = temp_enc.decrypt_to_temp(password)
                db_path_to_read = temp_path
            else:
                db_path_to_read = source_path
            
            # Open source database read-only
            conn = sqlite3.connect(db_path_to_read)
            conn.row_factory = sqlite3.Row
            
            try:
                # Extract all games with their tags
                cursor = conn.cursor()
                
                # Get all games
                cursor.execute("""
                    SELECT g.*, GROUP_CONCAT(t.name, ', ') AS tags
                    FROM games g
                    LEFT JOIN game_tags gt ON g.id = gt.game_id
                    LEFT JOIN tags t ON gt.tag_id = t.id
                    GROUP BY g.id
                """)
                
                games = []
                for row in cursor.fetchall():
                    game = dict(row)
                    # Convert to the format expected by import_games_to_database
                    tags_str = game.get('tags', '') or ''
                    tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
                    
                    games.append({
                        'title': game.get('title', 'Unknown'),
                        'key': game.get('game_key', ''),
                        'platform': game.get('platform_type', 'Steam'),
                        'notes': game.get('notes', ''),
                        'tags': tags_list,
                        'steam_app_id': game.get('steam_app_id'),
                    })
                
                return True, f"Found {len(games)} game(s) in source database", games
                
            finally:
                conn.close()
                # Clean up temp file if we created one
                if is_encrypted and temp_path:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        
        except Exception as e:
            return False, f"Merge failed: {str(e)}", []
    
    def detect_encryption(self, file_path: str) -> bool:
        """Detect if a database file is encrypted.
        
        Args:
            file_path: Path to the database file (can be .db or .db.enc)
            
        Returns:
            True if encrypted, False otherwise
        """
        try:
            from src.core.encryption_manager import EncryptionManager
            
            # Normalize the path - if user selected .db.enc, use .db as base
            file_path_obj = Path(file_path)
            if file_path_obj.suffix == '.enc' and file_path_obj.stem.endswith('.db'):
                # User selected "keys.db.enc", use "keys.db" as base path
                file_path = str(file_path_obj.with_suffix(''))  # Remove .enc
            
            temp_enc = EncryptionManager(file_path)
            return temp_enc.is_encrypted()
        except Exception:
            return False

    def verify_password(self, file_path: str, password: str | None) -> tuple[bool, str]:
        """Verify that the provided password can decrypt the given database file.

        Returns (True, message) on success (or if file is not encrypted),
        or (False, error_message) on failure.
        """
        try:
            from src.core.encryption_manager import EncryptionManager, InvalidPasswordError

            # Check if this is a legacy JSON file
            file_path_obj = Path(file_path)
            if file_path_obj.suffix == '.enc' and not file_path_obj.stem.endswith('.db'):
                # This is a legacy .enc or .json.enc file, verify differently
                return self._verify_legacy_json_password(file_path, password)

            # Normalize the path - if user selected .db.enc, use .db as base
            if file_path_obj.suffix == '.enc' and file_path_obj.stem.endswith('.db'):
                file_path = str(file_path_obj.with_suffix(''))  # Remove .enc

            temp_enc = EncryptionManager(file_path)

            if not temp_enc.is_encrypted():
                return True, "Database file is not encrypted"

            if not password:
                return False, "Password required for encrypted database"

            try:
                # Attempt a decryption to verify the password. We don't keep the
                # decrypted bytes here, this is just a quick verification step.
                temp_enc.decrypt(password)
                return True, "Password verified"
            except InvalidPasswordError:
                return False, "Incorrect password"
            except Exception as e:
                return False, f"Decryption failed: {e}"

        except Exception as e:
            return False, f"Verification error: {e}"
    
    def _verify_legacy_json_password(self, file_path: str, password: str | None) -> tuple[bool, str]:
        """Verify password for legacy SteamKM1 encrypted JSON files.
        
        Returns (True, message) on success, (False, error_message) on failure.
        """
        if not password:
            return False, "Password required for encrypted file"
        
        try:
            # Read encrypted file
            with open(file_path, 'r', encoding='utf-8') as f:
                encrypted_data = f.read()
            
            # Try to decrypt using the same method as import_from_legacy_json
            decrypted = self._decrypt_legacy_json(encrypted_data, password)
            
            if decrypted is None:
                return False, "Incorrect password"
            
            # Also try to parse as JSON to ensure it's valid
            try:
                json.loads(decrypted)
                return True, "Password verified"
            except json.JSONDecodeError:
                return False, "Invalid file format"
                
        except FileNotFoundError:
            return False, "File not found"
        except Exception as e:
            return False, f"Verification error: {e}"

    def detect_file_type(self, file_path: str) -> tuple[str, bool]:
        """Detect the type of import file.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            Tuple of (file_type, is_encrypted) where file_type is one of:
            - 'steamkm2_db': SteamKM2 database file
            - 'steamkm1_json': Legacy SteamKM1 JSON file
            - 'text': Text file with game keys
            - 'unknown': Unknown file type
        """
        file_path_obj = Path(file_path)
        
        # Check by extension first
        if file_path_obj.suffix == '.enc':
            # Check if it's a database or JSON
            stem = file_path_obj.stem
            if stem.endswith('.db'):
                return 'steamkm2_db', True
            elif stem.endswith('.json'):
                return 'steamkm1_json', True
            else:
                # .enc files without .json or .db prefix are likely legacy SteamKM1
                # They export as just ".enc" but contain encrypted JSON data
                return 'steamkm1_json', True
        
        elif file_path_obj.suffix == '.db':
            return 'steamkm2_db', False
        
        elif file_path_obj.suffix == '.json':
            return 'steamkm1_json', False
        
        elif file_path_obj.suffix in ['.txt', '.text']:
            return 'text', False
        
        # Try to detect by content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(100)
                if content.strip().startswith('{') or content.strip().startswith('['):
                    return 'steamkm1_json', False
                else:
                    return 'text', False
        except UnicodeDecodeError:
            # Binary file, could be encrypted
            return 'unknown', True
        except Exception:
            return 'unknown', False
    
    def import_from_text_file(self, file_path: str) -> tuple[bool, str, list[dict]]:
        """Import game keys from a text file.
        
        Supports various text formats:
        - "Title | Key | AppID" (optional AppID)
        - "Title | Key"
        - "Title: Key"
        - "Title - Key"
        - "Key" (only key, will generate title)
        - Lines with just keys separated by newlines
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Tuple of (success: bool, message: str, games: list[dict])
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            games = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                title = None
                key = None
                steam_app_id = None
                
                # Try different separators (use rsplit for : to split on last occurrence)
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        title = parts[0].strip()
                        key = parts[1].strip()
                        if len(parts) >= 3:
                            steam_app_id = parts[2].strip() or None
                elif ':' in line:
                    # Split on LAST colon to handle titles like "Game: Title: Key"
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        key = parts[1].strip()
                elif '-' in line:
                    parts = line.split('-', 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        key = parts[1].strip()
                elif '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        title = parts[0].strip()
                        key = parts[1].strip()
                        if len(parts) >= 3:
                            steam_app_id = parts[2].strip() or None
                
                # If no separator found, treat entire line as a key
                if key is None:
                    key = line.strip()
                    title = f"Game {line_num}"
                
                # Strip trailing colon from title if present
                if title and title.endswith(':'):
                    title = title[:-1].strip()
                
                if key:
                    games.append({
                        'title': title,
                        'key': key,
                        'platform': 'Steam',  # Default to Steam
                        'notes': f'Imported from text file: {Path(file_path).name}',
                        'tags': [],
                        'steam_app_id': steam_app_id
                    })
            
            if not games:
                return False, "No valid game keys found in file", []
            
            return True, f"Found {len(games)} game(s) in text file", games
        
        except Exception as e:
            return False, f"Failed to read text file: {str(e)}", []
    
    def import_from_legacy_json(self, file_path: str, password: str | None = None) -> tuple[bool, str, list[dict]]:
        """Import game keys from legacy SteamKM1 JSON file.
        
        Args:
            file_path: Path to the JSON file (.json or .json.enc)
            password: Password for encrypted files
            
        Returns:
            Tuple of (success: bool, message: str, games: list[dict])
        """
        try:
            file_path_obj = Path(file_path)
            
            # Determine if encrypted
            is_encrypted = file_path_obj.suffix == '.enc'
            
            if is_encrypted:
                if not password:
                    return False, "Password required for encrypted JSON file", []
                
                # Read encrypted file
                with open(file_path, 'r', encoding='utf-8') as f:
                    encrypted_data = f.read()
                
                # Decrypt using legacy SteamKM1 encryption
                json_data = self._decrypt_legacy_json(encrypted_data, password)
                if json_data is None:
                    return False, "Invalid password or corrupted file", []
            else:
                # Read plain JSON
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
            
            # Parse JSON
            try:
                data = json.loads(json_data)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON format: {str(e)}", []
            
            # Convert legacy format to new format
            games = []
            
            # Legacy SteamKM1 format: {"category": {"game_title": "game_key"}}
            # or can be a flat dict: {"unique_id": {"title": "...", "key": "...", "category": "...", "app_id": "..."}}
            if isinstance(data, dict):
                for category_or_id, category_games in data.items():
                    if isinstance(category_games, dict):
                        # Check if this is a game entry (has 'title' and 'key')
                        if 'title' in category_games and 'key' in category_games:
                            # Flat format with unique IDs
                            games.append({
                                'title': category_games['title'],
                                'key': category_games['key'],
                                'platform': 'Steam',
                                'notes': f'Imported from SteamKM1: {Path(file_path).name}',
                                'tags': [category_games.get('category')] if category_games.get('category') else [],
                                'steam_app_id': category_games.get('app_id')  # Extract app_id if present
                            })
                        else:
                            # Nested format: category -> {title: key}
                            for title, key in category_games.items():
                                games.append({
                                    'title': title,
                                    'key': key,
                                    'platform': 'Steam',
                                    'notes': f'Imported from SteamKM1: {Path(file_path).name}',
                                    'tags': [category_or_id] if category_or_id else [],
                                    'steam_app_id': None  # No app_id in nested format
                                })
            
            if not games:
                return False, "No games found in JSON file", []
            
            return True, f"Found {len(games)} game(s) in legacy SteamKM1 file", games
        
        except Exception as e:
            return False, f"Failed to import legacy JSON: {str(e)}", []
    
    def _decrypt_legacy_json(self, encrypted_data: str, password: str) -> str | None:
        """Decrypt legacy SteamKM1 encrypted JSON data.
        
        Uses the same encryption method as the original SteamKM1 app.
        
        Args:
            encrypted_data: Base64 encoded encrypted data
            password: Decryption password
            
        Returns:
            Decrypted JSON string or None if decryption fails
        """
        try:
            # Decode base64
            raw = base64.b64decode(encrypted_data)
            
            # Extract salt, iv, and ciphertext
            # Legacy format: salt(16) + iv(16) + ciphertext
            if len(raw) < 32:
                return None
            
            salt = raw[:16]
            iv = raw[16:32]
            ciphertext = raw[32:]
            
            # Derive key using PBKDF2 (same as legacy)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000  # Legacy used 480000 iterations
            )
            key = kdf.derive(password.encode('utf-8'))
            
            # Decrypt using AES-CBC
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            
            try:
                plaintext = decryptor.update(ciphertext) + decryptor.finalize()
                # Remove PKCS7 padding
                padding_length = plaintext[-1]
                plaintext = plaintext[:-padding_length]
                return plaintext.decode('utf-8')
            except Exception:
                return None
        
        except Exception:
            return None
    
    def import_games_to_database(
        self, 
        games: list[dict], 
        skip_keys: set[str] | None = None,
        overwrite_keys: set[str] | None = None
    ) -> tuple[bool, str, list[int]]:
        """Import a list of games into the database.
        
        Args:
            games: List of game dictionaries with keys: title, key, platform, notes, tags, steam_app_id
            skip_keys: Set of game keys to skip (don't import these duplicates)
            overwrite_keys: Set of game keys to overwrite (update existing games)
            
        Returns:
            Tuple of (success: bool, message: str, game_ids: list[int])
        """
        skip_keys = skip_keys or set()
        overwrite_keys = overwrite_keys or set()
        
        try:
            added_count = 0
            skipped_count = 0
            overwritten_count = 0
            added_ids = []
            
            for game in games:
                title = game.get('title', 'Unknown Game')
                key = game.get('key', '')
                platform = game.get('platform', 'Steam')
                notes = game.get('notes', '')
                tag_names = game.get('tags', [])
                steam_app_id = game.get('steam_app_id')  # Extract Steam App ID
                
                if not key:
                    skipped_count += 1
                    continue
                
                # Check if this key should be skipped
                if key in skip_keys:
                    skipped_count += 1
                    continue
                
                # Check if this key should overwrite an existing entry
                if key in overwrite_keys:
                    existing = self.db_manager.get_game_by_key(key)
                    if existing:
                        # Process tags for overwrite
                        is_used = False
                        is_dlc = False
                        regular_tags = []
                        
                        for tag_name in tag_names:
                            if tag_name:
                                tag_lower = tag_name.lower()
                                if tag_lower == 'used':
                                    is_used = True
                                elif tag_lower == 'dlc':
                                    is_dlc = True
                                else:
                                    regular_tags.append(tag_name)
                        
                        # Get or create tags
                        tag_ids = []
                        for tag_name in regular_tags:
                            existing_tags = self.db_manager.get_tags()
                            tag_id = None
                            for tag in existing_tags:
                                if tag['name'].lower() == tag_name.lower():
                                    tag_id = tag['id']
                                    break
                            if tag_id is None:
                                tag_id = self.db_manager.add_tag(tag_name)
                            tag_ids.append(tag_id)
                        
                        # Update existing game
                        self.db_manager.update_game(
                            game_id=existing['id'],
                            title=title,
                            game_key=key,
                            platform_type=platform,
                            notes=notes,
                            tag_ids=tag_ids if tag_ids else None,
                            is_used=is_used,
                            dlc_enabled=is_dlc,
                            steam_app_id=steam_app_id
                        )
                        added_ids.append(existing['id'])
                        overwritten_count += 1
                        continue
                
                # Check for special categories that should be toggles
                is_used = False
                is_dlc = False
                regular_tags = []
                
                for tag_name in tag_names:
                    if tag_name:
                        tag_lower = tag_name.lower()
                        if tag_lower == 'used':
                            is_used = True
                        elif tag_lower == 'dlc':
                            is_dlc = True
                        else:
                            regular_tags.append(tag_name)
                
                # Get or create tags (only for non-special categories)
                tag_ids = []
                for tag_name in regular_tags:
                    # Check if tag exists
                    existing_tags = self.db_manager.get_tags()
                    tag_id = None
                    for tag in existing_tags:
                        if tag['name'].lower() == tag_name.lower():
                            tag_id = tag['id']
                            break
                    
                    # Create tag if it doesn't exist
                    if tag_id is None:
                        tag_id = self.db_manager.add_tag(tag_name)
                    
                    tag_ids.append(tag_id)
                
                # Add game to database with special toggles and Steam App ID
                game_id = self.db_manager.add_game(
                    title=title,
                    game_key=key,
                    platform_type=platform,
                    notes=notes,
                    tag_ids=tag_ids if tag_ids else None,
                    is_used=is_used,
                    dlc_enabled=is_dlc,
                    steam_app_id=steam_app_id  # Include Steam App ID
                )
                added_ids.append(game_id)
                added_count += 1
            
            if added_count == 0 and overwritten_count == 0:
                if skipped_count > 0:
                    return True, f"Skipped {skipped_count} duplicate(s), no new games imported", []
                return False, "No games were imported", []
            
            message_parts = []
            if added_count > 0:
                message_parts.append(f"imported {added_count} new game(s)")
            if overwritten_count > 0:
                message_parts.append(f"updated {overwritten_count} existing game(s)")
            if skipped_count > 0:
                message_parts.append(f"skipped {skipped_count}")
            
            message = "Successfully " + ", ".join(message_parts)
            return True, message, added_ids
        
        except Exception as e:
            return False, f"Failed to import games to database: {str(e)}", []

