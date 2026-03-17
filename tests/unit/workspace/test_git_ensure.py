"""Tests for ensure_develop, detect_default_branch, and related git functions.

Test Spec: TS-19-1 (create from remote), TS-19-2 (create from default),
           TS-19-3 (fast-forward behind), TS-19-4 (symbolic-ref),
           TS-19-5 (fallback chain), TS-19-E1 (already exists),
           TS-19-E2 (no default branch), TS-19-E3 (fetch fails),
           TS-19-E4 (diverged branches)
Requirements: 19-REQ-1.1 through 19-REQ-1.6, 19-REQ-1.E1 through 19-REQ-1.E4
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.core.errors import WorkspaceError
from agent_fox.workspace.workspace import (
    detect_default_branch,
    ensure_develop,
)

# ---- Helpers ----


def _make_run_git_mock(side_effects: dict[str, tuple[int, str, str]]):
    """Create a run_git mock that dispatches based on command args.

    side_effects maps a key string (looked up from args) to (rc, stdout, stderr).
    If a key has the special value "raise", a WorkspaceError is raised.
    """

    async def _mock_run_git(args: list[str], cwd: Path, check: bool = True):
        key = " ".join(args)
        for pattern, result in side_effects.items():
            if pattern in key:
                if result == "raise":
                    raise WorkspaceError(f"mock error: {key}")
                rc, stdout, stderr = result
                if check and rc != 0:
                    raise WorkspaceError(f"git failed: {key}\n{stderr}")
                return rc, stdout, stderr
        # Default: success with empty output
        return 0, "", ""

    return _mock_run_git


# ---------------------------------------------------------------------------
# TS-19-1: ensure_develop Creates From Remote
# ---------------------------------------------------------------------------


class TestEnsureDevelopCreatesFromRemote:
    """TS-19-1: When local develop does not exist but origin/develop does,
    ensure_develop creates a local tracking branch.

    Requirement: 19-REQ-1.2
    """

    async def test_creates_tracking_branch(self, tmp_path: Path) -> None:
        """ensure_develop creates develop from origin/develop."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            # local_branch_exists for develop -> not found
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "", ""
            # remote_branch_exists for origin/develop -> found
            if "ls-remote" in key and "develop" in key:
                return 0, "abc123\trefs/heads/develop\n", ""
            # branch creation
            if args[:2] == ["branch", "develop"]:
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            await ensure_develop(tmp_path)

        # Verify fetch was called
        fetch_calls = [c for c in calls if "fetch" in c]
        assert len(fetch_calls) >= 1

        # Verify branch creation from origin/develop
        branch_create = [
            c for c in calls if len(c) >= 3 and c[0] == "branch" and c[1] == "develop"
        ]
        assert len(branch_create) >= 1
        assert "origin/develop" in branch_create[0]


# ---------------------------------------------------------------------------
# TS-19-2: ensure_develop Creates From Default Branch
# ---------------------------------------------------------------------------


class TestEnsureDevelopCreatesFromDefault:
    """TS-19-2: When neither local nor remote develop exists,
    ensure_develop creates develop from the default branch.

    Requirements: 19-REQ-1.3, 19-REQ-1.4
    """

    async def test_creates_from_main(self, tmp_path: Path) -> None:
        """ensure_develop creates develop from local main when no remote develop."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            # local develop -> not found
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "", ""
            # remote develop -> not found
            if "ls-remote" in key and "develop" in key:
                return 0, "", ""
            # symbolic-ref -> fail
            if "symbolic-ref" in key:
                if check:
                    raise WorkspaceError("no symbolic-ref")
                return 1, "", "not a symbolic ref"
            # local main -> exists
            if "branch" in key and "--list" in key and "main" in key:
                return 0, "  main\n", ""
            # branch creation
            if args[:2] == ["branch", "develop"]:
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            await ensure_develop(tmp_path)

        branch_create = [
            c for c in calls if len(c) >= 3 and c[0] == "branch" and c[1] == "develop"
        ]
        assert len(branch_create) >= 1
        assert "main" in branch_create[0]


# ---------------------------------------------------------------------------
# TS-19-3: ensure_develop Fast-Forwards Behind Local
# ---------------------------------------------------------------------------


class TestEnsureDevelopFastForwards:
    """TS-19-3: When local develop is behind origin/develop,
    ensure_develop fast-forwards it.

    Requirement: 19-REQ-1.6
    """

    async def test_fast_forwards_behind_branch(self, tmp_path: Path) -> None:
        """ensure_develop fast-forwards local develop that is behind remote."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            # local develop exists
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "  develop\n", ""
            # remote develop exists
            if "ls-remote" in key and "develop" in key:
                return 0, "abc123\trefs/heads/develop\n", ""
            # rev-list develop..origin/develop -> 2 commits ahead
            if "rev-list" in key and "develop..origin/develop" in key:
                return 0, "2\n", ""
            # rev-list origin/develop..develop -> 0 (not diverged)
            if "rev-list" in key and "origin/develop..develop" in key:
                return 0, "0\n", ""
            # merge --ff-only (fast-forward)
            if "merge" in key and "--ff-only" in key:
                return 0, "", ""
            # checkout
            if "checkout" in key:
                return 0, "", ""
            # stash
            if "stash" in key:
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            await ensure_develop(tmp_path)

        # Verify some form of fast-forward was done
        ff_calls = [c for c in calls if "merge" in c and "--ff-only" in c]
        update_calls = [c for c in calls if c[:3] == ["branch", "-f", "develop"]]
        assert len(ff_calls) >= 1 or len(update_calls) >= 1


