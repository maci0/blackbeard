"""Password hashing and verification using bcrypt with SHA-256 pre-hash.

bcrypt silently truncates inputs longer than 72 bytes.  Pre-hashing with
SHA-256 (hex-encoded = 64 chars, always under 72 bytes) eliminates this
limit so passwords of any length hash uniquely.  This is the same approach
used by Dropbox and Django.
"""

from __future__ import annotations

import hashlib
import hmac

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
    Invalid or corrupted hashes return False (never raise) so login timing
    stays uniform and callers cannot distinguish corrupt hashes from wrong
    passwords via exception paths.
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def secrets_equal(provided: str, expected: str) -> bool:
    """Compare two secret strings without leaking length via short-circuit.

    Hashes both sides to fixed-size digests, then uses ``hmac.compare_digest``.
    Safe for API keys, webhook secrets, and similar high-entropy tokens.
    Empty strings never match (including empty == empty).
    """
    if not provided or not expected:
        # Still exercise a full-length digest compare so empty vs non-empty
        # callers do not take a dramatically shorter path.
        dummy = hashlib.sha256(b"").digest()
        hmac.compare_digest(dummy, dummy)
        return False
    return hmac.compare_digest(
        hashlib.sha256(provided.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )
