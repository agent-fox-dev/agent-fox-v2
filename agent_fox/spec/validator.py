"""Static validation rules for specification files.

Requirements: 09-REQ-2.1, 09-REQ-2.2, 09-REQ-3.1, 09-REQ-3.2,
              09-REQ-4.1, 09-REQ-4.2, 09-REQ-5.1, 09-REQ-5.2,
              09-REQ-6.1, 09-REQ-6.2, 09-REQ-6.3, 09-REQ-7.1, 09-REQ-7.2,
              09-REQ-1.2, 09-REQ-1.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agent_fox.spec.discovery import SpecInfo  # noqa: F401
from agent_fox.spec.parser import (
    _ARCHETYPE_TAG,
    _DEP_TABLE_HEADER,
    _DEP_TABLE_HEADER_ALT,
    _KNOWN_ARCHETYPES,
    TaskGroupDef,  # noqa: F401
    _parse_table_rows,
    _safe_int,
    parse_tasks,  # noqa: F401
)

# -- Severity constants -------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_HINT = "hint"

# Sorting order: error < warning < hint
SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_HINT: 2}

# -- Constants -----------------------------------------------------------------

EXPECTED_FILES = ["prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"]
MAX_SUBTASKS_PER_GROUP = 6

# Regex patterns for parsing
_REQUIREMENT_HEADING = re.compile(r"^###\s+Requirement\s+(\d+):\s*(.+)$")
_REQUIREMENT_ID = re.compile(r"(?:\[|\*\*)(\d{2}-REQ-\d+\.\d+)(?:\]|[:\*])")
_GROUP_REF = re.compile(r"\bgroup\s+(\d+)\b", re.IGNORECASE)

# EARS keyword detection — all EARS patterns include SHALL
_EARS_KEYWORD = re.compile(r"\bSHALL\b")

# Requirement ID format variants (for inconsistency detection)
_REQ_ID_BRACKET = re.compile(r"\[(\d{2}-REQ-\d+\.(?:\d+|E\d+))\]")
_REQ_ID_BOLD = re.compile(r"\*\*(\d{2}-REQ-\d+\.(?:\d+|E\d+))[:\*]")

# Design document section patterns
_PROPERTY_HEADING = re.compile(r"^###\s+Property\s+\d+", re.IGNORECASE)

# Test spec entry headings: ### TS-NN-N, ### TS-NN-PN, ### TS-NN-EN
_TS_ENTRY_HEADING = re.compile(r"^###\s+(TS-\d{2}-(?:P|E)?\d+)")
_TS_REFERENCE = re.compile(r"TS-\d{2}-(?:P|E)?\d+")

# Markdown table row detection
_TABLE_PIPE_ROW = re.compile(r"^\s*\|.+\|")
_TABLE_SEP_ROW = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")

# Section heading (## level)
_H2_HEADING = re.compile(r"^##\s+(.+)$")

# -- Section schema definitions (Phase 4) -------------------------------------
# Maps file -> list of (section_name, required). "required" means warning if
# missing; non-required means hint.

_SECTION_SCHEMAS: dict[str, list[tuple[str, bool]]] = {
    "requirements.md": [
        ("Introduction", False),
        ("Glossary", False),
        ("Requirements", True),
    ],
    "design.md": [
        ("Overview", True),
        ("Architecture", True),
        ("Components and Interfaces", False),
        ("Data Models", False),
        ("Operational Readiness", False),
        ("Correctness Properties", True),
        ("Error Handling", True),
        ("Technology Stack", False),
        ("Definition of Done", True),
        ("Testing Strategy", False),
    ],
    "test_spec.md": [
        ("Overview", False),
        ("Test Cases", True),
        ("Edge Case Tests", False),
        ("Property Test Cases", False),
        ("Coverage Matrix", True),
    ],
    "tasks.md": [
        ("Overview", False),
        ("Test Commands", False),
        ("Tasks", True),
        ("Traceability", False),
        ("Notes", False),
    ],
}


def _normalize_heading(text: str) -> str:
    """Normalize a heading for fuzzy comparison."""
    return re.sub(r"[\s_\-]+", " ", text.strip().lower())


def _spec_prefix(spec_name: str) -> str | None:
    """Extract the two-digit numeric prefix from a spec name (e.g. '28').

    Returns None if the name doesn't start with a two-digit prefix,
    which disables prefix-based filtering.
    """
    m = re.match(r"(\d{2})_", spec_name)
    return m.group(1) if m else None


# -- Finding data model -------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A single validation finding."""

    spec_name: str  # e.g., "01_core_foundation"
    file: str  # e.g., "tasks.md"
    rule: str  # e.g., "missing-file", "oversized-group"
    severity: str  # "error" | "warning" | "hint"
    message: str  # Human-readable description
    line: int | None  # Source line number, if available


# -- Static validation rules ---------------------------------------------------


def check_missing_files(spec_name: str, spec_path: Path) -> list[Finding]:
    """Check for missing expected files in a spec folder.

    Rule: missing-file
    Severity: error
    Produces one finding per missing file.
    """
    findings: list[Finding] = []
    for filename in EXPECTED_FILES:
        if not (spec_path / filename).is_file():
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file=filename,
                    rule="missing-file",
                    severity=SEVERITY_ERROR,
                    message=f"Expected file '{filename}' is missing from spec folder",
                    line=None,
                )
            )
    return findings


def check_oversized_groups(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check for task groups with more than MAX_SUBTASKS_PER_GROUP subtasks.

    Rule: oversized-group
    Severity: warning
    Excludes verification steps from the subtask count.
    """
    findings: list[Finding] = []
    for group in task_groups:
        if group.completed:
            continue
        # Count non-verification subtasks: exclude N.V pattern
        non_verify_count = sum(
            1 for st in group.subtasks if not re.match(rf"^{group.number}\.V$", st.id)
        )
        if non_verify_count > MAX_SUBTASKS_PER_GROUP:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="tasks.md",
                    rule="oversized-group",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Task group {group.number} has {non_verify_count} subtasks "
                        f"(max {MAX_SUBTASKS_PER_GROUP})"
                    ),
                    line=None,
                )
            )
    return findings


def check_missing_verification(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check for task groups without a verification step.

    Rule: missing-verification
    Severity: warning
    A verification step matches the pattern N.V (e.g., "1.V Verify task group 1").
    """
    findings: list[Finding] = []
    for group in task_groups:
        if group.completed:
            continue
        # Checkpoint groups are themselves a final verification step
        if group.title.startswith("Checkpoint"):
            continue
        has_verify = any(
            re.match(rf"^{group.number}\.V$", st.id) for st in group.subtasks
        )
        if not has_verify:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="tasks.md",
                    rule="missing-verification",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Task group {group.number} is missing a verification step "
                        f"({group.number}.V)"
                    ),
                    line=None,
                )
            )
    return findings


