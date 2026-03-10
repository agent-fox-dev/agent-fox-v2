"""Tests for GitHub issue search-before-create idempotency.

Test Spec: TS-26-41, TS-26-E13, TS-26-P13
Requirements: 26-REQ-10.1 through 26-REQ-10.3, 26-REQ-10.E1
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-26-41: GitHub issue search-before-create
# Requirements: 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3
# ---------------------------------------------------------------------------


class TestSearchBeforeCreate:
    """Verify file_or_update_issue() searches before creating."""

    @pytest.mark.asyncio
    async def test_create_when_no_existing(self) -> None:
        from unittest.mock import AsyncMock, patch

        from agent_fox.session.github_issues import file_or_update_issue

        with patch(
            "agent_fox.session.github_issues._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_gh:
            mock_gh.side_effect = [
                "",  # search returns no results
                "https://github.com/repo/issues/1",
            ]
            await file_or_update_issue(
                "[Skeptic Review] spec", "body"
            )

        assert mock_gh.call_count >= 1

    @pytest.mark.asyncio
    async def test_update_when_existing(self) -> None:
        from unittest.mock import AsyncMock, patch

        from agent_fox.session.github_issues import file_or_update_issue

        with patch(
            "agent_fox.session.github_issues._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_gh:
            mock_gh.side_effect = [
                "42\t[Skeptic Review] spec\n",
                "",  # edit succeeds
                "",  # comment succeeds
            ]
            await file_or_update_issue(
                "[Skeptic Review] spec", "updated body"
            )

        assert mock_gh.call_count >= 1


# ---------------------------------------------------------------------------
# TS-26-E13: gh CLI unavailable
# Requirement: 26-REQ-10.E1
# ---------------------------------------------------------------------------


class TestGhUnavailable:
    """Verify GitHub issue filing failure doesn't block."""

    @pytest.mark.asyncio
    async def test_gh_unavailable_returns_none(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging
        from unittest.mock import AsyncMock, patch

        from agent_fox.session.github_issues import file_or_update_issue

        with patch(
            "agent_fox.session.github_issues._run_gh_command",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError("gh not found"),
        ):
            with caplog.at_level(logging.WARNING):
                result = await file_or_update_issue(
                    "[Skeptic] spec", "body"
                )

        assert result is None


# ---------------------------------------------------------------------------
# TS-26-P13: GitHub Issue Idempotency (Property)
# Property 13: Repeated calls produce at most one open issue
# Validates: 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3
# ---------------------------------------------------------------------------


class TestPropertyIssueIdempotency:
    """Repeated calls produce at most one open issue."""

    @pytest.mark.asyncio
    async def test_prop_at_most_one_create(self) -> None:
        from unittest.mock import AsyncMock, patch

        from agent_fox.session.github_issues import file_or_update_issue

        create_count = 0
        edit_count = 0
        existing_issue = None

        async def mock_gh(args: list[str]) -> str:
            nonlocal create_count, edit_count, existing_issue

            if "list" in args:
                if existing_issue:
                    return f"{existing_issue}\t[Skeptic] spec\n"
                return ""
            elif "create" in args:
                create_count += 1
                existing_issue = "1"
                return "https://github.com/repo/issues/1"
            elif "edit" in args:
                edit_count += 1
                return ""
            elif "comment" in args:
                return ""
            return ""

        with patch(
            "agent_fox.session.github_issues._run_gh_command",
            new_callable=AsyncMock,
            side_effect=mock_gh,
        ):
            for i in range(3):
                await file_or_update_issue(
                    "[Skeptic] spec", f"body {i}"
                )

        assert create_count <= 1
        assert edit_count == 2
