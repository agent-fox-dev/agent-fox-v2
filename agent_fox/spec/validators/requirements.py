"""Requirement-related validation rules."""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.spec.validators._helpers import (
    _EARS_KEYWORD,
    _REQ_ID_BOLD,
    _REQ_ID_BRACKET,
    _REQUIREMENT_HEADING,
    _REQUIREMENT_ID,
    MAX_REQUIREMENTS,
    SEVERITY_ERROR,
    SEVERITY_HINT,
    SEVERITY_WARNING,
    Finding,
)


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
                    message=(f"{current_req_name} has no acceptance criteria (no requirement ID pattern found)"),
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


def _collect_criterion_text(lines: list[str], start: int) -> str:
    """Collect the full text of a criterion starting at `start` (0-based).

    A criterion starts on the line containing a requirement ID and continues
    on subsequent lines that are indented continuation text (not a new numbered
    item, heading, blank line, or another requirement ID).
    """
    parts = [lines[start]]
    for j in range(start + 1, len(lines)):
        next_line = lines[j]
        # Stop at blank lines
        if not next_line.strip():
            break
        # Stop at new numbered list items (e.g. "1. ", "2. ")
        if re.match(r"^\d+\.\s", next_line):
            break
        # Stop at headings
        if next_line.startswith("#"):
            break
        # Stop at another requirement ID on a non-indented line
        if _REQUIREMENT_ID.search(next_line) and not next_line[0].isspace():
            break
        # Stop at horizontal rules
        if re.match(r"^-{3,}$", next_line.strip()):
            break
        # This is a continuation line
        parts.append(next_line)
    return " ".join(parts)


def check_missing_ears_keyword(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that acceptance criteria use EARS syntax (contain SHALL).

    Rule: missing-ears-keyword
    Severity: warning
    Scans requirements.md for lines containing requirement IDs and collects
    the full multi-line criterion text before checking for the EARS keyword.
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    findings: list[Finding] = []
    for i, line in enumerate(lines):
        # Only check lines that contain a requirement ID
        if not _REQUIREMENT_ID.search(line):
            continue
        # Collect the full criterion text (may span multiple lines)
        full_text = _collect_criterion_text(lines, i)
        if not _EARS_KEYWORD.search(full_text):
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
                    line=i + 1,  # 1-based line number
                )
            )
    return findings


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


def check_non_bracket_req_id_format(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that requirement IDs use bracket format, not bold-only format.

    Rule: non-bracket-req-id-format
    Severity: warning
    Flags specs where all requirement IDs use **NN-REQ-N.N:** bold format
    exclusively and none use the preferred [NN-REQ-N.N] bracket format.
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")

    has_bracket = bool(_REQ_ID_BRACKET.search(text))
    has_bold = bool(_REQ_ID_BOLD.search(text))

    if has_bold and not has_bracket:
        return [
            Finding(
                spec_name=spec_name,
                file="requirements.md",
                rule="non-bracket-req-id-format",
                severity=SEVERITY_WARNING,
                message=(
                    "requirements.md uses **NN-REQ-N.N:** bold format for all "
                    "requirement IDs. Use [NN-REQ-N.N] bracket format instead."
                ),
                line=None,
            )
        ]
    return []


def check_too_many_requirements(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that a spec does not have more than MAX_REQUIREMENTS requirements.

    Rule: too-many-requirements
    Severity: warning
    Counts '### Requirement N:' headings in requirements.md and emits a
    warning if the count exceeds MAX_REQUIREMENTS.
    """
    req_path = spec_path / "requirements.md"
    if not req_path.is_file():
        return []

    text = req_path.read_text(encoding="utf-8")
    count = sum(1 for line in text.splitlines() if _REQUIREMENT_HEADING.match(line))

    if count > MAX_REQUIREMENTS:
        return [
            Finding(
                spec_name=spec_name,
                file="requirements.md",
                rule="too-many-requirements",
                severity=SEVERITY_WARNING,
                message=(
                    f"requirements.md has {count} requirements (max {MAX_REQUIREMENTS}). "
                    f"Consider splitting into multiple specs."
                ),
                line=None,
            )
        ]
    return []
