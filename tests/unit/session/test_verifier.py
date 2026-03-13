"""Tests for Verifier archetype behavior.

Test Spec: TS-26-37, TS-26-38
Requirements: 26-REQ-9.1, 26-REQ-9.2
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-26-37: Verifier produces verification.md
# Requirement: 26-REQ-9.1
# ---------------------------------------------------------------------------


class TestVerifierTemplate:
    """Verify Verifier template references per-requirement verdict and JSON output."""

    def test_template_has_verdict_and_assessment(self) -> None:
        import os

        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "agent_fox",
            "_templates",
            "prompts",
            "verifier.md",
        )
        template_path = os.path.normpath(template_path)

        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        assert "PASS" in content
        assert "FAIL" in content
        assert "verdicts" in content


# ---------------------------------------------------------------------------
# TS-26-38: Verifier files GitHub issue on FAIL
# Requirement: 26-REQ-9.2
# ---------------------------------------------------------------------------


class TestVerifierGithubIssue:
    """Verify Verifier files a GitHub issue when verdict is FAIL."""

    @pytest.mark.asyncio
    async def test_verifier_files_issue_on_fail(self) -> None:
        from unittest.mock import AsyncMock

        from agent_fox.platform.github import IssueResult
        from agent_fox.session.github_issues import file_or_update_issue

        mock_platform = AsyncMock()
        mock_platform.search_issues.return_value = []
        mock_platform.create_issue.return_value = IssueResult(
            number=5,
            title="[Verifier] 05_memory group 2: FAIL",
            html_url="https://github.com/repo/issues/5",
        )

        result = await file_or_update_issue(
            "[Verifier] 05_memory group 2: FAIL",
            "## Verdict: FAIL\n- Test failures found",
            platform=mock_platform,
        )

        assert result == "https://github.com/repo/issues/5"
        mock_platform.create_issue.assert_called_once()
        # Verify title passed correctly
        call_args = mock_platform.create_issue.call_args
        assert "[Verifier] 05_memory group 2: FAIL" in call_args[0][0]
