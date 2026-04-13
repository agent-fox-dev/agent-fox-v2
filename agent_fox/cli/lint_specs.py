"""CLI command for spec validation: agent-fox lint-specs.

Thin CLI handler that delegates to the backing module at
agent_fox.spec.lint. Contains only argument parsing, output
formatting, git operations, and exit code mapping.

Requirements: 59-REQ-1.3, 59-REQ-1.4, 59-REQ-9.1, 59-REQ-9.2
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import click

from agent_fox.core.errors import PlanError
from agent_fox.spec.lint import run_lint_specs
from agent_fox.spec.validators import (
    SEVERITY_ERROR,
    SEVERITY_HINT,
    SEVERITY_WARNING,
    Finding,
)

logger = logging.getLogger(__name__)


_SEVERITY_MARKERS = {
    SEVERITY_ERROR: "\u2717",  # ✗
    SEVERITY_WARNING: "\u26a0",  # ⚠
    SEVERITY_HINT: "\u2139",  # ℹ
}


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


def _format_table(findings: list[Finding]) -> str:
    """Render findings as compact text lines grouped by spec."""
    if not findings:
        return "No findings.\n"

    lines: list[str] = []
    lines.append(f"Spec Validation \u2014 {len(findings)} findings")

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


def _format_json(findings: list[Finding]) -> str:
    """Serialize findings as JSON."""
    data = {
        "findings": _findings_to_dicts(findings),
        "summary": _build_summary(findings),
    }
    return json.dumps(data, indent=2)


def _format_fix_summary(fix_results: list) -> str:
    """Format a summary of applied fixes for stderr output."""
    counts: Counter[str] = Counter()
    for r in fix_results:
        counts[r.rule] += 1

    parts = [f"{count} {rule}" for rule, count in sorted(counts.items())]
    return f"Fixed: {', '.join(parts)}"


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
    """Create and checkout a feature branch for lint-specs fixes."""
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


@click.command("lint-specs")
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
def lint_specs_cmd(ctx: click.Context, ai: bool, fix: bool, lint_all: bool) -> None:
    """Validate specification files for structural and quality problems."""
    json_mode = ctx.obj.get("json", False)
    output_format = "json" if json_mode else "table"
    specs_dir = Path(".specs")

    try:
        result = run_lint_specs(specs_dir, ai=ai, fix=fix, lint_all=lint_all)
    except PlanError as exc:
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    # Handle git operations for --fix (CLI-specific concern)
    if fix and result.fix_results:
        summary = _format_fix_summary(result.fix_results)
        click.echo(summary, err=True)

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
                "Warning: fixes applied but could not be committed to a branch. Changes are in your working tree.",
                err=True,
            )

    # Output results
    if output_format == "json":
        click.echo(_format_json(result.findings))
    else:
        click.echo(_format_table(result.findings), nl=False)

    ctx.exit(result.exit_code)
