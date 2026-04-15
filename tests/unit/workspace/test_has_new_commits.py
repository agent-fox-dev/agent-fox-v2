"""Tests for has_new_commits().

Regression test for GitHub issue #338: git rev-list in has_new_commits()
crashes session on missing ref instead of returning False.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_fox.workspace.git import has_new_commits


class TestHasNewCommitsMissingRef:
    """Issue #338: has_new_commits returns False on missing ref instead of crashing."""

    @pytest.mark.asyncio
    async def test_returns_false_on_nonzero_exit(self) -> None:
        """When git rev-list fails (exit 128), return False instead of raising."""
        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(128, "", "fatal: bad revision 'develop..feature/x'"),
        ):
            result = await has_new_commits(Path("/repo"), "feature/x", "develop")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_commits_ahead(self) -> None:
        """Normal case: branch has commits ahead of base."""
        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(0, "3\n", ""),
        ):
            result = await has_new_commits(Path("/repo"), "feature/x", "develop")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_commits_ahead(self) -> None:
        """Branch is even with base — no new commits."""
        with patch(
            "agent_fox.workspace.git.run_git",
            new_callable=AsyncMock,
            return_value=(0, "0\n", ""),
        ):
            result = await has_new_commits(Path("/repo"), "feature/x", "develop")

        assert result is False
