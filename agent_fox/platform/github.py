"""GitHubPlatform: GitHub PR operations using the REST API.

Creates pull requests via the GitHub REST API, authenticated with a
GITHUB_PAT environment variable. Replaces the previous gh CLI implementation.

Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3, 19-REQ-4.4,
              19-REQ-4.E1, 19-REQ-4.E2, 19-REQ-4.E3, 19-REQ-4.E4
"""

from __future__ import annotations

import logging
import re

import httpx

from agent_fox.core.errors import IntegrationError

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubPlatform:
    """GitHub platform using the REST API.

    Creates pull requests via the GitHub REST API, authenticated
    with a GITHUB_PAT environment variable.

    Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3
    """

    def __init__(self, owner: str, repo: str, token: str) -> None:
        self._owner = owner
        self._repo = repo
        self._token = token

    async def create_pr(
        self,
        branch: str,
        title: str,
        body: str,
    ) -> str:
        """Create a GitHub PR via REST API.

        Args:
            branch: The feature branch (head).
            title: PR title.
            body: PR body/description.

        Returns:
            The PR URL as a string.

        Raises:
            IntegrationError: If PR creation fails.

        Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3
        """
        headers = self._auth_headers()
        default_branch = await self._get_default_branch(headers)
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": branch,
            "base": default_branch,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 201:
            pr_url = resp.json().get("html_url", "")
            logger.info("Created PR: %s", pr_url)
            return pr_url
        raise IntegrationError(
            f"GitHub PR creation failed ({resp.status_code}): {resp.text}",
            branch=branch,
        )

    async def _get_default_branch(self, headers: dict[str, str]) -> str:
        """Get the repository's default branch from the GitHub API."""
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("default_branch", "main")
        return "main"

    def _auth_headers(self) -> dict[str, str]:
        """Build authentication headers for GitHub API requests."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


def parse_github_remote(remote_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub remote URL.

    Supports HTTPS and SSH formats:
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git

    Returns None if the URL is not a recognized GitHub URL.

    Requirements: 19-REQ-4.4, 19-REQ-4.E4
    """
    pattern = r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$"
    match = re.search(pattern, remote_url)
    if match:
        return match.group(1), match.group(2)
    return None
