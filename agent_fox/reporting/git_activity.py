"""Git log parsing and commit classification for standup reports.

Extracts and classifies commits from ``git log`` output into human
and agent buckets based on author identity and commit message patterns.

Requirements: 07-REQ-2.3
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HumanCommit:
    """A commit record (human or agent) within the reporting window."""

    sha: str
    author: str
    timestamp: str  # ISO 8601
    subject: str
    files_changed: list[str]


# Conventional-commit prefix pattern used by coding agents.
_CONVENTIONAL_PREFIX_RE = re.compile(
    r"^(feat|fix|refactor|test|chore|style|docs|ci|build|perf|revert)"
    r"(\([^)]+\))?!?:\s",
)

# Merge-commit pattern produced by git merge (used by agent workflows).
_MERGE_BRANCH_RE = re.compile(r"^Merge branch\s+'")


def is_agent_commit(commit: HumanCommit, agent_author: str) -> bool:
    """Determine whether a commit was made by an agent.

    Checks two signals:
    1. Author name matches the configured agent identity.
    2. Commit subject uses a conventional-commit prefix or is a
       merge-branch commit — patterns agents follow but humans
       typically do not.
    """
    if commit.author == agent_author:
        return True
    if _CONVENTIONAL_PREFIX_RE.match(commit.subject):
        return True
    if _MERGE_BRANCH_RE.match(commit.subject):
        return True
    return False


def partition_commits(
    repo_path: Path,
    since: datetime,
    agent_author: str,
) -> tuple[list[HumanCommit], list[HumanCommit]]:
    """Query git log and partition commits into human and agent lists.

    Runs ``git log --since=<ISO>`` and classifies each commit using
    author identity and commit message patterns.

    Args:
        repo_path: Path to the git repository root.
        since: Start of reporting window.
        agent_author: Author name used by the agent.

    Returns:
        Tuple of (human_commits, agent_commits).
    """
    since_iso = since.isoformat()

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={since_iso}",
                "--format=%H|%an|%aI|%s",
                "--name-only",
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        logger.warning("git log failed: %s", exc)
        return [], []

    if result.returncode != 0:
        logger.warning("git log returned non-zero: %s", result.stderr.strip())
        return [], []

    all_commits = parse_git_log_output(result.stdout)

    human: list[HumanCommit] = []
    agent: list[HumanCommit] = []
    for c in all_commits:
        if is_agent_commit(c, agent_author):
            agent.append(c)
        else:
            human.append(c)
    return human, agent


def parse_git_log_output(output: str) -> list[HumanCommit]:
    """Parse structured git log output into HumanCommit records.

    Git outputs with ``--format="%H|%an|%aI|%s" --name-only``::

        <hash>|<author>|<ISO date>|<subject>
        <blank line>
        <file1>
        <file2>
        <hash>|<author>|<ISO date>|<subject>
        <blank line>
        <file1>
        ...

    Each commit has a header line followed by a blank separator, then
    file names. The next commit header follows immediately after files.

    Args:
        output: Raw stdout from git log command.

    Returns:
        List of parsed HumanCommit records.
    """
    commits: list[HumanCommit] = []
    if not output.strip():
        return commits

    lines = output.split("\n")

    # Collect commit blocks: each starts with a header (contains |),
    # followed by a blank line, then file names.
    headers: list[tuple[str, int]] = []  # (header, line_index)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and "|" in stripped:
            # Check if it looks like a commit header (40-char hex hash prefix)
            parts = stripped.split("|", 1)
            if len(parts[0]) == 40 and all(c in "0123456789abcdef" for c in parts[0]):
                headers.append((stripped, i))

    for idx, (header, start_line) in enumerate(headers):
        # Files are between this header and the next header
        if idx + 1 < len(headers):
            end_line = headers[idx + 1][1]
        else:
            end_line = len(lines)

        # Collect non-empty, non-header lines as file names
        files: list[str] = []
        for j in range(start_line + 1, end_line):
            stripped = lines[j].strip()
            if stripped:
                files.append(stripped)

        commit = parse_commit_header(header, files)
        if commit is not None:
            commits.append(commit)

    return commits


def parse_commit_header(
    header: str,
    files: list[str],
) -> HumanCommit | None:
    """Parse a single commit header line into a HumanCommit.

    Args:
        header: The header line in format "hash|author|date|subject".
        files: List of changed file paths.

    Returns:
        HumanCommit record or None if parsing fails.
    """
    parts = header.split("|", 3)
    if len(parts) < 4:
        logger.warning("Malformed git log header: %s", header)
        return None

    sha, author, timestamp, subject = parts
    return HumanCommit(
        sha=sha.strip(),
        author=author.strip(),
        timestamp=timestamp.strip(),
        subject=subject.strip(),
        files_changed=[f for f in files if f],
    )