# -- Regex patterns for archetype / checkbox validation ----------------------

# Broader pattern to catch malformed archetype tags: matches things like
# [archtype: X], [Archetype: X], [archetype X], [archetype:X], etc.
_MALFORMED_ARCHETYPE_TAG = re.compile(
    r"\[arch[e]?type[:\s]\s*\w+\]", re.IGNORECASE
)

# Valid checkbox characters in task group / subtask lines
_VALID_CHECKBOX_CHARS = {" ", "x", "-", "~"}

# Matches any checkbox-like pattern at the start of a task line
_CHECKBOX_LINE = re.compile(r"^(\s*)- \[(.)\](\s+\*?\s*)(\d+)[\.\s]")


def check_archetype_tags(
    spec_name: str,
    tasks_path: Path,
) -> list[Finding]:
    """Check archetype tags on task group titles for validity.

    Rules:
    - malformed-archetype-tag (error): tag syntax deviates from [archetype: X]
    - invalid-archetype-tag (warning): archetype name not in registry
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []

    for i, line in enumerate(lines, 1):
        # Only check top-level task group lines
        if not re.match(r"^- \[.\]", line):
            continue

        # Check for well-formed archetype tag
        good_match = _ARCHETYPE_TAG.search(line)
        if good_match:
            arch_name = good_match.group(1)
            if arch_name not in _KNOWN_ARCHETYPES:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="invalid-archetype-tag",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Unknown archetype '{arch_name}' in task group title "
                            f"(known: {', '.join(sorted(_KNOWN_ARCHETYPES))})"
                        ),
                        line=i,
                    )
                )
            # Check for duplicate tags on same line
            all_matches = _ARCHETYPE_TAG.findall(line)
            if len(all_matches) > 1:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="malformed-archetype-tag",
                        severity=SEVERITY_ERROR,
                        message=(
                            f"Duplicate archetype tags on line {i}: "
                            f"{', '.join(all_matches)}"
                        ),
                        line=i,
                    )
                )
        else:
            # Check for malformed variants
            bad_match = _MALFORMED_ARCHETYPE_TAG.search(line)
            if bad_match:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="malformed-archetype-tag",
                        severity=SEVERITY_ERROR,
                        message=(
                            f"Malformed archetype tag "
                            f"'{bad_match.group()}' on line {i}; "
                            f"expected format: [archetype: name]"
                        ),
                        line=i,
                    )
                )

    return findings


def check_checkbox_states(
    spec_name: str,
    tasks_path: Path,
) -> list[Finding]:
    """Check checkbox states in tasks.md for valid characters.

    Rule: invalid-checkbox-state (error)
    Valid characters: ' ' (space), 'x', '-', '~'
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []

    for i, line in enumerate(lines, 1):
        m = _CHECKBOX_LINE.match(line)
        if m:
            char = m.group(2)
            if char not in _VALID_CHECKBOX_CHARS:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file="tasks.md",
                        rule="invalid-checkbox-state",
                        severity=SEVERITY_ERROR,
                        message=(
                            f"Invalid checkbox state '[{char}]' on line {i}; "
                            f"valid states: [ ], [x], [-], [~]"
                        ),
                        line=i,
                    )
                )

    return findings


def check_missing_acceptance_criteria(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check for requirement sections without acceptance criteria.

    Rule: missing-acceptance-criteria
    Severity: error
    Scans requirements.md for requirement headings and checks each has at least
    one criterion line containing a requirement ID pattern [NN-REQ-N.N].
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    findings: list[Finding] = []
    current_req_name: str | None = None
    current_req_line: int | None = None
    has_criteria = False

    def _finalize_requirement() -> None:
        """Check if the current requirement section has acceptance criteria."""
        if current_req_name is not None and not has_criteria:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="requirements.md",
                    rule="missing-acceptance-criteria",
                    severity=SEVERITY_ERROR,
                    message=(
                        f"{current_req_name} has no acceptance criteria "
                        f"(no requirement ID pattern found)"
                    ),
                    line=current_req_line,
                )
            )

    for i, line in enumerate(lines, start=1):
        heading_match = _REQUIREMENT_HEADING.match(line)
        if heading_match:
            # Finalize previous requirement section
            _finalize_requirement()
            req_num = heading_match.group(1)
            req_title = heading_match.group(2).strip()
            current_req_name = f"Requirement {req_num}: {req_title}"
            current_req_line = i
            has_criteria = False
            continue

        # Check for requirement ID pattern in current section
        if current_req_name is not None and _REQUIREMENT_ID.search(line):
            has_criteria = True

    # Finalize the last requirement section
    _finalize_requirement()

    return findings


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


