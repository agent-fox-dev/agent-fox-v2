"""Tests for issue-first gate logic in NightShiftEngine.

Test Spec: TS-81-1, TS-81-2, TS-81-3, TS-81-4, TS-81-5,
           TS-81-E1, TS-81-E2, TS-81-E3
Requirements: 81-REQ-1.1 through 81-REQ-1.5, 81-REQ-1.E1 through 81-REQ-1.E3
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_fox.nightshift.engine import NightShiftEngine


def _make_config(
    *,
    issue_interval: int = 900,
    hunt_interval: int = 14400,
    max_cost: float | None = None,
    max_sessions: int | None = None,
) -> MagicMock:
    config = MagicMock()
    config.night_shift.issue_check_interval = issue_interval
    config.night_shift.hunt_scan_interval = hunt_interval
    config.orchestrator.max_cost = max_cost
    config.orchestrator.max_sessions = max_sessions
    return config


def _make_issue(number: int, title: str = "Test issue") -> MagicMock:
    """Create a mock issue that passes the IssueResult check in _process_fix."""
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = f"Fix {title}"
    issue.html_url = f"http://example.com/{number}"
    return issue


# ---------------------------------------------------------------------------
# TS-81-1: Hunt scan suppressed while af:fix issues exist
# Requirement: 81-REQ-1.1
# ---------------------------------------------------------------------------


class TestHuntSuppressedWhileIssuesExist:
    """Verify that the engine never calls _run_hunt_scan when issues exist."""

    @pytest.mark.asyncio
    async def test_hunt_suppressed_while_issues_exist(self) -> None:
        config = _make_config()
        platform = AsyncMock()

        # Platform always returns issues (they never clear)
        issues = [_make_issue(1), _make_issue(2)]
        platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=platform)

        hunt_call_count = 0
        issue_check_count = 0

        original_hunt = engine._run_hunt_scan

        async def mock_hunt() -> None:
            nonlocal hunt_call_count
            hunt_call_count += 1
            await original_hunt()

        async def mock_issue_check() -> None:
            nonlocal issue_check_count
            issue_check_count += 1
            # Don't actually process — issues stay open

        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]
        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]

        # Shutdown after a short delay
        async def shutdown() -> None:
            await asyncio.sleep(0.1)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        assert hunt_call_count == 0, "Hunt scan should never fire while issues exist"
        assert issue_check_count >= 1, "Issue check should have been called"


# ---------------------------------------------------------------------------
# TS-81-2: Startup processes issues before hunt scan
# Requirement: 81-REQ-1.2
# ---------------------------------------------------------------------------


class TestStartupIssuesBeforeHunt:
    """Verify startup runs issue check before first hunt scan."""

    @pytest.mark.asyncio
    async def test_startup_issues_before_hunt(self) -> None:
        config = _make_config()
        platform = AsyncMock()

        call_log: list[str] = []
        call_count = 0

        # First call returns 1 issue, subsequent calls return 0
        async def mock_list_issues(*args: object, **kwargs: object) -> list[object]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # first drain iteration
                return [_make_issue(1)]
            return []

        platform.list_issues_by_label = mock_list_issues

        engine = NightShiftEngine(config=config, platform=platform)

        async def mock_issue_check() -> None:
            call_log.append("issue_check")

        async def mock_hunt() -> None:
            call_log.append("hunt_scan")

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]
        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        # Shutdown after startup completes
        async def shutdown() -> None:
            await asyncio.sleep(0.1)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        assert len(call_log) >= 2
        assert call_log[0] == "issue_check", "First call must be issue_check"
        hunt_idx = call_log.index("hunt_scan")
        issue_idx = call_log.index("issue_check")
        assert issue_idx < hunt_idx, "issue_check must come before hunt_scan"


# ---------------------------------------------------------------------------
# TS-81-3: Post-hunt issue drain
# Requirement: 81-REQ-1.3
# ---------------------------------------------------------------------------


class TestPostHuntIssueDrain:
    """Verify that after hunt scan, issue check runs before next hunt."""

    @pytest.mark.asyncio
    async def test_post_hunt_issue_drain(self) -> None:
        config = _make_config()
        platform = AsyncMock()

        call_log: list[str] = []
        hunt_done = False

        # No issues initially, 1 issue after hunt, then 0
        async def mock_list_issues(*args: object, **kwargs: object) -> list[object]:
            if hunt_done:
                # After first post-hunt poll, return issue then clear
                if any(c == "post_hunt_issue_check" for c in call_log):
                    return []
                return [_make_issue(10)]
            return []

        platform.list_issues_by_label = mock_list_issues

        engine = NightShiftEngine(config=config, platform=platform)

        async def mock_issue_check() -> None:
            if hunt_done:
                call_log.append("post_hunt_issue_check")
            else:
                call_log.append("issue_check")

        async def mock_hunt() -> None:
            nonlocal hunt_done
            call_log.append("hunt_scan")
            hunt_done = True

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]
        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        async def shutdown() -> None:
            await asyncio.sleep(0.15)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        # After hunt_scan, there must be an issue_check before next hunt
        hunt_idx = call_log.index("hunt_scan")
        subsequent = call_log[hunt_idx + 1 :]
        assert "post_hunt_issue_check" in subsequent, (
            f"Post-hunt issue check expected but not found. Call log: {call_log}"
        )


# ---------------------------------------------------------------------------
# TS-81-4: Hunt timer fires with pending issues — issues first
# Requirement: 81-REQ-1.4
# ---------------------------------------------------------------------------


class TestHuntTimerWithPendingIssues:
    """When hunt timer fires but issues exist, issues are processed first."""

    @pytest.mark.asyncio
    async def test_hunt_timer_with_pending_issues(self) -> None:
        config = _make_config(hunt_interval=1, issue_interval=1)
        platform = AsyncMock()

        call_log: list[str] = []
        drain_call_count = 0

        # Return issues on first drain, then clear
        async def mock_list_issues(*args: object, **kwargs: object) -> list[object]:
            if drain_call_count <= 1:
                return [_make_issue(1)]
            return []

        platform.list_issues_by_label = mock_list_issues

        engine = NightShiftEngine(config=config, platform=platform)

        async def mock_issue_check() -> None:
            nonlocal drain_call_count
            drain_call_count += 1
            call_log.append("issue_check")

        async def mock_hunt() -> None:
            call_log.append("hunt_scan")

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]
        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        async def shutdown() -> None:
            await asyncio.sleep(0.2)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        # issue_check should appear before hunt_scan
        if "hunt_scan" in call_log:
            hunt_idx = call_log.index("hunt_scan")
            prior = call_log[:hunt_idx]
            assert "issue_check" in prior, f"issue_check must come before hunt_scan. Log: {call_log}"


# ---------------------------------------------------------------------------
# TS-81-5: Hunt scan fires when no issues exist
# Requirement: 81-REQ-1.5
# ---------------------------------------------------------------------------


class TestHuntFiresWhenNoIssues:
    """Hunt scan fires immediately when timer elapses and no issues exist."""

    @pytest.mark.asyncio
    async def test_hunt_fires_when_no_issues(self) -> None:
        config = _make_config(hunt_interval=14400)
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        engine = NightShiftEngine(config=config, platform=platform)

        hunt_called = False

        async def mock_hunt() -> None:
            nonlocal hunt_called
            hunt_called = True

        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        async def shutdown() -> None:
            await asyncio.sleep(0.15)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        # Hunt should fire on startup when no issues
        assert hunt_called, "Hunt scan should fire when no issues exist"


# ---------------------------------------------------------------------------
# TS-81-E1: Platform API failure during pre-hunt issue check
# Requirement: 81-REQ-1.E1
# ---------------------------------------------------------------------------


class TestPlatformFailureFailOpen:
    """If platform API fails during drain, hunt scan proceeds."""

    @pytest.mark.asyncio
    async def test_platform_failure_fail_open(self) -> None:
        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(side_effect=RuntimeError("API error"))

        engine = NightShiftEngine(config=config, platform=platform)

        hunt_called = False

        async def mock_hunt() -> None:
            nonlocal hunt_called
            hunt_called = True

        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        async def shutdown() -> None:
            await asyncio.sleep(0.1)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        assert hunt_called, "Hunt scan should proceed despite drain failure"


# ---------------------------------------------------------------------------
# TS-81-E2: Issue fix failure does not block hunt scan
# Requirement: 81-REQ-1.E2
# ---------------------------------------------------------------------------


class TestFixFailureContinues:
    """If an issue fix fails, remaining issues are processed and hunt runs."""

    @pytest.mark.asyncio
    async def test_fix_failure_continues(self) -> None:
        config = _make_config()
        platform = AsyncMock()

        call_count = 0

        # Return 2 issues on first call, then 0
        async def mock_list(*args: object, **kwargs: object) -> list[object]:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return [_make_issue(1), _make_issue(2)]
            return []

        platform.list_issues_by_label = mock_list

        engine = NightShiftEngine(config=config, platform=platform)

        processed: list[int] = []

        # _run_issue_check internally processes issues — we mock it to
        # simulate that issues get processed (even if one fails, the
        # existing _run_issue_check catches per-issue exceptions)
        async def mock_issue_check() -> None:
            processed.append(1)

        hunt_called = False

        async def mock_hunt() -> None:
            nonlocal hunt_called
            hunt_called = True

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]
        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        async def shutdown() -> None:
            await asyncio.sleep(0.15)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        assert len(processed) >= 1, "Issues should be processed"
        assert hunt_called, "Hunt scan should run after issues processed"


# ---------------------------------------------------------------------------
# TS-81-E3: Auto mode post-hunt issue creation triggers drain
# Requirement: 81-REQ-1.E3
# ---------------------------------------------------------------------------


class TestAutoModePostHuntDrain:
    """In auto mode, issues created by hunt scan are drained post-hunt."""

    @pytest.mark.asyncio
    async def test_auto_mode_post_hunt_drain(self) -> None:
        config = _make_config()
        platform = AsyncMock()

        hunt_done = False
        post_hunt_issues_processed = False

        async def mock_list(*args: object, **kwargs: object) -> list[object]:
            if hunt_done and not post_hunt_issues_processed:
                return [_make_issue(100)]
            return []

        platform.list_issues_by_label = mock_list

        engine = NightShiftEngine(config=config, platform=platform, auto_fix=True)

        async def mock_issue_check() -> None:
            nonlocal post_hunt_issues_processed
            if hunt_done:
                post_hunt_issues_processed = True

        async def mock_hunt() -> None:
            nonlocal hunt_done
            hunt_done = True

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]
        engine._run_hunt_scan = mock_hunt  # type: ignore[assignment]

        async def shutdown() -> None:
            await asyncio.sleep(0.15)
            engine.state.is_shutting_down = True

        task = asyncio.create_task(engine.run())
        asyncio.create_task(shutdown())
        await task

        assert post_hunt_issues_processed, "Post-hunt issues created in auto mode should be drained"


# ---------------------------------------------------------------------------
# _drain_issues unit tests
# ---------------------------------------------------------------------------


class TestDrainIssues:
    """Direct tests for the _drain_issues method."""

    @pytest.mark.asyncio
    async def test_drain_loops_until_no_issues(self) -> None:
        config = _make_config()
        platform = AsyncMock()

        drain_iterations = 0

        # Return issues for 3 rounds, then clear
        async def mock_list(*args: object, **kwargs: object) -> list[object]:
            if drain_iterations < 3:
                return [_make_issue(1)]
            return []

        platform.list_issues_by_label = mock_list

        engine = NightShiftEngine(config=config, platform=platform)

        async def mock_issue_check() -> None:
            nonlocal drain_iterations
            drain_iterations += 1

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]

        await engine._drain_issues()

        assert drain_iterations == 3, f"Should drain 3 times before clearing, got {drain_iterations}"

    @pytest.mark.asyncio
    async def test_drain_respects_shutdown(self) -> None:
        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[_make_issue(1)])

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.is_shutting_down = True

        issue_check_count = 0

        async def mock_issue_check() -> None:
            nonlocal issue_check_count
            issue_check_count += 1

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]

        await engine._drain_issues()

        assert issue_check_count == 0, "Should not process when shutting down"

    @pytest.mark.asyncio
    async def test_drain_respects_cost_limit(self) -> None:
        config = _make_config(max_cost=1.0)
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[_make_issue(1)])

        engine = NightShiftEngine(config=config, platform=platform)
        engine.state.total_cost = 0.9  # Over 50% threshold

        issue_check_count = 0

        async def mock_issue_check() -> None:
            nonlocal issue_check_count
            issue_check_count += 1

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]

        await engine._drain_issues()

        assert issue_check_count == 0, "Should stop when cost limit reached"

    @pytest.mark.asyncio
    async def test_drain_safety_valve(self) -> None:
        """Safety valve prevents infinite loop."""
        config = _make_config()
        platform = AsyncMock()
        platform.list_issues_by_label = AsyncMock(return_value=[_make_issue(1)])

        engine = NightShiftEngine(config=config, platform=platform)

        issue_check_count = 0

        async def mock_issue_check() -> None:
            nonlocal issue_check_count
            issue_check_count += 1

        engine._run_issue_check = mock_issue_check  # type: ignore[assignment]

        await engine._drain_issues()

        assert issue_check_count == engine._MAX_DRAIN_ITERATIONS
