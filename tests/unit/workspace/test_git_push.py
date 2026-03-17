"""Tests for push_to_remote git function.

Test Spec: TS-19-6 (push success), TS-19-7 (push failure returns False)
Requirements: 19-REQ-3.1, 19-REQ-3.E1
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from agent_fox.workspace.workspace import push_to_remote

# ---------------------------------------------------------------------------
# TS-19-6: push_to_remote Success
# ---------------------------------------------------------------------------


class TestPushToRemoteSuccess:
    """TS-19-6: push_to_remote calls git push and returns True on success.

    Requirement: 19-REQ-3.1
    """

    async def test_returns_true(self, tmp_path: Path) -> None:
        """push_to_remote returns True on successful push."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            return 0, "", ""

        with patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git):
            result = await push_to_remote(tmp_path, "develop")

        assert result is True
        push_calls = [c for c in calls if "push" in c]
        assert len(push_calls) == 1
        assert push_calls[0] == ["push", "origin", "develop"]

    async def test_custom_remote(self, tmp_path: Path) -> None:
        """push_to_remote uses the specified remote name."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            return 0, "", ""

        with patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git):
            result = await push_to_remote(tmp_path, "develop", remote="upstream")

        assert result is True
        push_calls = [c for c in calls if "push" in c]
        assert push_calls[0] == ["push", "upstream", "develop"]


# ---------------------------------------------------------------------------
# TS-19-7: push_to_remote Failure Returns False
# ---------------------------------------------------------------------------


class TestPushToRemoteFailure:
    """TS-19-7: push_to_remote logs a warning and returns False on failure.

    Requirement: 19-REQ-3.E1
    """

    async def test_returns_false(self, tmp_path: Path) -> None:
        """push_to_remote returns False when git push fails."""

        async def mock_run_git(args, cwd, check=True):
            return 1, "", "permission denied"

        with patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git):
            result = await push_to_remote(tmp_path, "develop")

        assert result is False

    async def test_logs_warning(self, tmp_path: Path, caplog) -> None:
        """push_to_remote logs a warning on failure."""

        async def mock_run_git(args, cwd, check=True):
            return 1, "", "permission denied"

        with patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git):
            with caplog.at_level(logging.WARNING):
                await push_to_remote(tmp_path, "develop")

        assert any("push" in r.message.lower() for r in caplog.records)
