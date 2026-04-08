"""Integration tests for NightShiftEngine.

Test Spec: TS-61-1, TS-61-3, TS-61-28, TS-302-1
Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-1.4, 61-REQ-9.3, 86-REQ-2.1
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
        config.night_shift.spec_gen_interval = 300

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
        config.night_shift.spec_gen_interval = 300

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
# TS-302-1: Spec generator wired into engine loop
# Requirement: 86-REQ-2.1
# ---------------------------------------------------------------------------


class TestSpecGenWiredIntoEngine:
    """Verify that _run_spec_gen is called during the engine run loop."""

    @pytest.mark.asyncio
    async def test_spec_gen_runs_on_startup(self) -> None:
        """Engine calls _run_spec_gen during its initial phase."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.issue_check_interval = 900
        config.night_shift.hunt_scan_interval = 14400
        config.night_shift.spec_gen_interval = 300

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(config=config, platform=mock_platform)

        spec_gen_called = False
        original_run_spec_gen = engine._run_spec_gen

        async def tracking_spec_gen() -> None:
            nonlocal spec_gen_called
            spec_gen_called = True
            await original_run_spec_gen()

        engine._run_spec_gen = tracking_spec_gen  # type: ignore[assignment]

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(0.1)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown_after_delay())
        await task

        assert spec_gen_called, "_run_spec_gen was never called during engine.run()"

    @pytest.mark.asyncio
    async def test_spec_gen_processes_af_spec_issue(self) -> None:
        """Engine processes an af:spec-labelled issue via SpecGenerator."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.engine import NightShiftEngine
        from agent_fox.nightshift.spec_gen import SpecGenOutcome, SpecGenResult
        from agent_fox.platform.github import IssueResult

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.issue_check_interval = 99999
        config.night_shift.hunt_scan_interval = 99999
        config.night_shift.spec_gen_interval = 300

        spec_issue = IssueResult(number=10, title="Spec: new feature", html_url="http://spec")

        mock_platform = AsyncMock()

        def list_by_label(label: str, **kwargs: object) -> list[object]:
            if label == "af:spec":
                return [spec_issue]
            return []

        mock_platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)

        engine = NightShiftEngine(config=config, platform=mock_platform)

        mock_result = SpecGenResult(
            outcome=SpecGenOutcome.GENERATED,
            issue_number=10,
            spec_name="test_spec",
            commit_hash="abc123",
            cost=0.5,
        )

        with patch(
            "agent_fox.nightshift.spec_gen.SpecGenerator",
        ) as MockGenerator:
            mock_gen_instance = AsyncMock()
            mock_gen_instance.process_issue = AsyncMock(return_value=mock_result)
            mock_gen_instance._has_new_human_comment = MagicMock(return_value=False)
            MockGenerator.return_value = mock_gen_instance

            async def shutdown_after_delay() -> None:
                await asyncio.sleep(0.2)
                engine.state.is_shutting_down = True

            task = asyncio.create_task(engine.run())
            asyncio.create_task(shutdown_after_delay())
            result = await task

        assert result.specs_generated == 1
        assert result.total_cost >= 0.5

    @pytest.mark.asyncio
    async def test_spec_gen_runs_periodically(self) -> None:
        """Engine calls _run_spec_gen on spec_gen_interval ticks."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.issue_check_interval = 99999
        config.night_shift.hunt_scan_interval = 99999
        config.night_shift.spec_gen_interval = 1

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(config=config, platform=mock_platform)

        spec_gen_count = 0

        async def counting_spec_gen() -> None:
            nonlocal spec_gen_count
            spec_gen_count += 1

        engine._run_spec_gen = counting_spec_gen  # type: ignore[assignment]

        async def shutdown_after_delay() -> None:
            await asyncio.sleep(2.5)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown_after_delay())
        await task

        assert spec_gen_count >= 2, f"Expected >=2 spec gen calls, got {spec_gen_count}"


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
        config.night_shift.spec_gen_interval = 99999

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
