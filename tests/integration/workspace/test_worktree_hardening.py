"""Integration tests for worktree cleanup hardening using real git repos.

Test Spec: TS-80-3, TS-80-4, TS-80-8, TS-80-E1, TS-80-SMOKE-1, TS-80-SMOKE-2
Requirements: 80-REQ-1.1, 80-REQ-1.2, 80-REQ-2.E1, 80-REQ-3.1, 80-REQ-3.2
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_fox.core.errors import WorkspaceError
from agent_fox.workspace import create_worktree, destroy_worktree
from agent_fox.workspace.git import delete_branch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Create a bare git repo suitable for worktree tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "develop"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _branch_exists(repo: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "--list", "--", branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return branch in result.stdout


# ---------------------------------------------------------------------------
# TS-80-3: destroy_worktree verifies before branch deletion
# Requirement: 80-REQ-1.1
# ---------------------------------------------------------------------------


class TestDestroyWorktreeVerifiesBeforeDeletion:
    """TS-80-3: destroy_worktree succeeds and deletes branch via clean flow."""

    @pytest.mark.asyncio
    async def test_destroy_deletes_branch_successfully(
        self, tmp_path: Path
    ) -> None:
        """TS-80-3: Branch is deleted after destroy_worktree completes."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)

        await destroy_worktree(repo, ws)

        assert not _branch_exists(repo, ws.branch), (
            f"Branch {ws.branch!r} should be deleted after destroy_worktree"
        )

    @pytest.mark.asyncio
    async def test_destroy_raises_no_workspace_error(
        self, tmp_path: Path
    ) -> None:
        """TS-80-3: No WorkspaceError raised during normal destroy."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)

        # Should not raise
        await destroy_worktree(repo, ws)


# ---------------------------------------------------------------------------
# TS-80-4: create_worktree handles stale worktree
# Requirement: 80-REQ-1.2
# ---------------------------------------------------------------------------


class TestCreateWorktreeHandlesStaleState:
    """TS-80-4: create_worktree recovers from stale worktree registry entries."""

    @pytest.mark.asyncio
    async def test_creates_worktree_despite_stale_registry(
        self, tmp_path: Path
    ) -> None:
        """TS-80-4: New worktree created when stale registry entry exists."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)

        # Simulate stale state: remove directory but leave git registry entry
        shutil.rmtree(ws.path)
        # Recreate as empty dir (as might happen after partial crash)
        ws.path.mkdir(parents=True)

        # Should succeed despite stale state
        ws2 = await create_worktree(repo, "spec", 0)

        assert ws2.path.exists(), "New worktree directory must exist"

    @pytest.mark.asyncio
    async def test_stale_worktree_replaced_with_valid_worktree(
        self, tmp_path: Path
    ) -> None:
        """TS-80-4: Resulting worktree is a valid git worktree."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)
        shutil.rmtree(ws.path)
        ws.path.mkdir(parents=True)

        ws2 = await create_worktree(repo, "spec", 0)

        # A valid worktree has a .git file (not directory)
        git_file = ws2.path / ".git"
        assert git_file.exists(), "Valid worktree must have a .git file"


# ---------------------------------------------------------------------------
# TS-80-8: create_worktree cleans orphan directories
# Requirement: 80-REQ-3.2
# ---------------------------------------------------------------------------


class TestCreateWorktreeCleansOrphans:
    """TS-80-8: Stale empty directories are cleaned during create_worktree."""

    @pytest.mark.asyncio
    async def test_new_worktree_succeeds_with_stale_sibling_dir(
        self, tmp_path: Path
    ) -> None:
        """TS-80-8: create_worktree succeeds even with stale empty ancestor dirs."""
        repo = _make_repo(tmp_path)
        # Pre-create an empty stale directory
        stale_dir = repo / ".agent-fox" / "worktrees" / "spec" / "99"
        stale_dir.mkdir(parents=True)

        # Create a worktree for group 0 under the same spec
        ws = await create_worktree(repo, "spec", 0)

        assert ws.path.exists(), "New worktree must be created"

    @pytest.mark.asyncio
    async def test_orphan_dir_removed_after_create(
        self, tmp_path: Path
    ) -> None:
        """TS-80-8: After create_worktree, the stale empty 99/ dir is gone."""
        repo = _make_repo(tmp_path)
        stale_dir = repo / ".agent-fox" / "worktrees" / "spec" / "99"
        stale_dir.mkdir(parents=True)

        ws = await create_worktree(repo, "spec", 0)
        assert ws.path.exists()

        # The stale directory should have been cleaned up
        # (it's an orphaned empty directory under the same spec)
        # NOTE: This asserts the NEW behavior — tests will fail until implemented
        assert not stale_dir.exists(), (
            "Stale empty directory 99/ should be cleaned up during create_worktree"
        )


# ---------------------------------------------------------------------------
# TS-80-E1: delete_branch with live worktree raises
# Requirement: 80-REQ-2.E1
# ---------------------------------------------------------------------------


class TestDeleteBranchLiveWorktreeRaises:
    """TS-80-E1: WorkspaceError raised when worktree directory actually exists."""

    @pytest.mark.asyncio
    async def test_raises_when_worktree_directory_exists(
        self, tmp_path: Path
    ) -> None:
        """TS-80-E1: Legitimate in-use worktree causes WorkspaceError."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)

        assert ws.path.exists(), "Test precondition: worktree must exist"

        with pytest.raises(WorkspaceError):
            await delete_branch(repo, ws.branch, force=True)


