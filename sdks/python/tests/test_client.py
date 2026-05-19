"""Tests for BlackbeardClient using httpx mock transport."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from blackbeard_sdk import BlackbeardClient
from blackbeard_sdk.resources import KIND_TO_PLURAL, _kind_plural


# -- Helpers ------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: Any = None,
) -> httpx.Response:
    """Build a mock httpx.Response."""
    content = json.dumps(json_data).encode() if json_data is not None else b""
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"},
    )


class MockTransport(httpx.BaseTransport):
    """Records requests and returns canned responses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self._response_queue: list[httpx.Response] = []

    def queue(self, resp: httpx.Response) -> None:
        self._response_queue.append(resp)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._response_queue:
            resp = self._response_queue.pop(0)
        else:
            resp = _mock_response(200, {"status": "ok"})
        resp.request = request
        return resp


@pytest.fixture
def transport() -> MockTransport:
    return MockTransport()


@pytest.fixture
def client(transport: MockTransport) -> BlackbeardClient:
    c = BlackbeardClient(base_url="http://test:8000", api_key="test-key")
    c._http = httpx.Client(
        base_url="http://test:8000",
        headers={"X-API-Key": "test-key"},
        transport=transport,
    )
    return c


# -- Auth tests ---------------------------------------------------------------


class TestAuth:
    def test_login_stores_token(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {
                "access_token": "jwt-abc",
                "refresh_token": "ref-xyz",
                "token_type": "bearer",
                "user": {"id": "u1", "email": "a@b.com"},
            })
        )
        result = client.login("a@b.com", "pass1234")
        assert result["access_token"] == "jwt-abc"
        assert client._http.headers["Authorization"] == "Bearer jwt-abc"
        req = transport.requests[0]
        assert req.method == "POST"
        assert req.url.path == "/api/v1/auth/login"

    def test_register(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(201, {
                "access_token": "jwt-new",
                "refresh_token": "ref-new",
                "token_type": "bearer",
                "user": {"id": "u2", "email": "b@c.com"},
            })
        )
        result = client.register("b@c.com", "Pass1234", "Bob")
        assert result["access_token"] == "jwt-new"
        assert client._http.headers["Authorization"] == "Bearer jwt-new"

    def test_whoami(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {"id": "u1", "email": "a@b.com"})
        )
        result = client.whoami()
        assert result["email"] == "a@b.com"
        req = transport.requests[0]
        assert req.url.path == "/api/v1/auth/me"

    def test_refresh_updates_token(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {
                "access_token": "jwt-refreshed",
                "token_type": "bearer",
            })
        )
        result = client.refresh("ref-xyz")
        assert result["access_token"] == "jwt-refreshed"
        assert client._http.headers["Authorization"] == "Bearer jwt-refreshed"


# -- Resource tests -----------------------------------------------------------


