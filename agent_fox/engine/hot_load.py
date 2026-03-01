"""Hot-loader: discover and incorporate new specs at sync barriers.

At sync barriers, scans .specs/ for new specification folders not present
in the current task graph, parses them, and incorporates them into the
graph without restart.

Requirements: 06-REQ-6.3, 06-REQ-7.1, 06-REQ-7.2, 06-REQ-7.3,
              06-REQ-7.E1, 06-REQ-7.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.graph.types import TaskGraph
from agent_fox.spec.discovery import SpecInfo  # noqa: F401

logger = logging.getLogger("agent_fox.engine.hot_load")


def discover_new_specs(
    specs_dir: Path,
    known_specs: set[str],
) -> list[SpecInfo]:
    """Find spec folders in .specs/ not already in the task graph.

    Args:
        specs_dir: Path to the .specs/ directory.
        known_specs: Set of spec names already in the current plan.

    Returns:
        List of newly discovered SpecInfo records, sorted by prefix.
    """
    raise NotImplementedError


def hot_load_specs(
    graph: TaskGraph,
    specs_dir: Path,
) -> tuple[TaskGraph, list[str]]:
    """Incorporate newly discovered specs into the task graph.

    1. Discover new spec folders not in graph.nodes.
    2. Parse tasks.md for each new spec.
    3. Parse cross-spec dependencies from each new spec's prd.md.
    4. Create nodes and edges for the new specs.
    5. Re-compute topological ordering.
    6. Return updated graph and list of new spec names.

    Args:
        graph: The current task graph.
        specs_dir: Path to the .specs/ directory.

    Returns:
        Tuple of (updated TaskGraph, list of newly added spec names).
        If no new specs are found, returns the original graph unchanged
        and an empty list.
    """
    raise NotImplementedError
