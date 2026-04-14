"""Traceability chain validation rules."""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.spec._patterns import (
    extract_test_spec_ids as _extract_test_spec_ids,
)
from agent_fox.spec.validators._helpers import (
    _H2_HEADING,
    _PROPERTY_HEADING,
    _REQUIREMENT_ID,
    SEVERITY_WARNING,
    _extract_req_ids_from_text,
    _normalize_heading,
    _spec_prefix,
)
from agent_fox.spec.validators.finding import Finding

# Pattern that matches only edge-case requirement IDs: [NN-REQ-N.EN]
_EDGE_CASE_REQ_ID = re.compile(r"\[(\d+-REQ-\d+\.E\d+)\]")


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
    # findall returns captured group -- bare IDs like "09-REQ-1.1"
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

    # Extract spec number prefix from spec_name
    spec_num_match = re.match(r"(\d+)", spec_name)
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
                        f"Property {prop_num} in design.md has no corresponding test spec entry ({expected_ts_id})"
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
                    message=(f"Error handling table references {ref_id} which does not exist in requirements.md"),
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
        # No coverage matrix -- handled by check_missing_coverage_matrix
        return []

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
                message=(f"Requirement {req_id} is in requirements.md but missing from the coverage matrix"),
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
        # No traceability table -- handled by check_missing_traceability_table
        return []

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
                message=(f"Requirement {req_id} is in requirements.md but missing from the traceability table"),
                line=None,
            )
        )
    return findings


def check_untraced_edge_cases(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check that every edge-case requirement has an entry in Edge Case Tests.

    Rule: untraced-edge-case
    Severity: warning
    Extracts [NN-REQ-N.EN] IDs from requirements.md and verifies each
    appears in the '## Edge Case Tests' section of test_spec.md.
    """
    req_path = spec_path / "requirements.md"
    ts_path = spec_path / "test_spec.md"

    if not req_path.is_file() or not ts_path.is_file():
        return []

    req_text = req_path.read_text(encoding="utf-8")
    edge_case_ids = sorted(set(_EDGE_CASE_REQ_ID.findall(req_text)))

    if not edge_case_ids:
        return []

    ts_text = ts_path.read_text(encoding="utf-8")

    # Extract only the Edge Case Tests section text
    lines = ts_text.splitlines()
    in_edge_section = False
    edge_section_text = ""

    for line in lines:
        heading = _H2_HEADING.match(line)
        if heading:
            section = heading.group(1).strip()
            normalized = _normalize_heading(section)
            in_edge_section = "edge" in normalized and "case" in normalized and "test" in normalized
            continue
        if in_edge_section:
            edge_section_text += line + "\n"

    findings: list[Finding] = []
    for edge_id in edge_case_ids:
        if edge_id not in edge_section_text:
            findings.append(
                Finding(
                    spec_name=spec_name,
                    file="test_spec.md",
                    rule="untraced-edge-case",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Edge case requirement {edge_id} is not referenced in the "
                        f"'## Edge Case Tests' section of test_spec.md"
                    ),
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
    from agent_fox.spec.validators.schema import _check_section_with_table

    return _check_section_with_table(
        spec_name,
        spec_path / "test_spec.md",
        ["coverage", "matrix"],
        "missing-coverage-matrix",
        "test_spec.md is missing a '## Coverage Matrix' section with a markdown table",
    )


def check_missing_traceability_table(
    spec_name: str,
    spec_path: Path,
) -> list[Finding]:
    """Check tasks.md for a Traceability section with a table.

    Rule: missing-traceability-table
    Severity: warning
    """
    from agent_fox.spec.validators.schema import _check_section_with_table

    return _check_section_with_table(
        spec_name,
        spec_path / "tasks.md",
        ["traceability"],
        "missing-traceability-table",
        "tasks.md is missing a '## Traceability' section with a markdown table",
    )
