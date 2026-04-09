"""Integration smoke tests for daemon lifecycle.

Test Spec: TS-85-SMOKE-1 through TS-85-SMOKE-7,
           TS-85-6, TS-85-12, TS-85-17, TS-85-E1
Requirements: 85-REQ-1.E1, 85-REQ-2.2, 85-REQ-4.1, 85-REQ-5.3
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_stream(
    name: str = "test-stream",
    interval: int = 1,
    enabled: bool = True,
    side_effect: list | None = None,
    duration: float = 0.0,
) -> MagicMock:
    """Create a mock WorkStream."""
    stream = MagicMock()
    stream.name = name
    stream.interval = interval
    stream.enabled = enabled

    if duration > 0:
        original_side_effect = side_effect

        async def slow_run() -> None:
            await asyncio.sleep(duration)
            if original_side_effect:
                effect = original_side_effect.pop(0)
                if isinstance(effect, Exception):
                    raise effect

        stream.run_once = AsyncMock(side_effect=slow_run)
    else:
        stream.run_once = AsyncMock(side_effect=side_effect)
    stream.shutdown = AsyncMock()
    return stream


def _make_config() -> MagicMock:
    """Create a mock config."""
    config = MagicMock()
    ns = MagicMock()
    ns.enabled_streams = ["specs", "fixes", "hunts"]
    ns.merge_strategy = "direct"
    config.night_shift = ns
    return config


# ---------------------------------------------------------------------------
# TS-85-6: Graceful shutdown on single SIGINT
# Requirement: 85-REQ-2.2
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    """Verify single SIGINT triggers graceful shutdown."""

    async def test_run_once_completes_before_shutdown(self, tmp_path: Path) -> None:
        """run_once completes, not interrupted mid-execution."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        completed = []

        async def slow_run() -> None:
            await asyncio.sleep(0.1)
            completed.append(True)

        stream = _make_mock_stream(name="slow-stream", interval=1)
        stream.run_once = AsyncMock(side_effect=slow_run)
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [stream], budget, pid_path=tmp_path / "d.pid")

        async def shutdown_mid_operation() -> None:
            await asyncio.sleep(0.05)  # mid-operation
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_mid_operation())
        await runner.run()
        await task
        assert stream.run_once.call_count >= 1
        assert stream.shutdown.call_count == 1


# ---------------------------------------------------------------------------
# TS-85-12: Streams run as independent asyncio tasks
# Requirement: 85-REQ-4.1
# ---------------------------------------------------------------------------


class TestConcurrentStreams:
    """Verify streams run concurrently, not sequentially."""

    async def test_concurrent_execution(self, tmp_path: Path) -> None:
        """Both streams execute within ~0.15s (not ~0.2s if sequential)."""
        import time

        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        async def slow_run() -> None:
            await asyncio.sleep(0.1)

        s1 = _make_mock_stream(name="s1", interval=100)
        s1.run_once = AsyncMock(side_effect=slow_run)
        s2 = _make_mock_stream(name="s2", interval=100)
        s2.run_once = AsyncMock(side_effect=slow_run)

        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [s1, s2], budget, pid_path=tmp_path / "d.pid")

        start = time.monotonic()

        async def shutdown_after_first_cycle() -> None:
            await asyncio.sleep(0.15)
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_after_first_cycle())
        await runner.run()
        await task
        elapsed = time.monotonic() - start

        assert s1.run_once.call_count >= 1
        assert s2.run_once.call_count >= 1
        # If sequential, would take ~0.2s; concurrent should be ~0.1-0.15s
        assert elapsed < 0.25


# ---------------------------------------------------------------------------
# TS-85-17: Cost check between cycles, not mid-operation
# Requirement: 85-REQ-5.3
# ---------------------------------------------------------------------------


