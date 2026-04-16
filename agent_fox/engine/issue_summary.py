"""Issue summary posting: notify originating issues when specs complete.

When all task groups of a spec are fully implemented and merged to develop,
this module posts a roll-up summary comment to the originating GitHub issue
referenced in the spec's prd.md ## Source section.

Requirements: 108-REQ-1 through 108-REQ-6
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.platform.protocol import PlatformProtocol

logger = logging.getLogger(__name__)

# GitHub issue URL pattern:
#   https://github.com/{owner}/{repo}/issues/{number}
_GITHUB_ISSUE_RE = re.compile(r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/issues/(?P<number>\d+)\s*$")

# Source line pattern within ## Source section:
#   Source: <value>
_SOURCE_LINE_RE = re.compile(r"^Source:\s*(.+)$")


@dataclass(frozen=True)
class SourceIssue:
    """Parsed issue reference from a prd.md Source section.

    Requirements: 108-REQ-1.2, 108-REQ-1.3
    """

    forge: str  # "github" (extensible to "gitlab", "linear", etc.)
    owner: str  # e.g., "agent-fox-dev"
    repo: str  # e.g., "agent-fox"
    issue_number: int  # e.g., 359


def parse_source_url(prd_path: Path) -> SourceIssue | None:
    """Extract the issue URL from prd.md's ## Source section.

    Returns None (never raises) if:
    - prd.md does not exist
    - ## Source section is missing
    - Source: line is absent within the section
    - Source line value does not match any known issue URL pattern

    Requirements: 108-REQ-1.1, 108-REQ-1.2, 108-REQ-1.3,
                  108-REQ-1.E1, 108-REQ-1.E2, 108-REQ-1.E3
    """
    try:
        # 108-REQ-1.E3: prd.md does not exist
        if not prd_path.exists():
            return None

        text = prd_path.read_text(encoding="utf-8")
        lines = text.splitlines()

        in_source_section = False
        for line in lines:
            stripped = line.strip()

            # Detect the ## Source section heading (exact match)
            if stripped == "## Source":
                in_source_section = True
                continue

            # Stop at the next markdown heading after entering the section
            if in_source_section and stripped.startswith("#"):
                break

            # Look for a "Source: <value>" line within the section
            if in_source_section:
                source_match = _SOURCE_LINE_RE.match(stripped)
                if source_match:
                    url = source_match.group(1).strip()
                    # Try GitHub issue URL pattern
                    gh_match = _GITHUB_ISSUE_RE.match(url)
                    if gh_match:
                        return SourceIssue(
                            forge="github",
                            owner=gh_match.group("owner"),
                            repo=gh_match.group("repo"),
                            issue_number=int(gh_match.group("number")),
                        )
                    # URL present but matches no known forge — return None
                    # 108-REQ-1.E2: non-issue-URL source
                    return None

        # 108-REQ-1.E1: ## Source missing or Source: line absent
        return None

    except Exception:
        # 108-REQ-1.3: Pure function — never propagate exceptions
        logger.debug("parse_source_url encountered an error", exc_info=True)
        return None


def _get_develop_head(repo_root: Path) -> str:
    """Return the current develop branch HEAD SHA.

    Runs ``git rev-parse develop`` in the given repository root.
    Returns ``"unknown"`` if the command fails for any reason.

    Requirements: 108-REQ-6.1, 108-REQ-6.E1
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "develop"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        logger.debug("git rev-parse develop failed", exc_info=True)
    return "unknown"


def build_summary_comment(
    spec_name: str,
    commit_sha: str,
    tasks_path: Path,
) -> str:
    """Construct the Markdown comment body for the originating issue.

    Includes the spec name, the develop HEAD commit SHA, a bulleted list
    of task group titles derived from tasks.md, and an auto-generated footer.

    Requirements: 108-REQ-3.1, 108-REQ-3.2, 108-REQ-3.3, 108-REQ-3.4
    """
    from agent_fox.spec.parser import parse_tasks  # noqa: PLC0415

    # Extract task group titles from tasks.md
    group_lines: list[str] = []
    try:
        if tasks_path.exists():
            groups = parse_tasks(tasks_path)
            group_lines = [f"- {g.title}" for g in groups]
    except Exception:
        logger.debug("Failed to parse tasks.md for summary comment", exc_info=True)

    task_section = "\n".join(group_lines) if group_lines else "*(no task groups found)*"

    return (
        f"## Spec Implemented\n\n"
        f"Spec `{spec_name}` has been fully implemented and merged to `develop`.\n\n"
        f"**Commit:** `{commit_sha}`\n\n"
        f"### Task Groups\n\n"
        f"{task_section}\n\n"
        f"---\n"
        f"*Auto-generated by agent-fox.*"
    )


async def post_issue_summaries(
    platform: PlatformProtocol,
    specs_dir: Path,
    completed_specs: set[str],
    already_posted: set[str],
    repo_root: Path,
) -> set[str]:
    """Post summary comments for newly completed specs.

    Iterates specs that are in ``completed_specs`` but not yet in
    ``already_posted``, extracts the originating issue URL from each
    spec's ``prd.md``, and posts a roll-up summary comment to that issue.

    Skips specs that:
    - have no valid source URL (108-REQ-1.E1, 108-REQ-1.E2)
    - are already in ``already_posted`` (108-REQ-2.E1)
    - have a forge type that doesn't match the platform (108-REQ-4.E2)

    Handles ``add_issue_comment()`` failures gracefully: logs a warning
    and continues without affecting the run status (108-REQ-4.E1).

    Returns:
        Set of spec names for which a comment was successfully posted.

    Requirements: 108-REQ-2.1, 108-REQ-2.2, 108-REQ-2.E1,
                  108-REQ-4.1, 108-REQ-4.E1, 108-REQ-4.E2
    """
    newly_completed = completed_specs - already_posted
    posted: set[str] = set()

    for spec_name in sorted(newly_completed):
        prd_path = specs_dir / spec_name / "prd.md"
        source_issue = parse_source_url(prd_path)

        if source_issue is None:
            logger.debug("No valid source URL for spec '%s'; skipping", spec_name)
            continue

        # 108-REQ-4.E2: Skip when platform forge type doesn't match source forge
        platform_forge = getattr(platform, "forge_type", None)
        if platform_forge != source_issue.forge:
            logger.info(
                "Skipping issue summary for spec '%s': source forge='%s', platform forge='%s'",
                spec_name,
                source_issue.forge,
                platform_forge,
            )
            continue

        commit_sha = _get_develop_head(repo_root)
        tasks_path = specs_dir / spec_name / "tasks.md"
        body = build_summary_comment(spec_name, commit_sha, tasks_path)

        try:
            await platform.add_issue_comment(source_issue.issue_number, body)
            posted.add(spec_name)
            logger.info(
                "Posted issue summary for spec '%s' to issue #%d",
                spec_name,
                source_issue.issue_number,
            )
        except Exception:
            # 108-REQ-4.E1: Graceful failure — warn and continue
            logger.warning(
                "Failed to post issue summary for spec '%s'",
                spec_name,
                exc_info=True,
            )

    return posted
