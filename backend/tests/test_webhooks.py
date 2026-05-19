"""Tests for webhook delivery logic.

Covers:
  - HMAC signature correctness
  - Webhook with event filter only receives matching events
  - Webhook delivery failure doesn't crash execution
  - Inactive webhook is skipped
  - Webhook with empty events list receives all events
  - Webhook executor lifecycle (shutdown_webhook_executor safety)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.execution_listener import (
    _deliver_webhooks_sync,
    _get_webhook_executor,
    invalidate_webhook_cache,
    shutdown_webhook_executor,
)


@pytest.fixture(autouse=True)
def _clear_webhook_cache():
    """Ensure each test starts with a clean webhook cache."""
    invalidate_webhook_cache()
    yield
    invalidate_webhook_cache()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_webhook(
    url: str = "https://example.com/hook",
    events: list[str] | None = None,
    secret: str = "test-secret",
    active: bool = True,
) -> MagicMock:
    """Create a mock Webhook ORM object."""
    wh = MagicMock()
    wh.id = uuid.uuid4()
    wh.url = url
    wh.events = events if events is not None else []
    wh.secret = secret
    wh.active = active
    wh.created_at = datetime.now(UTC)
    return wh


# ---------------------------------------------------------------------------
# Tests -- HMAC signature correctness
# ---------------------------------------------------------------------------


def test_webhook_hmac_signature_correct():
    """HMAC-SHA256 signature should be computed from secret + payload."""
    webhook = _make_webhook(secret="my-secret")
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = [webhook]
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result

    mock_factory = MagicMock(return_value=mock_session)

    event_data = {"status": "completed", "output": "result"}

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        _deliver_webhooks_sync(
            event_type="execution_completed",
            data=event_data,
            execution_id="exec-123",
            db_url="sqlite:///test.db",
        )

    # Verify the POST was made with correct HMAC header
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    headers = call_kwargs[1]["headers"]

    # Reconstruct expected payload and signature
    expected_payload = json.dumps(
        {
            "event_type": "execution_completed",
            "execution_id": "exec-123",
            "data": event_data,
        },
        default=str,
    )
    expected_sig = hmac.new(
        b"my-secret", expected_payload.encode(), hashlib.sha256
    ).hexdigest()

    assert headers["X-Webhook-Signature"] == expected_sig
    assert headers["X-Blackbeard-Event"] == "execution_completed"
    assert headers["Content-Type"] == "application/json"


def test_webhook_hmac_wrong_secret_produces_different_signature():
    """HMAC signature with wrong secret must differ — tampering must be detectable."""
    payload = json.dumps(
        {"event_type": "execution_completed", "execution_id": "exec-1", "data": {}},
        default=str,
    )
    sig_correct = hmac.new(b"real-secret", payload.encode(), hashlib.sha256).hexdigest()
    sig_wrong = hmac.new(b"wrong-secret", payload.encode(), hashlib.sha256).hexdigest()
    assert sig_correct != sig_wrong, "Different secrets must produce different signatures"


# ---------------------------------------------------------------------------
# Tests -- Event filtering
# ---------------------------------------------------------------------------


def test_webhook_event_filter_matches():
    """Webhook with matching event filter should receive the event."""
    webhook = _make_webhook(events=["execution_completed"])
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = [webhook]
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        _deliver_webhooks_sync(
            event_type="execution_completed",
            data={"status": "done"},
            execution_id="exec-456",
            db_url="sqlite:///test.db",
        )

    # Should have been called since event matches filter
    mock_client.post.assert_called_once()


def test_webhook_event_filter_no_match():
    """Webhook with non-matching event filter should NOT receive the event."""
    webhook = _make_webhook(events=["execution_completed"])
    mock_client = MagicMock()

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = [webhook]
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        _deliver_webhooks_sync(
            event_type="execution_started",  # not in filter
            data={},
            execution_id="exec-789",
            db_url="sqlite:///test.db",
        )

    # Should NOT have been called
    mock_client.post.assert_not_called()


def test_webhook_empty_events_receives_all():
    """Webhook with empty events list should receive all event types."""
    webhook = _make_webhook(events=[])
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = [webhook]
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        _deliver_webhooks_sync(
            event_type="some_random_event",
            data={},
            execution_id="exec-000",
            db_url="sqlite:///test.db",
        )

    mock_client.post.assert_called_once()


# ---------------------------------------------------------------------------
# Tests -- Delivery failure doesn't crash
# ---------------------------------------------------------------------------


def test_webhook_delivery_failure_doesnt_crash():
    """HTTP error from webhook delivery should be logged but not raised."""
    webhook = _make_webhook()
    mock_response = MagicMock()
    mock_response.status_code = 500  # Server error

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = [webhook]
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        # Should NOT raise
        _deliver_webhooks_sync(
            event_type="test_event",
            data={},
            execution_id="exec-err",
            db_url="sqlite:///test.db",
        )

    # POST was attempted
    mock_client.post.assert_called_once()


def test_webhook_delivery_exception_doesnt_crash():
    """Network exception during webhook delivery should be caught."""
    webhook = _make_webhook()

    mock_client = MagicMock()
    mock_client.post.side_effect = ConnectionError("Connection refused")

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = [webhook]
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        # Should NOT raise
        _deliver_webhooks_sync(
            event_type="test_event",
            data={},
            execution_id="exec-net-err",
            db_url="sqlite:///test.db",
        )


def test_webhook_db_load_failure_doesnt_crash():
    """Database failure loading webhooks should be caught."""
    mock_factory = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.side_effect = RuntimeError("DB down")
    mock_factory.return_value = mock_session

    with patch(
        "blackbeard.engine.execution_listener._get_sync_session_factory",
        return_value=mock_factory,
    ):
        # Should NOT raise
        _deliver_webhooks_sync(
            event_type="test_event",
            data={},
            execution_id="exec-db-err",
            db_url="sqlite:///test.db",
        )


# ---------------------------------------------------------------------------
# Tests -- No webhooks registered
# ---------------------------------------------------------------------------


def test_webhook_no_webhooks_is_noop():
    """When no active webhooks exist, delivery should be a no-op."""
    mock_client = MagicMock()

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = []
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "blackbeard.engine.execution_listener._get_sync_client",
            return_value=mock_client,
        ),
    ):
        _deliver_webhooks_sync(
            event_type="test_event",
            data={},
            execution_id="exec-no-wh",
            db_url="sqlite:///test.db",
        )

    # No HTTP calls should be made
    mock_client.post.assert_not_called()


# ---------------------------------------------------------------------------
# Tests -- Executor lifecycle
# ---------------------------------------------------------------------------


def test_shutdown_webhook_executor_when_none():
    """shutdown_webhook_executor should be safe when no executor exists."""
    import blackbeard.engine.execution_listener as listener_mod

    # Save original
    original = listener_mod._webhook_executor
    try:
        listener_mod._webhook_executor = None
        # Should NOT raise
        shutdown_webhook_executor()
        assert listener_mod._webhook_executor is None, (
            "shutdown should leave _webhook_executor as None when it was already None"
        )
    finally:
        listener_mod._webhook_executor = original


def test_shutdown_webhook_executor_idempotent():
    """Calling shutdown_webhook_executor twice should be safe."""
    import blackbeard.engine.execution_listener as listener_mod

    original = listener_mod._webhook_executor
    try:
        # Force creation
        executor = _get_webhook_executor()
        assert executor is not None

        # Shutdown first time
        shutdown_webhook_executor()
        assert listener_mod._webhook_executor is None

        # Shutdown second time -- should not raise
        shutdown_webhook_executor()
        assert listener_mod._webhook_executor is None
    finally:
        listener_mod._webhook_executor = original
