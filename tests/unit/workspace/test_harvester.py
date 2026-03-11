"""Harvester tests.

Test Spec: TS-03-10 (fast-forward merge), TS-03-11 (rebase on conflict),
           TS-03-E5 (no commits), TS-03-E6 (unresolvable conflict)
Requirements: 03-REQ-7.1 through 03-REQ-7.E2
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_fox.workspace.harvest import harvest
from agent_fox.workspace.workspace import create_worktree

from .conftest import add_commit_to_branch, get_branch_tip


class TestHarvesterFastForward:
    """TS-03-10: Harvester merges changes via fast-forward."""

    @pytest.mark.asyncio
    async def test_fast_forward_merge_succeeds(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting a feature branch with commits merges into develop."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(ws.path, "new_file.py", "print('hello')\n")

        files = await harvest(tmp_worktree_repo, ws)
        assert "new_file.py" in files

    @pytest.mark.asyncio
    async def test_develop_tip_matches_feature_after_merge(
        self,
        tmp_worktree_repo: Path,
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
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """When develop has diverged, harvester rebases and merges."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Add a commit on the feature branch (different file)
        add_commit_to_branch(
            ws.path,
            "feature_file.py",
            "feature content\n",
        )

        # Add a commit on develop (different file, no conflict)
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo,
            "other_file.py",
            "develop content\n",
        )

        files = await harvest(tmp_worktree_repo, ws)
        assert "feature_file.py" in files


class TestHarvesterMergeFallback:
    """Merge-commit fallback when rebase has conflicts but merge succeeds."""

    @pytest.mark.asyncio
    async def test_cherry_pick_conflict_falls_back_to_merge(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """When a cherry-picked commit causes rebase conflicts,
        the harvester falls back to a merge commit and succeeds."""
        # Simulate the real-world scenario: session 1 adds a file,
        # its changes get merged into develop. Session 2 independently
        # added the same content (cherry-pick equivalent).
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Add a file on the feature branch
        add_commit_to_branch(
            ws.path,
            "tests/test_scaffold.py",
            "def test_scaffold(): pass\n",
        )

        # Add the SAME file with SAME content on develop (simulates
        # a prior session's merge containing the same change)
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo,
            "tests/test_scaffold.py",
            "def test_scaffold(): pass\n",
        )

        # Harvest should succeed via merge fallback (not raise)
        files = await harvest(tmp_worktree_repo, ws)
        # The file was already on develop, so changed_files may be empty
        # The key assertion: no IntegrationError is raised
        assert isinstance(files, list)


class TestHarvesterNoCommits:
    """TS-03-E5: Harvester with no new commits is no-op."""

    @pytest.mark.asyncio
    async def test_no_commits_returns_empty_list(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting a branch with no new commits returns an empty list."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        # Don't add any commits
        files = await harvest(tmp_worktree_repo, ws)
        assert files == []

    @pytest.mark.asyncio
    async def test_no_commits_leaves_develop_unchanged(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting with no new commits does not change develop."""
        develop_tip_before = get_branch_tip(tmp_worktree_repo, "develop")
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        await harvest(tmp_worktree_repo, ws)

        develop_tip_after = get_branch_tip(tmp_worktree_repo, "develop")
        assert develop_tip_after == develop_tip_before


class TestHarvesterConflictAutoResolve:
    """Harvester auto-resolves add/add conflicts preferring feature branch."""

    @pytest.mark.asyncio
    async def test_add_add_conflict_resolved_with_theirs(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """When both branches add the same file with different content,
        the harvester auto-resolves by keeping the feature branch version."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Add a file on the feature branch
        add_commit_to_branch(
            ws.path,
            "shared.py",
            "feature content\n",
        )

        # Add the SAME file with DIFFERENT content on develop
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(
            tmp_worktree_repo,
            "shared.py",
            "develop content\n",
        )

        # Harvest should succeed (no IntegrationError)
        files = await harvest(tmp_worktree_repo, ws)
        assert isinstance(files, list)

        # The feature branch content should win on develop
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        shared = (tmp_worktree_repo / "shared.py").read_text()
        assert shared == "feature content\n"

    @pytest.mark.asyncio
    async def test_parallel_add_add_multiple_files(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Simulates parallel sessions creating overlapping files —
        the exact scenario from issue #84."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Feature branch creates several files (simulating a task group)
        add_commit_to_branch(ws.path, "Makefile", "feature-makefile\n")
        add_commit_to_branch(ws.path, "go.mod", "feature-gomod\n")

        # Meanwhile, develop got the same files from another session
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(tmp_worktree_repo, "Makefile", "develop-makefile\n")
        add_commit_to_branch(tmp_worktree_repo, "go.mod", "develop-gomod\n")

        # Harvest should succeed (no IntegrationError)
        files = await harvest(tmp_worktree_repo, ws)
        assert isinstance(files, list)

        # Feature branch content should win for both files
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        assert (tmp_worktree_repo / "Makefile").read_text() == "feature-makefile\n"
        assert (tmp_worktree_repo / "go.mod").read_text() == "feature-gomod\n"

    @pytest.mark.asyncio
    async def test_auto_resolve_preserves_non_conflicting_develop_changes(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Non-conflicting changes from develop are preserved."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        # Feature branch creates one file
        add_commit_to_branch(ws.path, "shared.py", "feature content\n")

        # Develop creates the same file AND a different file
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        add_commit_to_branch(tmp_worktree_repo, "shared.py", "develop content\n")
        add_commit_to_branch(tmp_worktree_repo, "other.py", "other content\n")

        files = await harvest(tmp_worktree_repo, ws)
        assert isinstance(files, list)

        # Checkout develop to verify merged content
        subprocess.run(
            ["git", "checkout", "develop"],
            cwd=tmp_worktree_repo,
            check=True,
            capture_output=True,
        )
        # Feature wins for the conflict
        assert (tmp_worktree_repo / "shared.py").read_text() == "feature content\n"
        # Develop's non-conflicting file is preserved
        assert (tmp_worktree_repo / "other.py").read_text() == "other content\n"
