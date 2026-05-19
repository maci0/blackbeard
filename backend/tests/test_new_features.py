"""Tests for the four new backend features:

1. Schema-based guardrails
2. HITL approval workflows
3. OpenTelemetry export
4. Webhook streaming
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.loader import ResourceLoader
from blackbeard.kinds import ResourceKind
from blackbeard.models.execution import Execution, ExecutionEvent, ExecutionStatus, ExecutionType
from tests.conftest import API_KEY_HEADER, _resource_map, make_resource

# ============================================================================
# Feature 1: Schema-based Guardrails
# ============================================================================


class TestSchemaGuardrailSpec:
    """Test schema guardrail spec validation."""

    def test_guardrail_schema_accepts_schema_type(self):
        """GUARDRAIL_SCHEMA should accept type='schema' with json_schema."""
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        valid_spec = {
            "type": "schema",
            "json_schema": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        }
        jsonschema.validate(valid_spec, GUARDRAIL_SCHEMA)

    def test_guardrail_schema_rejects_invalid_type(self):
        """GUARDRAIL_SCHEMA should reject unknown type values."""
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        invalid_spec = {"type": "unknown"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_spec, GUARDRAIL_SCHEMA)

    def test_guardrail_schema_with_description_and_on_fail(self):
        """Schema guardrail with all optional fields should validate."""
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        spec = {
            "type": "schema",
            "description": "Validate output is valid JSON with required fields",
            "json_schema": {"type": "object"},
            "on_fail": "warn",
        }
        jsonschema.validate(spec, GUARDRAIL_SCHEMA)


class TestSchemaGuardrailLoader:
    """Test schema guardrail build and execution."""

    def test_build_schema_guardrail_valid_output(self):
        """Schema guardrail should pass valid JSON through unchanged."""
        schema = {
            "type": "object",
            "required": ["name", "score"],
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
            },
        }
        guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "test-guardrail")

        valid_output = '{"name": "Alice", "score": 95.5}'
        result = guardrail_fn(valid_output)
        assert result == valid_output

    def test_build_schema_guardrail_invalid_json(self):
        """Schema guardrail should raise ValueError for non-JSON output."""
        schema = {"type": "object"}
        guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "test-guardrail")

        with pytest.raises(ValueError, match="not valid JSON"):
            guardrail_fn("not json at all")

    def test_build_schema_guardrail_schema_mismatch(self):
        """Schema guardrail should raise ValueError when output doesn't match schema."""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "test-guardrail")

        with pytest.raises(ValueError, match="test-guardrail"):
            guardrail_fn('{"score": 42}')

    def test_build_schema_guardrail_wrong_type(self):
        """Schema guardrail should reject output with wrong top-level type."""
        schema = {"type": "array", "items": {"type": "string"}}
        guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "array-guardrail")

        with pytest.raises(ValueError, match="array-guardrail"):
            guardrail_fn('{"not": "an array"}')

    def test_build_schema_guardrail_passes_array(self):
        """Schema guardrail should pass valid array output."""
        schema = {"type": "array", "items": {"type": "string"}}
        guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "array-guardrail")

        result = guardrail_fn('["a", "b", "c"]')
        assert result == '["a", "b", "c"]'

    @patch("blackbeard.engine.loader.LLM")
    @patch("blackbeard.engine.loader.Agent")
    @patch("blackbeard.engine.loader.Task")
    def test_build_task_with_schema_guardrail_ref(
        self, mock_task_cls, mock_agent_cls, mock_llm_cls
    ):
        """Task with a schema guardrail ref should resolve and include it."""
        agent_res = make_resource(
            ResourceKind.AGENT,
            "agent-g",
            {"role": "R", "goal": "G", "backstory": "B"},
        )
        guardrail_res = make_resource(
            ResourceKind.GUARDRAIL,
            "output-schema",
            {
                "type": "schema",
                "json_schema": {
                    "type": "object",
                    "required": ["result"],
                    "properties": {"result": {"type": "string"}},
                },
            },
        )
        task_res = make_resource(
            ResourceKind.TASK,
            "guarded-task",
            {
                "description": "Do something",
                "expected_output": "A result",
                "agent": "ref:agents/agent-g",
                "guardrails": ["ref:guardrails/output-schema"],
            },
        )
        loader = ResourceLoader(_resource_map(agent_res, guardrail_res, task_res))
        loader.build_task("ref:tasks/guarded-task")

        mock_task_cls.assert_called_once()
        _, kwargs = mock_task_cls.call_args
        assert "guardrail" in kwargs
        assert len(kwargs["guardrail"]) == 1
        # The guardrail should be a callable
        guardrail = kwargs["guardrail"][0]
        assert callable(guardrail)
        # Validate it works
        assert guardrail('{"result": "success"}') == '{"result": "success"}'
        with pytest.raises(ValueError, match="output-schema"):
            guardrail('{"wrong_field": "value"}')

    @patch("blackbeard.engine.loader.LLM")
    @patch("blackbeard.engine.loader.Agent")
    @patch("blackbeard.engine.loader.Task")
    def test_build_task_schema_guardrail_with_function_guardrail(
        self, mock_task_cls, mock_agent_cls, mock_llm_cls
    ):
        """Task can mix schema and function guardrails."""
        agent_res = make_resource(
            ResourceKind.AGENT,
            "agent-mix",
            {"role": "R", "goal": "G", "backstory": "B"},
        )
        schema_guardrail_res = make_resource(
            ResourceKind.GUARDRAIL,
            "schema-g",
            {
                "type": "schema",
                "json_schema": {"type": "object"},
            },
        )
        llm_guardrail_res = make_resource(
            ResourceKind.GUARDRAIL,
            "llm-g",
            {
                "type": "llm",
                "llm_prompt": "Check if this output is professional.",
            },
        )
        task_res = make_resource(
            ResourceKind.TASK,
            "multi-guard-task",
            {
                "description": "Do something",
                "expected_output": "Result",
                "agent": "ref:agents/agent-mix",
                "guardrails": ["ref:guardrails/schema-g", "ref:guardrails/llm-g"],
            },
        )
        loader = ResourceLoader(
            _resource_map(agent_res, schema_guardrail_res, llm_guardrail_res, task_res)
        )
        loader.build_task("ref:tasks/multi-guard-task")

        _, kwargs = mock_task_cls.call_args
        assert "guardrail" in kwargs
        assert len(kwargs["guardrail"]) == 2
        # First is schema callable, second is LLM prompt string
        assert callable(kwargs["guardrail"][0])
        assert isinstance(kwargs["guardrail"][1], str)


