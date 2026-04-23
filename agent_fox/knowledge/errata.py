"""Lightweight errata generation, storage, and retrieval.

Auto-generates errata when reviewer blocking occurs, stores them in
DuckDB for retrieval during future coder sessions, and persists them
to ``docs/errata/`` for human visibility.

Errata capture institutional knowledge: what went wrong, which
requirement was violated, and context about the failure. This enables
the "don't repeat mistakes" feedback loop.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Erratum:
    """A single erratum generated from a blocking review finding."""

    id: str
    spec_name: str
    task_group: str
    finding_summary: str
    requirement_ref: str | None = None
    fix_summary: str | None = None
    created_at: datetime | None = None


def generate_errata_from_findings(
    findings: list[Any],
    spec_name: str,
    task_group: str,
) -> list[Erratum]:
    """Create errata from critical/major review findings.

    Each critical or major finding produces one erratum. Minor and
    observation findings are excluded — they don't carry enough signal
    to justify persisting as institutional knowledge.

    Args:
        findings: List of ReviewFinding (or compatible) objects with
            ``severity``, ``description``, and ``requirement_ref`` attrs.
        spec_name: Spec being reviewed.
        task_group: Task group within the spec.

    Returns:
        List of Erratum objects ready for storage.
    """
    errata: list[Erratum] = []
    for f in findings:
        severity = getattr(f, "severity", "").lower()
        if severity not in ("critical", "major"):
            continue
        errata.append(
            Erratum(
                id=str(uuid.uuid4()),
                spec_name=spec_name,
                task_group=task_group,
                finding_summary=f"[{severity}] {f.description}",
                requirement_ref=getattr(f, "requirement_ref", None),
            )
        )
    return errata


def store_errata(
    conn: duckdb.DuckDBPyConnection,
    errata: list[Erratum],
) -> int:
    """Insert errata into the DuckDB ``errata`` table.

    Returns the number of rows inserted. Silently returns 0 if the
    errata table does not exist (e.g. migration not yet applied).
    """
    if not errata:
        return 0
    try:
        for e in errata:
            conn.execute(
                "INSERT INTO errata "
                "(id, spec_name, task_group, finding_summary, requirement_ref, fix_summary, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    e.id,
                    e.spec_name,
                    e.task_group,
                    e.finding_summary,
                    e.requirement_ref,
                    e.fix_summary,
                    e.created_at or datetime.now(UTC),
                ],
            )
    except duckdb.CatalogException:
        logger.debug("errata table does not exist, skipping store")
        return 0
    except Exception:
        logger.warning("Failed to store errata", exc_info=True)
        return 0
    logger.info(
        "Stored %d errata for %s/%s",
        len(errata),
        errata[0].spec_name,
        errata[0].task_group,
    )
    return len(errata)


def query_errata(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    *,
    limit: int = 10,
) -> list[Erratum]:
    """Retrieve errata for a spec, most recent first.

    Returns an empty list if the table does not exist or the query
    fails for any reason.
    """
    try:
        rows = conn.execute(
            "SELECT id, spec_name, task_group, finding_summary, "
            "requirement_ref, fix_summary, created_at "
            "FROM errata WHERE spec_name = ? "
            "ORDER BY created_at DESC LIMIT ?",
            [spec_name, limit],
        ).fetchall()
    except Exception:
        logger.debug("Could not query errata for %s", spec_name)
        return []
    return [
        Erratum(
            id=row[0],
            spec_name=row[1],
            task_group=row[2],
            finding_summary=row[3],
            requirement_ref=row[4],
            fix_summary=row[5],
            created_at=row[6],
        )
        for row in rows
    ]


def format_errata_for_prompt(errata: list[Erratum]) -> list[str]:
    """Format errata as ``[ERRATA]``-prefixed strings for prompt injection.

    Returns one string per erratum, suitable for inclusion in coder
    session context alongside ``[REVIEW]`` findings.
    """
    result: list[str] = []
    for e in errata:
        parts = [f"[ERRATA] {e.finding_summary}"]
        if e.requirement_ref:
            parts.append(f"(ref: {e.requirement_ref})")
        if e.fix_summary:
            parts.append(f"Fix: {e.fix_summary}")
        result.append(" ".join(parts))
    return result


def persist_erratum_markdown(
    errata: list[Erratum],
    project_root: Path,
) -> Path | None:
    """Write errata to a markdown file in ``docs/errata/``.

    Groups errata by spec_name and writes a single file per
    invocation. Returns the path of the written file, or None if
    no errata were provided or the write failed.

    The filename uses the spec_name to match the existing convention
    in ``docs/errata/``.
    """
    if not errata:
        return None

    spec_name = errata[0].spec_name
    errata_dir = project_root / "docs" / "errata"

    try:
        errata_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Failed to create errata directory: %s", errata_dir)
        return None

    filename = f"{spec_name}_auto_errata.md"
    filepath = errata_dir / filename

    lines = [
        f"# Errata: {spec_name} (auto-generated)",
        "",
        f"**Spec:** {spec_name}",
        f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d')}",
        "**Status:** Active",
        "**Source:** Auto-generated from reviewer blocking findings",
        "",
        "## Findings",
        "",
    ]

    for i, e in enumerate(errata, 1):
        lines.append(f"### Finding {i}")
        lines.append("")
        lines.append(f"**Summary:** {e.finding_summary}")
        if e.requirement_ref:
            lines.append(f"**Requirement:** {e.requirement_ref}")
        lines.append(f"**Task Group:** {e.task_group}")
        if e.fix_summary:
            lines.append(f"**Fix:** {e.fix_summary}")
        lines.append("")

    try:
        filepath.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        logger.warning("Failed to write erratum markdown: %s", filepath)
        return None

    logger.info("Wrote erratum markdown to %s", filepath)
    return filepath
