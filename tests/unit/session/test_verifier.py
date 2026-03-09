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
    """Verify Verifier template references per-requirement assessment and verdict."""

    def test_template_has_verdict_and_assessment(self) -> None:
        import os

        template_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "agent_fox", "_templates", "prompts", "verifier.md",
        )
        template_path = os.path.normpath(template_path)

        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        assert "PASS" in content
        assert "FAIL" in content
        assert "verification.md" in content


# ---------------------------------------------------------------------------
# TS-26-38: Verifier files GitHub issue on FAIL
# Requirement: 26-REQ-9.2
# ---------------------------------------------------------------------------


class TestVerifierGithubIssue:
    """Verify Verifier files a GitHub issue when verdict is FAIL."""

    @pytest.mark.asyncio
    async def test_verifier_files_issue_on_fail(self) -> None:
        from unittest.mock import AsyncMock, patch

        from agent_fox.session.github_issues import file_or_update_issue

        with patch(
            "agent_fox.session.github_issues._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_gh:
            mock_gh.side_effect = [
                "",  # search returns no results
                "https://github.com/repo/issues/5",  # create returns URL
            ]
            result = await file_or_update_issue(
                "[Verifier] 05_memory group 2: FAIL",
                "## Verdict: FAIL\n- Test failures found",
            )

        assert result is not None
        # Verify create was called with correct title
        create_call = mock_gh.call_args_list[1]
        create_args = create_call[0][0]
        assert "create" in create_args
        # The title should contain the verifier prefix
        title_idx = create_args.index("--title")
        assert "[Verifier] 05_memory group 2: FAIL" in create_args[title_idx + 1]
