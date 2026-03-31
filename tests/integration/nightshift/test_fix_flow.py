"""Integration tests for fix pipeline flow.

Test Spec: TS-61-18, TS-61-19, TS-61-20, TS-61-22, TS-61-E8, TS-61-E10
Requirements: 61-REQ-6.3, 61-REQ-6.4, 61-REQ-7.1, 61-REQ-7.3,
              61-REQ-6.E1, 61-REQ-7.E1
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
        mock_platform.create_pr = AsyncMock(
            return_value="https://github.com/test/repo/pull/99"
        )
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        archetypes_used: list[str] = []

        async def mock_execute(
            archetype: str, *args: object, **kwargs: object
        ) -> object:
            archetypes_used.append(archetype)
            return MagicMock(success=True)

        with patch.object(
            pipeline, "_run_session", side_effect=mock_execute
        ):
            issue = _make_issue()
            await pipeline.process_issue(
                issue, issue_body="Remove unused imports in engine/"
            )

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
        mock_platform.create_pr = AsyncMock(
            return_value="https://github.com/test/repo/pull/99"
        )
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue()
            await pipeline.process_issue(
                issue, issue_body="Fix something important"
            )

        assert mock_platform.add_issue_comment.call_count >= 1


# ---------------------------------------------------------------------------
# TS-61-20: PR created on fix success
# Requirement: 61-REQ-7.1
# ---------------------------------------------------------------------------


class TestPRCreation:
    """Verify that one PR is created per successful fix."""

    @pytest.mark.asyncio
    async def test_pr_created_on_success(self) -> None:
        """platform.create_pr() called exactly once on success."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.create_pr = AsyncMock(
            return_value="https://github.com/test/repo/pull/99"
        )
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue()
            await pipeline.process_issue(
                issue, issue_body="Fix something"
            )

        assert mock_platform.create_pr.call_count == 1


# ---------------------------------------------------------------------------
# TS-61-22: Issue comment links to PR
# Requirement: 61-REQ-7.3
# ---------------------------------------------------------------------------


class TestIssueCommentLinksToPR:
    """Verify that a comment with PR link is posted on the issue."""

    @pytest.mark.asyncio
    async def test_pr_link_in_comment(self) -> None:
        """Comment posted containing the PR URL."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.create_pr = AsyncMock(
            return_value="https://github.com/test/repo/pull/99"
        )
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue()
            await pipeline.process_issue(
                issue, issue_body="Fix something"
            )

        comments = [
            str(call) for call in mock_platform.add_issue_comment.call_args_list
        ]
        assert any("pull/99" in c for c in comments)


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

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(side_effect=RuntimeError("session failed")),
        ):
            issue = _make_issue()
            await pipeline.process_issue(
                issue, issue_body="Fix something"
            )

        comments = [
            str(call) for call in mock_platform.add_issue_comment.call_args_list
        ]
        assert any("fail" in c.lower() for c in comments)


# ---------------------------------------------------------------------------
# TS-61-E10: PR creation failure
# Requirement: 61-REQ-7.E1
# ---------------------------------------------------------------------------


class TestPRCreationFailure:
    """Verify fallback when PR creation fails."""

    @pytest.mark.asyncio
    async def test_branch_name_in_comment(self) -> None:
        """Comment posted on issue with branch name for manual PR creation."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.create_pr = AsyncMock(
            side_effect=httpx.HTTPError("API error")
        )
        mock_platform.add_issue_comment = AsyncMock()

        pipeline = FixPipeline(config=config, platform=mock_platform)

        with patch.object(
            pipeline,
            "_run_session",
            AsyncMock(return_value=MagicMock(success=True)),
        ):
            issue = _make_issue()
            await pipeline.process_issue(
                issue, issue_body="Fix something"
            )

        comments = [
            str(call) for call in mock_platform.add_issue_comment.call_args_list
        ]
        assert any("fix/" in c for c in comments)
