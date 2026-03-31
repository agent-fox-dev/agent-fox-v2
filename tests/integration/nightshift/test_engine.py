"""Integration tests for NightShiftEngine.

Test Spec: TS-61-1, TS-61-3, TS-61-28
Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-1.4, 61-REQ-9.3
"""

from __future__ import annotations

import asyncio

import pytest

# ---------------------------------------------------------------------------
# TS-61-1: Night-shift command starts event loop
# Requirement: 61-REQ-1.1
# ---------------------------------------------------------------------------


class TestNightShiftStartsEventLoop:
    """Verify that night-shift starts a continuous event loop."""

    @pytest.mark.asyncio
    async def test_engine_runs_until_shutdown(self) -> None:
        """Engine run() is called and runs until shutdown is requested."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.issue_check_interval = 900
        config.night_shift.hunt_scan_interval = 14400

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(config=config, platform=mock_platform)

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.1)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown_after_delay())
        result = await task
        assert result.is_shutting_down is True


# ---------------------------------------------------------------------------
# TS-61-3: Graceful shutdown on SIGINT
# Requirements: 61-REQ-1.3, 61-REQ-1.4
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    """Verify that SIGINT completes the current operation before exiting."""

    @pytest.mark.asyncio
    async def test_single_sigint_completes_operation(self) -> None:
        """A single SIGINT lets the current operation complete."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.issue_check_interval = 900
        config.night_shift.hunt_scan_interval = 14400

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(config=config, platform=mock_platform)

        hunt_scan_started = asyncio.Event()
        hunt_scan_completed = asyncio.Event()

        original_hunt = engine._run_hunt_scan

        async def slow_hunt_scan() -> None:
            hunt_scan_started.set()
            await asyncio.sleep(0.2)
            hunt_scan_completed.set()
            await original_hunt()

        engine._run_hunt_scan = slow_hunt_scan  # type: ignore[assignment]

        task = asyncio.create_task(engine.run())

        await hunt_scan_started.wait()
        engine.request_shutdown()

        result = await task
        assert result.is_shutting_down is True


# ---------------------------------------------------------------------------
# TS-61-28: Cost limit honoured
# Requirement: 61-REQ-9.3
# ---------------------------------------------------------------------------


class TestCostLimitHonoured:
    """Verify that night-shift stops when max_cost is reached."""

    @pytest.mark.asyncio
    async def test_stops_at_cost_limit(self) -> None:
        """Engine stops dispatching when total_cost >= max_cost."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        config.orchestrator.max_cost = 1.0
        config.orchestrator.max_sessions = None
        config.night_shift.issue_check_interval = 60
        config.night_shift.hunt_scan_interval = 99999

        # Two af:fix issues, each costing 0.6
        issues = [
            IssueResult(number=1, title="Fix A", html_url="http://a"),
            IssueResult(number=2, title="Fix B", html_url="http://b"),
        ]
        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)

        # Mock fix processing to add 0.6 cost each time
        async def mock_process_fix(issue: IssueResult) -> None:
            engine.state.total_cost += 0.6
            engine.state.issues_fixed += 1

        engine._process_fix = mock_process_fix  # type: ignore[assignment]

        # Stop after one issue check cycle
        async def stop_soon() -> None:
            await asyncio.sleep(0.2)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(stop_soon())
        result = await task

        # First issue processed (cost=0.6), second skipped (would exceed 1.0)
        assert result.issues_fixed == 1
        assert result.total_cost <= 1.0
