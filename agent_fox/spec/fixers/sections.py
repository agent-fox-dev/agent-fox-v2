"""Section fixers: append missing sections (traceability table, coverage matrix,
definition of done, error table, correctness properties) to spec files.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec._patterns import (
    H2_HEADING as _H2_HEADING,
)
from agent_fox.spec._patterns import (
    extract_req_ids_from_text as _extract_req_ids_from_text,
)
from agent_fox.spec._patterns import (
    extract_test_spec_ids as _extract_test_spec_ids,
)
from agent_fox.spec._patterns import (
    normalize_heading as _normalize_heading,
)

from .types import FixResult


def fix_missing_traceability_table(
    spec_name: str,
    spec_path: Path,
) -> list[FixResult]:
    """Append a Traceability section with a table to tasks.md.

    Generates a skeleton table populated with requirement IDs from
    requirements.md and matching test spec entries from test_spec.md.
    """
    tasks_path = spec_path / "tasks.md"
    req_path = spec_path / "requirements.md"
    if not tasks_path.is_file() or not req_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")
    req_ids = sorted(_extract_req_ids_from_text(req_text))
    if not req_ids:
        return []

    # Try to find matching test spec entries
    ts_ids = _extract_test_spec_ids(spec_path)
    ts_text = ""
    ts_path = spec_path / "test_spec.md"
    if ts_path.is_file():
        ts_text = ts_path.read_text(encoding="utf-8")

    # Build table rows
    rows: list[str] = []
    for req_id in req_ids:
        # Find test spec entries that reference this req ID
        matching_ts = ""
        for ts_id in sorted(ts_ids):
            # Check if this TS entry references the req ID
            if req_id in ts_text:
                # Simple heuristic: find TS entries near the req ID mention
                matching_ts = ts_id
                break
        rows.append(f"| {req_id} | {matching_ts} | TODO | TODO |")

    section = (
        "\n## Traceability\n\n"
        "| Requirement | Test Spec Entry | Implemented By Task "
        "| Verified By Test |\n"
        "|-------------|-----------------|---------------------"
        "|------------------|\n"
    )
    section += "\n".join(rows) + "\n"

    text = tasks_path.read_text(encoding="utf-8")
    text = text.rstrip() + "\n" + section
    tasks_path.write_text(text, encoding="utf-8")

    return [
        FixResult(
            rule="missing-traceability-table",
            spec_name=spec_name,
            file=str(tasks_path),
            description=(f"Appended Traceability section with {len(req_ids)} requirement(s)"),
        )
    ]


def fix_missing_coverage_matrix(
    spec_name: str,
    spec_path: Path,
) -> list[FixResult]:
    """Append a Coverage Matrix section to test_spec.md.

    Generates a skeleton table populated with requirement IDs from
    requirements.md and matching test spec entry IDs.
    """
    ts_path = spec_path / "test_spec.md"
    req_path = spec_path / "requirements.md"
    if not ts_path.is_file() or not req_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")
    req_ids = sorted(_extract_req_ids_from_text(req_text))
    if not req_ids:
        return []

    ts_text = ts_path.read_text(encoding="utf-8")
    ts_ids = sorted(_extract_test_spec_ids(spec_path))

    # Build table rows -- match each req ID to a test spec entry
    rows: list[str] = []
    for req_id in req_ids:
        matching_ts = ""
        for ts_id in ts_ids:
            # Check if this TS entry heading section references the req ID
            if req_id in ts_text:
                matching_ts = ts_id
                break
        test_type = "unit"
        if matching_ts and "P" in matching_ts:
            test_type = "property"
        rows.append(f"| {req_id} | {matching_ts} | {test_type} |")

    section = (
        "\n## Coverage Matrix\n\n| Requirement | Test Spec Entry | Type |\n|-------------|-----------------|------|\n"
    )
    section += "\n".join(rows) + "\n"

    text = ts_text.rstrip() + "\n" + section
    ts_path.write_text(text, encoding="utf-8")

    return [
        FixResult(
            rule="missing-coverage-matrix",
            spec_name=spec_name,
            file=str(ts_path),
            description=(f"Appended Coverage Matrix section with {len(req_ids)} requirement(s)"),
        )
    ]


_DOD_TEMPLATE = """\

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and pushed to remote
7. Feature branch is merged back to `develop`
8. `tasks.md` checkboxes are updated to reflect completion
"""


_ERROR_TABLE_TEMPLATE = """\

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| TODO | TODO | TODO |
"""

_CORRECTNESS_PROPS_TEMPLATE = """\

## Correctness Properties

### Property 1: TODO

*For any* valid input, THE system SHALL TODO.

**Validates: Requirements TODO**
"""


def _append_missing_section(
    spec_name: str,
    file_path: Path,
    heading_keywords: list[str],
    template: str,
    rule: str,
    description: str,
) -> list[FixResult]:
    """Append a section to a file if it doesn't already contain one.

    Checks for an H2 heading whose normalized text contains all keywords.
    If absent, appends the template text and returns a FixResult.
    """
    if not file_path.is_file():
        return []

    text = file_path.read_text(encoding="utf-8")

    for line in text.splitlines():
        m = _H2_HEADING.match(line)
        if m:
            normalized = _normalize_heading(m.group(1))
            if all(kw in normalized for kw in heading_keywords):
                return []

    file_path.write_text(text.rstrip() + "\n" + template, encoding="utf-8")
    return [FixResult(rule=rule, spec_name=spec_name, file=str(file_path), description=description)]


def fix_missing_definition_of_done(
    spec_name: str,
    design_path: Path,
) -> list[FixResult]:
    """Append a Definition of Done section to design.md."""
    return _append_missing_section(
        spec_name,
        design_path,
        ["definition", "done"],
        _DOD_TEMPLATE,
        "missing-definition-of-done",
        "Appended Definition of Done section",
    )


def fix_missing_error_table(
    spec_name: str,
    design_path: Path,
) -> list[FixResult]:
    """Append an Error Handling section with empty table to design.md."""
    return _append_missing_section(
        spec_name,
        design_path,
        ["error", "handling"],
        _ERROR_TABLE_TEMPLATE,
        "missing-error-table",
        "Appended Error Handling section with table template",
    )


def fix_missing_correctness_properties(
    spec_name: str,
    design_path: Path,
) -> list[FixResult]:
    """Append a Correctness Properties section stub to design.md."""
    return _append_missing_section(
        spec_name,
        design_path,
        ["correctness", "properties"],
        _CORRECTNESS_PROPS_TEMPLATE,
        "missing-correctness-properties",
        "Appended Correctness Properties section stub (fill in property details)",
    )
