"""Spec fixer: auto-fix functions for mechanically fixable lint findings.

Each fixer reads a file, applies a transformation, and writes back.
The module is separate from the validator to maintain single-responsibility:
validator detects, fixer corrects.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_fox.spec._patterns import (
    CHECKBOX_LINE as _CHECKBOX_LINE,
)
from agent_fox.spec._patterns import (
    H2_HEADING as _H2_HEADING,
)
from agent_fox.spec._patterns import (
    MALFORMED_ARCHETYPE_TAG as _MALFORMED_ARCHETYPE_TAG,
)
from agent_fox.spec._patterns import (
    VALID_CHECKBOX_CHARS as _VALID_CHECKBOX_CHARS,
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
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import (
    _ARCHETYPE_TAG,
    _DEP_TABLE_HEADER,
    _GROUP_PATTERN,
    _KNOWN_ARCHETYPES,
    _SUBTASK_PATTERN,
    _TABLE_SEP,
)
from agent_fox.spec.validator import Finding

logger = logging.getLogger(__name__)

# -- Regex patterns for parsing stale-dependency finding messages ---------------

_SUGGESTION_PATTERN = re.compile(r"Suggestion: (.+)$")
_IDENTIFIER_PATTERN = re.compile(r"identifier `([^`]+)`")


@dataclass(frozen=True)
class IdentifierFix:
    """A single identifier correction from AI validation.

    Requirements: 21-REQ-5.1
    """

    original: str  # the stale identifier (e.g., "SnippetStore")
    suggestion: str  # the AI-suggested replacement (e.g., "Store")
    upstream_spec: str  # which upstream spec this relates to


@dataclass(frozen=True)
class FixResult:
    """Result of applying a single fix."""

    rule: str
    spec_name: str
    file: str
    description: str


# Set of rules that have auto-fixers
FIXABLE_RULES = {
    "coarse-dependency",
    "missing-verification",
    "stale-dependency",
    "inconsistent-req-id-format",
    "missing-traceability-table",
    "missing-coverage-matrix",
    "missing-definition-of-done",
    "missing-error-table",
    "missing-correctness-properties",
    "invalid-archetype-tag",
    "malformed-archetype-tag",
    "invalid-checkbox-state",
    "traceability-table-mismatch",
    "coverage-matrix-mismatch",
}

# AI-specific fixable rules (only active when --ai flag is set)
AI_FIXABLE_RULES = {"vague-criterion", "implementation-leak", "untraced-requirement"}

# Regex for locating criterion IDs in requirements.md
# Supports bracket format: [99-REQ-1.1] and bold format: **99-REQ-1.1:**
_CRITERION_BRACKET = re.compile(
    r"^(\s*\d+\.\s*)\[({cid})\]\s*(.*)$",
)
_CRITERION_BOLD = re.compile(
    r"^(\s*\d+\.\s*)\*\*({cid}):\*\*\s*(.*)$",
)


def fix_stale_dependency(
    spec_name: str,
    prd_path: Path,
    fixes: list[IdentifierFix],
) -> list[FixResult]:
    """Apply AI-suggested identifier corrections to Relationship text.

    For each IdentifierFix:
    1. Read prd.md content.
    2. Find the backtick-delimited original identifier in Relationship text.
    3. Replace it with the suggested identifier (preserving backticks).
    4. Write the modified content back.

    Skips fixes where:
    - suggestion is None or empty
    - the suggested identifier already appears in the Relationship text
    - the original identifier is not found in the file

    Requirements: 21-REQ-5.1, 21-REQ-5.2, 21-REQ-5.E1, 21-REQ-5.E3
    """
    if not prd_path.is_file():
        return []

    results: list[FixResult] = []

    for fix in fixes:
        # Skip empty suggestions (21-REQ-5.E1)
        if not fix.suggestion:
            continue

        text = prd_path.read_text(encoding="utf-8")

        original_backticked = f"`{fix.original}`"
        suggestion_backticked = f"`{fix.suggestion}`"

        # Skip if original not found in file
        if original_backticked not in text:
            # Also skip if suggestion already present (21-REQ-5.E3)
            continue

        # Skip if suggestion already present to avoid duplicates (21-REQ-5.E3)
        if suggestion_backticked in text:
            continue

        # Replace the original with the suggestion
        text = text.replace(original_backticked, suggestion_backticked)
        prd_path.write_text(text, encoding="utf-8")

        results.append(
            FixResult(
                rule="stale-dependency",
                spec_name=spec_name,
                file=str(prd_path),
                description=(
                    f"Replaced stale identifier `{fix.original}` with "
                    f"`{fix.suggestion}` (upstream: {fix.upstream_spec})"
                ),
            )
        )

    return results


def fix_coarse_dependency(
    spec_name: str,
    prd_path: Path,
    known_specs: dict[str, list[int]],
    current_spec_groups: list[int],
) -> list[FixResult]:
    """Rewrite a standard-format dependency table to group-level format.

    Algorithm:
    1. Read prd.md and locate the standard header line
       (``| This Spec | Depends On |``).
    2. Parse each data row to extract (this_spec, depends_on, description).
    3. For each row, look up the upstream spec in known_specs:
       - from_group = last group of upstream spec (or 0 if unknown)
       - to_group = first group of current spec (or 0 if unknown)
    4. Replace the entire table (header + separator + rows) with the
       alt-format equivalent:
       ``| Spec | From Group | To Group | Relationship |``
    5. Write the modified content back to prd_path.

    Returns a list of FixResult describing what was changed.
    Returns an empty list if no standard-format table was found.

    Requirements: 20-REQ-6.3, 20-REQ-6.E2
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the standard-format table header
    header_idx: int | None = None
    for i, line in enumerate(lines):
        if _DEP_TABLE_HEADER.search(line):
            header_idx = i
            break

    if header_idx is None:
        return []

    # Determine where the table ends (header + separator + data rows)
    table_start = header_idx
    table_end = header_idx + 1  # at least the header

    i = header_idx + 1
    while i < len(lines):
        row = lines[i]
        if _TABLE_SEP.match(row):
            table_end = i + 1
            i += 1
            continue
        stripped = row.strip()
        if stripped.startswith("|"):
            table_end = i + 1
            i += 1
            continue
        break

    # Parse data rows (skip header and separator)
    parsed_rows: list[tuple[str, str]] = []  # (depends_on, description)
    for i in range(header_idx + 1, table_end):
        row = lines[i]
        if _TABLE_SEP.match(row):
            continue
        stripped = row.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        # cells[0] = this_spec, cells[1] = depends_on, cells[2] = description
        depends_on = cells[1].strip()
        description = cells[2].strip() if len(cells) >= 3 else ""
        parsed_rows.append((depends_on, description))

    if not parsed_rows:
        return []

    # Build replacement table in alt format
    to_group = current_spec_groups[0] if current_spec_groups else 0
    new_lines: list[str] = []
    new_lines.append("| Spec | From Group | To Group | Relationship |")
    new_lines.append("|------|-----------|----------|--------------|")
    for depends_on, description in parsed_rows:
        upstream_groups = known_specs.get(depends_on, [])
        from_group = max(upstream_groups) if upstream_groups else 0
        new_lines.append(
            f"| {depends_on} | {from_group} | {to_group} | {description} |"
        )

    # Replace the table in the original text
    result_lines = lines[:table_start] + new_lines + lines[table_end:]
    prd_path.write_text("\n".join(result_lines) + "\n", encoding="utf-8")

    return [
        FixResult(
            rule="coarse-dependency",
            spec_name=spec_name,
            file=str(prd_path),
            description=(
                f"Rewrote standard-format dependency table to group-level "
                f"format ({len(parsed_rows)} row(s))"
            ),
        )
    ]