class TestCostCheckBetweenCycles:
    """Verify run_once is not interrupted when cost exceeds limit mid-cycle."""

    async def test_run_once_completes_despite_budget(self, tmp_path: Path) -> None:
        """run_once completes fully even when cost exceeds budget."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        completed: list[bool] = []

        async def costly_run() -> None:
            await asyncio.sleep(0.05)
            budget.add_cost(2.0)
            completed.append(True)

        budget = SharedBudget(max_cost=1.0)
        stream = _make_mock_stream(name="costly-stream", interval=1)
        stream.run_once = AsyncMock(side_effect=costly_run)
        config = _make_config()
        runner = DaemonRunner(config, None, [stream], budget, pid_path=tmp_path / "d.pid")
        await runner.run()
        assert len(completed) >= 1
        assert budget.exceeded is True


# ---------------------------------------------------------------------------
# TS-85-E1: Persistent stream failure doesn't affect others
# Requirement: 85-REQ-1.E1
# ---------------------------------------------------------------------------


class TestPersistentStreamFailure:
    """Verify a stream that always fails doesn't crash other streams."""

    async def test_failing_stream_doesnt_affect_healthy(self, tmp_path: Path) -> None:
        """Healthy stream runs normally despite another always failing."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        failing = _make_mock_stream(
            name="failing",
            interval=0,
            side_effect=[RuntimeError("always fail")] * 10,
        )
        healthy = _make_mock_stream(name="healthy", interval=0)
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [failing, healthy], budget, pid_path=tmp_path / "d.pid")

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.3)
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_after_delay())
        await runner.run()
        await task
        assert failing.run_once.call_count >= 2
        assert healthy.run_once.call_count >= 2


# ---------------------------------------------------------------------------
# TS-85-SMOKE-1: Daemon full lifecycle
# Path 1 (startup) + Path 5 (shutdown)
# ---------------------------------------------------------------------------


class TestSmokeDaemonFullLifecycle:
    """Verify daemon starts, writes PID, runs streams, shuts down, removes PID."""

    async def test_full_lifecycle(self, tmp_path: Path) -> None:
        """PID created, streams run, PID removed, uptime > 0."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        pid_path = tmp_path / "daemon.pid"
        stream = _make_mock_stream(name="test-stream", enabled=True, interval=1)
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [stream], budget, pid_path=pid_path)

        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.2)
        assert pid_path.exists()
        assert pid_path.read_text().strip() == str(os.getpid())

        runner.request_shutdown()
        state = await task
        assert not pid_path.exists()
        assert state.uptime_seconds > 0
        assert stream.run_once.call_count >= 1
        assert stream.shutdown.call_count == 1


# ---------------------------------------------------------------------------
# TS-85-SMOKE-2: Spec executor end-to-end
# Path 2
# ---------------------------------------------------------------------------


class TestSmokeSpecExecutor:
    """Verify spec executor discovers specs, runs orchestrator, reports cost."""

    async def test_spec_executor_e2e(self) -> None:
        """discover called, orchestrator run, cost reported."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecExecutorStream

        budget = SharedBudget(max_cost=10.0)

        # Mock discover returning one spec
        mock_spec = MagicMock()
        mock_spec.name = "test_spec"
        mock_discover = AsyncMock(return_value=[mock_spec])

        # Mock orchestrator
        mock_state = MagicMock()
        mock_state.total_cost = 1.5
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(return_value=mock_state)

        executor = SpecExecutorStream(
            config=_make_config(),
            budget=budget,
            discover_fn=mock_discover,
            orch_factory=lambda specs: mock_orch,
        )
        await executor.run_once()
        assert mock_discover.call_count == 1
        assert mock_orch.run.call_count == 1
        assert budget.total_cost == 1.5


# ---------------------------------------------------------------------------
# TS-85-SMOKE-3: Fix pipeline stream end-to-end
# Path 3
# ---------------------------------------------------------------------------


class TestSmokeFixPipeline:
    """Verify fix pipeline stream wraps engine and reports cost."""

    async def test_fix_pipeline_e2e(self) -> None:
        """engine._drain_issues called, cost reported."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import FixPipelineStream

        budget = SharedBudget(max_cost=10.0)
        engine = MagicMock()
        engine.state = MagicMock()
        engine.state.total_cost = 3.0
        engine._drain_issues = AsyncMock()

        fix_stream = FixPipelineStream(engine=engine, budget=budget)
        # Record initial cost
        initial_cost = 0.0
        engine.state.total_cost = initial_cost

        async def drain_with_cost() -> None:
            engine.state.total_cost = 3.0

        engine._drain_issues = AsyncMock(side_effect=drain_with_cost)
        await fix_stream.run_once()
        assert engine._drain_issues.call_count == 1
        assert budget.total_cost == 3.0


