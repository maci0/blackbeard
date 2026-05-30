"""Unit tests for remaining untested functions across the Blackbeard backend.

Covers:
- engine/scheduler.py: start, stop, reload, _schedule, _run_cron, _trigger_target
- engine/sandbox/base.py: BaseSandbox, _build_command, _execute_subprocess
- engine/sandbox/container_runtime.py: ContainerSandbox init, _build_command, execute
- engine/sandbox/gvisor_runtime.py: GVisorSandbox init, _build_command, execute
- engine/sandbox/wasm_runtime.py: WasmSandbox.invoke (additional coverage)
- api/auth.py: register, generate_api_key, revoke_api_key
- api/collaboration.py: ValkeyCollabBackend._listen, validate_ws_auth
- models/database.py: instrument_engine
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. AutomationScheduler.start()
# ---------------------------------------------------------------------------


class TestAutomationSchedulerStart:
    """Tests for AutomationScheduler.start()."""

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        assert scheduler._running is False

        mock_result = MagicMock()
        mock_result.scalars.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "blackbeard.engine.scheduler.async_session",
            return_value=mock_session,
        ):
            await scheduler.start()

        assert scheduler._running is True
        assert len(scheduler._tasks) == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_schedules_cron_automations(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        automation = MagicMock()
        automation.name = "daily-report"
        automation.project = "default"
        automation.spec = {
            "enabled": True,
            "trigger": {"type": "cron", "cron": "0 9 * * *"},
            "target": {"kind": "Crew", "name": "report-crew"},
            "inputs": {"topic": "daily"},
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value = [automation]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "blackbeard.engine.scheduler.async_session",
            return_value=mock_session,
        ):
            await scheduler.start()

        assert scheduler._running is True
        assert "daily-report" in scheduler._tasks

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_skips_disabled_automations(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        automation = MagicMock()
        automation.name = "disabled-auto"
        automation.project = "default"
        automation.spec = {
            "enabled": False,
            "trigger": {"type": "cron", "cron": "0 9 * * *"},
            "target": {"kind": "Crew", "name": "crew"},
            "inputs": {},
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value = [automation]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "blackbeard.engine.scheduler.async_session",
            return_value=mock_session,
        ):
            await scheduler.start()

        assert "disabled-auto" not in scheduler._tasks

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_skips_non_cron_triggers(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        automation = MagicMock()
        automation.name = "webhook-auto"
        automation.project = "default"
        automation.spec = {
            "enabled": True,
            "trigger": {"type": "webhook"},
            "target": {"kind": "Crew", "name": "crew"},
            "inputs": {},
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value = [automation]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "blackbeard.engine.scheduler.async_session",
            return_value=mock_session,
        ):
            await scheduler.start()

        assert "webhook-auto" not in scheduler._tasks

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_sets_running_false_on_exception(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "blackbeard.engine.scheduler.async_session",
                return_value=mock_session,
            ),
            pytest.raises(RuntimeError, match="db down"),
        ):
            await scheduler.start()

        assert scheduler._running is False


# ---------------------------------------------------------------------------
# 2. AutomationScheduler.stop()
# ---------------------------------------------------------------------------


class TestAutomationSchedulerStop:
    """Tests for AutomationScheduler.stop()."""

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True

        await scheduler.stop()

        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_all_tasks(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True

        task1 = MagicMock()
        task2 = MagicMock()
        scheduler._tasks = {"auto1": task1, "auto2": task2}

        await scheduler.stop()

        task1.cancel.assert_called_once()
        task2.cancel.assert_called_once()
        assert len(scheduler._tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_clears_tasks_dict(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True
        scheduler._tasks = {"a": MagicMock(), "b": MagicMock(), "c": MagicMock()}

        await scheduler.stop()

        assert scheduler._tasks == {}


# ---------------------------------------------------------------------------
# 3. AutomationScheduler.reload()
# ---------------------------------------------------------------------------


class TestAutomationSchedulerReload:
    """Tests for AutomationScheduler.reload()."""

    @pytest.mark.asyncio
    async def test_reload_calls_stop_then_start(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        call_order: list[str] = []

        async def mock_stop() -> None:
            call_order.append("stop")

        async def mock_start() -> None:
            call_order.append("start")

        scheduler.stop = mock_stop  # type: ignore[assignment]
        scheduler.start = mock_start  # type: ignore[assignment]

        await scheduler.reload()

        assert call_order == ["stop", "start"]


# ---------------------------------------------------------------------------
# 4. AutomationScheduler._schedule()
# ---------------------------------------------------------------------------


class TestAutomationSchedulerSchedule:
    """Tests for AutomationScheduler._schedule()."""

    def test_schedule_creates_task(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True

        # Patch asyncio.create_task to capture the call
        mock_task = MagicMock()
        with patch("asyncio.create_task", return_value=mock_task):
            scheduler._schedule(
                "my-automation",
                "0 9 * * *",
                {"kind": "Crew", "name": "crew"},
                {"key": "value"},
                "default",
            )

        assert "my-automation" in scheduler._tasks
        assert scheduler._tasks["my-automation"] is mock_task
        mock_task.add_done_callback.assert_called_once()

    def test_schedule_rejects_sub_minute_cron(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        # 6-field cron expression (second-resolution) should be rejected
        with patch("asyncio.create_task") as mock_create:
            scheduler._schedule(
                "too-fast",
                "*/5 * * * * *",
                {"kind": "Crew", "name": "crew"},
                {},
                "default",
            )

        mock_create.assert_not_called()
        assert "too-fast" not in scheduler._tasks

    def test_schedule_rejects_invalid_cron(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        with patch("asyncio.create_task") as mock_create:
            scheduler._schedule(
                "bad-cron",
                "not-a-cron",
                {"kind": "Crew", "name": "crew"},
                {},
                "default",
            )

        mock_create.assert_not_called()
        assert "bad-cron" not in scheduler._tasks

    def test_schedule_cancels_existing_task(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        old_task = MagicMock()
        scheduler._tasks["existing"] = old_task

        new_task = MagicMock()
        with patch("asyncio.create_task", return_value=new_task):
            scheduler._schedule(
                "existing",
                "0 9 * * *",
                {"kind": "Crew", "name": "crew"},
                {},
                "default",
            )

        old_task.cancel.assert_called_once()
        assert scheduler._tasks["existing"] is new_task


# ---------------------------------------------------------------------------
# 5. AutomationScheduler._run_cron()
# ---------------------------------------------------------------------------


class TestAutomationSchedulerRunCron:
    """Tests for AutomationScheduler._run_cron()."""

    @pytest.mark.asyncio
    async def test_run_cron_returns_on_invalid_expression(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True

        # "invalid" is not a valid cron expression; _run_cron should return
        await scheduler._run_cron(
            "bad-auto",
            "invalid-cron-expr",
            {"kind": "Crew", "name": "crew"},
            {},
            "default",
        )

        # Should return without raising

    @pytest.mark.asyncio
    async def test_run_cron_triggers_target_and_stops(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True

        trigger_called = asyncio.Event()

        async def mock_trigger(name: str, target: Any, inputs: Any, project: str) -> None:
            trigger_called.set()
            # Stop the scheduler after first trigger to break the loop
            scheduler._running = False

        scheduler._trigger_target = mock_trigger  # type: ignore[assignment]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await scheduler._run_cron(
                "test-auto",
                "* * * * *",
                {"kind": "Crew", "name": "crew"},
                {"key": "val"},
                "default",
            )

        assert trigger_called.is_set()

    @pytest.mark.asyncio
    async def test_run_cron_breaks_when_running_is_false(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = False

        # Should exit immediately since _running is False
        await scheduler._run_cron(
            "auto",
            "0 9 * * *",
            {"kind": "Crew", "name": "crew"},
            {},
            "default",
        )


# ---------------------------------------------------------------------------
# 6. AutomationScheduler._trigger_target()
# ---------------------------------------------------------------------------


class TestAutomationSchedulerTriggerTarget:
    """Tests for AutomationScheduler._trigger_target()."""

    @pytest.mark.asyncio
    async def test_trigger_crew_target(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "blackbeard.engine.scheduler.async_session",
                return_value=mock_session,
            ),
            patch("blackbeard.engine.executor.kickoff", new_callable=AsyncMock) as mock_kickoff,
            patch("blackbeard.engine.executor.run_flow", new_callable=AsyncMock),
        ):
            await scheduler._trigger_target(
                "auto-1",
                {"kind": "Crew", "name": "my-crew"},
                {"topic": "AI"},
                "default",
            )

        mock_kickoff.assert_awaited_once_with(
            mock_session,
            "my-crew",
            inputs={"topic": "AI"},
            project="default",
        )

    @pytest.mark.asyncio
    async def test_trigger_flow_target(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "blackbeard.engine.scheduler.async_session",
                return_value=mock_session,
            ),
            patch("blackbeard.engine.executor.kickoff", new_callable=AsyncMock),
            patch("blackbeard.engine.executor.run_flow", new_callable=AsyncMock) as mock_run_flow,
        ):
            await scheduler._trigger_target(
                "auto-2",
                {"kind": "Flow", "name": "my-flow"},
                {"step": "1"},
                "default",
            )

        mock_run_flow.assert_awaited_once_with(
            mock_session,
            "my-flow",
            inputs={"step": "1"},
            project="default",
        )

    @pytest.mark.asyncio
    async def test_trigger_handles_exception_gracefully(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "blackbeard.engine.scheduler.async_session",
                return_value=mock_session,
            ),
            patch(
                "blackbeard.engine.executor.kickoff",
                new_callable=AsyncMock,
                side_effect=RuntimeError("kickoff failed"),
            ),
        ):
            # Should not raise -- error is caught and logged
            await scheduler._trigger_target(
                "failing-auto",
                {"kind": "Crew", "name": "bad-crew"},
                {},
                "default",
            )


# ---------------------------------------------------------------------------
# 7. ContainerSandbox and GVisorSandbox
# ---------------------------------------------------------------------------


class TestContainerSandboxInit:
    """Tests for ContainerSandbox.__init__."""

    def test_init_with_explicit_runtime(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")

        assert sandbox.runtime == "docker"

    def test_init_auto_detects_podman(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        def mock_which(name: str) -> str | None:
            if name == "podman":
                return "/usr/bin/podman"
            return None

        with patch("shutil.which", side_effect=mock_which):
            sandbox = ContainerSandbox(runtime="auto")

        assert sandbox.runtime == "podman"

    def test_init_auto_detects_docker_fallback(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        def mock_which(name: str) -> str | None:
            if name == "docker":
                return "/usr/bin/docker"
            return None

        with patch("shutil.which", side_effect=mock_which):
            sandbox = ContainerSandbox(runtime="auto")

        assert sandbox.runtime == "docker"

    def test_init_raises_when_runtime_not_found(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import (
            ContainerRuntimeError,
            ContainerSandbox,
        )

        with (
            patch("shutil.which", return_value=None),
            pytest.raises(ContainerRuntimeError, match="not found"),
        ):
            ContainerSandbox(runtime="nonexistent-runtime")

    def test_init_raises_when_no_runtime_available(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import (
            ContainerRuntimeError,
            ContainerSandbox,
        )

        with (
            patch("shutil.which", return_value=None),
            pytest.raises(ContainerRuntimeError, match="No container runtime"),
        ):
            ContainerSandbox(runtime="auto")


class TestContainerSandboxBuildCommand:
    """Tests for ContainerSandbox._build_command."""

    def _make_sandbox(self) -> Any:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            return ContainerSandbox(runtime="docker")

    def test_basic_command(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("python:3.13-slim", ["python", "-c", "print(1)"])

        assert cmd[0] == "docker"
        assert "run" in cmd
        assert "--rm" in cmd
        assert "python:3.13-slim" in cmd
        assert "python" in cmd
        assert "--cap-drop" in cmd
        assert "ALL" in cmd

    def test_network_disabled_by_default(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo", "test"])

        net_idx = cmd.index("--network")
        assert cmd[net_idx + 1] == "none"

    def test_network_enabled(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo", "test"], network=True)

        assert "--network" not in cmd

    def test_read_only_by_default(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo", "test"])

        assert "--read-only" in cmd

    def test_read_only_disabled(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo", "test"], read_only=False)

        assert "--read-only" not in cmd

    def test_env_vars_sorted(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command(
            "img:latest", ["echo"], env={"B_VAR": "2", "A_VAR": "1"}
        )

        e_indices = [i for i, x in enumerate(cmd) if x == "-e"]
        assert len(e_indices) == 2
        assert cmd[e_indices[0] + 1] == "A_VAR=1"
        assert cmd[e_indices[1] + 1] == "B_VAR=2"

    def test_env_var_invalid_key_skipped(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command(
            "img:latest", ["echo"], env={"-flag": "evil", "GOOD": "ok"}
        )

        joined = " ".join(cmd)
        assert "-flag=evil" not in joined
        assert "GOOD=ok" in joined

    def test_stdin_flag_when_input_data(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command(
            "img:latest", ["cat"], input_data="hello"
        )

        assert "-i" in cmd

    def test_no_stdin_flag_without_input_data(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo", "test"])

        # -i appears as part of -i flag for stdin but not in basic commands
        assert "-i" not in cmd

    def test_rejects_invalid_image_name(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerRuntimeError

        sandbox = self._make_sandbox()

        with pytest.raises(ContainerRuntimeError, match="Invalid container image"):
            sandbox._build_command("--privileged", ["sh"])

    def test_memory_limit(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"], memory_limit="512m")

        mem_idx = cmd.index("--memory")
        assert cmd[mem_idx + 1] == "512m"


class TestContainerSandboxExecute:
    """Tests for ContainerSandbox.execute with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_execute_returns_result(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"hello world\n", b"")
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await sandbox.execute("python:3.13", ["echo", "hello"])

        assert result.exit_code == 0
        assert result.stdout == "hello world\n"
        assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_execute_timeout_raises(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import (
            ContainerSandbox,
            ContainerTimeoutError,
        )

        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")

        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = TimeoutError()
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
            pytest.raises(ContainerTimeoutError, match="timed out"),
        ):
            await sandbox.execute("img:latest", ["sleep", "999"], timeout=1)

    @pytest.mark.asyncio
    async def test_execute_runtime_not_found_raises(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import (
            ContainerRuntimeError,
            ContainerSandbox,
        )

        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("docker not found"),
            ),
            pytest.raises(ContainerRuntimeError, match="not found"),
        ):
            await sandbox.execute("img:latest", ["echo"])

    @pytest.mark.asyncio
    async def test_execute_os_error_raises(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import (
            ContainerRuntimeError,
            ContainerSandbox,
        )

        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("permission denied"),
            ),
            pytest.raises(ContainerRuntimeError, match="Failed to start"),
        ):
            await sandbox.execute("img:latest", ["echo"])

    @pytest.mark.asyncio
    async def test_execute_with_input_data(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"echoed input", b"")
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await sandbox.execute(
                "python:3.13", ["cat"], input_data="my input"
            )

        assert result.exit_code == 0
        assert result.stdout == "echoed input"
        # Verify communicate was called with encoded input
        mock_proc.communicate.assert_awaited_once_with(b"my input")


