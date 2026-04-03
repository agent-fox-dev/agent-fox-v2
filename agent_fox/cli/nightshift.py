"""CLI command for the night-shift autonomous maintenance daemon.

Runs continuously, scanning the codebase on a timed schedule using both
static tooling and AI-powered agents to discover maintenance issues.
Each finding is reported as a platform issue. Issues labelled ``af:fix``
are automatically processed through the full archetype pipeline and a
pull request is opened per fix.

Requirements: 61-REQ-1.1, 61-REQ-1.2, 61-REQ-1.3, 61-REQ-1.4
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
@click.pass_context
def night_shift_cmd(ctx: click.Context, auto: bool) -> None:
    """Run the night-shift autonomous maintenance daemon.

    Polls for open issues labelled ``af:fix`` and runs hunt scans on
    configurable intervals.  Continues until interrupted with Ctrl-C
    (SIGINT) or until the configured cost limit is reached.

    Exit codes:
      0 -- clean shutdown (single SIGINT or cost limit reached)
      1 -- startup failure (platform not configured, etc.)
      130 -- immediate abort (double SIGINT)
    """
    from agent_fox.nightshift.engine import (
        NightShiftEngine,
        validate_night_shift_prerequisites,
    )
    from agent_fox.nightshift.platform_factory import create_platform

    config = ctx.obj["config"]
    project_root = Path.cwd()

    # 61-REQ-1.E1: Validate platform is configured before entering the loop.
    validate_night_shift_prerequisites(config)

    # Instantiate the platform from config (exits with code 1 on failure).
    platform = create_platform(config, project_root)

    engine = NightShiftEngine(config=config, platform=platform, auto_fix=auto)

    # --- Signal handling ----------------------------------------------------
    # First SIGINT/SIGTERM: graceful shutdown (current operation completes).
    # Second interrupt: immediate abort with exit code 130.
    # 61-REQ-1.3, 61-REQ-1.4
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
            engine.request_shutdown()
        else:
            logger.warning("Second interrupt received — aborting immediately")
            sys.exit(130)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    # -----------------------------------------------------------------------

    click.echo("Night-shift daemon starting. Press Ctrl-C to stop gracefully.")

    try:
        state = asyncio.run(engine.run())
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Night-shift engine failed: %s", exc, exc_info=True)
        click.echo(f"Error: night-shift engine failed: {exc}", err=True)
        sys.exit(1)
    finally:
        # Close platform connection if it supports it
        try:
            if hasattr(platform, "close"):
                asyncio.run(platform.close())
        except Exception:  # noqa: BLE001
            pass

    click.echo(
        f"Night-shift stopped. "
        f"Scans completed: {state.hunt_scans_completed}, "
        f"Issues fixed: {state.issues_fixed}, "
        f"Total cost: ${state.total_cost:.4f}"
    )
