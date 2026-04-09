"""Analyze specification graph deliverable lists to find scope overlaps.

Requirements: 87-REQ-3.1 through 87-REQ-3.4, 87-REQ-3.E1 through 87-REQ-3.E3
"""

from __future__ import annotations

import logging
from collections import defaultdict

from agent_fox.scope_guard.models import (
    OverlapRecord,
    OverlapResult,
    OverlapSeverity,
    SpecGraph,
    TaskGroup,
)

logger = logging.getLogger(__name__)


def detect_overlaps(spec_graph: SpecGraph) -> OverlapResult:
    """Detect scope overlaps across task groups in a specification graph.

    Compares deliverable lists across all task groups and identifies any
    function that appears in more than one task group's deliverables.
    Overlap between task groups with a dependency is a WARNING; without
    dependency it is an ERROR.
    """
    task_groups = spec_graph.task_groups

    # Edge case: 0 or 1 task groups → no overlap possible (87-REQ-3.E3)
    if len(task_groups) <= 1:
        return OverlapResult(overlaps=[], has_errors=False, has_warnings=False)

    # Filter out task groups with empty deliverable lists (87-REQ-3.E1)
    active_groups: list[TaskGroup] = []
    for tg in task_groups:
        if not tg.deliverables:
            logger.warning(
                "Task group %d has no enumerated deliverables; "
                "excluded from overlap analysis",
                tg.number,
            )
        else:
            active_groups.append(tg)

    if len(active_groups) <= 1:
        return OverlapResult(overlaps=[], has_errors=False, has_warnings=False)

    # Build index: (file_path, function_id) → list of task group numbers
    deliverable_index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for tg in active_groups:
        for d in tg.deliverables:
            key = (d.file_path, d.function_id)
            deliverable_index[key].append(tg.number)

    # Find overlaps: entries with more than one task group
    raw_overlaps: list[tuple[str, str, list[int]]] = []
    for (file_path, function_id), tg_numbers in deliverable_index.items():
        if len(tg_numbers) > 1:
            raw_overlaps.append((file_path, function_id, tg_numbers))

    if not raw_overlaps:
        return OverlapResult(overlaps=[], has_errors=False, has_warnings=False)

    # Classify severity based on dependency relationships
    overlaps = _classify_overlaps(raw_overlaps, spec_graph)
    has_errors = any(o.severity == OverlapSeverity.ERROR for o in overlaps)
    has_warnings = any(o.severity == OverlapSeverity.WARNING for o in overlaps)

    return OverlapResult(
        overlaps=overlaps,
        has_errors=has_errors,
        has_warnings=has_warnings,
    )


def _classify_overlaps(
    raw_overlaps: list[tuple[str, str, list[int]]],
    spec_graph: SpecGraph,
) -> list[OverlapRecord]:
    """Classify each overlap as WARNING (dependency exists) or ERROR (no dependency).

    87-REQ-3.3: ERROR if no dependency relationship between overlapping groups.
    87-REQ-3.4: WARNING if dependency relationship exists.
    """
    # Build dependency lookup: tg_number → set of depends_on
    deps: dict[int, set[int]] = {}
    for tg in spec_graph.task_groups:
        deps[tg.number] = set(tg.depends_on)

    records: list[OverlapRecord] = []
    for file_path, function_id, tg_numbers in raw_overlaps:
        severity = _determine_severity(tg_numbers, deps)
        deliverable_id = f"{file_path}::{function_id}"
        records.append(
            OverlapRecord(
                deliverable_id=deliverable_id,
                task_group_numbers=sorted(tg_numbers),
                severity=severity,
            )
        )
    return records


def _determine_severity(
    tg_numbers: list[int], deps: dict[int, set[int]]
) -> OverlapSeverity:
    """Determine overlap severity for a set of task group numbers.

    If ANY pair of overlapping task groups has a dependency relationship
    (either A depends on B or B depends on A), classify as WARNING.
    If NO pairs have a dependency relationship, classify as ERROR.
    """
    for i, a in enumerate(tg_numbers):
        for b in tg_numbers[i + 1 :]:
            a_deps = deps.get(a, set())
            b_deps = deps.get(b, set())
            if b in a_deps or a in b_deps:
                return OverlapSeverity.WARNING
    return OverlapSeverity.ERROR
