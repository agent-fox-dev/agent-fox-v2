"""AI-powered fixers: criterion rewrites and test spec entry generation.

Requirements: 22-REQ-1.*, 22-REQ-4.*
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agent_fox.spec._patterns import (
    H2_HEADING as _H2_HEADING,
)
from agent_fox.spec._patterns import (
    normalize_heading as _normalize_heading,
)

from .types import FixResult

logger = logging.getLogger(__name__)


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
            bracket_pattern = re.compile(rf"^(\s*\d+\.\s*)\[({re.escape(criterion_id)})\]\s*(.*)$")
            bold_pattern = re.compile(rf"^(\s*\d+\.\s*)\*\*({re.escape(criterion_id)}):\*\*\s*(.*)$")

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
