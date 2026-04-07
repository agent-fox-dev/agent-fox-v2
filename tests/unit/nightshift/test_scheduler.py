"""Unit tests for Scheduler.

Test Spec: TS-61-4, TS-61-5, TS-61-6, TS-61-E4
Requirements: 61-REQ-2.1, 61-REQ-2.2, 61-REQ-2.3, 61-REQ-2.E2
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-61-4: Issue check runs at configured interval
# Requirement: 61-REQ-2.1
# ---------------------------------------------------------------------------


class TestIssueCheckInterval:
    """Verify that issue checks are scheduled at the configured interval."""

    @pytest.mark.asyncio
    async def test_issue_check_at_interval(self) -> None:
        """Issue check called 3 times over 250 simulated seconds (interval=120)."""
        from agent_fox.nightshift.scheduler import Scheduler

        call_count = 0

        async def on_issue_check() -> None:
            nonlocal call_count
            call_count += 1

        async def noop() -> None:
            pass

        scheduler = Scheduler(
            issue_interval=120,
            hunt_interval=99999,
            on_issue_check=on_issue_check,
            on_hunt_scan=noop,
        )
        await scheduler.run_for(250)
        # t=0, t=120, t=240
        assert call_count == 3


# ---------------------------------------------------------------------------
# TS-61-5: Hunt scan runs at configured interval
# Requirement: 61-REQ-2.2
# ---------------------------------------------------------------------------


class TestHuntScanInterval:
    """Verify that hunt scans are scheduled at the configured interval."""

    @pytest.mark.asyncio
    async def test_hunt_scan_at_interval(self) -> None:
        """Hunt scan called 3 times over 250 simulated seconds (interval=100)."""
        from agent_fox.nightshift.scheduler import Scheduler

        call_count = 0

        async def on_hunt_scan() -> None:
            nonlocal call_count
            call_count += 1

        async def noop() -> None:
            pass

        scheduler = Scheduler(
            issue_interval=99999,
            hunt_interval=100,
            on_issue_check=noop,
            on_hunt_scan=on_hunt_scan,
        )
        await scheduler.run_for(250)
        # t=0, t=100, t=200
        assert call_count == 3


# ---------------------------------------------------------------------------
# TS-61-6: Initial scan on startup
# Requirement: 61-REQ-2.3
# ---------------------------------------------------------------------------


class TestInitialScanOnStartup:
    """Verify that both callbacks run immediately on startup."""

    @pytest.mark.asyncio
    async def test_both_run_immediately(self) -> None:
        """Both issue check and hunt scan fire before any interval elapses."""
        from agent_fox.nightshift.scheduler import Scheduler

        issue_checked = False
        hunt_scanned = False

        async def on_issue_check() -> None:
            nonlocal issue_checked
            issue_checked = True

        async def on_hunt_scan() -> None:
            nonlocal hunt_scanned
            hunt_scanned = True

        scheduler = Scheduler(
            issue_interval=900,
            hunt_interval=14400,
            on_issue_check=on_issue_check,
            on_hunt_scan=on_hunt_scan,
        )
        await scheduler.run_for(1)
        assert issue_checked is True
        assert hunt_scanned is True


# ---------------------------------------------------------------------------
# TS-61-E4: Hunt scan overlap prevention
# Requirement: 61-REQ-2.E2
# ---------------------------------------------------------------------------


class TestHuntScanOverlap:
    """Verify that overlapping hunt scans are skipped."""

    @pytest.mark.asyncio
    async def test_skip_overlapping_scan(self, caplog: pytest.LogCaptureFixture) -> None:
        """When a hunt scan is already in progress, the next is skipped."""
        import logging

        with caplog.at_level(logging.INFO, logger="agent_fox.nightshift.engine"):
            # Create a minimal engine and simulate overlap
            engine = _make_mock_engine()
            engine._hunt_scan_in_progress = True  # type: ignore[attr-defined]
            await engine._run_hunt_scan()  # type: ignore[attr-defined]

        log_text = caplog.text.lower()
        assert "skip" in log_text or "overlap" in log_text or "progress" in log_text


def _make_mock_engine() -> object:
    """Create a NightShiftEngine with mock dependencies."""
    from unittest.mock import AsyncMock, MagicMock

    from agent_fox.nightshift.engine import NightShiftEngine

    config = MagicMock()
    config.orchestrator.max_cost = None
    config.orchestrator.max_sessions = None
    platform = AsyncMock()
    return NightShiftEngine(config=config, platform=platform)
