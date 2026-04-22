"""Context assembly: spec documents, findings, memory facts, steering.

Gathers spec documents, review/drift/verification findings from DuckDB,
memory facts, and steering directives into session context for coding
agents.

Requirements: 03-REQ-4.1 through 03-REQ-4.E1, 03-REQ-5.1, 03-REQ-5.2,
              27-REQ-5.1, 27-REQ-5.2, 27-REQ-5.3, 27-REQ-5.E1, 27-REQ-5.E2,
              27-REQ-10.1, 27-REQ-10.2, 32-REQ-8.1, 32-REQ-8.2,
              42-REQ-1.1, 42-REQ-1.2, 42-REQ-4.1, 42-REQ-4.2
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.session.steering import load_steering

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriorFinding:
    """A finding from a prior task group, tagged by type.

    Requirements: 42-REQ-4.1, 42-REQ-4.2
    """

    type: str  # "review" | "drift" | "verification"
    group: str  # task_group value
    severity: str  # severity level or verdict
    description: str  # description text or evidence
    created_at: str  # ISO timestamp string for sorting


# ---------------------------------------------------------------------------
# Findings rendering
# ---------------------------------------------------------------------------

# Core spec files — always expected to exist for every spec.
_CORE_SPEC_FILES: list[tuple[str, str]] = [
    ("requirements.md", "## Requirements"),
    ("design.md", "## Design"),
    ("test_spec.md", "## Test Specification"),
    ("tasks.md", "## Tasks"),
]

# Archetype-produced files — only present after the corresponding archetype
# (Skeptic / Verifier) has run.  Included silently when they exist on disk,
# skipped silently when they don't.
_ARCHETYPE_SPEC_FILES: list[tuple[str, str]] = [
    ("review.md", "## Skeptic Review"),
    ("verification.md", "## Verification Report"),
]


def _render_severity_findings(
    findings: list,
    title: str,
    format_finding: Callable[..., str],
    *,
    show_empty_groups: bool = False,
) -> str:
    """Render findings grouped by severity as a markdown section.

    Args:
        findings: List of finding objects with a ``severity`` attribute.
        title: Markdown heading for the section (e.g. "## Skeptic Review").
        format_finding: Callable that formats a single finding as a string.
        show_empty_groups: If True, render "(none)" for severity levels
            with no findings.
    """
    severity_groups = {
        "critical": "### Critical Findings",
        "major": "### Major Findings",
        "minor": "### Minor Findings",
        "observation": "### Observations",
    }

    lines = [title, ""]
    counts: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "observation": 0}

    for sev, header in severity_groups.items():
        sev_findings = [f for f in findings if f.severity == sev]
        counts[sev] = len(sev_findings)
        if sev_findings:
            lines.append(header)
            for f in sev_findings:
                lines.append(format_finding(f))
            lines.append("")
        elif show_empty_groups:
            lines.append(header)
            lines.append("(none)")
            lines.append("")

    lines.append(
        f"Summary: {counts['critical']} critical, {counts['major']} major, "
        f"{counts['minor']} minor, {counts['observation']} observations."
    )

    return "\n".join(lines)


def render_drift_context(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> str | None:
    """Render active drift findings as a markdown section.

    Returns None if no findings exist (32-REQ-8.E1).

    Requirements: 32-REQ-8.1, 32-REQ-8.2
    """
    from agent_fox.knowledge.review_store import (
        query_active_drift_findings,
    )

    findings = query_active_drift_findings(conn, spec_name)
    if not findings:
        return None

    def _format(f):
        desc = sanitize_prompt_content(f.description, label="drift-finding")
        refs = []
        if f.spec_ref:
            refs.append(f"spec: {f.spec_ref}")
        if f.artifact_ref:
            refs.append(f"artifact: {f.artifact_ref}")
        if refs:
            desc += f" ({', '.join(refs)})"
        return f"- {desc}"

    return _render_severity_findings(findings, "## Oracle Drift Report", _format)


def render_review_context(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> str | None:
    """Render active findings as a markdown section.

    Returns None if no findings exist (27-REQ-5.E2).

    Requirements: 27-REQ-5.1, 27-REQ-5.3
    """
    from agent_fox.knowledge.review_store import (
        query_active_findings,
    )

    findings = query_active_findings(conn, spec_name)
    if not findings:
        return None

    def _format_review(f):
        sanitized = sanitize_prompt_content(f.description, label="review-finding")
        return f"- [severity: {f.severity}] {sanitized}"

    return _render_severity_findings(
        findings,
        "## Skeptic Review",
        _format_review,
        show_empty_groups=True,
    )


def render_verification_context(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> str | None:
    """Render active verdicts as a markdown section.

    Returns None if no verdicts exist (27-REQ-5.E2).

    Requirements: 27-REQ-5.2, 27-REQ-5.3
    """
    from agent_fox.knowledge.review_store import (
        query_active_verdicts,
    )

    verdicts = query_active_verdicts(conn, spec_name)
    if not verdicts:
        return None

    lines = [
        "## Verification Report",
        "",
        "| Requirement | Status | Notes |",
        "|-------------|--------|-------|",
    ]

    has_fail = False
    for v in verdicts:
        raw_notes = v.evidence or ""
        notes = sanitize_prompt_content(raw_notes, label="verification-evidence") if raw_notes else ""
        lines.append(f"| {v.requirement_id} | {v.verdict} | {notes} |")
        if v.verdict == "FAIL":
            has_fail = True

    lines.append("")
    overall = "FAIL" if has_fail else "PASS"
    lines.append(f"Verdict: {overall}")

    return "\n".join(lines)


def _migrate_legacy_files(
    conn: duckdb.DuckDBPyConnection,
    spec_dir: Path,
    spec_name: str,
) -> None:
    """Migrate legacy review.md/verification.md files to DB records.

    Only runs when no DB records exist for the spec. On parse failure,
    logs a warning and skips (27-REQ-10.E1).

    Requirements: 27-REQ-10.1, 27-REQ-10.2, 27-REQ-10.E1
    """
    from agent_fox.knowledge.review_store import (
        insert_findings,
        insert_verdicts,
        query_active_findings,
        query_active_verdicts,
    )
    from agent_fox.session.review_parser import (
        parse_legacy_review_md,
        parse_legacy_verification_md,
    )

    # Table-driven legacy migration: (filename, query_fn, parse_fn, insert_fn, label)
    _migrations: list[tuple[str, Any, Any, Any, str]] = [
        (
            "review.md",
            query_active_findings,
            parse_legacy_review_md,
            insert_findings,
            "findings",
        ),
        (
            "verification.md",
            query_active_verdicts,
            parse_legacy_verification_md,
            insert_verdicts,
            "verdicts",
        ),
    ]
    for filename, query_fn, parse_fn, insert_fn, label in _migrations:
        path = spec_dir / filename
        if not path.exists() or query_fn(conn, spec_name):
            continue
        try:
            content = path.read_text(encoding="utf-8")
            records = parse_fn(content, spec_name, "legacy", "legacy-migration")
            if records:
                insert_fn(conn, records)
                logger.info("Migrated %d %s from %s", len(records), label, path)
        except Exception:
            logger.warning(
                "Failed to migrate legacy %s file %s, skipping",
                label,
                path,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def assemble_context(
    spec_dir: Path,
    task_group: int,
    memory_facts: list[str] | None = None,
    *,
    conn: duckdb.DuckDBPyConnection,
    project_root: Path | None = None,
) -> str:
    """Assemble task-specific context for a coding session.

    Reads the following files from spec_dir (if they exist):
    - requirements.md
    - design.md
    - test_spec.md
    - tasks.md

    Renders review/verification/drift sections from DuckDB
    (27-REQ-5.1, 27-REQ-5.2, 38-REQ-4.1, 38-REQ-4.2).
    DB errors propagate — no file-based fallback (38-REQ-3.E1).

    Appends relevant memory facts (if provided).

    When project_root is provided, includes steering directives from
    .specs/steering.md after spec files and before memory facts
    (64-REQ-2.1, 64-REQ-2.2).

    Returns a formatted string with section headers.

    Logs a warning for any missing spec file but does not raise.
    """
    sections: list[str] = []

    # Derive spec_name from directory name
    spec_name = spec_dir.name

    # DB-backed rendering — errors propagate (38-REQ-3.E1, 38-REQ-4.2)
    db_rendered_files: set[str] = set()

    # Attempt legacy file migration first (27-REQ-10.1, 27-REQ-10.2)
    _migrate_legacy_files(conn, spec_dir, spec_name)

    # DB-backed rendering (27-REQ-5.1, 27-REQ-5.2, 38-REQ-4.3)
    review_md = render_review_context(conn, spec_name)
    if review_md is not None:
        sections.append(review_md)
        db_rendered_files.add("review.md")

    verification_md = render_verification_context(conn, spec_name)
    if verification_md is not None:
        sections.append(verification_md)
        db_rendered_files.add("verification.md")

    # Render oracle drift report (32-REQ-8.1)
    drift_md = render_drift_context(conn, spec_name)
    if drift_md is not None:
        sections.append(drift_md)

    # 03-REQ-4.1: Read spec documents
    file_sections: list[str] = []
    for filename, header in _CORE_SPEC_FILES:
        filepath = spec_dir / filename
        if not filepath.exists():
            # 03-REQ-4.E1: Skip missing files with a warning
            logger.warning(
                "Spec file '%s' not found in %s, skipping",
                filename,
                spec_dir,
            )
            continue
        content = filepath.read_text(encoding="utf-8")
        safe_content = sanitize_prompt_content(content, label="spec")
        file_sections.append(f"{header}\n\n{safe_content}")

    # Include archetype-produced files (review.md, verification.md) only
    # when they exist on disk and weren't already rendered from the DB.
    for filename, header in _ARCHETYPE_SPEC_FILES:
        if filename in db_rendered_files:
            continue
        filepath = spec_dir / filename
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        safe_content = sanitize_prompt_content(content, label="spec")
        file_sections.append(f"{header}\n\n{safe_content}")

    # Insert file sections before DB-rendered sections
    sections = file_sections + sections

    # 64-REQ-2.1, 64-REQ-2.2: Include steering directives after spec files,
    # before memory facts.
    if project_root is not None:
        steering_content = load_steering(project_root, spec_root=spec_dir.parent)
        if steering_content:
            sections.append(f"## Steering Directives\n\n{steering_content}")

    # 03-REQ-4.2: Include memory facts (sanitize stored facts against injection)
    if memory_facts:
        facts_text = "\n".join(f"- {sanitize_prompt_content(fact, label='memory-fact')}" for fact in memory_facts)
        sections.append(f"## Memory Facts\n\n{facts_text}")

    # 39-REQ-6.1, 39-REQ-6.2: Include prior group findings
    if task_group > 1:
        try:
            prior_findings = get_prior_group_findings(
                conn,
                spec_name,
                task_group=task_group,
            )
            if prior_findings:
                prior_section = render_prior_group_findings(prior_findings)
                sections.append(prior_section)
        except Exception:
            logger.debug(
                "Failed to fetch prior group findings for %s group %d",
                spec_name,
                task_group,
            )

    # 03-REQ-4.3: Return formatted string with section headers
    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Prior group findings
# ---------------------------------------------------------------------------


def get_prior_group_findings(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    *,
    task_group: int,
) -> list[PriorFinding]:
    """Query active findings from all three tables for prior task groups.

    Returns PriorFinding objects from groups 1 through task_group-1 for the
    given spec, excluding superseded findings, sorted by created_at ascending.

    Queries review_findings, drift_findings, and verification_results tables.
    If any table does not exist (pre-migration database), that table's results
    are silently skipped.

    Requirements: 42-REQ-4.1, 42-REQ-4.E1
    """
    if task_group <= 1:
        return []

    # Build list of prior group identifiers (as strings, matching DB format)
    prior_groups = [str(g) for g in range(1, task_group)]
    placeholders = ", ".join("?" for _ in prior_groups)

    findings: list[PriorFinding] = []

    def _query_findings_table(
        table: str,
        finding_type: str,
        columns: str = "CAST(id AS VARCHAR), severity, description, task_group, CAST(created_at AS VARCHAR)",
        *,
        row_mapper: Callable[[tuple], PriorFinding] | None = None,
    ) -> None:
        """Query a findings table and append results to the findings list."""
        try:
            rows = conn.execute(
                f"SELECT {columns} FROM {table} "
                f"WHERE spec_name = ? AND task_group IN ({placeholders}) "
                f"AND superseded_by IS NULL",
                [spec_name, *prior_groups],
            ).fetchall()
            for row in rows:
                if row_mapper is not None:
                    findings.append(row_mapper(row))
                else:
                    findings.append(
                        PriorFinding(
                            type=finding_type,
                            group=str(row[3]),
                            severity=str(row[1]),
                            description=str(row[2]),
                            created_at=str(row[4]) if row[4] is not None else "",
                        )
                    )
        except Exception:
            logger.debug(
                "Failed to query %s for prior groups (table may not exist)",
                table,
            )

    def _map_verification_row(row: tuple) -> PriorFinding:
        verdict = str(row[1])
        req_id = str(row[2])
        evidence = str(row[3]) if row[3] is not None else ""
        description = f"{req_id}: {verdict}"
        if evidence:
            description = f"{req_id}: {verdict} — {evidence}"
        return PriorFinding(
            type="verification",
            group=str(row[4]),
            severity=verdict,
            description=description,
            created_at=str(row[5]) if row[5] is not None else "",
        )

    _query_findings_table("review_findings", "review")
    _query_findings_table("drift_findings", "drift")
    _query_findings_table(
        "verification_results",
        "verification",
        columns="CAST(id AS VARCHAR), verdict, requirement_id, evidence, task_group, CAST(created_at AS VARCHAR)",
        row_mapper=_map_verification_row,
    )

    return findings


def render_prior_group_findings(findings: list[PriorFinding]) -> str:
    """Render prior group findings as a markdown section.

    Findings are rendered under a "Prior Group Findings" header with each
    finding prefixed by its group number and type label. Findings are
    sorted by created_at ascending.

    Returns empty string when findings list is empty (causes section omission).

    Requirements: 42-REQ-4.2, 42-REQ-4.3, 42-REQ-4.E2
    """
    if not findings:
        return ""

    # Sort by created_at ascending (42-REQ-4.3)
    sorted_findings = sorted(findings, key=lambda f: f.created_at)

    lines = ["## Prior Group Findings", ""]

    for f in sorted_findings:
        group_label = f"[group {f.group}]"
        type_label = f"[{f.type}]"
        sev_label = f"[{f.severity}]"
        safe_desc = sanitize_prompt_content(f.description, label="prior-finding")
        lines.append(f"- {group_label} {type_label} {sev_label} {safe_desc}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Causal context selection
# ---------------------------------------------------------------------------


def select_context_with_causal(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    touched_files: list[str],
    *,
    keyword_facts: list[dict],
    max_facts: int = 50,
    causal_budget: int = 10,
) -> list[dict]:
    """Select session context facts with causal enhancement.

    Note: The causal graph traversal (CausalFact, traverse_with_reviews) has
    been removed as part of the knowledge decoupling (spec 114). This function
    now returns keyword_facts trimmed to max_facts without causal enhancement.
    """
    return keyword_facts[:max_facts]
