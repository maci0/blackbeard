"""Tests for functions with zero or minimal test coverage.

Targets the 5 functions with no coverage and 8 with partial coverage
identified by cross-referencing function definitions against the
coverage-missing-lines report.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# 1. collaboration.publish_raw + unsubscribe
# ---------------------------------------------------------------------------


class TestCollabFunctions:
    @pytest.mark.asyncio
    async def test_publish_raw_calls_redis(self) -> None:
        from blackbeard.api.collaboration import ValkeyCollabBackend

        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis
            backend = ValkeyCollabBackend()
            await backend.publish_raw("room1", '{"type":"test"}')
            mock_redis.publish.assert_called_once_with("collab:room1", '{"type":"test"}')

    @pytest.mark.asyncio
    async def test_publish_raw_handles_error(self) -> None:
        from blackbeard.api.collaboration import ValkeyCollabBackend

        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.publish.side_effect = ConnectionError("down")
            mock_from_url.return_value = mock_redis
            backend = ValkeyCollabBackend()
            await backend.publish_raw("room1", "{}")  # should not raise

    @pytest.mark.asyncio
    async def test_unsubscribe_cancels(self) -> None:
        from blackbeard.api.collaboration import ValkeyCollabBackend

        with patch("redis.asyncio.from_url", return_value=AsyncMock()):
            backend = ValkeyCollabBackend()
            task = MagicMock()
            backend._subscriptions["r1"] = task
            await backend.unsubscribe("r1")
            task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_noop(self) -> None:
        from blackbeard.api.collaboration import ValkeyCollabBackend

        with patch("redis.asyncio.from_url", return_value=AsyncMock()):
            backend = ValkeyCollabBackend()
            await backend.unsubscribe("nonexistent")


# ---------------------------------------------------------------------------
# 2. oidc_login + _ensure_oauth
# ---------------------------------------------------------------------------


class TestOidc:
    @pytest.mark.asyncio
    async def test_login_redirects(self) -> None:
        from blackbeard.api.oidc import oidc_login

        mock_oauth = MagicMock()
        mock_oauth.provider.authorize_redirect = AsyncMock(
            return_value=MagicMock(status_code=307)
        )
        req = MagicMock()
        req.url_for.return_value = "http://localhost/cb"

        with (
            patch("blackbeard.api.oidc._ensure_oauth", return_value=mock_oauth),
            patch("blackbeard.api.oidc.settings") as ms,
        ):
            ms.oidc_redirect_uri = ""
            result = await oidc_login(req)
            assert result.status_code == 307

    @pytest.mark.asyncio
    async def test_ensure_oauth_creates(self) -> None:
        import blackbeard.api.oidc as mod

        mod._oauth = None
        mock_oauth_instance = MagicMock()
        mock_oauth_cls = MagicMock(return_value=mock_oauth_instance)
        mock_oauth_instance.register = MagicMock()

        mock_secret = MagicMock()
        mock_secret.get_secret_value.return_value = "test-secret-value"
        ms = MagicMock()
        ms.oidc_issuer = "https://example.com"
        ms.oidc_client_id = "id"
        ms.oidc_client_secret = mock_secret
        ms.oidc_scopes = "openid"

        with (
            patch.object(mod, "settings", ms),
            patch.object(mod, "OAuth", mock_oauth_cls),
        ):

            result = await mod._ensure_oauth()
            assert result is mock_oauth_instance


# ---------------------------------------------------------------------------
# 3. main.lifespan
# ---------------------------------------------------------------------------


class TestLifespan:
    @pytest.mark.asyncio
    async def test_runs(self) -> None:
        from blackbeard.main import lifespan

        ms = AsyncMock()
        mr = MagicMock()
        mr.scalars.return_value.all.return_value = []
        ms.execute.return_value = mr

        with (
            patch("blackbeard.main._validate_startup_config"),
            patch("blackbeard.main.async_session") as ctx,
            patch("blackbeard.main.engine") as eng,
            patch("blackbeard.main.shutdown_executor"),
            patch("blackbeard.main.close_all_clients"),
            patch("blackbeard.main.shutdown_health_clients"),
            patch("blackbeard.main.shutdown_otel"),
            patch("blackbeard.main.shutdown_webhook_executor"),
            patch("blackbeard.main.recover_stale_executions", new_callable=AsyncMock),
        ):
            ctx.return_value.__aenter__ = AsyncMock(return_value=ms)
            ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            eng.dispose = AsyncMock()
            async with lifespan(MagicMock()):
                pass


# ---------------------------------------------------------------------------
# 4. chat helpers
# ---------------------------------------------------------------------------


class TestChatHelpers:
    def test_parse_retry_after(self) -> None:
        from blackbeard.api.chat import _parse_retry_after

        resp = MagicMock()
        resp.headers.get.return_value = "30"
        assert _parse_retry_after(resp) == "30"

    def test_parse_retry_after_clamped(self) -> None:
        from blackbeard.api.chat import _parse_retry_after

        resp = MagicMock()
        resp.headers.get.return_value = "99999"
        assert _parse_retry_after(resp) == "3600"

    def test_parse_retry_after_invalid(self) -> None:
        from blackbeard.api.chat import _parse_retry_after

        resp = MagicMock()
        resp.headers.get.return_value = "xyz"
        assert _parse_retry_after(resp) == "30"

    def test_extract_content_valid(self) -> None:
        from blackbeard.api.chat import _extract_content

        data = {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        content, _usage, finish = _extract_content(data)
        assert content == "hi"
        assert finish == "stop"

    def test_extract_content_empty(self) -> None:
        from blackbeard.api.chat import _extract_content

        content, _usage, _finish = _extract_content({"choices": []})
        assert content == ""

    @given(val=st.text(max_size=20))
    @settings(max_examples=20)
    def test_fuzz_retry_after(self, val: str) -> None:
        from blackbeard.api.chat import _parse_retry_after

        resp = MagicMock()
        resp.headers.get.return_value = val
        result = _parse_retry_after(resp)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 5. resources._resolve_kind
# ---------------------------------------------------------------------------


class TestResolveKind:
    def test_valid(self) -> None:
        from blackbeard.api.resources import _resolve_kind

        assert _resolve_kind("agents") == "Agent"

    def test_invalid_raises(self) -> None:
        from fastapi import HTTPException

        from blackbeard.api.resources import _resolve_kind

        with pytest.raises(HTTPException):
            _resolve_kind("nope")

    @given(plural=st.text(min_size=1, max_size=30))
    @settings(max_examples=20)
    def test_fuzz(self, plural: str) -> None:
        from fastapi import HTTPException

        from blackbeard.api.resources import _resolve_kind

        with contextlib.suppress(HTTPException):
            _resolve_kind(plural)


# ---------------------------------------------------------------------------
# 6. executions._StreamEvent
# ---------------------------------------------------------------------------


class TestStreamEvent:
    def test_init(self) -> None:
        from blackbeard.api.executions import _StreamEvent

        ev = _StreamEvent(kind="event", data={"k": "v"}, event_type="test")
        assert ev.kind == "event"

    def test_heartbeat(self) -> None:
        from blackbeard.api.executions import _StreamEvent

        ev = _StreamEvent(kind="heartbeat", data={"status": "running"})
        assert ev.event_type == ""
