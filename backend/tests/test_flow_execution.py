"""Tests for flow execution via _run_flow_steps().

Covers:
  - Flow with 2 crew steps executing sequentially
  - Flow step outputs chaining into next step's inputs
  - Flow with function step calling the function
  - Flow with missing crew ref logging warning and skipping
  - Flow resource not found raising LoaderError
  - Router/condition step type (no-op path)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.flow_runner import run_flow_steps as _run_flow_steps
from blackbeard.engine.loader import LoaderError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crew_output(raw: str):
    """Create a mock CrewOutput with the given raw string."""
    mock = MagicMock()
    mock.raw = raw
    # Make isinstance() check work by patching at usage site
    return mock


# ---------------------------------------------------------------------------
# Tests -- _run_flow_steps
# ---------------------------------------------------------------------------


def test_flow_two_crew_steps_sequential():
    """Flow with 2 crew steps should execute them sequentially."""
    resource_snapshot = {
        "Flow/my-flow": {
            "kind": "Flow",
            "name": "my-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {"name": "step-1", "type": "crew", "crew": "ref:crews/crew-a"},
                    {"name": "step-2", "type": "crew", "crew": "ref:crews/crew-b"},
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_crew_a = MagicMock()
    mock_crew_b = MagicMock()

    # Create mock CrewOutput instances
    from crewai.crews.crew_output import CrewOutput

    output_a = MagicMock(spec=CrewOutput)
    output_a.raw = "Result from crew A"
    output_b = MagicMock(spec=CrewOutput)
    output_b.raw = "Result from crew B"

    mock_crew_a.kickoff.return_value = output_a
    mock_crew_b.kickoff.return_value = output_b

    def build_crew_side_effect(name):
        if name == "crew-a":
            return mock_crew_a
        if name == "crew-b":
            return mock_crew_b
        raise LoaderError(f"Crew '{name}' not found")

    mock_loader.build_crew.side_effect = build_crew_side_effect
    mock_listener = MagicMock()

    result = _run_flow_steps(
        mock_loader, resource_snapshot, "my-flow", {"topic": "AI"}, mock_listener
    )

    # Both crews should have been called
    assert mock_crew_a.kickoff.call_count == 1
    assert mock_crew_b.kickoff.call_count == 1

    # The last result should be returned
    assert result is output_b


def test_flow_step_outputs_chain():
    """Step outputs should chain into next step's inputs."""
    resource_snapshot = {
        "Flow/chain-flow": {
            "kind": "Flow",
            "name": "chain-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {"name": "fetch", "type": "crew", "crew": "ref:crews/fetcher"},
                    {"name": "process", "type": "crew", "crew": "ref:crews/processor"},
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_fetcher = MagicMock()
    mock_processor = MagicMock()

    from crewai.crews.crew_output import CrewOutput

    fetch_output = MagicMock(spec=CrewOutput)
    fetch_output.raw = "fetched data"
    mock_fetcher.kickoff.return_value = fetch_output

    process_output = MagicMock(spec=CrewOutput)
    process_output.raw = "processed result"
    mock_processor.kickoff.return_value = process_output

    def build_crew_side_effect(name):
        if name == "fetcher":
            return mock_fetcher
        if name == "processor":
            return mock_processor
        raise LoaderError(f"Unknown crew: {name}")

    mock_loader.build_crew.side_effect = build_crew_side_effect
    mock_listener = MagicMock()

    _run_flow_steps(mock_loader, resource_snapshot, "chain-flow", {"query": "test"}, mock_listener)

    # Verify the second step received the first step's output in inputs
    process_call_inputs = mock_processor.kickoff.call_args[1]["inputs"]
    assert process_call_inputs["query"] == "test"
    assert process_call_inputs["fetch"] == "fetched data"


def test_flow_function_step():
    """Flow with a function step should call the function with inputs."""
    resource_snapshot = {
        "Flow/fn-flow": {
            "kind": "Flow",
            "name": "fn-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {
                        "name": "transform",
                        "type": "function",
                        "function_path": "blackbeard.flows.my_module:transform_data",
                    },
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_listener = MagicMock()

    mock_fn = MagicMock(return_value="transformed")
    mock_module = MagicMock()
    mock_module.transform_data = mock_fn

    with patch("importlib.import_module", return_value=mock_module):
        _run_flow_steps(mock_loader, resource_snapshot, "fn-flow", {"data": "raw"}, mock_listener)

    mock_fn.assert_called_once()
    call_args = mock_fn.call_args[0][0]
    assert call_args["data"] == "raw"


def test_flow_missing_crew_ref_skips_step():
    """Flow step with no crew ref should log warning and skip."""
    resource_snapshot = {
        "Flow/skip-flow": {
            "kind": "Flow",
            "name": "skip-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {"name": "broken-step", "type": "crew"},
                    {"name": "ok-step", "type": "crew", "crew": "ref:crews/ok"},
                ],
            },
        },
    }

    mock_loader = MagicMock()
    from crewai.crews.crew_output import CrewOutput

    ok_output = MagicMock(spec=CrewOutput)
    ok_output.raw = "ok result"
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = ok_output
    mock_loader.build_crew.return_value = mock_crew
    mock_listener = MagicMock()

    result = _run_flow_steps(mock_loader, resource_snapshot, "skip-flow", {}, mock_listener)

    # Only one crew should have been built (the broken step was skipped)
    assert mock_loader.build_crew.call_count == 1
    assert result is ok_output


def test_flow_not_found_raises_loader_error():
    """Flow resource not found in snapshot should raise LoaderError."""
    resource_snapshot = {}

    mock_loader = MagicMock()
    mock_listener = MagicMock()

    with pytest.raises(LoaderError, match="not found"):
        _run_flow_steps(mock_loader, resource_snapshot, "missing-flow", {}, mock_listener)


def test_flow_non_crew_output_stringified():
    """Non-CrewOutput result from crew.kickoff should be stringified."""
    resource_snapshot = {
        "Flow/str-flow": {
            "kind": "Flow",
            "name": "str-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {"name": "step-1", "type": "crew", "crew": "crews/my-crew"},
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = "plain string result"
    mock_loader.build_crew.return_value = mock_crew
    mock_listener = MagicMock()

    result = _run_flow_steps(mock_loader, resource_snapshot, "str-flow", {}, mock_listener)

    assert result == "plain string result"


def test_flow_router_step_continues():
    """Router step type should log and continue without error."""
    resource_snapshot = {
        "Flow/router-flow": {
            "kind": "Flow",
            "name": "router-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {"name": "route-step", "type": "router"},
                    {"name": "cond-step", "type": "condition"},
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_listener = MagicMock()

    # Should not raise
    result = _run_flow_steps(mock_loader, resource_snapshot, "router-flow", {}, mock_listener)

    # No crews should be built
    mock_loader.build_crew.assert_not_called()
    assert result is None


def test_flow_function_step_blocked_module():
    """Function step referencing a blocked module should be rejected."""
    resource_snapshot = {
        "Flow/blocked-flow": {
            "kind": "Flow",
            "name": "blocked-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {
                        "name": "evil",
                        "type": "function",
                        "function_path": "os:system",
                    },
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_listener = MagicMock()

    with patch("importlib.import_module") as mock_import:
        result = _run_flow_steps(mock_loader, resource_snapshot, "blocked-flow", {}, mock_listener)

    # Blocked module must never be imported
    mock_import.assert_not_called()
    assert result is None


def test_flow_function_step_not_in_allowlist():
    """Function step with path not in allowlist must not be imported."""
    resource_snapshot = {
        "Flow/noallow-flow": {
            "kind": "Flow",
            "name": "noallow-flow",
            "project": "default",
            "spec": {
                "steps": [
                    {
                        "name": "notallowed",
                        "type": "function",
                        "function_path": "mycompany.internal:run",
                    },
                ],
            },
        },
    }

    mock_loader = MagicMock()
    mock_listener = MagicMock()

    with patch("importlib.import_module") as mock_import:
        result = _run_flow_steps(mock_loader, resource_snapshot, "noallow-flow", {}, mock_listener)

    mock_import.assert_not_called()
    assert result is None


def test_flow_empty_steps():
    """Flow with empty steps list should return None and build no crews."""
    resource_snapshot = {
        "Flow/empty-flow": {
            "kind": "Flow",
            "name": "empty-flow",
            "project": "default",
            "spec": {
                "steps": [],
            },
        },
    }

    mock_loader = MagicMock()
    mock_listener = MagicMock()

    result = _run_flow_steps(mock_loader, resource_snapshot, "empty-flow", {}, mock_listener)
    assert result is None
    mock_loader.build_crew.assert_not_called()
