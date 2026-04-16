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
from agent_fox.spec.validators import (
    Finding,
    compute_exit_code,
    sort_findings,
    validate_specs,
)

logger = logging.getLogger(__name__)

# Batch limits for AI fix dispatch
_MAX_REWRITE_BATCH = 20  # Max criteria per rewrite_criteria() call
_MAX_UNTRACED_BATCH = 20  # Max requirement IDs per generate_test_spec_entries() call


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
            file=str(specs_dir),
            rule="no-specs",
            severity="error",
            message=f"No specifications found in {specs_dir} directory",
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
        # AI fixes first (requires --ai)
        if ai:
            ai_fix_results = _apply_ai_fixes(findings, discovered, specs_dir)
            all_fix_results.extend(ai_fix_results)

        # Mechanical fixes
        from agent_fox.spec.fixers.runner import apply_fixes

        known_specs = _build_known_specs(discovered)
        fix_results = apply_fixes(findings, discovered, specs_dir, known_specs)
        all_fix_results.extend(fix_results)

        if all_fix_results:
            # Re-validate after fixes (AI fixes are NOT re-invoked)
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
        ai_findings = asyncio.run(run_ai_validation(discovered, standard_model, specs_dir=specs_dir))
        return sort_findings(findings + ai_findings)
    except Exception as exc:
        logger.warning("AI validation failed: %s", exc)
        return findings


async def _apply_ai_fixes_async(
    findings: list[Finding],
    discovered: list[SpecInfo],
    specs_dir: Path,
    model: str,
) -> list:
    """Dispatch AI-fixable findings to the correct generator+fixer pair.

    For each spec:
    1. Criteria rewrites: vague-criterion / implementation-leak findings
       -> rewrite_criteria() -> fix_ai_criteria()
    2. Test spec generation: untraced-requirement findings
       -> generate_test_spec_entries() -> fix_ai_test_spec_entries()

    Returns list of all FixResult objects produced.

    Requirements: 109-REQ-2.1, 109-REQ-2.2, 109-REQ-2.3, 109-REQ-3.1,
                  109-REQ-3.2, 109-REQ-4.1, 109-REQ-2.E1, 109-REQ-2.E2,
                  109-REQ-3.E1, 109-REQ-3.E2, 109-REQ-3.E3
    """
    from agent_fox.spec.ai_validation import generate_test_spec_entries, rewrite_criteria  # noqa: PLC0415
    from agent_fox.spec.fixers.ai import fix_ai_criteria, fix_ai_test_spec_entries  # noqa: PLC0415
    from agent_fox.spec.fixers.types import _REQ_ID_IN_MESSAGE, AI_FIXABLE_RULES  # noqa: PLC0415

    # Filter to AI-fixable findings only
    ai_findings = [f for f in findings if f.rule in AI_FIXABLE_RULES]
    if not ai_findings:
        return []

    # Build a lookup from spec name to SpecInfo
    spec_lookup: dict[str, SpecInfo] = {s.name: s for s in discovered}

    # Group findings by spec name
    findings_by_spec: dict[str, list[Finding]] = {}
    for f in ai_findings:
        findings_by_spec.setdefault(f.spec_name, []).append(f)

    all_results: list = []

    for spec_name, spec_findings in findings_by_spec.items():
        spec_info = spec_lookup.get(spec_name)
        if spec_info is None:
            continue

        req_path = spec_info.path / "requirements.md"
        if not req_path.is_file():
            continue

        req_text = req_path.read_text()

        # -- 1. Criteria rewrites (vague-criterion + implementation-leak) -------

        criteria_findings = [f for f in spec_findings if f.rule in {"vague-criterion", "implementation-leak"}]

        if criteria_findings:
            # Build findings_map: criterion_id -> rule name
            findings_map: dict[str, str] = {}
            for f in criteria_findings:
                m = _REQ_ID_IN_MESSAGE.search(f.message)
                if m:
                    findings_map[m.group(1)] = f.rule

            try:
                for i in range(0, len(criteria_findings), _MAX_REWRITE_BATCH):
                    batch = criteria_findings[i : i + _MAX_REWRITE_BATCH]
                    rewrites = await rewrite_criteria(
                        spec_name=spec_name,
                        requirements_text=req_text,
                        findings=batch,
                        model=model,
                    )
                    if rewrites:
                        fix_results = fix_ai_criteria(
                            spec_name=spec_name,
                            req_path=req_path,
                            rewrites=rewrites,
                            findings_map=findings_map,
                        )
                        all_results.extend(fix_results)
                        # Re-read requirements after rewrite for subsequent batches
                        req_text = req_path.read_text()
            except Exception as exc:
                logger.warning("AI criteria rewrite failed for spec '%s': %s", spec_name, exc)
                continue  # Skip remaining processing for this spec

        # -- 2. Test spec generation (untraced-requirement) --------------------

        untraced_findings = [f for f in spec_findings if f.rule == "untraced-requirement"]

        if untraced_findings:
            ts_path = spec_info.path / "test_spec.md"
            if not ts_path.is_file():
                # REQ-3.E3: skip generation when test_spec.md is missing
                continue

            ts_text = ts_path.read_text()

            # Extract requirement IDs from finding messages
            untraced_ids: list[str] = []
            for f in untraced_findings:
                m = _REQ_ID_IN_MESSAGE.search(f.message)
                if m:
                    untraced_ids.append(m.group(1))

            if not untraced_ids:
                continue

            try:
                for i in range(0, len(untraced_ids), _MAX_UNTRACED_BATCH):
                    batch_ids = untraced_ids[i : i + _MAX_UNTRACED_BATCH]
                    entries = await generate_test_spec_entries(
                        spec_name=spec_name,
                        requirements_text=req_text,
                        test_spec_text=ts_text,
                        untraced_req_ids=batch_ids,
                        model=model,
                    )
                    if entries:
                        fix_results = fix_ai_test_spec_entries(
                            spec_name=spec_name,
                            ts_path=ts_path,
                            entries=entries,
                        )
                        all_results.extend(fix_results)
                        # Re-read test spec after insertion for subsequent batches
                        ts_text = ts_path.read_text()
            except Exception as exc:
                logger.warning("AI test spec generation failed for spec '%s': %s", spec_name, exc)

    return all_results


def _apply_ai_fixes(
    findings: list[Finding],
    discovered: list[SpecInfo],
    specs_dir: Path,
) -> list:
    """Synchronous wrapper for AI fix dispatch.

    Resolves the STANDARD model tier and delegates to
    _apply_ai_fixes_async() via asyncio.run().
    Returns empty list on any top-level failure.

    Requirements: 109-REQ-1.1, 109-REQ-1.E1, 109-REQ-3.3
    """
    import asyncio

    try:
        model = resolve_model("STANDARD").model_id
        return asyncio.run(_apply_ai_fixes_async(findings, discovered, specs_dir, model))
    except Exception as exc:
        logger.warning("AI fix pipeline failed: %s", exc)
        return []
