"""Tests for the interactive TUI shell module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from blackbeard_cli.shell import (
    DISPATCH,
    SHELL_COMMANDS,
    ShellCompleter,
    ShellState,
)

# ---------------------------------------------------------------------------
# ShellState
# ---------------------------------------------------------------------------


class TestShellState:
    def test_initialization(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="test-key-123",
            timeout=30.0,
        )
        assert state.server == "http://localhost:8000"
        assert state.project == "default"
        assert state.api_key == "test-key-123"
        assert state.timeout == 30.0

    def test_initialization_without_api_key(self):
        state = ShellState(
            server="http://example.com:9000",
            project="staging",
            api_key=None,
            timeout=10.0,
        )
        assert state.api_key is None
        assert state.project == "staging"

    def test_internal_cache_starts_empty(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=30.0,
        )
        assert state._resource_cache == {}
        assert state._cache_ts == 0.0


class TestShellStateHeaders:
    def test_returns_api_key_header(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="my-secret-key",
            timeout=30.0,
        )
        headers = state.headers()
        assert headers == {"X-API-Key": "my-secret-key"}

    def test_falls_back_to_jwt_token(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key=None,
            timeout=30.0,
        )
        with patch(
            "blackbeard_cli.credentials.get_valid_token", return_value="jwt-token-abc",
        ):
            headers = state.headers()

        assert headers == {"Authorization": "Bearer jwt-token-abc"}

    def test_returns_empty_when_no_credentials(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key=None,
            timeout=30.0,
        )
        with patch("blackbeard_cli.credentials.get_valid_token", return_value=None):
            headers = state.headers()

        assert headers == {}


class TestShellStateFetchResourceNames:
    def test_returns_names_from_api(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {"metadata": {"name": "agent-a"}},
                {"metadata": {"name": "agent-b"}},
            ],
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("blackbeard_cli.shell.httpx.Client", return_value=mock_client):
            names = state.fetch_resource_names("Agent")

        assert names == ["agent-a", "agent-b"]

    def test_returns_empty_for_unknown_kind(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        names = state.fetch_resource_names("NonexistentKind")
        assert names == []

    def test_caches_results(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        state._resource_cache["Agent"] = ["cached-agent"]
        state._cache_ts = 1e18  # far in the future so cache stays valid

        # Should return cached value without making HTTP calls
        names = state.fetch_resource_names("Agent")
        assert names == ["cached-agent"]


# ---------------------------------------------------------------------------
# ShellCompleter
# ---------------------------------------------------------------------------


class TestShellCompleter:
    def _make_document(self, text: str) -> MagicMock:
        doc = MagicMock()
        doc.text_before_cursor = text
        return doc

    def test_completes_command_names(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        completer = ShellCompleter(state)
        doc = self._make_document("he")

        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "help" in texts
        assert "health" in texts

    def test_completes_all_commands_from_empty(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        completer = ShellCompleter(state)
        doc = self._make_document("")

        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        for cmd in SHELL_COMMANDS:
            assert cmd in texts

    def test_completes_kind_after_ls(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        completer = ShellCompleter(state)
        doc = self._make_document("ls ")

        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "Agent" in texts
        assert "Crew" in texts
        assert "Task" in texts

    def test_completes_partial_kind(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        completer = ShellCompleter(state)
        doc = self._make_document("ls Ag")

        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "Agent" in texts
        assert "AgentPolicy" in texts


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_all_commands_have_handlers(self):
        # Every command listed in SHELL_COMMANDS (except exit/quit) should
        # have a handler in the dispatch table.
        for cmd in SHELL_COMMANDS:
            if cmd in ("exit", "quit"):
                continue
            assert cmd in DISPATCH, f"missing handler for '{cmd}'"

    def test_known_command_dispatches(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        handler = DISPATCH.get("help")
        assert handler is not None
        # help should run without error
        handler(state, [])

    def test_unknown_command_returns_none(self):
        handler = DISPATCH.get("nonexistent_command_xyz")
        assert handler is None

    def test_use_command_changes_project(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        handler = DISPATCH["use"]
        handler(state, ["staging"])
        assert state.project == "staging"

    def test_use_command_clears_cache(self):
        state = ShellState(
            server="http://localhost:8000",
            project="default",
            api_key="key",
            timeout=5.0,
        )
        state._resource_cache["Agent"] = ["old-agent"]

        handler = DISPATCH["use"]
        handler(state, ["production"])
        assert state._resource_cache == {}
