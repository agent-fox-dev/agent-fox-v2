"""Tests for GitHubPlatform implementation.

Test Spec: TS-10-7 (create_pr), TS-10-8 (wait_for_ci pass),
           TS-10-9 (wait_for_review approved), TS-10-10 (merge_pr),
           TS-10-E1 (gh not installed), TS-10-E2 (gh not authenticated),
           TS-10-E3 (create_pr fails), TS-10-E4 (CI check failure),
           TS-10-E5 (CI timeout), TS-10-E6 (review rejected),
           TS-10-E7 (merge failure)
Requirements: 10-REQ-3.1, 10-REQ-3.2, 10-REQ-3.3, 10-REQ-3.4, 10-REQ-3.5,
              10-REQ-3.E1, 10-REQ-3.E2, 10-REQ-3.E3, 10-REQ-3.E4,
              10-REQ-3.E5, 10-REQ-3.E6
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import GitHubPlatform

# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestGitHubPlatformCreatePr:
    """TS-10-7: GitHubPlatform.create_pr calls gh pr create.

    Requirement: 10-REQ-3.2
    """

    async def test_returns_pr_url(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """create_pr returns the PR URL from gh stdout."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/owner/repo/pull/42\n",
            stderr="",
        )
        result = await github_platform.create_pr(
            "feature/test",
            "My PR",
            "Body text",
            ["bug", "urgent"],
        )
        assert result == "https://github.com/owner/repo/pull/42"

    async def test_passes_correct_arguments(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """create_pr passes --head, --title, --body, --label to gh."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/owner/repo/pull/42\n",
            stderr="",
        )
        await github_platform.create_pr(
            "feature/test",
            "My PR",
            "Body text",
            ["bug", "urgent"],
        )
        # Find the create call (not the auth status call)
        create_calls = [
            c
            for c in mock_gh_subprocess.call_args_list
            if "pr" in str(c) and "create" in str(c)
        ]
        assert len(create_calls) >= 1
        cmd = create_calls[0][0][0]
        assert "--head" in cmd
        assert "feature/test" in cmd
        assert "--title" in cmd
        assert "--label" in cmd

    async def test_create_pr_no_labels(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """create_pr works with empty labels list."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/owner/repo/pull/1\n",
            stderr="",
        )
        result = await github_platform.create_pr(
            "feature/test",
            "Title",
            "Body",
            [],
        )
        assert result == "https://github.com/owner/repo/pull/1"


class TestGitHubPlatformWaitForCi:
    """TS-10-8: GitHubPlatform.wait_for_ci returns True when all checks pass.

    Requirement: 10-REQ-3.3
    """

    async def test_returns_true_when_all_pass(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_ci returns True when all checks report success."""
        checks = [
            {"name": "build", "state": "completed", "conclusion": "success"},
            {"name": "lint", "state": "completed", "conclusion": "success"},
        ]
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(checks),
            stderr="",
        )
        result = await github_platform.wait_for_ci(
            "https://github.com/owner/repo/pull/42",
            600,
        )
        assert result is True

    async def test_returns_true_when_skipped(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_ci returns True when checks are skipped/neutral."""
        checks = [
            {"name": "build", "state": "completed", "conclusion": "success"},
            {"name": "optional", "state": "completed", "conclusion": "skipped"},
        ]
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(checks),
            stderr="",
        )
        result = await github_platform.wait_for_ci(
            "https://github.com/owner/repo/pull/42",
            600,
        )
        assert result is True

    async def test_returns_true_when_no_checks(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_ci returns True when no checks are configured."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps([]),
            stderr="",
        )
        result = await github_platform.wait_for_ci(
            "https://github.com/owner/repo/pull/42",
            600,
        )
        assert result is True


class TestGitHubPlatformWaitForReview:
    """TS-10-9: GitHubPlatform.wait_for_review returns True when approved.

    Requirement: 10-REQ-3.4
    """

    async def test_returns_true_when_approved(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_review returns True when reviewDecision is APPROVED."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"reviewDecision": "APPROVED"}),
            stderr="",
        )
        result = await github_platform.wait_for_review(
            "https://github.com/owner/repo/pull/42",
        )
        assert result is True


