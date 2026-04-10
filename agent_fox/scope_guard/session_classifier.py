"""Classify session outcomes based on commit analysis.

Requirements: 87-REQ-1.3, 87-REQ-4.1, 87-REQ-4.E1 through 87-REQ-4.E3
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from agent_fox.scope_guard.models import (
    FileChange,
    ScopeGuardSessionOutcome,
    SessionClassification,
    SessionResult,
    TaskGroup,
    ViolationRecord,
)
from agent_fox.scope_guard.stub_validator import validate_stubs


def classify_session(session: SessionResult, task_group: TaskGroup) -> ScopeGuardSessionOutcome:
    """Classify a session result into an outcome category.

    Classification logic (mutually exclusive, checked in order):
    1. ``harvest-error`` — exit_status indicates a harvest failure.
    2. ``failure`` — session exited with an error or timeout.
    3. ``no-op`` — normal exit with zero *functional* commits.
    4. ``success`` — normal exit with functional commits (may include
       stub-violation flag for test-writing archetypes).
    """
    stub_violation = False
    violation_details: list[ViolationRecord] = []
    reason = ""

    # 1. Harvest error
    if session.exit_status == "harvest-error":
        return _build_outcome(
            session,
            task_group,
            SessionClassification.HARVEST_ERROR,
            reason="harvest process failed",
        )

    # 2. Failure — error or timeout exit
    if session.exit_status in ("error", "timeout"):
        return _build_outcome(
            session,
            task_group,
            SessionClassification.FAILURE,
            reason=f"session exited with {session.exit_status}",
        )

    # 3. Count functional (non-whitespace/comment-only) commits
    functional = _count_functional_commits(session)

    if functional == 0:
        return _build_outcome(
            session,
            task_group,
            SessionClassification.NO_OP,
            reason="no functional commits",
        )

    # 4. Success path — check for stub violations on test-writing sessions
    if task_group.archetype == "test-writing" and session.modified_files:
        result = validate_stubs(session.modified_files, task_group)
        if not result.passed:
            stub_violation = True
            violation_details = list(result.violations)
            reason = "stub enforcement violation"

    return _build_outcome(
        session,
        task_group,
        SessionClassification.SUCCESS,
        stub_violation=stub_violation,
        violation_details=violation_details,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COMMENT_LINE_RE = re.compile(
    r"^\s*(?:"
    r"//|"  # C-style line comment
    r"#|"  # Python/shell comment
    r"\*|"  # continuation of block comment
    r"/\*|"  # block comment open
    r"\*/|"  # block comment close
    r"\{-|"  # Haskell block comment open
    r"-\}"  # Haskell block comment close
    r")"
)


def _is_functional_diff(diff_text: str) -> bool:
    """Return True if *diff_text* contains at least one functional change.

    A diff is considered non-functional if it consists entirely of whitespace,
    blank lines, and/or comment-only lines.

    The *diff_text* may be a unified diff (with ``+``/``-`` prefixes) or raw
    source code.  Both formats are handled.
    """
    is_unified = _looks_like_unified_diff(diff_text)

    for line in diff_text.splitlines():
        stripped = line.strip()
        # Skip blank lines
        if not stripped:
            continue

        if is_unified:
            # Skip diff metadata lines
            if stripped.startswith(("---", "+++", "@@", "diff ", "index ")):
                continue
            # Only look at added/removed lines
            if not stripped.startswith(("+", "-")):
                continue
            # Strip the diff prefix (+/-)
            content = stripped[1:].strip()
        else:
            # Raw source — every line is a candidate
            content = stripped

        if not content:
            continue
        # If it's not purely a comment line, it's functional
        if not _COMMENT_LINE_RE.match(content):
            return True
    return False


def _looks_like_unified_diff(text: str) -> bool:
    """Heuristic: does *text* look like a unified diff?"""
    for line in text.splitlines()[:10]:
        if line.startswith(("diff ", "--- ", "+++ ", "@@ ")):
            return True
    return False


def _count_functional_commits(session: SessionResult) -> int:
    """Count commits that contain functional (non-whitespace/comment) changes.

    When commit_count is 0 or there are no modified files, returns 0.
    When there are modified files, we check whether any diff contains
    functional changes. If none do, returns 0.
    """
    if session.commit_count <= 0:
        return 0

    if not session.modified_files:
        return 0

    # Check if any file has functional changes
    for fc in session.modified_files:
        if _is_functional_diff(fc.diff_text):
            return session.commit_count

    return 0


def _is_whitespace_only_change(file_change: FileChange) -> bool:
    """Return True if the file change consists only of whitespace."""
    return not _is_functional_diff(file_change.diff_text)


def _build_outcome(
    session: SessionResult,
    task_group: TaskGroup,
    classification: SessionClassification,
    *,
    stub_violation: bool = False,
    violation_details: list[ViolationRecord] | None = None,
    reason: str = "",
) -> ScopeGuardSessionOutcome:
    return ScopeGuardSessionOutcome(
        session_id=session.session_id,
        spec_number=session.spec_number,
        task_group_number=session.task_group_number,
        classification=classification,
        duration_seconds=session.duration_seconds,
        cost_dollars=session.cost_dollars,
        timestamp=datetime.now(tz=UTC),
        stub_violation=stub_violation,
        violation_details=violation_details or [],
        reason=reason,
    )