def fix_missing_verification(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Append a verification step to task groups that lack one.

    For each task group without a N.V subtask:
    1. Find the last subtask line of the group.
    2. Insert after it:
         - [ ] N.V Verify task group N
           - [ ] All spec tests pass
           - [ ] No linter warnings
           - [ ] No regressions in existing tests

    Returns a list of FixResult, one per group fixed.
    Returns an empty list if all groups already have verification steps.

    Requirements: 20-REQ-6.4
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # First pass: identify groups and their subtask ranges
    groups: list[dict] = []
    current_group: dict | None = None

    for i, line in enumerate(lines):
        group_match = _GROUP_PATTERN.match(line)
        if group_match:
            if current_group is not None:
                groups.append(current_group)
            title = group_match.group(4)
            current_group = {
                "number": int(group_match.group(3)),
                "title": title,
                "start": i,
                "last_subtask_line": i,
                "has_verify": False,
            }
            continue

        if current_group is not None:
            subtask_match = _SUBTASK_PATTERN.match(line)
            if subtask_match:
                st_id = subtask_match.group(2)
                current_group["last_subtask_line"] = i
                if re.match(rf"^{current_group['number']}\.V$", st_id):
                    current_group["has_verify"] = True

    if current_group is not None:
        groups.append(current_group)

    # Find groups that need verification steps (checkpoint groups are
    # themselves a final verification and never need a N.V subtask)
    groups_to_fix = [
        g
        for g in groups
        if not g["has_verify"] and not g["title"].startswith("Checkpoint")
    ]
    if not groups_to_fix:
        return []

    # Insert verification steps in reverse order to preserve line indices
    results: list[FixResult] = []
    for group in reversed(groups_to_fix):
        num = group["number"]
        insert_after = group["last_subtask_line"]
        verification_lines = [
            f"  - [ ] {num}.V Verify task group {num}",
            "    - [ ] All spec tests pass",
            "    - [ ] No linter warnings",
            "    - [ ] No regressions in existing tests",
        ]
        # Insert after the last subtask line
        for j, vline in enumerate(verification_lines):
            lines.insert(insert_after + 1 + j, vline)

        results.append(
            FixResult(
                rule="missing-verification",
                spec_name=spec_name,
                file=str(tasks_path),
                description=(f"Appended verification step {num}.V to task group {num}"),
            )
        )

    # Reverse results so they're in group order (we built them reversed)
    results.reverse()

    tasks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def fix_inconsistent_req_id_format(
    spec_name: str,
    req_path: Path,
) -> list[FixResult]:
    """Convert bold-format requirement IDs to bracket format.

    Replaces **NN-REQ-N.N:** with [NN-REQ-N.N] throughout requirements.md.
    """
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")

    # Pattern: **05-REQ-1.2:** or **05-REQ-1.E1:**
    bold_pattern = re.compile(r"\*\*(\d{2}-REQ-\d+\.(?:\d+|E\d+)):\*\*")

    new_text, count = bold_pattern.subn(r"[\1]", text)
    if count == 0:
        return []

    req_path.write_text(new_text, encoding="utf-8")
    return [
        FixResult(
            rule="inconsistent-req-id-format",
            spec_name=spec_name,
            file=str(req_path),
            description=(
                f"Converted {count} bold-format requirement ID(s) to bracket format"
            ),
        )
    ]


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
            description=(
                f"Appended Traceability section with {len(req_ids)} requirement(s)"
            ),
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

    # Build table rows — match each req ID to a test spec entry
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
        "\n## Coverage Matrix\n\n"
        "| Requirement | Test Spec Entry | Type |\n"
        "|-------------|-----------------|------|\n"
    )
    section += "\n".join(rows) + "\n"

    text = ts_text.rstrip() + "\n" + section
    ts_path.write_text(text, encoding="utf-8")

    return [
        FixResult(
            rule="missing-coverage-matrix",
            spec_name=spec_name,
            file=str(ts_path),
            description=(
                f"Appended Coverage Matrix section with {len(req_ids)} requirement(s)"
            ),
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
    return [
        FixResult(
            rule=rule, spec_name=spec_name, file=str(file_path), description=description
        )
    ]


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


def _fix_archetype_tags_in_file(
    spec_name: str,
    tasks_path: Path,
    *,
    mode: str,
) -> list[FixResult]:
    """Shared fixer for archetype tag issues.

    Args:
        mode: ``"invalid"`` to remove unknown tags, ``"malformed"`` to
            normalize syntax and remove duplicates.
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    results: list[FixResult] = []

    for i, line in enumerate(lines):
        if not re.match(r"^- \[.\]", line):
            continue

        if mode == "invalid":
            match = _ARCHETYPE_TAG.search(line)
            if match and match.group(1) not in _KNOWN_ARCHETYPES:
                old_tag = match.group()
                lines[i] = line.replace(old_tag, "").rstrip()
                lines[i] = re.sub(r"  +", " ", lines[i]).rstrip()
                results.append(
                    FixResult(
                        rule="invalid-archetype-tag",
                        spec_name=spec_name,
                        file=str(tasks_path),
                        description=(
                            f"Removed unknown archetype tag '{old_tag}' "
                            f"from line {i + 1} (defaults to coder)"
                        ),
                    )
                )

        elif mode == "malformed":
            # Handle duplicate well-formed tags: keep first, remove rest
            all_good = list(_ARCHETYPE_TAG.finditer(line))
            if len(all_good) > 1:
                new_line = line
                for m in reversed(all_good[1:]):
                    new_line = new_line[: m.start()] + new_line[m.end() :]
                lines[i] = re.sub(r"  +", " ", new_line).rstrip()
                results.append(
                    FixResult(
                        rule="malformed-archetype-tag",
                        spec_name=spec_name,
                        file=str(tasks_path),
                        description=(
                            f"Removed duplicate archetype tags "
                            f"on line {i + 1}, kept first"
                        ),
                    )
                )
                continue

            # Skip lines that already have a well-formed tag
            if _ARCHETYPE_TAG.search(line):
                continue

            # Try to normalize malformed tags
            bad_match = _MALFORMED_ARCHETYPE_TAG.search(line)
            if bad_match:
                bad_tag = bad_match.group()
                name_match = re.search(r"(\w+)\]$", bad_tag)
                if name_match:
                    name = name_match.group(1).lower()
                    normalized = f"[archetype: {name}]"
                    lines[i] = line.replace(bad_tag, normalized)
                    results.append(
                        FixResult(
                            rule="malformed-archetype-tag",
                            spec_name=spec_name,
                            file=str(tasks_path),
                            description=(
                                f"Normalized '{bad_tag}' to "
                                f"'{normalized}' on line {i + 1}"
                            ),
                        )
                    )

    if results:
        tasks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def fix_invalid_archetype_tag(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Remove archetype tags that reference unknown archetype names."""
    return _fix_archetype_tags_in_file(spec_name, tasks_path, mode="invalid")


def fix_malformed_archetype_tag(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Normalize malformed archetype tags to [archetype: name] format."""
    return _fix_archetype_tags_in_file(spec_name, tasks_path, mode="malformed")


def fix_invalid_checkbox_state(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Normalize invalid checkbox characters to [ ] (not started).

    Scans task group and subtask lines for checkbox characters not in
    {' ', 'x', '-', '~'} and replaces them with a space.
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    results: list[FixResult] = []

    for i, line in enumerate(lines):
        m = _CHECKBOX_LINE.match(line)
        if m:
            char = m.group(2)
            if char not in _VALID_CHECKBOX_CHARS:
                # Replace the invalid checkbox character with a space
                start = m.start(2)
                end = m.end(2)
                lines[i] = line[:start] + " " + line[end:]
                results.append(
                    FixResult(
                        rule="invalid-checkbox-state",
                        spec_name=spec_name,
                        file=str(tasks_path),
                        description=(
                            f"Normalized invalid checkbox '[{char}]' to '[ ]' "
                            f"on line {i + 1}"
                        ),
                    )
                )

    if results:
        tasks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


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
            description=(
                f"Appended {len(missing_req_ids)} missing requirement(s) "
                f"to traceability table"
            ),
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
            description=(
                f"Appended {len(missing_req_ids)} missing requirement(s) "
                f"to coverage matrix"
            ),
        )
    ]


def apply_fixes(
    findings: list[Finding],
    discovered_specs: list[SpecInfo],
    specs_dir: Path,
    known_specs: dict[str, list[int]],
) -> list[FixResult]:
    """Apply all available auto-fixes for the given findings.

    Iterates through findings, identifies those with FIXABLE_RULES,
    groups them by spec and rule, and applies the appropriate fixer.

    Deduplicates by (spec_name, rule) to avoid applying the same fixer
    twice to the same file.

    Returns a list of all FixResults applied.

    Requirements: 20-REQ-6.2, 20-REQ-6.5, 20-REQ-6.E1, 20-REQ-6.E3,
                  20-REQ-6.E4
    """
    if not findings:
        return []

    # Filter to fixable findings and deduplicate by (spec_name, rule)
    fixable: dict[tuple[str, str], Finding] = {}
    # For rules that need ALL findings per spec (not just first), collect them
    stale_dep_findings: dict[str, list[Finding]] = {}
    mismatch_findings: dict[tuple[str, str], list[Finding]] = {}
    _MULTI_FINDING_RULES = {
        "stale-dependency",
        "traceability-table-mismatch",
        "coverage-matrix-mismatch",
    }
    for finding in findings:
        if finding.rule in FIXABLE_RULES:
            key = (finding.spec_name, finding.rule)
            if finding.rule == "stale-dependency":
                stale_dep_findings.setdefault(finding.spec_name, []).append(finding)
                if key not in fixable:
                    fixable[key] = finding
            elif finding.rule in _MULTI_FINDING_RULES:
                mismatch_findings.setdefault(key, []).append(finding)
                if key not in fixable:
                    fixable[key] = finding
            else:
                if key not in fixable:
                    fixable[key] = finding

    if not fixable:
        return []

    # Build spec lookup
    spec_by_name: dict[str, SpecInfo] = {s.name: s for s in discovered_specs}

    all_results: list[FixResult] = []

    # Dispatch table: rule -> (filename, fixer_fn) for fixers that take
    # (spec_name, file_path) and need only a file-existence guard.
    _fixer = tuple[str, Callable[..., list[FixResult]]]
    _FILE_FIXERS: dict[str, _fixer] = {
        "missing-verification": (
            "tasks.md",
            fix_missing_verification,
        ),
        "inconsistent-req-id-format": (
            "requirements.md",
            fix_inconsistent_req_id_format,
        ),
        "missing-definition-of-done": (
            "design.md",
            fix_missing_definition_of_done,
        ),
        "missing-error-table": (
            "design.md",
            fix_missing_error_table,
        ),
        "missing-correctness-properties": (
            "design.md",
            fix_missing_correctness_properties,
        ),
        "invalid-archetype-tag": (
            "tasks.md",
            fix_invalid_archetype_tag,
        ),
        "malformed-archetype-tag": (
            "tasks.md",
            fix_malformed_archetype_tag,
        ),
        "invalid-checkbox-state": (
            "tasks.md",
            fix_invalid_checkbox_state,
        ),
    }

    # Dispatch table: rule -> fixer_fn for fixers that take (spec_name, spec_path).
    _DIR_FIXERS: dict[str, Callable[..., list[FixResult]]] = {
        "missing-traceability-table": fix_missing_traceability_table,
        "missing-coverage-matrix": fix_missing_coverage_matrix,
    }

    for (spec_name, rule), _finding in fixable.items():
        spec = spec_by_name.get(spec_name)
        if spec is None:
            continue

        try:
            if rule in _FILE_FIXERS:
                filename, fixer_fn = _FILE_FIXERS[rule]
                path = spec.path / filename
                if path.is_file():
                    all_results.extend(fixer_fn(spec_name, path))

            elif rule in _DIR_FIXERS:
                all_results.extend(_DIR_FIXERS[rule](spec_name, spec.path))

            elif rule == "coarse-dependency":
                prd_path = spec.path / "prd.md"
                if prd_path.is_file():
                    current_groups = known_specs.get(spec_name, [])
                    all_results.extend(
                        fix_coarse_dependency(
                            spec_name, prd_path, known_specs, current_groups
                        )
                    )

            elif rule == "stale-dependency":
                prd_path = spec.path / "prd.md"
                if prd_path.is_file():
                    id_fixes = _parse_stale_dep_fixes(
                        stale_dep_findings.get(spec_name, [])
                    )
                    if id_fixes:
                        all_results.extend(
                            fix_stale_dependency(spec_name, prd_path, id_fixes)
                        )

            elif rule == "traceability-table-mismatch":
                key = (spec_name, rule)
                missing_ids = _extract_req_ids_from_findings(
                    mismatch_findings.get(key, [])
                )
                if missing_ids:
                    all_results.extend(
                        fix_traceability_table_mismatch(
                            spec_name, spec.path, missing_ids
                        )
                    )

            elif rule == "coverage-matrix-mismatch":
                key = (spec_name, rule)
                missing_ids = _extract_req_ids_from_findings(
                    mismatch_findings.get(key, [])
                )
                if missing_ids:
                    all_results.extend(
                        fix_coverage_matrix_mismatch(spec_name, spec.path, missing_ids)
                    )

        except OSError as exc:
            logger.warning(
                "Failed to apply fix for rule '%s' on spec '%s': %s",
                rule,
                spec_name,
                exc,
            )
            continue

    return all_results


_REQ_ID_IN_MESSAGE = re.compile(r"\b(\d{2}-REQ-\d+\.(?:\d+|E\d+))\b")


def _extract_req_ids_from_findings(findings: list[Finding]) -> list[str]:
    """Extract requirement IDs from mismatch finding messages."""
    ids: list[str] = []
    for finding in findings:
        m = _REQ_ID_IN_MESSAGE.search(finding.message)
        if m:
            ids.append(m.group(1))
    return sorted(set(ids))


def _parse_stale_dep_fixes(findings: list[Finding]) -> list[IdentifierFix]:
    """Extract IdentifierFix objects from stale-dependency finding messages.

    Parses the machine-readable message format:
    ``identifier \\`{id}\\` not found ... Suggestion: {suggestion}``

    Requirements: 21-REQ-5.3
    """
    fixes: list[IdentifierFix] = []
    for finding in findings:
        id_match = _IDENTIFIER_PATTERN.search(finding.message)
        sug_match = _SUGGESTION_PATTERN.search(finding.message)
        if id_match and sug_match:
            fixes.append(
                IdentifierFix(
                    original=id_match.group(1),
                    suggestion=sug_match.group(1),
                    upstream_spec=finding.message.split(":")[0].replace(
                        "Dependency on ", ""
                    ),
                )
            )
    return fixes


def fix_ai_criteria(
    spec_name: str,
    req_path: Path,
    rewrites: dict[str, str],
    findings_map: dict[str, str],
) -> list[FixResult]:
    """Apply AI-generated criterion rewrites to requirements.md.

    For each criterion_id in rewrites:
    1. Locate the line containing the criterion ID in the file.
    2. Replace the criterion text (everything after the ID prefix)
       with the rewrite text.
    3. Record a FixResult.

    Args:
        spec_name: Spec name for FixResult metadata.
        req_path: Path to requirements.md.
        rewrites: Mapping of criterion_id -> replacement_text.
        findings_map: Mapping of criterion_id -> rule name (e.g. vague-criterion).

    Returns:
        List of FixResult for each successfully applied rewrite.

    Requirements: 22-REQ-1.2, 22-REQ-1.3, 22-REQ-1.E2, 22-REQ-4.3
    """
    if not req_path.is_file() or not rewrites:
        return []

    text = req_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    results: list[FixResult] = []

    for criterion_id, replacement in rewrites.items():
        # Try to locate this criterion ID in the file
        found = False
        for i, line in enumerate(lines):
            # Check bracket format: [99-REQ-1.1]
            bracket_pattern = re.compile(
                rf"^(\s*\d+\.\s*)\[({re.escape(criterion_id)})\]\s*(.*)$"
            )
            bold_pattern = re.compile(
                rf"^(\s*\d+\.\s*)\*\*({re.escape(criterion_id)}):\*\*\s*(.*)$"
            )

            bracket_match = bracket_pattern.match(line)
            bold_match = bold_pattern.match(line)

            if bracket_match:
                prefix = bracket_match.group(1)
                cid = bracket_match.group(2)
                lines[i] = f"{prefix}[{cid}] {replacement}"
                found = True
                break
            elif bold_match:
                prefix = bold_match.group(1)
                cid = bold_match.group(2)
                lines[i] = f"{prefix}**{cid}:** {replacement}"
                found = True
                break

        if not found:
            logger.warning(
                "Criterion ID '%s' not found in %s, skipping rewrite",
                criterion_id,
                req_path,
            )
            continue

        rule = findings_map.get(criterion_id, "vague-criterion")
        results.append(
            FixResult(
                rule=rule,
                spec_name=spec_name,
                file=str(req_path),
                description=(f"Rewrote criterion {criterion_id}: {replacement[:60]}"),
            )
        )

    if results:
        req_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return results


def fix_ai_test_spec_entries(
    spec_name: str,
    ts_path: Path,
    entries: dict[str, str],
) -> list[FixResult]:
    """Insert AI-generated test spec entries into test_spec.md.

    Entries are inserted before the Coverage Matrix section if present,
    otherwise appended to the end of the file.

    Args:
        spec_name: Spec name for FixResult metadata.
        ts_path: Path to test_spec.md.
        entries: Mapping of requirement_id -> test spec entry markdown.

    Returns:
        List of FixResult for each successfully inserted entry.
    """
    if not ts_path.is_file() or not entries:
        return []

    text = ts_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the Coverage Matrix heading to insert before it
    insert_idx: int | None = None
    for i, line in enumerate(lines):
        m = _H2_HEADING.match(line)
        if m:
            normalized = _normalize_heading(m.group(1))
            if "coverage" in normalized and "matrix" in normalized:
                # Insert before the heading, with a blank line
                insert_idx = i
                break

    results: list[FixResult] = []
    new_lines: list[str] = []
    for req_id, entry_text in entries.items():
        new_lines.append("")
        new_lines.extend(entry_text.splitlines())
        new_lines.append("")
        results.append(
            FixResult(
                rule="untraced-requirement",
                spec_name=spec_name,
                file=str(ts_path),
                description=(f"Generated test spec entry for {req_id}"),
            )
        )

    if not results:
        return []

    if insert_idx is not None:
        # Insert before Coverage Matrix
        for j, new_line in enumerate(new_lines):
            lines.insert(insert_idx + j, new_line)
    else:
        # Append to end
        lines.extend(new_lines)

    ts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def parse_finding_criterion_id(finding: Finding) -> str | None:
    """Extract criterion ID from a Finding's message.

    The AI analysis format is: ``[criterion_id] explanation``.

    Requirements: 22-REQ-4.3
    """
    msg = finding.message
    if msg.startswith("["):
        end = msg.find("]")
        if end > 0:
            return msg[1:end]
    return None
