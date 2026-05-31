"""JWT credential storage for CLI authentication.

Stores credentials in ~/.config/blackbeard/credentials.json with 0600 permissions.
Handles auto-refresh of expired access tokens using the refresh token.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 15 min token minus 60s safety margin to refresh before expiry.
ACCESS_TOKEN_LIFETIME_S = 840

_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "blackbeard"
_CREDENTIALS_FILE = _CONFIG_DIR / "credentials.json"


@dataclass
class StoredCredentials:
    """Typed wrapper around stored credentials."""

    server: str
    access_token: str
    refresh_token: str
    email: str
    expires_at: float


def load_credentials() -> StoredCredentials | None:
    """Load credentials from disk. Returns None if missing or corrupt."""
    if not _CREDENTIALS_FILE.exists():
        return None
    try:
        data = json.loads(_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        return StoredCredentials(
            server=data["server"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            email=data["email"],
            expires_at=float(data["expires_at"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.debug("Credentials file corrupt or incompatible — ignoring", exc_info=True)
        return None


def save_credentials(
    server: str,
    access_token: str,
    refresh_token: str,
    email: str,
    expires_at: float,
) -> None:
    """Write credentials to disk with 0600 permissions."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(_CONFIG_DIR, 0o700)

    data: dict[str, Any] = {
        "server": server,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "email": email,
        "expires_at": expires_at,
    }

    fd = os.open(str(_CREDENTIALS_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def clear_credentials() -> bool:
    """Remove the credentials file. Returns True if file existed."""
    if _CREDENTIALS_FILE.exists():
        _CREDENTIALS_FILE.unlink()
        return True
    return False


def _refresh_token(server: str, refresh_token: str, timeout: float) -> StoredCredentials | None:
    """Exchange refresh token for a new access token."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{server}/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        if resp.status_code != 200:
            logger.debug("Token refresh returned HTTP %d", resp.status_code)
            return None
        data = resp.json()
        return StoredCredentials(
            server=server,
            access_token=data["access_token"],
            refresh_token=refresh_token,
            email="",
            expires_at=time.time() + ACCESS_TOKEN_LIFETIME_S,
        )
    except (httpx.RequestError, KeyError, TypeError):
        logger.debug("Token refresh failed", exc_info=True)
        return None


def get_valid_token(server: str, timeout: float) -> str | None:
    """Load credentials, auto-refresh if expired, return access_token or None.

    Returns None if no stored credentials, wrong server, or refresh fails.
    """
    creds = load_credentials()
    if creds is None:
        return None

    if creds.server.rstrip("/") != server.rstrip("/"):
        return None

    if creds.expires_at > time.time() + 30:
        return creds.access_token

    refreshed = _refresh_token(server, creds.refresh_token, timeout)
    if refreshed is None:
        return None

    save_credentials(
        server=server,
        access_token=refreshed.access_token,
        refresh_token=creds.refresh_token,
        email=creds.email,
        expires_at=refreshed.expires_at,
    )
    return refreshed.access_token
