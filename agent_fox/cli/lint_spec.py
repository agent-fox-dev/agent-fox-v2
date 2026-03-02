"""CLI command for spec validation: agent-fox lint-spec.

Requirements: 09-REQ-9.1, 09-REQ-9.2, 09-REQ-9.3, 09-REQ-9.4, 09-REQ-9.5,
              09-REQ-1.E1
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from agent_fox.core.errors import PlanError
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

# Severity display styles for Rich table output
_SEVERITY_STYLES = {
    SEVERITY_ERROR: "bold red",
    SEVERITY_WARNING: "yellow",
    SEVERITY_HINT: "dim cyan",
}


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


def format_table(findings: list[Finding], console: Console) -> None:
    """Render findings as a Rich table grouped by spec.

    Table columns: Severity, File, Rule, Message, Line
    Groups: one section per spec, with a header row.
    Footer: summary counts (N errors, N warnings, N hints).
    """
    if not findings:
        console.print("[green]No findings.[/green]")
        return

    # Group findings by spec name, preserving encounter order
    specs_seen: list[str] = []
    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        if f.spec_name not in grouped:
            specs_seen.append(f.spec_name)
            grouped[f.spec_name] = []
        grouped[f.spec_name].append(f)

    # Create the table
    table = Table(title="Specification Validation Results", show_lines=True)
    table.add_column("Severity", style="bold", width=8)
    table.add_column("File", width=20)
    table.add_column("Rule", width=28)
    table.add_column("Message")
    table.add_column("Line", width=6, justify="right")

    for spec_name in specs_seen:
        # Add spec header as a section row
        table.add_row(
            f"[bold underline]{spec_name}[/bold underline]",
            "", "", "", "",
        )
        for f in grouped[spec_name]:
            style = _SEVERITY_STYLES.get(f.severity, "")
            table.add_row(
                f"[{style}]{f.severity}[/{style}]",
                f.file,
                f.rule,
                f.message,
                str(f.line) if f.line is not None else "-",
            )

    console.print(table)

    # Summary line
    summary = _build_summary(findings)
    parts = []
    if summary["error"] > 0:
        parts.append(f"[bold red]{summary['error']} error(s)[/bold red]")
    if summary["warning"] > 0:
        parts.append(f"[yellow]{summary['warning']} warning(s)[/yellow]")
    if summary["hint"] > 0:
        parts.append(f"[dim cyan]{summary['hint']} hint(s)[/dim cyan]")
    console.print(f"\nSummary: {', '.join(parts)}")


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
        logger.warning(
            "PyYAML is not installed; falling back to JSON output."
        )
        return format_json(findings)

    data = {
        "findings": _findings_to_dicts(findings),
        "summary": _build_summary(findings),
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


@click.command("lint-spec")
@click.option(
    "--format", "output_format",
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
@click.pass_context
def lint_spec(ctx: click.Context, output_format: str, ai: bool) -> None:
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

            ai_findings = asyncio.run(
                run_ai_validation(discovered, "claude-sonnet-4-20250514")
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
        console = Console(file=sys.stdout)
        format_table(findings, console)
