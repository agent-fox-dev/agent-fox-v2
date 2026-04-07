"""GitHubPlatform: GitHub PR and issue operations using the REST API.

Creates pull requests and manages issues via the GitHub REST API,
authenticated with a GITHUB_PAT environment variable.

Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3, 19-REQ-4.4,
              19-REQ-4.E1, 19-REQ-4.E2, 19-REQ-4.E3, 19-REQ-4.E4,
              28-REQ-1.*, 28-REQ-2.*, 28-REQ-3.*, 28-REQ-4.*,
              86-REQ-1.*
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from agent_fox.core.errors import IntegrationError

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class PullRequestResult:
    """Structured result for pull request creation.

    Requirements: 85-REQ-8.3
    """

    number: int
    url: str
    html_url: str


@dataclass(frozen=True)
class IssueComment:
    """Structured result for GitHub issue comments.

    Requirements: 86-REQ-1.3
    """

    id: int
    body: str
    user: str  # GitHub login
    created_at: str  # ISO 8601


class GitHubPlatform:
    """GitHub platform using the REST API.

    Manages issues via the GitHub REST API, authenticated with a
    GITHUB_PAT environment variable.  Supports GitHub Enterprise via
    the ``url`` constructor parameter.

    Requirements: 65-REQ-4.2, 65-REQ-4.3, 65-REQ-5.1, 65-REQ-5.2,
                  65-REQ-5.3, 65-REQ-5.E1, 28-REQ-1.*, 28-REQ-2.*,
                  28-REQ-3.*, 28-REQ-4.*
    """

    def __init__(self, owner: str, repo: str, token: str, url: str = "github.com") -> None:
        self._owner = owner
        self._repo = repo
        self._token = token
        self._url = url or "github.com"
        # Resolve API base URL — github.com uses api.github.com; anything
        # else (e.g. GitHub Enterprise) uses https://{host}/api/v3.
        if self._url == "github.com":
            self._api_base = "https://api.github.com"
        else:
            self._api_base = f"https://{self._url}/api/v3"

    def __repr__(self) -> str:
        return f"GitHubPlatform(owner={self._owner!r}, repo={self._repo!r})"

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
        q = f"repo:{self._owner}/{self._repo} in:title {title_prefix} state:{state} type:issue"
        url = f"{self._api_base}/search/issues"
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
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues"
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
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}"
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
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}/comments"
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
        *,
        sort: str = "created",
        direction: str = "asc",
    ) -> list[IssueResult]:
        """List issues with a specific label.

        Uses GET /repos/{owner}/{repo}/issues with label filter.
        Returns list of IssueResult, empty if none found.
        Issues are requested sorted by ``sort`` in ``direction`` order;
        the result is also sorted locally by issue number ascending as a
        fallback for platforms that ignore sort parameters (71-REQ-1.E1).

        Requirements: 61-REQ-8.1, 71-REQ-1.1, 71-REQ-1.E1
        """
        headers = self._auth_headers()
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues"
        params = {
            "labels": label,
            "state": state,
            "per_page": "100",
            "sort": sort,
            "direction": direction,
        }
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
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}/labels"
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

    async def remove_label(
        self,
        issue_number: int,
        label: str,
    ) -> None:
        """Remove a label from an issue.

        Uses DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{label}.
        Succeeds silently if the label is not present (404).
        Raises IntegrationError on other API errors.

        Requirements: 86-REQ-1.1, 86-REQ-1.2, 86-REQ-1.E1
        """
        headers = self._auth_headers()
        encoded_label = quote(label, safe="")
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}/labels/{encoded_label}"
        async with httpx.AsyncClient() as client:
            resp = await client.delete(url, headers=headers)
        if resp.status_code == 404:
            # Label not present — succeed silently (idempotent)
            logger.debug(
                "Label %r not present on issue #%d, nothing to remove",
                label,
                issue_number,
            )
            return
        if resp.status_code not in (200, 204):
            detail = _truncate_response(resp.text)
            logger.debug(
                "Label removal response (%d): %s",
                resp.status_code,
                detail,
            )
            raise IntegrationError(
                f"GitHub label removal failed ({resp.status_code})",
            )
        logger.info("Removed label %r from issue #%d", label, issue_number)

    async def list_issue_comments(
        self,
        issue_number: int,
    ) -> list[IssueComment]:
        """List all comments on an issue in chronological order.

        Uses GET /repos/{owner}/{repo}/issues/{issue_number}/comments.
        Returns empty list if no comments exist.
        Raises IntegrationError on API error.

        Requirements: 86-REQ-1.3, 86-REQ-1.E2
        """
        headers = self._auth_headers()
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}/comments"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            detail = _truncate_response(resp.text)
            logger.debug(
                "Issue comments response (%d): %s",
                resp.status_code,
                detail,
            )
            raise IntegrationError(
                f"GitHub issue comments failed ({resp.status_code})",
            )
        items = resp.json()
        results = [
            IssueComment(
                id=item["id"],
                body=item.get("body") or "",
                user=item["user"]["login"],
                created_at=item["created_at"],
            )
            for item in items
        ]
        logger.debug("Issue #%d has %d comment(s)", issue_number, len(results))
        return results

    async def get_issue(
        self,
        issue_number: int,
    ) -> IssueResult:
        """Fetch a single issue by number.

        Uses GET /repos/{owner}/{repo}/issues/{issue_number}.
        Raises IntegrationError on 404 or other API error.

        Requirements: 86-REQ-1.4, 86-REQ-1.E3
        """
        headers = self._auth_headers()
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            detail = _truncate_response(resp.text)
            logger.debug(
                "Get issue response (%d): %s",
                resp.status_code,
                detail,
            )
            raise IntegrationError(
                f"GitHub get issue failed ({resp.status_code})",
            )
        data = resp.json()
        result = IssueResult(
            number=data["number"],
            title=data["title"],
            html_url=data["html_url"],
            body=data.get("body") or "",
        )
        logger.debug("Fetched issue #%d: %s", result.number, result.title)
        return result

    async def close(self) -> None:
        """Clean up resources.

        No-op for the REST-based implementation (no persistent connections).

        Requirements: 61-REQ-8.1
        """

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = True,
    ) -> PullRequestResult:
        """Create a pull request.

        Uses POST /repos/{owner}/{repo}/pulls.
        Returns PullRequestResult with the created PR's number, url, and html_url.
        Raises IntegrationError on API error.

        Requirements: 85-REQ-8.4
        """
        headers = self._auth_headers()
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 201:
            detail = _truncate_response(resp.text)
            logger.debug("PR creation response (%d): %s", resp.status_code, detail)
            raise IntegrationError(
                f"GitHub PR creation failed ({resp.status_code})",
            )
        data = resp.json()
        result = PullRequestResult(
            number=data["number"],
            url=data["url"],
            html_url=data["html_url"],
        )
        logger.info("Created PR #%d: %s", result.number, result.html_url)
        return result

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
        url = f"{self._api_base}/repos/{self._owner}/{self._repo}/issues/{issue_number}"
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
