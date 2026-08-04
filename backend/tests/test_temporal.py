"""Tests for the optional Temporal workflow engine module.

These tests exercise the code paths that work without the temporalio
package installed: dataclass serialization, config defaults, and the
graceful-degradation flag.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from blackbeard.engine.temporal import TEMPORAL_AVAILABLE, CrewExecutionInput

# ---------------------------------------------------------------------------
# TEMPORAL_AVAILABLE flag
# ---------------------------------------------------------------------------


class TestTemporalAvailability:
    def test_flag_is_boolean(self):
        assert isinstance(TEMPORAL_AVAILABLE, bool)

    def test_flag_reflects_import_status(self):
        # In the test environment temporalio is not installed,
        # so the flag should be False.
        try:
            import temporalio  # noqa: F401

            expected = True
        except ImportError:
            expected = False
        assert TEMPORAL_AVAILABLE is expected


# ---------------------------------------------------------------------------
# CrewExecutionInput dataclass
# ---------------------------------------------------------------------------


class TestCrewExecutionInput:
    def test_basic_creation(self):
        inp = CrewExecutionInput(
            execution_id="550e8400-e29b-41d4-a716-446655440000",
            resource_snapshot={"agents/researcher": {"role": "Analyst"}},
            crew_name="research-crew",
            inputs={"topic": "quantum computing"},
            execution_type="kickoff",
        )
        assert inp.execution_id == "550e8400-e29b-41d4-a716-446655440000"
        assert inp.crew_name == "research-crew"
        assert inp.execution_type == "kickoff"
        assert inp.inputs == {"topic": "quantum computing"}

    def test_default_values(self):
        inp = CrewExecutionInput(
            execution_id="test-id",
            resource_snapshot={},
            crew_name="crew",
            inputs={},
            execution_type="kickoff",
        )
        assert inp.n_iterations == 1
        assert inp.training_file == "training_data.pkl"

    def test_custom_iterations_and_training_file(self):
        inp = CrewExecutionInput(
            execution_id="test-id",
            resource_snapshot={},
            crew_name="crew",
            inputs={},
            execution_type="train",
            n_iterations=5,
            training_file="custom_train.pkl",
        )
        assert inp.n_iterations == 5
        assert inp.training_file == "custom_train.pkl"

    def test_serializable_to_dict(self):
        inp = CrewExecutionInput(
            execution_id="abc-123",
            resource_snapshot={"crews/demo": {"agents": []}},
            crew_name="demo",
            inputs={"key": "value"},
            execution_type="test",
            n_iterations=3,
            training_file="data.pkl",
        )
        d = asdict(inp)
        assert d["execution_id"] == "abc-123"
        assert d["crew_name"] == "demo"
        assert d["n_iterations"] == 3
        assert isinstance(d["resource_snapshot"], dict)

    def test_complex_resource_snapshot(self):
        snapshot = {
            "agents/researcher": {
                "role": "Analyst",
                "goal": "Find info",
                "backstory": "Expert researcher",
            },
            "tasks/analyze": {
                "description": "Analyze data",
                "expected_output": "Report",
            },
            "crews/research": {
                "agents": ["ref:agents/researcher"],
                "tasks": ["ref:tasks/analyze"],
            },
        }
        inp = CrewExecutionInput(
            execution_id="snap-test",
            resource_snapshot=snapshot,
            crew_name="research",
            inputs={},
            execution_type="kickoff",
        )
        assert len(inp.resource_snapshot) == 3
        assert "agents/researcher" in inp.resource_snapshot


# ---------------------------------------------------------------------------
# submit_temporal_execution (unavailable path)
# ---------------------------------------------------------------------------


class TestSubmitTemporalExecution:
    async def test_raises_when_temporal_unavailable(self):
        if TEMPORAL_AVAILABLE:
            pytest.skip("temporalio is installed, cannot test unavailable path")

        from blackbeard.engine.temporal import submit_temporal_execution

        with pytest.raises(RuntimeError, match="not installed"):
            await submit_temporal_execution(
                execution_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
                resource_snapshot={},
                crew_name="test",
                inputs={},
                execution_type="kickoff",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Settings defaults for temporal fields
# ---------------------------------------------------------------------------


class TestTemporalSettings:
    def test_temporal_host_defaults_to_none(self):
        from blackbeard.config import settings

        assert settings.temporal_host is None

    def test_temporal_namespace_default(self):
        from blackbeard.config import settings

        assert settings.temporal_namespace == "blackbeard"

    def test_temporal_task_queue_default(self):
        from blackbeard.config import settings

        assert settings.temporal_task_queue == "crew-execution"

    def test_temporal_workflow_timeout_default(self):
        from blackbeard.config import settings

        assert settings.temporal_workflow_timeout_s == 3600