def check_untraced_requirements(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check for requirements not referenced by any test in test_spec.md.

    Rule: untraced-requirement
    Severity: warning
    Collects requirement IDs from requirements.md and checks for references
    in test_spec.md.
    """
    req_path = spec_path / "requirements.md"
    test_spec_path = spec_path / "test_spec.md"

    if not req_path.is_file() or not test_spec_path.is_file():
        return []

    # Collect all requirement IDs from requirements.md
    req_text = req_path.read_text(encoding="utf-8")
    # findall returns captured group — bare IDs like "09-REQ-1.1"
    req_ids_bare: list[str] = _REQUIREMENT_ID.findall(req_text)

    if not req_ids_bare:
        return []

    # Read test_spec.md content
    test_text = test_spec_path.read_text(encoding="utf-8")

    findings: list[Finding] = []
    seen: set[str] = set()
    for req_id in req_ids_bare:
        if req_id in seen:
            continue
        seen.add(req_id)
        if req_id not in test_text:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="test_spec.md",
                    rule="untraced-requirement",
                    severity=SEVERITY_WARNING,
                    message=(f"Requirement {req_id} is not referenced in test_spec.md"),
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


# -- Phase 1: Completeness checks ---------------------------------------------


def check_missing_ears_keyword(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that acceptance criteria use EARS syntax (contain SHALL).

    Rule: missing-ears-keyword
    Severity: warning
    Scans requirements.md for lines containing requirement IDs and checks
    each has at least one EARS keyword (SHALL).
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    findings: list[Finding] = []
    for i, line in enumerate(lines, start=1):
        # Only check lines that contain a requirement ID
        if not _REQUIREMENT_ID.search(line):
            continue
        if not _EARS_KEYWORD.search(line):
            # Extract the requirement ID for the message
            match = _REQUIREMENT_ID.search(line)
            req_id = match.group(1) if match else "unknown"
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="requirements.md",
                    rule="missing-ears-keyword",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Criterion {req_id} does not contain EARS keyword "
                        f"'SHALL'. Use EARS syntax for testable requirements."
                    ),
                    line=i,
                )
            )
    return findings


def check_design_completeness(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check design.md for required sections: Correctness Properties,
    Error Handling, and Definition of Done.

    Rules: missing-correctness-properties, missing-error-table,
           missing-definition-of-done
    Severity: warning
    """
    design_path = spec_path / "design.md"
    if not design_path.is_file():
        return []

    text = design_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    has_correctness = False
    has_property = False
    has_error_handling = False
    has_error_table = False
    has_dod = False

    in_error_section = False

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            normalized = _normalize_heading(section)
            in_error_section = "error" in normalized and "handling" in normalized
            if "correctness" in normalized and "properties" in normalized:
                has_correctness = True
            elif in_error_section:
                has_error_handling = True
            elif "definition" in normalized and "done" in normalized:
                has_dod = True
            continue

        if _PROPERTY_HEADING.match(line):
            has_property = True

        if in_error_section and _TABLE_PIPE_ROW.match(line):
            if not _TABLE_SEP_ROW.match(line):
                has_error_table = True

    findings: list[Finding] = []

    if not has_correctness or not has_property:
        findings.append(
            Finding(
                spec_name=spec_name,
                file="design.md",
                rule="missing-correctness-properties",
                severity=SEVERITY_WARNING,
                message=(
                    "design.md is missing a '## Correctness Properties' section "
                    "with at least one '### Property N:' entry"
                ),
                line=None,
            )
        )

    if not has_error_handling or not has_error_table:
        findings.append(
            Finding(
                spec_name=spec_name,
                file="design.md",
                rule="missing-error-table",
                severity=SEVERITY_WARNING,
                message=(
                    "design.md is missing a '## Error Handling' section "
                    "with a markdown table"
                ),
                line=None,
            )
        )

    if not has_dod:
        findings.append(
            Finding(
                spec_name=spec_name,
                file="design.md",
                rule="missing-definition-of-done",
                severity=SEVERITY_WARNING,
                message="design.md is missing a '## Definition of Done' section",
                line=None,
            )
        )

    return findings


def check_missing_coverage_matrix(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check test_spec.md for a Coverage Matrix section with a table.

    Rule: missing-coverage-matrix
    Severity: warning
    """
    ts_path = spec_path / "test_spec.md"
    if not ts_path.is_file():
        return []

    text = ts_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    has_heading = False
    has_table = False
    in_section = False

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            normalized = _normalize_heading(section)
            in_section = "coverage" in normalized and "matrix" in normalized
            if in_section:
                has_heading = True
            continue

        if in_section and _TABLE_PIPE_ROW.match(line):
            if not _TABLE_SEP_ROW.match(line):
                has_table = True

    if not has_heading or not has_table:
        return [
            Finding(
                spec_name=spec_name,
                file="test_spec.md",
                rule="missing-coverage-matrix",
                severity=SEVERITY_WARNING,
                message=(
                    "test_spec.md is missing a '## Coverage Matrix' section "
                    "with a markdown table"
                ),
                line=None,
            )
        ]
    return []


def check_missing_traceability_table(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check tasks.md for a Traceability section with a table.

    Rule: missing-traceability-table
    Severity: warning
    """
    tasks_path = spec_path / "tasks.md"
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    has_heading = False
    has_table = False
    in_section = False

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            in_section = "traceability" in _normalize_heading(section)
            if in_section:
                has_heading = True
            continue

        if in_section and _TABLE_PIPE_ROW.match(line):
            if not _TABLE_SEP_ROW.match(line):
                has_table = True

    if not has_heading or not has_table:
        return [
            Finding(
                spec_name=spec_name,
                file="tasks.md",
                rule="missing-traceability-table",
                severity=SEVERITY_WARNING,
                message=(
                    "tasks.md is missing a '## Traceability' section "
                    "with a markdown table"
                ),
                line=None,
            )
        ]
    return []


def check_inconsistent_req_id_format(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that requirement IDs use a consistent format.

    Rule: inconsistent-req-id-format
    Severity: hint
    Flags specs that mix [NN-REQ-N.N] and **NN-REQ-N.N:** formats.
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")

    has_bracket = bool(_REQ_ID_BRACKET.search(text))
    has_bold = bool(_REQ_ID_BOLD.search(text))

    if has_bracket and has_bold:
        return [
            Finding(
                spec_name=spec_name,
                file="requirements.md",
                rule="inconsistent-req-id-format",
                severity=SEVERITY_HINT,
                message=(
                    "requirements.md mixes [NN-REQ-N.N] and **NN-REQ-N.N:** "
                    "formats. Use one format consistently (prefer [brackets])."
                ),
                line=None,
            )
        ]
    return []


# -- Phase 3: Traceability chain checks ---------------------------------------


def _extract_test_spec_ids(spec_path: Path) -> set[str]:
    """Extract all TS-NN-N IDs from test_spec.md headings."""
    ts_path = spec_path / "test_spec.md"
    if not ts_path.is_file():
        return set()
    text = ts_path.read_text(encoding="utf-8")
    ids: set[str] = set()
    for line in text.splitlines():
        m = _TS_ENTRY_HEADING.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def _extract_property_numbers(spec_path: Path) -> list[int]:
    """Extract Property N numbers from design.md."""
    design_path = spec_path / "design.md"
    if not design_path.is_file():
        return []
    text = design_path.read_text(encoding="utf-8")
    nums: list[int] = []
    for line in text.splitlines():
        m = _PROPERTY_HEADING.match(line)
        if m:
            # Extract number from "### Property N: ..."
            num_match = re.search(r"Property\s+(\d+)", line, re.IGNORECASE)
            if num_match:
                nums.append(int(num_match.group(1)))
    return nums


# Permissive requirement ID pattern — matches bare IDs in tables/prose
_REQ_ID_BARE = re.compile(r"(\d{2}-REQ-\d+\.(?:\d+|E\d+))")


def _extract_req_ids_from_text(
    text: str, spec_prefix: str | None = None,
) -> set[str]:
    """Extract requirement IDs from arbitrary text.

    Uses a permissive pattern that matches bare IDs (without brackets or bold)
    so it works in tables, prose, and formatted text.

    Args:
        text: The text to scan for requirement IDs.
        spec_prefix: If set (e.g. "28"), only return IDs whose numeric prefix
            matches. This filters out cross-spec references that happen to
            appear in the text.
    """
    ids = set(_REQ_ID_BARE.findall(text))
    if spec_prefix is not None:
        ids = {rid for rid in ids if rid.startswith(f"{spec_prefix}-REQ-")}
    return ids


def check_untraced_test_specs(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that every TS-NN-N entry in test_spec.md is referenced in tasks.md.

    Rule: untraced-test-spec
    Severity: warning
    """
    ts_ids = _extract_test_spec_ids(spec_path)
    if not ts_ids:
        return []

    tasks_path = spec_path / "tasks.md"
    if not tasks_path.is_file():
        return []

    tasks_text = tasks_path.read_text(encoding="utf-8")

    findings: list[Finding] = []
    for ts_id in sorted(ts_ids):
        if ts_id not in tasks_text:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="tasks.md",
                    rule="untraced-test-spec",
                    severity=SEVERITY_WARNING,
                    message=f"Test spec entry {ts_id} is not referenced in tasks.md",
                    line=None,
                )
            )
    return findings


def check_untraced_properties(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that every Property N in design.md has a TS-NN-PN in test_spec.md.

    Rule: untraced-property
    Severity: warning
    """
    prop_nums = _extract_property_numbers(spec_path)
    if not prop_nums:
        return []

    ts_path = spec_path / "test_spec.md"
    if not ts_path.is_file():
        return []

    ts_text = ts_path.read_text(encoding="utf-8")

    # Extract spec number from spec_name (first two digits)
    spec_num_match = re.match(r"(\d{2})", spec_name)
    spec_num = spec_num_match.group(1) if spec_num_match else "00"

    findings: list[Finding] = []
    for prop_num in prop_nums:
        expected_ts_id = f"TS-{spec_num}-P{prop_num}"
        if expected_ts_id not in ts_text:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="test_spec.md",
                    rule="untraced-property",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Property {prop_num} in design.md has no corresponding "
                        f"test spec entry ({expected_ts_id})"
                    ),
                    line=None,
                )
            )
    return findings


def check_orphan_error_refs(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that requirement IDs in design.md error table exist in requirements.md.

    Rule: orphan-error-ref
    Severity: warning
    """
    design_path = spec_path / "design.md"
    req_path = spec_path / "requirements.md"
    if not design_path.is_file() or not req_path.is_file():
        return []

    design_text = design_path.read_text(encoding="utf-8")
    req_text = req_path.read_text(encoding="utf-8")

    # Extract req IDs from requirements.md
    known_req_ids = _extract_req_ids_from_text(req_text, _spec_prefix(spec_name))
    if not known_req_ids:
        return []

    # Find error handling section in design.md and extract req IDs from it
    lines = design_text.splitlines()
    in_error_section = False
    error_section_req_ids: set[str] = set()

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            normalized = _normalize_heading(section)
            in_error_section = "error" in normalized and "handling" in normalized
            continue

        if in_error_section:
            ids_in_line = _REQUIREMENT_ID.findall(line)
            error_section_req_ids.update(ids_in_line)

    findings: list[Finding] = []
    for ref_id in sorted(error_section_req_ids):
        if ref_id not in known_req_ids:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="design.md",
                    rule="orphan-error-ref",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Error handling table references {ref_id} which "
                        f"does not exist in requirements.md"
                    ),
                    line=None,
                )
            )
    return findings


def check_coverage_matrix_completeness(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check coverage matrix in test_spec.md against requirements.md.

    Rule: coverage-matrix-mismatch
    Severity: warning
    Reports requirement IDs present in requirements.md but missing from
    the coverage matrix.
    """
    req_path = spec_path / "requirements.md"
    ts_path = spec_path / "test_spec.md"
    if not req_path.is_file() or not ts_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")
    ts_text = ts_path.read_text(encoding="utf-8")

    req_ids = _extract_req_ids_from_text(req_text, _spec_prefix(spec_name))
    if not req_ids:
        return []

    # Find coverage matrix section
    lines = ts_text.splitlines()
    in_matrix = False
    matrix_text = ""

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            normalized = _normalize_heading(section)
            in_matrix = "coverage" in normalized and "matrix" in normalized
            continue
        if in_matrix:
            matrix_text += line + "\n"

    if not matrix_text:
        return []  # No coverage matrix found — handled by check_missing_coverage_matrix

    matrix_req_ids = _extract_req_ids_from_text(matrix_text)

    findings: list[Finding] = []
    missing = sorted(req_ids - matrix_req_ids)
    for req_id in missing:
        findings.append(
            Finding(
                spec_name=spec_name,
                file="test_spec.md",
                rule="coverage-matrix-mismatch",
                severity=SEVERITY_WARNING,
                message=(
                    f"Requirement {req_id} is in requirements.md but missing "
                    f"from the coverage matrix"
                ),
                line=None,
            )
        )
    return findings


def check_traceability_table_completeness(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check traceability table in tasks.md against requirements.md.

    Rule: traceability-table-mismatch
    Severity: warning
    Reports requirement IDs present in requirements.md but missing from
    the traceability table.
    """
    req_path = spec_path / "requirements.md"
    tasks_path = spec_path / "tasks.md"
    if not req_path.is_file() or not tasks_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")
    tasks_text = tasks_path.read_text(encoding="utf-8")

    req_ids = _extract_req_ids_from_text(req_text, _spec_prefix(spec_name))
    if not req_ids:
        return []

    # Find traceability section
    lines = tasks_text.splitlines()
    in_traceability = False
    trace_text = ""

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            in_traceability = "traceability" in _normalize_heading(section)
            continue
        if in_traceability:
            trace_text += line + "\n"

    if not trace_text:
        return []  # No traceability table — handled by check_missing_traceability_table

    trace_req_ids = _extract_req_ids_from_text(trace_text)

    findings: list[Finding] = []
    missing = sorted(req_ids - trace_req_ids)
    for req_id in missing:
        findings.append(
            Finding(
                spec_name=spec_name,
                file="tasks.md",
                rule="traceability-table-mismatch",
                severity=SEVERITY_WARNING,
                message=(
                    f"Requirement {req_id} is in requirements.md but missing "
                    f"from the traceability table"
                ),
                line=None,
            )
        )
    return findings


# -- Phase 4: Section schema validation ---------------------------------------


def check_section_schema(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check spec files for expected and unexpected sections.

    Rules: missing-section (warning for required, hint for recommended),
           extra-section (hint)
    """
    findings: list[Finding] = []

    for filename, schema in _SECTION_SCHEMAS.items():
        file_path = spec_path / filename
        if not file_path.is_file():
            continue

        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines()

        # Extract actual H2 headings (skip fenced code blocks)
        actual_headings: list[str] = []
        in_fence = False
        for line in lines:
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = _H2_HEADING.match(line)
            if m:
                actual_headings.append(m.group(1).strip())

        actual_normalized = {_normalize_heading(h) for h in actual_headings}

        # Check for expected sections
        for section_name, required in schema:
            normalized = _normalize_heading(section_name)
            if normalized not in actual_normalized:
                findings.append(
                    Finding(
                        spec_name=spec_name,
                        file=filename,
                        rule="missing-section",
                        severity=SEVERITY_WARNING if required else SEVERITY_HINT,
                        message=(
                            f"{filename} is missing expected section "
                            f"'## {section_name}'"
                        ),
                        line=None,
                    )
                )

        # NOTE: We intentionally do NOT flag extra sections. Specs can have
        # domain-specific sections beyond the standard template (e.g.,
        # "Detection Rules", "Cross-Reference Consistency").

    return findings


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by spec_name, file, then severity (error < warning < hint).

    Requirements: 09-REQ-1.3
    """
    return sorted(
        findings,
        key=lambda f: (f.spec_name, f.file, SEVERITY_ORDER.get(f.severity, 99)),
    )


# -- Validation orchestrator ---------------------------------------------------


def validate_specs(
    specs_dir: Path,
    discovered_specs: list[SpecInfo],
) -> list[Finding]:
    """Run all static validation rules against all discovered specs.

    1. For each spec, run check_missing_files.
    2. For specs with tasks.md, parse task groups and run:
       - check_oversized_groups
       - check_missing_verification
    3. For specs with requirements.md, run:
       - check_missing_acceptance_criteria
    4. For specs with requirements.md and test_spec.md, run:
       - check_untraced_requirements
    5. Build known_specs map, then for each spec with prd.md, run:
       - check_broken_dependencies
    6. Sort all findings by spec_name, file, severity order.
    7. Return the complete findings list.

    Requirements: 09-REQ-1.1, 09-REQ-1.2, 09-REQ-1.3
    """
    findings: list[Finding] = []

    # Build known_specs map from ALL specs in the directory, not just the
    # filtered subset.  Dependency validation needs to resolve references to
    # specs that may have been filtered out (e.g. already-implemented specs).
    known_specs: dict[str, list[int]] = {}
    _spec_dir_pattern = re.compile(r"^\d{2}_.+$")
    for entry in sorted(specs_dir.iterdir()):
        if not entry.is_dir() or not _spec_dir_pattern.match(entry.name):
            continue
        tasks_path = entry / "tasks.md"
        if tasks_path.is_file():
            try:
                groups = parse_tasks(tasks_path)
                known_specs[entry.name] = [g.number for g in groups]
            except Exception:
                known_specs[entry.name] = []
        else:
            known_specs[entry.name] = []

    # Parse task groups for the specs being linted
    parsed_groups: dict[str, list[TaskGroupDef]] = {}
    for spec in discovered_specs:
        tasks_path = spec.path / "tasks.md"
        if tasks_path.is_file():
            try:
                groups = parse_tasks(tasks_path)
                parsed_groups[spec.name] = groups
            except Exception:
                findings.append(
                    Finding(
                        spec_name=spec.name,
                        file="tasks.md",
                        rule="parse-error",
                        severity=SEVERITY_WARNING,
                        message="Failed to parse tasks.md",
                        line=None,
                    )
                )

    # Run all rules against each spec
    for spec in discovered_specs:
        # 1. Missing files check
        findings.extend(check_missing_files(spec.name, spec.path))

        # 2. Task-based checks (oversized groups, missing verification)
        if spec.name in parsed_groups:
            groups = parsed_groups[spec.name]
            findings.extend(check_oversized_groups(spec.name, groups))
            findings.extend(check_missing_verification(spec.name, groups))

        # 2b. Archetype tag and checkbox state checks
        tasks_path = spec.path / "tasks.md"
        if tasks_path.is_file():
            findings.extend(check_archetype_tags(spec.name, tasks_path))
            findings.extend(check_checkbox_states(spec.name, tasks_path))

        # 3. Acceptance criteria check
        if (spec.path / "requirements.md").is_file():
            findings.extend(check_missing_acceptance_criteria(spec.name, spec.path))

        # 4. Traceability check
        if (spec.path / "requirements.md").is_file() and (
            spec.path / "test_spec.md"
        ).is_file():
            findings.extend(check_untraced_requirements(spec.name, spec.path))

        # 5. Dependency check
        if (spec.path / "prd.md").is_file():
            findings.extend(
                check_broken_dependencies(spec.name, spec.path, known_specs)
            )

        # 6. Coarse dependency check
        if (spec.path / "prd.md").is_file():
            findings.extend(_check_coarse_dependency(spec.name, spec.path / "prd.md"))

        # -- Phase 1: Completeness checks --
        # 7. EARS keyword check
        if (spec.path / "requirements.md").is_file():
            findings.extend(check_missing_ears_keyword(spec.name, spec.path))

        # 8. Design completeness (correctness properties, error table, DoD)
        if (spec.path / "design.md").is_file():
            findings.extend(check_design_completeness(spec.name, spec.path))

        # 9. Coverage matrix check
        if (spec.path / "test_spec.md").is_file():
            findings.extend(check_missing_coverage_matrix(spec.name, spec.path))

        # 10. Traceability table check
        if (spec.path / "tasks.md").is_file():
            findings.extend(check_missing_traceability_table(spec.name, spec.path))

        # 11. Requirement ID format consistency
        if (spec.path / "requirements.md").is_file():
            findings.extend(check_inconsistent_req_id_format(spec.name, spec.path))

        # -- Phase 3: Traceability chain checks --
        # 12. Test spec -> tasks traceability
        if (spec.path / "test_spec.md").is_file() and (
            spec.path / "tasks.md"
        ).is_file():
            findings.extend(check_untraced_test_specs(spec.name, spec.path))

        # 13. Property -> test spec traceability
        if (spec.path / "design.md").is_file() and (
            spec.path / "test_spec.md"
        ).is_file():
            findings.extend(check_untraced_properties(spec.name, spec.path))

        # 14. Error table -> requirements cross-reference
        if (spec.path / "design.md").is_file() and (
            spec.path / "requirements.md"
        ).is_file():
            findings.extend(check_orphan_error_refs(spec.name, spec.path))

        # 15. Coverage matrix completeness
        if (spec.path / "requirements.md").is_file() and (
            spec.path / "test_spec.md"
        ).is_file():
            findings.extend(check_coverage_matrix_completeness(spec.name, spec.path))

        # 16. Traceability table completeness
        if (spec.path / "requirements.md").is_file() and (
            spec.path / "tasks.md"
        ).is_file():
            findings.extend(check_traceability_table_completeness(spec.name, spec.path))

        # -- Phase 4: Section schema validation --
        # 17. Section schema checks
        findings.extend(check_section_schema(spec.name, spec.path))

    # 18. Circular dependency check (cross-spec, runs once for all specs)
    findings.extend(_check_circular_dependency(discovered_specs))

    # 19. Sort findings
    return sort_findings(findings)


def compute_exit_code(findings: list[Finding]) -> int:
    """Determine exit code from findings: 1 if any errors, 0 otherwise.

    Requirements: 09-REQ-9.4, 09-REQ-9.5
    """
    return 1 if any(f.severity == SEVERITY_ERROR for f in findings) else 0


# ---------------------------------------------------------------------------
# AI-powered semantic analysis (merged from ai_validator.py)
# ---------------------------------------------------------------------------

import json
import logging as _logging_ai
import re as _re_ai
from collections import defaultdict as _defaultdict_ai
from typing import Any as _Any_ai

from anthropic.types import TextBlock

from agent_fox.core.client import create_async_anthropic_client
from agent_fox.spec.parser import _DEP_TABLE_HEADER_ALT, _parse_table_rows

_ai_logger = _logging_ai.getLogger(__name__)

# -- JSON extraction from AI responses ----------------------------------------

_JSON_FENCE = _re_ai.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", _re_ai.DOTALL)


def _extract_response_text(response: _Any_ai, context: str) -> str | None:
    """Extract text from an AI response, handling TextBlock union.

    Returns the text content of the first block, or None if unavailable.
    Logs a warning with *context* when no text is found.
    """
    first_block = response.content[0]
    if isinstance(first_block, TextBlock):
        return first_block.text
    maybe_text: str | None = getattr(first_block, "text", None)
    if maybe_text is None:
        _ai_logger.warning("AI response for %s has no text content, skipping", context)
    return maybe_text


def _extract_json(text: str) -> dict:
    """Parse JSON from an AI response, stripping markdown code fences if present.

    Tries raw parsing first, then falls back to extracting fenced blocks.
    Raises json.JSONDecodeError or TypeError on failure.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Try extracting from code fences
    match = _JSON_FENCE.search(text)
    if match:
        return json.loads(match.group(1))
    raise json.JSONDecodeError("No JSON found in AI response", text, 0)


# -- Backtick extraction regex ------------------------------------------------

_BACKTICK_TOKEN = _re_ai.compile(r"`([^`]+)`")

# -- Stale-dependency data model -----------------------------------------------


@dataclass(frozen=True)
class DependencyRef:
    """A code identifier extracted from a dependency Relationship cell.

    Requirements: 21-REQ-1.1
    """

    declaring_spec: str  # spec that declares the dependency
    upstream_spec: str  # spec being depended on
    identifier: str  # extracted code identifier (normalized)
    raw_relationship: str  # original Relationship text for context


def _normalize_identifier(raw: str) -> str:
    """Normalize a backtick-extracted identifier.

    - Strip trailing parentheses: ``Delete()`` -> ``Delete``
    - Preserve dotted paths as-is.

    Requirements: 21-REQ-1.2, 21-REQ-1.3
    """
    if raw.endswith("()"):
        return raw[:-2]
    return raw


def extract_relationship_identifiers(
    declaring_spec: str,
    prd_path: Path,
) -> list[DependencyRef]:
    """Extract backtick-delimited code identifiers from dependency tables.

    Parses prd.md for the alternative dependency table format
    (| Spec | From Group | To Group | Relationship |) and extracts all
    backtick-delimited tokens from the Relationship column.

    Normalization:
    - Strip trailing parentheses: ``Delete()`` -> ``Delete``
    - Preserve dotted paths: ``store.SnippetStore.Delete`` stays as-is

    Returns an empty list if no dependency table or no backtick tokens found.

    Requirements: 21-REQ-1.1, 21-REQ-1.2, 21-REQ-1.3, 21-REQ-1.E1, 21-REQ-1.E2
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    refs: list[DependencyRef] = []

    for i, line in enumerate(lines):
        if not _DEP_TABLE_HEADER_ALT.search(line):
            continue

        for cells in _parse_table_rows(lines, i + 1):
            if len(cells) < 4:
                continue

            upstream_spec = cells[0].strip()
            relationship = cells[3].strip()

            if not upstream_spec or not relationship:
                continue

            # Extract backtick tokens from the Relationship column
            tokens = _BACKTICK_TOKEN.findall(relationship)
            for token in tokens:
                identifier = _normalize_identifier(token)
                refs.append(
                    DependencyRef(
                        declaring_spec=declaring_spec,
                        upstream_spec=upstream_spec,
                        identifier=identifier,
                        raw_relationship=relationship,
                    )
                )

    return refs


# -- Stale-dependency AI prompt ------------------------------------------------

_STALE_DEP_PROMPT = """\
You are an expert software architect reviewing specification documents. \
You will be given a design document from an upstream specification and a \
list of code identifiers that downstream specifications claim to depend on.

For each identifier, determine whether the upstream design document defines, \
describes, or reasonably implies that identifier. Consider:
- Exact name matches (type, function, method, struct, interface)
- Qualified names (e.g., `store.Store` matching a `Store` type in a \
  `store` package section)
- Method references (e.g., `Store.Delete` matching a `Delete` method on \
  `Store`)
- Standard library or language built-ins (e.g., `error`, `context.Context`, \
  `slog`) should be marked as "found" since they are not defined in specs

Return your analysis as a JSON object with this exact structure:
{{
  "results": [
    {{
      "identifier": "the identifier being checked",
      "found": true or false,
      "explanation": "brief reason why it was or was not found",
      "suggestion": "if not found, a suggested correction or null"
    }}
  ]
}}

Upstream design document ({upstream_spec}):

{design_content}

---

Identifiers to validate:
{identifiers_json}
"""

_RULE_STALE_DEP = "stale-dependency"


async def validate_dependency_interfaces(
    upstream_spec: str,
    design_content: str,
    refs: list[DependencyRef],
    model: str,
) -> list[Finding]:
    """Validate dependency identifiers against an upstream design document.

    Sends a single AI request per upstream spec containing the design.md
    content and all identifiers referencing that spec. Parses the
    structured JSON response and produces Warning-severity findings for
    identifiers the AI determines are not present.

    Requirements: 21-REQ-2.1, 21-REQ-2.3, 21-REQ-2.4, 21-REQ-2.5,
                  21-REQ-2.E3
    """
    identifiers = [r.identifier for r in refs]
    identifiers_json = json.dumps(identifiers)

    prompt = _STALE_DEP_PROMPT.format(
        upstream_spec=upstream_spec,
        design_content=design_content,
        identifiers_json=identifiers_json,
    )

    async with create_async_anthropic_client() as client:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

    # Extract text from response
    response_text = _extract_response_text(
        response, f"stale-dep check on '{upstream_spec}'"
    )
    if response_text is None:
        return []

    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError):
        _ai_logger.warning(
            "AI response for stale-dep check on '%s' was not valid JSON, skipping",
            upstream_spec,
        )
        return []

    results = data.get("results", [])
    if not isinstance(results, list):
        _ai_logger.warning(
            "AI response for stale-dep check on '%s' has invalid 'results', skipping",
            upstream_spec,
        )
        return []

    # Build a lookup from identifier -> DependencyRef(s) for finding context
    ref_by_id: dict[str, DependencyRef] = {}
    for ref in refs:
        if ref.identifier not in ref_by_id:
            ref_by_id[ref.identifier] = ref

    findings: list[Finding] = []
    for result in results:
        if not isinstance(result, dict):
            continue

        identifier = result.get("identifier", "")
        found = result.get("found", True)
        explanation = result.get("explanation", "")
        suggestion = result.get("suggestion")

        if found:
            continue

        # Look up the declaring spec from the ref
        matched_ref = ref_by_id.get(identifier)
        declaring_spec = matched_ref.declaring_spec if matched_ref else "unknown"

        suggestion_text = suggestion if suggestion else ""
        message = (
            f"Dependency on {upstream_spec}: identifier `{identifier}` "
            f"not found in design.md. {explanation}."
        )
        if suggestion_text:
            message += f" Suggestion: {suggestion_text}"

        findings.append(
            Finding(
                spec_name=declaring_spec,
                file="prd.md",
                rule=_RULE_STALE_DEP,
                severity=SEVERITY_WARNING,
                message=message,
                line=None,
            )
        )

    return findings


async def run_stale_dependency_validation(
    discovered_specs: list[SpecInfo],
    specs_dir: Path,
    model: str,
) -> list[Finding]:
    """Run stale-dependency validation across all discovered specs.

    Algorithm:
    1. For each spec with a prd.md, extract dependency identifiers.
    2. Group identifiers by upstream spec name.
    3. For each upstream spec group:
       a. Read the upstream spec's design.md (once per upstream spec).
       b. If design.md doesn't exist, skip (no finding).
       c. Call validate_dependency_interfaces() with all refs for that
          upstream spec.
    4. Collect and return all findings.

    If the AI model is unavailable, log a warning and return empty list.

    Requirements: 21-REQ-2.2, 21-REQ-2.E1, 21-REQ-2.E2, 21-REQ-3.1,
                  21-REQ-3.2, 21-REQ-3.E1
    """
    # 1. Extract all dependency identifiers from all specs
    all_refs: list[DependencyRef] = []
    for spec in discovered_specs:
        prd_path = spec.path / "prd.md"
        if not prd_path.is_file():
            continue
        refs = extract_relationship_identifiers(spec.name, prd_path)
        all_refs.extend(refs)

    if not all_refs:
        return []

    # 2. Group by upstream spec
    by_upstream: dict[str, list[DependencyRef]] = _defaultdict_ai(list)
    for ref in all_refs:
        by_upstream[ref.upstream_spec].append(ref)

    # 3. Validate each upstream spec
    findings: list[Finding] = []
    for upstream_name, refs in by_upstream.items():
        design_path = specs_dir / upstream_name / "design.md"
        if not design_path.is_file():
            continue  # 21-REQ-2.E1: skip if design.md missing

        design_content = design_path.read_text(encoding="utf-8")

        try:
            upstream_findings = await validate_dependency_interfaces(
                upstream_name, design_content, refs, model
            )
            findings.extend(upstream_findings)
        except Exception as exc:
            _ai_logger.warning(
                "Stale-dependency validation failed for upstream '%s': %s. Skipping.",
                upstream_name,
                exc,
            )

    return findings


# -- Existing AI validation rules -----------------------------------------------

# Rule names for AI-detected issues
_RULE_VAGUE = "vague-criterion"
_RULE_IMPLEMENTATION_LEAK = "implementation-leak"

# Map from AI response issue_type to rule name
_ISSUE_TYPE_TO_RULE = {
    "vague": _RULE_VAGUE,
    "implementation-leak": _RULE_IMPLEMENTATION_LEAK,
}

_AI_PROMPT = """\
You are an expert specification reviewer. Analyze the following acceptance \
criteria from a software specification and identify quality issues.

For each criterion, check for two types of problems:
1. **Vague or unmeasurable** criteria: Criteria that use subjective language \
like "should be fast", "look good", "easy to use", "performant", etc. These \
cannot be objectively verified.
2. **Implementation-leaking** criteria: Criteria that describe HOW the system \
should be built (implementation details) rather than WHAT it should do \
(behavior). For example, "use Redis for caching" or "implement with a \
singleton pattern".

Return your analysis as a JSON object with this exact structure:
{
  "issues": [
    {
      "criterion_id": "the requirement ID, e.g. 09-REQ-1.1",
      "issue_type": "vague" or "implementation-leak",
      "explanation": "why this criterion is problematic",
      "suggestion": "how to improve it"
    }
  ]
}

If there are no issues, return: {"issues": []}

Here are the acceptance criteria to analyze:

"""


async def analyze_acceptance_criteria(
    spec_name: str,
    spec_path: Path,
    model: str,
) -> list[Finding]:
    """Use AI to analyze acceptance criteria for quality issues.

    Reads requirements.md, extracts acceptance criteria text, and sends
    it to the STANDARD-tier model for analysis.

    The prompt asks the model to identify:
    1. Vague or unmeasurable criteria (rule: vague-criterion)
    2. Implementation-leaking criteria (rule: implementation-leak)

    Returns Hint-severity findings for each issue identified.
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")

    # Create the Anthropic client and send the request
    async with create_async_anthropic_client() as client:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": _AI_PROMPT + req_text,
                }
            ],
        )

    # Parse the response
    response_text = _extract_response_text(response, f"spec '{spec_name}'")
    if response_text is None:
        return []

    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError):
        _ai_logger.warning(
            "AI response for spec '%s' was not valid JSON, skipping",
            spec_name,
        )
        return []

    issues = data.get("issues", [])
    if not isinstance(issues, list):
        _ai_logger.warning(
            "AI response for spec '%s' has invalid 'issues' field, skipping",
            spec_name,
        )
        return []

    findings: list[Finding] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue

        criterion_id = issue.get("criterion_id", "unknown")
        issue_type = issue.get("issue_type", "")
        explanation = issue.get("explanation", "")
        suggestion = issue.get("suggestion", "")

        rule = _ISSUE_TYPE_TO_RULE.get(issue_type)
        if rule is None:
            continue

        message = f"[{criterion_id}] {explanation}"
        if suggestion:
            message += f" Suggestion: {suggestion}"

        findings.append(
            Finding(
                spec_name=spec_name,
                file="requirements.md",
                rule=rule,
                severity=SEVERITY_HINT,
                message=message,
                line=None,
            )
        )

    return findings


