"""Tests for af:fixed label assignment on issue closure (fixes #429).

Verifies that the af:fixed label is added when issues are closed via:
1. fix_pipeline.py — successful fix closure
2. engine.py — supersession closure
3. engine.py — staleness closure

The af:fix label is intentionally preserved on closure to maintain provenance.
af:fixed is added as a re-processing guard and to signal resolution by agent-fox.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.platform.protocol import IssueResult
from agent_fox.workspace import WorkspaceInfo


def _mock_workspace() -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


LABEL_FIXED = "af:fixed"


# ---------------------------------------------------------------------------
# Fix pipeline: af:fixed added after successful close
# ---------------------------------------------------------------------------


class TestFixPipelineLabelFixed:
    """Verify af:fixed label is assigned when fix pipeline closes an issue."""

    @pytest.mark.asyncio
    async def test_fixed_label_assigned_on_successful_close(self) -> None:
        """After close_issue succeeds, assign_label('af:fixed') is called."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()
        mock_platform.assign_label = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "triage":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=42,
            title="Some bug",
            html_url="https://github.com/test/repo/issues/42",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")):
            await pipeline.process_issue(issue, issue_body="Bug description.")

        mock_platform.close_issue.assert_awaited_once()
        mock_platform.assign_label.assert_any_await(42, LABEL_FIXED)

    @pytest.mark.asyncio
    async def test_fix_label_not_removed_on_successful_close(self) -> None:
        """After close_issue succeeds, remove_label is NOT called (af:fix preserved)."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()
        mock_platform.remove_label = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "triage":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=42,
            title="Some bug",
            html_url="https://github.com/test/repo/issues/42",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="merged")):
            await pipeline.process_issue(issue, issue_body="Bug description.")

        mock_platform.close_issue.assert_awaited_once()
        mock_platform.remove_label.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fixed_label_not_assigned_when_harvest_fails(self) -> None:
        """When harvest fails and issue is NOT closed, assign_label is NOT called."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.orchestrator.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()
        mock_platform.assign_label = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        triage_response = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"},
                ],
            }
        )
        review_response = json.dumps(
            {
                "verdicts": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ok"}],
                "overall_verdict": "PASS",
                "summary": "ok",
            }
        )

        async def mock_run_session(archetype: str, workspace: object = None, **kwargs: object) -> MagicMock:
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "triage":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        pipeline._run_session = mock_run_session  # type: ignore[assignment]

        issue = IssueResult(
            number=42,
            title="Some bug",
            html_url="https://github.com/test/repo/issues/42",
        )

        with patch.object(pipeline, "_harvest_and_push", AsyncMock(return_value="error")):
            await pipeline.process_issue(issue, issue_body="Bug description.")

        mock_platform.close_issue.assert_not_awaited()
        mock_platform.assign_label.assert_not_awaited()


# ---------------------------------------------------------------------------
# Engine: af:fixed assigned on supersession and staleness closures
# ---------------------------------------------------------------------------


class TestEngineLabelFixedOnClose:
    """Verify af:fixed label is assigned when engine closes issues."""

    @pytest.mark.asyncio
    async def test_fixed_label_assigned_on_supersession_close(self) -> None:
        """When an issue is closed as superseded, af:fixed label is assigned."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.categories.dependency_freshness = True
        config.night_shift.categories.todo_fixme = False
        config.night_shift.categories.test_coverage = False
        config.night_shift.categories.deprecated_api = False
        config.night_shift.categories.linter_debt = False
        config.night_shift.categories.dead_code = False
        config.night_shift.categories.documentation_drift = False

        issue1 = IssueResult(number=10, title="Issue A", html_url="http://test/10")
        issue2 = IssueResult(number=11, title="Issue B", html_url="http://test/11")
        issue3 = IssueResult(number=12, title="Issue C", html_url="http://test/12")

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[issue1, issue2, issue3])
        mock_platform.close_issue = AsyncMock()
        mock_platform.assign_label = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        # Mock dependencies to produce a supersession pair (keep #10, close #11)
        # Need >= 3 issues for batch triage to run
        with (
            patch("agent_fox.nightshift.engine.parse_text_references", return_value=[]),
            patch("agent_fox.nightshift.engine.fetch_github_relationships", AsyncMock(return_value=[])),
            patch(
                "agent_fox.nightshift.engine.run_batch_triage",
                AsyncMock(return_value=MagicMock(edges=[], supersession_pairs=[(10, 11)])),
            ),
            patch("agent_fox.nightshift.engine.build_graph", return_value=[10, 12]),
            patch.object(engine, "_process_fix", AsyncMock()),
            patch("agent_fox.nightshift.engine.check_staleness", AsyncMock(return_value=MagicMock(obsolete_issues=[]))),
        ):
            await engine._run_issue_check()

        # Issue #11 should have been closed AND had af:fixed assigned
        close_calls = [call.args[0] for call in mock_platform.close_issue.call_args_list]
        assert 11 in close_calls
        mock_platform.assign_label.assert_any_await(11, LABEL_FIXED)

    @pytest.mark.asyncio
    async def test_fixed_label_assigned_on_staleness_close(self) -> None:
        """When an issue is closed as stale after a fix, af:fixed label is assigned."""
        from agent_fox.nightshift.engine import NightShiftEngine

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None
        config.night_shift.categories.dependency_freshness = True
        config.night_shift.categories.todo_fixme = False
        config.night_shift.categories.test_coverage = False
        config.night_shift.categories.deprecated_api = False
        config.night_shift.categories.linter_debt = False
        config.night_shift.categories.dead_code = False
        config.night_shift.categories.documentation_drift = False

        issue1 = IssueResult(number=20, title="Issue A", html_url="http://test/20")
        issue2 = IssueResult(number=21, title="Issue B", html_url="http://test/21")

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=[issue1, issue2])
        mock_platform.close_issue = AsyncMock()
        mock_platform.assign_label = AsyncMock()

        engine = NightShiftEngine(config=config, platform=mock_platform)

        staleness_result = MagicMock(
            obsolete_issues=[21],
            rationale={21: "Resolved by fix for #20"},
        )

        with (
            patch("agent_fox.nightshift.engine.parse_text_references", return_value=[]),
            patch("agent_fox.nightshift.engine.fetch_github_relationships", AsyncMock(return_value=[])),
            patch("agent_fox.nightshift.engine.build_graph", return_value=[20, 21]),
            patch.object(engine, "_process_fix", AsyncMock()),
            patch("agent_fox.nightshift.engine.check_staleness", AsyncMock(return_value=staleness_result)),
        ):
            await engine._run_issue_check()

        # Issue #21 should have been closed AND had af:fixed assigned
        close_calls = [call.args[0] for call in mock_platform.close_issue.call_args_list]
        assert 21 in close_calls
        mock_platform.assign_label.assert_any_await(21, LABEL_FIXED)
