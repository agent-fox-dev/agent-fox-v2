"""Pre-session workspace health check tests for dispatch.

Test Spec: TS-118-10 (pre-session check blocks node on dirty workspace)
Requirements: 118-REQ-4.1, 118-REQ-4.2, 118-REQ-4.3
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from agent_fox.workspace.health import check_workspace_health


class TestPreSessionCheckBlocksOnDirty:
    """TS-118-10: pre-session check blocks node when workspace is dirty.

    Requirements: 118-REQ-4.2
    """

    @pytest.mark.asyncio
    async def test_presession_check_detects_dirty(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Pre-session workspace check detects untracked files that would
        block harvest and returns a report with has_issues=True."""
        # Create untracked files in the workspace
        (tmp_worktree_repo / "leftover.py").write_text("leftover\n")

        report = await check_workspace_health(tmp_worktree_repo)

        assert report.has_issues is True
        assert "leftover.py" in report.untracked_files

    @pytest.mark.asyncio
    async def test_presession_check_passes_clean(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Pre-session workspace check passes for a clean workspace,
        allowing dispatch to proceed."""
        report = await check_workspace_health(tmp_worktree_repo)

        assert report.has_issues is False


class TestPreSessionCheckFailsOpen:
    """TS-118-E5: pre-session check proceeds on git command failure.

    Requirements: 118-REQ-4.E1
    """

    @pytest.mark.asyncio
    async def test_presession_git_error_fails_open(
        self,
        tmp_worktree_repo: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When git commands fail during pre-session check, dispatch proceeds."""
        import logging

        async def failing_run_git(args, **kwargs):
            return (1, "", "fatal: error")

        with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.health"):
            with patch(
                "agent_fox.workspace.health.run_git",
                side_effect=failing_run_git,
            ):
                report = await check_workspace_health(tmp_worktree_repo)

        # Fail-open: report should be clean (no issues detected)
        assert report.has_issues is False
