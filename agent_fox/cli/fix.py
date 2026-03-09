"""CLI command for error auto-fix: agent-fox fix.

Detects quality checks, runs them, clusters failures, generates fix
specifications, and runs coding sessions to resolve failures iteratively.

Requirements: 08-REQ-7.1, 08-REQ-7.2, 08-REQ-7.E1,
              23-REQ-5.3, 23-REQ-5.E1
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console

from agent_fox.cli import json_io
from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.checks import detect_checks
from agent_fox.fix.fix import TerminationReason, run_fix_loop
from agent_fox.fix.report import render_fix_report
from agent_fox.fix.spec_gen import FixSpec
from agent_fox.session.session import run_session
from agent_fox.workspace.workspace import WorkspaceInfo

logger = logging.getLogger(__name__)


def _build_fix_session_runner(
    config: AgentFoxConfig, project_root: Path
) -> TerminationReason | None:
    """Build a session runner callable for the fix loop.

    Returns an async callable that takes a FixSpec and runs a
    coding session in the project root directory.
    """

    async def _run(fix_spec: FixSpec) -> float:
        workspace = WorkspaceInfo(
            path=project_root,
            branch="",
            spec_name=f"fix:{fix_spec.cluster_label}",
            task_group=0,
        )
        system_prompt = (
            "You are an auto-fix coding agent. Fix the quality check "
            "failures described below. Make minimal, targeted changes."
        )
        outcome = await run_session(
            workspace=workspace,
            node_id=f"fix:{fix_spec.cluster_label}",
            system_prompt=system_prompt,
            task_prompt=fix_spec.task_prompt,
            config=config,
        )
        from agent_fox.core.models import calculate_cost, resolve_model

        model_entry = resolve_model(config.models.coding)
        return calculate_cost(outcome.input_tokens, outcome.output_tokens, model_entry)

    return _run  # type: ignore[return-value]


@click.command("fix")
@click.option(
    "--max-passes",
    type=int,
    default=3,
    help="Maximum number of fix passes (default: 3).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Generate fix specs only, do not run sessions.",
)
@click.pass_context
def fix_cmd(ctx: click.Context, max_passes: int, dry_run: bool) -> None:
    """Detect and auto-fix quality check failures.

    Runs quality checks (tests, lint, type-check, build), groups failures
    by root cause, generates fix specifications, and runs coding sessions
    to resolve them. Iterates until all checks pass or max passes reached.
    """
    config = ctx.obj["config"]
    json_mode: bool = ctx.obj.get("json", False)
    project_root = Path.cwd()
    console = Console()

    # 23-REQ-7.1: read stdin JSON when in JSON mode
    if json_mode:
        stdin_data = json_io.read_stdin()
        if max_passes == 3 and "max_passes" in stdin_data:  # default
            max_passes = int(stdin_data["max_passes"])

    # 08-REQ-1.E1: Early exit if no quality checks detected
    checks = detect_checks(project_root)
    if not checks:
        if json_mode:
            json_io.emit_error(
                "No quality checks detected in this project. "
                "Ensure configuration files (pyproject.toml, package.json, "
                "Makefile, Cargo.toml) are present."
            )
            ctx.exit(1)
            return
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
        logger.warning("--max-passes=%d is invalid, clamping to 1", max_passes)
        max_passes = 1

    # Build session runner (None in dry-run mode)
    runner = None if dry_run else _build_fix_session_runner(config, project_root)

    # Run the fix loop
    try:
        result = asyncio.run(
            run_fix_loop(
                project_root=project_root,
                config=config,
                max_passes=max_passes,
                session_runner=runner,
            )
        )
    except KeyboardInterrupt:
        # 23-REQ-5.E1: emit interrupted status in JSON mode
        if json_mode:
            json_io.emit_line({"status": "interrupted"})
        ctx.exit(130)
        return

    # 23-REQ-5.3: emit JSONL in JSON mode
    if json_mode:
        json_io.emit_line({
            "event": "complete",
            "summary": {
                "passes_completed": result.passes_completed,
                "clusters_resolved": result.clusters_resolved,
                "clusters_remaining": result.clusters_remaining,
                "sessions_consumed": result.sessions_consumed,
                "termination_reason": str(result.termination_reason),
            },
        })
    else:
        # Render the report
        render_fix_report(result, console)

    # Exit code: 0 if all fixed, 1 otherwise
    if result.termination_reason != TerminationReason.ALL_FIXED:
        ctx.exit(1)
