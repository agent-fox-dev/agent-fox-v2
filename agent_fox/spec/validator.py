"""Static validation rules for specification files.

Requirements: 09-REQ-2.1, 09-REQ-2.2, 09-REQ-3.1, 09-REQ-3.2,
              09-REQ-4.1, 09-REQ-4.2, 09-REQ-5.1, 09-REQ-5.2,
              09-REQ-6.1, 09-REQ-6.2, 09-REQ-6.3, 09-REQ-7.1, 09-REQ-7.2,
              09-REQ-1.2, 09-REQ-1.3
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import TaskGroupDef  # noqa: F401

# -- Severity constants -------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_HINT = "hint"

# Sorting order: error < warning < hint
SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_HINT: 2}

# -- Constants -----------------------------------------------------------------

EXPECTED_FILES = ["prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"]
MAX_SUBTASKS_PER_GROUP = 6


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
    raise NotImplementedError


def check_oversized_groups(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check for task groups with more than MAX_SUBTASKS_PER_GROUP subtasks.

    Rule: oversized-group
    Severity: warning
    Excludes verification steps from the subtask count.
    """
    raise NotImplementedError


def check_missing_verification(
    spec_name: str,
    task_groups: list[TaskGroupDef],
) -> list[Finding]:
    """Check for task groups without a verification step.

    Rule: missing-verification
    Severity: warning
    A verification step matches the pattern N.V (e.g., "1.V Verify task group 1").
    """
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by spec_name, file, then severity (error < warning < hint).

    Requirements: 09-REQ-1.3
    """
    raise NotImplementedError


# -- Validation orchestrator ---------------------------------------------------

def validate_specs(
    specs_dir: Path,
    discovered_specs: list[SpecInfo],
) -> list[Finding]:
    """Run all static validation rules against all discovered specs.

    Requirements: 09-REQ-1.1, 09-REQ-1.2, 09-REQ-1.3
    """
    raise NotImplementedError


def compute_exit_code(findings: list[Finding]) -> int:
    """Determine exit code from findings: 1 if any errors, 0 otherwise.

    Requirements: 09-REQ-9.4, 09-REQ-9.5
    """
    raise NotImplementedError
