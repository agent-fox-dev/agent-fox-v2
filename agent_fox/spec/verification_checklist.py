"""Verification checklist builder for the verifier archetype.

Builds a structured checklist from tasks.md checkboxes, requirements.md
acceptance criteria, and errata — injected into the verifier's session
context so it can enforce task completion and requirement coverage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_fox.spec._patterns import REQ_ID_BARE
from agent_fox.spec.parser import parse_tasks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtaskAuditEntry:
    """Audit entry for a single subtask checkbox."""

    group_number: int
    subtask_id: str
    title: str
    checked: bool
    skipped: bool  # [-] or [~] markers


@dataclass(frozen=True)
class RequirementMapping:
    """Maps a requirement ID to its test coverage status."""

    requirement_id: str
    covered: bool
    test_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationChecklist:
    """Complete verification checklist for a spec."""

    spec_name: str
    task_audit: list[SubtaskAuditEntry]
    requirement_coverage: list[RequirementMapping]
    has_errata: bool


def build_verification_checklist(
    spec_dir: Path,
    conn: Any,
    *,
    tests_dir: Path | None = None,
) -> VerificationChecklist:
    """Build a verification checklist from spec files and DB state.

    Args:
        spec_dir: Path to the spec directory (e.g. .agent-fox/specs/10_my_spec).
        conn: DuckDB connection for errata queries.
        tests_dir: Path to the tests directory for requirement-to-test scanning.

    Returns:
        A populated VerificationChecklist.
    """
    spec_name = spec_dir.name

    task_audit = _audit_task_checkboxes(spec_dir)
    has_errata = _check_errata_exist(conn, spec_name)
    requirement_coverage = scan_requirement_test_coverage(spec_dir, tests_dir)

    return VerificationChecklist(
        spec_name=spec_name,
        task_audit=task_audit,
        requirement_coverage=requirement_coverage,
        has_errata=has_errata,
    )


def _audit_task_checkboxes(spec_dir: Path) -> list[SubtaskAuditEntry]:
    """Parse tasks.md and audit every subtask checkbox state."""
    tasks_path = spec_dir / "tasks.md"
    if not tasks_path.is_file():
        return []

    try:
        groups = parse_tasks(tasks_path)
    except Exception:
        logger.warning("Failed to parse tasks.md for checklist audit in %s", spec_dir)
        return []

    entries: list[SubtaskAuditEntry] = []
    for group in groups:
        for subtask in group.subtasks:
            entries.append(
                SubtaskAuditEntry(
                    group_number=group.number,
                    subtask_id=subtask.id,
                    title=subtask.title,
                    checked=subtask.completed,
                    skipped=_is_subtask_skipped(tasks_path, subtask.id),
                )
            )
    return entries


_SUBTASK_SKIP_PATTERN = re.compile(r"^\s+- \[([~\-])\] (\d+\.(?:\d+|V))")


def _is_subtask_skipped(tasks_path: Path, subtask_id: str) -> bool:
    """Check if a subtask is marked with [-] or [~] (intentionally skipped)."""
    text = tasks_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = _SUBTASK_SKIP_PATTERN.match(line)
        if m and m.group(2) == subtask_id:
            return True
    return False


def _check_errata_exist(conn: Any, spec_name: str) -> bool:
    """Check if any errata exist for this spec in the DB."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM errata WHERE spec_name = ?",
            [spec_name],
        ).fetchone()
        return row is not None and row[0] > 0
    except Exception:
        logger.debug("Could not query errata for %s", spec_name)
        return False


def scan_requirement_test_coverage(
    spec_dir: Path,
    tests_dir: Path | None = None,
) -> list[RequirementMapping]:
    """Map requirement IDs to test file coverage.

    For each requirement ID found in requirements.md, scans test files
    for references (in comments, docstrings, or function names).

    Args:
        spec_dir: Path to the spec directory containing requirements.md.
        tests_dir: Path to the project's tests directory. If None or
            non-existent, all requirements are marked uncovered.

    Returns:
        List of RequirementMapping, one per requirement ID.
    """
    req_path = spec_dir / "requirements.md"
    if not req_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")
    req_ids = sorted(set(REQ_ID_BARE.findall(req_text)))
    if not req_ids:
        return []

    test_content = _load_test_file_contents(tests_dir)

    mappings: list[RequirementMapping] = []
    for req_id in req_ids:
        test_files = _find_test_files_for_req(req_id, test_content)
        mappings.append(
            RequirementMapping(
                requirement_id=req_id,
                covered=len(test_files) > 0,
                test_files=test_files,
            )
        )
    return mappings


