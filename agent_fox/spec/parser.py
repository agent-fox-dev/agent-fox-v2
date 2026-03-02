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
_SUBTASK_PATTERN = re.compile(r"^\s+- \[([ x\-])\] (\d+\.\d+) (.+)$")

# Cross-spec dependency table header detection
_DEP_TABLE_HEADER = re.compile(r"\|\s*This Spec\s*\|\s*Depends On\s*\|", re.IGNORECASE)

# Table separator row (e.g., |---|---|---|)
_TABLE_SEP = re.compile(r"^\s*\|[\s\-|]+\|\s*$")


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
            current_title = title.strip()
            current_optional = optional_marker is not None
            current_completed = checkbox == "x"
            current_subtasks = []
            current_body_lines = []
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


def parse_cross_deps(prd_path: Path) -> list[CrossSpecDep]:
    """Parse cross-spec dependency table from a spec's prd.md.

    Looks for a markdown table with columns matching
    ``| This Spec | Depends On |``. Each data row yields a CrossSpecDep
    with spec-level dependency (from_group=0 and to_group=0 as sentinels,
    to be resolved by the builder to first/last group numbers).

    Args:
        prd_path: Path to the spec's prd.md file.

    Returns:
        List of CrossSpecDep declarations. Empty if no table found.
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    deps: list[CrossSpecDep] = []
    in_table = False
    header_found = False

    for line in lines:
        # Look for the dependency table header
        if not header_found:
            if _DEP_TABLE_HEADER.search(line):
                header_found = True
                in_table = True
            continue

        # Skip separator row
        if in_table and _TABLE_SEP.match(line):
            continue

        # Parse data rows
        if in_table:
            # Stop at end of table (non-table line)
            stripped = line.strip()
            if not stripped.startswith("|"):
                break

            # Split cells by pipe
            cells = [c.strip() for c in stripped.split("|")]
            # Filter out empty strings from leading/trailing pipes
            cells = [c for c in cells if c]

            if len(cells) >= 2:
                from_spec = cells[0].strip()
                to_spec = cells[1].strip()
                if from_spec and to_spec:
                    deps.append(
                        CrossSpecDep(
                            from_spec=from_spec,
                            from_group=0,  # sentinel: resolve to first group
                            to_spec=to_spec,
                            to_group=0,  # sentinel: resolve to last group
                        )
                    )

    return deps