# -- AI rewrite prompt and function (Spec 22) ---------------------------------

_REWRITE_PROMPT = """\
You are an expert requirements engineer using the EARS (Easy Approach to \
Requirements Syntax) methodology. You will rewrite acceptance criteria that \
have been flagged for quality issues.

EARS syntax uses these keywords:
- SHALL — for unconditional requirements
- WHEN <trigger>, THE system SHALL — for event-driven requirements
- WHILE <state>, THE system SHALL — for state-driven requirements
- IF <condition>, THEN THE system SHALL — for conditional requirements
- WHERE <feature>, THE system SHALL — for feature-driven requirements

Rules for rewriting:
1. Use EARS syntax keywords (SHALL, WHEN, WHILE, IF/THEN, WHERE) in every \
rewritten criterion.
2. Preserve the original intent and behavioral scope — only fix the \
identified quality issue (vagueness or implementation leak).
3. Produce text that would pass the vague-criterion and implementation-leak \
analysis rules and would not be flagged again.
4. Make criteria measurable and objectively verifiable.
5. Do NOT include the requirement ID prefix in the replacement text — \
only provide the criterion body.

Return your rewrites as a JSON object with this exact structure:
{{
  "rewrites": [
    {{
      "criterion_id": "the requirement ID, e.g. 09-REQ-1.1",
      "original": "the original criterion text",
      "replacement": "the rewritten criterion text"
    }}
  ]
}}

Here is the full requirements document for context:

{requirements_text}

---

The following criteria have been flagged for rewriting:

{flagged_criteria}
"""

