"""Harvester tests.

Test Spec: TS-03-10 (squash merge), TS-03-11 (diverged squash merge),
           TS-03-E5 (no commits), TS-03-E6 (unresolvable conflict)
Requirements: 03-REQ-7.1 through 03-REQ-7.E2,
              45-REQ-4.1, 45-REQ-6.1
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.workspace import create_worktree
from agent_fox.workspace.harvest import harvest

from .conftest import add_commit_to_branch


class TestHarvesterSquashMerge:
    """TS-03-10: Harvester merges changes via squash merge."""

    @pytest.mark.asyncio
    async def test_squash_merge_succeeds(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Harvesting a feature branch with commits squash-merges into develop."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(ws.path, "new_file.py", "print('hello')\n")

        files = await harvest(tmp_worktree_repo, ws)
        assert "new_file.py" in files

    @pytest.mark.asyncio
    async def test_squash_produces_single_commit(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """After harvest, develop has exactly one new commit (squash)."""
        develop_tip_before = subprocess.run(
            ["git", "rev-parse", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(ws.path, "file_a.py", "a\n")
        add_commit_to_branch(ws.path, "file_b.py", "b\n")

        await harvest(tmp_worktree_repo, ws)

        # Count commits on develop since the tip before harvest
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{develop_tip_before}..develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert int(result.stdout.strip()) == 1, "Squash merge should produce exactly one commit"


class TestSquashCommitMessage:
    """Squash merge uses the feature branch tip commit's message, not SQUASH_MSG."""

    @pytest.mark.asyncio
    async def test_squash_uses_tip_commit_message(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """The squash commit title should be the feature branch tip's subject,
        not 'Squashed commit of the following:'."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(
            ws.path, "new_file.py", "print('hello')\n",
            message="feat: add greeting module",
        )

        await harvest(tmp_worktree_repo, ws)

        result = subprocess.run(
            ["git", "log", "-1", "--format=%s", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        subject = result.stdout.strip()
        assert subject == "feat: add greeting module"
        assert "Squashed commit" not in subject

    @pytest.mark.asyncio
    async def test_squash_multi_commit_uses_tip_subject(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Multi-commit branch uses the tip commit's subject as the title
        and includes earlier commit subjects in the body."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(
            ws.path, "file_a.py", "a\n",
            message="feat: add module A",
        )
        add_commit_to_branch(
            ws.path, "file_b.py", "b\n",
            message="feat: add module B",
        )

        await harvest(tmp_worktree_repo, ws)

        result = subprocess.run(
            ["git", "log", "-1", "--format=%s", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        subject = result.stdout.strip()
        assert subject == "feat: add module B"
        assert "Squashed commit" not in subject

        body_result = subprocess.run(
            ["git", "log", "-1", "--format=%b", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        body = body_result.stdout.strip()
        assert "- feat: add module A" in body

    @pytest.mark.asyncio
    async def test_squash_no_author_date_lines(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Squash commit message must not contain Author: or Date: metadata."""
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)
        add_commit_to_branch(
            ws.path, "new_file.py", "content\n",
            message="fix: resolve edge case",
        )

        await harvest(tmp_worktree_repo, ws)

        result = subprocess.run(
            ["git", "log", "-1", "--format=%B", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        full_msg = result.stdout
        assert "Author:" not in full_msg
        assert "Date:" not in full_msg


class TestHarvesterDivergedSquashMerge:
    """TS-03-11: Harvester squash-merges diverged branches."""

    @pytest.mark.asyncio
    async def test_diverged_merge_succeeds(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """When develop has diverged, harvester squash-merges successfully."""
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
    """Squash merge with identical content on both branches."""

    @pytest.mark.asyncio
    async def test_cherry_pick_conflict_falls_back_to_merge(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """When both branches have the same file with the same content,
        squash merge produces no new changes (no-op commit)."""
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

        # Harvest should succeed — no IntegrationError raised
        files = await harvest(tmp_worktree_repo, ws)
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
        develop_tip_before = subprocess.run(
            ["git", "rev-parse", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        ws = await create_worktree(tmp_worktree_repo, "test_spec", 1)

        await harvest(tmp_worktree_repo, ws)

        develop_tip_after = subprocess.run(
            ["git", "rev-parse", "develop"],
            cwd=tmp_worktree_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert develop_tip_after == develop_tip_before


class TestHarvesterConflictAutoResolve:
    """Harvester delegates conflict resolution to the merge agent.

    Previously these tests verified -X theirs auto-resolution. With the
    removal of blind strategy options (45-REQ-6.1), conflicts that cannot
    be resolved deterministically are delegated to the merge agent. When
    the agent fails, harvest raises IntegrationError.
    """

    @pytest.mark.asyncio
    async def test_add_add_conflict_raises_without_agent(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """When both branches add the same file with different content,
        the harvester delegates to the merge agent. When the agent fails,
        this raises IntegrationError (45-REQ-4.E1)."""
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

        # With the merge agent mocked to fail, harvest should raise
        with patch(
            "agent_fox.workspace.harvest.run_merge_agent",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(IntegrationError, match="(?i)agent"):
                await harvest(tmp_worktree_repo, ws)

    @pytest.mark.asyncio
    async def test_parallel_add_add_multiple_files(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Simulates parallel sessions creating overlapping files —
        the exact scenario from issue #84. When the merge agent fails,
        raises IntegrationError."""
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

        # With the merge agent mocked to fail, harvest should raise
        with patch(
            "agent_fox.workspace.harvest.run_merge_agent",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(IntegrationError, match="(?i)agent"):
                await harvest(tmp_worktree_repo, ws)

    @pytest.mark.asyncio
    async def test_auto_resolve_preserves_non_conflicting_develop_changes(
        self,
        tmp_worktree_repo: Path,
    ) -> None:
        """Non-conflicting changes from develop are preserved only when merge
        succeeds. With conflicting files, the merge agent is needed.
        When the agent fails, raises IntegrationError."""
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

        # With the merge agent mocked to fail, harvest should raise
        with patch(
            "agent_fox.workspace.harvest.run_merge_agent",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(IntegrationError, match="(?i)agent"):
                await harvest(tmp_worktree_repo, ws)
