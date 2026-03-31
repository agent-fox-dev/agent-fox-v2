"""CLI command for knowledge store export: agent-fox export.

Thin CLI handler that delegates to the backing module at
agent_fox.knowledge.export. Contains only argument parsing,
output formatting, and exit code mapping.

Requirements: 59-REQ-1.1, 59-REQ-1.2, 59-REQ-9.1, 59-REQ-9.2
"""

from __future__ import annotations

from pathlib import Path

import click
import duckdb

from agent_fox.core.paths import DEFAULT_DB_PATH
from agent_fox.knowledge.export import export_db, export_memory


@click.command("export")
@click.option("--memory", is_flag=True, help="Export memory summary")
@click.option("--db", is_flag=True, help="Export full database dump")
@click.pass_context
def export_cmd(ctx: click.Context, memory: bool, db: bool) -> None:
    """Export knowledge store data as Markdown or JSON."""
    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    if memory and db:
        click.echo(
            "Error: --memory and --db are mutually exclusive. Please specify only one.",
            err=True,
        )
        ctx.exit(1)
        return

    if not memory and not db:
        click.echo(
            "Error: must specify either --memory or --db.",
            err=True,
        )
        ctx.exit(1)
        return

    if not DEFAULT_DB_PATH.exists():
        click.echo(
            f"Error: knowledge store not found at {DEFAULT_DB_PATH}. "
            "Run 'agent-fox code' first.",
            err=True,
        )
        ctx.exit(1)
        return

    conn = duckdb.connect(str(DEFAULT_DB_PATH), read_only=True)

    try:
        if memory:
            output_path = (
                Path("docs/memory.json") if json_mode else Path("docs/memory.md")
            )
            result = export_memory(conn, output_path, json_mode=json_mode)
            if result.count == 0:
                click.echo(
                    "Warning: no facts found. "
                    f"Wrote empty output to {result.output_path}",
                    err=True,
                )
            else:
                click.echo(
                    f"Wrote {result.count} facts to {result.output_path}",
                    err=True,
                )
        elif db:
            output_path = (
                Path(".agent-fox/knowledge_dump.json")
                if json_mode
                else Path(".agent-fox/knowledge_dump.md")
            )
            result = export_db(conn, output_path, json_mode=json_mode)
            if result.count == 0:
                click.echo(
                    "Error: no tables found in knowledge store.",
                    err=True,
                )
                ctx.exit(1)
                return
            click.echo(
                f"Wrote {result.count} tables to {result.output_path}",
                err=True,
            )
    finally:
        conn.close()
