"""CLI command for error auto-fix: agent-fox fix.

Detects quality checks, runs them, clusters failures, generates fix
specifications, and runs coding sessions to resolve failures iteratively.

With --auto: after all checks pass, iteratively analyze and improve
the codebase using an analyzer-coder-verifier pipeline.

Requirements: 08-REQ-7.1, 08-REQ-7.2, 08-REQ-7.E1,
              23-REQ-5.3, 23-REQ-5.E1,
              31-REQ-1.*, 31-REQ-2.*, 31-REQ-9.*, 31-REQ-10.*,
              76-REQ-1.*, 76-REQ-2.*, 76-REQ-3.*
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import click

from agent_fox.cli import json_io
from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.checks import detect_checks
from agent_fox.fix.events import CheckEvent, FixProgressEvent
from agent_fox.fix.fix import FixSessionRunner, TerminationReason, run_fix_loop
from agent_fox.fix.improve import ImproveResult, ImproveTermination, run_improve_loop
from agent_fox.fix.improve_report import build_combined_json, render_combined_report
from agent_fox.fix.report import render_fix_report
from agent_fox.fix.spec_gen import FixSpec
from agent_fox.session.session import run_session
from agent_fox.ui.display import create_theme, render_banner
from agent_fox.ui.progress import ProgressDisplay
from agent_fox.workspace import WorkspaceInfo

logger = logging.getLogger(__name__)


def _build_fix_session_runner(
    config: AgentFoxConfig,
    project_root: Path,
    activity_callback: Any | None = None,
) -> FixSessionRunner:
    """Build a session runner callable for the fix loop.

    Returns an async callable that takes a FixSpec and runs a
    coding session in the project root directory.

    Args:
        config: Agent Fox configuration.
        project_root: Root path of the project being fixed.
        activity_callback: Optional callback forwarded to run_session for
            real-time tool-use events (76-REQ-3.1).
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
            activity_callback=activity_callback,
        )
        from agent_fox.core.config import PricingConfig
        from agent_fox.core.models import calculate_cost, resolve_model

        model_entry = resolve_model(config.models.coding)
        pricing = getattr(config, "pricing", PricingConfig())
        return calculate_cost(
            outcome.input_tokens,
            outcome.output_tokens,
            model_entry.model_id,
            pricing,
        )

    return _run


def _build_improve_session_runner(
    config: AgentFoxConfig,
    project_root: Path,
    activity_callback: Any | None = None,
) -> Any:
    """Build a session runner callable for the improve loop.

    Returns an async callable: (system_prompt, task_prompt, tier) -> (cost, response).

    Args:
        config: Agent Fox configuration.
        project_root: Root path of the project being improved.
        activity_callback: Optional callback forwarded to run_session for
            real-time tool-use events (76-REQ-3.2).
    """

    async def _run(
        system_prompt: str, task_prompt: str, model_tier: str
    ) -> tuple[float, str]:
        workspace = WorkspaceInfo(
            path=project_root,
            branch="",
            spec_name="auto-improve",
            task_group=0,
        )
        outcome = await run_session(
            workspace=workspace,
            node_id=f"improve:{model_tier.lower()}",
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            config=config,
            activity_callback=activity_callback,
        )
        from agent_fox.core.config import PricingConfig
        from agent_fox.core.models import calculate_cost, resolve_model

        model_entry = resolve_model(config.models.coding)
        pricing = getattr(config, "pricing", PricingConfig())
        cost = calculate_cost(
            outcome.input_tokens,
            outcome.output_tokens,
            model_entry.model_id,
            pricing,
        )
        response = outcome.output if hasattr(outcome, "output") else ""
        return cost, response

    return _run