_MAX_CRITERIA_PER_BATCH = 20


async def rewrite_criteria(
    spec_name: str,
    requirements_text: str,
    findings: list[Finding],
    model: str,
) -> dict[str, str]:
    """Send a batched rewrite request for flagged criteria.

    Args:
        spec_name: Name of the spec being fixed.
        requirements_text: Full content of requirements.md.
        findings: AI findings with rule vague-criterion or implementation-leak.
        model: Model ID for the STANDARD tier.

    Returns:
        Mapping of criterion_id -> replacement_text.
        Empty dict on failure.

    Requirements: 22-REQ-1.1, 22-REQ-2.*, 22-REQ-3.*
    """
    if not findings:
        return {}

    # Build the flagged criteria list for the prompt
    flagged_lines: list[str] = []
    for finding in findings:
        flagged_lines.append(
            f"- Criterion {finding.message.split(']')[0].lstrip('[')}]: "
            f"Issue type: {finding.rule}. {finding.message}"
        )

    flagged_criteria = "\n".join(flagged_lines)

    prompt = _REWRITE_PROMPT.format(
        requirements_text=requirements_text,
        flagged_criteria=flagged_criteria,
    )

    try:
        async with create_async_anthropic_client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
    except Exception as exc:
        _ai_logger.warning(
            "AI rewrite call failed for spec '%s': %s. Skipping rewrite.",
            spec_name,
            exc,
        )
        return {}

    # Extract text from response
    response_text = _extract_response_text(response, f"rewrite for spec '{spec_name}'")
    if response_text is None:
        return {}

    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError):
        _ai_logger.warning(
            "AI rewrite response for spec '%s' was not valid JSON, skipping",
            spec_name,
        )
        return {}

    rewrites_list = data.get("rewrites", [])
    if not isinstance(rewrites_list, list):
        _ai_logger.warning(
            "AI rewrite response for spec '%s' has invalid 'rewrites', skipping",
            spec_name,
        )
        return {}

    # Build the result mapping
    result: dict[str, str] = {}
    for entry in rewrites_list:
        if not isinstance(entry, dict):
            continue
        criterion_id = entry.get("criterion_id", "")
        replacement = entry.get("replacement", "")
        if criterion_id and replacement:
            result[criterion_id] = replacement

    return result