class TestGitHubPlatformMergePr:
    """TS-10-10: GitHubPlatform.merge_pr calls gh pr merge.

    Requirement: 10-REQ-3.5
    """

    async def test_calls_gh_merge(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """merge_pr calls gh pr merge with --merge flag."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        pr_url = "https://github.com/owner/repo/pull/42"
        await github_platform.merge_pr(pr_url)
        merge_calls = [
            c for c in mock_gh_subprocess.call_args_list if "merge" in str(c)
        ]
        assert len(merge_calls) >= 1
        cmd = merge_calls[0][0][0]
        assert "gh" in cmd
        assert "merge" in cmd
        assert pr_url in cmd
        assert "--merge" in cmd

    async def test_merge_succeeds_without_exception(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """merge_pr does not raise on success."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        result = await github_platform.merge_pr(
            "https://github.com/owner/repo/pull/42",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestGitHubPlatformGhNotInstalled:
    """TS-10-E1: GitHubPlatform raises when gh not installed.

    Requirement: 10-REQ-3.E1
    """

    def test_raises_integration_error(self) -> None:
        """GitHubPlatform raises IntegrationError when gh is not found."""
        with patch(
            "agent_fox.platform.github.shutil.which",
            return_value=None,
        ):
            with pytest.raises(IntegrationError, match="gh"):
                GitHubPlatform()


class TestGitHubPlatformGhNotAuthenticated:
    """TS-10-E2: GitHubPlatform raises when gh not authenticated.

    Requirement: 10-REQ-3.E1
    """

    def test_raises_integration_error(self) -> None:
        """GitHubPlatform raises IntegrationError when gh auth fails."""
        with (
            patch(
                "agent_fox.platform.github.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "agent_fox.platform.github.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[],
                    returncode=1,
                    stdout="",
                    stderr="not logged in",
                ),
            ),
        ):
            with pytest.raises(IntegrationError, match="auth"):
                GitHubPlatform()


class TestGitHubPlatformCreatePrFailure:
    """TS-10-E3: GitHubPlatform.create_pr raises on gh failure.

    Requirement: 10-REQ-3.E2
    """

    async def test_raises_on_create_failure(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """create_pr raises IntegrationError when gh pr create fails."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="no permission",
        )
        with pytest.raises(IntegrationError, match="no permission"):
            await github_platform.create_pr(
                "feature/test",
                "Title",
                "Body",
                [],
            )


class TestGitHubPlatformCiCheckFailure:
    """TS-10-E4: GitHubPlatform.wait_for_ci returns False on check failure.

    Requirement: 10-REQ-3.E3
    """

    async def test_returns_false_on_failure(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_ci returns False when a CI check fails."""
        checks = [
            {"name": "build", "state": "completed", "conclusion": "failure"},
        ]
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(checks),
            stderr="",
        )
        result = await github_platform.wait_for_ci(
            "https://github.com/owner/repo/pull/42",
            600,
        )
        assert result is False


class TestGitHubPlatformCiTimeout:
    """TS-10-E5: GitHubPlatform.wait_for_ci returns False on timeout.

    Requirement: 10-REQ-3.E4
    """

    async def test_returns_false_on_timeout(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_ci returns False when timeout expires."""
        checks = [
            {"name": "build", "state": "in_progress", "conclusion": ""},
        ]
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(checks),
            stderr="",
        )
        with patch("agent_fox.platform.github._CI_POLL_INTERVAL", 0):
            result = await github_platform.wait_for_ci(
                "https://github.com/owner/repo/pull/42",
                1,
            )
        assert result is False


class TestGitHubPlatformReviewRejected:
    """TS-10-E6: GitHubPlatform.wait_for_review returns False on changes requested.

    Requirement: 10-REQ-3.E5
    """

    async def test_returns_false_on_changes_requested(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """wait_for_review returns False when changes are requested."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"reviewDecision": "CHANGES_REQUESTED"}),
            stderr="",
        )
        result = await github_platform.wait_for_review(
            "https://github.com/owner/repo/pull/42",
        )
        assert result is False


class TestGitHubPlatformMergeFailure:
    """TS-10-E7: GitHubPlatform.merge_pr raises on merge failure.

    Requirement: 10-REQ-3.E6
    """

    async def test_raises_on_merge_failure(
        self,
        github_platform: GitHubPlatform,
        mock_gh_subprocess: MagicMock,
    ) -> None:
        """merge_pr raises IntegrationError when gh pr merge fails."""
        mock_gh_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="merge conflict",
        )
        with pytest.raises(IntegrationError, match="merge conflict"):
            await github_platform.merge_pr(
                "https://github.com/owner/repo/pull/42",
            )
