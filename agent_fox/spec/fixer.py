"""Spec fixer: auto-fix functions for mechanically fixable lint findings.

Each fixer reads a file, applies a transformation, and writes back.
The module is separate from the validator to maintain single-responsibility:
validator detects, fixer corrects.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import (
    _DEP_TABLE_HEADER,
    _GROUP_PATTERN,
    _SUBTASK_PATTERN,
    _TABLE_SEP,
)
from agent_fox.spec.validator import Finding

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FixResult:
    """Result of applying a single fix."""

    rule: str
    spec_name: str
    file: str
    description: str


# Set of rules that have auto-fixers
FIXABLE_RULES = {"coarse-dependency", "missing-verification"}


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
            current_group = {
                "number": int(group_match.group(3)),
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
                if re.match(
                    rf"^{current_group['number']}\.V$", st_id
                ):
                    current_group["has_verify"] = True

    if current_group is not None:
        groups.append(current_group)

    # Find groups that need verification steps
    groups_to_fix = [g for g in groups if not g["has_verify"]]
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
                description=(
                    f"Appended verification step {num}.V to task group {num}"
                ),
            )
        )

    # Reverse results so they're in group order (we built them reversed)
    results.reverse()

    tasks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


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
    for finding in findings:
        if finding.rule in FIXABLE_RULES:
            key = (finding.spec_name, finding.rule)
            if key not in fixable:
                fixable[key] = finding

    if not fixable:
        return []

    # Build spec lookup
    spec_by_name: dict[str, SpecInfo] = {s.name: s for s in discovered_specs}

    all_results: list[FixResult] = []

    for (spec_name, rule), _finding in fixable.items():
        spec = spec_by_name.get(spec_name)
        if spec is None:
            continue

        try:
            if rule == "coarse-dependency":
                prd_path = spec.path / "prd.md"
                if prd_path.is_file():
                    current_groups = known_specs.get(spec_name, [])
                    results = fix_coarse_dependency(
                        spec_name, prd_path, known_specs, current_groups
                    )
                    all_results.extend(results)

            elif rule == "missing-verification":
                tasks_path = spec.path / "tasks.md"
                if tasks_path.is_file():
                    results = fix_missing_verification(spec_name, tasks_path)
                    all_results.extend(results)

        except OSError as exc:
            logger.warning(
                "Failed to apply fix for rule '%s' on spec '%s': %s",
                rule,
                spec_name,
                exc,
            )
            continue

    return all_results
