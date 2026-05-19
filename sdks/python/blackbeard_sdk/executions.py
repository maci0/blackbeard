"""Execution lifecycle operations for the Blackbeard SDK."""

from __future__ import annotations

import time
from typing import Any

import httpx


class ExecutionMixin:
    """Execution lifecycle methods mixed into BlackbeardClient."""

    _http: httpx.Client

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
        resp = self._http.post(
            f"/api/v1/crews/{crew_name}/kickoff",
            params={"namespace": namespace},
            json={"inputs": inputs or {}},
        )
        resp.raise_for_status()
        return resp.json()

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
        resp = self._http.post(
            f"/api/v1/crews/{crew_name}/train",
            params={"namespace": namespace},
            json={
                "inputs": inputs or {},
                "n_iterations": n_iterations,
                "filename": filename,
            },
        )
        resp.raise_for_status()
        return resp.json()

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
        resp = self._http.post(
            f"/api/v1/crews/{crew_name}/test",
            params={"namespace": namespace},
            json={
                "inputs": inputs or {},
                "n_iterations": n_iterations,
            },
        )
        resp.raise_for_status()
        return resp.json()

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
        resp = self._http.post(
            f"/api/v1/flows/{flow_name}/run",
            params={"namespace": namespace},
            json={"inputs": inputs or {}},
        )
        resp.raise_for_status()
        return resp.json()

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        """Get execution details by ID.

        Args:
            execution_id: Execution UUID string.

        Returns:
            Execution dict.
        """
        resp = self._http.get(f"/api/v1/executions/{execution_id}")
        resp.raise_for_status()
        return resp.json()

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
        resp = self._http.get("/api/v1/executions", params=params)
        resp.raise_for_status()
        return resp.json()["items"]

    def cancel(self, execution_id: str) -> dict[str, Any]:
        """Cancel a queued or running execution.

        Args:
            execution_id: Execution UUID string.

        Returns:
            Updated execution dict.
        """
        resp = self._http.patch(f"/api/v1/executions/{execution_id}/cancel")
        resp.raise_for_status()
        return resp.json()

    def get_execution_spend(self, execution_id: str) -> dict[str, Any]:
        """Get LiteLLM spend data for an execution.

        Args:
            execution_id: Execution UUID string.

        Returns:
            Spend data dict from LiteLLM.
        """
        resp = self._http.get(f"/api/v1/executions/{execution_id}/spend")
        resp.raise_for_status()
        return resp.json()

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
        resp = self._http.get(
            f"/api/v1/executions/{execution_id}/events",
            params={"after": after, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

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
        terminal = {"completed", "failed", "cancelled"}
        deadline = time.monotonic() + timeout
        while True:
            execution = self.get_execution(execution_id)
            if execution.get("status") in terminal:
                return execution
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Execution {execution_id} did not complete within {timeout}s "
                    f"(current status: {execution.get('status')})"
                )
            time.sleep(poll_interval)
