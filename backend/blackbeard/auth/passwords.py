"""Password hashing and verification using bcrypt with SHA-256 pre-hash.

bcrypt silently truncates inputs longer than 72 bytes.  Pre-hashing with
SHA-256 (hex-encoded = 64 chars, always under 72 bytes) eliminates this
limit so passwords of any length hash uniquely.  This is the same approach
used by Dropbox and Django.
"""

from __future__ import annotations

import hashlib

import bcrypt


def _prehash(plain: str) -> bytes:
    """SHA-256 pre-hash a password to fit within bcrypt's 72-byte limit."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(plain: str) -> str:
    """Hash a plaintext password using SHA-256 + bcrypt.

    Returns the hashed password as a UTF-8 string suitable for database storage.
    """
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Returns True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