# ---------------------------------------------------------------------------
# TS-80-SMOKE-1: Full destroy_worktree with simulated stale state
# Design Path: Path 2
# ---------------------------------------------------------------------------


class TestSmokeDestroyWorktreeWithStaleState:
    """TS-80-SMOKE-1: End-to-end destroy_worktree with stale registry entry."""

    @pytest.mark.asyncio
    async def test_destroy_succeeds_with_stale_registry(
        self, tmp_path: Path
    ) -> None:
        """TS-80-SMOKE-1: destroy_worktree succeeds when registry is stale."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)

        # Simulate crash: remove directory but do NOT prune registry
        shutil.rmtree(ws.path)

        # Must not raise
        await destroy_worktree(repo, ws)

    @pytest.mark.asyncio
    async def test_no_empty_dirs_left_after_destroy_stale(
        self, tmp_path: Path
    ) -> None:
        """TS-80-SMOKE-1: No empty worktree dirs remain after destroy_worktree."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)
        shutil.rmtree(ws.path)

        await destroy_worktree(repo, ws)

        worktrees_root = repo / ".agent-fox" / "worktrees"
        if worktrees_root.exists():
            leftover = [d for d in worktrees_root.glob("spec/*") if d.exists()]
            assert not leftover, (
                f"Empty worktree dirs remain after destroy: {leftover}"
            )


# ---------------------------------------------------------------------------
# TS-80-SMOKE-2: Full create_worktree with stale predecessor
# Design Path: Path 4
# ---------------------------------------------------------------------------


class TestSmokeCreateWorktreeWithStalePredecessor:
    """TS-80-SMOKE-2: End-to-end create_worktree with stale predecessor."""

    @pytest.mark.asyncio
    async def test_create_succeeds_after_simulated_crash(
        self, tmp_path: Path
    ) -> None:
        """TS-80-SMOKE-2: create_worktree recovers from stale predecessor."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)

        # Simulate crash: remove directory, leave registry, recreate empty dir
        shutil.rmtree(ws.path)
        ws.path.mkdir(parents=True)  # Stale empty dir

        # Should succeed
        ws2 = await create_worktree(repo, "spec", 0)

        assert ws2.path.exists(), "Worktree must be created"

    @pytest.mark.asyncio
    async def test_new_worktree_is_valid_after_stale_recovery(
        self, tmp_path: Path
    ) -> None:
        """TS-80-SMOKE-2: WorkspaceInfo has correct path and branch after recovery."""
        repo = _make_repo(tmp_path)
        ws = await create_worktree(repo, "spec", 0)
        shutil.rmtree(ws.path)
        ws.path.mkdir(parents=True)

        ws2 = await create_worktree(repo, "spec", 0)

        assert ws2.path.exists()
        assert (ws2.path / ".git").exists(), "Must be a valid git worktree"
        assert ws2.branch == "feature/spec/0"
