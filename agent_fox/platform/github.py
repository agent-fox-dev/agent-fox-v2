"""GitHubPlatform: GitHub PR and issue operations using the REST API.

Creates pull requests and manages issues via the GitHub REST API,
authenticated with a GITHUB_PAT environment variable.

Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3, 19-REQ-4.4,
              19-REQ-4.E1, 19-REQ-4.E2, 19-REQ-4.E3, 19-REQ-4.E4,
              28-REQ-1.*, 28-REQ-2.*, 28-REQ-3.*, 28-REQ-4.*
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from agent_fox.core.errors import IntegrationError

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_MAX_ERROR_TEXT = 500


def _truncate_response(text: str) -> str:
    """Truncate API response text to avoid leaking verbose error details."""
    if len(text) <= _MAX_ERROR_TEXT:
        return text
    return text[:_MAX_ERROR_TEXT] + "..."


@dataclass(frozen=True)
class IssueResult:
    """Structured result for GitHub issue operations.

    Requirements: 28-REQ-2.2
    """

    number: int
    title: str
    html_url: str


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
        detail = _truncate_response(resp.text)
        raise IntegrationError(
            f"GitHub PR creation failed ({resp.status_code}): {detail}",
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

    # ------------------------------------------------------------------
    # Issue operations (28-REQ-1.* through 28-REQ-4.*)
    # ------------------------------------------------------------------

    async def search_issues(
        self,
        title_prefix: str,
        state: str = "open",
    ) -> list[IssueResult]:
        """Search for issues by title prefix.

        Uses GET /search/issues with query:
        repo:{owner}/{repo} in:title {title_prefix} state:{state} type:issue

        Returns list of IssueResult, empty if none found.
        Raises IntegrationError on API error.

        Requirements: 28-REQ-1.1, 28-REQ-1.2, 28-REQ-1.3, 28-REQ-1.E1, 28-REQ-1.E2
        """
        headers = self._auth_headers()
        q = (
            f"repo:{self._owner}/{self._repo} "
            f"in:title {title_prefix} "
            f"state:{state} type:issue"
        )
        url = f"{_GITHUB_API}/search/issues"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params={"q": q}, headers=headers)
        if resp.status_code != 200:
            detail = _truncate_response(resp.text)
            raise IntegrationError(
                f"GitHub issue search failed ({resp.status_code}): {detail}",
            )
        items = resp.json().get("items", [])
        results = [
            IssueResult(
                number=item["number"],
                title=item["title"],
                html_url=item["html_url"],
            )
            for item in items
        ]
        logger.debug(
            "Issue search for %r found %d result(s)",
            title_prefix,
            len(results),
        )
        return results

    async def create_issue(
        self,
        title: str,
        body: str,
    ) -> IssueResult:
        """Create a new issue.

        Uses POST /repos/{owner}/{repo}/issues.
        Returns IssueResult with the created issue's number, title, and URL.
        Raises IntegrationError on API error.

        Requirements: 28-REQ-2.1, 28-REQ-2.2, 28-REQ-2.E1
        """
        headers = self._auth_headers()
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}/issues"
        payload = {"title": title, "body": body}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 201:
            detail = _truncate_response(resp.text)
            raise IntegrationError(
                f"GitHub issue creation failed ({resp.status_code}): {detail}",
            )
        data = resp.json()
        result = IssueResult(
            number=data["number"],
            title=data["title"],
            html_url=data["html_url"],
        )
        logger.info("Created issue #%d: %s", result.number, result.html_url)
        return result

    async def update_issue(
        self,
        issue_number: int,
        body: str,
    ) -> None:
        """Update an existing issue's body.

        Uses PATCH /repos/{owner}/{repo}/issues/{issue_number}.
        Raises IntegrationError on API error.

        Requirements: 28-REQ-3.1, 28-REQ-3.E1
        """
        headers = self._auth_headers()
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}/issues/{issue_number}"
        payload = {"body": body}
        async with httpx.AsyncClient() as client:
            resp = await client.patch(url, json=payload, headers=headers)
        if resp.status_code != 200:
            detail = _truncate_response(resp.text)
            raise IntegrationError(
                f"GitHub issue update failed ({resp.status_code}): {detail}",
            )
        logger.info("Updated issue #%d", issue_number)

    async def add_issue_comment(
        self,
        issue_number: int,
        comment: str,
    ) -> None:
        """Add a comment to an existing issue.

        Uses POST /repos/{owner}/{repo}/issues/{issue_number}/comments.
        Raises IntegrationError on API error.

        Requirements: 28-REQ-3.2, 28-REQ-3.E1
        """
        headers = self._auth_headers()
        url = (
            f"{_GITHUB_API}/repos/{self._owner}/{self._repo}"
            f"/issues/{issue_number}/comments"
        )
        payload = {"body": comment}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 201:
            detail = _truncate_response(resp.text)
            raise IntegrationError(
                f"GitHub issue comment failed ({resp.status_code}): {detail}",
            )
        logger.info("Added comment to issue #%d", issue_number)

    async def close_issue(
        self,
        issue_number: int,
        comment: str | None = None,
    ) -> None:
        """Close an issue and optionally add a closing comment.

        Uses PATCH /repos/{owner}/{repo}/issues/{issue_number}
        with body {"state": "closed"}.
        If comment is provided, adds it before closing.
        Raises IntegrationError on API error.

        Requirements: 28-REQ-4.1, 28-REQ-4.E1
        """
        if comment is not None:
            await self.add_issue_comment(issue_number, comment)

        headers = self._auth_headers()
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}/issues/{issue_number}"
        payload = {"state": "closed"}
        async with httpx.AsyncClient() as client:
            resp = await client.patch(url, json=payload, headers=headers)
        if resp.status_code != 200:
            detail = _truncate_response(resp.text)
            raise IntegrationError(
                f"GitHub issue close failed ({resp.status_code}): {detail}",
            )
        logger.info("Closed issue #%d", issue_number)


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