class TestGVisorSandboxInit:
    """Tests for GVisorSandbox.__init__."""

    def test_init_with_explicit_runtime(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        def mock_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=mock_which):
            sandbox = GVisorSandbox(container_runtime="docker")

        assert sandbox.runtime == "docker"

    def test_init_auto_prefers_podman(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        def mock_which(name: str) -> str | None:
            if name in ("podman", "runsc"):
                return f"/usr/bin/{name}"
            return None

        with patch("shutil.which", side_effect=mock_which):
            sandbox = GVisorSandbox(container_runtime="auto")

        assert sandbox.runtime == "podman"

    def test_init_raises_when_no_runtime(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import (
            GVisorRuntimeError,
            GVisorSandbox,
        )

        with (
            patch("shutil.which", return_value=None),
            pytest.raises(GVisorRuntimeError, match="No container runtime"),
        ):
            GVisorSandbox(container_runtime="auto")


class TestGVisorSandboxBuildCommand:
    """Tests for GVisorSandbox._build_command."""

    def _make_sandbox(self) -> Any:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        def mock_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=mock_which):
            return GVisorSandbox(container_runtime="docker")

    def test_includes_runtime_runsc(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("python:3.13", ["python", "-c", "pass"])

        assert "--runtime=runsc" in cmd

    def test_always_read_only(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"])

        assert "--read-only" in cmd

    def test_always_network_none(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"])

        net_idx = cmd.index("--network")
        assert cmd[net_idx + 1] == "none"

    def test_rejects_invalid_image(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorRuntimeError

        sandbox = self._make_sandbox()

        with pytest.raises(GVisorRuntimeError, match="Invalid container image"):
            sandbox._build_command("--rm-all", ["sh"])

    def test_env_var_invalid_key_skipped(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command(
            "img:latest", ["echo"], env={"-bad": "val", "GOOD": "ok"}
        )

        joined = " ".join(cmd)
        assert "-bad=val" not in joined
        assert "GOOD=ok" in joined


class TestGVisorSandboxExecute:
    """Tests for GVisorSandbox.execute with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_execute_returns_result(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        def mock_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=mock_which):
            sandbox = GVisorSandbox(container_runtime="docker")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"gvisor output\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("python:3.13", ["echo", "test"])

        assert result.exit_code == 0
        assert result.stdout == "gvisor output\n"

    @pytest.mark.asyncio
    async def test_execute_timeout_raises(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import (
            GVisorSandbox,
            GVisorTimeoutError,
        )

        def mock_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=mock_which):
            sandbox = GVisorSandbox(container_runtime="docker")

        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = TimeoutError()
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
            pytest.raises(GVisorTimeoutError, match="timed out"),
        ):
            await sandbox.execute("img:latest", ["sleep", "999"], timeout=1)

    @pytest.mark.asyncio
    async def test_execute_runtime_not_found(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import (
            GVisorRuntimeError,
            GVisorSandbox,
        )

        def mock_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=mock_which):
            sandbox = GVisorSandbox(container_runtime="docker")

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("docker"),
            ),
            pytest.raises(GVisorRuntimeError, match="not found"),
        ):
            await sandbox.execute("img:latest", ["echo"])


# ---------------------------------------------------------------------------
# 7b. BaseSandbox (base.py) — _build_command and _execute_subprocess
# ---------------------------------------------------------------------------


class TestBaseSandboxBuildCommand:
    """Tests for BaseSandbox._build_command via a concrete subclass."""

    def _make_sandbox(self) -> Any:
        from blackbeard.engine.sandbox.base import BaseSandbox

        class ConcreteSandbox(BaseSandbox):
            _default_memory = "128m"
            _default_timeout = 15
            _error_prefix = "Test"

            def _extra_flags(self) -> list[str]:
                return ["--custom-flag"]

            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                return await self._execute_subprocess(*args, **kwargs)

        with patch("shutil.which", return_value="/usr/bin/podman"):
            return ConcreteSandbox(container_runtime="podman")

    def test_build_command_with_defaults(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo", "hi"])

        assert cmd[0] == "podman"
        assert "run" in cmd
        assert "--rm" in cmd
        assert "--custom-flag" in cmd
        assert "--memory" in cmd
        mem_idx = cmd.index("--memory")
        assert cmd[mem_idx + 1] == "128m"  # _default_memory

    def test_build_command_with_env(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command(
            "img:latest", ["echo"], env={"MY_VAR": "hello"}
        )

        assert "-e" in cmd
        e_idx = cmd.index("-e")
        assert cmd[e_idx + 1] == "MY_VAR=hello"

    def test_build_command_network_disabled(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"])

        net_idx = cmd.index("--network")
        assert cmd[net_idx + 1] == "none"

    def test_build_command_network_enabled(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"], network=True)

        assert "--network" not in cmd

    def test_build_command_read_only_default(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"])

        assert "--read-only" in cmd

    def test_build_command_read_only_disabled(self) -> None:
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img:latest", ["echo"], read_only=False)

        assert "--read-only" not in cmd


class TestBaseSandboxExecuteSubprocess:
    """Tests for BaseSandbox._execute_subprocess via a concrete subclass."""

    def _make_sandbox(self) -> Any:
        from blackbeard.engine.sandbox.base import BaseSandbox

        class ConcreteSandbox(BaseSandbox):
            _default_memory = "128m"
            _default_timeout = 10
            _error_prefix = "Test"

            def _extra_flags(self) -> list[str]:
                return []

            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                return await self._execute_subprocess(*args, **kwargs)

        with patch("shutil.which", return_value="/usr/bin/docker"):
            return ConcreteSandbox(container_runtime="docker")

    @pytest.mark.asyncio
    async def test_execute_subprocess_returns_result(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxResult

        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"output", b"error")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("img:latest", ["cmd"])

        assert isinstance(result, SandboxResult)
        assert result.exit_code == 1
        assert result.stdout == "output"
        assert result.stderr == "error"

    @pytest.mark.asyncio
    async def test_execute_subprocess_timeout(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxTimeoutError

        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
            pytest.raises(SandboxTimeoutError, match="timed out"),
        ):
            await sandbox.execute("img:latest", ["sleep", "999"], timeout=1)

    @pytest.mark.asyncio
    async def test_execute_subprocess_file_not_found(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxRuntimeError

        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("not found"),
            ),
            pytest.raises(SandboxRuntimeError, match="not found"),
        ):
            await sandbox.execute("img:latest", ["echo"])

    @pytest.mark.asyncio
    async def test_execute_subprocess_os_error(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxRuntimeError

        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("permission denied"),
            ),
            pytest.raises(SandboxRuntimeError, match="Failed to start"),
        ):
            await sandbox.execute("img:latest", ["echo"])


# ---------------------------------------------------------------------------
# 8. WasmSandbox.invoke
# ---------------------------------------------------------------------------


class TestWasmSandboxInvoke:
    """Tests for WasmSandbox.invoke — additional coverage for untested paths."""

    def test_invoke_returns_result_with_json_output(self) -> None:
        sandbox = self._make_sandbox()

        mock_store = MagicMock()
        mock_store.get_fuel.return_value = 90_000_000
        mock_exports = MagicMock()
        mock_run = MagicMock(return_value=json.dumps({"output": "hello", "success": True}))
        mock_exports.get.return_value = mock_run
        mock_instance = MagicMock()
        mock_instance.exports.return_value = mock_exports

        with patch.object(sandbox, "_instantiate", return_value=(mock_store, mock_instance)):
            result = sandbox.invoke("/app/tools/test.wasm", {"key": "value"})

        assert result.success is True
        assert result.output == "hello"

    def _make_sandbox(self) -> Any:
        """Create a WasmSandbox with mocked internals."""
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        sandbox = WasmSandbox.__new__(WasmSandbox)
        sandbox._fuel_limit = 100_000_000
        sandbox._cache = MagicMock()
        sandbox._allowed_capabilities = set()
        sandbox._engine = MagicMock()
        return sandbox

    def test_invoke_handles_fuel_exhaustion(self) -> None:
        import wasmtime

        from blackbeard.engine.sandbox.wasm_runtime import WasmTimeoutError

        sandbox = self._make_sandbox()

        mock_store = MagicMock()
        mock_exports = MagicMock()
        mock_run = MagicMock(side_effect=wasmtime.WasmtimeError("all fuel consumed"))
        mock_exports.get.return_value = mock_run
        mock_instance = MagicMock()
        mock_instance.exports.return_value = mock_exports

        with patch.object(sandbox, "_instantiate", return_value=(mock_store, mock_instance)):
            with pytest.raises(WasmTimeoutError, match="fuel limit"):
                sandbox.invoke("/app/tools/test.wasm", "input")

    def test_invoke_handles_missing_run_export(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmExecutionError

        sandbox = self._make_sandbox()

        mock_store = MagicMock()
        mock_exports = MagicMock()
        mock_exports.get.return_value = None  # no "run" export
        mock_instance = MagicMock()
        mock_instance.exports.return_value = mock_exports

        with patch.object(sandbox, "_instantiate", return_value=(mock_store, mock_instance)):
            with pytest.raises(WasmExecutionError, match="does not export"):
                sandbox.invoke("/app/tools/test.wasm", "input")

    def test_invoke_handles_non_string_result(self) -> None:
        sandbox = self._make_sandbox()

        mock_store = MagicMock()
        mock_store.get_fuel.return_value = 95_000_000
        mock_exports = MagicMock()
        mock_run = MagicMock(return_value=42)  # non-string result
        mock_exports.get.return_value = mock_run
        mock_instance = MagicMock()
        mock_instance.exports.return_value = mock_exports

        with patch.object(sandbox, "_instantiate", return_value=(mock_store, mock_instance)):
            result = sandbox.invoke("/app/tools/test.wasm", {"data": "test"})

        assert result.success is True
        assert result.output == "42"

    def test_invoke_with_dict_input_serializes(self) -> None:
        sandbox = self._make_sandbox()

        mock_store = MagicMock()
        mock_store.get_fuel.return_value = 99_000_000
        mock_exports = MagicMock()
        mock_run = MagicMock(return_value="plain text output")
        mock_exports.get.return_value = mock_run
        mock_instance = MagicMock()
        mock_instance.exports.return_value = mock_exports

        with patch.object(sandbox, "_instantiate", return_value=(mock_store, mock_instance)):
            result = sandbox.invoke("/app/tools/test.wasm", {"key": "value"})

        # Verify input was serialized as JSON
        call_args = mock_run.call_args[0]
        assert call_args[1] == '{"key": "value"}'
        assert result.success is True
        assert result.output == "plain text output"


# ---------------------------------------------------------------------------
# 9. auth.py — register endpoint
# ---------------------------------------------------------------------------


class TestRegisterEndpoint:
    """Tests for the register endpoint via the test client."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: Any) -> None:
        with patch(
            "blackbeard.api.auth._register_litellm_user",
            new_callable=AsyncMock,
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "strongpass1",
                    "display_name": "New User",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "new@example.com"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client: Any) -> None:
        with patch(
            "blackbeard.api.auth._register_litellm_user",
            new_callable=AsyncMock,
        ):
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "dupe@example.com",
                    "password": "strongpass1",
                    "display_name": "First User",
                },
            )

            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "dupe@example.com",
                    "password": "strongpass2",
                    "display_name": "Second User",
                },
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_weak_password_rejected(self, client: Any) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com",
                "password": "short",
                "display_name": "Weak User",
            },
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10. auth.py — generate_api_key / revoke_api_key
# ---------------------------------------------------------------------------


class TestApiKeyManagement:
    """Tests for generate_api_key and revoke_api_key endpoints."""

    @pytest.mark.asyncio
    async def test_generate_api_key_returns_key(self, client: Any) -> None:
        with patch(
            "blackbeard.api.auth._register_litellm_user",
            new_callable=AsyncMock,
        ):
            reg_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "apikey@example.com",
                    "password": "strongpass1",
                    "display_name": "API Key User",
                },
            )

        token = reg_resp.json()["access_token"]

        resp = await client.post(
            "/api/v1/auth/api-key",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert data["api_key"].startswith("bb-")

    @pytest.mark.asyncio
    async def test_generate_api_key_requires_jwt(self, client: Any) -> None:
        resp = await client.post("/api/v1/auth/api-key")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_api_key_returns_204(self, client: Any) -> None:
        with patch(
            "blackbeard.api.auth._register_litellm_user",
            new_callable=AsyncMock,
        ):
            reg_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "revoke@example.com",
                    "password": "strongpass1",
                    "display_name": "Revoke User",
                },
            )

        token = reg_resp.json()["access_token"]

        # Generate first
        await client.post(
            "/api/v1/auth/api-key",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Then revoke
        resp = await client.delete(
            "/api/v1/auth/api-key",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_api_key_idempotent(self, client: Any) -> None:
        with patch(
            "blackbeard.api.auth._register_litellm_user",
            new_callable=AsyncMock,
        ):
            reg_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "idem@example.com",
                    "password": "strongpass1",
                    "display_name": "Idempotent User",
                },
            )

        token = reg_resp.json()["access_token"]

        # Revoke without generating — should still return 204
        resp = await client.delete(
            "/api/v1/auth/api-key",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_api_key_requires_jwt(self, client: Any) -> None:
        resp = await client.delete("/api/v1/auth/api-key")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 11. ValkeyCollabBackend._listen
# ---------------------------------------------------------------------------


class TestValkeyCollabBackendListen:
    """Tests for ValkeyCollabBackend._listen."""

    def _make_backend_and_pubsub(self, messages: list[dict[str, Any]]) -> tuple[Any, Any]:
        """Create a ValkeyCollabBackend with a mocked pubsub that yields messages."""
        from blackbeard.api.collaboration import ValkeyCollabBackend

        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()

        async def mock_listen():
            for msg in messages:
                yield msg
            raise asyncio.CancelledError()

        mock_pubsub.listen = mock_listen

        # redis.pubsub() is a sync call, so use MagicMock (not AsyncMock)
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub

        backend = ValkeyCollabBackend.__new__(ValkeyCollabBackend)
        backend._redis = mock_redis
        backend._subscriptions = {}
        backend._subscriber_lock = asyncio.Lock()

        return backend, mock_pubsub

    @pytest.mark.asyncio
    async def test_listen_receives_and_broadcasts(self) -> None:
        messages = [
            {"type": "message", "data": json.dumps({"type": "node_add", "data": {}})},
        ]
        backend, mock_pubsub = self._make_backend_and_pubsub(messages)

        with patch(
            "blackbeard.api.collaboration._broadcast_local",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await backend._listen("test-room")

        mock_pubsub.subscribe.assert_awaited_once_with("collab:test-room")
        mock_broadcast.assert_awaited_once()
        call_args = mock_broadcast.call_args
        assert call_args[0][0] == "test-room"
        # sender=None passed as keyword arg for cross-replica messages
        assert call_args.kwargs["sender"] is None

    @pytest.mark.asyncio
    async def test_listen_skips_non_message_types(self) -> None:
        messages = [
            {"type": "subscribe", "data": None},
            {"type": "message", "data": json.dumps({"type": "node_move", "data": {}})},
        ]
        backend, _ = self._make_backend_and_pubsub(messages)

        with patch(
            "blackbeard.api.collaboration._broadcast_local",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await backend._listen("room")

        # Only the "message" type should trigger broadcast
        assert mock_broadcast.await_count == 1

    @pytest.mark.asyncio
    async def test_listen_retries_on_subscribe_failure(self) -> None:
        """When subscribe() fails, retries accumulate (retries not reset)."""
        from blackbeard.api.collaboration import ValkeyCollabBackend

        call_count = 0

        def make_pubsub() -> Any:
            nonlocal call_count
            call_count += 1
            mock_pubsub = MagicMock()

            if call_count <= 2:
                # First two attempts fail at subscribe
                mock_pubsub.subscribe = AsyncMock(
                    side_effect=ConnectionError("connection lost")
                )
            else:
                # Third attempt succeeds then cancels on listen
                mock_pubsub.subscribe = AsyncMock()

                async def success_listen():
                    yield {"type": "message", "data": json.dumps({"type": "node_add", "data": {}})}
                    raise asyncio.CancelledError()

                mock_pubsub.listen = success_listen

            return mock_pubsub

        mock_redis = MagicMock()
        mock_redis.pubsub = make_pubsub

        backend = ValkeyCollabBackend.__new__(ValkeyCollabBackend)
        backend._redis = mock_redis
        backend._subscriptions = {}
        backend._subscriber_lock = asyncio.Lock()

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch(
                "blackbeard.api.collaboration._broadcast_local",
                new_callable=AsyncMock,
            ),
        ):
            await backend._listen("retry-room")

        # Should have retried twice (retries 1 and 2) before succeeding on 3rd
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_listen_gives_up_after_max_retries(self) -> None:
        """When subscribe() keeps failing, gives up after _MAX_LISTEN_RETRIES."""
        from blackbeard.api.collaboration import ValkeyCollabBackend

        def make_failing_pubsub() -> Any:
            mock_pubsub = MagicMock()
            # Fail at subscribe so retries accumulate (not reset)
            mock_pubsub.subscribe = AsyncMock(
                side_effect=ConnectionError("connection lost")
            )
            return mock_pubsub

        mock_redis = MagicMock()
        mock_redis.pubsub = make_failing_pubsub

        backend = ValkeyCollabBackend.__new__(ValkeyCollabBackend)
        backend._redis = mock_redis
        backend._subscriptions = {}
        backend._subscriber_lock = asyncio.Lock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await backend._listen("fail-room")

        # Should have given up (not in subscriptions)
        assert "fail-room" not in backend._subscriptions

    @pytest.mark.asyncio
    async def test_listen_handles_malformed_json(self) -> None:
        messages = [
            {"type": "message", "data": "not-valid-json{{{"},
            {"type": "message", "data": json.dumps({"type": "node_add", "data": {}})},
        ]
        backend, _ = self._make_backend_and_pubsub(messages)

        with patch(
            "blackbeard.api.collaboration._broadcast_local",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await backend._listen("json-room")

        # Malformed JSON is skipped, valid message is broadcast
        assert mock_broadcast.await_count == 1


# ---------------------------------------------------------------------------
# 12. validate_ws_auth
# ---------------------------------------------------------------------------


class TestValidateWsAuth:
    """Tests for collaboration.validate_ws_auth."""

    def test_valid_jwt_returns_true(self) -> None:
        from blackbeard.api.collaboration import validate_ws_auth

        with patch(
            "blackbeard.api.collaboration.decode_access_token",
            return_value={"sub": "user-1", "type": "access"},
        ):
            assert validate_ws_auth("valid-jwt-token", "") is True

    def test_expired_jwt_falls_through(self) -> None:
        import jwt as pyjwt

        from blackbeard.api.collaboration import validate_ws_auth

        with (
            patch(
                "blackbeard.api.collaboration.decode_access_token",
                side_effect=pyjwt.ExpiredSignatureError("expired"),
            ),
            patch(
                "blackbeard.api.collaboration.get_api_key",
                return_value="system-key",
            ),
        ):
            # Token invalid, API key also doesn't match
            result = validate_ws_auth("expired-token", "wrong-key")

        assert result is False

    def test_valid_api_key_returns_true(self) -> None:
        from blackbeard.api.collaboration import validate_ws_auth

        with patch(
            "blackbeard.api.collaboration.get_api_key",
            return_value="correct-api-key",
        ):
            assert validate_ws_auth("", "correct-api-key") is True

    def test_invalid_api_key_returns_false(self) -> None:
        from blackbeard.api.collaboration import validate_ws_auth

        with patch(
            "blackbeard.api.collaboration.get_api_key",
            return_value="correct-api-key",
        ):
            assert validate_ws_auth("", "wrong-key") is False

    def test_empty_both_returns_false(self) -> None:
        from blackbeard.api.collaboration import validate_ws_auth

        with patch(
            "blackbeard.api.collaboration.get_api_key",
            return_value="system-key",
        ):
            assert validate_ws_auth("", "") is False

    def test_invalid_jwt_falls_back_to_api_key(self) -> None:
        import jwt as pyjwt

        from blackbeard.api.collaboration import validate_ws_auth

        with (
            patch(
                "blackbeard.api.collaboration.decode_access_token",
                side_effect=pyjwt.InvalidTokenError("bad token"),
            ),
            patch(
                "blackbeard.api.collaboration.get_api_key",
                return_value="valid-system-key",
            ),
        ):
            assert validate_ws_auth("bad-jwt", "valid-system-key") is True


# ---------------------------------------------------------------------------
# 13. instrument_engine
# ---------------------------------------------------------------------------


class TestInstrumentEngine:
    """Tests for models.database.instrument_engine."""

    def _capture_listeners(self) -> tuple[Any, dict[str, Any]]:
        """Patch event.listens_for to capture registered listeners."""
        listeners: dict[str, Any] = {}

        def mock_listens_for(target: Any, event_name: str) -> Any:
            def decorator(fn: Any) -> Any:
                listeners[event_name] = fn
                return fn
            return decorator

        mock_engine = MagicMock()
        return mock_engine, listeners, mock_listens_for  # type: ignore[return-value]

    def test_does_not_crash(self) -> None:
        from blackbeard.models.database import instrument_engine

        mock_engine = MagicMock()

        def mock_listens_for(target: Any, event_name: str) -> Any:
            def decorator(fn: Any) -> Any:
                return fn
            return decorator

        with patch("blackbeard.models.database.event.listens_for", side_effect=mock_listens_for):
            instrument_engine(mock_engine, label="test")

    def test_registers_event_listeners(self) -> None:
        from blackbeard.models.database import instrument_engine

        mock_engine = MagicMock()

        with patch("blackbeard.models.database.event") as mock_event:
            instrument_engine(mock_engine, label="test-engine")

        # Should register before_cursor_execute, after_cursor_execute,
        # checkout, and checkin listeners
        calls = mock_event.listens_for.call_args_list
        event_names = [c[0][1] for c in calls]
        assert "before_cursor_execute" in event_names
        assert "after_cursor_execute" in event_names
        assert "checkout" in event_names
        assert "checkin" in event_names

    def test_slow_query_listener_fires(self) -> None:
        from blackbeard.models.database import instrument_engine

        mock_engine = MagicMock()
        listeners: dict[str, Any] = {}

        def mock_listens_for(target: Any, event_name: str) -> Any:
            def decorator(fn: Any) -> Any:
                listeners[event_name] = fn
                return fn
            return decorator

        with patch("blackbeard.models.database.event.listens_for", side_effect=mock_listens_for):
            instrument_engine(mock_engine, label="slow-test")

        # Simulate a slow query
        mock_conn = MagicMock()
        mock_conn.info = {}

        # Set start time
        listeners["before_cursor_execute"](mock_conn, None, None, None, None, None)
        assert "query_start_time" in mock_conn.info

        # Backdate the start time to simulate slow query
        mock_conn.info["query_start_time"] = time.monotonic() - 2.0

        with patch("blackbeard.models.database.logger") as mock_logger:
            listeners["after_cursor_execute"](
                mock_conn, None, "SELECT * FROM users", None, None, None
            )

        mock_logger.warning.assert_called_once()
        assert "Slow query" in str(mock_logger.warning.call_args)

    def test_pool_exhaustion_listener(self) -> None:
        from blackbeard.models.database import instrument_engine

        mock_engine = MagicMock()
        listeners: dict[str, Any] = {}

        def mock_listens_for(target: Any, event_name: str) -> Any:
            def decorator(fn: Any) -> Any:
                listeners[event_name] = fn
                return fn
            return decorator

        with patch("blackbeard.models.database.event.listens_for", side_effect=mock_listens_for):
            instrument_engine(mock_engine, label="pool-test")

        # Simulate pool exhaustion
        mock_pool = MagicMock()
        mock_pool.checkedout.return_value = 10
        mock_pool.size.return_value = 5
        mock_pool.overflow.return_value = 5
        mock_engine.pool = mock_pool

        mock_conn_rec = MagicMock()
        mock_conn_rec.info = {}

        with patch("blackbeard.models.database.logger") as mock_logger:
            listeners["checkout"](None, mock_conn_rec, None)

        mock_logger.error.assert_called_once()
        assert "pool exhausted" in str(mock_logger.error.call_args).lower()

    def test_long_checkout_listener(self) -> None:
        from blackbeard.models.database import instrument_engine

        mock_engine = MagicMock()
        listeners: dict[str, Any] = {}

        def mock_listens_for(target: Any, event_name: str) -> Any:
            def decorator(fn: Any) -> Any:
                listeners[event_name] = fn
                return fn
            return decorator

        with patch("blackbeard.models.database.event.listens_for", side_effect=mock_listens_for):
            instrument_engine(mock_engine, label="checkin-test")

        # Simulate long-held connection
        mock_conn_rec = MagicMock()
        mock_conn_rec.info = {"_bb_checkout_time": time.monotonic() - 10.0}

        with patch("blackbeard.models.database.logger") as mock_logger:
            listeners["checkin"](None, mock_conn_rec)

        mock_logger.warning.assert_called_once()
        assert "held for" in str(mock_logger.warning.call_args).lower()


# ---------------------------------------------------------------------------
# SandboxResult / ContainerResult / GVisorResult to_dict
# ---------------------------------------------------------------------------


class TestSandboxResultToDict:
    """Tests for result dataclass serialization."""

    def test_sandbox_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxResult

        result = SandboxResult(exit_code=0, stdout="out", stderr="err")
        d = result.to_dict()
        assert d == {"exit_code": 0, "stdout": "out", "stderr": "err"}

    def test_container_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerResult

        result = ContainerResult(exit_code=1, stdout="output", stderr="error")
        d = result.to_dict()
        assert d == {"exit_code": 1, "stdout": "output", "stderr": "error"}

    def test_gvisor_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorResult

        result = GVisorResult(exit_code=137, stdout="", stderr="killed")
        d = result.to_dict()
        assert d == {"exit_code": 137, "stdout": "", "stderr": "killed"}


# ---------------------------------------------------------------------------
# WasmToolResult to_dict
# ---------------------------------------------------------------------------


class TestWasmToolResultToDict:
    """Tests for WasmToolResult serialization."""

    def test_to_dict_success(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmToolResult

        result = WasmToolResult(
            output="hello", success=True, error=None, duration_ms=50
        )
        d = result.to_dict()
        assert d == {
            "output": "hello",
            "success": True,
            "error": None,
            "duration_ms": 50,
        }

    def test_to_dict_failure(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmToolResult

        result = WasmToolResult(
            output="", success=False, error="fuel exhausted", duration_ms=100
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "fuel exhausted"


# ---------------------------------------------------------------------------
# ModuleCache
# ---------------------------------------------------------------------------


class TestModuleCache:
    """Tests for WasmSandbox ModuleCache."""

    def test_get_returns_none_for_missing(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import ModuleCache

        cache = ModuleCache(max_size=5)
        assert cache.get("missing") is None

    def test_put_and_get(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import ModuleCache

        cache = ModuleCache(max_size=5)
        mock_module = MagicMock()
        cache.put("key1", mock_module)

        assert cache.get("key1") is mock_module

    def test_eviction_on_overflow(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import ModuleCache

        cache = ModuleCache(max_size=2)
        m1, m2, m3 = MagicMock(), MagicMock(), MagicMock()
        cache.put("k1", m1)
        cache.put("k2", m2)
        cache.put("k3", m3)  # should evict k1

        assert cache.get("k1") is None
        assert cache.get("k2") is m2
        assert cache.get("k3") is m3

    def test_clear(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import ModuleCache

        cache = ModuleCache(max_size=5)
        cache.put("k1", MagicMock())
        cache.put("k2", MagicMock())

        cache.clear()
        assert cache.size == 0

    def test_size_property(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import ModuleCache

        cache = ModuleCache(max_size=10)
        assert cache.size == 0
        cache.put("k1", MagicMock())
        assert cache.size == 1

    def test_put_updates_existing(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import ModuleCache

        cache = ModuleCache(max_size=5)
        m1, m2 = MagicMock(), MagicMock()
        cache.put("k1", m1)
        cache.put("k1", m2)

        assert cache.get("k1") is m2
        assert cache.size == 1
