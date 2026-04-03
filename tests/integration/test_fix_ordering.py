"""Integration tests for fix issue ordering and dependency detection.

Test Spec: TS-71-1, TS-71-17
Requirements: 71-REQ-1.1, 71-REQ-5.4
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(number: int, body: str = "", title: str = "") -> IssueResult:
    """Create a minimal IssueResult for testing."""
    return IssueResult(
        number=number,
        title=title or f"Issue #{number}",
        html_url=f"https://github.com/test/repo/issues/{number}",
        body=body,
    )


# ---------------------------------------------------------------------------
# Integration: End-to-end _run_issue_check() with mocked platform and AI
# TS-71-1: Issues fetched in ascending order (end-to-end)
# TS-71-17: Obsolete issues removed from queue (end-to-end)
# ---------------------------------------------------------------------------


class TestEndToEndIssueCheck:
    """End-to-end integration test for _run_issue_check()."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_triage_and_staleness(self) -> None:
        """Full issue check: triage -> process -> staleness -> skip obsolete."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)
        mock_platform.close_issue = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        processed: list[int] = []

        async def track_fix(issue: IssueResult) -> None:
            processed.append(issue.number)

        engine._process_fix = track_fix  # type: ignore[assignment]

        with (
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                new_callable=AsyncMock,
            ) as mock_triage,
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                new_callable=AsyncMock,
            ) as mock_staleness,
        ):
            from agent_fox.nightshift.staleness import StalenessResult
            from agent_fox.nightshift.triage import TriageResult

            mock_triage.return_value = TriageResult(
                processing_order=[10, 20, 30],
                edges=[],
                supersession_pairs=[],
            )

            call_count = 0

            async def staleness_side_effect(*args: object, **kwargs: object) -> StalenessResult:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # After fixing #10, mark #20 as obsolete
                    return StalenessResult(obsolete_issues=[20], rationale={20: "resolved by #10"})
                return StalenessResult(obsolete_issues=[], rationale={})

            mock_staleness.side_effect = staleness_side_effect

            await engine._run_issue_check()

        # #10 processed, #20 skipped (obsolete), #30 processed
        assert processed == [10, 30]

        # Platform should have been asked to close #20
        mock_platform.close_issue.assert_called()

    @pytest.mark.asyncio
    async def test_ascending_fetch_end_to_end(self) -> None:
        """Verify platform called with direction='asc' in full pipeline."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None

        mock_platform = AsyncMock()
        issues = [_make_issue(10), _make_issue(20), _make_issue(30)]
        mock_platform.list_issues_by_label = AsyncMock(return_value=issues)

        engine = NightShiftEngine(config=config, platform=mock_platform)
        engine._process_fix = AsyncMock()  # type: ignore[assignment]

        with (
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                new_callable=AsyncMock,
            ) as mock_triage,
            patch(
                "agent_fox.nightshift.engine.check_staleness",
                new_callable=AsyncMock,
            ) as mock_staleness,
        ):
            from agent_fox.nightshift.staleness import StalenessResult
            from agent_fox.nightshift.triage import TriageResult

            mock_triage.return_value = TriageResult(
                processing_order=[10, 20, 30],
                edges=[],
                supersession_pairs=[],
            )
            mock_staleness.return_value = StalenessResult(obsolete_issues=[], rationale={})

            await engine._run_issue_check()

        call_kwargs = mock_platform.list_issues_by_label.call_args
        assert call_kwargs.kwargs.get("direction") == "asc" or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] == "asc"
        )