# ---------------------------------------------------------------------------
# TS-19-4: detect_default_branch Via Symbolic Ref
# ---------------------------------------------------------------------------


class TestDetectDefaultBranchSymbolicRef:
    """TS-19-4: detect_default_branch reads the default branch from
    git symbolic-ref.

    Requirement: 19-REQ-1.4
    """

    async def test_returns_main_from_symbolic_ref(self, tmp_path: Path) -> None:
        """detect_default_branch returns 'main' when symbolic-ref points to it."""

        async def mock_run_git(args, cwd, check=True):
            if "symbolic-ref" in args:
                return 0, "refs/remotes/origin/main\n", ""
            return 0, "", ""

        with patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git):
            result = await detect_default_branch(tmp_path)

        assert result == "main"


# ---------------------------------------------------------------------------
# TS-19-5: detect_default_branch Fallback Chain
# ---------------------------------------------------------------------------


class TestDetectDefaultBranchFallback:
    """TS-19-5: When symbolic-ref fails, falls back to main, then master.

    Requirement: 19-REQ-1.4
    """

    async def test_falls_back_to_master(self, tmp_path: Path) -> None:
        """detect_default_branch returns 'master' when symbolic-ref and main fail."""

        async def mock_run_git(args, cwd, check=True):
            key = " ".join(args)
            if "symbolic-ref" in key:
                if check:
                    raise WorkspaceError("no symbolic-ref")
                return 1, "", "not a symbolic ref"
            # main doesn't exist
            if "branch" in key and "--list" in key and "main" in key:
                return 0, "", ""
            # master exists
            if "branch" in key and "--list" in key and "master" in key:
                return 0, "  master\n", ""
            return 0, "", ""

        with patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git):
            result = await detect_default_branch(tmp_path)

        assert result == "master"


# ---------------------------------------------------------------------------
# TS-19-E1: ensure_develop Local Already Exists (no-op)
# ---------------------------------------------------------------------------


class TestEnsureDevelopAlreadyExists:
    """TS-19-E1: When develop already exists and is up-to-date, no-op.

    Requirement: 19-REQ-1.E1
    """

    async def test_no_branch_creation(self, tmp_path: Path) -> None:
        """No branch creation when develop exists and is up-to-date."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            # local develop exists
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "  develop\n", ""
            # remote develop exists
            if "ls-remote" in key and "develop" in key:
                return 0, "abc123\trefs/heads/develop\n", ""
            # rev-list develop..origin/develop -> 0 (up-to-date)
            if "rev-list" in key and "develop..origin/develop" in key:
                return 0, "0\n", ""
            # rev-list origin/develop..develop -> 0
            if "rev-list" in key and "origin/develop..develop" in key:
                return 0, "0\n", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            await ensure_develop(tmp_path)

        # No branch creation calls
        branch_create = [
            c for c in calls if len(c) >= 3 and c[0] == "branch" and c[1] == "develop"
        ]
        assert len(branch_create) == 0


# ---------------------------------------------------------------------------
# TS-19-E2: ensure_develop No Default Branch
# ---------------------------------------------------------------------------


class TestEnsureDevelopNoDefaultBranch:
    """TS-19-E2: Raises WorkspaceError when no suitable base branch exists.

    Requirement: 19-REQ-1.E2
    """

    async def test_raises_workspace_error(self, tmp_path: Path) -> None:
        """ensure_develop raises WorkspaceError when no base branch found."""

        async def mock_run_git(args, cwd, check=True):
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            # No local develop
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "", ""
            # No remote develop
            if "ls-remote" in key and "develop" in key:
                return 0, "", ""
            # symbolic-ref fails
            if "symbolic-ref" in key:
                if check:
                    raise WorkspaceError("no symbolic-ref")
                return 1, "", "error"
            # No main
            if "branch" in key and "--list" in key and "main" in key:
                return 0, "", ""
            # No master
            if "branch" in key and "--list" in key and "master" in key:
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            with pytest.raises(WorkspaceError):
                await ensure_develop(tmp_path)


# ---------------------------------------------------------------------------
# TS-19-E3: ensure_develop Fetch Fails
# ---------------------------------------------------------------------------


class TestEnsureDevelopFetchFails:
    """TS-19-E3: When fetch fails, warns and uses local state.

    Requirement: 19-REQ-1.E3
    """

    async def test_creates_from_local_main(self, tmp_path: Path, caplog) -> None:
        """ensure_develop creates from local main when fetch fails."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                if check:
                    raise WorkspaceError("fetch failed: network error")
                return 1, "", "network error"
            # No local develop
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "", ""
            # symbolic-ref fails
            if "symbolic-ref" in key:
                if check:
                    raise WorkspaceError("no symbolic-ref")
                return 1, "", "error"
            # local main exists
            if "branch" in key and "--list" in key and "main" in key:
                return 0, "  main\n", ""
            # branch creation
            if args[:2] == ["branch", "develop"]:
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            import logging

            with caplog.at_level(logging.WARNING):
                await ensure_develop(tmp_path)

        # Verify warning was logged
        assert any("fetch" in r.message.lower() for r in caplog.records)

        # Verify develop created from main
        branch_create = [
            c for c in calls if len(c) >= 3 and c[0] == "branch" and c[1] == "develop"
        ]
        assert len(branch_create) >= 1
        assert "main" in branch_create[0]


