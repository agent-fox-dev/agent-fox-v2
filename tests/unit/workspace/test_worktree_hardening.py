"""Unit tests for worktree cleanup hardening.

Test Spec: TS-80-1, TS-80-2, TS-80-5, TS-80-6, TS-80-7, TS-80-9, TS-80-10,
           TS-80-E2, TS-80-E3, TS-80-E4
Requirements: 80-REQ-1.3, 80-REQ-1.E1, 80-REQ-1.E2, 80-REQ-2.1, 80-REQ-2.2,
              80-REQ-3.1, 80-REQ-3.E1, 80-REQ-3.E2
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_fox.core.errors import WorkspaceError
from agent_fox.workspace import WorkspaceInfo

# ---------------------------------------------------------------------------
# TS-80-1: branch_used_by_worktree returns True when referenced
# Requirement: 80-REQ-1.3
# ---------------------------------------------------------------------------


class TestBranchUsedByWorktree:
    """TS-80-1, TS-80-2, TS-80-10: Porcelain output parsing."""

    _PORCELAIN_WITH_FEATURE = (
        "worktree /repo\n"
        "HEAD abc123\n"
        "branch refs/heads/develop\n"
        "\n"
        "worktree /repo/.agent-fox/worktrees/spec/0\n"
        "HEAD def456\n"
        "branch refs/heads/feature/spec/0\n"
        "\n"
    )

    _PORCELAIN_DEVELOP_ONLY = (
        "worktree /repo\n"
        "HEAD abc123\n"
        "branch refs/heads/develop\n"
        "\n"
    )

    @pytest.mark.asyncio
    async def test_returns_true_when_branch_referenced(
        self, tmp_path: Path
    ) -> None:
        """TS-80-1: Returns True when branch appears in porcelain branch line."""
        from agent_fox.workspace.git import branch_used_by_worktree

        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(0, self._PORCELAIN_WITH_FEATURE, ""),
        ):
            result = await branch_used_by_worktree(tmp_path, "feature/spec/0")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_branch_not_referenced(
        self, tmp_path: Path
    ) -> None:
        """TS-80-2: Returns False when branch not in porcelain output."""
        from agent_fox.workspace.git import branch_used_by_worktree

        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(0, self._PORCELAIN_DEVELOP_ONLY, ""),
        ):
            result = await branch_used_by_worktree(tmp_path, "feature/other/1")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_porcelain_command_fails(
        self, tmp_path: Path
    ) -> None:
        """TS-80-10: Optimistic fallback: returns False on command failure."""
        from agent_fox.workspace.git import branch_used_by_worktree

        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            side_effect=WorkspaceError("git worktree list failed"),
        ):
            result = await branch_used_by_worktree(tmp_path, "feature/spec/0")

        # Optimistic fallback: return False so caller proceeds
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_detached_head_worktrees(
        self, tmp_path: Path
    ) -> None:
        """Detached HEAD worktrees have no branch line — should not match."""
        from agent_fox.workspace.git import branch_used_by_worktree

        porcelain_detached = (
            "worktree /repo\n"
            "HEAD abc123\n"
            "branch refs/heads/develop\n"
            "\n"
            "worktree /repo/.agent-fox/worktrees/spec/0\n"
            "HEAD def456\n"
            "detached\n"
            "\n"
        )
        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(0, porcelain_detached, ""),
        ):
            result = await branch_used_by_worktree(tmp_path, "feature/spec/0")

        assert result is False

    @pytest.mark.asyncio
    async def test_does_not_match_partial_branch_names(
        self, tmp_path: Path
    ) -> None:
        """Branch name must match fully — not as a substring."""
        from agent_fox.workspace.git import branch_used_by_worktree

        # The porcelain has feature/spec/0 but we're looking for feature/spec
        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(0, self._PORCELAIN_WITH_FEATURE, ""),
        ):
            result = await branch_used_by_worktree(tmp_path, "feature/spec")

        assert result is False


# ---------------------------------------------------------------------------
# TS-80-5, TS-80-6: delete_branch self-healing
# Requirements: 80-REQ-2.1, 80-REQ-2.2
# ---------------------------------------------------------------------------


class TestDeleteBranchSelfHealing:
    """TS-80-5, TS-80-6: delete_branch prunes and retries on stale worktree error."""

    # Error message git emits when a branch is locked by a worktree
    _USED_BY_WORKTREE_STDERR = (
        "error: Cannot delete branch 'feature/spec/0' "
        "used by worktree at '/nonexistent/path'\n"
    )

    @pytest.mark.asyncio
    async def test_prunes_and_retries_on_stale_worktree_error(
        self, tmp_path: Path
    ) -> None:
        """TS-80-5: Prune + retry when 'used by worktree' path doesn't exist."""
        from agent_fox.workspace.git import delete_branch

        call_responses: list[tuple[int, str, str]] = [
            # First delete attempt: fails with "used by worktree"
            (1, "", self._USED_BY_WORKTREE_STDERR),
            # git worktree prune: succeeds
            (0, "", ""),
            # Second delete attempt: succeeds
            (0, "", ""),
        ]
        mock_run_git = AsyncMock(side_effect=call_responses)

        with patch("agent_fox.workspace.git.run_git", mock_run_git):
            # Should not raise
            await delete_branch(tmp_path, "feature/spec/0", force=True)

        # Verify prune was called between the two delete attempts
        calls = mock_run_git.call_args_list
        assert any(
            "prune" in str(c) for c in calls
        ), "git worktree prune should have been called"

    @pytest.mark.asyncio
    async def test_retry_failure_is_non_fatal_when_path_missing(
        self, tmp_path: Path
    ) -> None:
        """TS-80-6: Non-fatal when retry also fails and worktree path is absent."""
        from agent_fox.workspace.git import delete_branch

        # Both delete attempts fail with "used by worktree" for non-existent path
        call_responses: list[tuple[int, str, str]] = [
            (1, "", self._USED_BY_WORKTREE_STDERR),
            (0, "", ""),  # prune succeeds
            (1, "", self._USED_BY_WORKTREE_STDERR),  # retry still fails
        ]
        mock_run_git = AsyncMock(side_effect=call_responses)

        with patch("agent_fox.workspace.git.run_git", mock_run_git):
            # Should NOT raise — treat as non-fatal
            await delete_branch(tmp_path, "feature/spec/0", force=True)

    @pytest.mark.asyncio
    async def test_retry_failure_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TS-80-6: Warning is logged when retry also fails."""
        from agent_fox.workspace.git import delete_branch

        call_responses: list[tuple[int, str, str]] = [
            (1, "", self._USED_BY_WORKTREE_STDERR),
            (0, "", ""),
            (1, "", self._USED_BY_WORKTREE_STDERR),
        ]
        mock_run_git = AsyncMock(side_effect=call_responses)

        with patch("agent_fox.workspace.git.run_git", mock_run_git):
            with caplog.at_level(logging.WARNING, logger="agent_fox.workspace.git"):
                await delete_branch(tmp_path, "feature/spec/0", force=True)

        assert any(
            "worktree" in record.message.lower() or "feature/spec/0" in record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ), "Expected a WARNING log about the worktree or branch"


# ---------------------------------------------------------------------------
# TS-80-7: _cleanup_empty_ancestors
# Requirement: 80-REQ-3.1
# ---------------------------------------------------------------------------


class TestCleanupEmptyAncestors:
    """TS-80-7, TS-80-E2, TS-80-E3: Orphan ancestor directory cleanup."""

    def test_removes_empty_parent_up_to_root(self, tmp_path: Path) -> None:
        """TS-80-7: Empty spec_name/ directory is removed (0/ is the leaf)."""
        from agent_fox.workspace.worktree import _cleanup_empty_ancestors

        root = tmp_path / "worktrees"
        spec_dir = root / "spec_name"
        task_dir = spec_dir / "0"
        task_dir.mkdir(parents=True)

        _cleanup_empty_ancestors(task_dir, root)

        assert not spec_dir.exists(), "Empty spec_name/ should be removed"
        assert root.exists(), "Root worktrees/ must not be removed"

    def test_leaves_non_empty_parent_in_place(self, tmp_path: Path) -> None:
        """TS-80-E2: Non-empty ancestor directories are preserved."""
        from agent_fox.workspace.worktree import _cleanup_empty_ancestors

        root = tmp_path / "worktrees"
        sibling = root / "spec_name" / "1"
        sibling.mkdir(parents=True)
        target = root / "spec_name" / "0"
        target.mkdir(parents=True)

        _cleanup_empty_ancestors(target, root)

        # spec_name/ has sibling "1/" so must remain
        assert (root / "spec_name").exists(), "Non-empty spec_name/ must be preserved"
        # The target leaf itself should be gone
        assert not target.exists(), "Empty 0/ should be removed"

    def test_cleanup_failure_is_non_fatal(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TS-80-E3: PermissionError during cleanup is swallowed."""
        from agent_fox.workspace.worktree import _cleanup_empty_ancestors

        root = tmp_path / "worktrees"
        task_dir = root / "spec_name" / "0"
        task_dir.mkdir(parents=True)

        with patch("pathlib.Path.rmdir", side_effect=PermissionError("denied")):
            # Must not raise
            _cleanup_empty_ancestors(task_dir, root)

    def test_root_itself_is_never_removed(self, tmp_path: Path) -> None:
        """Root boundary is respected even when root itself is the parent."""
        from agent_fox.workspace.worktree import _cleanup_empty_ancestors

        root = tmp_path / "worktrees"
        task_dir = root / "0"
        task_dir.mkdir(parents=True)

        _cleanup_empty_ancestors(task_dir, root)

        assert root.exists(), "Root must never be removed"