def _format_fix_milestone(event: FixProgressEvent) -> str:
    """Format a FixProgressEvent into a human-readable milestone string."""
    prefix = f"[{event.phase}] Pass {event.pass_number}/{event.max_passes}"
    stage = event.stage
    detail = event.detail

    if stage == "checks_start":
        return f"{prefix}: running checks"
    elif stage == "all_passed":
        return f"{prefix}: ✔ all checks passed"
    elif stage == "clusters_found":
        return f"{prefix}: {detail} cluster(s) found"
    elif stage == "session_start":
        return f"{prefix}: fixing cluster '{detail}'"
    elif stage == "session_done":
        return f"{prefix}: fix session complete"
    elif stage == "session_error":
        return f"{prefix}: ✘ session error for cluster '{detail}'"
    elif stage == "cost_limit":
        return f"{prefix}: ✘ cost limit reached"
    elif stage == "analyzer_start":
        return f"{prefix}: analyzing"
    elif stage == "analyzer_done":
        return f"{prefix}: analysis done"
    elif stage == "coder_start":
        return f"{prefix}: coding improvements"
    elif stage == "coder_done":
        return f"{prefix}: coding done"
    elif stage == "verifier_start":
        return f"{prefix}: verifying"
    elif stage == "verifier_pass":
        return f"{prefix}: ✔ verifier passed"
    elif stage == "verifier_fail":
        return f"{prefix}: ✘ verifier failed (rolling back)"
    elif stage == "converged":
        return f"{prefix}: converged — no further improvements"
    else:
        return f"{prefix}: {stage}" + (f" — {detail}" if detail else "")


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
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help="After repair, run iterative improvement passes.",
)
@click.option(
    "--improve-passes",
    type=int,
    default=3,
    help="Maximum improvement passes (default: 3, requires --auto).",
)
@click.pass_context
def fix_cmd(
    ctx: click.Context,
    max_passes: int,
    dry_run: bool,
    auto: bool,
    improve_passes: int,
) -> None:
    """Detect and auto-fix quality check failures.

    With --auto: after all checks pass, iteratively analyze and improve
    the codebase using an analyzer-coder-verifier pipeline.
    """
    config = ctx.obj["config"]
    json_mode: bool = ctx.obj.get("json", False)
    quiet: bool = ctx.obj.get("quiet", False)
    project_root = Path.cwd()

    # 31-REQ-1.3: --improve-passes without --auto is an error
    if not auto and improve_passes != 3:
        click.echo(
            "Error: --improve-passes requires --auto to be set.",
            err=True,
        )
        ctx.exit(1)
        return

    # 31-REQ-1.E1: Clamp --improve-passes to >= 1
    if auto and improve_passes < 1:
        logger.warning("--improve-passes=%d is invalid, clamping to 1", improve_passes)
        improve_passes = 1

    # 31-REQ-1.E2: --dry-run with --auto — Phase 2 will be skipped
    if auto and dry_run:
        logger.info("Dry-run mode is incompatible with Phase 2; Phase 2 will not run.")

    # 23-REQ-7.1: read stdin JSON when in JSON mode
    if json_mode:
        stdin_data = json_io.read_stdin()
        if max_passes == 3 and "max_passes" in stdin_data:  # default
            max_passes = int(stdin_data["max_passes"])
        if auto and improve_passes == 3 and "improve_passes" in stdin_data:
            improve_passes = int(stdin_data["improve_passes"])

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

    # -- Progress display setup (76-REQ-2.1, 76-REQ-2.3) --
    theme = create_theme(config.theme)
    progress = ProgressDisplay(theme, quiet=quiet or json_mode)

    # -- Banner (76-REQ-1.1, 76-REQ-1.2, 76-REQ-1.3) --
    if not (quiet or json_mode):
        render_banner(theme, config.models)

    # -- Callback handlers for progress display --
    def on_fix_progress(event: FixProgressEvent) -> None:
        """Convert FixProgressEvent to permanent milestone line on the console."""
        line = _format_fix_milestone(event)
        theme.console.print(line, highlight=False)

    def on_check(event: CheckEvent) -> None:
        """Update spinner for check start; print milestone line on check done."""
        if event.stage == "start":
            # Update spinner text to show the running check
            from agent_fox.ui.progress import ActivityEvent

            act = ActivityEvent(
                node_id="checks",
                tool_name="Bash",
                argument=event.check_name,
            )
            progress.on_activity(act)
        else:
            # Print a permanent line with the check result
            status = "✔" if event.passed else f"✘ (exit {event.exit_code})"
            theme.console.print(
                f"  check {event.check_name}: {status}", highlight=False
            )

    # Build session runner (None in dry-run mode)
    runner = (
        None
        if dry_run
        else _build_fix_session_runner(
            config, project_root, activity_callback=progress.activity_callback
        )
    )

    # -- Run Phase 1 and Phase 2 with display lifecycle (76-REQ-2.2, 76-REQ-2.E1) --
    progress.start()
    try:
        # Run the fix loop (Phase 1)
        try:
            result = asyncio.run(
                run_fix_loop(
                    project_root=project_root,
                    config=config,
                    max_passes=max_passes,
                    session_runner=runner,
                    progress_callback=on_fix_progress,
                    check_callback=on_check,
                )
            )
        except KeyboardInterrupt:
            # 23-REQ-5.E1: emit interrupted status in JSON mode
            if json_mode:
                json_io.emit_line({"status": "interrupted"})
            ctx.exit(130)
            return

        # -- Phase 2: Improve (31-REQ-1.1, 31-REQ-2.1) --
        improve_result: ImproveResult | None = None

        if (
            auto
            and not dry_run
            and result.termination_reason == TerminationReason.ALL_FIXED
        ):
            # 31-REQ-2.3: Compute remaining budget
            max_cost = getattr(config.orchestrator, "max_cost", None)
            remaining_budget = max_cost if max_cost is not None else None

            improve_runner = _build_improve_session_runner(
                config, project_root, activity_callback=progress.activity_callback
            )

            try:
                improve_result = asyncio.run(
                    run_improve_loop(
                        project_root=project_root,
                        config=config,
                        checks=checks,
                        max_passes=improve_passes,
                        remaining_budget=remaining_budget,
                        phase1_diff="",
                        session_runner=improve_runner,
                        progress_callback=on_fix_progress,
                    )
                )
            except KeyboardInterrupt:
                if json_mode:
                    json_io.emit_line({"status": "interrupted"})
                ctx.exit(130)
                return

    finally:
        # 76-REQ-2.2, 76-REQ-2.E1: always stop the display
        progress.stop()

    # -- Report --
    console = theme.console

    if improve_result is not None:
        # Combined Phase 1 + Phase 2 report
        total_cost = improve_result.total_cost
        if json_mode:
            json_io.emit_line(build_combined_json(result, improve_result, total_cost))
        else:
            render_combined_report(result, improve_result, total_cost, console)

        # 31-REQ-10.1, 31-REQ-10.2: Exit codes
        if improve_result.termination_reason == ImproveTermination.VERIFIER_FAIL:
            ctx.exit(1)
        # else exit 0 (successful improvement or natural convergence)
    else:
        # Phase 1 only report
        if json_mode:
            json_io.emit_line(
                {
                    "event": "complete",
                    "summary": {
                        "passes_completed": result.passes_completed,
                        "clusters_resolved": result.clusters_resolved,
                        "clusters_remaining": result.clusters_remaining,
                        "sessions_consumed": result.sessions_consumed,
                        "termination_reason": str(result.termination_reason),
                    },
                }
            )
        else:
            render_fix_report(result, console)

        # Exit code: 0 if all fixed, 1 otherwise
        if result.termination_reason != TerminationReason.ALL_FIXED:
            ctx.exit(1)
