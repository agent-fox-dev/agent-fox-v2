"""CLI command for spec validation: agent-fox lint-spec.

Requirements: 09-REQ-9.1, 09-REQ-9.2, 09-REQ-9.3, 09-REQ-9.4, 09-REQ-9.5,
              09-REQ-1.E1
"""

from __future__ import annotations

import asyncio
import json
import logging
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


def format_table(findings: list[Finding]) -> str:
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


def format_json(findings: list[Finding]) -> str:
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


def format_yaml(findings: list[Finding]) -> str:
    """Serialize findings as YAML with the same structure as JSON."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("PyYAML is not installed; falling back to JSON output.")
        return format_json(findings)

    data = {
        "findings": _findings_to_dicts(findings),
        "summary": _build_summary(findings),
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


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


@click.command("lint-spec")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format for findings.",
)
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
@click.pass_context
def lint_spec(ctx: click.Context, output_format: str, ai: bool, fix: bool) -> None:
    """Validate specification files for structural and quality problems."""
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

    # Run static validation
    findings = validate_specs(specs_dir, discovered)

    # Optionally run AI validation
    if ai:
        try:
            from agent_fox.spec.ai_validator import run_ai_validation

            # 09-REQ-8.1: use STANDARD tier via model registry
            standard_model = resolve_model("STANDARD").model_id
            ai_findings = asyncio.run(
                run_ai_validation(discovered, standard_model, specs_dir=specs_dir)
            )
            findings = sort_findings(findings + ai_findings)
        except Exception as exc:
            logger.warning("AI validation failed: %s", exc)

    # 20-REQ-6.1: Apply auto-fixes when --fix is provided
    if fix:
        from agent_fox.spec.fixer import apply_fixes

        known_specs = _build_known_specs(discovered)
        fix_results = apply_fixes(findings, discovered, specs_dir, known_specs)
        if fix_results:
            # Print fix summary to stderr (20-REQ-6.6)
            summary = _format_fix_summary(fix_results)
            click.echo(summary, err=True)
            # Re-validate to get remaining findings (20-REQ-6.2)
            findings = validate_specs(specs_dir, discovered)
            if ai:
                try:
                    from agent_fox.spec.ai_validator import run_ai_validation

                    standard_model = resolve_model("STANDARD").model_id
                    ai_findings = asyncio.run(
                        run_ai_validation(
                            discovered, standard_model, specs_dir=specs_dir
                        )
                    )
                    findings = sort_findings(findings + ai_findings)
                except Exception as exc:
                    logger.warning("AI validation failed: %s", exc)

    # Output results
    _output_findings(findings, output_format)

    # Set exit code based on findings
    exit_code = compute_exit_code(findings)
    ctx.exit(exit_code)


def _output_findings(findings: list[Finding], output_format: str) -> None:
    """Output findings in the requested format."""
    if output_format == "json":
        click.echo(format_json(findings))
    elif output_format == "yaml":
        click.echo(format_yaml(findings))
    else:
        click.echo(format_table(findings), nl=False)
