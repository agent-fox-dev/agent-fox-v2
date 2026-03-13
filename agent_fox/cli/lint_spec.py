"""CLI command for spec validation: agent-fox lint-spec.

Requirements: 09-REQ-9.1, 09-REQ-9.2, 09-REQ-9.3, 09-REQ-9.4, 09-REQ-9.5,
              09-REQ-1.E1
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import click

from agent_fox.core.errors import PlanError
from agent_fox.core.models import resolve_model
from agent_fox.spec.discovery import SpecInfo, discover_specs
from agent_fox.spec.validator import (
    SEVERITY_ERROR,
    SEVERITY_HINT,
    SEVERITY_WARNING,
    Finding,
    compute_exit_code,
    sort_findings,
    validate_specs,
)

logger = logging.getLogger(__name__)


def _findings_to_dicts(findings: list[Finding]) -> list[dict]:
    """Convert a list of Finding instances to plain dictionaries."""
    return [
        {
            "spec_name": f.spec_name,
            "file": f.file,
            "rule": f.rule,
            "severity": f.severity,
            "message": f.message,
            "line": f.line,
        }
        for f in findings
    ]


def _build_summary(findings: list[Finding]) -> dict:
    """Build a summary counts dictionary from findings."""
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    hint_count = sum(1 for f in findings if f.severity == SEVERITY_HINT)
    return {
        "error": error_count,
        "warning": warning_count,
        "hint": hint_count,
        "total": len(findings),
    }


_SEVERITY_MARKERS = {
    SEVERITY_ERROR: "\u2717",  # ✗
    SEVERITY_WARNING: "\u26a0",  # ⚠
    SEVERITY_HINT: "\u2139",  # ℹ
}


def _format_table(findings: list[Finding]) -> str:
    """Render findings as compact text lines grouped by spec.

    Output structure:
        Spec Validation \u2014 N findings

        {spec_name} (N findings)
          {marker} {file}:{line}  {rule} \u2014 {message}
          ...

        Summary: N error(s) | N warning(s) | N hint(s)
    """
    if not findings:
        return "No findings.\n"

    lines: list[str] = []
    lines.append(f"Spec Validation \u2014 {len(findings)} findings")

    # Group findings by spec name, preserving encounter order
    specs_seen: list[str] = []
    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        if f.spec_name not in grouped:
            specs_seen.append(f.spec_name)
            grouped[f.spec_name] = []
        grouped[f.spec_name].append(f)

    for spec_name in specs_seen:
        spec_findings = grouped[spec_name]
        lines.append("")
        lines.append(f"{spec_name} ({len(spec_findings)} findings)")
        for f in spec_findings:
            marker = _SEVERITY_MARKERS.get(f.severity, "?")
            loc = f.file
            if f.line is not None:
                loc = f"{f.file}:{f.line}"
            lines.append(f"  {marker} {loc}  {f.rule} \u2014 {f.message}")

    # Summary line
    summary = _build_summary(findings)
    parts = []
    if summary["error"] > 0:
        parts.append(f"{summary['error']} error(s)")
    if summary["warning"] > 0:
        parts.append(f"{summary['warning']} warning(s)")
    if summary["hint"] > 0:
        parts.append(f"{summary['hint']} hint(s)")
    lines.append("")
    lines.append(f"Summary: {' | '.join(parts)}")

    return "\n".join(lines) + "\n"


def _format_json(findings: list[Finding]) -> str:
    """Serialize findings as JSON.

    Structure:
    {
        "findings": [...],
        "summary": {"error": N, "warning": N, "hint": N, "total": N}
    }
    """
    data = {
        "findings": _findings_to_dicts(findings),
        "summary": _build_summary(findings),
    }
    return json.dumps(data, indent=2)


def _build_known_specs(
    discovered: list[SpecInfo],
) -> dict[str, list[int]]:
    """Build a mapping of spec name to list of task group numbers.

    Used by the fixer to look up upstream group numbers.
    """
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


def _format_fix_summary(fix_results: list) -> str:
    """Format a summary of applied fixes for stderr output."""
    from collections import Counter

    counts: Counter[str] = Counter()
    for r in fix_results:
        counts[r.rule] += 1

    parts = [f"{count} {rule}" for rule, count in sorted(counts.items())]
    return f"Fixed: {', '.join(parts)}"


def _is_spec_implemented(spec: SpecInfo) -> bool:
    """Check whether a spec is fully implemented based on its tasks.md.

    A spec is considered implemented when its tasks.md exists and every
    top-level task group has a completed checkbox (``[x]``).

    Specs without tasks.md are considered NOT implemented.
    """
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


def _git_run(*args: str) -> str:
    """Run a git command and return stdout. Raises on failure."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _git_current_branch() -> str:
    """Return the name of the current git branch."""
    return _git_run("rev-parse", "--abbrev-ref", "HEAD")


