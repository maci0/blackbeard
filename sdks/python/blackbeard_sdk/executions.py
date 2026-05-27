"""Execution lifecycle operations for the Blackbeard SDK."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


class ExecutionMixin:
    """Execution lifecycle methods mixed into BlackbeardClient."""

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        raise NotImplementedError

    def kickoff(
        self,
        crew_name: str,
        inputs: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Kick off a crew execution.

        Args:
            crew_name: Name of the crew to execute.
            inputs: Key-value inputs passed to the crew.
            namespace: Namespace containing the crew.

        Returns:
            Execution dict with status=queued.
        """
        return self._send(
            "POST",
            f"/api/v1/crews/{quote(crew_name, safe='')}/kickoff",
            params={"namespace": namespace},
            json={"inputs": inputs or {}},
        ).json()

    def train(
        self,
        crew_name: str,
        inputs: dict[str, Any] | None = None,
        n_iterations: int = 3,
        filename: str = "training_data.pkl",
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Start a crew training run.

        Args:
            crew_name: Name of the crew to train.
            inputs: Key-value inputs passed to the crew.
            n_iterations: Number of training iterations (1-100).
            filename: Filename for training data output (must end with .pkl).
            namespace: Namespace containing the crew.

        Returns:
            Execution dict with status=queued.
        """
        return self._send(
            "POST",
            f"/api/v1/crews/{quote(crew_name, safe='')}/train",
            params={"namespace": namespace},
            json={
                "inputs": inputs or {},
                "n_iterations": n_iterations,
                "filename": filename,
            },
        ).json()

    def test(
        self,
        crew_name: str,
        inputs: dict[str, Any] | None = None,
        n_iterations: int = 3,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Start a crew test run.

        Args:
            crew_name: Name of the crew to test.
            inputs: Key-value inputs passed to the crew.
            n_iterations: Number of test iterations (1-100).
            namespace: Namespace containing the crew.

        Returns:
            Execution dict with status=queued.
        """
        return self._send(
            "POST",
            f"/api/v1/crews/{quote(crew_name, safe='')}/test",
            params={"namespace": namespace},
            json={
                "inputs": inputs or {},
                "n_iterations": n_iterations,
            },
        ).json()

    def run_flow(
        self,
        flow_name: str,
        inputs: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Run a flow.

        Args:
            flow_name: Name of the flow to run.
            inputs: Key-value inputs passed to the flow.
            namespace: Namespace containing the flow.

        Returns:
            Execution dict with status=queued.
        """
        return self._send(
            "POST",
            f"/api/v1/flows/{quote(flow_name, safe='')}/run",
            params={"namespace": namespace},
            json={"inputs": inputs or {}},
        ).json()

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        """Get execution details by ID.

        Args:
            execution_id: Execution UUID string.

        Returns:
            Execution dict.
        """
        return self._send(
            "GET", f"/api/v1/executions/{quote(execution_id, safe='')}"
        ).json()

    def list_executions(
        self,
        *,
        crew_name: str | None = None,
        namespace: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List executions with optional filters.

        Args:
            crew_name: Filter by crew name.
            namespace: Filter by namespace.
            status: Filter by execution status.
            limit: Maximum number of results (1-1000).
            offset: Number of results to skip.

        Returns:
            List of execution dicts.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if crew_name:
            params["crew_name"] = crew_name
        if namespace:
            params["namespace"] = namespace
        if status:
            params["status"] = status
        return self._send(
            "GET", "/api/v1/executions", params=params
        ).json()["items"]

    def cancel(self, execution_id: str) -> dict[str, Any]:
        """Cancel a queued or running execution.

        Args:
            execution_id: Execution UUID string.

        Returns:
            Updated execution dict.
        """
        return self._send(
            "PATCH",
            f"/api/v1/executions/{quote(execution_id, safe='')}/cancel",
        ).json()

    def get_execution_spend(self, execution_id: str) -> list[dict[str, Any]]:
        """Get LiteLLM spend data for an execution.

        Args:
            execution_id: Execution UUID string.

        Returns:
            List of spend records from LiteLLM.
        """
        return self._send(
            "GET",
            f"/api/v1/executions/{quote(execution_id, safe='')}/spend",
        ).json()

    def get_execution_events(
        self,
        execution_id: str,
        *,
        after: int = -1,
        limit: int = 200,
    ) -> dict[str, Any]:
        """List execution events for streaming/replay.

        Args:
            execution_id: Execution UUID string.
            after: Return events with sequence > after.
            limit: Maximum events to return (1-1000).

        Returns:
            Dict with events list, next_sequence, and has_more.
        """
        return self._send(
            "GET",
            f"/api/v1/executions/{quote(execution_id, safe='')}/events",
            params={"after": after, "limit": limit},
        ).json()

    def respond(
        self,
        execution_id: str,
        response: str,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """Submit a human-in-the-loop response to a paused execution.

        Args:
            execution_id: Execution UUID string.
            response: Free-text response from the human reviewer.
            feedback: Optional additional feedback or instructions.

        Returns:
            Dict with status and execution_id confirming the response was recorded.
        """
        body: dict[str, str] = {"response": response}
        if feedback is not None:
            body["feedback"] = feedback
        return self._send(
            "POST",
            f"/api/v1/executions/{quote(execution_id, safe='')}/respond",
            json=body,
        ).json()

    def retry(self, execution_id: str) -> dict[str, Any]:
        """Retry a terminal execution.

        Creates a new execution with the same crew, namespace, and inputs.
        Only works on completed, failed, or cancelled executions.

        Args:
            execution_id: Execution UUID string of the original execution.

        Returns:
            New execution dict with status=queued.
        """
        return self._send(
            "POST",
            f"/api/v1/executions/{quote(execution_id, safe='')}/retry",
        ).json()

    def wait(
        self,
        execution_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Wait for an execution to reach a terminal status.

        Polls the execution endpoint until the status is one of
        completed, failed, or cancelled, or until the timeout is reached.

        Args:
            execution_id: Execution UUID string.
            poll_interval: Seconds between polls.
            timeout: Maximum seconds to wait before raising TimeoutError.

        Returns:
            Final execution dict.

        Raises:
            TimeoutError: If the execution does not complete within the timeout.
        """
        deadline = time.monotonic() + timeout
        while True:
            execution = self.get_execution(execution_id)
            if execution.get("status") in TERMINAL_STATUSES:
                return execution
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Execution {execution_id} did not complete within {timeout}s "
                    f"(current status: {execution.get('status')})"
                )
            time.sleep(poll_interval)
