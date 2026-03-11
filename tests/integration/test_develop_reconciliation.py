"""Integration tests for develop branch reconciliation.

Test Spec: TS-36-1, TS-36-2, TS-36-4, TS-36-5, TS-36-6, TS-36-7
Requirements: 36-REQ-1.1, 36-REQ-1.2, 36-REQ-1.4,
              36-REQ-2.1, 36-REQ-2.2, 36-REQ-2.4

Uses real temporary git repositories with actual diverged branches.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_fox.workspace.harvest import _push_develop_if_pushable
from agent_fox.workspace.workspace import _sync_develop_with_remote

# ---- Helpers ----


def _run(args: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    """Run a git command synchronously."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _run_unchecked(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command without raising on failure."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _git_config(repo: Path) -> None:
    """Set minimal git config for commits."""
    _run(["config", "user.email", "test@test.com"], cwd=repo)
    _run(["config", "user.name", "Test"], cwd=repo)


def _add_commit(repo: Path, filename: str, content: str, msg: str | None = None) -> str:
    """Add a file and commit it. Returns the commit SHA."""
    filepath = repo / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    _run(["add", filename], cwd=repo)
    _run(["commit", "-m", msg or f"add {filename}"], cwd=repo)
    result = _run(["rev-parse", "HEAD"], cwd=repo)
    return result.stdout.strip()


def _get_head(repo: Path, ref: str = "HEAD") -> str:
    """Get the SHA of a ref."""
    result = _run(["rev-parse", ref], cwd=repo)
    return result.stdout.strip()


def _get_parents(repo: Path, ref: str = "HEAD") -> list[str]:
    """Get parent SHAs of a commit."""
    result = _run(["log", "--format=%P", "-1", ref], cwd=repo)
    return result.stdout.strip().split()


def _create_repo_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare 'origin' repo and a cloned working copy.

    Both have a develop branch with an initial commit.
    Returns (working_repo, bare_origin).
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _run(["init", "--bare"], cwd=origin)

    working = tmp_path / "working"
    _run(["clone", str(origin), str(working)], cwd=tmp_path)
    _git_config(working)

    # Create initial commit and develop branch
    _add_commit(working, "README.md", "# Test\n", "initial")
    _run(["push", "origin", "HEAD:refs/heads/main"], cwd=working)
    _run(["checkout", "-b", "develop"], cwd=working)
    _add_commit(working, "setup.py", "# setup\n", "setup")
    _run(["push", "origin", "develop"], cwd=working)

    return working, origin


def _create_diverged_repo(
    tmp_path: Path,
    *,
    conflicting: bool = False,
) -> tuple[Path, Path]:
    """Create a repo where local develop and origin/develop have diverged.

    If conflicting=True, both sides modify the same file with different content
    (will cause merge conflicts). Otherwise, they modify different files.

    Returns (working_repo, bare_origin).
    """
    working, origin = _create_repo_with_origin(tmp_path)

    # Add a commit to origin/develop (simulate another session pushing)
    # Use a second clone to push to origin
    other = tmp_path / "other"
    _run(["clone", str(origin), str(other)], cwd=tmp_path)
    _git_config(other)
    _run(["checkout", "develop"], cwd=other)

    if conflicting:
        _add_commit(other, "shared.txt", "remote content\nline2\n", "remote change")
    else:
        _add_commit(other, "remote_file.txt", "remote content\n", "remote change")

    _run(["push", "origin", "develop"], cwd=other)

    # Add a local commit on develop (diverging from origin)
    if conflicting:
        _add_commit(working, "shared.txt", "local content\nline2\n", "local change")
    else:
        _add_commit(working, "local_file.txt", "local content\n", "local change")

    # Fetch to update origin/develop tracking ref
    _run(["fetch", "origin"], cwd=working)

    return working, origin


# ---------------------------------------------------------------------------
# TS-36-1: Rebase Fails Then Merge Commit Succeeds
# ---------------------------------------------------------------------------


