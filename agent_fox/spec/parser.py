"""Task definition parser: parse tasks.md and prd.md dependency tables.

Requirements: 02-REQ-2.1, 02-REQ-2.2, 02-REQ-2.3, 02-REQ-2.4,
              02-REQ-2.E1, 02-REQ-2.E2
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Top-level group pattern:
#   - [ ] 1. Title          (required)
#   - [x] 2. Title          (completed)
#   - [-] 3. Title          (in-progress)
#   - [ ] * 4. Title        (optional)
_GROUP_PATTERN = re.compile(r"^- \[([ x\-])\] (\* )?(\d+)\. (.+)$")

# Subtask pattern (indented):
#   - [ ] 1.1 Subtask title
#   - [x] 2.3 Subtask title
_SUBTASK_PATTERN = re.compile(r"^\s+- \[([ x\-])\] (\d+\.(?:\d+|V)) (.+)$")

# Cross-spec dependency table header detection — standard format:
#   | This Spec | Depends On | What It Uses |
_DEP_TABLE_HEADER = re.compile(r"\|\s*This Spec\s*\|\s*Depends On\s*\|", re.IGNORECASE)

# Alternative dependency table format with group-level granularity:
#   | Spec | From Group | To Group | Relationship |
_DEP_TABLE_HEADER_ALT = re.compile(
    r"\|\s*Spec\s*\|\s*From Group\s*\|\s*To Group\s*\|", re.IGNORECASE
)

# Table separator row (e.g., |---|---|---|)
_TABLE_SEP = re.compile(r"^\s*\|[\s\-|]+\|\s*$")

# Archetype tag pattern: [archetype: X]
_ARCHETYPE_TAG = re.compile(r"\[archetype:\s*(\w+)\]")

# Known archetype names for validation
_KNOWN_ARCHETYPES = {
    "coder", "skeptic", "verifier",
    "librarian", "cartographer", "coordinator",
}


@dataclass(frozen=True)
class SubtaskDef:
    """A single nested subtask within a task group."""

    id: str  # e.g., "1.2"
    title: str  # subtask description text
    completed: bool  # checkbox state


@dataclass(frozen=True)
class TaskGroupDef:
    """A parsed top-level task group from tasks.md."""

    number: int  # group number (1, 2, 3, ...)
    title: str  # group title text
    optional: bool  # True if marked with *
    completed: bool  # True if checkbox is [x]
    subtasks: tuple[SubtaskDef, ...]  # nested subtasks
    body: str  # full raw text of the group
    archetype: str | None = None  # 26-REQ-5.1: from [archetype: X] tag


@dataclass(frozen=True)
class CrossSpecDep:
    """A cross-spec dependency declaration from a prd.md table."""

    from_spec: str  # source spec name (the spec declaring the dependency)
    from_group: int  # source group number (0 = first group, resolved by builder)
    to_spec: str  # target spec name (the spec being depended on)
    to_group: int  # target group number (0 = last group, resolved by builder)


def parse_tasks(tasks_path: Path) -> list[TaskGroupDef]:
    """Parse a tasks.md file into a list of task group definitions.

    Scans the file for top-level task group entries (checkbox markdown lines
    starting with ``- [ ] N.``) and extracts subtasks, optional markers,
    titles, and body text.

    Args:
        tasks_path: Path to the tasks.md file.

    Returns:
        List of TaskGroupDef in document order.
    """
    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    groups: list[TaskGroupDef] = []

    # State for current group being parsed
    current_number: int | None = None
    current_title: str = ""
    current_optional: bool = False
    current_completed: bool = False
    current_subtasks: list[SubtaskDef] = []
    current_body_lines: list[str] = []
    current_archetype: str | None = None

    def _finalize_group() -> None:
        """Finalize and append the current group being parsed."""
        if current_number is not None:
            body = "\n".join(current_body_lines).strip()
            groups.append(
                TaskGroupDef(
                    number=current_number,
                    title=current_title,
                    optional=current_optional,
                    completed=current_completed,
                    subtasks=tuple(current_subtasks),
                    body=body,
                    archetype=current_archetype,
                )
            )

    for line in lines:
        group_match = _GROUP_PATTERN.match(line)
        if group_match:
            # Finalize previous group before starting a new one
            _finalize_group()

            checkbox = group_match.group(1)
            optional_marker = group_match.group(2)
            number_str = group_match.group(3)
            title = group_match.group(4)

            current_number = int(number_str)
            raw_title = title.strip()
            current_optional = optional_marker is not None
            current_completed = checkbox == "x"
            current_subtasks = []
            current_body_lines = []

            # 26-REQ-5.1: extract [archetype: X] tag from title
            arch_match = _ARCHETYPE_TAG.search(raw_title)
            if arch_match:
                arch_name = arch_match.group(1)
                if arch_name not in _KNOWN_ARCHETYPES:
                    # 26-REQ-5.E2: unknown archetype tag
                    logger.warning(
                        "Unknown archetype '%s' in tasks.md tag; "
                        "will default to 'coder'",
                        arch_name,
                    )
                current_archetype = arch_name
                # Strip the tag from the title
                current_title = _ARCHETYPE_TAG.sub("", raw_title).strip()
            else:
                current_archetype = None
                current_title = raw_title
            continue

        # Only process subtasks and body if we're inside a group
        if current_number is not None:
            subtask_match = _SUBTASK_PATTERN.match(line)
            if subtask_match:
                st_checkbox = subtask_match.group(1)
                st_id = subtask_match.group(2)
                st_title = subtask_match.group(3).strip()
                current_subtasks.append(
                    SubtaskDef(
                        id=st_id,
                        title=st_title,
                        completed=st_checkbox == "x",
                    )
                )
                current_body_lines.append(line)
            elif line.strip():
                # Non-empty, non-subtask line within a group's body
                current_body_lines.append(line)

    # Finalize the last group
    _finalize_group()

    # 02-REQ-2.E1: warn if no groups found
    if not groups:
        logger.warning(
            "No task groups found in '%s'",
            tasks_path,
        )

    return groups


def _parse_table_rows(lines: list[str], start: int) -> list[list[str]]:
    """Parse markdown table data rows starting after the header line.

    Skips separator rows and stops at the first non-table line.
    Returns a list of cell lists (one per data row).
    """
    rows: list[list[str]] = []
    for line in lines[start:]:
        if _TABLE_SEP.match(line):
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)
    return rows


def _safe_int(value: str, default: int = 0) -> int:
    """Parse an integer from a string, returning *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_cross_deps(
    prd_path: Path,
    spec_name: str | None = None,
) -> list[CrossSpecDep]:
    """Parse cross-spec dependency tables from a spec's prd.md.

    Recognises two table formats:

    **Standard format** (``| This Spec | Depends On |``):
    Yields spec-level dependencies with sentinel group numbers (0/0),
    resolved by the builder to the first/last groups.

    **Alternative format** (``| Spec | From Group | To Group |``):
    Yields group-level dependencies. Requires *spec_name* so the
    parser knows which spec is declaring the dependency. The columns
    map as follows:

    - *Spec* — the dependency spec (``to_spec``)
    - *From Group* — the group in the dependency spec (``to_group``)
    - *To Group* — the group in this spec (``from_group``)

    Args:
        prd_path: Path to the spec's prd.md file.
        spec_name: Name of the spec whose prd.md is being parsed.
            Required for the alternative table format.

    Returns:
        List of CrossSpecDep declarations. Empty if no table found.
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    deps: list[CrossSpecDep] = []

    for i, line in enumerate(lines):
        # --- Standard format: | This Spec | Depends On | ... ---
        if _DEP_TABLE_HEADER.search(line):
            for cells in _parse_table_rows(lines, i + 1):
                if len(cells) < 2:
                    continue
                from_spec = cells[0].strip()
                to_spec = cells[1].strip()
                if not from_spec or not to_spec:
                    continue
                deps.append(
                    CrossSpecDep(
                        from_spec=from_spec,
                        from_group=0,  # sentinel: resolve to first group
                        to_spec=to_spec,
                        to_group=0,  # sentinel: resolve to last group
                    )
                )

        # --- Alternative format: | Spec | From Group | To Group | ... ---
        elif _DEP_TABLE_HEADER_ALT.search(line):
            if spec_name is None:
                logger.warning(
                    "Alternative dependency table found in '%s' but "
                    "spec_name not provided; skipping.",
                    prd_path,
                )
                continue
            for cells in _parse_table_rows(lines, i + 1):
                if len(cells) < 3:
                    continue
                dep_spec = cells[0].strip()
                dep_group = _safe_int(cells[1].strip())
                this_group = _safe_int(cells[2].strip())
                if not dep_spec:
                    continue
                deps.append(
                    CrossSpecDep(
                        from_spec=spec_name,
                        from_group=this_group,
                        to_spec=dep_spec,
                        to_group=dep_group,
                    )
                )

    return deps