class TestResources:
    def test_list_agents(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {
                "items": [{"kind": "Agent", "metadata": {"name": "researcher"}}],
                "total": 1,
                "limit": 100,
                "offset": 0,
                "has_more": False,
            })
        )
        items = client.list("Agent")
        assert len(items) == 1
        assert items[0]["kind"] == "Agent"
        req = transport.requests[0]
        assert req.url.path == "/api/v1/agents"
        assert "namespace=default" in str(req.url)

    def test_list_with_plural(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {"items": [], "total": 0, "limit": 100, "offset": 0, "has_more": False})
        )
        client.list("agents", namespace="prod")
        req = transport.requests[0]
        assert req.url.path == "/api/v1/agents"
        assert "namespace=prod" in str(req.url)

    def test_get_resource(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {"kind": "Task", "metadata": {"name": "write-report"}})
        )
        result = client.get("Task", "write-report")
        assert result["metadata"]["name"] == "write-report"
        req = transport.requests[0]
        assert req.url.path == "/api/v1/tasks/write-report"

    def test_create_resource(self, client: BlackbeardClient, transport: MockTransport) -> None:
        resource = {
            "kind": "Agent",
            "metadata": {"name": "coder", "namespace": "default"},
            "spec": {"role": "Software Engineer"},
        }
        transport.queue(_mock_response(201, {**resource, "version": 1}))
        result = client.create(resource)
        assert result["version"] == 1
        req = transport.requests[0]
        assert req.method == "POST"
        assert req.url.path == "/api/v1/agents"

    def test_create_without_kind_raises(self, client: BlackbeardClient) -> None:
        with pytest.raises(ValueError, match="must contain a 'kind' key"):
            client.create({"metadata": {"name": "foo"}})

    def test_update_resource(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(_mock_response(200, {"kind": "Agent", "version": 2}))
        result = client.update("Agent", "coder", {"spec": {"role": "Senior Engineer"}, "version": 1})
        assert result["version"] == 2
        req = transport.requests[0]
        assert req.method == "PUT"
        assert req.url.path == "/api/v1/agents/coder"

    def test_delete_resource(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(_mock_response(204))
        client.delete("Agent", "coder")
        req = transport.requests[0]
        assert req.method == "DELETE"
        assert req.url.path == "/api/v1/agents/coder"

    def test_apply_multiple(self, client: BlackbeardClient, transport: MockTransport) -> None:
        resources = [
            {"kind": "Agent", "metadata": {"name": "a1"}},
            {"kind": "Task", "metadata": {"name": "t1"}},
        ]
        transport.queue(_mock_response(201, {"kind": "Agent", "metadata": {"name": "a1"}}))
        transport.queue(_mock_response(201, {"kind": "Task", "metadata": {"name": "t1"}}))
        results = client.apply(resources)
        assert len(results) == 2
        assert transport.requests[0].url.path == "/api/v1/agents"
        assert transport.requests[1].url.path == "/api/v1/tasks"

    def test_export_all(self, client: BlackbeardClient, transport: MockTransport) -> None:
        # Queue one response per kind
        for _kind in KIND_TO_PLURAL:
            transport.queue(
                _mock_response(200, {"items": [], "total": 0, "limit": 1000, "offset": 0, "has_more": False})
            )
        result = client.export_all()
        assert isinstance(result, str)
        # Should have made one request per kind
        assert len(transport.requests) == len(KIND_TO_PLURAL)

    def test_unknown_kind_raises(self, client: BlackbeardClient) -> None:
        with pytest.raises(ValueError, match="Unknown resource kind"):
            client.list("FakeKind")


# -- Execution tests ----------------------------------------------------------


class TestExecutions:
    def test_kickoff(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(202, {
                "id": "exec-1",
                "crew_name": "my-crew",
                "status": "queued",
            })
        )
        result = client.kickoff("my-crew", inputs={"topic": "AI"})
        assert result["status"] == "queued"
        req = transport.requests[0]
        assert req.method == "POST"
        assert req.url.path == "/api/v1/crews/my-crew/kickoff"
        body = json.loads(req.content)
        assert body["inputs"]["topic"] == "AI"

    def test_train(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(202, {"id": "exec-2", "status": "queued"})
        )
        result = client.train("my-crew", n_iterations=5)
        assert result["status"] == "queued"
        body = json.loads(transport.requests[0].content)
        assert body["n_iterations"] == 5
        assert body["filename"] == "training_data.pkl"

    def test_test(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(202, {"id": "exec-3", "status": "queued"})
        )
        result = client.test("my-crew", n_iterations=2)
        assert result["status"] == "queued"
        body = json.loads(transport.requests[0].content)
        assert body["n_iterations"] == 2

    def test_run_flow(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(202, {"id": "exec-4", "status": "queued"})
        )
        result = client.run_flow("my-flow", inputs={"step": "1"})
        assert result["status"] == "queued"
        req = transport.requests[0]
        assert req.url.path == "/api/v1/flows/my-flow/run"

    def test_get_execution(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {"id": "exec-1", "status": "completed"})
        )
        result = client.get_execution("exec-1")
        assert result["status"] == "completed"

    def test_list_executions(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {
                "items": [{"id": "e1"}, {"id": "e2"}],
                "total": 2,
                "limit": 100,
                "offset": 0,
                "has_more": False,
            })
        )
        items = client.list_executions(crew_name="my-crew")
        assert len(items) == 2
        assert "crew_name=my-crew" in str(transport.requests[0].url)

    def test_cancel(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {"id": "exec-1", "status": "cancelled"})
        )
        result = client.cancel("exec-1")
        assert result["status"] == "cancelled"
        req = transport.requests[0]
        assert req.method == "PATCH"

    def test_wait_completes(self, client: BlackbeardClient, transport: MockTransport) -> None:
        # First poll: running, second poll: completed
        transport.queue(_mock_response(200, {"id": "e1", "status": "running"}))
        transport.queue(_mock_response(200, {"id": "e1", "status": "completed"}))
        with patch("blackbeard_sdk.executions.time.sleep"):
            result = client.wait("e1", poll_interval=0.01, timeout=5)
        assert result["status"] == "completed"

    def test_wait_timeout(self, client: BlackbeardClient, transport: MockTransport) -> None:
        # Always return running
        for _ in range(50):
            transport.queue(_mock_response(200, {"id": "e1", "status": "running"}))
        with patch("blackbeard_sdk.executions.time.sleep"):
            with patch("blackbeard_sdk.executions.time.monotonic", side_effect=[0, 0, 999]):
                with pytest.raises(TimeoutError, match="did not complete"):
                    client.wait("e1", timeout=1)

    def test_get_execution_spend(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, [{"request_id": "e1", "spend": 0.05}])
        )
        result = client.get_execution_spend("e1")
        assert isinstance(result, list)

    def test_get_execution_events(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {
                "events": [{"sequence": 1, "event_type": "task_started"}],
                "next_sequence": 1,
                "has_more": False,
            })
        )
        result = client.get_execution_events("e1", after=0)
        assert len(result["events"]) == 1