# ---------------------------------------------------------------------------
# TS-80-9: post-prune still referenced triggers second prune
# Requirement: 80-REQ-1.E1
# ---------------------------------------------------------------------------


class TestDestroyWorktreePostPruneRetry:
    """TS-80-9, TS-80-E4: Post-prune verification with retry logic in destroy_worktree."""

    @pytest.mark.asyncio
    async def test_second_prune_called_when_first_verify_still_referenced(
        self, tmp_path: Path
    ) -> None:
        """TS-80-9: Two prunes made when branch still referenced after first."""
        from agent_fox.workspace.git import branch_used_by_worktree  # noqa: F401
        from agent_fox.workspace.worktree import destroy_worktree

        workspace = WorkspaceInfo(
            path=tmp_path / ".agent-fox" / "worktrees" / "spec" / "0",
            branch="feature/spec/0",
            spec_name="spec",
            task_group=0,
        )
        # branch_used_by_worktree: True on first check, False on second
        used_sequence = [True, False]
        used_iter = iter(used_sequence)

        prune_call_count = 0

        async def mock_run_git(args: list[str], **kwargs: object) -> tuple[int, str, str]:
            nonlocal prune_call_count
            if args[:2] == ["worktree", "prune"]:
                prune_call_count += 1
            return (0, "", "")

        async def mock_branch_used(repo: Path, branch: str) -> bool:
            return next(used_iter)

        with (
            patch("agent_fox.workspace.worktree.run_git", side_effect=mock_run_git),
            patch(
                "agent_fox.workspace.worktree.branch_used_by_worktree",
                side_effect=mock_branch_used,
            ),
            patch("agent_fox.workspace.worktree.delete_branch", new_callable=AsyncMock),
            patch("agent_fox.workspace.worktree._cleanup_empty_ancestors"),
        ):
            await destroy_worktree(tmp_path, workspace)

        assert prune_call_count >= 2, "Expected at least two prune calls"

    @pytest.mark.asyncio
    async def test_branch_deletion_skipped_when_still_referenced_after_two_prunes(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TS-80-E4: Skip deletion and log warning when branch still referenced."""
        from agent_fox.workspace.git import branch_used_by_worktree  # noqa: F401
        from agent_fox.workspace.worktree import destroy_worktree

        workspace = WorkspaceInfo(
            path=tmp_path / ".agent-fox" / "worktrees" / "spec" / "0",
            branch="feature/spec/0",
            spec_name="spec",
            task_group=0,
        )

        delete_was_called = False

        async def mock_delete_branch(*args: object, **kwargs: object) -> None:
            nonlocal delete_was_called
            delete_was_called = True

        with (
            patch(
                "agent_fox.workspace.worktree.run_git",
                new_callable=AsyncMock,
                return_value=(0, "", ""),
            ),
            patch(
                "agent_fox.workspace.worktree.branch_used_by_worktree",
                new_callable=AsyncMock,
                return_value=True,  # Always referenced
            ),
            patch(
                "agent_fox.workspace.worktree.delete_branch",
                side_effect=mock_delete_branch,
            ),
            patch("agent_fox.workspace.worktree._cleanup_empty_ancestors"),
            caplog.at_level(logging.WARNING, logger="agent_fox.workspace.worktree"),
        ):
            # Must not raise
            await destroy_worktree(tmp_path, workspace)

        assert not delete_was_called, "Branch deletion must be skipped when still referenced"
        assert any(
            "still referenced" in record.message.lower()
            or "skip" in record.message.lower()
            or "worktree" in record.message.lower()
            for record in caplog.records
            if record.levelno >= logging.WARNING
        ), "Expected a WARNING about the branch still being referenced"
