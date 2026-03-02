"""GitHubPlatform: GitHub PR operations using the gh CLI.

Creates pull requests, polls for CI status and review approval,
and merges PRs through the gh command-line tool.

Requirements: 10-REQ-3.1, 10-REQ-3.2, 10-REQ-3.3, 10-REQ-3.4, 10-REQ-3.5,
              10-REQ-3.E1, 10-REQ-3.E2, 10-REQ-3.E3, 10-REQ-3.E4,
              10-REQ-3.E5, 10-REQ-3.E6
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil  # noqa: F401
import subprocess  # noqa: F401
import time

from agent_fox.core.errors import IntegrationError

logger = logging.getLogger(__name__)

_CI_POLL_INTERVAL = 30  # seconds between CI check polls
_REVIEW_POLL_INTERVAL = 60  # seconds between review status polls


class GitHubPlatform:
    """GitHub platform using the gh CLI.

    Creates pull requests, polls for CI status and review approval,
    and merges PRs through the gh command-line tool.
    """

    def __init__(
        self,
        ci_timeout: int = 600,
        auto_merge: bool = False,
        base_branch: str = "develop",
    ) -> None:
        self._ci_timeout = ci_timeout
        self._auto_merge = auto_merge
        self._base_branch = base_branch
        self._verify_gh_available()

    def _verify_gh_available(self) -> None:
        """Check that gh CLI is installed and authenticated."""
        if shutil.which("gh") is None:
            raise IntegrationError(
                "The 'gh' CLI is not installed. Install it from "
                "https://cli.github.com/ and run 'gh auth login'.",
            )
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise IntegrationError(
                "The 'gh' CLI is not authenticated. Run 'gh auth login' first.",
                details=result.stderr,
            )

    async def _run_gh(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a gh CLI command asynchronously."""
        return await asyncio.to_thread(
            subprocess.run,
            ["gh", *args],
            capture_output=True,
            text=True,
        )

    async def create_pr(
        self,
        branch: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> str:
        """Create a GitHub PR using gh pr create."""
        cmd = [
            "pr",
            "create",
            "--head",
            branch,
            "--base",
            self._base_branch,
            "--title",
            title,
            "--body",
            body,
        ]
        for label in labels:
            cmd.extend(["--label", label])
        result = await self._run_gh(cmd)
        if result.returncode != 0:
            raise IntegrationError(
                f"Failed to create PR for branch {branch}: {result.stderr}",
                branch=branch,
                command="gh pr create",
            )
        pr_url = result.stdout.strip()
        logger.info("Created PR: %s", pr_url)
        if self._auto_merge:
            await self._run_gh(["pr", "merge", pr_url, "--auto", "--merge"])
        return pr_url

    async def wait_for_ci(self, pr_url: str, timeout: int) -> bool:
        """Poll gh pr checks until all pass, any fail, or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await self._run_gh(
                ["pr", "checks", pr_url, "--json", "name,state,conclusion"],
            )
            if result.returncode != 0:
                logger.warning("Failed to fetch CI checks: %s", result.stderr)
                await asyncio.sleep(_CI_POLL_INTERVAL)
                continue
            try:
                checks = json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning("Failed to parse CI checks output")
                await asyncio.sleep(_CI_POLL_INTERVAL)
                continue
            if not checks:
                # No checks configured; treat as pass
                return True
            all_complete = all(c.get("state") == "completed" for c in checks)
            if all_complete:
                any_failed = any(
                    c.get("conclusion") not in ("success", "skipped", "neutral")
                    for c in checks
                )
                return not any_failed
            await asyncio.sleep(_CI_POLL_INTERVAL)
        logger.warning("CI timeout after %d seconds for %s", timeout, pr_url)
        return False

    async def wait_for_review(self, pr_url: str) -> bool:
        """Poll gh pr view until approved or changes requested."""
        while True:
            result = await self._run_gh(
                ["pr", "view", pr_url, "--json", "reviewDecision"],
            )
            if result.returncode != 0:
                logger.warning("Failed to fetch review status: %s", result.stderr)
                await asyncio.sleep(_REVIEW_POLL_INTERVAL)
                continue
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning("Failed to parse review status output")
                await asyncio.sleep(_REVIEW_POLL_INTERVAL)
                continue
            decision = data.get("reviewDecision", "")
            if decision == "APPROVED":
                return True
            if decision == "CHANGES_REQUESTED":
                return False
            await asyncio.sleep(_REVIEW_POLL_INTERVAL)

    async def merge_pr(self, pr_url: str) -> None:
        """Merge a PR using gh pr merge."""
        result = await self._run_gh(["pr", "merge", pr_url, "--merge"])
        if result.returncode != 0:
            raise IntegrationError(
                f"Failed to merge PR {pr_url}: {result.stderr}",
                pr_url=pr_url,
                command="gh pr merge",
            )
        logger.info("Merged PR: %s", pr_url)
