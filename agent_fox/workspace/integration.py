"""Post-harvest remote integration: push changes, create PRs.

Extracted from session_lifecycle.py to isolate platform integration
(GitHub, remote push) from the session lifecycle orchestration.

Requirements: 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3, 19-REQ-3.4,
              19-REQ-3.E1, 19-REQ-3.E2, 19-REQ-3.E3,
              19-REQ-4.E1, 19-REQ-4.E4
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from agent_fox.core.config import PlatformConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.workspace.workspace import (
    WorkspaceInfo,
    get_remote_url,
    local_branch_exists,
    push_to_remote,
)

logger = logging.getLogger(__name__)


async def post_harvest_integrate(
    repo_root: Path,
    workspace: WorkspaceInfo,
    platform_config: PlatformConfig,
) -> None:
    """Push changes to remote after harvest.

    Behavior depends on platform configuration:
    - type="none": push develop to origin
    - type="github", auto_merge=true: push feature + push develop
    - type="github", auto_merge=false: push feature + create PR vs default branch

    All remote operations are best-effort: failures are logged as
    warnings and never raised.

    Requirements: 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3, 19-REQ-3.4,
                  19-REQ-3.E1, 19-REQ-3.E2, 19-REQ-3.E3,
                  19-REQ-4.E1, 19-REQ-4.E4
    """
    from agent_fox.platform.github import GitHubPlatform, parse_github_remote

    feature_branch = workspace.branch

    if platform_config.type == "github":
        # Check for GITHUB_PAT — fall back to no-platform if missing
        token = os.environ.get("GITHUB_PAT")
        if not token:
            logger.warning(
                "GITHUB_PAT not set — falling back to pushing develop only",
            )
            # Fall back to no-platform behavior
            result = await push_to_remote(repo_root, "develop")
            if not result:
                logger.warning("Failed to push develop to origin")
            return

        # Parse remote URL for owner/repo
        remote_url = await get_remote_url(repo_root)
        if not remote_url:
            logger.warning(
                "Could not determine remote URL"
                " — falling back to pushing develop only",
            )
            result = await push_to_remote(repo_root, "develop")
            if not result:
                logger.warning("Failed to push develop to origin")
            return

        parsed = parse_github_remote(remote_url)
        if parsed is None:
            logger.warning(
                "Remote URL '%s' is not a GitHub URL"
                " — falling back to pushing develop only",
                remote_url,
            )
            result = await push_to_remote(repo_root, "develop")
            if not result:
                logger.warning("Failed to push develop to origin")
            return

        owner, repo = parsed

        # Push feature branch if it still exists locally (19-REQ-3.E3)
        if await local_branch_exists(repo_root, feature_branch):
            result = await push_to_remote(repo_root, feature_branch)
            if not result:
                logger.warning(
                    "Failed to push feature branch '%s' to origin",
                    feature_branch,
                )
        else:
            logger.warning(
                "Feature branch '%s' no longer exists locally — skipping push",
                feature_branch,
            )

        if platform_config.auto_merge:
            # 19-REQ-3.2: push develop too
            result = await push_to_remote(repo_root, "develop")
            if not result:
                logger.warning("Failed to push develop to origin")
        else:
            # 19-REQ-3.3: create PR, do NOT push develop
            platform = GitHubPlatform(owner=owner, repo=repo, token=token)
            try:
                spec = workspace.spec_name
                group = workspace.task_group
                pr_url = await platform.create_pr(
                    branch=feature_branch,
                    title=f"feat: {spec} task group {group}",
                    body=f"Automated PR for {spec} task group {group}.",
                )
                logger.info("Created PR: %s", pr_url)
            except (IntegrationError, Exception) as exc:
                logger.warning(
                    "PR creation failed for '%s': %s",
                    feature_branch,
                    exc,
                )
    else:
        # 19-REQ-3.1: type="none" — just push develop
        result = await push_to_remote(repo_root, "develop")
        if not result:
            logger.warning("Failed to push develop to origin")
