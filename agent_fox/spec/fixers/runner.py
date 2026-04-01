"""Fix orchestrator: apply_fixes and helpers.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.validator import Finding

from .archetype import fix_invalid_archetype_tag, fix_malformed_archetype_tag
from .checkbox import fix_invalid_checkbox_state
from .sections import (
    fix_missing_correctness_properties,
    fix_missing_coverage_matrix,
    fix_missing_definition_of_done,
    fix_missing_error_table,
    fix_missing_traceability_table,
)
from .standard import (
    _parse_stale_dep_fixes,
    fix_coarse_dependency,
    fix_inconsistent_req_id_format,
    fix_missing_verification,
    fix_stale_dependency,
)
from .tables import fix_coverage_matrix_mismatch, fix_traceability_table_mismatch
from .types import _REQ_ID_IN_MESSAGE, FIXABLE_RULES, FixResult

logger = logging.getLogger(__name__)


def _extract_req_ids_from_findings(findings: list[Finding]) -> list[str]:
    """Extract requirement IDs from mismatch finding messages."""
    ids: list[str] = []
    for finding in findings:
        m = _REQ_ID_IN_MESSAGE.search(finding.message)
        if m:
            ids.append(m.group(1))
    return sorted(set(ids))


def apply_fixes(
    findings: list[Finding],
    discovered_specs: list[SpecInfo],
    specs_dir: Path,
    known_specs: dict[str, list[int]],
) -> list[FixResult]:
    """Apply all available auto-fixes for the given findings.

    Iterates through findings, identifies those with FIXABLE_RULES,
    groups them by spec and rule, and applies the appropriate fixer.

    Deduplicates by (spec_name, rule) to avoid applying the same fixer
    twice to the same file.

    Returns a list of all FixResults applied.

    Requirements: 20-REQ-6.2, 20-REQ-6.5, 20-REQ-6.E1, 20-REQ-6.E3,
                  20-REQ-6.E4
    """
    if not findings:
        return []

    # Filter to fixable findings and deduplicate by (spec_name, rule)
    fixable: dict[tuple[str, str], Finding] = {}
    # For rules that need ALL findings per spec (not just first), collect them
    stale_dep_findings: dict[str, list[Finding]] = {}
    mismatch_findings: dict[tuple[str, str], list[Finding]] = {}
    _MULTI_FINDING_RULES = {
        "stale-dependency",
        "traceability-table-mismatch",
        "coverage-matrix-mismatch",
    }
    for finding in findings:
        if finding.rule in FIXABLE_RULES:
            key = (finding.spec_name, finding.rule)
            if finding.rule == "stale-dependency":
                stale_dep_findings.setdefault(finding.spec_name, []).append(finding)
                if key not in fixable:
                    fixable[key] = finding
            elif finding.rule in _MULTI_FINDING_RULES:
                mismatch_findings.setdefault(key, []).append(finding)
                if key not in fixable:
                    fixable[key] = finding
            else:
                if key not in fixable:
                    fixable[key] = finding

    if not fixable:
        return []

    # Build spec lookup
    spec_by_name: dict[str, SpecInfo] = {s.name: s for s in discovered_specs}

    all_results: list[FixResult] = []

    # Dispatch table: rule -> (filename, fixer_fn) for fixers that take
    # (spec_name, file_path) and need only a file-existence guard.
    _fixer = tuple[str, Callable[..., list[FixResult]]]
    _FILE_FIXERS: dict[str, _fixer] = {
        "missing-verification": (
            "tasks.md",
            fix_missing_verification,
        ),
        "inconsistent-req-id-format": (
            "requirements.md",
            fix_inconsistent_req_id_format,
        ),
        "missing-definition-of-done": (
            "design.md",
            fix_missing_definition_of_done,
        ),
        "missing-error-table": (
            "design.md",
            fix_missing_error_table,
        ),
        "missing-correctness-properties": (
            "design.md",
            fix_missing_correctness_properties,
        ),
        "invalid-archetype-tag": (
            "tasks.md",
            fix_invalid_archetype_tag,
        ),
        "malformed-archetype-tag": (
            "tasks.md",
            fix_malformed_archetype_tag,
        ),
        "invalid-checkbox-state": (
            "tasks.md",
            fix_invalid_checkbox_state,
        ),
    }

    # Dispatch table: rule -> fixer_fn for fixers that take (spec_name, spec_path).
    _DIR_FIXERS: dict[str, Callable[..., list[FixResult]]] = {
        "missing-traceability-table": fix_missing_traceability_table,
        "missing-coverage-matrix": fix_missing_coverage_matrix,
    }

    for (spec_name, rule), _finding in fixable.items():
        spec = spec_by_name.get(spec_name)
        if spec is None:
            continue

        try:
            if rule in _FILE_FIXERS:
                filename, fixer_fn = _FILE_FIXERS[rule]
                path = spec.path / filename
                if path.is_file():
                    all_results.extend(fixer_fn(spec_name, path))

            elif rule in _DIR_FIXERS:
                all_results.extend(_DIR_FIXERS[rule](spec_name, spec.path))

            elif rule == "coarse-dependency":
                prd_path = spec.path / "prd.md"
                if prd_path.is_file():
                    current_groups = known_specs.get(spec_name, [])
                    all_results.extend(
                        fix_coarse_dependency(
                            spec_name, prd_path, known_specs, current_groups
                        )
                    )

            elif rule == "stale-dependency":
                prd_path = spec.path / "prd.md"
                if prd_path.is_file():
                    id_fixes = _parse_stale_dep_fixes(
                        stale_dep_findings.get(spec_name, [])
                    )
                    if id_fixes:
                        all_results.extend(
                            fix_stale_dependency(spec_name, prd_path, id_fixes)
                        )

            elif rule == "traceability-table-mismatch":
                key = (spec_name, rule)
                missing_ids = _extract_req_ids_from_findings(
                    mismatch_findings.get(key, [])
                )
                if missing_ids:
                    all_results.extend(
                        fix_traceability_table_mismatch(
                            spec_name, spec.path, missing_ids
                        )
                    )

            elif rule == "coverage-matrix-mismatch":
                key = (spec_name, rule)
                missing_ids = _extract_req_ids_from_findings(
                    mismatch_findings.get(key, [])
                )
                if missing_ids:
                    all_results.extend(
                        fix_coverage_matrix_mismatch(spec_name, spec.path, missing_ids)
                    )

        except OSError as exc:
            logger.warning(
                "Failed to apply fix for rule '%s' on spec '%s': %s",
                rule,
                spec_name,
                exc,
            )
            continue

    return all_results
