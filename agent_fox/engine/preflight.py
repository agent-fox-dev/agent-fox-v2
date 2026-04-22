"""Pre-flight check: skip coder sessions when work is already complete.

Before launching an expensive coder session, checks three gates:
1. Task group completion — DB first, tasks.md fallback
2. No active critical/major review findings
3. Tests pass (only when gates 1 & 2 pass)

If all gates pass the node is marked completed and the session is skipped.
"""

from __future__ import annotations

import logging
import subprocess
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TEST_TIMEOUT_SECONDS = 300


class PreflightVerdict(StrEnum):
    LAUNCH = "launch"
    SKIP = "skip"


def is_task_group_done_db(
    conn: Any,
    spec_name: str,
    group_number: int,
) -> bool | None:
    """Check plan_nodes DB for task group completion.

    Returns True if the node status is 'completed', False if it exists
    but is not completed, or None if the node is not found in the DB
    (indicating the caller should fall back to tasks.md).
    """
    try:
        row = conn.execute(
            """
            SELECT status
            FROM plan_nodes
            WHERE spec_name = ? AND group_number = ?
            LIMIT 1
            """,
            [spec_name, group_number],
        ).fetchone()
    except Exception:
        logger.debug(
            "Failed to query plan_nodes for %s:%d",
            spec_name,
            group_number,
            exc_info=True,
        )
        return None

    if row is None:
        return None
    return row[0] == "completed"


def is_task_group_done_file(
    specs_dir: Path,
    spec_name: str,
    group_number: int,
) -> bool:
    """Check tasks.md checkbox state for a specific task group.

    Returns True only when the task group exists and has completed=True.
    """
    from agent_fox.spec.parser import parse_tasks

    tasks_path = specs_dir / spec_name / "tasks.md"
    if not tasks_path.is_file():
        return False
    try:
        groups = parse_tasks(tasks_path)
    except Exception:
        logger.debug(
            "Failed to parse tasks.md for %s",
            spec_name,
            exc_info=True,
        )
        return False

    for group in groups:
        if group.number == group_number:
            return group.completed
    return False


def is_task_group_done(
    conn: Any | None,
    spec_name: str,
    group_number: int,
    specs_dir: Path,
) -> bool:
    """Check whether a task group is already complete.

    Uses the DB as the source of truth, falling back to tasks.md
    when DB state is unavailable.
    """
    if conn is not None:
        db_result = is_task_group_done_db(conn, spec_name, group_number)
        if db_result is not None:
            return db_result

    return is_task_group_done_file(specs_dir, spec_name, group_number)


def has_active_critical_findings(
    conn: Any | None,
    spec_name: str,
    task_group: int,
) -> bool:
    """Return True if unresolved critical/major findings exist."""
    if conn is None:
        return False
    try:
        from agent_fox.knowledge.review_store import query_active_findings

        findings = query_active_findings(conn, spec_name, str(task_group))
        return any(f.severity in ("critical", "major") for f in findings)
    except Exception:
        logger.debug(
            "Failed to query review findings for %s:%d",
            spec_name,
            task_group,
            exc_info=True,
        )
        return False


def do_tests_pass(cwd: Path) -> bool:
    """Run ``make test`` and return True if exit code is 0."""
    try:
        result = subprocess.run(
            ["make", "test"],
            cwd=cwd,
            capture_output=True,
            timeout=_TEST_TIMEOUT_SECONDS,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning("Pre-flight test run timed out after %ds", _TEST_TIMEOUT_SECONDS)
        return False
    except Exception:
        logger.debug("Pre-flight test run failed", exc_info=True)
        return False


def run_preflight(
    spec_name: str,
    group_number: int,
    conn: Any | None,
    specs_dir: Path,
    cwd: Path,
) -> PreflightVerdict:
    """Run the pre-flight check for a coder session.

    Gates are evaluated in order with short-circuit: if any gate
    fails, the check returns LAUNCH immediately to avoid running
    later (more expensive) gates.
    """
    if not is_task_group_done(conn, spec_name, group_number, specs_dir):
        return PreflightVerdict.LAUNCH

    if has_active_critical_findings(conn, spec_name, group_number):
        logger.info(
            "Preflight: %s:%d has done checkboxes but active findings, launching coder",
            spec_name,
            group_number,
        )
        return PreflightVerdict.LAUNCH

    if not do_tests_pass(cwd):
        logger.info(
            "Preflight: %s:%d has done checkboxes but tests fail, launching coder",
            spec_name,
            group_number,
        )
        return PreflightVerdict.LAUNCH

    logger.info(
        "Preflight: %s:%d is complete — checkboxes done, no findings, tests pass. Skipping coder session.",
        spec_name,
        group_number,
    )
    return PreflightVerdict.SKIP
