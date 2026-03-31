"""In-memory spec builder and branch name utilities.

Requirements: 61-REQ-6.1, 61-REQ-6.2
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_fox.platform.github import IssueResult


@dataclass(frozen=True)
class InMemorySpec:
    """Lightweight spec for the fix engine.

    Requirements: 61-REQ-6.1
    """

    issue_number: int
    title: str
    task_prompt: str
    system_context: str
    branch_name: str


def sanitise_branch_name(title: str) -> str:
    """Convert an issue title to a sanitised branch name.

    Returns ``fix/{sanitised-title}`` where the title is lowercased,
    special characters are removed, and spaces become hyphens.

    Requirements: 61-REQ-6.2
    """
    slug = title.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove anything that isn't alphanumeric or hyphen
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return f"fix/{slug}"


def build_in_memory_spec(issue: IssueResult, issue_body: str) -> InMemorySpec:
    """Build a lightweight in-memory spec from a platform issue.

    Requirements: 61-REQ-6.1
    """
    branch = sanitise_branch_name(issue.title)
    task_prompt = (
        f"Fix the issue: {issue.title}\n\nIssue #{issue.number}\n\n{issue_body}"
    )
    return InMemorySpec(
        issue_number=issue.number,
        title=issue.title,
        task_prompt=task_prompt,
        system_context=issue_body,
        branch_name=branch,
    )
