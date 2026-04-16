"""CLI command for standup report: agent-fox standup.

Generates a daily activity report covering agent work, human
commits, file overlaps, and queued tasks.

Requirements: 07-REQ-2.1, 07-REQ-3.1, 07-REQ-3.4,
              23-REQ-3.2, 23-REQ-8.2
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import click
from rich.console import Console

from agent_fox.cli import handle_agent_fox_errors
from agent_fox.core.paths import DEFAULT_DB_PATH
from agent_fox.reporting.formatters import (
    OutputFormat,
    get_formatter,
    write_output,
)
from agent_fox.reporting.standup import generate_standup

logger = logging.getLogger(__name__)


@click.command("standup")
@click.option(
    "--hours",
    type=int,
    default=24,
    help="Reporting window in hours (default: 24)",
)
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="Write report to file instead of stdout",
)
@click.pass_context
@handle_agent_fox_errors
def standup_cmd(ctx: click.Context, hours: int, output: str | None) -> None:
    """Generate daily activity report."""
    json_mode = ctx.obj.get("json", False)
    project_root = Path.cwd()

    db_conn = None
    try:
        import duckdb

        if DEFAULT_DB_PATH.exists():
            db_conn = duckdb.connect(str(DEFAULT_DB_PATH), read_only=True)
    except Exception:
        logger.debug("DuckDB unavailable for standup", exc_info=True)

    try:
        report = generate_standup(
            repo_path=project_root,
            hours=hours,
            db_conn=db_conn,
        )
    finally:
        if db_conn is not None:
            db_conn.close()

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(asdict(report))
    else:
        console = Console()
        formatter = get_formatter(OutputFormat.TABLE, console=console)
        content = formatter.format_standup(report)

        output_path = Path(output) if output else None
        write_output(content, output_path=output_path, console=console)
