"""Integration tests for fix pipeline flow.

Test Spec: TS-61-18, TS-61-19, TS-61-E8
Requirements: 61-REQ-6.3, 61-REQ-6.4, 61-REQ-6.E1

Note: TS-61-20 (PR creation) and TS-61-22 (PR link comment) were removed
in spec 65 when create_pr was removed from the platform layer (65-REQ-4.2).
The fix pipeline now posts a completion comment with the branch name
instead of creating a PR.
TS-61-E10 (PR creation failure fallback) is superseded: the pipeline always
posts a branch-name completion comment, so no fallback path exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.workspace import WorkspaceInfo


def _mock_workspace() -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/mock-worktree"),
        branch="fix/test-branch",
        spec_name="fix-issue-42",
        task_group=0,
    )


def _make_issue(number: int = 42, title: str = "Fix unused imports") -> object:
    """Create an IssueResult for testing."""
    from agent_fox.platform.protocol import IssueResult

    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/test/repo/issues/{number}",
    )


# ---------------------------------------------------------------------------
# TS-61-18: Full archetype pipeline for fixes
# Requirement: 61-REQ-6.3
# ---------------------------------------------------------------------------


class TestArchetypePipeline:
    """Verify that fixes use the full archetype pipeline."""

    @pytest.mark.asyncio
    async def test_triage_coder_reviewer_invoked(self) -> None:
        """Session runner is invoked with triage, coder, and reviewer."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.routing.retries_before_escalation = 1
        config.orchestrator.max_retries = 3
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]
        pipeline._harvest_and_push = AsyncMock(return_value="merged")  # type: ignore[method-assign]

        archetypes_used: list[str] = []

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

        async def mock_execute(archetype: str, workspace: object = None, *args: object, **kwargs: object) -> object:
            archetypes_used.append(archetype)
            outcome = MagicMock(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            if archetype == "maintainer":
                outcome.response = triage_response
            elif archetype == "reviewer":
                outcome.response = review_response
            else:
                outcome.response = ""
            return outcome

        with patch.object(pipeline, "_run_session", side_effect=mock_execute):
            issue = _make_issue()
            await pipeline.process_issue(issue, issue_body="Remove unused imports in engine/")  # type: ignore[arg-type]

        assert "maintainer" in archetypes_used
        assert "coder" in archetypes_used
        assert "reviewer" in archetypes_used


# ---------------------------------------------------------------------------
# TS-61-19: Fix progress documented in issue
# Requirement: 61-REQ-6.4
# ---------------------------------------------------------------------------


class TestFixProgressComments:
    """Verify that implementation details are posted as issue comments."""

    @pytest.mark.asyncio
    async def test_comments_posted_during_fix(self) -> None:
        """At least one comment is posted to the issue during the fix."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue()
            await pipeline.process_issue(issue, issue_body="Fix something important")  # type: ignore[arg-type]

        assert mock_platform.add_issue_comment.call_count >= 1


# ---------------------------------------------------------------------------
# Fix completion comment includes branch name
# Validates post-65 behavior: branch name posted instead of PR link
# ---------------------------------------------------------------------------


class TestFixCompletionComment:
    """Verify that on success the branch name appears in a completion comment."""

    @pytest.mark.asyncio
    async def test_branch_name_in_completion_comment(self) -> None:
        """Completion comment contains the fix branch name."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue(number=42, title="Fix unused imports")
            await pipeline.process_issue(issue, issue_body="Fix something")  # type: ignore[arg-type]

        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("fix/" in c for c in comments)


# ---------------------------------------------------------------------------
# TS-61-E8: Fix session failure after retries
# Requirement: 61-REQ-6.E1
# ---------------------------------------------------------------------------


class TestFixSessionFailure:
    """Verify that fix failure results in an issue comment."""

    @pytest.mark.asyncio
    async def test_failure_comment_posted(self) -> None:
        """Comment posted on issue describing the failure."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._setup_workspace = AsyncMock(return_value=_mock_workspace())  # type: ignore[method-assign]
        pipeline._cleanup_workspace = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(side_effect=RuntimeError("session failed")),
        ):
            issue = _make_issue()
            await pipeline.process_issue(issue, issue_body="Fix something")  # type: ignore[arg-type]

        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("fail" in c.lower() for c in comments)
