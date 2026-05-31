"""Tests for the git version control API endpoints."""

from __future__ import annotations

from unittest.mock import patch

from httpx import AsyncClient

from tests.conftest import _bearer, _login_payload, _register_user


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    """Register a user and return bearer auth headers."""
    await _register_user(client, email="git-test@example.com")
    resp = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(email="git-test@example.com"),
    )
    token = resp.json()["access_token"]
    return _bearer(token)


# ---------------------------------------------------------------------------
# GET /api/v1/git/log
# ---------------------------------------------------------------------------


class TestGitLog:
    async def test_returns_entries(self, client: AsyncClient):
        headers = await _auth_headers(client)
        mock_entries = [
            {
                "commit": "abc123def456",
                "author": "admin",
                "email": "admin@blackbeard",
                "timestamp": "1700000000",
                "message": "create Agent/researcher",
            },
        ]
        with patch("blackbeard.api.git.get_log", return_value=mock_entries):
            resp = await client.get("/api/v1/git/log", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["entries"][0]["commit"] == "abc123def456"
        assert data["entries"][0]["author"] == "admin"

    async def test_passes_query_params(self, client: AsyncClient):
        headers = await _auth_headers(client)
        with patch("blackbeard.api.git.get_log", return_value=[]) as mock_log:
            resp = await client.get(
                "/api/v1/git/log",
                params={"kind": "Agent", "name": "foo", "project": "myproj", "limit": 10},
                headers=headers,
            )

        assert resp.status_code == 200
        mock_log.assert_called_once_with(kind="Agent", name="foo", project="myproj", limit=10)

    async def test_empty_log(self, client: AsyncClient):
        headers = await _auth_headers(client)
        with patch("blackbeard.api.git.get_log", return_value=[]):
            resp = await client.get("/api/v1/git/log", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["entries"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/git/diff
# ---------------------------------------------------------------------------


class TestGitDiff:
    async def test_returns_diff(self, client: AsyncClient):
        headers = await _auth_headers(client)
        diff_text = "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new"
        with patch("blackbeard.api.git.get_diff", return_value=diff_text):
            resp = await client.get("/api/v1/git/diff", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["diff"] == diff_text
        assert data["commit_a"] == "HEAD~1"
        assert data["commit_b"] == "HEAD"

    async def test_custom_commits(self, client: AsyncClient):
        headers = await _auth_headers(client)
        with patch("blackbeard.api.git.get_diff", return_value="") as mock_diff:
            resp = await client.get(
                "/api/v1/git/diff",
                params={"commit_a": "abc", "commit_b": "def"},
                headers=headers,
            )

        assert resp.status_code == 200
        mock_diff.assert_called_once_with(
            commit_a="abc", commit_b="def", kind=None, name=None, project="default",
        )


# ---------------------------------------------------------------------------
# GET /api/v1/git/blame/{kind}/{name}
# ---------------------------------------------------------------------------


class TestGitBlame:
    async def test_returns_blame(self, client: AsyncClient):
        headers = await _auth_headers(client)
        blame_output = "abc1234 (admin 2024-01-01 1) role: Analyst"
        with patch("blackbeard.api.git.get_blame", return_value=blame_output):
            resp = await client.get(
                "/api/v1/git/blame/Agent/researcher",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["blame"] == blame_output
        assert data["kind"] == "Agent"
        assert data["name"] == "researcher"

    async def test_returns_404_when_empty(self, client: AsyncClient):
        headers = await _auth_headers(client)
        with patch("blackbeard.api.git.get_blame", return_value=""):
            resp = await client.get(
                "/api/v1/git/blame/Agent/nonexistent",
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/v1/git/show/{commit}/{kind}/{name}
# ---------------------------------------------------------------------------


class TestGitShow:
    async def test_returns_content(self, client: AsyncClient):
        headers = await _auth_headers(client)
        yaml_content = "apiVersion: blackbeard/v1\nkind: Agent\nmetadata:\n  name: test\n"
        with patch("blackbeard.api.git.get_show", return_value=yaml_content):
            resp = await client.get(
                "/api/v1/git/show/abc123/Agent/test",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == yaml_content
        assert data["commit"] == "abc123"
        assert data["kind"] == "Agent"
        assert data["name"] == "test"

    async def test_returns_404_when_empty(self, client: AsyncClient):
        headers = await _auth_headers(client)
        with patch("blackbeard.api.git.get_show", return_value=""):
            resp = await client.get(
                "/api/v1/git/show/badcommit/Agent/missing",
                headers=headers,
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    async def test_passes_project_param(self, client: AsyncClient):
        headers = await _auth_headers(client)
        with patch("blackbeard.api.git.get_show", return_value="content") as mock_show:
            resp = await client.get(
                "/api/v1/git/show/abc/Crew/demo",
                params={"project": "staging"},
                headers=headers,
            )

        assert resp.status_code == 200
        mock_show.assert_called_once_with(
            commit="abc", kind="Crew", name="demo", project="staging",
        )