# -- Health tests -------------------------------------------------------------


class TestHealth:
    def test_health(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {"status": "ok", "service": "blackbeard", "version": "0.1.0"})
        )
        result = client.health()
        assert result["status"] == "ok"

    def test_readiness(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(
            _mock_response(200, {
                "status": "healthy",
                "service": "blackbeard",
                "checks": {"database": {"status": "up"}},
            })
        )
        result = client.readiness()
        assert result["status"] == "healthy"


# -- Client lifecycle tests ---------------------------------------------------


class TestClientLifecycle:
    def test_context_manager(self, transport: MockTransport) -> None:
        with BlackbeardClient(base_url="http://test:8000", api_key="k") as c:
            c._http = httpx.Client(
                base_url="http://test:8000",
                transport=transport,
            )
            transport.queue(_mock_response(200, {"status": "ok"}))
            c.health()
        # After context exit, client should be closed

    def test_repr(self) -> None:
        c = BlackbeardClient(base_url="http://localhost:8000")
        assert "localhost:8000" in repr(c)
        c.close()

    def test_api_key_header(self) -> None:
        c = BlackbeardClient(api_key="my-key")
        assert c._http.headers["X-API-Key"] == "my-key"
        c.close()

    def test_token_header(self) -> None:
        c = BlackbeardClient(token="jwt-token")
        assert c._http.headers["Authorization"] == "Bearer jwt-token"
        c.close()


# -- kind_plural helper tests -------------------------------------------------


class TestKindPlural:
    def test_known_kinds(self) -> None:
        assert _kind_plural("Agent") == "agents"
        assert _kind_plural("LLMConnection") == "llm-connections"
        assert _kind_plural("RoleBinding") == "role-bindings"

    def test_plural_passthrough(self) -> None:
        assert _kind_plural("agents") == "agents"
        assert _kind_plural("llm-connections") == "llm-connections"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown resource kind"):
            _kind_plural("Nonexistent")
