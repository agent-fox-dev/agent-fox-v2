"""Table mismatch fixers: traceability table and coverage matrix mismatches.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec._patterns import (
    H2_HEADING as _H2_HEADING,
)
from agent_fox.spec._patterns import (
    normalize_heading as _normalize_heading,
)

from .types import FixResult


def _find_last_table_line_in_section(
    lines: list[str],
    section_keywords: list[str],
) -> int | None:
    """Find the last table row inside a markdown section.

    Scans for a ## heading whose normalized text contains all
    *section_keywords*, then returns the index of the last pipe-delimited
    row in that section.  Returns ``None`` if no matching section or
    table is found.
    """
    in_section = False
    last_table_line: int | None = None
    for i, line in enumerate(lines):
        heading = _H2_HEADING.match(line)
        if heading:
            normalized = _normalize_heading(heading.group(1).strip())
            in_section = all(kw in normalized for kw in section_keywords)
            continue
        if in_section and line.strip().startswith("|"):
            last_table_line = i
    return last_table_line


def _append_rows_to_table(
    file_path: Path,
    lines: list[str],
    last_table_line: int,
    new_rows: list[str],
) -> None:
    """Insert *new_rows* after *last_table_line* and write back."""
    for j, row in enumerate(new_rows):
        lines.insert(last_table_line + 1 + j, row)
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fix_traceability_table_mismatch(
    spec_name: str,
    spec_path: Path,
    missing_req_ids: list[str],
) -> list[FixResult]:
    """Append missing requirement IDs to the traceability table in tasks.md.

    Adds rows with TODO placeholders for each missing requirement.
    """
    tasks_path = spec_path / "tasks.md"
    if not tasks_path.is_file() or not missing_req_ids:
        return []

    lines = tasks_path.read_text(encoding="utf-8").splitlines()
    last = _find_last_table_line_in_section(lines, ["traceability"])
    if last is None:
        return []

    rows = [f"| {rid} | TODO | TODO | TODO |" for rid in sorted(missing_req_ids)]
    _append_rows_to_table(tasks_path, lines, last, rows)

    return [
        FixResult(
            rule="traceability-table-mismatch",
            spec_name=spec_name,
            file=str(tasks_path),
            description=(f"Appended {len(missing_req_ids)} missing requirement(s) to traceability table"),
        )
    ]


def fix_coverage_matrix_mismatch(
    spec_name: str,
    spec_path: Path,
    missing_req_ids: list[str],
) -> list[FixResult]:
    """Append missing requirement IDs to the coverage matrix in test_spec.md.

    Adds rows with TODO placeholders for each missing requirement.
    """
    ts_path = spec_path / "test_spec.md"
    if not ts_path.is_file() or not missing_req_ids:
        return []

    lines = ts_path.read_text(encoding="utf-8").splitlines()
    last = _find_last_table_line_in_section(lines, ["coverage", "matrix"])
    if last is None:
        return []

    rows = [f"| {rid} | TODO | TODO |" for rid in sorted(missing_req_ids)]
    _append_rows_to_table(ts_path, lines, last, rows)

    return [
        FixResult(
            rule="coverage-matrix-mismatch",
            spec_name=spec_name,
            file=str(ts_path),
            description=(f"Appended {len(missing_req_ids)} missing requirement(s) to coverage matrix"),
        )
    ]