def _create_fix_branch() -> str:
    """Create and checkout a feature branch for lint-spec fixes.

    Branch name format: lint-spec/fix-YYYYMMDD-HHMMSS
    Returns the branch name.
    """
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    branch = f"lint-spec/fix-{ts}"
    _git_run("checkout", "-b", branch)
    return branch


def _commit_fixes(fix_summary: str) -> None:
    """Stage .specs/ changes and commit with a descriptive message."""
    _git_run("add", ".specs/")
    _git_run(
        "commit",
        "-m",
        f"fix(specs): lint-spec auto-fix\n\n{fix_summary}",
    )


@click.command("lint-spec")
@click.option(
    "--ai",
    is_flag=True,
    default=False,
    help="Enable AI-powered semantic analysis of acceptance criteria.",
)
@click.option(
    "--fix",
    is_flag=True,
    default=False,
    help="Automatically fix mechanically fixable findings.",
)
@click.option(
    "--all",
    "lint_all",
    is_flag=True,
    default=False,
    help="Lint all specs, including fully-implemented ones.",
)
@click.pass_context
def lint_spec(ctx: click.Context, ai: bool, fix: bool, lint_all: bool) -> None:
    """Validate specification files for structural and quality problems."""
    json_mode = ctx.obj.get("json", False)
    output_format = "json" if json_mode else "table"
    specs_dir = Path(".specs")

    # Discover specs -- handle missing/empty .specs/ directory
    try:
        discovered: list[SpecInfo] = discover_specs(specs_dir)
    except PlanError:
        # 09-REQ-1.E1: no specifications found
        finding = Finding(
            spec_name="(none)",
            file=".specs/",
            rule="no-specs",
            severity=SEVERITY_ERROR,
            message="No specifications found in .specs/ directory",
            line=None,
        )
        _output_findings([finding], output_format)
        ctx.exit(1)
        return

    # Filter out fully-implemented specs unless --all is set
    if not lint_all:
        filtered = [s for s in discovered if not _is_spec_implemented(s)]
        skipped = len(discovered) - len(filtered)
        if skipped > 0:
            logger.info(
                "Skipping %d fully-implemented spec(s) (use --all to include)",
                skipped,
            )
        if not filtered:
            _output_findings([], output_format)
            ctx.exit(0)
            return
        discovered = filtered

    # Run static validation
    findings = validate_specs(specs_dir, discovered)

    # Optionally run AI validation
    if ai:
        findings = _merge_ai_findings(findings, discovered, specs_dir)

    # 22-REQ-1.1: Apply AI rewrites when both --ai and --fix are provided
    ai_fix_results: list = []
    if ai and fix:
        ai_fix_results = _apply_ai_fixes(findings, discovered, specs_dir)

    # 20-REQ-6.1: Apply auto-fixes when --fix is provided
    if fix:
        from agent_fox.spec.fixer import apply_fixes

        known_specs = _build_known_specs(discovered)
        fix_results = apply_fixes(findings, discovered, specs_dir, known_specs)
        all_fix_results = ai_fix_results + fix_results
        if all_fix_results:
            # Print fix summary to stderr (20-REQ-6.6, 22-REQ-4.1)
            summary = _format_fix_summary(all_fix_results)
            click.echo(summary, err=True)

            # Re-validate while fixes are still applied (20-REQ-6.2)
            findings = validate_specs(specs_dir, discovered)
            if ai:
                findings = _merge_ai_findings(findings, discovered, specs_dir)

            # Commit fixes to a feature branch so the user can review
            try:
                original_branch = _git_current_branch()
                branch = _create_fix_branch()
                _commit_fixes(summary)
                _git_run("checkout", original_branch)
                click.echo(
                    f"Fixes committed to branch '{branch}'. "
                    f"Review and merge when ready:\n"
                    f"  git diff {original_branch}..{branch}\n"
                    f"  git merge {branch}",
                    err=True,
                )
            except subprocess.CalledProcessError as exc:
                logger.warning(
                    "Failed to commit fixes to branch: %s",
                    exc.stderr or exc,
                )
                click.echo(
                    "Warning: fixes applied but could not be "
                    "committed to a branch. Changes are in your "
                    "working tree.",
                    err=True,
                )

    # Output results
    _output_findings(findings, output_format)

    # Set exit code based on findings
    exit_code = compute_exit_code(findings)
    ctx.exit(exit_code)


def _merge_ai_findings(
    findings: list[Finding],
    discovered: list[SpecInfo],
    specs_dir: Path,
) -> list[Finding]:
    """Run AI validation and merge results into existing findings.

    Requirements: 09-REQ-8.1
    """
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