async def run_ai_validation(
    discovered_specs: list[SpecInfo],
    model: str,
    specs_dir: Path | None = None,
) -> list[Finding]:
    """Run AI validation across all discovered specs.

    Runs both the existing acceptance criteria analysis and the new
    stale-dependency validation. The specs_dir parameter is needed for
    the stale-dependency rule to locate upstream design.md files.

    If the AI model is unavailable (auth error, network error), logs a
    warning and returns an empty list.

    Requirements: 21-REQ-4.1
    """
    findings: list[Finding] = []

    for spec in discovered_specs:
        req_path = spec.path / "requirements.md"
        if not req_path.is_file():
            continue

        try:
            spec_findings = await analyze_acceptance_criteria(
                spec.name, spec.path, model
            )
            findings.extend(spec_findings)
        except Exception as exc:
            _ai_logger.warning(
                "AI analysis unavailable for spec '%s': %s. Skipping AI checks.",
                spec.name,
                exc,
            )
            return []

    # NEW: stale-dependency validation (21-REQ-4.1)
    if specs_dir is not None:
        try:
            stale_findings = await run_stale_dependency_validation(
                discovered_specs, specs_dir, model
            )
            findings.extend(stale_findings)
        except Exception as exc:
            _ai_logger.warning(
                "Stale-dependency validation unavailable: %s. Skipping.",
                exc,
            )

    return findings
