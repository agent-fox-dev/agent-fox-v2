"""Failure collection.

Runs detected quality checks as subprocesses, captures stdout/stderr, and
parses failures into structured records.

Requirements: 08-REQ-2.1, 08-REQ-2.2, 08-REQ-2.3, 08-REQ-2.E1
"""

from __future__ import annotations

import subprocess  # noqa: F401
from dataclasses import dataclass
from pathlib import Path

from agent_fox.fix.detector import CheckDescriptor  # noqa: F401

SUBPROCESS_TIMEOUT = 300  # 5 minutes


@dataclass(frozen=True)
class FailureRecord:
    """A structured failure from a quality check."""

    check: CheckDescriptor  # Which check produced this failure
    output: str  # Combined stdout + stderr
    exit_code: int  # Process exit code


def run_checks(
    checks: list[CheckDescriptor],
    project_root: Path,
) -> tuple[list[FailureRecord], list[CheckDescriptor]]:
    """Run all check commands and return (failures, passed_checks).

    Each check is run as a subprocess with a 5-minute timeout.
    Commands that exit 0 are considered passing.
    Commands that exit non-zero produce a FailureRecord.
    Commands that time out produce a FailureRecord with a timeout message.

    Returns a tuple of (failure_records, checks_that_passed).
    """
    raise NotImplementedError
