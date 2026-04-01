"""Dependency validation rules (broken, coarse, circular)."""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import (
    _DEP_TABLE_HEADER,
    _DEP_TABLE_HEADER_ALT,
    _parse_table_rows,
    _safe_int,
)
from agent_fox.spec.validators._helpers import (
    _GROUP_REF,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from agent_fox.spec.validators.finding import Finding


def check_broken_dependencies(
    spec_name: str,
    spec_path: Path,
    known_specs: dict[str, list[int]],
    current_spec_groups: list[int] | None = None,
) -> list[Finding]:
    """Check for dependency references to non-existent specs or task groups.

    Rule: broken-dependency
    Severity: error
    Parses dependency tables from prd.md (both standard and alternative
    formats) and validates each reference against the known_specs dict
    (mapping spec name to list of group numbers).

    Args:
        spec_name: Name of the spec being validated.
        spec_path: Path to the spec folder.
        known_specs: Mapping of spec name to list of group numbers.
        current_spec_groups: Group numbers in the current spec (for
            validating To Group in alt format). If None, uses
            known_specs[spec_name] if available.
    """
    prd_path = spec_path / "prd.md"
    if not prd_path.is_file():
        return []

    if current_spec_groups is None:
        current_spec_groups = known_specs.get(spec_name, [])

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    findings: list[Finding] = []

    for i, line in enumerate(lines):
        # --- Standard format: | This Spec | Depends On | ... ---
        if _DEP_TABLE_HEADER.search(line):
            for cells in _parse_table_rows(lines, i + 1):
                if len(cells) < 2:
                    continue

                to_spec = cells[1].strip()
                description = cells[2].strip() if len(cells) >= 3 else ""

                if to_spec not in known_specs:
                    findings.append(
                        Finding(
                            spec_name=spec_name,
                            file="prd.md",
                            rule="broken-dependency",
                            severity=SEVERITY_ERROR,
                            message=(
                                f"Dependency references non-existent spec '{to_spec}'"
                            ),
                            line=None,
                        )
                    )
                else:
                    group_matches = _GROUP_REF.findall(description)
                    for group_num_str in group_matches:
                        group_num = int(group_num_str)
                        if group_num not in known_specs[to_spec]:
                            findings.append(
                                Finding(
                                    spec_name=spec_name,
                                    file="prd.md",
                                    rule="broken-dependency",
                                    severity=SEVERITY_ERROR,
                                    message=(
                                        f"Dependency references non-existent "
                                        f"task group {group_num} in spec "
                                        f"'{to_spec}'"
                                    ),
                                    line=None,
                                )
                            )

        # --- Alternative format: | Spec | From Group | To Group | ... ---
        elif _DEP_TABLE_HEADER_ALT.search(line):
            for cells in _parse_table_rows(lines, i + 1):
                if len(cells) < 3:
                    continue

                dep_spec = cells[0].strip()
                from_group = _safe_int(cells[1].strip())
                to_group = _safe_int(cells[2].strip())

                if not dep_spec:
                    continue

                # Check spec exists
                if dep_spec not in known_specs:
                    findings.append(
                        Finding(
                            spec_name=spec_name,
                            file="prd.md",
                            rule="broken-dependency",
                            severity=SEVERITY_ERROR,
                            message=(
                                f"Dependency references non-existent spec '{dep_spec}'"
                            ),
                            line=None,
                        )
                    )
                else:
                    # Check from-group exists in dependency spec
                    if from_group and from_group not in known_specs[dep_spec]:
                        findings.append(
                            Finding(
                                spec_name=spec_name,
                                file="prd.md",
                                rule="broken-dependency",
                                severity=SEVERITY_ERROR,
                                message=(
                                    f"Dependency references non-existent "
                                    f"task group {from_group} in spec "
                                    f"'{dep_spec}'"
                                ),
                                line=None,
                            )
                        )

                # Check to-group exists in current spec
                if to_group and to_group not in current_spec_groups:
                    findings.append(
                        Finding(
                            spec_name=spec_name,
                            file="prd.md",
                            rule="broken-dependency",
                            severity=SEVERITY_ERROR,
                            message=(
                                f"Dependency references non-existent "
                                f"task group {to_group} in current spec"
                            ),
                            line=None,
                        )
                    )

    return findings


def _check_coarse_dependency(
    spec_name: str,
    prd_path: Path,
) -> list[Finding]:
    """Detect specs using the standard (coarse) dependency table format.

    Rule: coarse-dependency
    Severity: warning

    Scans prd.md for the standard header pattern
    ``| This Spec | Depends On |``. If found, produces a Warning
    recommending the group-level format.

    Requirements: 20-REQ-3.1, 20-REQ-3.2, 20-REQ-3.3
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")

    if _DEP_TABLE_HEADER.search(text):
        return [
            Finding(
                spec_name=spec_name,
                file="prd.md",
                rule="coarse-dependency",
                severity=SEVERITY_WARNING,
                message=(
                    "Dependency table uses the standard format "
                    "(| This Spec | Depends On |), which resolves to "
                    "last-group-to-first-group and may serialize work that "
                    "could run in parallel. Consider using the group-level "
                    "format (| Spec | From Group | To Group | Relationship |) "
                    "for finer-grained parallelism."
                ),
                line=None,
            )
        ]

    return []


def _check_circular_dependency(
    specs: list[SpecInfo],
) -> list[Finding]:
    """Detect dependency cycles across all specs.

    Rule: circular-dependency
    Severity: error

    1. Parse each spec's prd.md dependency table (both standard and alt
       formats) to extract spec-level edges.
    2. Build a directed graph of spec-level dependencies.
    3. Run cycle detection using DFS with coloring.
    4. For each cycle found, produce an Error finding.

    Skips edges referencing specs not in the discovered set
    (the broken-dependency rule handles those).

    Requirements: 20-REQ-4.1, 20-REQ-4.2, 20-REQ-4.3
    """
    known_names = {s.name for s in specs}

    # Build adjacency list: spec_name -> set of dependency spec names
    graph: dict[str, set[str]] = {s.name: set() for s in specs}

    for spec in specs:
        prd_path = spec.path / "prd.md"
        if not prd_path.is_file():
            continue

        text = prd_path.read_text(encoding="utf-8")
        lines = text.splitlines()

        for i, line in enumerate(lines):
            # Standard format: | This Spec | Depends On | ...
            if _DEP_TABLE_HEADER.search(line):
                for cells in _parse_table_rows(lines, i + 1):
                    if len(cells) >= 2:
                        dep_spec = cells[1].strip()
                        if dep_spec in known_names:
                            graph[spec.name].add(dep_spec)

            # Alt format: | Spec | From Group | To Group | ...
            elif _DEP_TABLE_HEADER_ALT.search(line):
                for cells in _parse_table_rows(lines, i + 1):
                    if len(cells) >= 1:
                        dep_spec = cells[0].strip()
                        if dep_spec in known_names:
                            graph[spec.name].add(dep_spec)

    # DFS cycle detection with coloring
    # WHITE=0 (unvisited), GRAY=1 (in progress), BLACK=2 (finished)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {name: WHITE for name in graph}
    parent: dict[str, str | None] = {name: None for name in graph}
    cycles: list[list[str]] = []

    def _dfs(node: str) -> None:
        color[node] = GRAY
        for neighbor in sorted(graph[node]):  # sorted for determinism
            if color[neighbor] == GRAY:
                # Found a cycle -- trace it back
                cycle = [neighbor, node]
                current = node
                while parent[current] is not None and parent[current] != neighbor:
                    current = parent[current]  # type: ignore[assignment]
                    cycle.append(current)
                cycle.reverse()
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                parent[neighbor] = node
                _dfs(neighbor)
        color[node] = BLACK

    for name in sorted(graph):
        if color[name] == WHITE:
            _dfs(name)

    # Produce findings
    findings: list[Finding] = []
    seen_cycle_sets: list[frozenset[str]] = []
    for cycle in cycles:
        cycle_set = frozenset(cycle)
        # Deduplicate: don't report the same set of specs twice
        if cycle_set in seen_cycle_sets:
            continue
        seen_cycle_sets.append(cycle_set)
        cycle_str = " -> ".join(cycle)
        findings.append(
            Finding(
                spec_name=cycle[0],
                file="prd.md",
                rule="circular-dependency",
                severity=SEVERITY_ERROR,
                message=f"Circular dependency detected: {cycle_str}",
                line=None,
            )
        )

    return findings
