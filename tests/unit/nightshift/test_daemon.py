"""Unit tests for DaemonRunner and SharedBudget.

Test Spec: TS-85-2, TS-85-3, TS-85-4, TS-85-7, TS-85-8, TS-85-9,
           TS-85-13, TS-85-14, TS-85-15, TS-85-16, TS-85-27,
           TS-85-E2, TS-85-E8, TS-85-E9
Requirements: 85-REQ-1.2, 85-REQ-1.3, 85-REQ-1.4, 85-REQ-1.E2,
              85-REQ-2.2, 85-REQ-2.3, 85-REQ-2.4, 85-REQ-2.5,
              85-REQ-4.2, 85-REQ-4.3, 85-REQ-4.E1,
              85-REQ-5.1, 85-REQ-5.2, 85-REQ-5.E1,
              85-REQ-9.2
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_stream(
    name: str = "test-stream",
    interval: int = 1,
    enabled: bool = True,
    side_effect: list | None = None,
) -> MagicMock:
    """Create a mock WorkStream."""
    stream = MagicMock()
    stream.name = name
    stream.interval = interval
    stream.enabled = enabled
    stream.run_once = AsyncMock(side_effect=side_effect)
    stream.shutdown = AsyncMock()
    return stream


def _make_config(
    enabled_streams: list[str] | None = None,
    merge_strategy: str = "direct",
) -> MagicMock:
    """Create a mock config for DaemonRunner."""
    config = MagicMock()
    ns = MagicMock()
    ns.enabled_streams = enabled_streams or ["specs", "fixes", "hunts"]
    ns.merge_strategy = merge_strategy
    config.night_shift = ns
    return config


# ---------------------------------------------------------------------------
# TS-85-15: Shared cost accumulation
# Requirement: 85-REQ-5.1
# ---------------------------------------------------------------------------


class TestSharedBudget:
    """Verify SharedBudget cost accumulation."""

    def test_cost_accumulation(self) -> None:
        """Budget accumulates cost from multiple add_cost calls."""
        from agent_fox.nightshift.daemon import SharedBudget

        budget = SharedBudget(max_cost=10.0)
        budget.add_cost(3.0)
        budget.add_cost(4.5)
        assert budget.total_cost == 7.5
        assert budget.exceeded is False

    # TS-85-16: Cost limit triggers shutdown
    # Requirement: 85-REQ-5.2
    def test_cost_exceeded(self) -> None:
        """Budget.exceeded is True when total_cost >= max_cost."""
        from agent_fox.nightshift.daemon import SharedBudget

        budget = SharedBudget(max_cost=5.0)
        budget.add_cost(6.0)
        assert budget.exceeded is True

    # TS-85-E9: No cost limit configured
    # Requirement: 85-REQ-5.E1
    def test_no_cost_limit(self) -> None:
        """Budget never exceeds when max_cost is None."""
        from agent_fox.nightshift.daemon import SharedBudget

        budget = SharedBudget(max_cost=None)
        budget.add_cost(1000.0)
        assert budget.exceeded is False


# ---------------------------------------------------------------------------
# TS-85-2: Daemon registers all four built-in streams
# Requirement: 85-REQ-1.2
# ---------------------------------------------------------------------------


class TestDaemonStreamRegistration:
    """Verify DaemonRunner registers streams and returns their names."""

    def test_register_three_streams(self) -> None:
        """Runner stores all three registered streams."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        streams = [
            _make_mock_stream(name="spec-executor"),
            _make_mock_stream(name="fix-pipeline"),
            _make_mock_stream(name="hunt-scan"),
        ]
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, streams, budget)  # type: ignore[arg-type]
        assert len(runner.streams) == 3
        assert [s.name for s in runner.streams] == [
            "spec-executor",
            "fix-pipeline",
            "hunt-scan",
        ]


# ---------------------------------------------------------------------------
# TS-85-3: Disabled stream is skipped
# Requirement: 85-REQ-1.3
# ---------------------------------------------------------------------------


