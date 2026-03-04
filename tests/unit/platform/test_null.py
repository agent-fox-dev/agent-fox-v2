"""Tests for NullPlatform implementation.

Test Spec: TS-10-3 (create_pr merges), TS-10-4 (wait_for_ci),
           TS-10-5 (wait_for_review), TS-10-6 (merge_pr no-op),
           TS-10-E9 (merge conflict)
Requirements: 10-REQ-2.2, 10-REQ-2.3, 10-REQ-2.4, 10-REQ-2.5
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.null import NullPlatform


class TestNullPlatformCreatePr:
    """TS-10-3: NullPlatform.create_pr merges directly and returns empty string.

    Requirement: 10-REQ-2.2
    """

    async def test_returns_empty_string(
        self,
        null_platform: NullPlatform,
        mock_subprocess: MagicMock,
    ) -> None:
        """create_pr returns an empty string (no PR URL)."""
        result = await null_platform.create_pr(
            "feature/test",
            "Title",
            "Body",
            ["label"],
        )
        assert result == ""

    async def test_calls_git_checkout_develop(
        self,
        null_platform: NullPlatform,
        mock_subprocess: MagicMock,
    ) -> None:
        """create_pr calls git checkout develop."""
        await null_platform.create_pr("feature/test", "Title", "Body", [])
        calls = mock_subprocess.call_args_list
        checkout_call = calls[0]
        assert checkout_call[0][0] == ["git", "checkout", "develop"]

    async def test_calls_git_merge_no_ff(
        self,
        null_platform: NullPlatform,
        mock_subprocess: MagicMock,
    ) -> None:
        """create_pr calls git merge --no-ff with the branch name."""
        await null_platform.create_pr("feature/test", "Title", "Body", [])
        calls = mock_subprocess.call_args_list
        merge_call = calls[1]
        assert merge_call[0][0] == ["git", "merge", "--no-ff", "feature/test"]


class TestNullPlatformWaitForCi:
    """TS-10-4: NullPlatform.wait_for_ci returns True immediately.

    Requirement: 10-REQ-2.3
    """

    async def test_returns_true(self, null_platform: NullPlatform) -> None:
        """wait_for_ci always returns True."""
        result = await null_platform.wait_for_ci("", 600)
        assert result is True

    async def test_returns_true_with_any_timeout(
        self,
        null_platform: NullPlatform,
    ) -> None:
        """wait_for_ci returns True regardless of timeout value."""
        result = await null_platform.wait_for_ci("", 0)
        assert result is True


class TestNullPlatformWaitForReview:
    """TS-10-5: NullPlatform.wait_for_review returns True immediately.

    Requirement: 10-REQ-2.4
    """

    async def test_returns_true(self, null_platform: NullPlatform) -> None:
        """wait_for_review always returns True."""
        result = await null_platform.wait_for_review("")
        assert result is True


class TestNullPlatformMergePr:
    """TS-10-6: NullPlatform.merge_pr is a no-op.

    Requirement: 10-REQ-2.5
    """

    async def test_returns_none(self, null_platform: NullPlatform) -> None:
        """merge_pr returns None."""
        result = await null_platform.merge_pr("")
        assert result is None


class TestNullPlatformMergeConflict:
    """TS-10-E9: NullPlatform.create_pr raises on merge conflict.

    Requirement: 10-REQ-2.2
    """

    async def test_raises_on_merge_failure(
        self,
        null_platform: NullPlatform,
        mock_subprocess: MagicMock,
    ) -> None:
        """create_pr raises IntegrationError when git merge fails."""

        def _side_effect(args, **kwargs):
            if args[0:2] == ["git", "merge"]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=1,
                    stdout="",
                    stderr="CONFLICT",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="",
                stderr="",
            )

        mock_subprocess.side_effect = _side_effect

        with pytest.raises(IntegrationError, match="feature/conflict"):
            await null_platform.create_pr(
                "feature/conflict",
                "Title",
                "Body",
                [],
            )

    async def test_raises_on_checkout_failure(
        self,
        null_platform: NullPlatform,
        mock_subprocess: MagicMock,
    ) -> None:
        """create_pr raises IntegrationError when git checkout fails."""
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="error: pathspec",
        )

        with pytest.raises(IntegrationError, match="develop"):
            await null_platform.create_pr(
                "feature/test",
                "Title",
                "Body",
                [],
            )
