"""CLI command for status report: agent-fox status.

Displays a progress dashboard showing task counts, token usage,
cost, and problem tasks.

Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3, 07-REQ-3.1,
              23-REQ-3.1, 23-REQ-8.1
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import click
from rich.console import Console

from agent_fox.cli import handle_agent_fox_errors
from agent_fox.reporting.formatters import (
    OutputFormat,
    get_formatter,
    write_output,
)
from agent_fox.reporting.status import generate_status

logger = logging.getLogger(__name__)

_AGENT_FOX_DIR = ".agent-fox"


@click.command("status")
@click.pass_context
@handle_agent_fox_errors
def status_cmd(ctx: click.Context) -> None:
    """Show execution progress dashboard."""
    json_mode = ctx.obj.get("json", False)
    project_root = Path.cwd()
    agent_dir = project_root / _AGENT_FOX_DIR
    state_path = agent_dir / "state.jsonl"
    plan_path = agent_dir / "plan.json"

    report = generate_status(state_path, plan_path)

    if json_mode:
        from agent_fox.cli.json_io import emit

        emit(asdict(report))
    else:
        console = Console()
        formatter = get_formatter(OutputFormat.TABLE, console=console)
        content = formatter.format_status(report)
        write_output(content, console=console)
