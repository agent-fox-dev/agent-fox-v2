"""Platform protocol: abstract forge operations.

Defines the interface for platform implementations (GitHub, GitLab, etc.).

Requirements: 61-REQ-8.1
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_fox.platform.github import IssueResult


@runtime_checkable
class PlatformProtocol(Protocol):
    """Abstract forge operations for issue and PR management.

    Requirements: 61-REQ-8.1
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

    async def create_pr(
        self,
        branch: str,
        title: str,
        body: str,
    ) -> str: ...

    async def close(self) -> None: ...