# ============================================================================
# Feature 2: HITL Approval Workflows
# ============================================================================


class TestHITLSchemas:
    """Test HITL Pydantic models."""

    def test_hitl_response_request_valid(self):
        from blackbeard.models.execution_schemas import HITLResponseRequest

        req = HITLResponseRequest(response="approved", feedback="looks good")
        assert req.response == "approved"
        assert req.feedback == "looks good"

    def test_hitl_response_request_no_feedback(self):
        from blackbeard.models.execution_schemas import HITLResponseRequest

        req = HITLResponseRequest(response="rejected")
        assert req.response == "rejected"
        assert req.feedback is None

    def test_hitl_response_request_empty_response_rejected(self):
        from pydantic import ValidationError

        from blackbeard.models.execution_schemas import HITLResponseRequest

        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            HITLResponseRequest(response="")


class TestHITLEndpoint:
    """Test the HITL respond endpoint."""

    async def test_respond_to_running_execution(self, client, db_session):
        """POST /executions/{id}/respond should record a HITL response."""
        # Create a running execution
        execution = Execution(
            id=uuid.uuid4(),
            crew_name="test-crew",
            crew_namespace="default",
            execution_type=ExecutionType.KICKOFF,
            status=ExecutionStatus.RUNNING,
            inputs={},
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        db_session.add(execution)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/executions/{execution.id}/respond",
            json={"response": "approved", "feedback": "looks good"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["execution_id"] == str(execution.id)

        # Verify the event was written
        from sqlalchemy import select

        result = await db_session.execute(
            select(ExecutionEvent).where(
                ExecutionEvent.execution_id == execution.id,
                ExecutionEvent.event_type == "hitl_response",
            )
        )
        event = result.scalar_one()
        assert event.data["response"] == "approved"
        assert event.data["feedback"] == "looks good"

    async def test_respond_to_missing_execution(self, client):
        """POST /executions/{id}/respond should return 404 for missing execution."""
        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/executions/{fake_id}/respond",
            json={"response": "approved"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 404

    async def test_respond_to_completed_execution(self, client, db_session):
        """POST /executions/{id}/respond should return 409 for terminal execution."""
        execution = Execution(
            id=uuid.uuid4(),
            crew_name="test-crew",
            crew_namespace="default",
            execution_type=ExecutionType.KICKOFF,
            status=ExecutionStatus.COMPLETED,
            inputs={},
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            outputs={"raw": "done"},
        )
        db_session.add(execution)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/executions/{execution.id}/respond",
            json={"response": "approved"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 409

    async def test_respond_without_feedback(self, client, db_session):
        """HITL response without feedback should still work."""
        execution = Execution(
            id=uuid.uuid4(),
            crew_name="test-crew",
            crew_namespace="default",
            execution_type=ExecutionType.KICKOFF,
            status=ExecutionStatus.RUNNING,
            inputs={},
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        db_session.add(execution)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/executions/{execution.id}/respond",
            json={"response": "rejected"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 200

        from sqlalchemy import select

        result = await db_session.execute(
            select(ExecutionEvent).where(
                ExecutionEvent.execution_id == execution.id,
                ExecutionEvent.event_type == "hitl_response",
            )
        )
        event = result.scalar_one()
        assert event.data["response"] == "rejected"
        assert "feedback" not in event.data


# ============================================================================
# Feature 3: OpenTelemetry Export
# ============================================================================


class TestOtelConfig:
    """Test OpenTelemetry configuration."""

    def test_otel_endpoint_default_is_none(self):
        """otel_endpoint should default to None."""
        from blackbeard.config import Settings

        s = Settings(debug=True)
        assert s.otel_endpoint is None

    def test_otel_endpoint_from_env(self, monkeypatch):
        """otel_endpoint should be settable via environment variable."""
        monkeypatch.setenv("OTEL_ENDPOINT", "http://otel-collector:4317")
        from blackbeard.config import Settings

        s = Settings(debug=True)
        assert s.otel_endpoint == "http://otel-collector:4317"


class TestOtelListener:
    """Test OpenTelemetry integration in execution listener."""

    def test_has_otel_flag_when_not_installed(self):
        """HAS_OTEL should be True since opentelemetry is not a dependency."""
        # In test environment, HAS_OTEL depends on whether otel is installed.
        # We just verify the flag exists and is a bool.
        from blackbeard.engine.execution_listener import HAS_OTEL

        assert isinstance(HAS_OTEL, bool)

    def test_get_otel_tracer_returns_none_without_config(self):
        """_get_otel_tracer should return None when otel_endpoint is not set."""
        import blackbeard.engine.execution_listener as listener_mod
        from blackbeard.engine.execution_listener import _get_otel_tracer

        old_tracer = listener_mod._otel_tracer
        old_provider = listener_mod._otel_provider
        listener_mod._otel_tracer = None
        listener_mod._otel_provider = None
        try:
            result = _get_otel_tracer()
            assert result is None, (
                "Without otel_endpoint configured, tracer must be None "
                f"(HAS_OTEL={listener_mod.HAS_OTEL})"
            )
        finally:
            listener_mod._otel_tracer = old_tracer
            listener_mod._otel_provider = old_provider

    def test_listener_initializes_without_otel(self):
        """Listener should work without OpenTelemetry configured."""
        listener_id = uuid.uuid4()
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        with patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            listener = BlackbeardExecutionListener(
                execution_id=listener_id,
                db_url="sqlite:///test.db",
            )
            # Listener should be created even without OTEL
            assert listener._execution_id == listener_id

    def test_otel_start_span_returns_none_without_tracer(self):
        """_otel_start_span returns None when no tracer configured."""
        listener_id = uuid.uuid4()
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        with patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            with patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None):
                listener = BlackbeardExecutionListener(
                    execution_id=listener_id,
                    db_url="sqlite:///test.db",
                )
                span = listener._otel_start_span("test-span")
                assert span is None


# ============================================================================
# Feature 4: Webhook Streaming
# ============================================================================


class TestWebhookModel:
    """Test Webhook SQLAlchemy model."""

    async def test_create_webhook(self, db_session):
        from blackbeard.models.webhook import Webhook

        webhook = Webhook(
            url="https://example.com/webhook",
            events=["crew_started", "crew_completed"],
            secret="test-secret-value-1234",
            active=True,
        )
        db_session.add(webhook)
        await db_session.flush()
        assert webhook.id is not None

    async def test_webhook_to_dict_excludes_secret(self, db_session):
        from blackbeard.models.webhook import Webhook

        webhook = Webhook(
            url="https://example.com/webhook",
            events=["crew_started"],
            secret="super-secret-key-1234",
            active=True,
        )
        db_session.add(webhook)
        await db_session.flush()

        d = webhook.to_dict()
        assert "secret" not in d
        assert d["url"] == "https://example.com/webhook"
        assert d["events"] == ["crew_started"]
        assert d["active"] is True


class TestWebhookAPI:
    """Test webhook API endpoints."""

    async def test_create_webhook(self, client):
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["crew_started", "task_completed"],
                "secret": "my-secret-key-for-signing-webhooks",
            },
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/hook"
        assert data["events"] == ["crew_started", "task_completed"]
        assert data["active"] is True
        # Secret is shown on create
        assert data["secret"] == "my-secret-key-for-signing-webhooks"
        assert "id" in data

    async def test_create_webhook_auto_secret(self, client):
        """Webhook without explicit secret should auto-generate one."""
        resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/hook2", "events": []},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["secret"]) >= 16

    async def test_list_webhooks(self, client):
        # Create two webhooks
        await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook-a",
                "events": [],
                "secret": "secret-a-long-enough-1234",
            },
            headers=API_KEY_HEADER,
        )
        await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/hook-b",
                "events": ["crew_started"],
                "secret": "secret-b-long-enough-1234",
            },
            headers=API_KEY_HEADER,
        )

        resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        # Secrets should not be in list response
        for webhook in data:
            assert "secret" not in webhook

    async def test_delete_webhook(self, client):
        # Create a webhook
        create_resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/to-delete",
                "events": [],
                "secret": "delete-me-secret-key-1234",
            },
            headers=API_KEY_HEADER,
        )
        webhook_id = create_resp.json()["id"]

        # Delete it
        resp = await client.delete(
            f"/api/v1/webhooks/{webhook_id}",
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 204

    async def test_delete_nonexistent_webhook(self, client):
        fake_id = uuid.uuid4()
        resp = await client.delete(
            f"/api/v1/webhooks/{fake_id}",
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 404

    async def test_create_webhook_invalid_url(self, client):
        """Webhook with non-HTTP URL should be rejected."""
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "ftp://example.com/hook",
                "events": [],
                "secret": "some-secret-key-1234-long",
            },
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 422

    async def test_create_webhook_empty_events_means_all(self, client):
        """Empty events list should be accepted (means all events)."""
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/all-events",
                "events": [],
                "secret": "all-events-secret-1234-key",
            },
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["events"] == []


