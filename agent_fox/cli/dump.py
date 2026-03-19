"""CLI command for knowledge store export: agent-fox dump.

Provides two mutually exclusive export modes: memory summary (--memory)
and full database dump (--db). Supports Markdown and JSON output formats
via the global --json flag.

Requirements: 49-REQ-1.1, 49-REQ-1.2, 49-REQ-1.E1, 49-REQ-2.1,
              49-REQ-2.3, 49-REQ-3.3, 49-REQ-3.E1, 49-REQ-4.1, 49-REQ-5.1
"""

from __future__ import annotations

from pathlib import Path

import click
import duckdb

from agent_fox.cli.paths import DEFAULT_DB_PATH
from agent_fox.knowledge.dump import (
    discover_tables,
    dump_all_tables_json,
    dump_all_tables_md,
)
from agent_fox.knowledge.rendering import render_summary, render_summary_json


@click.command("dump")
@click.option("--memory", is_flag=True, help="Export memory summary")
@click.option("--db", is_flag=True, help="Export full database dump")
@click.pass_context
def dump_cmd(ctx: click.Context, memory: bool, db: bool) -> None:
    """Export knowledge store data as Markdown or JSON."""
    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    # 49-REQ-1.E1: mutual exclusivity
    if memory and db:
        click.echo(
            "Error: --memory and --db are mutually exclusive. Please specify only one.",
            err=True,
        )
        ctx.exit(1)
        return

    # 49-REQ-1.2: at least one flag required
    if not memory and not db:
        click.echo(
            "Error: must specify either --memory or --db.",
            err=True,
        )
        ctx.exit(1)
        return

    # 49-REQ-4.1: database must exist
    if not DEFAULT_DB_PATH.exists():
        click.echo(
            f"Error: knowledge store not found at {DEFAULT_DB_PATH}. "
            "Run 'agent-fox code' first.",
            err=True,
        )
        ctx.exit(1)
        return

    # 49-REQ-5.1: read-only access
    conn = duckdb.connect(str(DEFAULT_DB_PATH), read_only=True)

    try:
        if memory:
            _export_memory(conn, json_mode)
        elif db:
            _export_db(ctx, conn, json_mode)
    finally:
        conn.close()


def _export_memory(conn: duckdb.DuckDBPyConnection, json_mode: bool) -> None:
    """Export memory summary to Markdown or JSON.

    Requirements: 49-REQ-2.1, 49-REQ-2.2, 49-REQ-2.3, 49-REQ-2.E1
    """
    if json_mode:
        output_path = Path("docs/memory.json")
        count = render_summary_json(conn, output_path)
        if count == 0:
            click.echo(
                f"Warning: no facts found. Wrote empty JSON to {output_path}",
                err=True,
            )
        else:
            click.echo(
                f"Wrote {count} facts to {output_path}",
                err=True,
            )
    else:
        output_path = Path("docs/memory.md")
        render_summary(conn, output_path)
        # Count facts for the confirmation message
        from agent_fox.knowledge.store import read_all_facts

        facts = read_all_facts(conn)
        count = len(facts)
        if count == 0:
            click.echo(
                f"Warning: no facts found. Wrote empty memory to {output_path}",
                err=True,
            )
        else:
            click.echo(
                f"Wrote {count} facts to {output_path}",
                err=True,
            )


def _export_db(
    ctx: click.Context, conn: duckdb.DuckDBPyConnection, json_mode: bool
) -> None:
    """Export full database dump to Markdown or JSON.

    Requirements: 49-REQ-3.1, 49-REQ-3.2, 49-REQ-3.3, 49-REQ-3.E1
    """
    # 49-REQ-3.E1: check for tables
    tables = discover_tables(conn)
    if not tables:
        click.echo("Error: no tables found in knowledge store.", err=True)
        ctx.exit(1)
        return

    if json_mode:
        output_path = Path(".agent-fox/knowledge_dump.json")
        table_count = dump_all_tables_json(conn, output_path)
        click.echo(
            f"Wrote {table_count} tables to {output_path}",
            err=True,
        )
    else:
        output_path = Path(".agent-fox/knowledge_dump.md")
        table_count = dump_all_tables_md(conn, output_path)
        click.echo(
            f"Wrote {table_count} tables to {output_path}",
            err=True,
        )