class TestRebaseFailMergeSucceed:
    """TS-36-1: When local develop has diverged from origin/develop and rebase
    fails, a merge commit is attempted and succeeds.

    Requirement: 36-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_diverged_non_conflicting_produces_merge_commit(
        self, tmp_path: Path
    ) -> None:
        """Diverged branches with non-conflicting changes -> merge commit."""
        working, _origin = _create_diverged_repo(tmp_path, conflicting=False)

        # Ensure we're on develop
        _run(["checkout", "develop"], cwd=working)

        await _sync_develop_with_remote(working)

        # After reconciliation, HEAD should have incorporated origin/develop.
        # Check that origin/develop is an ancestor of develop.
        result = _run_unchecked(
            ["merge-base", "--is-ancestor", "origin/develop", "develop"],
            cwd=working,
        )
        assert result.returncode == 0, (
            "origin/develop should be an ancestor of develop after reconciliation"
        )


# ---------------------------------------------------------------------------
# TS-36-2: Rebase Fails Then Merge Fails Then Ours Succeeds
# ---------------------------------------------------------------------------


class TestMergeFailOursSucceed:
    """TS-36-2: When both rebase and merge commit fail, merge with -X ours
    succeeds and preserves local changes.

    Requirement: 36-REQ-1.2
    """

    @pytest.mark.asyncio
    async def test_conflicting_divergence_preserves_local(self, tmp_path: Path) -> None:
        """Conflicting divergence -> -X ours preserves local content."""
        working, _origin = _create_diverged_repo(tmp_path, conflicting=True)

        _run(["checkout", "develop"], cwd=working)

        await _sync_develop_with_remote(working)

        # Local content should be preserved (ours strategy)
        content = (working / "shared.txt").read_text()
        assert "local content" in content, (
            f"Expected local content preserved by -X ours, got: {content}"
        )


# ---------------------------------------------------------------------------
# TS-36-4: Fast-Forward When Behind Only
# ---------------------------------------------------------------------------


class TestFastForwardBehindOnly:
    """TS-36-4: When local develop is behind origin/develop, fast-forward.

    Requirement: 36-REQ-1.4
    """

    @pytest.mark.asyncio
    async def test_behind_only_fast_forwards(self, tmp_path: Path) -> None:
        """Local behind origin -> fast-forwards to match."""
        working, origin = _create_repo_with_origin(tmp_path)

        # Push more commits to origin via another clone
        other = tmp_path / "other"
        _run(["clone", str(origin), str(other)], cwd=tmp_path)
        _git_config(other)
        _run(["checkout", "develop"], cwd=other)
        _add_commit(other, "extra1.txt", "extra1\n", "extra 1")
        _add_commit(other, "extra2.txt", "extra2\n", "extra 2")
        _add_commit(other, "extra3.txt", "extra3\n", "extra 3")
        _run(["push", "origin", "develop"], cwd=other)

        # Fetch in working to update tracking refs
        _run(["fetch", "origin"], cwd=working)

        origin_head = _get_head(working, "origin/develop")
        local_head = _get_head(working, "develop")
        assert local_head != origin_head, "Precondition: local should be behind"

        await _sync_develop_with_remote(working)

        # After sync, local develop should match origin/develop
        new_local = _get_head(working, "develop")
        assert new_local == origin_head


# ---------------------------------------------------------------------------
# TS-36-5: Post-Harvest Reconciles Before Push
# ---------------------------------------------------------------------------


class TestPostHarvestReconcile:
    """TS-36-5: When origin/develop is ahead after harvest, reconciliation
    happens before push.

    Requirement: 36-REQ-2.1
    """

    @pytest.mark.asyncio
    async def test_post_harvest_reconcile_and_push(self, tmp_path: Path) -> None:
        """Diverged post-harvest -> reconcile then push succeeds."""
        working, origin = _create_diverged_repo(tmp_path, conflicting=False)

        _run(["checkout", "develop"], cwd=working)

        await _push_develop_if_pushable(working)

        # After push, origin/develop should match local develop
        _run(["fetch", "origin"], cwd=working)
        local_head = _get_head(working, "develop")
        origin_head = _get_head(working, "origin/develop")
        assert local_head == origin_head, (
            "After reconcile+push, origin/develop should match local develop"
        )


# ---------------------------------------------------------------------------
# TS-36-6: Post-Harvest Push Succeeds After Reconciliation
# ---------------------------------------------------------------------------


class TestPushAfterReconcile:
    """TS-36-6: After successful reconciliation, the push to origin succeeds.

    Requirement: 36-REQ-2.2
    """

    @pytest.mark.asyncio
    async def test_origin_matches_local_after_reconcile_push(
        self, tmp_path: Path
    ) -> None:
        """origin/develop HEAD matches local develop HEAD after push."""
        working, origin = _create_diverged_repo(tmp_path, conflicting=False)
        _run(["checkout", "develop"], cwd=working)

        await _push_develop_if_pushable(working)

        _run(["fetch", "origin"], cwd=working)
        assert _get_head(working, "develop") == _get_head(working, "origin/develop")


# ---------------------------------------------------------------------------
# TS-36-7: Post-Harvest Push Directly When Ahead
# ---------------------------------------------------------------------------


class TestPushWhenAhead:
    """TS-36-7: When local is ahead of origin (no divergence), push proceeds
    without reconciliation.

    Requirement: 36-REQ-2.4
    """

    @pytest.mark.asyncio
    async def test_push_when_local_ahead(self, tmp_path: Path) -> None:
        """Local ahead, no divergence -> push without reconciliation."""
        working, origin = _create_repo_with_origin(tmp_path)

        # Add local-only commits
        _run(["checkout", "develop"], cwd=working)
        _add_commit(working, "new_feature.py", "feature\n", "add feature")

        await _push_develop_if_pushable(working)

        # Fetch and verify origin matches
        _run(["fetch", "origin"], cwd=working)
        assert _get_head(working, "develop") == _get_head(working, "origin/develop")