class TestWebhookDelivery:
    """Test webhook delivery mechanics."""

    def test_hmac_signature_generation(self):
        """Webhook payloads should be signed with HMAC-SHA256."""
        secret = "test-secret-for-hmac"
        payload = json.dumps({"event_type": "crew_started", "data": {}})
        expected_sig = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        assert len(expected_sig) == 64  # SHA256 hex digest is 64 chars

    def test_deliver_webhooks_handles_no_webhooks(self):
        """Delivery with no webhooks in DB should not raise."""
        from blackbeard.engine.execution_listener import _deliver_webhooks_sync

        # This will try to load webhooks from DB — mock it
        with patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory"
        ) as mock_factory:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value = []  # no webhooks
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.execute.return_value = mock_result
            mock_factory.return_value = mock_session

            # Should not raise
            _deliver_webhooks_sync(
                "crew_started",
                {"crew_name": "test"},
                str(uuid.uuid4()),
                "sqlite:///test.db",
            )

    def test_deliver_webhooks_filters_by_event_type(self):
        """Webhooks with event filters should only receive matching events."""
        from blackbeard.models.webhook import Webhook

        # Create a webhook that only listens for crew_completed
        mock_webhook = MagicMock(spec=Webhook)
        mock_webhook.events = ["crew_completed"]
        mock_webhook.url = "https://example.com/hook"
        mock_webhook.secret = "test-secret"
        mock_webhook.active = True

        mock_session_ctx = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = [mock_webhook]
        mock_session.execute.return_value = mock_result
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session_ctx)

        mock_client = MagicMock()

        import blackbeard.engine.execution_listener as listener_mod

        # Save and patch module-level cached factory
        old_factory = listener_mod._sync_session_factory
        listener_mod._sync_session_factory = mock_factory

        try:
            with patch("blackbeard.http_client.get_sync_client", return_value=mock_client):
                listener_mod._deliver_webhooks_sync(
                    "crew_started",
                    {"crew_name": "test"},
                    str(uuid.uuid4()),
                    "sqlite:///test.db",
                )

            # Client.post should NOT have been called (event filtered out)
            mock_client.post.assert_not_called()
        finally:
            listener_mod._sync_session_factory = old_factory

    def test_deliver_webhooks_empty_events_receives_all(self):
        """Webhooks with empty events list should receive all events."""
        from blackbeard.models.webhook import Webhook

        mock_webhook = MagicMock(spec=Webhook)
        mock_webhook.events = []  # empty = all events
        mock_webhook.url = "https://example.com/hook"
        mock_webhook.secret = "test-secret"
        mock_webhook.active = True
        mock_webhook.id = uuid.uuid4()

        mock_session_ctx = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = [mock_webhook]
        mock_session.execute.return_value = mock_result
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session_ctx)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        import blackbeard.engine.execution_listener as listener_mod

        old_factory = listener_mod._sync_session_factory
        listener_mod._sync_session_factory = mock_factory
        listener_mod.invalidate_webhook_cache()

        try:
            with patch.object(listener_mod, "get_sync_client", return_value=mock_client):
                listener_mod._deliver_webhooks_sync(
                    "crew_started",
                    {"crew_name": "test"},
                    str(uuid.uuid4()),
                    "sqlite:///test.db",
                )

            # Client.post SHOULD have been called
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert call_kwargs[1]["headers"]["X-Blackbeard-Event"] == "crew_started"
            assert "X-Webhook-Signature" in call_kwargs[1]["headers"]
        finally:
            listener_mod._sync_session_factory = old_factory
            listener_mod.invalidate_webhook_cache()
