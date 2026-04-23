"""Section schema and design completeness validation rules."""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.validators._helpers import (
    _H2_HEADING,
    _PROPERTY_HEADING,
    _SECTION_SCHEMAS,
    _TABLE_PIPE_ROW,
    _TABLE_SEP_ROW,
    SEVERITY_HINT,
    SEVERITY_WARNING,
    Finding,
    _normalize_heading,
)


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
                message=("design.md is missing a '## Error Handling' section with a markdown table"),
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


def _check_section_with_table(
    spec_name: str,
    file_path: Path,
    heading_keywords: list[str],
    rule: str,
    message: str,
) -> list[Finding]:
    """Check that a file contains a section heading with a table beneath it.

    Returns a Finding if the heading or table is missing.
    """
    if not file_path.is_file():
        return []

    lines = file_path.read_text(encoding="utf-8").splitlines()

    has_heading = False
    has_table = False
    in_section = False

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            normalized = _normalize_heading(heading.group(1).strip())
            in_section = all(kw in normalized for kw in heading_keywords)
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
                file=file_path.name,
                rule=rule,
                severity=SEVERITY_WARNING,
                message=message,
                line=None,
            )
        ]
    return []


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
                        message=(f"{filename} is missing expected section '## {section_name}'"),
                        line=None,
                    )
                )

        # NOTE: We intentionally do NOT flag extra sections. Specs can have
        # domain-specific sections beyond the standard template (e.g.,
        # "Detection Rules", "Cross-Reference Consistency").

    return findings
