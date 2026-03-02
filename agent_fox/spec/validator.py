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
from agent_fox.spec.parser import TaskGroupDef, parse_tasks  # noqa: F401

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
_REQUIREMENT_ID = re.compile(r"\[\d{2}-REQ-\d+\.\d+\]")
_DEP_TABLE_HEADER = re.compile(r"\|\s*This Spec\s*\|\s*Depends On\s*\|", re.IGNORECASE)
_TABLE_SEP = re.compile(r"^\s*\|[\s\-|]+\|\s*$")
_GROUP_REF = re.compile(r"\bgroup\s+(\d+)\b", re.IGNORECASE)


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
) -> list[Finding]:
    """Check for dependency references to non-existent specs or task groups.

    Rule: broken-dependency
    Severity: error
    Parses the dependency table from prd.md and validates each reference
    against the known_specs dict (mapping spec name to list of group numbers).
    """
    prd_path = spec_path / "prd.md"
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    findings: list[Finding] = []
    in_table = False
    header_found = False

    for line_num, line in enumerate(lines, start=1):
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
            stripped = line.strip()
            if not stripped.startswith("|"):
                break

            # Split cells by pipe
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]

            if len(cells) < 2:
                continue

            to_spec = cells[1].strip()
            description = cells[2].strip() if len(cells) >= 3 else ""

            # Check if the target spec exists
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
                        line=line_num,
                    )
                )
            else:
                # Check for group references in the description column
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
                                line=line_num,
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
    req_ids: list[str] = _REQUIREMENT_ID.findall(req_text)
    # Strip brackets to get bare IDs like "09-REQ-1.1"
    req_ids_bare = [rid.strip("[]") for rid in req_ids]

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

    # Build known_specs map: spec_name -> list of group numbers
    known_specs: dict[str, list[int]] = {}

    # Parse task groups for all specs that have tasks.md
    parsed_groups: dict[str, list[TaskGroupDef]] = {}
    for spec in discovered_specs:
        tasks_path = spec.path / "tasks.md"
        if tasks_path.is_file():
            try:
                groups = parse_tasks(tasks_path)
                parsed_groups[spec.name] = groups
                known_specs[spec.name] = [g.number for g in groups]
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
        else:
            known_specs[spec.name] = []

    # Run all rules against each spec
    for spec in discovered_specs:
        # 1. Missing files check
        findings.extend(check_missing_files(spec.name, spec.path))

        # 2. Task-based checks (oversized groups, missing verification)
        if spec.name in parsed_groups:
            groups = parsed_groups[spec.name]
            findings.extend(check_oversized_groups(spec.name, groups))
            findings.extend(check_missing_verification(spec.name, groups))

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

    # 6. Sort findings
    return sort_findings(findings)


def compute_exit_code(findings: list[Finding]) -> int:
    """Determine exit code from findings: 1 if any errors, 0 otherwise.

    Requirements: 09-REQ-9.4, 09-REQ-9.5
    """
    return 1 if any(f.severity == SEVERITY_ERROR for f in findings) else 0
