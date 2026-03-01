"""Harvester tests.

Test Spec: TS-03-10 (fast-forward merge), TS-03-11 (rebase on conflict),
           TS-03-E5 (no commits), TS-03-E6 (unresolvable conflict)
Requirements: 03-REQ-7.1 through 03-REQ-7.E2
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.harvester import harvest
from agent_fox.workspace.worktree import create_worktree

from .conftest import add_commit_to_branch, get_branch_tip


class TestHarvesterFastForward:
    """TS-03-10: Harvester merges changes via fast-forward."""

    @pytest.mark.asyncio
    async def test_fast_forward_merge_succeeds(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting a feature branch with commits merges into develop."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(ws.path, "new_file.py", "print('hello')\n")

        files = await harvest(tmp_worktree_repo, ws)
        assert "new_file.py" in files

    @pytest.mark.asyncio
    async def test_develop_tip_matches_feature_after_merge(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """After harvest, develop tip matches the feature branch tip."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(ws.path, "new_file.py", "print('hello')\n")

        await harvest(tmp_worktree_repo, ws)

        develop_tip = get_branch_tip(tmp_worktree_repo, "develop")
        feature_tip = get_branch_tip(tmp_worktree_repo, ws.branch)
        assert develop_tip == feature_tip


class TestHarvesterRebaseRetry:
    """TS-03-11: Harvester rebases on conflict and retries."""

    @pytest.mark.asyncio
    async def test_diverged_merge_succeeds_after_rebase(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """When develop has diverged, harvester rebases and merges."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Add a commit on the feature branch (different file)
        add_commit_to_branch(
            ws.path, "feature_file.py", "feature content\n",
        )

        # Add a commit on develop (different file, no conflict)
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo, "other_file.py", "develop content\n",
        )

        files = await harvest(tmp_worktree_repo, ws)
        assert "feature_file.py" in files


class TestHarvesterNoCommits:
    """TS-03-E5: Harvester with no new commits is no-op."""

    @pytest.mark.asyncio
    async def test_no_commits_returns_empty_list(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting a branch with no new commits returns an empty list."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        # Don't add any commits
        files = await harvest(tmp_worktree_repo, ws)
        assert files == []

    @pytest.mark.asyncio
    async def test_no_commits_leaves_develop_unchanged(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting with no new commits does not change develop."""
        develop_tip_before = get_branch_tip(tmp_worktree_repo, "develop")
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        await harvest(tmp_worktree_repo, ws)

        develop_tip_after = get_branch_tip(tmp_worktree_repo, "develop")
        assert develop_tip_after == develop_tip_before


class TestHarvesterUnresolvableConflict:
    """TS-03-E6: Harvester raises IntegrationError on unresolvable conflict."""

    @pytest.mark.asyncio
    async def test_conflict_raises_integration_error(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """An unresolvable merge conflict raises IntegrationError."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Modify the same file on the feature branch
        add_commit_to_branch(
            ws.path, "shared.py", "feature content\n",
        )

        # Modify the same file on develop (creates conflict)
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo, "shared.py", "develop content\n",
        )

        with pytest.raises(IntegrationError):
            await harvest(tmp_worktree_repo, ws)

    @pytest.mark.asyncio
    async def test_conflict_leaves_develop_unchanged(
        self, tmp_worktree_repo: Path,
    ) -> None:
        """After a conflict, develop remains at its original tip."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        add_commit_to_branch(
            ws.path, "shared.py", "feature content\n",
        )

        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo, "shared.py", "develop content\n",
        )
        # Capture develop tip after the divergent commit
        develop_tip_after_commit = get_branch_tip(tmp_worktree_repo, "develop")

        with pytest.raises(IntegrationError):
            await harvest(tmp_worktree_repo, ws)

        # Develop should be unchanged from the point after the divergent commit
        develop_tip_after_harvest = get_branch_tip(tmp_worktree_repo, "develop")
        assert develop_tip_after_harvest == develop_tip_after_commit
