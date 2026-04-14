"""Specification discovery: scan .specs/ for valid spec folders.

Requirements: 02-REQ-1.1, 02-REQ-1.2, 02-REQ-1.3, 02-REQ-1.E1, 02-REQ-1.E2
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from agent_fox.core.errors import PlanError

logger = logging.getLogger(__name__)

# Pattern: numeric prefix (2+ digits), underscore, descriptive name
_SPEC_DIR_PATTERN = re.compile(r"^(\d+)_(.+)$")


@dataclass(frozen=True)
class SpecInfo:
    """Metadata about a discovered specification folder."""

    name: str  # e.g., "01_core_foundation"
    prefix: int  # e.g., 1
    path: Path  # e.g., Path(".specs/01_core_foundation")
    has_tasks: bool  # whether tasks.md exists
    has_prd: bool  # whether prd.md exists


def discover_specs(
    specs_dir: Path,
    filter_spec: str | None = None,
) -> list[SpecInfo]:
    """Discover spec folders in the given directory.

    Args:
        specs_dir: Path to the .specs/ directory.
        filter_spec: If set, return only this spec (by name or prefix).

    Returns:
        List of SpecInfo sorted by numeric prefix.

    Raises:
        PlanError: If no specs found or filter matches nothing.
    """
    # 02-REQ-1.E1: missing or empty .specs/ directory
    if not specs_dir.is_dir():
        raise PlanError(f"No specifications found: '{specs_dir}' does not exist")

    # Scan for subdirectories matching NN_name pattern
    specs: list[SpecInfo] = []
    for entry in sorted(specs_dir.iterdir()):
        if not entry.is_dir():
            continue
        match = _SPEC_DIR_PATTERN.match(entry.name)
        if not match:
            continue

        prefix = int(match.group(1))
        has_tasks = (entry / "tasks.md").is_file()
        has_prd = (entry / "prd.md").is_file()

        # 02-REQ-1.3: log warning when tasks.md is missing
        if not has_tasks:
            logger.warning(
                "Spec folder '%s' has no tasks.md, skipping for planning",
                entry.name,
            )

        specs.append(
            SpecInfo(
                name=entry.name,
                prefix=prefix,
                path=entry,
                has_tasks=has_tasks,
                has_prd=has_prd,
            )
        )

    # 02-REQ-1.E1: no specs found at all
    if not specs:
        raise PlanError(f"No specifications found in '{specs_dir}'")

    # 02-REQ-1.1: sort by numeric prefix
    specs.sort(key=lambda s: s.prefix)

    # 02-REQ-1.2: filter to a single spec if requested
    if filter_spec is not None:
        filtered = [s for s in specs if s.name == filter_spec]
        if not filtered:
            # 02-REQ-1.E2: filter matches nothing
            available = ", ".join(s.name for s in specs)
            raise PlanError(f"Spec '{filter_spec}' not found. Available specs: {available}")
        return filtered

    return specs
