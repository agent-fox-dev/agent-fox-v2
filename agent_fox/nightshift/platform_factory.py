"""Platform factory: instantiate platform from config.

Requirements: 61-REQ-8.3, 61-REQ-8.E1
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from agent_fox.platform.github import GitHubPlatform, parse_github_remote

logger = logging.getLogger(__name__)

_SUPPORTED_PLATFORMS = {"github"}


def create_platform(config: object, project_root: Path) -> GitHubPlatform:
    """Create a platform instance from configuration.

    Requirements: 61-REQ-8.3, 61-REQ-8.E1
    """
    platform_cfg = getattr(config, "platform", None)
    platform_type = getattr(platform_cfg, "type", "none")

    if platform_type == "none":
        logger.error("Night-shift requires a configured platform. Set [platform] type = 'github' in your config.")
        sys.exit(1)

    if platform_type not in _SUPPORTED_PLATFORMS:
        logger.error(
            "Unsupported platform type '%s'. Supported types: %s",
            platform_type,
            ", ".join(sorted(_SUPPORTED_PLATFORMS)),
        )
        sys.exit(1)

    token = os.environ.get("GITHUB_PAT", "")
    if not token:
        logger.error("GITHUB_PAT environment variable is required")
        sys.exit(1)

    # Try to detect owner/repo from git remote
    owner, repo = "owner", "repo"
    try:
        import subprocess

        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        if result.returncode == 0:
            parsed = parse_github_remote(result.stdout.strip())
            if parsed:
                owner, repo = parsed
    except Exception:
        pass

    url = getattr(platform_cfg, "url", "") or "github.com"
    return GitHubPlatform(owner=owner, repo=repo, token=token, url=url)
