"""Tests for GitHub issue search-before-create idempotency (REST API).

Test Spec: TS-28-7 through TS-28-10, TS-28-12, TS-28-E4, TS-28-E5
Requirements: 28-REQ-5.*, 28-REQ-6.1
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import IssueResult
from agent_fox.session.github_issues import file_or_update_issue


def _mock_platform(
    search_results: list[IssueResult] | None = None,
    search_side_effect: Exception | None = None,
    create_result: IssueResult | None = None,
    create_side_effect: Exception | None = None,
) -> AsyncMock:
    """Build a mock GitHubPlatform with preset return values."""
    platform = AsyncMock()
    if search_side_effect:
        platform.search_issues.side_effect = search_side_effect
    else:
        platform.search_issues.return_value = search_results or []
    if create_side_effect:
        platform.create_issue.side_effect = create_side_effect
    elif create_result:
        platform.create_issue.return_value = create_result
    else:
        platform.create_issue.return_value = IssueResult(
            number=1, title="title", html_url="https://github.com/o/r/issues/1"
        )
    platform.update_issue.return_value = None
    platform.add_issue_comment.return_value = None
    platform.close_issue.return_value = None
    return platform


# ---------------------------------------------------------------------------
# TS-28-7: file_or_update_issue Creates New Issue
# Requirements: 28-REQ-5.2, 28-REQ-5.3
# ---------------------------------------------------------------------------


class TestFileOrUpdateIssueCreate:
    """Verify file_or_update_issue creates a new issue when none exists."""

    @pytest.mark.asyncio
    async def test_creates_when_no_existing(self) -> None:
        mock = _mock_platform(
            search_results=[],
            create_result=IssueResult(
                number=1,
                title="[Skeptic] spec",
                html_url="https://github.com/o/r/issues/1",
            ),
        )

        result = await file_or_update_issue("[Skeptic] spec", "findings", platform=mock)

        assert result == "https://github.com/o/r/issues/1"
        mock.search_issues.assert_called_once()
        mock.create_issue.assert_called_once()
        mock.update_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-28-8: file_or_update_issue Updates Existing Issue
# Requirements: 28-REQ-5.2, 28-REQ-5.3
# ---------------------------------------------------------------------------


class TestFileOrUpdateIssueUpdate:
    """Verify file_or_update_issue updates existing issue."""

    @pytest.mark.asyncio
    async def test_updates_when_existing(self) -> None:
        existing = IssueResult(
            number=42,
            title="[Skeptic] spec",
            html_url="https://github.com/o/r/issues/42",
        )
        mock = _mock_platform(search_results=[existing])

        result = await file_or_update_issue("[Skeptic] spec", "updated", platform=mock)

        assert result == "https://github.com/o/r/issues/42"
        mock.update_issue.assert_called_once_with(42, "updated")
        mock.add_issue_comment.assert_called_once()
        mock.create_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-28-9: file_or_update_issue Closes When Empty
# Requirement: 28-REQ-5.3
# ---------------------------------------------------------------------------


class TestFileOrUpdateIssueClose:
    """Verify close-if-empty behavior."""

    @pytest.mark.asyncio
    async def test_closes_when_empty_body(self) -> None:
        existing = IssueResult(
            number=42,
            title="[Skeptic] spec",
            html_url="https://github.com/o/r/issues/42",
        )
        mock = _mock_platform(search_results=[existing])

        result = await file_or_update_issue(
            "[Skeptic] spec", "", platform=mock, close_if_empty=True
        )

        mock.close_issue.assert_called_once()
        assert result is None


# ---------------------------------------------------------------------------
# TS-28-10: No gh CLI References in Module
# Requirement: 28-REQ-5.4
# ---------------------------------------------------------------------------


class TestNoGhCliReferences:
    """Verify github_issues.py contains no gh CLI references."""

    def test_no_subprocess_imports(self) -> None:
        source_path = (
            Path(__file__).resolve().parents[3]
            / "agent_fox"
            / "session"
            / "github_issues.py"
        )
        content = source_path.read_text()
        assert "create_subprocess_exec" not in content
        assert "_run_gh_command" not in content


# ---------------------------------------------------------------------------
# TS-28-E4: file_or_update_issue Platform None
# Requirement: 28-REQ-5.E1
# ---------------------------------------------------------------------------


class TestPlatformNone:
    """Verify file_or_update_issue returns None when platform is None."""

    @pytest.mark.asyncio
    async def test_returns_none_with_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING):
            result = await file_or_update_issue("[Skeptic] spec", "body", platform=None)

        assert result is None
        assert any("warning" in r.levelname.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-28-E5: file_or_update_issue API Error Swallowed
# Requirement: 28-REQ-5.E2
# ---------------------------------------------------------------------------


class TestApiErrorSwallowed:
    """Verify file_or_update_issue catches IntegrationError."""

    @pytest.mark.asyncio
    async def test_search_error_returns_none(self) -> None:
        mock = _mock_platform(
            search_side_effect=IntegrationError("API error"),
        )

        result = await file_or_update_issue("[Skeptic] spec", "body", platform=mock)

        assert result is None

    @pytest.mark.asyncio
    async def test_create_error_returns_none(self) -> None:
        mock = _mock_platform(
            search_results=[],
            create_side_effect=IntegrationError("create failed"),
        )

        result = await file_or_update_issue("[Skeptic] spec", "body", platform=mock)

        assert result is None


# ---------------------------------------------------------------------------
# TS-28-12: Errata Document Exists
# Requirement: 28-REQ-6.1
# ---------------------------------------------------------------------------


class TestErrataExists:
    """Verify errata document exists and references correct requirements."""

    def test_errata_file_exists_with_correct_content(self) -> None:
        errata_path = (
            Path(__file__).resolve().parents[3]
            / "docs"
            / "errata"
            / "28_github_issue_rest_api.md"
        )
        assert errata_path.exists(), f"Errata file not found: {errata_path}"
        content = errata_path.read_text()
        assert "26-REQ-10.1" in content
        assert "26-REQ-10.2" in content
        assert "26-REQ-10.3" in content
        assert "26-REQ-10.E1" in content
        assert "REST API" in content