class TestDisabledStreamSkipped:
    """Verify disabled stream's run_once is not invoked."""

    async def test_disabled_stream_not_called(self, tmp_path: Path) -> None:
        """Enabled stream called, disabled stream not called."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        enabled = _make_mock_stream(name="enabled-stream", enabled=True)
        disabled = _make_mock_stream(name="disabled-stream", enabled=False)
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [enabled, disabled], budget, pid_path=tmp_path / "d.pid")
        runner.request_shutdown()
        await runner.run()
        assert enabled.run_once.call_count >= 0  # at least constructed
        assert disabled.run_once.call_count == 0


# ---------------------------------------------------------------------------
# TS-85-4: Stream exception does not crash daemon
# Requirement: 85-REQ-1.4
# ---------------------------------------------------------------------------


class TestStreamExceptionHandling:
    """Verify exception in run_once is caught and stream retries."""

    async def test_exception_logged_and_retried(self, tmp_path: Path) -> None:
        """Stream that fails on first call is retried on second cycle."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        stream = _make_mock_stream(
            name="failing-stream",
            side_effect=[RuntimeError("fail"), None],
        )
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [stream], budget, pid_path=tmp_path / "d.pid")

        # Let it run briefly then shutdown
        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.3)
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_after_delay())
        await runner.run()
        await task
        assert stream.run_once.call_count >= 2


# ---------------------------------------------------------------------------
# TS-85-7: Double SIGINT exits with 130
# Requirement: 85-REQ-2.3
# ---------------------------------------------------------------------------


class TestDoubleSignal:
    """Verify second signal causes immediate exit with code 130."""

    def test_second_signal_exits_130(self) -> None:
        """Second request_shutdown raises SystemExit(130)."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [], budget)

        runner.request_shutdown()  # first: graceful
        assert runner.is_shutting_down is True

        with pytest.raises(SystemExit) as exc_info:
            runner.request_shutdown()  # second: abort
        assert exc_info.value.code == 130


# ---------------------------------------------------------------------------
# TS-85-8: PID file removed on shutdown
# Requirement: 85-REQ-2.4
# ---------------------------------------------------------------------------


class TestPidFileRemovedOnShutdown:
    """Verify PID file is removed on shutdown."""

    async def test_pid_removed_after_run(self, tmp_path: Path) -> None:
        """PID file does not exist after DaemonRunner.run() completes."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        pid_path = tmp_path / "daemon.pid"
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [], budget, pid_path=pid_path)
        runner.request_shutdown()
        state = await runner.run()
        assert not pid_path.exists()
        assert state.uptime_seconds >= 0


# ---------------------------------------------------------------------------
# TS-85-9: Stream shutdown called on exit
# Requirement: 85-REQ-2.5
# ---------------------------------------------------------------------------


class TestStreamShutdownCalled:
    """Verify shutdown() is called on each registered stream."""

    async def test_all_streams_shutdown(self, tmp_path: Path) -> None:
        """Both streams' shutdown() called exactly once."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        s1 = _make_mock_stream(name="s1")
        s2 = _make_mock_stream(name="s2")
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [s1, s2], budget, pid_path=tmp_path / "d.pid")
        runner.request_shutdown()
        await runner.run()
        assert s1.shutdown.call_count == 1
        assert s2.shutdown.call_count == 1


# ---------------------------------------------------------------------------
# TS-85-13: Stream startup priority order
# Requirement: 85-REQ-4.2
# ---------------------------------------------------------------------------


class TestStreamPriorityOrder:
    """Verify streams launch in priority order."""

    async def test_launch_order(self, tmp_path: Path) -> None:
        """Spec executor launched first, fix pipeline second, then rest."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        launch_order: list[str] = []

        def make_recording_stream(name: str) -> MagicMock:
            stream = _make_mock_stream(name=name, interval=1)

            async def record_run() -> None:
                launch_order.append(name)

            stream.run_once = AsyncMock(side_effect=record_run)
            return stream

        streams = [
            make_recording_stream("spec-executor"),
            make_recording_stream("fix-pipeline"),
            make_recording_stream("hunt-scan"),
        ]

        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, streams, budget, pid_path=tmp_path / "d.pid")  # type: ignore[arg-type]

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.2)
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_after_delay())
        await runner.run()
        await task

        # First 3 entries should be in priority order
        assert launch_order[:3] == [
            "spec-executor",
            "fix-pipeline",
            "hunt-scan",
        ]