def _load_test_file_contents(tests_dir: Path | None) -> dict[str, str]:
    """Load all test file contents into a dict keyed by relative path."""
    if tests_dir is None or not tests_dir.is_dir():
        return {}
    contents: dict[str, str] = {}
    for test_file in tests_dir.rglob("test_*.py"):
        try:
            contents[test_file.name] = test_file.read_text(encoding="utf-8")
        except OSError:
            continue
    return contents


def _normalize_req_id_for_funcname(req_id: str) -> str:
    """Convert '10-REQ-1.1' to 'req_10_1_1' for function name matching."""
    without_prefix = re.sub(r"^(\d+)-REQ-", r"req_\1_", req_id)
    return without_prefix.replace(".", "_").replace("-", "_").lower()


def _find_test_files_for_req(
    req_id: str,
    test_content: dict[str, str],
) -> list[str]:
    """Find test files that reference a requirement ID."""
    normalized = _normalize_req_id_for_funcname(req_id)
    matching: list[str] = []
    for filename, content in test_content.items():
        if req_id in content or normalized in content:
            matching.append(filename)
    return sorted(matching)


def render_checklist_markdown(checklist: VerificationChecklist) -> str:
    """Render a verification checklist as markdown for context injection."""
    lines = [
        "## Verification Checklist",
        "",
        f"Spec: `{checklist.spec_name}`",
        "",
    ]

    # Task completion audit
    lines.append("### Task Completion Audit")
    lines.append("")
    if checklist.task_audit:
        lines.append("| Group | Subtask | Title | Status |")
        lines.append("|-------|---------|-------|--------|")
        for entry in checklist.task_audit:
            if entry.skipped:
                status = "SKIPPED"
            elif entry.checked:
                status = "DONE"
            else:
                status = "**UNCHECKED**"
            lines.append(f"| {entry.group_number} | {entry.subtask_id} | {entry.title} | {status} |")
        unchecked = [e for e in checklist.task_audit if not e.checked and not e.skipped]
        lines.append("")
        if unchecked:
            lines.append(
                f"**{len(unchecked)} unchecked subtask(s).** Each must be completed or documented in an erratum."
            )
        else:
            lines.append("All subtasks completed or intentionally skipped.")
    else:
        lines.append("No tasks found.")
    lines.append("")

    # Errata notice
    if checklist.has_errata:
        lines.append(
            "**Note:** Errata exist for this spec. Check `docs/errata/` "
            "and the errata DB table for documented deviations."
        )
        lines.append("")

    # Requirement-to-test coverage
    lines.append("### Requirement-to-Test Coverage")
    lines.append("")
    if checklist.requirement_coverage:
        lines.append("| Requirement | Status | Test Files |")
        lines.append("|-------------|--------|------------|")
        for mapping in checklist.requirement_coverage:
            if mapping.covered:
                status = "COVERED"
                files = ", ".join(mapping.test_files)
            else:
                status = "**UNCOVERED**"
                files = "-"
            lines.append(f"| {mapping.requirement_id} | {status} | {files} |")
        uncovered = [m for m in checklist.requirement_coverage if not m.covered]
        lines.append("")
        if uncovered:
            lines.append(
                f"**{len(uncovered)} requirement(s) without test coverage.** "
                f"Each uncovered requirement is a critical finding."
            )
        else:
            lines.append("All requirements have test coverage.")
    else:
        lines.append("No requirements found to map.")
    lines.append("")

    # Enforcement rules
    lines.append("### Enforcement Rules")
    lines.append("")
    lines.append("- Any **UNCHECKED** subtask without a corresponding erratum → FAIL verdict.")
    lines.append("- Any **UNCOVERED** requirement without test coverage → FAIL verdict.")
    lines.append("- Errata document intentional deviations — verify they are legitimate.")

    return "\n".join(lines)
