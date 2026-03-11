"""Tests for post-harvest remote integration.

Test Spec: TS-19-10 (no platform pushes develop), TS-19-11 (github auto_merge),
           TS-19-12 (github no auto_merge creates PR),
           TS-19-E5 (push failure continues), TS-19-E6 (PR failure continues),
           TS-19-E7 (GITHUB_PAT not set falls back),
           TS-19-E11 (feature branch deleted)
Requirements: 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3, 19-REQ-3.E1,
              19-REQ-3.E2, 19-REQ-3.E3, 19-REQ-4.E1
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from agent_fox.core.config import PlatformConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.harvest import post_harvest_integrate
from agent_fox.workspace.workspace import WorkspaceInfo

# ---- Helper to create a minimal workspace ----

def _make_workspace(branch: str = "feature/test_spec/1") -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/test-worktree"),
        branch=branch,
        spec_name="test_spec",
        task_group=1,
    )


# ---------------------------------------------------------------------------
# TS-19-10: Post-Harvest No Platform Pushes Develop
# ---------------------------------------------------------------------------


class TestPostHarvestNoPlatform:
    """TS-19-10: With no platform (type="none"), post-harvest pushes develop.

    Requirement: 19-REQ-3.1
    """

    async def test_pushes_develop_only(self, tmp_path: Path) -> None:
        """Post-harvest with type=none pushes develop to origin."""
        config = PlatformConfig(type="none")
        workspace = _make_workspace()
        push_calls: list[str] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
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
        ):
            await post_harvest_integrate(
                repo_root=tmp_path,
                workspace=workspace,
                platform_config=config,
            )

        assert "develop" in push_calls
        # No PR should be created — we just need develop pushed


# ---------------------------------------------------------------------------
# TS-19-11: Post-Harvest GitHub Auto-Merge Pushes Both
# ---------------------------------------------------------------------------


class TestPostHarvestGithubAutoMerge:
    """TS-19-11: With github + auto_merge=true, post-harvest pushes feature
    branch and develop.

    Requirement: 19-REQ-3.2
    """

    async def test_pushes_feature_and_develop(self, tmp_path: Path) -> None:
        """Post-harvest with github + auto_merge pushes both branches."""
        config = PlatformConfig(type="github", auto_merge=True)
        workspace = _make_workspace()
        push_calls: list[str] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
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
            patch.dict("os.environ", {"GITHUB_PAT": "test-token"}),
            patch(
                "agent_fox.workspace.harvest.get_remote_url",
                return_value="https://github.com/owner/repo.git",
            ),
        ):
            await post_harvest_integrate(
                repo_root=tmp_path,
                workspace=workspace,
                platform_config=config,
            )

        assert workspace.branch in push_calls
        assert "develop" in push_calls


# ---------------------------------------------------------------------------
# TS-19-12: Post-Harvest GitHub No Auto-Merge Creates PR
# ---------------------------------------------------------------------------


class TestPostHarvestGithubCreatePR:
    """TS-19-12: With github + auto_merge=false, post-harvest pushes feature
    branch and creates a PR against main.

    Requirement: 19-REQ-3.3
    """

    async def test_pushes_feature_and_creates_pr(self, tmp_path: Path) -> None:
        """Post-harvest creates PR and does NOT push develop."""
        config = PlatformConfig(type="github", auto_merge=False)
        workspace = _make_workspace()
        push_calls: list[str] = []
        pr_created = False

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
            return True

        async def mock_create_pr(self_inner, branch, title, body):
            nonlocal pr_created
            pr_created = True
            return "https://github.com/owner/repo/pull/1"

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
            ),
            patch.dict("os.environ", {"GITHUB_PAT": "test-token"}),
            patch(
                "agent_fox.workspace.harvest.get_remote_url",
                return_value="https://github.com/owner/repo.git",
            ),
            patch(
                "agent_fox.platform.github.GitHubPlatform.create_pr",
                mock_create_pr,
            ),
        ):
            await post_harvest_integrate(
                repo_root=tmp_path,
                workspace=workspace,
                platform_config=config,
            )

        assert workspace.branch in push_calls
        assert "develop" not in push_calls
        assert pr_created is True


# ---------------------------------------------------------------------------
# TS-19-E5: Post-Harvest Push Failure Continues
# ---------------------------------------------------------------------------


class TestPostHarvestPushFailureContinues:
    """TS-19-E5: When push fails, log warning and continue.

    Requirement: 19-REQ-3.E1
    """

    async def test_no_exception_on_push_failure(
        self, tmp_path: Path, caplog
    ) -> None:
        """Post-harvest doesn't raise when push fails."""
        config = PlatformConfig(type="none")
        workspace = _make_workspace()

        async def mock_push(repo_root, branch, remote="origin"):
            return False  # push failed

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
            ),
        ):
            with caplog.at_level(logging.WARNING):
                # Should not raise
                await post_harvest_integrate(
                    repo_root=tmp_path,
                    workspace=workspace,
                    platform_config=config,
                )


