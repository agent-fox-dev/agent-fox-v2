"""Platform protocol: abstract issue-tracking operations.

Defines the interface for platform implementations (GitHub, GitLab, etc.).
Scoped to issue tracking only — PR creation has been removed.

Requirements: 61-REQ-8.1, 65-REQ-4.1, 86-REQ-1.5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class IssueResult:
    """Structured result for issue operations.

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
    """Structured result for issue comments.

    Requirements: 86-REQ-1.3
    """

    id: int
    body: str
    user: str  # login
    created_at: str  # ISO 8601


@runtime_checkable
class PlatformProtocol(Protocol):
    """Abstract forge operations for issue and PR management.

    Requirements: 61-REQ-8.1, 86-REQ-1.5
    """

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> IssueResult: ...

    async def list_issues_by_label(
        self,
        label: str,
        state: str = "open",
        *,
        sort: str = "created",
        direction: str = "asc",
    ) -> list[IssueResult]: ...

    async def add_issue_comment(
        self,
        issue_number: int,
        body: str,
    ) -> None: ...

    async def assign_label(
        self,
        issue_number: int,
        label: str,
    ) -> None: ...

    async def close_issue(
        self,
        issue_number: int,
        comment: str | None = None,
    ) -> None: ...

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = True,
    ) -> PullRequestResult:
        """Create a pull request from head branch to base branch.

        Requirements: 85-REQ-8.3
        """
        ...

    async def remove_label(
        self,
        issue_number: int,
        label: str,
    ) -> None:
        """Remove a label from an issue.

        Succeeds silently if the label is not present (idempotent).

        Requirements: 86-REQ-1.1, 86-REQ-1.2
        """
        ...

    async def list_issue_comments(
        self,
        issue_number: int,
    ) -> list[IssueComment]:
        """List all comments on an issue in chronological order.

        Requirements: 86-REQ-1.3
        """
        ...

    async def get_issue(
        self,
        issue_number: int,
    ) -> IssueResult:
        """Fetch a single issue by number.

        Requirements: 86-REQ-1.4
        """
        ...

    async def update_issue(
        self,
        issue_number: int,
        body: str,
    ) -> None:
        """Update the body of an existing issue.

        Used by the ignore ingestion pipeline to append the
        ``<!-- af:knowledge-ingested -->`` marker to af:ignore issue bodies
        after they have been ingested into the knowledge store.

        Requirements: 110-REQ-5.3
        """
        ...

    async def create_label(
        self,
        name: str,
        color: str,
        description: str = "",
    ) -> None:
        """Create a label on the repository, succeeding silently if it exists.

        Uses POST /repos/{owner}/{repo}/labels.  Treats a 422
        "already_exists" response as success so this method is safe to
        call on every ``af init`` run.

        Args:
            name: Label name (e.g. ``"af:fix"``).
            color: Six-character hex color without leading ``#``
                   (e.g. ``"12ec39"``).
            description: Optional human-readable description.

        Requirements: 358-REQ-1, 358-REQ-2
        """
        ...

    async def close(self) -> None: ...
