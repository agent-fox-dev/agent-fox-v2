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

import pytest


def _make_issue(number: int = 42, title: str = "Fix unused imports") -> object:
    """Create an IssueResult for testing."""
    from agent_fox.platform.github import IssueResult

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
    async def test_skeptic_coder_verifier_invoked(self) -> None:
        """Session runner is invoked with skeptic, coder, and verifier."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        archetypes_used: list[str] = []

        async def mock_execute(archetype: str, *args: object, **kwargs: object) -> object:
            archetypes_used.append(archetype)
            return MagicMock(success=True)

        with patch.object(pipeline, "_run_session", side_effect=mock_execute):
            issue = _make_issue()
            await pipeline.process_issue(issue, issue_body="Remove unused imports in engine/")

        assert "skeptic" in archetypes_used
        assert "coder" in archetypes_used
        assert "verifier" in archetypes_used


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
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue()
            await pipeline.process_issue(issue, issue_body="Fix something important")

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
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue(number=42, title="Fix unused imports")
            await pipeline.process_issue(issue, issue_body="Fix something")

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
        pipeline._create_fix_branch = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(side_effect=RuntimeError("session failed")),
        ):
            issue = _make_issue()
            await pipeline.process_issue(issue, issue_body="Fix something")

        comments = [str(call) for call in mock_platform.add_issue_comment.call_args_list]
        assert any("fail" in c.lower() for c in comments)
