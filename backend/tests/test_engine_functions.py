"""Unit tests for untested engine, API, and infrastructure functions.

Covers executor, execution_listener, flow_runner, scheduler, loader,
litellm/model_sync, sse, and api/executions helpers. Uses mocks
throughout: no real DB, no real CrewAI, no real LiteLLM.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. executor._sanitize_error
# ---------------------------------------------------------------------------


class TestSanitizeError:
    """Tests for blackbeard.engine.executor._sanitize_error."""

    def test_safe_prefix_passes_through(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Agent 'researcher' not found in project 'default'"
        result = _sanitize_error(msg)
        assert "researcher" in result

    def test_safe_prefix_with_resource(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Resource 'my-crew' does not exist"
        result = _sanitize_error(msg)
        assert "my-crew" in result

    def test_safe_prefix_with_kind(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Kind 'Agent' is invalid"
        result = _sanitize_error(msg)
        assert "Agent" in result

    def test_safe_prefix_crew_kind(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Crew 'my-crew' not found in project 'default'"
        result = _sanitize_error(msg)
        assert "my-crew" in result

    def test_internal_error_returns_generic(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "psycopg2.OperationalError: connection refused at 10.0.0.5:5432"
        result = _sanitize_error(msg)
        assert result == "Execution failed: check server logs for details"
        assert "10.0.0.5" not in result

    def test_arbitrary_traceback_returns_generic(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Traceback (most recent call last):\n  File ..."
        result = _sanitize_error(msg)
        assert result == "Execution failed: check server logs for details"

    def test_long_safe_error_truncates(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Agent '" + "x" * 600
        result = _sanitize_error(msg)
        assert len(result) <= 504  # 500 + "..."
        assert result.endswith("...")

    def test_scrubs_pii_in_safe_error(self) -> None:
        from blackbeard.engine.executor import _sanitize_error

        msg = "Agent 'researcher' failed for user@example.com"
        result = _sanitize_error(msg)
        assert "user@example.com" not in result
        assert "[EMAIL]" in result


# ---------------------------------------------------------------------------
# 2. executor._get_executor
# ---------------------------------------------------------------------------


class TestGetExecutor:
    """Tests for blackbeard.engine.executor._get_executor."""

    def test_creates_executor_on_first_call(self) -> None:
        import blackbeard.engine.executor as mod

        original = mod._executor
        try:
            mod._executor = None
            executor = mod._get_executor()
            assert isinstance(executor, ThreadPoolExecutor)
        finally:
            if mod._executor is not None and mod._executor is not original:
                mod._executor.shutdown(wait=False)
            mod._executor = original

    def test_returns_same_instance_on_second_call(self) -> None:
        import blackbeard.engine.executor as mod

        original = mod._executor
        try:
            mod._executor = None
            first = mod._get_executor()
            second = mod._get_executor()
            assert first is second
        finally:
            if mod._executor is not None and mod._executor is not original:
                mod._executor.shutdown(wait=False)
            mod._executor = original


# ---------------------------------------------------------------------------
# 3. executor.get_pool_status
# ---------------------------------------------------------------------------


class TestGetPoolStatus:
    """Tests for blackbeard.engine.executor.get_pool_status."""

    def test_returns_zeros_when_no_executor(self) -> None:
        import blackbeard.engine.executor as mod

        original = mod._executor
        try:
            mod._executor = None
            status = mod.get_pool_status()
            assert status["active_threads"] == 0
            assert status["queued_tasks"] == 0
            assert status["saturated"] is False
            assert "max_workers" in status
        finally:
            mod._executor = original

    def test_returns_stats_after_creating_executor(self) -> None:
        import blackbeard.engine.executor as mod

        original = mod._executor
        try:
            mod._executor = None
            mod._get_executor()
            status = mod.get_pool_status()
            assert "active_threads" in status
            assert "max_workers" in status
            assert "queued_tasks" in status
            assert "saturated" in status
        finally:
            if mod._executor is not None and mod._executor is not original:
                mod._executor.shutdown(wait=False)
            mod._executor = original


# ---------------------------------------------------------------------------
# 4. executor.shutdown_executor
# ---------------------------------------------------------------------------


class TestShutdownExecutor:
    """Tests for blackbeard.engine.executor.shutdown_executor."""

    def test_clears_executor_global(self) -> None:
        import blackbeard.engine.executor as mod

        original_executor = mod._executor
        original_bg_engine = mod._bg_engine
        original_bg_session = mod._bg_session_factory
        try:
            mod._executor = ThreadPoolExecutor(max_workers=1)
            mod._bg_engine = None
            mod._bg_session_factory = None
            with patch("blackbeard.engine.execution_listener.dispose_sync_engine"):
                mod.shutdown_executor(wait=True)
            assert mod._executor is None
        finally:
            mod._executor = original_executor
            mod._bg_engine = original_bg_engine
            mod._bg_session_factory = original_bg_session

    def test_dispose_task_awaited_when_loop_running(self) -> None:
        import threading

        import blackbeard.engine.executor as mod

        original_executor = mod._executor
        original_bg_engine = mod._bg_engine
        original_bg_session = mod._bg_session_factory
        original_task = mod._bg_dispose_task
        disposed = threading.Event()

        class _FakeEngine:
            async def dispose(self) -> None:
                disposed.set()

        async def scenario() -> None:
            mod._executor = ThreadPoolExecutor(max_workers=1)
            mod._bg_engine = _FakeEngine()
            mod._bg_session_factory = None
            mod._bg_dispose_task = None
            with patch("blackbeard.engine.execution_listener.dispose_sync_engine"):
                mod.shutdown_executor(wait=True)
            assert mod._bg_dispose_task is not None, "dispose task not stashed"
            await mod.wait_for_bg_engine_dispose(timeout=5.0)

        try:
            asyncio.run(scenario())
            assert disposed.is_set(), "bg engine dispose never ran"
            assert mod._executor is None
        finally:
            mod._executor = original_executor
            mod._bg_engine = original_bg_engine
            mod._bg_session_factory = original_bg_session
            mod._bg_dispose_task = original_task


# ---------------------------------------------------------------------------
# 5. api.executions._poll_backoff
# ---------------------------------------------------------------------------


class TestPollBackoff:
    """Tests for blackbeard.api.executions._poll_backoff."""

    def test_phase1_returns_1(self) -> None:
        from blackbeard.api.executions import _poll_backoff

        assert _poll_backoff(0) == 1
        assert _poll_backoff(15) == 1
        assert _poll_backoff(29) == 1

    def test_phase2_returns_2(self) -> None:
        from blackbeard.api.executions import _poll_backoff

        assert _poll_backoff(30) == 2
        assert _poll_backoff(45) == 2
        assert _poll_backoff(60) == 2
        assert _poll_backoff(100) == 2
        assert _poll_backoff(999) == 2


# ---------------------------------------------------------------------------
# 6. api.executions._serialize_event
# ---------------------------------------------------------------------------


class TestSerializeEvent:
    """Tests for blackbeard.api.executions._serialize_event."""

    def test_serializes_event_with_sequence_and_timestamp(self) -> None:
        from blackbeard.api.executions import _serialize_event

        ev = MagicMock()
        ev.data = {"task_name": "research", "output_preview": "some text"}
        ev.sequence = 7
        ev.timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = _serialize_event(ev)
        assert result["sequence"] == 7
        assert result["timestamp"] == "2025-01-15T10:30:00+00:00"
        assert result["task_name"] == "research"
        assert result["output_preview"] == "some text"

    def test_serializes_event_with_no_data(self) -> None:
        from blackbeard.api.executions import _serialize_event

        ev = MagicMock()
        ev.data = None
        ev.sequence = 0
        ev.timestamp = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)

        result = _serialize_event(ev)
        assert result["sequence"] == 0
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# 7. execution_listener._log_webhook_future_exception
# ---------------------------------------------------------------------------


class TestLogWebhookFutureException:
    """Tests for blackbeard.engine.execution_listener._log_webhook_future_exception."""

    def test_logs_when_future_has_exception(self) -> None:
        from blackbeard.engine.execution_listener import (
            _log_webhook_future_exception,
        )

        future = MagicMock()
        future.exception.return_value = RuntimeError("connection timeout")

        with patch("blackbeard.engine.execution_listener.logger") as mock_logger:
            _log_webhook_future_exception(future)

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "connection timeout" in str(call_args)

    def test_no_log_when_future_succeeds(self) -> None:
        from blackbeard.engine.execution_listener import (
            _log_webhook_future_exception,
        )

        future = MagicMock()
        future.exception.return_value = None

        with patch("blackbeard.engine.execution_listener.logger") as mock_logger:
            _log_webhook_future_exception(future)

        mock_logger.error.assert_not_called()

    def test_handles_cancelled_future(self) -> None:
        from blackbeard.engine.execution_listener import (
            _log_webhook_future_exception,
        )

        future = MagicMock()
        future.exception.side_effect = Exception("cancelled")

        with patch("blackbeard.engine.execution_listener.logger") as mock_logger:
            _log_webhook_future_exception(future)

        # Generic exception on .exception() is caught; warning logged
        mock_logger.warning.assert_called()


# ---------------------------------------------------------------------------
# 8. execution_listener._get_webhook_hostname
# ---------------------------------------------------------------------------


class TestGetWebhookHostname:
    """Tests for blackbeard.engine.execution_listener._get_webhook_hostname."""

    def test_returns_hostname_for_external_url(self) -> None:
        from blackbeard.engine.execution_listener import (
            _get_webhook_hostname,
            _webhook_host_cache,
            _webhook_host_cache_lock,
        )

        # Clear cache for deterministic test
        with _webhook_host_cache_lock:
            _webhook_host_cache.clear()

        with patch(
            "blackbeard.engine.execution_listener.is_internal_host",
            return_value=False,
        ):
            result = _get_webhook_hostname("https://example.com/hook")
            assert result == "example.com"

    def test_returns_none_for_internal_url(self) -> None:
        from blackbeard.engine.execution_listener import (
            _get_webhook_hostname,
            _webhook_host_cache,
            _webhook_host_cache_lock,
        )

        with _webhook_host_cache_lock:
            _webhook_host_cache.clear()

        with patch(
            "blackbeard.engine.execution_listener.is_internal_host",
            return_value=True,
        ):
            result = _get_webhook_hostname("https://localhost:8000/hook")
            assert result is None

    def test_returns_none_for_empty_hostname(self) -> None:
        from blackbeard.engine.execution_listener import (
            _get_webhook_hostname,
            _webhook_host_cache,
            _webhook_host_cache_lock,
        )

        with _webhook_host_cache_lock:
            _webhook_host_cache.clear()

        # A URL with no hostname: urlparse returns empty string
        result = _get_webhook_hostname("not-a-url")
        assert result is None


# ---------------------------------------------------------------------------
# 9. execution_listener.invalidate_webhook_cache
# ---------------------------------------------------------------------------


class TestInvalidateWebhookCache:
    """Tests for blackbeard.engine.execution_listener.invalidate_webhook_cache."""

    def test_clears_webhook_cache(self) -> None:
        import blackbeard.engine.execution_listener as mod

        # Seed the cache
        mod._webhook_cache_entry = (1234.0, [MagicMock()])
        with mod._webhook_host_cache_lock:
            mod._webhook_host_cache["https://example.com"] = "example.com"

        mod.invalidate_webhook_cache()

        assert mod._webhook_cache_entry is None
        with mod._webhook_host_cache_lock:
            assert len(mod._webhook_host_cache) == 0


# ---------------------------------------------------------------------------
# 10. execution_listener._deliver_single_webhook
# ---------------------------------------------------------------------------


class TestDeliverSingleWebhook:
    """Tests for blackbeard.engine.execution_listener._deliver_single_webhook."""

    def test_sends_hmac_signature_header(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_single_webhook

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        webhook = MagicMock()
        webhook.url = "https://example.com/hook"
        webhook.secret = "test-secret"
        webhook.id = "wh-1"

        with patch(
            "blackbeard.engine.execution_listener.get_sync_client",
            return_value=mock_client,
        ):
            _deliver_single_webhook(
                webhook, '{"event":"test"}', "test_event", execution_id="exec-1"
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert "X-Webhook-Signature" in headers
        assert headers["X-Blackbeard-Event"] == "test_event"
        assert headers["Content-Type"] == "application/json"

    def test_does_not_crash_on_client_failure(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_single_webhook

        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("network unreachable")

        webhook = MagicMock()
        webhook.url = "https://example.com/hook"
        webhook.secret = "test-secret"
        webhook.id = "wh-2"

        with patch(
            "blackbeard.engine.execution_listener.get_sync_client",
            return_value=mock_client,
        ):
            # Should not raise
            _deliver_single_webhook(
                webhook, '{"event":"test"}', "test_event", execution_id="exec-2"
            )

    def test_logs_warning_on_error_response(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_single_webhook

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        webhook = MagicMock()
        webhook.url = "https://example.com/hook"
        webhook.secret = "test-secret"
        webhook.id = "wh-3"

        with (
            patch(
                "blackbeard.engine.execution_listener.get_sync_client",
                return_value=mock_client,
            ),
            patch("blackbeard.engine.execution_listener.logger") as mock_logger,
        ):
            _deliver_single_webhook(
                webhook, '{"event":"test"}', "test_event", execution_id="exec-3"
            )

        mock_logger.warning.assert_called_once()
        assert "delivery failed" in str(mock_logger.warning.call_args).lower()


# ---------------------------------------------------------------------------
# 11. flow_runner.call_hook
# ---------------------------------------------------------------------------


class TestCallHook:
    """Tests for blackbeard.engine.flow_runner.call_hook."""

    def test_calls_valid_callable(self) -> None:
        from blackbeard.engine.flow_runner import call_hook

        mock_fn = MagicMock()
        loader = MagicMock()
        loader.import_callable.return_value = mock_fn

        call_hook(loader, "mymodule.my_func", {"key": "value"}, "before_kickoff")

        loader.import_callable.assert_called_once_with("mymodule.my_func")
        mock_fn.assert_called_once_with({"key": "value"})

    def test_logs_warning_on_import_failure(self) -> None:
        from blackbeard.engine.flow_runner import call_hook

        loader = MagicMock()
        loader.import_callable.return_value = None

        with patch("blackbeard.engine.flow_runner.logger") as mock_logger:
            call_hook(loader, "missing.module.func", None, "after_kickoff")

        mock_logger.warning.assert_called_once()
        assert "could not be imported" in str(mock_logger.warning.call_args)

    def test_logs_warning_on_hook_exception(self) -> None:
        from blackbeard.engine.flow_runner import call_hook

        mock_fn = MagicMock(side_effect=ValueError("bad input"))
        loader = MagicMock()
        loader.import_callable.return_value = mock_fn

        with patch("blackbeard.engine.flow_runner.logger") as mock_logger:
            # Should not raise
            call_hook(loader, "mymodule.bad_func", "arg", "on_error")

        mock_logger.warning.assert_called_once()
        assert "raised an exception" in str(mock_logger.warning.call_args)


# ---------------------------------------------------------------------------
# 12. flow_runner.run_flow_steps
# ---------------------------------------------------------------------------


class TestRunFlowSteps:
    """Tests for blackbeard.engine.flow_runner.run_flow_steps."""

    def test_raises_on_missing_flow(self) -> None:
        from blackbeard.engine.flow_runner import run_flow_steps
        from blackbeard.engine.loader import LoaderError

        loader = MagicMock()
        snapshot: dict[str, dict[str, Any]] = {}
        listener = MagicMock()

        with pytest.raises(LoaderError, match="not found"):
            run_flow_steps(loader, snapshot, "nonexistent-flow", {}, listener)

    def test_empty_steps_returns_none(self) -> None:
        from blackbeard.engine.flow_runner import run_flow_steps

        loader = MagicMock()
        snapshot = {
            "Flow/test-flow": {
                "kind": "Flow",
                "name": "test-flow",
                "project": "default",
                "spec": {"steps": []},
            }
        }
        listener = MagicMock()

        result = run_flow_steps(loader, snapshot, "test-flow", {}, listener)
        assert result is None

    def test_crew_step_calls_kickoff(self) -> None:
        from blackbeard.engine.flow_runner import run_flow_steps

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "crew output"
        loader = MagicMock()
        loader.build_crew.return_value = mock_crew

        snapshot = {
            "Flow/my-flow": {
                "kind": "Flow",
                "name": "my-flow",
                "project": "default",
                "spec": {
                    "steps": [
                        {
                            "name": "step1",
                            "type": "crew",
                            "crew": "ref:crews/test-crew",
                        }
                    ]
                },
            }
        }
        listener = MagicMock()

        result = run_flow_steps(loader, snapshot, "my-flow", {"topic": "AI"}, listener)

        loader.build_crew.assert_called_once_with("test-crew")
        mock_crew.kickoff.assert_called_once()
        assert result == "crew output"


# ---------------------------------------------------------------------------
# 13 & 14. scheduler.AutomationScheduler
# ---------------------------------------------------------------------------


class TestAutomationScheduler:
    """Tests for blackbeard.engine.scheduler.AutomationScheduler."""

    def test_initial_state(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        assert scheduler._tasks == {}
        assert scheduler._running is False

    def test_log_cron_task_exception_with_failed_task(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = RuntimeError("cron job failed")
        task.get_name.return_value = "cron-test-automation"

        with patch("blackbeard.engine.scheduler.logger") as mock_logger:
            AutomationScheduler._log_cron_task_exception(task)

        mock_logger.error.assert_called_once()
        assert "cron job failed" in str(mock_logger.error.call_args)

    def test_log_cron_task_exception_with_cancelled_task(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        task = MagicMock()
        task.cancelled.return_value = True

        with patch("blackbeard.engine.scheduler.logger") as mock_logger:
            AutomationScheduler._log_cron_task_exception(task)

        mock_logger.error.assert_not_called()

    def test_log_cron_task_exception_with_no_exception(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = None

        with patch("blackbeard.engine.scheduler.logger") as mock_logger:
            AutomationScheduler._log_cron_task_exception(task)

        mock_logger.error.assert_not_called()


# ---------------------------------------------------------------------------
# 16. loader._build_knowledge_source
# ---------------------------------------------------------------------------


class TestBuildKnowledgeSource:
    """Tests for blackbeard.engine.loader.ResourceLoader._build_knowledge_source."""

    def test_returns_none_for_wrong_kind(self) -> None:
        from blackbeard.engine.loader import ResourceLoader
        from blackbeard.kinds import ResourceKind

        agent = MagicMock()
        agent.kind = ResourceKind.AGENT
        agent.name = "agent-1"
        agent.spec = {}

        resources = {"Agent/agent-1": agent}
        loader = ResourceLoader(resources)

        result = loader._build_knowledge_source("ref:agents/agent-1")
        assert result is None

    def test_returns_none_for_unsupported_type(self) -> None:
        from blackbeard.engine.loader import ResourceLoader
        from blackbeard.kinds import ResourceKind

        ks = MagicMock()
        ks.kind = ResourceKind.KNOWLEDGE_SOURCE
        ks.name = "ks-1"
        ks.project = "default"
        ks.spec = {"type": "unsupported_type", "file_paths": []}

        resources = {"KnowledgeSource/ks-1": ks}
        loader = ResourceLoader(resources)

        result = loader._build_knowledge_source("ref:knowledge-sources/ks-1")
        assert result is None

    def test_builds_string_knowledge_source(self) -> None:
        from blackbeard.engine.loader import ResourceLoader
        from blackbeard.kinds import ResourceKind

        ks = MagicMock()
        ks.kind = ResourceKind.KNOWLEDGE_SOURCE
        ks.name = "ks-string"
        ks.project = "default"
        ks.spec = {"type": "string", "content": "Hello world"}

        resources = {"KnowledgeSource/ks-string": ks}
        loader = ResourceLoader(resources)

        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch.dict(
            "blackbeard.engine.loader._ks_class_cache",
            {
                "crewai.knowledge.source.string_knowledge_source.StringKnowledgeSource": mock_cls,
            },
        ):
            result = loader._build_knowledge_source("ref:knowledge-sources/ks-string")

        mock_cls.assert_called_once_with(content="Hello world")
        assert result is mock_instance


# ---------------------------------------------------------------------------
# 17. loader._build_discovery_tools
# ---------------------------------------------------------------------------


class TestBuildDiscoveryTools:
    """Tests for blackbeard.engine.loader.ResourceLoader._build_discovery_tools."""

    def test_returns_list_of_tools(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        loader = ResourceLoader({})

        mock_search = MagicMock()
        mock_get = MagicMock()

        with (
            patch(
                "blackbeard.engine.discovery_tools.SearchToolsTool",
                return_value=mock_search,
            ),
            patch(
                "blackbeard.engine.discovery_tools.GetToolTool",
                return_value=mock_get,
            ),
        ):
            tools = loader._build_discovery_tools("default")

        assert isinstance(tools, list)
        assert len(tools) == 2
        assert tools[0] is mock_search
        assert tools[1] is mock_get

    def test_caches_result(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        loader = ResourceLoader({})

        mock_search = MagicMock()
        mock_get = MagicMock()

        with (
            patch(
                "blackbeard.engine.discovery_tools.SearchToolsTool",
                return_value=mock_search,
            ),
            patch(
                "blackbeard.engine.discovery_tools.GetToolTool",
                return_value=mock_get,
            ),
        ):
            first = loader._build_discovery_tools("default")
            second = loader._build_discovery_tools("default")

        assert first is second


# ---------------------------------------------------------------------------
# 18. litellm.model_sync.add_model (sync_model_to_litellm equivalent)
# ---------------------------------------------------------------------------


class TestLiteLLMModelSync:
    """Tests for blackbeard.litellm.model_sync.add_model and delete_model."""

    @pytest.mark.asyncio
    async def test_add_model_posts_to_litellm(self) -> None:
        from blackbeard.litellm.model_sync import add_model

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        spec = {
            "provider": "openai",
            "model": "gpt-4o",
            "parameters": {},
        }

        with patch(
            "blackbeard.litellm.model_sync._get_client",
            return_value=mock_client,
        ):
            result = await add_model("my-gpt4", spec)

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/model/new" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_model_returns_false_on_failure(self) -> None:
        from blackbeard.litellm.model_sync import add_model

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        spec = {"provider": "openai", "model": "gpt-4o", "parameters": {}}

        with patch(
            "blackbeard.litellm.model_sync._get_client",
            return_value=mock_client,
        ):
            result = await add_model("failing-model", spec)

        assert result is False


# ---------------------------------------------------------------------------
# 19. litellm.model_sync.delete_model (delete_model_from_litellm)
# ---------------------------------------------------------------------------


class TestDeleteModelFromLiteLLM:
    """Tests for blackbeard.litellm.model_sync.delete_model."""

    @pytest.mark.asyncio
    async def test_delete_model_posts_to_litellm(self) -> None:
        from blackbeard.litellm.model_sync import delete_model

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch(
            "blackbeard.litellm.model_sync._get_client",
            return_value=mock_client,
        ):
            result = await delete_model("my-model")

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/model/delete" in call_args[0][0]
        assert call_args.kwargs["json"] == {"id": "my-model"}

    @pytest.mark.asyncio
    async def test_delete_model_returns_false_on_error(self) -> None:
        import httpx

        from blackbeard.litellm.model_sync import delete_model

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPError("connection refused")

        with patch(
            "blackbeard.litellm.model_sync._get_client",
            return_value=mock_client,
        ):
            result = await delete_model("bad-model")

        assert result is False


# ---------------------------------------------------------------------------
# 20. sse.acquire_stream / release_stream
# ---------------------------------------------------------------------------


class TestSSEState:
    """Tests for blackbeard.sse.acquire_stream and get_active_count."""

    def test_get_status_returns_dict(self) -> None:
        import blackbeard.sse as sse_mod

        status = sse_mod.get_status()
        assert isinstance(status, dict)
        assert "active" in status
        assert "max" in status
        assert isinstance(status["active"], int)
        assert isinstance(status["max"], int)

    def test_get_active_count_returns_int(self) -> None:
        import blackbeard.sse as sse_mod

        count = sse_mod.get_active_count()
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_acquire_and_release_stream(self) -> None:
        """Test that acquire_stream increments/decrements active count."""
        import blackbeard.sse as sse_mod

        original_semaphore = sse_mod.semaphore
        original_active = sse_mod._active_streams
        try:
            # Fresh semaphore so the release() in acquire_stream's finally
            # cannot inflate the shared module-level semaphore's counter.
            sse_mod.semaphore = asyncio.Semaphore(1)
            with sse_mod._active_lock:
                sse_mod._active_streams = 0

            async with sse_mod.acquire_stream() as acquired:
                assert acquired is True
                assert sse_mod.get_active_count() == 1

            assert sse_mod.get_active_count() == 0
        finally:
            sse_mod.semaphore = original_semaphore
            with sse_mod._active_lock:
                sse_mod._active_streams = original_active

    @pytest.mark.asyncio
    async def test_rejects_when_at_capacity(self) -> None:
        import blackbeard.sse as sse_mod

        original_semaphore = sse_mod.semaphore
        original_active = sse_mod._active_streams
        try:
            # Replace semaphore with one that has zero capacity
            sse_mod.semaphore = asyncio.Semaphore(0)

            async with sse_mod.acquire_stream() as acquired:
                assert acquired is False

        finally:
            sse_mod.semaphore = original_semaphore
            with sse_mod._active_lock:
                sse_mod._active_streams = original_active
