"""Finding data model and related utilities."""

from __future__ import annotations

from dataclasses import dataclass

from agent_fox.spec.validators._helpers import (
    SEVERITY_ERROR,
    SEVERITY_ORDER,
)


@dataclass(frozen=True)
class Finding:
    """A single validation finding."""

    spec_name: str  # e.g., "01_core_foundation"
    file: str  # e.g., "tasks.md"
    rule: str  # e.g., "missing-file", "oversized-group"
    severity: str  # "error" | "warning" | "hint"
    message: str  # Human-readable description
    line: int | None  # Source line number, if available


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by spec_name, file, then severity (error < warning < hint).

    Requirements: 09-REQ-1.3
    """
    return sorted(
        findings,
        key=lambda f: (f.spec_name, f.file, SEVERITY_ORDER.get(f.severity, 99)),
    )


def compute_exit_code(findings: list[Finding]) -> int:
    """Determine exit code from findings: 1 if any errors, 0 otherwise.

    Requirements: 09-REQ-9.4, 09-REQ-9.5
    """
    return 1 if any(f.severity == SEVERITY_ERROR for f in findings) else 0
