"""Fuzz tests for internal engine and API helper functions.

Targets functions in executor, execution_listener, flow_runner,
scheduler, sse, and litellm modules that were previously untested.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# 1. executor._sanitize_error
# ---------------------------------------------------------------------------


@given(error_msg=st.text(min_size=0, max_size=2000))
@settings(max_examples=100)
def test_fuzz_sanitize_error(error_msg):
    from blackbeard.engine.executor import _sanitize_error

    result = _sanitize_error(error_msg)
    assert isinstance(result, str)
    assert len(result) <= 510  # 500 + "..."


# ---------------------------------------------------------------------------
# 2. executions._poll_backoff
# ---------------------------------------------------------------------------


@given(polls=st.integers(min_value=0, max_value=10000))
@settings(max_examples=100)
def test_fuzz_poll_backoff(polls):
    from blackbeard.api.executions import _poll_backoff

    result = _poll_backoff(polls)
    assert result in (1, 3, 5)


# ---------------------------------------------------------------------------
# 3. executions._serialize_event
# ---------------------------------------------------------------------------


@given(
    seq=st.integers(min_value=0, max_value=100000),
    event_type=st.text(min_size=1, max_size=50),
    data_keys=st.dictionaries(
        st.text(min_size=1, max_size=20),
        st.one_of(st.text(max_size=100), st.integers(), st.none()),
        max_size=10,
    ),
)
@settings(max_examples=50)
def test_fuzz_serialize_event(seq, event_type, data_keys):
    from datetime import UTC, datetime

    from blackbeard.api.executions import _serialize_event

    mock_event = MagicMock()
    mock_event.sequence = seq
    mock_event.event_type = event_type
    mock_event.timestamp = datetime.now(UTC)
    mock_event.data = data_keys

    result = _serialize_event(mock_event)
    assert isinstance(result, dict)
    assert result["sequence"] == seq
    assert "timestamp" in result


# ---------------------------------------------------------------------------
# 4. execution_listener._get_webhook_hostname
# ---------------------------------------------------------------------------


@given(url=st.text(min_size=0, max_size=500))
@settings(max_examples=100)
def test_fuzz_get_webhook_hostname(url):
    from blackbeard.engine.execution_listener import _get_webhook_hostname

    result = _get_webhook_hostname(url)
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# 5. execution_listener._log_webhook_future_exception
# ---------------------------------------------------------------------------


def test_fuzz_log_webhook_future_no_crash():
    from blackbeard.engine.execution_listener import _log_webhook_future_exception

    # Future with no exception
    mock_future = MagicMock()
    mock_future.exception.return_value = None
    _log_webhook_future_exception(mock_future)

    # Future with exception
    mock_future.exception.return_value = RuntimeError("test")
    _log_webhook_future_exception(mock_future)

    # Future that raises on .exception()
    mock_future.exception.side_effect = Exception("cancelled")
    _log_webhook_future_exception(mock_future)


# ---------------------------------------------------------------------------
# 6. flow_runner.call_hook
# ---------------------------------------------------------------------------


@given(
    hook_path=st.text(min_size=1, max_size=100),
    hook_name=st.text(min_size=1, max_size=50),
)
@settings(max_examples=50)
def test_fuzz_call_hook(hook_path, hook_name):
    from blackbeard.engine.flow_runner import call_hook

    mock_loader = MagicMock()
    mock_loader.import_callable.return_value = None
    call_hook(mock_loader, hook_path, {"test": True}, hook_name)


# ---------------------------------------------------------------------------
# 7. sse.SSEState
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_acquire_release():
    from blackbeard.sse import acquire_stream, get_active_count, get_status

    async with acquire_stream() as ok:
        assert isinstance(ok, bool)
    assert get_active_count() >= 0
    status = get_status()
    assert "active" in status
    assert "max" in status


# ---------------------------------------------------------------------------
# 8. scheduler.AutomationScheduler init
# ---------------------------------------------------------------------------


def test_scheduler_init():
    from blackbeard.engine.scheduler import AutomationScheduler

    scheduler = AutomationScheduler()
    assert scheduler._running is False
    assert scheduler._tasks == {}


# ---------------------------------------------------------------------------
# 9. model_sync helpers
# ---------------------------------------------------------------------------


def test_litellm_build_params_with_api_key():
    """_build_litellm_params propagates api_key_env into result."""
    from blackbeard.litellm.model_sync import _build_litellm_params

    result = _build_litellm_params({
        "provider": "anthropic",
        "model": "claude-3-opus",
        "api_key_env": "ANTHROPIC_API_KEY",
    })
    assert result["model"] == "anthropic/claude-3-opus"
    assert result["api_key"] == "os.environ/ANTHROPIC_API_KEY"


def test_litellm_build_params():
    """_build_litellm_params should handle arbitrary specs without crashing."""
    from blackbeard.litellm.model_sync import _build_litellm_params

    result = _build_litellm_params({"provider": "ollama", "model": "llama3"})
    assert isinstance(result, dict)
    assert "model" in result
    assert result["model"] == "ollama/llama3"


# ---------------------------------------------------------------------------
# 10. executor.get_pool_status
# ---------------------------------------------------------------------------


def test_pool_status_no_executor():
    from blackbeard.engine.executor import _executor_lock, get_pool_status

    with _executor_lock:
        import blackbeard.engine.executor as _mod

        saved = _mod._executor
        _mod._executor = None
    try:
        status = get_pool_status()
        assert isinstance(status, dict)
        assert status["active_threads"] == 0
        assert status["saturated"] is False
    finally:
        with _executor_lock:
            _mod._executor = saved


# ---------------------------------------------------------------------------
# 11. execution_listener.invalidate_webhook_cache
# ---------------------------------------------------------------------------


def test_invalidate_webhook_cache():
    import blackbeard.engine.execution_listener as _mod
    from blackbeard.engine.execution_listener import invalidate_webhook_cache

    _mod._webhook_cache_entry = (0.0, [])
    invalidate_webhook_cache()
    assert _mod._webhook_cache_entry is None


# ---------------------------------------------------------------------------
# 12. loader._build_knowledge_source — with mock
# ---------------------------------------------------------------------------


@given(source_type=st.sampled_from(["text", "pdf", "csv", "json", "string"]))
@settings(max_examples=10)
def test_fuzz_ks_type_map(source_type):
    from blackbeard.engine.loader import _KS_TYPE_MAP

    assert source_type in _KS_TYPE_MAP
    module_path, class_name = _KS_TYPE_MAP[source_type]
    assert isinstance(module_path, str)
    assert isinstance(class_name, str)
