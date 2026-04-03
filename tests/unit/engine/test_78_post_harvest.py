"""Tests for local-only feature branch post-harvest integration — spec 78.

Test Spec: TS-78-1 through TS-78-3, TS-78-E1
Requirements: 78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.3, 78-REQ-1.E1
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_fox.workspace import WorkspaceInfo
from agent_fox.workspace.harvest import post_harvest_integrate

# ---- Helper to create a minimal workspace ----


def _make_workspace(branch: str = "feature/test_spec/1") -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/test-worktree"),
        branch=branch,
        spec_name="test_spec",
        task_group=1,
    )


# ---------------------------------------------------------------------------
# TS-78-1: Post-harvest does not call push_to_remote directly
# ---------------------------------------------------------------------------


class TestPostHarvestDoesNotPushFeatureBranch:
    """TS-78-1: post_harvest_integrate never calls push_to_remote directly.

    Requirement: 78-REQ-1.1
    """

    async def test_does_not_push_feature_branch(self, tmp_path: Path) -> None:
        """push_to_remote must not be called at all by post_harvest_integrate."""
        workspace = _make_workspace()
        mock_push_remote = AsyncMock(return_value=True)

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                mock_push_remote,
            ),
            patch(
                "agent_fox.workspace.harvest._push_develop_if_pushable",
                new_callable=AsyncMock,
            ),
        ):
            await post_harvest_integrate(
                repo_root=tmp_path,
                workspace=workspace,
            )

        # push_to_remote must NOT be called directly — _push_develop_if_pushable
        # is separately mocked, so any direct call is a violation.
        assert mock_push_remote.call_count == 0


# ---------------------------------------------------------------------------
# TS-78-2: Post-harvest calls _push_develop_if_pushable
# ---------------------------------------------------------------------------


class TestPostHarvestPushesDevelop:
    """TS-78-2: post_harvest_integrate calls _push_develop_if_pushable.

    Requirement: 78-REQ-1.2
    """

    async def test_pushes_develop(self, tmp_path: Path) -> None:
        """post_harvest_integrate calls _push_develop_if_pushable exactly once."""
        workspace = _make_workspace()

        with (
            patch(
                "agent_fox.workspace.harvest._push_develop_if_pushable",
                new_callable=AsyncMock,
            ) as mock_push_develop,
        ):
            await post_harvest_integrate(
                repo_root=tmp_path,
                workspace=workspace,
            )

        mock_push_develop.assert_called_once_with(tmp_path)


# ---------------------------------------------------------------------------
# TS-78-3: Post-harvest does not call local_branch_exists
# ---------------------------------------------------------------------------


class TestPostHarvestDoesNotCheckBranchExistence:
    """TS-78-3: post_harvest_integrate does not call local_branch_exists.

    Requirement: 78-REQ-1.3
    """

    def test_does_not_check_branch_existence(self) -> None:
        """local_branch_exists must not be imported in the harvest module."""
        import agent_fox.workspace.harvest as harvest_mod

        assert not hasattr(harvest_mod, "local_branch_exists"), (
            "harvest module still imports local_branch_exists; "
            "feature branch existence check must be removed (78-REQ-1.3)"
        )


# ---------------------------------------------------------------------------
# TS-78-E1: Post-harvest with deleted feature branch still pushes develop
# ---------------------------------------------------------------------------


class TestPostHarvestDeletedBranchStillPushesDevelop:
    """TS-78-E1: Even with a deleted feature branch, develop is still pushed.

    Requirement: 78-REQ-1.E1
    """

    async def test_deleted_branch_still_pushes_develop(self, tmp_path: Path) -> None:
        """No exception raised; _push_develop_if_pushable still called."""
        workspace = _make_workspace(branch="feature/deleted/1")

        with (
            patch(
                "agent_fox.workspace.harvest._push_develop_if_pushable",
                new_callable=AsyncMock,
            ) as mock_push_develop,
        ):
            # Must not raise even with a "deleted" branch
            await post_harvest_integrate(
                repo_root=tmp_path,
                workspace=workspace,
            )

        mock_push_develop.assert_called_once_with(tmp_path)