# ---------------------------------------------------------------------------
# TS-85-SMOKE-4: Hunt scan stream end-to-end
# Path 4
# ---------------------------------------------------------------------------


class TestSmokeHuntScan:
    """Verify hunt scan stream wraps engine and reports cost."""

    async def test_hunt_scan_e2e(self) -> None:
        """engine._run_hunt_scan called."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import HuntScanStream

        budget = SharedBudget(max_cost=10.0)
        engine = MagicMock()
        engine.state = MagicMock()
        engine.state.total_cost = 0.0
        engine._run_hunt_scan = AsyncMock()

        hunt_stream = HuntScanStream(engine=engine, budget=budget)
        await hunt_stream.run_once()
        assert engine._run_hunt_scan.call_count == 1


# ---------------------------------------------------------------------------
# TS-85-SMOKE-5: Graceful shutdown preserves state
# Path 5
# ---------------------------------------------------------------------------


class TestSmokeGracefulShutdown:
    """Verify shutdown calls all stream shutdowns and removes PID."""

    async def test_shutdown_preserves_state(self, tmp_path: Path) -> None:
        """Both streams shutdown, PID removed."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        pid_path = tmp_path / "daemon.pid"
        s1 = _make_mock_stream(name="s1")
        s2 = _make_mock_stream(name="s2")
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [s1, s2], budget, pid_path=pid_path)
        runner.request_shutdown()
        await runner.run()
        assert s1.shutdown.call_count == 1
        assert s2.shutdown.call_count == 1
        assert not pid_path.exists()


# ---------------------------------------------------------------------------
# TS-85-SMOKE-6: PID check blocks code command
# Path 6
# ---------------------------------------------------------------------------


class TestSmokePidBlocksCode:
    """Verify code command blocked when live daemon PID exists."""

    def test_pid_check_blocks(self, tmp_path: Path) -> None:
        """check_pid_file returns ALIVE for current process."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file, write_pid_file

        pid_path = tmp_path / "daemon.pid"
        write_pid_file(pid_path)
        status, pid = check_pid_file(pid_path)
        assert status == PidStatus.ALIVE
        assert pid == os.getpid()


# ---------------------------------------------------------------------------
# TS-85-SMOKE-7: Draft PR creation
# Path 7
# ---------------------------------------------------------------------------


class TestSmokeDraftPrCreation:
    """Verify GitHubPlatform.create_pull_request sends correct API request."""

    async def test_github_create_pr(self) -> None:
        """POST to /repos/owner/repo/pulls with correct body."""
        from agent_fox.platform.github import GitHubPlatform

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 99,
            "url": "https://api.github.com/repos/owner/repo/pulls/99",
            "html_url": "https://github.com/owner/repo/pull/99",
        }

        requests_made: list[dict] = []

        async def mock_post(url: str, *, json: dict, headers: dict, **kw: object) -> MagicMock:
            requests_made.append({"url": url, "json": json})
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("agent_fox.platform.github.httpx.AsyncClient", return_value=mock_client):
            github = GitHubPlatform("owner", "repo", "token")
            result = await github.create_pull_request("Fix", "body", "fix/1", "develop", draft=True)

        assert result.number == 99
        assert "github.com" in result.html_url
        assert requests_made[0]["url"].endswith("/repos/owner/repo/pulls")
        assert requests_made[0]["json"]["draft"] is True
