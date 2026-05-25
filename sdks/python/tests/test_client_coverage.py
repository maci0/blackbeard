"""Additional tests for BlackbeardClient covering error handling and edge cases.

Covers:
  - HTTP error responses (404, 500, network errors) for all method categories
  - Edge cases in resource operations (label_selector, offset, namespace)
  - Execution lifecycle edge cases (custom params, status filters)
  - Client initialization variants
  - export_all with actual resources
  - apply with empty list
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from blackbeard_sdk import BlackbeardApiError, BlackbeardClient
from blackbeard_sdk.resources import KIND_TO_PLURAL, _kind_plural

from .conftest import MockTransport, _mock_response


# -- Error handling tests -----------------------------------------------------


class TestErrorHandling:
    def test_health_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.health()

    def test_health_500(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(500, {"detail": "Internal error"}))
        with pytest.raises(BlackbeardApiError):
            client.health()

    def test_readiness_500(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(500, {"detail": "degraded"}))
        with pytest.raises(BlackbeardApiError):
            client.readiness()

    def test_list_404(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.list("Agent")

    def test_get_404(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.get("Agent", "nonexistent")

    def test_create_422(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(422, {"detail": "Validation error"}))
        with pytest.raises(BlackbeardApiError):
            client.create({"kind": "Agent", "metadata": {"name": "bad"}})

    def test_update_409(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(409, {"detail": "Version conflict"}))
        with pytest.raises(BlackbeardApiError):
            client.update("Agent", "test", {"spec": {}, "version": 1})

    def test_delete_500(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(500, {"detail": "Internal error"}))
        with pytest.raises(BlackbeardApiError):
            client.delete("Agent", "test")

    def test_kickoff_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Crew not found"}))
        with pytest.raises(BlackbeardApiError):
            client.kickoff("nonexistent-crew")

    def test_train_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Crew not found"}))
        with pytest.raises(BlackbeardApiError):
            client.train("nonexistent-crew")

    def test_test_404(self, client: BlackbeardClient, transport: MockTransport) -> None:
        transport.queue(_mock_response(404, {"detail": "Crew not found"}))
        with pytest.raises(BlackbeardApiError):
            client.test("nonexistent-crew")

    def test_run_flow_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Flow not found"}))
        with pytest.raises(BlackbeardApiError):
            client.run_flow("nonexistent-flow")

    def test_get_execution_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.get_execution("nonexistent-id")

    def test_cancel_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.cancel("nonexistent-id")

    def test_login_401(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(401, {"detail": "Invalid credentials"}))
        with pytest.raises(BlackbeardApiError):
            client.login("bad@email.com", "wrongpass")

    def test_register_409(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(409, {"detail": "Already exists"}))
        with pytest.raises(BlackbeardApiError):
            client.register("dup@email.com", "pass123", "Dup User")

    def test_whoami_401(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(401, {"detail": "Not authenticated"}))
        with pytest.raises(BlackbeardApiError):
            client.whoami()

    def test_refresh_401(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(401, {"detail": "Invalid token"}))
        with pytest.raises(BlackbeardApiError):
            client.refresh("bad-refresh-token")

    def test_get_execution_spend_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.get_execution_spend("nonexistent-id")

    def test_get_execution_events_404(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(404, {"detail": "Not found"}))
        with pytest.raises(BlackbeardApiError):
            client.get_execution_events("nonexistent-id")


# -- Resource edge cases ------------------------------------------------------


class TestResourceEdgeCases:
    def test_list_with_label_selector(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(
                200,
                {
                    "items": [{"kind": "Agent", "metadata": {"name": "labeled"}}],
                    "total": 1,
                    "limit": 100,
                    "offset": 0,
                    "has_more": False,
                },
            )
        )
        items = client.list("Agent", label_selector="env=prod,team=ml")
        assert len(items) == 1
        req = transport.requests[0]
        assert "label_selector=env" in str(req.url)

    def test_list_with_offset(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(
                200,
                {
                    "items": [],
                    "total": 5,
                    "limit": 2,
                    "offset": 4,
                    "has_more": False,
                },
            )
        )
        items = client.list("Agent", limit=2, offset=4)
        assert items == []
        req = transport.requests[0]
        assert "offset=4" in str(req.url)
        assert "limit=2" in str(req.url)

    def test_get_with_custom_namespace(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(200, {"kind": "Agent", "metadata": {"name": "test"}})
        )
        client.get("Agent", "test", namespace="prod")
        req = transport.requests[0]
        assert "namespace=prod" in str(req.url)

    def test_update_with_custom_namespace(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(200, {"kind": "Agent", "version": 2}))
        client.update("Agent", "test", {"spec": {}, "version": 1}, namespace="staging")
        req = transport.requests[0]
        assert "namespace=staging" in str(req.url)

    def test_delete_with_custom_namespace(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(204))
        client.delete("Agent", "test", namespace="prod")
        req = transport.requests[0]
        assert "namespace=prod" in str(req.url)

    def test_apply_empty_list(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        results = client.apply([])
        assert results == []
        assert len(transport.requests) == 0


# -- Execution edge cases -----------------------------------------------------


class TestExecutionEdgeCases:
    def test_kickoff_without_inputs(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(202, {"id": "exec-x", "status": "queued"}))
        result = client.kickoff("my-crew")
        body = json.loads(transport.requests[0].content)
        assert body["inputs"] == {}
        assert result["status"] == "queued"

    def test_kickoff_custom_namespace(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(202, {"id": "exec-x", "status": "queued"}))
        client.kickoff("my-crew", namespace="prod")
        req = transport.requests[0]
        assert "namespace=prod" in str(req.url)

    def test_train_with_custom_filename(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(202, {"id": "exec-x", "status": "queued"}))
        client.train("my-crew", filename="custom.pkl")
        body = json.loads(transport.requests[0].content)
        assert body["filename"] == "custom.pkl"

    def test_train_with_inputs(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(202, {"id": "exec-x", "status": "queued"}))
        client.train("my-crew", inputs={"topic": "AI"}, n_iterations=10)
        body = json.loads(transport.requests[0].content)
        assert body["inputs"]["topic"] == "AI"
        assert body["n_iterations"] == 10

    def test_test_with_inputs(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(202, {"id": "exec-x", "status": "queued"}))
        client.test("my-crew", inputs={"topic": "ML"}, n_iterations=5)
        body = json.loads(transport.requests[0].content)
        assert body["inputs"]["topic"] == "ML"
        assert body["n_iterations"] == 5

    def test_run_flow_without_inputs(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(202, {"id": "exec-x", "status": "queued"}))
        client.run_flow("my-flow")
        body = json.loads(transport.requests[0].content)
        assert body["inputs"] == {}

    def test_list_executions_with_filters(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(
                200,
                {
                    "items": [{"id": "e1"}],
                    "total": 1,
                    "limit": 50,
                    "offset": 10,
                    "has_more": False,
                },
            )
        )
        items = client.list_executions(
            crew_name="my-crew",
            namespace="prod",
            status="completed",
            limit=50,
            offset=10,
        )
        assert len(items) == 1
        req = transport.requests[0]
        url_str = str(req.url)
        assert "crew_name=my-crew" in url_str
        assert "namespace=prod" in url_str
        assert "status=completed" in url_str
        assert "limit=50" in url_str
        assert "offset=10" in url_str

    def test_list_executions_no_filters(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(
                200,
                {
                    "items": [],
                    "total": 0,
                    "limit": 100,
                    "offset": 0,
                    "has_more": False,
                },
            )
        )
        items = client.list_executions()
        assert items == []

    def test_wait_failed_execution(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(200, {"id": "e1", "status": "failed", "error": "boom"})
        )
        with patch("blackbeard_sdk.executions.time.sleep"):
            result = client.wait("e1")
        assert result["status"] == "failed"

    def test_wait_cancelled_execution(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(_mock_response(200, {"id": "e1", "status": "cancelled"}))
        with patch("blackbeard_sdk.executions.time.sleep"):
            result = client.wait("e1")
        assert result["status"] == "cancelled"

    def test_get_execution_events_custom_params(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            _mock_response(
                200,
                {
                    "events": [],
                    "next_sequence": 50,
                    "has_more": False,
                },
            )
        )
        result = client.get_execution_events("e1", after=49, limit=10)
        req = transport.requests[0]
        assert "after=49" in str(req.url)
        assert "limit=10" in str(req.url)
        assert result["has_more"] is False


# -- Client initialization ---------------------------------------------------


class TestClientInit:
    def test_no_auth(self) -> None:
        c = BlackbeardClient(base_url="http://test:8000")
        assert "X-API-Key" not in c._http.headers
        assert "Authorization" not in c._http.headers
        c.close()

    def test_both_auth_token_wins(self) -> None:
        c = BlackbeardClient(api_key="key", token="tok")
        assert c._http.headers["Authorization"] == "Bearer tok"
        assert "X-API-Key" not in c._http.headers
        c.close()

    def test_custom_timeout(self) -> None:
        c = BlackbeardClient(timeout=60.0)
        assert c._http.timeout.connect == 60.0
        c.close()

    def test_default_base_url(self) -> None:
        c = BlackbeardClient()
        assert "localhost:8000" in str(c._http.base_url)
        c.close()


# -- Export all with resources ------------------------------------------------


class TestExportAll:
    def test_export_all_with_resources(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        """export_all uses the server's bulk export endpoint."""
        import yaml

        yaml_body = (
            b"---\nkind: Agent\nmetadata:\n  name: a1\nspec:\n  role: R\n"
        )
        transport.queue(
            httpx.Response(
                200,
                content=yaml_body,
                headers={"content-type": "application/x-yaml"},
            )
        )

        result = client.export_all()
        assert isinstance(result, str)
        docs = [d for d in yaml.safe_load_all(result) if d is not None]
        assert len(docs) == 1
        assert docs[0]["kind"] == "Agent"
        assert len(transport.requests) == 1
        assert transport.requests[0].url.path == "/api/v1/resources/export"

    def test_export_all_custom_namespace(
        self, client: BlackbeardClient, transport: MockTransport
    ) -> None:
        transport.queue(
            httpx.Response(
                200,
                content=b"",
                headers={"content-type": "application/x-yaml"},
            )
        )
        client.export_all(namespace="staging")
        assert len(transport.requests) == 1
        assert "namespace=staging" in str(transport.requests[0].url)


# -- kind_plural edge cases ---------------------------------------------------


class TestKindPluralEdge:
    def test_automation_kind(self) -> None:
        """Automation kind resolves to its plural."""
        assert _kind_plural("Automation") == "automations"

    def test_all_known_kinds_resolve(self) -> None:
        for kind, expected_plural in KIND_TO_PLURAL.items():
            assert _kind_plural(kind) == expected_plural

    def test_all_plurals_pass_through(self) -> None:
        for plural in KIND_TO_PLURAL.values():
            assert _kind_plural(plural) == plural

    def test_case_sensitive(self) -> None:
        """Kind lookup is case-sensitive."""
        with pytest.raises(ValueError):
            _kind_plural("agent")  # lowercase should fail
