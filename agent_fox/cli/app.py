"""CLI entry point for agent-fox.

Defines the Click command group with global options (--version,
--verbose, --quiet), banner display when invoked without a subcommand,
and configuration loading. Subcommands are registered at module level.

Requirements: 01-REQ-1.1, 01-REQ-1.2, 01-REQ-1.3, 01-REQ-1.4,
              01-REQ-1.E1, 01-REQ-4.E1
"""

from __future__ import annotations

import logging

import click

from agent_fox import __version__
from agent_fox.core.config import ThemeConfig, load_config
from agent_fox.core.errors import AgentFoxError
from agent_fox.infra.logging import setup_logging
from agent_fox.ui.banner import render_banner
from agent_fox.ui.theme import create_theme

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--quiet", "-q", is_flag=True, help="Suppress info messages")
@click.pass_context
def main(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """agent-fox: autonomous coding-agent orchestrator."""
    ctx.ensure_object(dict)
    setup_logging(verbose=verbose, quiet=quiet)

    try:
        config = load_config()
    except AgentFoxError as exc:
        logger.debug("Config load failed", exc_info=True)
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    # 01-REQ-1.3: show banner when invoked without a subcommand
    if ctx.invoked_subcommand is None:
        theme_config = config.theme if config else ThemeConfig()
        theme = create_theme(theme_config)
        render_banner(theme)
        click.echo(ctx.get_help())


# Import and register subcommands
from agent_fox.cli.fix import fix_cmd  # noqa: E402
from agent_fox.cli.init import init_cmd  # noqa: E402
from agent_fox.cli.lint_spec import lint_spec  # noqa: E402
from agent_fox.cli.plan import plan_cmd  # noqa: E402

main.add_command(fix_cmd, name="fix")
main.add_command(init_cmd, name="init")
main.add_command(lint_spec, name="lint-spec")
main.add_command(plan_cmd, name="plan")
