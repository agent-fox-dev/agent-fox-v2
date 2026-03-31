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
    body: str = ""


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

    def __repr__(self) -> str:
        return f"GitHubPlatform(owner={self._owner!r}, repo={self._repo!r})"

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
        logger.debug("PR creation response (%d): %s", resp.status_code, detail)
        raise IntegrationError(
            f"GitHub PR creation failed ({resp.status_code})",
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
            logger.debug("Issue search response (%d): %s", resp.status_code, detail)
            raise IntegrationError(
                f"GitHub issue search failed ({resp.status_code})",
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
        labels: list[str] | None = None,
    ) -> IssueResult:
        """Create a new issue.

        Uses POST /repos/{owner}/{repo}/issues.
        Returns IssueResult with the created issue's number, title, and URL.
        Raises IntegrationError on API error.

        Requirements: 28-REQ-2.1, 28-REQ-2.2, 28-REQ-2.E1
        """
        headers = self._auth_headers()
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}/issues"
        payload: dict[str, object] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 201:
            detail = _truncate_response(resp.text)
            logger.debug("Issue creation response (%d): %s", resp.status_code, detail)
            raise IntegrationError(
                f"GitHub issue creation failed ({resp.status_code})",
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
            logger.debug("Issue update response (%d): %s", resp.status_code, detail)
            raise IntegrationError(
                f"GitHub issue update failed ({resp.status_code})",
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
            logger.debug("Issue comment response (%d): %s", resp.status_code, detail)
            raise IntegrationError(
                f"GitHub issue comment failed ({resp.status_code})",
            )
        logger.info("Added comment to issue #%d", issue_number)

    async def list_issues_by_label(
        self,
        label: str,
        state: str = "open",
    ) -> list[IssueResult]:
        """List issues with a specific label.

        Uses GET /repos/{owner}/{repo}/issues with label filter.
        Returns list of IssueResult, empty if none found.

        Requirements: 61-REQ-8.1
        """
        headers = self._auth_headers()
        url = f"{_GITHUB_API}/repos/{self._owner}/{self._repo}/issues"
        params = {"labels": label, "state": state, "per_page": "100"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            detail = _truncate_response(resp.text)
            logger.debug(
                "Issue list by label response (%d): %s",
                resp.status_code,
                detail,
            )
            raise IntegrationError(
                f"GitHub issue list failed ({resp.status_code})",
            )
        items = resp.json()
        results = [
            IssueResult(
                number=item["number"],
                title=item["title"],
                html_url=item["html_url"],
                body=item.get("body") or "",
            )
            for item in items
            if "pull_request" not in item  # exclude PRs
        ]
        logger.debug("Issues with label %r: %d result(s)", label, len(results))
        return results

    async def assign_label(
        self,
        issue_number: int,
        label: str,
    ) -> None:
        """Assign a label to an issue.

        Uses POST /repos/{owner}/{repo}/issues/{issue_number}/labels.

        Requirements: 61-REQ-8.1
        """
        headers = self._auth_headers()
        url = (
            f"{_GITHUB_API}/repos/{self._owner}/{self._repo}"
            f"/issues/{issue_number}/labels"
        )
        payload = {"labels": [label]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            detail = _truncate_response(resp.text)
            logger.debug(
                "Label assignment response (%d): %s",
                resp.status_code,
                detail,
            )
            raise IntegrationError(
                f"GitHub label assignment failed ({resp.status_code})",
            )
        logger.info("Assigned label %r to issue #%d", label, issue_number)

    async def close(self) -> None:
        """Clean up resources.

        No-op for the REST-based implementation (no persistent connections).

        Requirements: 61-REQ-8.1
        """

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
            logger.debug("Issue close response (%d): %s", resp.status_code, detail)
            raise IntegrationError(
                f"GitHub issue close failed ({resp.status_code})",
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
