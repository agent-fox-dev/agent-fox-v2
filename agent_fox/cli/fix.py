"""CLI command for error auto-fix: agent-fox fix.

Detects quality checks, runs them, clusters failures, generates fix
specifications, and runs coding sessions to resolve failures iteratively.

Requirements: 08-REQ-7.1, 08-REQ-7.2, 08-REQ-7.E1
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console

from agent_fox.fix.detector import detect_checks
from agent_fox.fix.loop import TerminationReason, run_fix_loop
from agent_fox.fix.report import render_fix_report

logger = logging.getLogger(__name__)


@click.command("fix")
@click.option(
    "--max-passes",
    type=int,
    default=3,
    help="Maximum number of fix passes (default: 3).",
)
@click.pass_context
def fix_cmd(ctx: click.Context, max_passes: int) -> None:
    """Detect and auto-fix quality check failures.

    Runs quality checks (tests, lint, type-check, build), groups failures
    by root cause, generates fix specifications, and runs coding sessions
    to resolve them. Iterates until all checks pass or max passes reached.
    """
    config = ctx.obj["config"]
    project_root = Path.cwd()
    console = Console()

    # 08-REQ-1.E1: Early exit if no quality checks detected
    checks = detect_checks(project_root)
    if not checks:
        click.echo(
            "Error: No quality checks detected in this project. "
            "Ensure configuration files (pyproject.toml, package.json, "
            "Makefile, Cargo.toml) are present.",
            err=True,
        )
        ctx.exit(1)
        return

    # 08-REQ-7.E1: Clamp max_passes (loop also clamps, but warn at CLI level)
    if max_passes < 1:
        logger.warning(
            "--max-passes=%d is invalid, clamping to 1", max_passes
        )
        max_passes = 1

    # Run the fix loop
    result = asyncio.run(
        run_fix_loop(
            project_root=project_root,
            config=config,
            max_passes=max_passes,
        )
    )

    # Render the report
    render_fix_report(result, console)

    # Exit code: 0 if all fixed, 1 otherwise
    if result.termination_reason != TerminationReason.ALL_FIXED:
        ctx.exit(1)
