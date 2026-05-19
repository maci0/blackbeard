"""Authentication helpers for the Blackbeard SDK."""

from __future__ import annotations

from typing import Any

import httpx


class AuthMixin:
    """Authentication methods mixed into BlackbeardClient."""

    _http: httpx.Client

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate with email and password.

        Returns an AuthResponse dict containing access_token, refresh_token,
        token_type, and user profile. The client automatically stores the
        access token for subsequent requests.
        """
        resp = self._http.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        # Store the token so subsequent requests are authenticated
        self._http.headers["Authorization"] = f"Bearer {data['access_token']}"
        return data

    def register(self, email: str, password: str, display_name: str) -> dict[str, Any]:
        """Register a new user account.

        Returns an AuthResponse dict. The client automatically stores the
        access token for subsequent requests.
        """
        resp = self._http.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": display_name,
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        self._http.headers["Authorization"] = f"Bearer {data['access_token']}"
        return data

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new access token.

        Returns a TokenResponse dict. The client automatically updates
        the stored access token.
        """
        resp = self._http.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        self._http.headers["Authorization"] = f"Bearer {data['access_token']}"
        return data

    def whoami(self) -> dict[str, Any]:
        """Get the currently authenticated user's profile."""
        resp = self._http.get("/api/v1/auth/me")
        resp.raise_for_status()
        return resp.json()
