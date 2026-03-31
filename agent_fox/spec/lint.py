"""Backing module for spec linting.

Provides a function to validate specification files that can be called
from code without the CLI framework.

Requirements: 59-REQ-3.1, 59-REQ-3.2, 59-REQ-3.3, 59-REQ-3.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from agent_fox.core.errors import PlanError
from agent_fox.core.models import resolve_model
from agent_fox.spec.discovery import SpecInfo, discover_specs
from agent_fox.spec.validator import (
    Finding,
    compute_exit_code,
    sort_findings,
    validate_specs,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LintResult:
    """Result of a spec lint run.

    Attributes:
        findings: List of validation findings.
        fix_results: List of fix results (when fix=True).
        exit_code: 0 for clean, 1 for error-severity findings.
    """

    findings: list[Finding] = field(default_factory=list)
    fix_results: list = field(default_factory=list)
    exit_code: int = 0


def _is_spec_implemented(spec: SpecInfo) -> bool:
    """Check whether a spec is fully implemented based on its tasks.md."""
    tasks_path = spec.path / "tasks.md"
    if not tasks_path.is_file():
        return False

    from agent_fox.spec.parser import parse_tasks

    try:
        groups = parse_tasks(tasks_path)
    except Exception:
        return False

    if not groups:
        return False

    return all(g.completed for g in groups)


def run_lint_specs(
    specs_dir: Path,
    *,
    ai: bool = False,
    fix: bool = False,
    lint_all: bool = False,
) -> LintResult:
    """Run spec linting and return structured results.

    Args:
        specs_dir: Path to the specifications directory.
        ai: Enable AI-powered semantic analysis.
        fix: Apply mechanical auto-fixes.
        lint_all: Include fully-implemented specs.

    Returns:
        LintResult with findings, fix results, and exit code.

    Raises:
        PlanError: If specs_dir does not exist.

    Requirements: 59-REQ-3.1, 59-REQ-3.2, 59-REQ-3.3, 59-REQ-3.E1
    """
    if not specs_dir.exists():
        raise PlanError(f"Specs directory not found: {specs_dir}")

    # Discover specs
    try:
        discovered: list[SpecInfo] = discover_specs(specs_dir)
    except PlanError:
        # No specs found — return error finding
        no_spec_finding = Finding(
            spec_name="(none)",
            file=".specs/",
            rule="no-specs",
            severity="error",
            message="No specifications found in .specs/ directory",
            line=None,
        )
        return LintResult(findings=[no_spec_finding], exit_code=1)

    # Filter out fully-implemented specs unless lint_all is set
    if not lint_all:
        filtered = [s for s in discovered if not _is_spec_implemented(s)]
        skipped = len(discovered) - len(filtered)
        if skipped > 0:
            logger.info(
                "Skipping %d fully-implemented spec(s) (use --all to include)",
                skipped,
            )
        if not filtered:
            return LintResult(findings=[], exit_code=0)
        discovered = filtered

    # Run static validation
    findings = validate_specs(specs_dir, discovered)

    # Optionally run AI validation
    if ai:
        findings = _merge_ai_findings(findings, discovered, specs_dir)

    # Apply fixes if requested
    all_fix_results: list = []
    if fix:
        from agent_fox.spec.fixer import apply_fixes

        known_specs = _build_known_specs(discovered)
        fix_results = apply_fixes(findings, discovered, specs_dir, known_specs)
        all_fix_results.extend(fix_results)

        if all_fix_results:
            # Re-validate after fixes
            findings = validate_specs(specs_dir, discovered)
            if ai:
                findings = _merge_ai_findings(findings, discovered, specs_dir)

    exit_code = compute_exit_code(findings)
    return LintResult(
        findings=findings,
        fix_results=all_fix_results,
        exit_code=exit_code,
    )


def _build_known_specs(
    discovered: list[SpecInfo],
) -> dict[str, list[int]]:
    """Build a mapping of spec name to list of task group numbers."""
    from agent_fox.spec.parser import parse_tasks

    known: dict[str, list[int]] = {}
    for spec in discovered:
        tasks_path = spec.path / "tasks.md"
        if tasks_path.is_file():
            try:
                groups = parse_tasks(tasks_path)
                known[spec.name] = [g.number for g in groups]
            except Exception:
                known[spec.name] = []
        else:
            known[spec.name] = []
    return known


def _merge_ai_findings(
    findings: list[Finding],
    discovered: list[SpecInfo],
    specs_dir: Path,
) -> list[Finding]:
    """Run AI validation and merge results into existing findings."""
    import asyncio

    try:
        from agent_fox.spec.ai_validation import run_ai_validation

        standard_model = resolve_model("STANDARD").model_id
        ai_findings = asyncio.run(
            run_ai_validation(discovered, standard_model, specs_dir=specs_dir)
        )
        return sort_findings(findings + ai_findings)
    except Exception as exc:
        logger.warning("AI validation failed: %s", exc)
        return findings
