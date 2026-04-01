"""File-existence validation rules."""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.validators._helpers import EXPECTED_FILES, SEVERITY_ERROR
from agent_fox.spec.validators.finding import Finding


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
