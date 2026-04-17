"""Unit tests for the processed-issue deduplication guard in NightShiftEngine.

Verifies that issues already processed in a run are not re-processed when
the platform API returns them again (e.g. due to eventual consistency after
the issue was closed).

Issue: #465 — Night-shift re-processes closed issues (double-fix of #464).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.protocol import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(max_cost: float | None = None, max_sessions: int | None = None):
    """Return a NightShiftEngine with a mocked platform and minimal config."""
    from agent_fox.nightshift.engine import NightShiftEngine

    config = MagicMock()
    config.orchestrator.max_cost = max_cost
    config.orchestrator.max_sessions = max_sessions
    config.night_shift.similarity_threshold = 0.85

    platform = AsyncMock()
    # Default: no issues; individual tests override as needed.
    platform.list_issues_by_label = AsyncMock(return_value=[])
    platform.fetch_github_relationships = AsyncMock(return_value=[])

    engine = NightShiftEngine(config=config, platform=platform)
    return engine, platform


def _make_issue(number: int, title: str = "Test issue") -> IssueResult:
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/example/repo/issues/{number}",
        body="Issue body",
    )


# ---------------------------------------------------------------------------
# Test: _processed_issues is initialised to empty set
# ---------------------------------------------------------------------------


class TestProcessedIssuesInit:
    """Verify _processed_issues starts empty on construction."""

    def test_initial_state_is_empty(self) -> None:
        engine, _ = _make_engine()
        assert engine._processed_issues == set()


# ---------------------------------------------------------------------------
# Test: processed issue is not re-processed in subsequent scan cycles
# ---------------------------------------------------------------------------


class TestNoReprocessing:
    """Issue processed once should not be processed again."""

    @pytest.mark.asyncio
    async def test_processed_issue_skipped_on_second_call(self) -> None:
        """An issue returned a second time by the platform is skipped."""
        engine, platform = _make_engine()

        issue = _make_issue(464)

        # Patch _process_fix so we can count how many times it's called.
        process_fix_calls: list[int] = []

        async def fake_process_fix(iss, **_kwargs) -> None:
            process_fix_calls.append(iss.number)

        # Also stub out helpers called inside _run_issue_check.
        with (
            patch("agent_fox.nightshift.engine.parse_text_references", return_value=[]),
            patch(
                "agent_fox.nightshift.engine.fetch_github_relationships",
                new=AsyncMock(return_value=[]),
            ),
            patch("agent_fox.nightshift.engine.build_graph", return_value=[464]),
            patch.object(engine, "_process_fix", side_effect=fake_process_fix),
        ):
            # First scan: platform returns issue #464.
            platform.list_issues_by_label = AsyncMock(return_value=[issue])
            await engine._run_issue_check()

            # Second scan: platform still returns issue #464 (e.g. eventual consistency).
            platform.list_issues_by_label = AsyncMock(return_value=[issue])
            await engine._run_issue_check()

        # _process_fix should have been called exactly once.
        assert process_fix_calls == [464]

    @pytest.mark.asyncio
    async def test_new_issue_still_processed_after_prior_issue_fixed(self) -> None:
        """A new issue is processed even when a prior issue has been marked done."""
        engine, platform = _make_engine()

        issue_464 = _make_issue(464)
        issue_470 = _make_issue(470)

        process_fix_calls: list[int] = []

        async def fake_process_fix(iss, **_kwargs) -> None:
            process_fix_calls.append(iss.number)

        # build_graph receives the already-filtered issues list, so it should
        # return only the numbers for the issues it was given.
        def fake_build_graph(issues, edges):
            return [i.number for i in issues]

        with (
            patch("agent_fox.nightshift.engine.parse_text_references", return_value=[]),
            patch(
                "agent_fox.nightshift.engine.fetch_github_relationships",
                new=AsyncMock(return_value=[]),
            ),
            patch("agent_fox.nightshift.engine.build_graph", side_effect=fake_build_graph),
            patch.object(engine, "_process_fix", side_effect=fake_process_fix),
        ):
            # First scan: only issue #464.
            platform.list_issues_by_label = AsyncMock(return_value=[issue_464])
            await engine._run_issue_check()

            # Second scan: platform still returns stale #464 plus a new #470.
            # After dedup filtering, only #470 should be passed to build_graph.
            platform.list_issues_by_label = AsyncMock(return_value=[issue_464, issue_470])
            await engine._run_issue_check()

        # Issue #464 processed once; issue #470 processed once.
        assert process_fix_calls.count(464) == 1
        assert process_fix_calls.count(470) == 1


# ---------------------------------------------------------------------------
# Test: processed issue number recorded even when _process_fix fails
# ---------------------------------------------------------------------------


class TestProcessedOnFailure:
    """Issue number is recorded in _processed_issues even when fix raises."""

    @pytest.mark.asyncio
    async def test_issue_marked_after_exception(self) -> None:
        """Failed issue is still added to _processed_issues."""
        engine, platform = _make_engine()

        issue = _make_issue(464)

        async def failing_process_fix(iss, **_kwargs) -> None:
            raise RuntimeError("fix failed")

        with (
            patch("agent_fox.nightshift.engine.parse_text_references", return_value=[]),
            patch(
                "agent_fox.nightshift.engine.fetch_github_relationships",
                new=AsyncMock(return_value=[]),
            ),
            patch("agent_fox.nightshift.engine.build_graph", return_value=[464]),
            patch.object(engine, "_process_fix", side_effect=failing_process_fix),
        ):
            platform.list_issues_by_label = AsyncMock(return_value=[issue])
            await engine._run_issue_check()

        assert 464 in engine._processed_issues


# ---------------------------------------------------------------------------
# Test: _drain_issues stops when all remaining issues are already processed
# ---------------------------------------------------------------------------


class TestDrainIssuesFiltersProcessed:
    """_drain_issues re-poll filters already-processed issues."""

    @pytest.mark.asyncio
    async def test_drain_terminates_when_all_processed(self) -> None:
        """Drain loop terminates even if platform re-poll returns processed issues."""
        engine, platform = _make_engine()

        issue = _make_issue(464)
        # Pre-populate processed set so the issue is already known.
        engine._processed_issues.add(464)

        run_issue_check_calls = 0

        async def fake_run_issue_check(_seen: set[int] | None = None) -> None:
            nonlocal run_issue_check_calls
            run_issue_check_calls += 1

        with patch.object(engine, "_run_issue_check", side_effect=fake_run_issue_check):
            # Platform keeps returning issue #464 (as if it hasn't propagated the close).
            platform.list_issues_by_label = AsyncMock(return_value=[issue])
            drained = await engine._drain_issues()

        # Drain should return True (considers queue clear) after a single iteration.
        assert drained is True
        assert run_issue_check_calls == 1
