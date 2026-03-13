"""Helpers for encrypting and decrypting the SteamKM2 database file."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


META_VERSION = 1
PBKDF2_ITERATIONS = 220_000
NONCE_SIZE = 12
KEY_SIZE = 32
SALT_SIZE = 16


class InvalidPasswordError(ValueError):
    """Raised when an incorrect password is provided for decryption."""


class EncryptionManager:
    """Encrypts and decrypts the SQLite database using AES-GCM."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def is_encrypted(self) -> bool:
        # Single-file format: presence of .enc indicates encryption
        return self._encrypted_path().exists()

    def enable(self, password: str) -> None:
        """Encrypt the plaintext database file using a new password."""
        if self.is_encrypted():
            raise RuntimeError("Database is already encrypted.")
        plain_path = Path(self.db_path)
        if not plain_path.exists():
            # Create an empty database file so we have something to encrypt
            plain_path.touch()
        plaintext = plain_path.read_bytes()
        salt = os.urandom(SALT_SIZE)
        key = self._derive_key(password, salt, PBKDF2_ITERATIONS)
        nonce, ciphertext = self._encrypt(plaintext, key)
        # Store metadata in-memory then write combined .enc file
        self._last_written_meta = (salt, PBKDF2_ITERATIONS)
        self._write_encrypted(nonce, ciphertext)
        plain_path.unlink(missing_ok=True)

    def disable(self, password: str) -> None:
        """Decrypt the database file and write plaintext back to the original path."""
        plaintext = self.decrypt(password)
        Path(self.db_path).write_bytes(plaintext)
        self._encrypted_path().unlink(missing_ok=True)
        # No separate .meta file is used in single-file format

    def decrypt(self, password: str) -> bytes:
        """Return decrypted database bytes using the provided password."""
        if not self.is_encrypted():
            raise RuntimeError("Database is not encrypted.")
        # Read encrypted data first to populate header-derived metadata
        nonce, ciphertext = self._read_encrypted()
        salt, iterations = self._read_metadata()
        key = self._derive_key(password, salt, iterations)
        try:
            return self._decrypt(nonce, ciphertext, key)
        except Exception as exc:  # cryptography raises InvalidTag on failure
            raise InvalidPasswordError("Incorrect password") from exc

    def decrypt_to_temp(self, password: str) -> Tuple[str, bytes]:
        """Decrypt into a temporary file, returning (path, key)."""
        plaintext = self.decrypt(password)
        # _read_encrypted was called during decrypt, so metadata should be populated
        salt, iterations = self._read_metadata()
        key = self._derive_key(password, salt, iterations)
        temp_dir = tempfile.mkdtemp(prefix="steamkm2_db_")
        temp_path = Path(temp_dir) / "keys.db"
        temp_path.write_bytes(plaintext)
        return str(temp_path), key

    def reencrypt_from_plain(self, path: str, key: bytes) -> None:
        """Re-encrypt the plaintext database found at *path* using the supplied key."""
        data = Path(path).read_bytes()
        nonce, ciphertext = self._encrypt(data, key)
        # Ensure we have metadata available to include in the .enc header.
        # Try to read existing metadata from the file; if not present, _read_metadata
        # may fall back to legacy .meta (if any). This preserves parameters.
        try:
            # Populate _last_read_meta by parsing current .enc (if present)
            if self._encrypted_path().exists():
                try:
                    self._read_encrypted()
                except Exception:
                    pass
            salt, iterations = self._read_metadata()
            self._last_written_meta = (salt, iterations)
        except Exception:
            # If no metadata available, generate new salt/iterations
            salt = os.urandom(SALT_SIZE)
            iterations = PBKDF2_ITERATIONS
            self._last_written_meta = (salt, iterations)

        self._write_encrypted(nonce, ciphertext)

    def change_password(self, current_password: str, new_password: str, *, plaintext_path: str | None = None) -> bytes:
        """Change the database password and return the key derived from the new password."""
        if not self.is_encrypted():
            raise RuntimeError("Database is not encrypted.")
        if plaintext_path:
            # Verify the existing password before re-encrypting using the current plaintext copy.
            self.decrypt(current_password)
            data = Path(plaintext_path).read_bytes()
        else:
            data = self.decrypt(current_password)
        salt = os.urandom(SALT_SIZE)
        key = self._derive_key(new_password, salt, PBKDF2_ITERATIONS)
        nonce, ciphertext = self._encrypt(data, key)
        # set metadata then write combined file
        self._last_written_meta = (salt, PBKDF2_ITERATIONS)
        self._write_encrypted(nonce, ciphertext)
        return key

    def cleanup_temp(self, path: str | None) -> None:
        if not path:
            return
        p = Path(path)
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass
        try:
            parent = p.parent
            if parent.exists():
                parent.rmdir()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _derive_key(self, password: str, salt: bytes, iterations: int) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=iterations,
        )
        return kdf.derive(password.encode("utf-8"))

    def _encrypt(self, data: bytes, key: bytes) -> Tuple[bytes, bytes]:
        nonce = os.urandom(NONCE_SIZE)
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(nonce, data, None)
        return nonce, ciphertext

    def _decrypt(self, nonce: bytes, ciphertext: bytes, key: bytes) -> bytes:
        cipher = AESGCM(key)
        return cipher.decrypt(nonce, ciphertext, None)

    def _write_encrypted(self, nonce: bytes, ciphertext: bytes) -> None:
        # Write a single .enc file containing a small header with KDF params
        # Header format (versioned):
        # 4 bytes: MAGIC b'SKM2'
        # 1 byte: version (1)
        # 2 bytes: salt length (big-endian)
        # salt bytes
        # 4 bytes: iterations (big-endian)
        # 2 bytes: nonce length (big-endian)
        # nonce bytes
        # remaining bytes: ciphertext
        salt, iterations = self._last_written_meta
        magic = b'SKM2'
        version = (META_VERSION).to_bytes(1, 'big')
        salt_len = len(salt).to_bytes(2, 'big')
        iterations_b = int(iterations).to_bytes(4, 'big')
        nonce_len = len(nonce).to_bytes(2, 'big')
        payload = magic + version + salt_len + salt + iterations_b + nonce_len + nonce + ciphertext
        # Atomic write
        tmp = self._encrypted_path().with_suffix('.enc.tmp')
        tmp.write_bytes(payload)
        tmp.replace(self._encrypted_path())

    def _read_encrypted(self) -> Tuple[bytes, bytes]:
        data = self._encrypted_path().read_bytes()
        # Try to parse header. If no header present, fall back to legacy format
        # legacy: payload = nonce(12) + ciphertext
        if data.startswith(b'SKM2'):
            # Parse new header
            idx = 4
            version = data[idx]
            idx += 1
            if version != META_VERSION:
                raise RuntimeError(f"Unsupported encrypted file version: {version}")
            salt_len = int.from_bytes(data[idx:idx+2], 'big')
            idx += 2
            salt = data[idx:idx+salt_len]
            idx += salt_len
            iterations = int.from_bytes(data[idx:idx+4], 'big')
            idx += 4
            nonce_len = int.from_bytes(data[idx:idx+2], 'big')
            idx += 2
            nonce = data[idx:idx+nonce_len]
            idx += nonce_len
            ciphertext = data[idx:]
            # store last read meta for potential re-encrypt operations
            self._last_read_meta = (salt, iterations)
            return nonce, ciphertext
        else:
            # Legacy format: first NONCE_SIZE bytes are nonce
            if len(data) < NONCE_SIZE:
                raise RuntimeError("Encrypted payload is malformed.")
            nonce = data[:NONCE_SIZE]
            ciphertext = data[NONCE_SIZE:]
            # No metadata available in-file for legacy; _read_metadata will be used
            self._last_read_meta = None
            return nonce, ciphertext

    def _write_metadata(self, salt: bytes, iterations: int) -> None:
        # For backward compatibility we still keep the method, but we also
        # store the last written metadata in memory so the combined .enc write
        # can include it. We intentionally stop writing a separate .meta file
        # to produce a single-file encrypted DB.
        self._last_written_meta = (salt, iterations)

    def _read_metadata(self) -> Tuple[bytes, int]:
        # Prefer metadata read during _read_encrypted (new single-file format)
        if hasattr(self, '_last_read_meta') and self._last_read_meta:
            return self._last_read_meta

        # Fallback: try to read legacy .meta file (not written by new code)
        meta_path = self._meta_path()
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="ascii"))
            salt = base64.b64decode(meta["salt"])
            iterations = int(meta.get("iterations", PBKDF2_ITERATIONS))
            return salt, iterations

        raise RuntimeError("Metadata for encrypted database not found")

    def _encrypted_path(self) -> Path:
        return Path(f"{self.db_path}.enc")

    def _meta_path(self) -> Path:
        return Path(f"{self.db_path}.meta")
