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
import re
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


def _parse_errata_markdown(spec_name: str, content: str) -> list[Erratum]:
    """Parse errata markdown content into Erratum objects.

    Supports two formats:

    - **Auto-generated**: structured ``### Finding N`` blocks with
      ``**Summary:**``, ``**Task Group:**``, ``**Requirement:**``,
      ``**Fix:**`` fields — produces one Erratum per finding block.
    - **Manual/narrative**: free-form prose — produces one synthetic
      Erratum per file, using the document title as the finding summary.

    Returns an empty list if content is empty or no meaningful content
    is found.
    """
    if not content.strip():
        return []

    errata: list[Erratum] = []

    # Detect and parse structured "### Finding N" blocks (auto-generated format)
    finding_blocks = re.split(r"### Finding \d+", content)
    if len(finding_blocks) > 1:
        for block in finding_blocks[1:]:  # skip pre-finding header
            summary_match = re.search(r"\*\*Summary:\*\*\s*(.+)", block)
            tg_match = re.search(r"\*\*Task Group:\*\*\s*(.+)", block)
            req_match = re.search(r"\*\*Requirement:\*\*\s*(.+)", block)
            fix_match = re.search(r"\*\*Fix:\*\*\s*(.+)", block)

            finding_summary = summary_match.group(1).strip() if summary_match else None
            if not finding_summary:
                continue
            errata.append(
                Erratum(
                    id=str(uuid.uuid4()),
                    spec_name=spec_name,
                    task_group=tg_match.group(1).strip() if tg_match else "1",
                    finding_summary=finding_summary,
                    requirement_ref=req_match.group(1).strip() if req_match else None,
                    fix_summary=fix_match.group(1).strip() if fix_match else None,
                )
            )

    if errata:
        return errata

    # Manual/narrative format: produce one synthetic Erratum from the title
    title_match = re.search(r"^# (.+)", content, re.MULTILINE)
    finding_summary = title_match.group(1).strip() if title_match else f"Spec erratum for {spec_name}"
    errata.append(
        Erratum(
            id=str(uuid.uuid4()),
            spec_name=spec_name,
            task_group="1",
            finding_summary=finding_summary[:500],  # cap length
        )
    )
    return errata


def index_errata_from_markdown(
    conn: duckdb.DuckDBPyConnection,
    project_root: Path,
) -> int:
    """Index errata markdown files into the DuckDB ``errata`` table.

    Reads every ``*.md`` file under ``docs/errata/``, derives
    ``spec_name`` from the filename stem (stripping the ``_auto_errata``
    suffix when present), and inserts ``Erratum`` rows for each file
    that has no existing rows for that ``spec_name``.

    Idempotent: skips files whose ``spec_name`` already has rows in the
    table. Parse failures on individual files are logged as warnings and
    skipped — they do not abort indexing of other files or raise.

    Returns the total number of rows inserted. Returns 0 silently if the
    ``errata`` table does not exist, matching the graceful-degradation
    contract of :func:`store_errata`.
    """
    errata_dir = project_root / "docs" / "errata"
    if not errata_dir.is_dir():
        logger.debug("No errata directory at %s, skipping indexing", errata_dir)
        return 0

    # Probe for table existence before touching any files
    try:
        conn.execute("SELECT 1 FROM errata LIMIT 0")
    except duckdb.CatalogException:
        logger.debug("errata table does not exist, skipping index_errata_from_markdown")
        return 0

    total_inserted = 0
    for md_file in sorted(errata_dir.glob("*.md")):
        spec_name = md_file.stem
        if spec_name.endswith("_auto_errata"):
            spec_name = spec_name[: -len("_auto_errata")]

        # Idempotency: skip if already indexed for this spec
        if query_errata(conn, spec_name, limit=1):
            logger.debug("Errata already indexed for %s, skipping", spec_name)
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            parsed = _parse_errata_markdown(spec_name, content)
        except Exception:
            logger.warning(
                "Failed to parse errata file %s, skipping",
                md_file,
                exc_info=True,
            )
            continue

        if not parsed:
            logger.warning("No errata parsed from %s, skipping", md_file)
            continue

        inserted = store_errata(conn, parsed)
        total_inserted += inserted

    if total_inserted > 0:
        logger.info(
            "Indexed %d errata from markdown files in %s",
            total_inserted,
            errata_dir,
        )
    return total_inserted
