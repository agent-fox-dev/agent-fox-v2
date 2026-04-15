"""Unit tests for staleness check logic.

Covers issue #228: check_staleness must close issues that the AI says are
obsolete AND that GitHub confirms are still open — not issues that are already
closed externally.

Requirements: 71-REQ-5.1, 71-REQ-5.2, 71-REQ-5.E1, 71-REQ-5.E2
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Response parser (unchanged, just regression coverage)
# ---------------------------------------------------------------------------


class TestParseStatenessResponse:
    """_parse_staleness_response extracts obsolete issue numbers correctly."""

    def test_parses_valid_json(self) -> None:
        """Parses a clean JSON response."""
        from agent_fox.nightshift.staleness import _parse_staleness_response
        from agent_fox.platform.protocol import IssueResult

        remaining = [
            IssueResult(number=10, title="A", html_url="", body=""),
            IssueResult(number=20, title="B", html_url="", body=""),
        ]
        response = '{"obsolete": [{"issue_number": 10, "rationale": "resolved"}]}'
        result = _parse_staleness_response(response, remaining)
        assert result.obsolete_issues == [10]
        assert result.rationale[10] == "resolved"

    def test_ignores_unknown_issue_numbers(self) -> None:
        """Issue numbers not in remaining list are silently dropped."""
        from agent_fox.nightshift.staleness import _parse_staleness_response
        from agent_fox.platform.protocol import IssueResult

        remaining = [IssueResult(number=10, title="A", html_url="", body="")]
        response = '{"obsolete": [{"issue_number": 99, "rationale": "?"}]}'
        result = _parse_staleness_response(response, remaining)
        assert result.obsolete_issues == []


# ---------------------------------------------------------------------------
# Issue #228: corrected gate logic in check_staleness
# ---------------------------------------------------------------------------


class TestCheckStalenessGateLogic:
    """check_staleness closes issues AI says are obsolete AND still open on GitHub."""

    @pytest.mark.asyncio
    async def test_ai_obsolete_and_still_open_is_returned(self) -> None:
        """Issue flagged by AI that is still open → included in obsolete list."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.staleness import StalenessResult, check_staleness
        from agent_fox.platform.protocol import IssueResult

        fixed = IssueResult(number=1, title="Fixed", html_url="", body="")
        remaining = [IssueResult(number=2, title="Remaining", html_url="", body="")]

        mock_platform = AsyncMock()
        # GitHub says issue 2 is still open
        mock_platform.list_issues_by_label = AsyncMock(
            return_value=[IssueResult(number=2, title="Remaining", html_url="", body="")]
        )

        config = MagicMock()

        # AI says issue 2 is obsolete
        ai_result = StalenessResult(obsolete_issues=[2], rationale={2: "fixed by issue 1"})

        with patch(
            "agent_fox.nightshift.staleness._run_ai_staleness",
            AsyncMock(return_value=ai_result),
        ):
            result = await check_staleness(fixed, remaining, "", config, mock_platform)

        assert 2 in result.obsolete_issues
        assert result.rationale[2] == "fixed by issue 1"

    @pytest.mark.asyncio
    async def test_ai_obsolete_but_already_closed_is_not_returned(self) -> None:
        """Issue flagged by AI that is already closed → NOT in obsolete list.

        close_issue() should not be called on an already-closed issue.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.staleness import StalenessResult, check_staleness
        from agent_fox.platform.protocol import IssueResult

        fixed = IssueResult(number=1, title="Fixed", html_url="", body="")
        remaining = [IssueResult(number=2, title="Remaining", html_url="", body="")]

        mock_platform = AsyncMock()
        # GitHub says issue 2 is already closed (not in open list)
        mock_platform.list_issues_by_label = AsyncMock(return_value=[])

        config = MagicMock()

        ai_result = StalenessResult(obsolete_issues=[2], rationale={2: "fixed by issue 1"})

        with patch(
            "agent_fox.nightshift.staleness._run_ai_staleness",
            AsyncMock(return_value=ai_result),
        ):
            result = await check_staleness(fixed, remaining, "", config, mock_platform)

        assert 2 not in result.obsolete_issues

    @pytest.mark.asyncio
    async def test_ai_failure_returns_empty(self) -> None:
        """When AI call fails, no issues are closed (71-REQ-5.E1)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.staleness import check_staleness
        from agent_fox.platform.protocol import IssueResult

        fixed = IssueResult(number=1, title="Fixed", html_url="", body="")
        remaining = [IssueResult(number=2, title="Remaining", html_url="", body="")]

        mock_platform = AsyncMock()
        # Issue 2 still open on GitHub
        mock_platform.list_issues_by_label = AsyncMock(
            return_value=[IssueResult(number=2, title="Remaining", html_url="", body="")]
        )

        config = MagicMock()

        with patch(
            "agent_fox.nightshift.staleness._run_ai_staleness",
            AsyncMock(side_effect=RuntimeError("AI unavailable")),
        ):
            result = await check_staleness(fixed, remaining, "", config, mock_platform)

        # Without AI, we cannot know what to close
        assert result.obsolete_issues == []

    @pytest.mark.asyncio
    async def test_github_failure_returns_empty(self) -> None:
        """When GitHub re-fetch fails, return empty (71-REQ-5.E2)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.nightshift.staleness import StalenessResult, check_staleness
        from agent_fox.platform.protocol import IssueResult

        fixed = IssueResult(number=1, title="Fixed", html_url="", body="")
        remaining = [IssueResult(number=2, title="Remaining", html_url="", body="")]

        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(side_effect=RuntimeError("GitHub unavailable"))

        config = MagicMock()
        ai_result = StalenessResult(obsolete_issues=[2], rationale={2: "fixed"})

        with patch(
            "agent_fox.nightshift.staleness._run_ai_staleness",
            AsyncMock(return_value=ai_result),
        ):
            result = await check_staleness(fixed, remaining, "", config, mock_platform)

        assert result.obsolete_issues == []
