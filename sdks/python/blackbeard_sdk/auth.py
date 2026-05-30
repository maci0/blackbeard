"""Authentication helpers for the Blackbeard SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


class AuthMixin:
    """Authentication methods mixed into BlackbeardClient."""

    _http: httpx.Client
    _token: str | None
    _api_key: str | None

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        raise NotImplementedError

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate with email and password.

        Returns an AuthResponse dict containing access_token, refresh_token,
        token_type, and user profile. The client automatically stores the
        access token for subsequent requests.
        """
        data: dict[str, Any] = self._send(
            "POST",
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        ).json()
        self._set_bearer_token(data["access_token"])
        return data

    def register(self, email: str, password: str, display_name: str) -> dict[str, Any]:
        """Register a new user account.

        Returns an AuthResponse dict. The client automatically stores the
        access token for subsequent requests.
        """
        data: dict[str, Any] = self._send(
            "POST",
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": display_name,
            },
        ).json()
        self._set_bearer_token(data["access_token"])
        return data

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new access token.

        Returns a TokenResponse dict. The client automatically updates
        the stored access token.
        """
        data: dict[str, Any] = self._send(
            "POST",
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        ).json()
        self._set_bearer_token(data["access_token"])
        return data

    def _set_bearer_token(self, token: str) -> None:
        """Switch auth to Bearer token, removing any API key header."""
        self._token = token
        self._api_key = None
        self._http.headers.pop("X-API-Key", None)
        self._http.headers["Authorization"] = f"Bearer {token}"

    def whoami(self) -> dict[str, Any]:
        """Get the currently authenticated user's profile."""
        return self._send("GET", "/api/v1/auth/me").json()

    def generate_api_key(self) -> dict[str, Any]:
        """Generate or rotate the current user's API key.

        Requires JWT Bearer authentication (not API key auth).
        Any previously issued key for this user is replaced.

        Returns:
            Dict with ``api_key`` containing the new ``bb-`` prefixed key.
        """
        return self._send("POST", "/api/v1/auth/api-key").json()

    def revoke_api_key(self) -> None:
        """Revoke the current user's API key. Idempotent.

        Requires JWT Bearer authentication (not API key auth).
        """
        self._send("DELETE", "/api/v1/auth/api-key")
