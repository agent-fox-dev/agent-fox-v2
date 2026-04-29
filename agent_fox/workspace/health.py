"""Workspace health check and force-clean logic.

Single responsibility: assess and optionally remediate repository working
tree state before session dispatch.

Requirements: 118-REQ-1.1, 118-REQ-1.3, 118-REQ-1.E1, 118-REQ-1.E2,
              118-REQ-2.1, 118-REQ-2.E1, 118-REQ-2.E2,
              118-REQ-8.1, 118-REQ-8.2, 118-REQ-8.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from agent_fox.workspace.git import run_git

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthReport:
    """Result of a workspace health check.

    Attributes:
        untracked_files: Untracked files in the repo (excluding .gitignore).
        dirty_index_files: Files staged in the index but not committed.
    """

    untracked_files: list[str]
    dirty_index_files: list[str]

    @property
    def has_issues(self) -> bool:
        """Return True if the workspace has any issues."""
        return bool(self.untracked_files or self.dirty_index_files)

    @property
    def all_files(self) -> list[str]:
        """Return a sorted deduplicated list of all problematic files."""
        return sorted(set(self.untracked_files + self.dirty_index_files))


async def check_workspace_health(repo_root: Path) -> HealthReport:
    """Check repo working tree for untracked files and dirty index.

    Uses ``git ls-files --others --exclude-standard`` for untracked files
    and ``git diff --cached --name-only`` for dirty index.

    Fails open on git command errors: returns an empty report and logs
    a WARNING.

    Requirements: 118-REQ-1.1, 118-REQ-1.E1, 118-REQ-1.E2
    """
    untracked: list[str] = []
    dirty_index: list[str] = []

    # Detect untracked files
    try:
        rc, stdout, _stderr = await run_git(
            ["ls-files", "--others", "--exclude-standard"],
            cwd=repo_root,
            check=False,
        )
        if rc != 0:
            logger.warning(
                "git ls-files failed (rc=%d); proceeding with empty untracked list",
                rc,
            )
        else:
            untracked = [f for f in stdout.strip().split("\n") if f]
    except Exception:
        logger.warning(
            "git ls-files raised an exception; proceeding with empty untracked list",
            exc_info=True,
        )

    # Detect dirty index (staged but uncommitted changes)
    try:
        rc, stdout, _stderr = await run_git(
            ["diff", "--cached", "--name-only"],
            cwd=repo_root,
            check=False,
        )
        if rc != 0:
            logger.warning(
                "git diff --cached failed (rc=%d); proceeding with empty dirty index list",
                rc,
            )
        else:
            dirty_index = [f for f in stdout.strip().split("\n") if f]
    except Exception:
        logger.warning(
            "git diff --cached raised an exception; proceeding with empty dirty index list",
            exc_info=True,
        )

    return HealthReport(
        untracked_files=untracked,
        dirty_index_files=dirty_index,
    )


async def force_clean_workspace(
    repo_root: Path,
    report: HealthReport,
) -> HealthReport:
    """Remove untracked files and reset dirty index.

    Handles permission errors per file: logs a WARNING and keeps the
    file in the returned report. Returns an updated HealthReport
    reflecting the actual state after cleanup.

    Requirements: 118-REQ-2.1, 118-REQ-2.E1, 118-REQ-2.E2
    """
    failed_untracked: list[str] = []

    # Remove untracked files
    for rel_path in report.untracked_files:
        abs_path = repo_root / rel_path
        try:
            abs_path.unlink()
            logger.warning("Force-clean: removed untracked file %s", rel_path)
        except OSError as exc:
            logger.warning(
                "Force-clean: could not remove %s: %s",
                rel_path,
                exc,
            )
            failed_untracked.append(rel_path)

    # Reset dirty index via git checkout -- .
    remaining_dirty: list[str] = []
    if report.dirty_index_files:
        try:
            rc, _stdout, stderr = await run_git(
                ["checkout", "--", "."],
                cwd=repo_root,
                check=False,
            )
            if rc != 0:
                logger.warning(
                    "Force-clean: git checkout -- . failed (rc=%d): %s",
                    rc,
                    stderr.strip(),
                )
                remaining_dirty = list(report.dirty_index_files)
            else:
                logger.warning(
                    "Force-clean: reset dirty index files: %s",
                    ", ".join(report.dirty_index_files),
                )
        except Exception:
            logger.warning(
                "Force-clean: git checkout raised an exception",
                exc_info=True,
            )
            remaining_dirty = list(report.dirty_index_files)

    return HealthReport(
        untracked_files=failed_untracked,
        dirty_index_files=remaining_dirty,
    )


def format_health_diagnostic(
    report: HealthReport,
    *,
    max_files: int = 20,
) -> str:
    """Format a HealthReport into an actionable error message.

    Includes:
    - File list (truncated at ``max_files`` with "... and N more")
    - ``git clean -fd`` remediation command
    - ``--force-clean`` suggestion for automatic cleanup

    Requirements: 118-REQ-8.1, 118-REQ-8.2, 118-REQ-8.E1
    """
    lines: list[str] = []
    lines.append("Workspace has issues that would block harvest:")
    lines.append("")

    all_files = report.all_files
    shown = all_files[:max_files]

    if report.untracked_files:
        untracked_shown = [f for f in shown if f in report.untracked_files]
        if untracked_shown:
            lines.append("Untracked files:")
            for f in untracked_shown:
                lines.append(f"  {f}")

    if report.dirty_index_files:
        dirty_shown = [f for f in shown if f in report.dirty_index_files]
        if dirty_shown:
            lines.append("Staged but uncommitted files:")
            for f in dirty_shown:
                lines.append(f"  {f}")

    if len(all_files) > max_files:
        overflow = len(all_files) - max_files
        lines.append(f"  ... and {overflow} more")

    lines.append("")
    lines.append("Remediation:")
    lines.append("  git clean -fd          # remove untracked files")
    lines.append("  git checkout -- .      # reset staged changes")
    lines.append("")
    lines.append("Or re-run with --force-clean to automatically clean the workspace.")

    return "\n".join(lines)
