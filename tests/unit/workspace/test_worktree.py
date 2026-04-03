"""Worktree management tests.

Test Spec: TS-03-1 (creation), TS-03-2 (destruction), TS-03-3 (stale removal),
           TS-03-E1 (git error), TS-03-E2 (destroy non-existent)
Requirements: 03-REQ-1.1 through 03-REQ-1.E3, 03-REQ-2.1 through 03-REQ-2.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_fox.core.errors import WorkspaceError
from agent_fox.workspace import (
    WorkspaceInfo,
    create_worktree,
    destroy_worktree,
)

from .conftest import add_commit_to_branch, get_branch_tip, list_branches


class TestWorktreeCreation:
    """TS-03-1: Worktree creation produces correct structure."""

    @pytest.mark.asyncio
    async def test_creates_worktree_directory(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Creating a worktree produces the expected directory."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        expected_path = tmp_worktree_repo / ".agent-fox" / "worktrees" / "test_spec" / "1"
        assert ws.path == expected_path
        assert ws.path.is_dir()

    @pytest.mark.asyncio
    async def test_creates_feature_branch(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Creating a worktree creates the feature branch in the repo."""
        _ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        branches = list_branches(tmp_worktree_repo)
        assert "feature/test_spec/1" in branches

    @pytest.mark.asyncio
    async def test_returns_correct_workspace_info(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """WorkspaceInfo has correct branch, spec_name, and task_group."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        assert ws.branch == "feature/test_spec/1"
        assert ws.spec_name == "test_spec"
        assert ws.task_group == 1

    @pytest.mark.asyncio
    async def test_worktree_has_branch_checked_out(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """The worktree has the feature branch checked out."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        # Verify the worktree is on the feature branch by checking HEAD
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ws.path,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "feature/test_spec/1"


class TestWorktreeDestruction:
    """TS-03-2: Worktree destruction removes directory and branch."""

    @pytest.mark.asyncio
    async def test_removes_worktree_directory(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Destroying a worktree removes its directory."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        await destroy_worktree(tmp_worktree_repo, ws)
        assert not ws.path.exists()

    @pytest.mark.asyncio
    async def test_removes_feature_branch(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Destroying a worktree removes its feature branch."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        await destroy_worktree(tmp_worktree_repo, ws)
        branches = list_branches(tmp_worktree_repo)
        assert "feature/test_spec/1" not in branches

    @pytest.mark.asyncio
    async def test_removes_empty_spec_directory(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Destroying the only worktree in a spec removes the spec dir."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        await destroy_worktree(tmp_worktree_repo, ws)
        spec_dir = tmp_worktree_repo / ".agent-fox" / "worktrees" / "test_spec"
        assert not spec_dir.exists()


class TestStaleWorktreeRemoval:
    """TS-03-3: Stale worktree is removed on re-creation."""

    @pytest.mark.asyncio
    async def test_recreate_stale_worktree_succeeds(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Re-creating an existing worktree does not raise."""
        _ws1 = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        # Add a commit to develop to prove the branch point moves
        import subprocess

        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo,
            "new_file.txt",
            "new content\n",
        )
        ws2 = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        assert ws2.path.is_dir()

    @pytest.mark.asyncio
    async def test_recreated_worktree_has_fresh_branch_point(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Re-created worktree points to the current develop tip."""
        _ws1 = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        # Add a commit to develop
        import subprocess

        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo,
            "new_file.txt",
            "new content\n",
        )
        develop_tip = get_branch_tip(tmp_worktree_repo, "develop")
        ws2 = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        branch_tip = get_branch_tip(tmp_worktree_repo, ws2.branch)
        assert branch_tip == develop_tip


class TestWorktreeCreationGitError:
    """TS-03-E1: Worktree creation fails on git error."""

    @pytest.mark.asyncio
    async def test_raises_workspace_error_on_git_failure(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """A git failure during worktree creation raises WorkspaceError."""
        with patch(
            "agent_fox.workspace.worktree.run_git",
            new_callable=AsyncMock,
            side_effect=WorkspaceError("git worktree add failed: fatal error"),
        ):
            with pytest.raises(WorkspaceError):
                await create_worktree(tmp_worktree_repo, "test_spec", 1)


class TestSpecNameValidation:
    """H1: Spec names with path traversal characters are rejected."""

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Spec name containing '..' is rejected."""
        with pytest.raises(WorkspaceError, match="Invalid spec name"):
            await create_worktree(tmp_worktree_repo, "99_../../../tmp/evil", 1)

    @pytest.mark.asyncio
    async def test_rejects_slash(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Spec name containing '/' is rejected."""
        with pytest.raises(WorkspaceError, match="Invalid spec name"):
            await create_worktree(tmp_worktree_repo, "99_foo/bar", 1)

    @pytest.mark.asyncio
    async def test_accepts_valid_spec_name(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """A valid spec name with alphanumerics and underscores passes."""
        ws = await create_worktree(tmp_worktree_repo, "01_core_foundation", 1)
        assert ws.spec_name == "01_core_foundation"


class TestDestroyNonExistentWorktree:
    """TS-03-E2: Destroy non-existent worktree is no-op."""

    @pytest.mark.asyncio
    async def test_destroy_nonexistent_does_not_raise(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Destroying a non-existent worktree succeeds silently."""
        ws = WorkspaceInfo(
            path=Path("/nonexistent/path"),
            branch="feature/x/1",
            spec_name="x",
            task_group=1,
        )
        # Should not raise
        await destroy_worktree(tmp_worktree_repo, ws)
