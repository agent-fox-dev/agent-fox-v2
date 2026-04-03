"""Standard fixers: stale-dependency, coarse-dependency, missing-verification,
inconsistent-req-id-format, and related helpers.

Requirements: 20-REQ-6.*, 21-REQ-5.*
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.spec.parser import (
    _DEP_TABLE_HEADER,
    _GROUP_PATTERN,
    _SUBTASK_PATTERN,
    _TABLE_SEP,
)
from agent_fox.spec.validator import Finding

from .types import (
    _IDENTIFIER_PATTERN,
    _SUGGESTION_PATTERN,
    FixResult,
    IdentifierFix,
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
        new_lines.append(f"| {depends_on} | {from_group} | {to_group} | {description} |")

    # Replace the table in the original text
    result_lines = lines[:table_start] + new_lines + lines[table_end:]
    prd_path.write_text("\n".join(result_lines) + "\n", encoding="utf-8")

    return [
        FixResult(
            rule="coarse-dependency",
            spec_name=spec_name,
            file=str(prd_path),
            description=(f"Rewrote standard-format dependency table to group-level format ({len(parsed_rows)} row(s))"),
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
    groups_to_fix = [g for g in groups if not g["has_verify"] and not g["title"].startswith("Checkpoint")]
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
            description=(f"Converted {count} bold-format requirement ID(s) to bracket format"),
        )
    ]


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
                    upstream_spec=finding.message.split(":")[0].replace("Dependency on ", ""),
                )
            )
    return fixes


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