def _apply_ai_fixes(
    findings: list[Finding],
    discovered: list[SpecInfo],
    specs_dir: Path,
) -> list:
    """Apply AI-powered fixes for criteria rewrites and test spec generation.

    Handles two categories:
    1. vague-criterion / implementation-leak: rewrites criteria in requirements.md
    2. untraced-requirement: generates test spec entries in test_spec.md

    Requirements: 22-REQ-1.1, 22-REQ-1.4, 22-REQ-3.1, 22-REQ-3.E1, 22-REQ-4.1
    """
    from agent_fox.spec.ai_validation import (
        _MAX_CRITERIA_PER_BATCH,
        generate_test_spec_entries,
        rewrite_criteria,
    )
    from agent_fox.spec.fixer import (
        _REQ_ID_IN_MESSAGE,
        AI_FIXABLE_RULES,
        fix_ai_criteria,
        fix_ai_test_spec_entries,
        parse_finding_criterion_id,
    )

    # Filter to AI-fixable findings
    ai_findings = [f for f in findings if f.rule in AI_FIXABLE_RULES]
    if not ai_findings:
        return []

    # Separate criteria rewrites from test spec generation
    criteria_rules = {"vague-criterion", "implementation-leak"}
    criteria_findings = [f for f in ai_findings if f.rule in criteria_rules]
    untraced_findings = [f for f in ai_findings if f.rule == "untraced-requirement"]

    # Build spec lookup
    spec_by_name: dict[str, SpecInfo] = {s.name: s for s in discovered}
    standard_model = resolve_model("STANDARD").model_id
    all_results: list = []

    # --- 1. Criteria rewrites (vague-criterion, implementation-leak) ---
    if criteria_findings:
        by_spec: dict[str, list[Finding]] = {}
        for f in criteria_findings:
            by_spec.setdefault(f.spec_name, []).append(f)

        for spec_name, spec_findings in by_spec.items():
            spec = spec_by_name.get(spec_name)
            if spec is None:
                continue

            req_path = spec.path / "requirements.md"
            if not req_path.is_file():
                continue

            requirements_text = req_path.read_text(encoding="utf-8")

            batches = [
                spec_findings[i : i + _MAX_CRITERIA_PER_BATCH]
                for i in range(0, len(spec_findings), _MAX_CRITERIA_PER_BATCH)
            ]

            for batch in batches:
                try:
                    rewrites = asyncio.run(
                        rewrite_criteria(
                            spec_name,
                            requirements_text,
                            batch,
                            standard_model,
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "AI rewrite failed for spec '%s': %s",
                        spec_name,
                        exc,
                    )
                    continue

                if not rewrites:
                    continue

                findings_map: dict[str, str] = {}
                for f in batch:
                    cid = parse_finding_criterion_id(f)
                    if cid:
                        findings_map[cid] = f.rule

                results = fix_ai_criteria(spec_name, req_path, rewrites, findings_map)
                all_results.extend(results)

    # --- 2. Test spec generation (untraced-requirement) ---
    if untraced_findings:
        by_spec_untraced: dict[str, list[Finding]] = {}
        for f in untraced_findings:
            by_spec_untraced.setdefault(f.spec_name, []).append(f)

        for spec_name, spec_findings in by_spec_untraced.items():
            spec = spec_by_name.get(spec_name)
            if spec is None:
                continue

            req_path = spec.path / "requirements.md"
            ts_path = spec.path / "test_spec.md"
            if not req_path.is_file() or not ts_path.is_file():
                continue

            requirements_text = req_path.read_text(encoding="utf-8")
            test_spec_text = ts_path.read_text(encoding="utf-8")

            # Extract requirement IDs from finding messages
            untraced_ids: list[str] = []
            for f in spec_findings:
                m = _REQ_ID_IN_MESSAGE.search(f.message)
                if m:
                    untraced_ids.append(m.group(1))

            if not untraced_ids:
                continue

            try:
                entries = asyncio.run(
                    generate_test_spec_entries(
                        spec_name,
                        requirements_text,
                        test_spec_text,
                        untraced_ids,
                        standard_model,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "AI test spec generation failed for '%s': %s",
                    spec_name,
                    exc,
                )
                continue

            if entries:
                results = fix_ai_test_spec_entries(spec_name, ts_path, entries)
                all_results.extend(results)

    return all_results


def _output_findings(findings: list[Finding], output_format: str) -> None:
    """Output findings in the requested format."""
    if output_format == "json":
        click.echo(_format_json(findings))
    else:
        click.echo(_format_table(findings), nl=False)
