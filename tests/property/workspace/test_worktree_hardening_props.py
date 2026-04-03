"""Property tests for worktree cleanup hardening.

Test Spec: TS-80-P1, TS-80-P2, TS-80-P3
Properties: Property 5 (porcelain parsing), Property 4 (ancestor cleanup),
            Property 2 (delete_branch stale safety)
Requirements: 80-REQ-1.3, 80-REQ-3.1, 80-REQ-3.E1, 80-REQ-2.1, 80-REQ-2.2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.errors import WorkspaceError

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid git ref name characters (simplified, alphanumeric + safe separators)
_branch_name_strategy = st.from_regex(
    r"[a-z][a-z0-9/_-]{0,30}",
    fullmatch=True,
)

# Path-like strings for worktree paths in porcelain output
_path_strategy = st.from_regex(r"/[a-z0-9/_.-]{1,40}", fullmatch=True)

# Short hex SHA
_sha_strategy = st.from_regex(r"[0-9a-f]{7}", fullmatch=True)


@dataclass
class _WorktreeEntry:
    """Represents one entry in porcelain output."""

    path: str
    head_sha: str
    branch_ref: str | None  # None = detached HEAD


def _build_porcelain(entries: list[_WorktreeEntry]) -> str:
    """Build a git worktree list --porcelain string from entries."""
    parts: list[str] = []
    for e in entries:
        lines = [f"worktree {e.path}", f"HEAD {e.head_sha}"]
        if e.branch_ref is not None:
            lines.append(f"branch {e.branch_ref}")
        else:
            lines.append("detached")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts) + "\n"


_worktree_entry_strategy = st.builds(
    _WorktreeEntry,
    path=_path_strategy,
    head_sha=_sha_strategy,
    branch_ref=st.one_of(
        st.none(),
        st.from_regex(r"refs/heads/[a-z][a-z0-9/_-]{0,20}", fullmatch=True),
    ),
)


# ---------------------------------------------------------------------------
# TS-80-P1: Porcelain Parsing Accuracy
# Property 5 from design.md
# Requirement: 80-REQ-1.3
# ---------------------------------------------------------------------------


class TestPorcelainParsingAccuracy:
    """TS-80-P1: branch_used_by_worktree correctly detects branch in porcelain output."""

    @given(
        branch_name=_branch_name_strategy,
        entries=st.lists(_worktree_entry_strategy, min_size=0, max_size=5),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_result_matches_presence_in_porcelain(
        self,
        branch_name: str,
        entries: list[_WorktreeEntry],
    ) -> None:
        """TS-80-P1: Returns True iff branch appears in any porcelain branch line."""
        from agent_fox.workspace.git import branch_used_by_worktree

        # Skip branch names that would fail ref validation
        assume(branch_name and not branch_name.startswith("-"))

        porcelain = _build_porcelain(entries)
        expected = any(
            e.branch_ref == f"refs/heads/{branch_name}" for e in entries
        )

        mock_run_git = AsyncMock(return_value=(0, porcelain, ""))
        with patch("agent_fox.workspace.git.run_git", mock_run_git):
            result = asyncio.get_event_loop().run_until_complete(
                branch_used_by_worktree(Path("/repo"), branch_name)
            )

        assert result == expected, (
            f"branch_used_by_worktree({branch_name!r}) returned {result}, "
            f"expected {expected}. Porcelain:\n{porcelain}"
        )

    @given(
        branch_name=_branch_name_strategy,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_empty_porcelain_returns_false(self, branch_name: str) -> None:
        """TS-80-P1: Empty porcelain output always returns False."""
        from agent_fox.workspace.git import branch_used_by_worktree

        assume(branch_name and not branch_name.startswith("-"))

        mock_run_git = AsyncMock(return_value=(0, "", ""))
        with patch("agent_fox.workspace.git.run_git", mock_run_git):
            result = asyncio.get_event_loop().run_until_complete(
                branch_used_by_worktree(Path("/repo"), branch_name)
            )

        assert result is False


# ---------------------------------------------------------------------------
# TS-80-P2: Ancestor Cleanup Safety
# Property 4 from design.md
# Requirements: 80-REQ-3.1, 80-REQ-3.E1
# ---------------------------------------------------------------------------


@dataclass
class _DirTree:
    """Simple directory tree for property tests."""

    # Relative paths to directories that should be non-empty (have a file)
    non_empty: list[str]
    # Relative paths to empty directories (target is last one)
    empty_chain: list[str]


def _non_empty_dir_strategy() -> st.SearchStrategy[list[str]]:
    """Generate a list of non-empty directory paths."""
    return st.lists(
        st.from_regex(r"[a-z][a-z0-9]{0,8}/[a-z][a-z0-9]{0,8}", fullmatch=True),
        min_size=0,
        max_size=3,
    )


def _empty_chain_strategy() -> st.SearchStrategy[list[str]]:
    """Generate a chain of nested empty directories (depth 1-3)."""
    return st.lists(
        st.from_regex(r"[a-z][a-z0-9]{0,8}", fullmatch=True),
        min_size=1,
        max_size=3,
        unique=True,
    )


class TestAncestorCleanupSafety:
    """TS-80-P2: Ancestor cleanup never removes non-empty dirs or the root."""

    @given(
        non_empty_dirs=_non_empty_dir_strategy(),
        chain=_empty_chain_strategy(),
    )
    @settings(
        max_examples=80,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_root_always_preserved(
        self,
        tmp_path: Path,
        non_empty_dirs: list[str],
        chain: list[str],
    ) -> None:
        """TS-80-P2: Root directory is never removed by _cleanup_empty_ancestors."""
        from agent_fox.workspace.worktree import _cleanup_empty_ancestors

        root = tmp_path / "worktrees"
        root.mkdir(parents=True, exist_ok=True)

        # Create the empty chain (target is deepest dir)
        target = root
        for part in chain:
            target = target / part
        target.mkdir(parents=True, exist_ok=True)

        # Create non-empty sibling dirs with a file inside
        for rel_path in non_empty_dirs:
            d = root / rel_path
            d.mkdir(parents=True, exist_ok=True)
            (d / "placeholder.txt").write_text("x")

        _cleanup_empty_ancestors(target, root)

        assert root.exists(), "Root must never be removed"

    @given(
        chain=_empty_chain_strategy(),
    )
    @settings(
        max_examples=80,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_non_empty_ancestor_preserved(
        self,
        tmp_path: Path,
        chain: list[str],
    ) -> None:
        """TS-80-P2: Non-empty ancestor directories are never removed."""
        from agent_fox.workspace.worktree import _cleanup_empty_ancestors

        assume(len(chain) >= 2)

        root = tmp_path / "worktrees"
        root.mkdir(parents=True, exist_ok=True)

        # Build chain but make an intermediate directory non-empty
        intermediate = root / chain[0]
        intermediate.mkdir(parents=True, exist_ok=True)
        # Add a sibling file to make intermediate non-empty
        (intermediate / "sibling.txt").write_text("occupied")

        # Build the full target path
        target = intermediate
        for part in chain[1:]:
            target = target / part
        target.mkdir(parents=True, exist_ok=True)

        _cleanup_empty_ancestors(target, root)

        # The intermediate dir has sibling.txt — must not be removed
        assert intermediate.exists(), (
            f"Non-empty intermediate directory {intermediate} must be preserved"
        )


# ---------------------------------------------------------------------------
# TS-80-P3: delete_branch Never Raises on Stale Worktree
# Property 2 from design.md
# Requirements: 80-REQ-2.1, 80-REQ-2.2
# ---------------------------------------------------------------------------

# Strategy for non-existent paths (start with /nonexistent)
_nonexistent_path_strategy = st.from_regex(
    r"/nonexistent/[a-z0-9/_-]{1,30}",
    fullmatch=True,
)


class TestDeleteBranchNeverRaisesOnStaleWorktree:
    """TS-80-P3: delete_branch does not raise when 'used by worktree' path is absent."""

    @given(
        branch_name=_branch_name_strategy,
        worktree_path=_nonexistent_path_strategy,
    )
    @settings(
        max_examples=60,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_no_exception_for_nonexistent_worktree_path(
        self,
        tmp_path: Path,
        branch_name: str,
        worktree_path: str,
    ) -> None:
        """TS-80-P3: delete_branch returns normally when 'used by worktree' path absent."""
        from agent_fox.workspace.git import delete_branch

        assume(branch_name and not branch_name.startswith("-"))
        # Ensure the path genuinely does not exist
        assume(not Path(worktree_path).exists())

        used_by_err = (
            f"error: Cannot delete branch '{branch_name}' "
            f"used by worktree at '{worktree_path}'\n"
        )
        call_responses: list[tuple[int, str, str]] = [
            # First delete attempt: fails with "used by worktree"
            (1, "", used_by_err),
            # git worktree prune: succeeds
            (0, "", ""),
            # Retry delete: also fails (worst case)
            (1, "", used_by_err),
        ]
        mock_run_git = AsyncMock(side_effect=call_responses)

        with patch("agent_fox.workspace.git.run_git", mock_run_git):
            # Must NOT raise WorkspaceError
            try:
                asyncio.get_event_loop().run_until_complete(
                    delete_branch(tmp_path, branch_name, force=True)
                )
            except WorkspaceError as exc:
                pytest.fail(
                    f"delete_branch raised WorkspaceError for stale worktree: {exc}"
                )
