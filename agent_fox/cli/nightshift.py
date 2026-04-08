"""CLI command for the night-shift autonomous maintenance daemon.

Runs continuously, scanning the codebase on a timed schedule using both
static tooling and AI-powered agents to discover maintenance issues.
Each finding is reported as a platform issue. Issues labelled ``af:fix``
are automatically processed through the full archetype pipeline and a
pull request is opened per fix.

Requirements: 61-REQ-1.1, 61-REQ-1.2, 61-REQ-1.3, 61-REQ-1.4,
              85-REQ-2.1, 85-REQ-4.1, 85-REQ-6.1
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.command("night-shift")
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help="Auto-assign af:fix label to every issue created during hunt scans.",
)
@click.option(
    "--no-specs",
    is_flag=True,
    default=False,
    help="Disable the spec-executor stream.",
)
@click.option(
    "--no-fixes",
    is_flag=True,
    default=False,
    help="Disable the fix-pipeline stream.",
)
@click.option(
    "--no-hunts",
    is_flag=True,
    default=False,
    help="Disable the hunt-scan stream.",
)
@click.option(
    "--no-spec-gen",
    is_flag=True,
    default=False,
    help="Disable the spec-generator stream.",
)
@click.pass_context
def night_shift_cmd(
    ctx: click.Context,
    auto: bool,
    no_specs: bool,
    no_fixes: bool,
    no_hunts: bool,
    no_spec_gen: bool,
) -> None:
    """Run the night-shift autonomous maintenance daemon.

    Polls for open issues labelled ``af:fix`` and runs hunt scans on
    configurable intervals.  Continues until interrupted with Ctrl-C
    (SIGINT) or until the configured cost limit is reached.

    Exit codes:
      0 -- clean shutdown (single SIGINT or cost limit reached)
      1 -- startup failure (platform not configured, etc.)
      130 -- immediate abort (double SIGINT)
    """
    from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget
    from agent_fox.nightshift.engine import (
        NightShiftEngine,
        validate_night_shift_prerequisites,
    )
    from agent_fox.nightshift.platform_factory import create_platform
    from agent_fox.nightshift.streams import build_streams

    config = ctx.obj["config"]
    project_root = Path.cwd()

    # 61-REQ-1.E1: Validate platform is configured before entering the loop.
    validate_night_shift_prerequisites(config)

    # Instantiate the platform from config (exits with code 1 on failure).
    platform = create_platform(config, project_root)

    # --- ProgressDisplay setup (81-REQ-2.1) ---------------------------------
    from agent_fox.core.config import ThemeConfig
    from agent_fox.ui.display import create_theme
    from agent_fox.ui.progress import ProgressDisplay

    theme_config = getattr(config, "theme", None) or ThemeConfig()
    theme = create_theme(theme_config)
    quiet = ctx.obj.get("quiet", False) if isinstance(ctx.obj, dict) else False
    progress = ProgressDisplay(theme, quiet=quiet)
    progress.start()
    # -----------------------------------------------------------------------

    # Create the engine for business logic (fix pipeline, hunt scan).
    # Streams delegate to engine methods; the engine is NOT the lifecycle
    # manager.  DaemonRunner handles lifecycle, scheduling, and budget.
    engine = NightShiftEngine(
        config=config,
        platform=platform,
        auto_fix=auto,
        activity_callback=progress.activity_callback,
        task_callback=progress.task_callback,
        status_callback=progress.print_status,
    )

    # Shared cost budget (85-REQ-5.1, 85-REQ-5.2)
    max_cost = getattr(getattr(config, "orchestrator", None), "max_cost", None)
    budget = SharedBudget(max_cost=max_cost)

    # Build work streams with CLI flags (85-REQ-6.1)
    streams = build_streams(
        config,
        no_specs=no_specs,
        no_fixes=no_fixes,
        no_hunts=no_hunts,
        no_spec_gen=no_spec_gen,
        auto=auto,
        engine=engine,
        budget=budget,
        platform=platform,
        repo_root=project_root,
    )

    # Create the daemon runner (85-REQ-1.2, 85-REQ-2.1, 85-REQ-4.1)
    pid_path = project_root / ".agent-fox" / "daemon.pid"
    runner = DaemonRunner(
        config=config,
        platform=platform,
        streams=streams,
        budget=budget,
        pid_path=pid_path,
    )

    # --- Signal handling ----------------------------------------------------
    # First SIGINT/SIGTERM: graceful shutdown (current operation completes).
    # Second interrupt: immediate abort with exit code 130.
    # 61-REQ-1.3, 61-REQ-1.4, 85-REQ-2.2, 85-REQ-2.3
    _interrupt_count = 0

    def _signal_handler(signum: int, frame: object) -> None:
        nonlocal _interrupt_count
        _interrupt_count += 1
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        if _interrupt_count == 1:
            logger.info(
                "%s received — completing current operation then exiting (send another signal to abort immediately)",
                sig_name,
            )
            runner.request_shutdown()
        else:
            logger.warning("Second interrupt received — aborting immediately")
            sys.exit(130)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    # -----------------------------------------------------------------------

    click.echo("Night-shift daemon starting. Press Ctrl-C to stop gracefully.")

    try:
        daemon_state = asyncio.run(runner.run())
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Night-shift daemon failed: %s", exc, exc_info=True)
        click.echo(f"Error: night-shift daemon failed: {exc}", err=True)
        sys.exit(1)
    finally:
        progress.stop()
        # Close platform connection if it supports it
        try:
            if hasattr(platform, "close"):
                asyncio.run(platform.close())
        except Exception:  # noqa: BLE001
            pass

    # Pull detailed stats from the engine state (streams don't track these).
    click.echo(
        f"Night-shift stopped. "
        f"Scans completed: {engine.state.hunt_scans_completed}, "
        f"Issues fixed: {engine.state.issues_fixed}, "
        f"Specs generated: {engine.state.specs_generated}, "
        f"Total cost: ${daemon_state.total_cost:.4f}"
    )