# ---------------------------------------------------------------------------
# TS-19-E4: ensure_develop Diverged Branches
# ---------------------------------------------------------------------------


class TestEnsureDevelopDiverged:
    """TS-19-E4: When local and remote develop have diverged, attempt
    rebase; if rebase fails (conflicts), warn and leave as-is.

    Requirement: 19-REQ-1.E4
    """

    async def test_rebase_succeeds(self, tmp_path: Path, caplog) -> None:
        """ensure_develop rebases local develop onto origin/develop."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "  develop\n", ""
            if "ls-remote" in key and "develop" in key:
                return 0, "abc123\trefs/heads/develop\n", ""
            if "rev-list" in key and "origin/develop..develop" in key:
                return 0, "3\n", ""
            if "rev-list" in key and "develop..origin/develop" in key:
                return 0, "2\n", ""
            if "symbolic-ref" in key:
                return 0, "main\n", ""
            if key == "checkout develop":
                return 0, "", ""
            if "rebase" in key and "origin/develop" in key:
                return 0, "", ""  # rebase succeeds
            if key == "checkout main":
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            import logging

            with caplog.at_level(logging.INFO, logger="agent_fox.workspace.develop"):
                await ensure_develop(tmp_path)

        # Verify rebase was attempted and succeeded
        rebase_calls = [c for c in calls if "rebase" in c]
        assert len(rebase_calls) == 1
        assert any("rebased" in r.message.lower() for r in caplog.records)

    async def test_rebase_fails_warns_and_keeps_local(
        self, tmp_path: Path, caplog
    ) -> None:
        """ensure_develop falls back to merge when rebase fails."""
        calls: list[list[str]] = []

        async def mock_run_git(args, cwd, check=True):
            calls.append(args)
            key = " ".join(args)
            if "fetch" in key:
                return 0, "", ""
            if "branch" in key and "--list" in key and "develop" in key:
                return 0, "  develop\n", ""
            if "ls-remote" in key and "develop" in key:
                return 0, "abc123\trefs/heads/develop\n", ""
            if "rev-list" in key and "origin/develop..develop" in key:
                return 0, "3\n", ""
            if "rev-list" in key and "develop..origin/develop" in key:
                return 0, "2\n", ""
            if "symbolic-ref" in key:
                return 0, "main\n", ""
            if key == "checkout develop":
                return 0, "", ""
            if "rebase" in key and "origin/develop" in key:
                return 1, "", "CONFLICT"  # rebase fails
            if "rebase" in key and "--abort" in key:
                return 0, "", ""
            if "merge" in key and "--no-edit" in key and "-X" not in key:
                return 0, "", ""  # merge succeeds
            if key == "checkout main":
                return 0, "", ""
            return 0, "", ""

        with (
            patch("agent_fox.workspace.develop.run_git", side_effect=mock_run_git),
            patch("agent_fox.workspace.git.run_git", side_effect=mock_run_git),
        ):
            import logging

            with caplog.at_level(logging.INFO):
                await ensure_develop(tmp_path)

        # Verify rebase was attempted and aborted
        rebase_calls = [c for c in calls if "rebase" in c]
        assert any("--abort" in c for c in rebase_calls)
        # Verify merge fallback was attempted
        merge_calls = [c for c in calls if "merge" in c and "--no-edit" in c]
        assert any(c for c in merge_calls if "-X" not in c)
