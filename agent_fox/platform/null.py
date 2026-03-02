"""NullPlatform: direct merge to develop (no PRs).

Used when platform type is "none" (the default). Merges the feature branch
directly into the development branch using git commands.

Requirements: 10-REQ-2.1, 10-REQ-2.2, 10-REQ-2.3, 10-REQ-2.4, 10-REQ-2.5
"""

from __future__ import annotations

import asyncio
import logging
import subprocess  # noqa: F401

from agent_fox.core.errors import IntegrationError

logger = logging.getLogger(__name__)


class NullPlatform:
    """Direct-merge platform. No PRs, no gates.

    Used when platform type is "none" (the default). Merges the feature branch
    directly into the development branch using git commands.
    """

    def __init__(self, develop_branch: str = "develop") -> None:
        self._develop_branch = develop_branch

    async def create_pr(
        self,
        branch: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> str:
        """Merge branch directly into develop. Returns empty string."""
        logger.info("NullPlatform: merging %s into %s", branch, self._develop_branch)
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "checkout", self._develop_branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise IntegrationError(
                f"Failed to checkout {self._develop_branch}: {result.stderr}",
                branch=self._develop_branch,
            )
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "merge", "--no-ff", branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise IntegrationError(
                f"Failed to merge {branch}: {result.stderr}",
                branch=branch,
            )
        return ""

    async def wait_for_ci(self, pr_url: str, timeout: int) -> bool:
        """No CI to wait for. Always returns True."""
        return True

    async def wait_for_review(self, pr_url: str) -> bool:
        """No review to wait for. Always returns True."""
        return True

    async def merge_pr(self, pr_url: str) -> None:
        """No-op. Merge already happened in create_pr."""
        pass