# ---------------------------------------------------------------------------
# TS-19-E6: Post-Harvest PR Creation Failure Continues
# ---------------------------------------------------------------------------


class TestPostHarvestPRFailureContinues:
    """TS-19-E6: When PR creation fails, log warning and continue.

    Requirement: 19-REQ-3.E2
    """

    async def test_no_exception_on_pr_failure(
        self, tmp_path: Path, caplog
    ) -> None:
        """Post-harvest doesn't raise when PR creation fails."""
        config = PlatformConfig(type="github", auto_merge=False)
        workspace = _make_workspace()

        async def mock_push(repo_root, branch, remote="origin"):
            return True

        async def mock_create_pr(self_inner, branch, title, body):
            raise IntegrationError("API error")

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
            ),
            patch.dict("os.environ", {"GITHUB_PAT": "test-token"}),
            patch(
                "agent_fox.workspace.harvest.get_remote_url",
                return_value="https://github.com/owner/repo.git",
            ),
            patch(
                "agent_fox.platform.github.GitHubPlatform.create_pr",
                mock_create_pr,
            ),
        ):
            with caplog.at_level(logging.WARNING):
                # Should not raise
                await post_harvest_integrate(
                    repo_root=tmp_path,
                    workspace=workspace,
                    platform_config=config,
                )


# ---------------------------------------------------------------------------
# TS-19-E7: GITHUB_PAT Not Set Falls Back
# ---------------------------------------------------------------------------


class TestPostHarvestMissingPAT:
    """TS-19-E7: Missing GITHUB_PAT causes fallback to no-platform behavior.

    Requirement: 19-REQ-4.E1
    """

    async def test_falls_back_to_push_develop(
        self, tmp_path: Path, caplog
    ) -> None:
        """Without GITHUB_PAT, falls back to pushing develop only."""
        config = PlatformConfig(type="github", auto_merge=False)
        workspace = _make_workspace()
        push_calls: list[str] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
            return True

        env_without_pat = {k: v for k, v in __import__("os").environ.items()}
        env_without_pat.pop("GITHUB_PAT", None)

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                return_value=True,
            ),
            patch.dict("os.environ", env_without_pat, clear=True),
        ):
            with caplog.at_level(logging.WARNING):
                await post_harvest_integrate(
                    repo_root=tmp_path,
                    workspace=workspace,
                    platform_config=config,
                )

        # Should fall back to pushing develop
        assert "develop" in push_calls
        # Warning about missing token
        assert any(
            "github_pat" in r.message.lower() or "token" in r.message.lower()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# TS-19-E11: Feature Branch Deleted Before Push
# ---------------------------------------------------------------------------


class TestPostHarvestFeatureBranchDeleted:
    """TS-19-E11: If feature branch no longer exists locally, skip pushing it.

    Requirement: 19-REQ-3.E3
    """

    async def test_skips_feature_push(
        self, tmp_path: Path, caplog
    ) -> None:
        """Post-harvest skips feature branch push when branch deleted."""
        config = PlatformConfig(type="github", auto_merge=True)
        workspace = _make_workspace()
        push_calls: list[str] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
            return True

        async def mock_local_exists(repo_root, branch):
            # Feature branch doesn't exist, but develop does
            return branch == "develop"

        with (
            patch(
                "agent_fox.workspace.harvest.push_to_remote",
                side_effect=mock_push,
            ),
            patch(
                "agent_fox.workspace.harvest.local_branch_exists",
                side_effect=mock_local_exists,
            ),
            patch.dict("os.environ", {"GITHUB_PAT": "test-token"}),
            patch(
                "agent_fox.workspace.harvest.get_remote_url",
                return_value="https://github.com/owner/repo.git",
            ),
        ):
            with caplog.at_level(logging.WARNING):
                await post_harvest_integrate(
                    repo_root=tmp_path,
                    workspace=workspace,
                    platform_config=config,
                )

        # Feature branch should NOT be pushed
        assert workspace.branch not in push_calls
        # Develop should still be pushed
        assert "develop" in push_calls
