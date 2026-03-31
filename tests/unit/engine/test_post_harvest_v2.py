"""Tests for simplified post-harvest integration — spec 65.

Test Spec: TS-65-7 through TS-65-11, TS-65-E3
Requirements: 65-REQ-3.1, 65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4, 65-REQ-3.5,
              65-REQ-3.E1
"""

from __future__ import annotations

import inspect
import logging
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
# TS-65-7: Post-harvest pushes feature branch
# ---------------------------------------------------------------------------


class TestPostHarvestPushesFeature:
    """TS-65-7: post_harvest_integrate pushes the feature branch to origin.

    Requirement: 65-REQ-3.1
    """

    async def test_pushes_feature_branch(self, tmp_path: Path) -> None:
        """post_harvest_integrate calls push_to_remote with the feature branch."""
        workspace = _make_workspace()
        push_calls: list[tuple] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append((repo_root, branch))
            return True

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
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

        pushed_branches = [branch for _, branch in push_calls]
        assert workspace.branch in pushed_branches


# ---------------------------------------------------------------------------
# TS-65-8: Post-harvest pushes develop
# ---------------------------------------------------------------------------


class TestPostHarvestPushesDevelop:
    """TS-65-8: post_harvest_integrate pushes develop to origin.

    Requirement: 65-REQ-3.2
    """

    async def test_pushes_develop(self, tmp_path: Path) -> None:
        """post_harvest_integrate calls _push_develop_if_pushable."""
        workspace = _make_workspace()

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                return_value=True,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
            ),
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
# TS-65-9: Post-harvest has no platform_config parameter
# ---------------------------------------------------------------------------


class TestPostHarvestNoPlatformConfigParam:
    """TS-65-9: post_harvest_integrate signature has no platform_config param.

    Requirement: 65-REQ-3.3
    """

    def test_no_platform_config_param(self) -> None:
        """post_harvest_integrate does not accept platform_config."""
        sig = inspect.signature(post_harvest_integrate)
        assert "platform_config" not in sig.parameters


# ---------------------------------------------------------------------------
# TS-65-10: Post-harvest does not import GitHubPlatform
# ---------------------------------------------------------------------------


class TestPostHarvestNoGitHubPlatformRef:
    """TS-65-10: post_harvest_integrate source has no GitHubPlatform references.

    Requirement: 65-REQ-3.4
    """

    def test_no_github_platform_ref(self) -> None:
        """Source of post_harvest_integrate does not contain GitHubPlatform."""
        source = inspect.getsource(post_harvest_integrate)
        assert "GitHubPlatform" not in source


# ---------------------------------------------------------------------------
# TS-65-11: Post-harvest push failure is best-effort
# ---------------------------------------------------------------------------


class TestPostHarvestPushFailureBestEffort:
    """TS-65-11: Push failure logs warning but does not raise exception.

    Requirement: 65-REQ-3.5
    """

    async def test_push_failure_no_exception(self, tmp_path: Path, caplog) -> None:
        """Push failure is swallowed — no exception raised."""
        workspace = _make_workspace()

        async def mock_push(repo_root, branch, remote="origin"):
            return False  # simulate push failure

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
            ),
            patch(
                "agent_fox.workspace.harvest._push_develop_if_pushable",
                new_callable=AsyncMock,
            ),
        ):
            with caplog.at_level(logging.WARNING):
                # Must not raise
                await post_harvest_integrate(
                    repo_root=tmp_path,
                    workspace=workspace,
                )

        # Warning must be logged
        assert any(r.levelno >= logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-65-E3: Feature branch deleted before post-harvest
# ---------------------------------------------------------------------------


class TestPostHarvestFeatureBranchDeleted:
    """TS-65-E3: Deleted feature branch is skipped; develop still pushed.

    Requirement: 65-REQ-3.E1
    """

    async def test_feature_branch_deleted(self, tmp_path: Path, caplog) -> None:
        """When feature branch is gone, skip its push; still push develop."""
        workspace = _make_workspace()
        push_calls: list[str] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
            return True

        async def mock_local_exists(repo_root, branch):
            # Feature branch does not exist locally
            return branch != workspace.branch

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                side_effect=mock_local_exists,
            ),
            patch(
                "agent_fox.workspace.harvest._push_develop_if_pushable",
                new_callable=AsyncMock,
            ) as mock_push_develop,
        ):
            with caplog.at_level(logging.WARNING):
                await post_harvest_integrate(
                    repo_root=tmp_path,
                    workspace=workspace,
                )

        # Feature branch push must NOT happen
        assert workspace.branch not in push_calls
        # Develop push must still be attempted
        mock_push_develop.assert_called_once_with(tmp_path)
        # Warning must be logged about missing branch
        assert any(r.levelno >= logging.WARNING for r in caplog.records)
