"""CLI entry point for agent-fox.

Defines the Click command group with global options (--version,
--verbose, --quiet, --json), banner display when invoked without a
subcommand, and configuration loading. Subcommands are registered at
module level.

Requirements: 01-REQ-1.1, 01-REQ-1.2, 01-REQ-1.3, 01-REQ-1.4,
              01-REQ-1.E1, 01-REQ-4.E1,
              23-REQ-1.1, 23-REQ-1.2, 23-REQ-2.1, 23-REQ-6.1,
              23-REQ-6.2, 23-REQ-6.E1
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from agent_fox import __version__
from agent_fox.core.config import ThemeConfig, load_config
from agent_fox.core.errors import AgentFoxError
from agent_fox.core.logging import setup_logging
from agent_fox.ui.banner import render_banner
from agent_fox.ui.theme import create_theme

logger = logging.getLogger(__name__)


class BannerGroup(click.Group):
    """Custom Click group with a top-level exception handler.

    Wraps subcommand dispatch so that any unhandled exception is caught,
    logged at DEBUG level, and reported as a user-friendly error message
    with exit code 1.  In JSON mode, errors are emitted as JSON envelopes
    to stdout instead of plain text to stderr.

    Requirements: 01-REQ-4.E1, 23-REQ-6.1, 23-REQ-6.2, 23-REQ-6.E1
    """

    def invoke(self, ctx: click.Context) -> None:
        try:
            super().invoke(ctx)
        except click.exceptions.Exit:
            raise
        except click.ClickException as exc:
            # In JSON mode, convert Click errors to JSON envelopes
            if ctx.obj and ctx.obj.get("json"):
                from agent_fox.cli.json_io import emit_error

                emit_error(str(exc))
                sys.exit(1)
            raise
        except AgentFoxError as exc:
            logger.debug("Unhandled AgentFoxError", exc_info=True)
            if ctx.obj and ctx.obj.get("json"):
                from agent_fox.cli.json_io import emit_error

                emit_error(str(exc))
                sys.exit(1)
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        except Exception as exc:
            logger.debug("Unexpected error", exc_info=True)
            if ctx.obj and ctx.obj.get("json"):
                from agent_fox.cli.json_io import emit_error

                emit_error(str(exc))
                sys.exit(1)
            click.echo(f"Error: unexpected error: {exc}", err=True)
            sys.exit(1)


@click.group(cls=BannerGroup, invoke_without_command=True)
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--quiet", "-q", is_flag=True, help="Suppress info messages")
@click.option(
    "--json",
    "json_mode",
    is_flag=True,
    default=False,
    help="Switch to structured JSON I/O mode",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool, quiet: bool, json_mode: bool) -> None:
    """agent-fox: autonomous coding-agent orchestrator."""
    ctx.ensure_object(dict)

    # 23-REQ-1.2: store JSON flag so every subcommand can access it
    ctx.obj["json"] = json_mode

    setup_logging(verbose=verbose, quiet=quiet)

    try:
        config = load_config(Path(".agent-fox/config.toml"))
    except AgentFoxError as exc:
        logger.debug("Config load failed", exc_info=True)
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error(str(exc))
            ctx.exit(1)
            return
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    # 14-REQ-4.1: render banner on every invocation (suppressed by --quiet)
    # 23-REQ-2.1: suppress banner in JSON mode
    if not json_mode:
        theme_config = config.theme if config else ThemeConfig()
        theme = create_theme(theme_config)
        render_banner(theme, config.models, quiet=quiet)

    # 01-REQ-1.3: show help when invoked without a subcommand
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Import and register subcommands
from agent_fox.cli.code import code_cmd  # noqa: E402
from agent_fox.cli.fix import fix_cmd  # noqa: E402
from agent_fox.cli.init import init_cmd  # noqa: E402
from agent_fox.cli.lint_spec import lint_spec  # noqa: E402
from agent_fox.cli.plan import plan_cmd  # noqa: E402
from agent_fox.cli.reset import reset_cmd  # noqa: E402
from agent_fox.cli.serve_tools import serve_tools_cmd  # noqa: E402
from agent_fox.cli.standup import standup_cmd  # noqa: E402
from agent_fox.cli.status import status_cmd  # noqa: E402

main.add_command(code_cmd, name="code")
main.add_command(fix_cmd, name="fix")
main.add_command(init_cmd, name="init")
main.add_command(lint_spec, name="lint-spec")
main.add_command(plan_cmd, name="plan")
main.add_command(reset_cmd, name="reset")
main.add_command(standup_cmd, name="standup")
main.add_command(serve_tools_cmd, name="serve-tools")
main.add_command(status_cmd, name="status")