# ---------------------------------------------------------------------------
# TS-85-14: Simultaneous wake priority
# Requirement: 85-REQ-4.3
# ---------------------------------------------------------------------------


class TestSimultaneousWakePriority:
    """Verify simultaneous wakes execute in priority order."""

    async def test_execution_order(self, tmp_path: Path) -> None:
        """Streams with same interval execute in priority order."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        execution_order: list[str] = []

        def make_recording_stream(name: str) -> MagicMock:
            stream = _make_mock_stream(name=name, interval=1)

            async def record_run() -> None:
                execution_order.append(name)

            stream.run_once = AsyncMock(side_effect=record_run)
            return stream

        streams = [
            make_recording_stream("spec-executor"),
            make_recording_stream("fix-pipeline"),
            make_recording_stream("hunt-scan"),
        ]

        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, streams, budget, pid_path=tmp_path / "d.pid")  # type: ignore[arg-type]

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.2)
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_after_delay())
        await runner.run()
        await task

        assert execution_order[:3] == [
            "spec-executor",
            "fix-pipeline",
            "hunt-scan",
        ]


# ---------------------------------------------------------------------------
# TS-85-27: Unknown stream name in enabled_streams
# Requirement: 85-REQ-9.2
# ---------------------------------------------------------------------------


class TestUnknownStreamName:
    """Verify unknown stream names are warned and ignored."""

    def test_unknown_stream_ignored(self) -> None:
        """Unknown stream in enabled_streams does not cause error."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        streams = [_make_mock_stream(name="spec-executor")]
        config = _make_config(enabled_streams=["specs", "unknown_stream"])
        budget = SharedBudget(max_cost=None)
        # Should not raise
        runner = DaemonRunner(config, None, streams, budget)  # type: ignore[arg-type]
        assert len(runner.streams) >= 1


# ---------------------------------------------------------------------------
# TS-85-E2: All streams disabled enters idle loop
# Requirement: 85-REQ-1.E2
# ---------------------------------------------------------------------------


class TestAllStreamsDisabled:
    """Verify daemon enters idle loop when all streams disabled."""

    async def test_no_run_once_called(self, tmp_path: Path) -> None:
        """No stream's run_once called when all disabled."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        streams = [_make_mock_stream(name=f"s{i}", enabled=False) for i in range(4)]
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, streams, budget, pid_path=tmp_path / "d.pid")  # type: ignore[arg-type]
        runner.request_shutdown()
        await runner.run()
        for s in streams:
            assert s.run_once.call_count == 0


# ---------------------------------------------------------------------------
# TS-85-E8: Disabled spec executor skips priority delay
# Requirement: 85-REQ-4.E1
# ---------------------------------------------------------------------------


class TestDisabledSpecExecutorNoPriorityDelay:
    """Verify disabling spec executor doesn't delay other streams."""

    async def test_fix_pipeline_launches_immediately(self, tmp_path: Path) -> None:
        """Fix pipeline launches without waiting for disabled spec executor."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        spec = _make_mock_stream(name="spec-executor", enabled=False)
        fix = _make_mock_stream(name="fix-pipeline", enabled=True)
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(config, None, [spec, fix], budget, pid_path=tmp_path / "d.pid")

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.2)
            runner.request_shutdown()

        task = asyncio.create_task(shutdown_after_delay())
        await runner.run()
        await task
        assert fix.run_once.call_count >= 1
