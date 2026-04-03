"""Database dump utilities for exporting knowledge store tables.

Provides functions to discover tables, render individual tables as
Markdown, and export all tables in Markdown or JSON format.

Requirements: 49-REQ-3.1, 49-REQ-3.2, 49-REQ-3.4
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb

logger = logging.getLogger("agent_fox.knowledge.dump")

MAX_CELL_LENGTH = 120


def discover_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """List all user table names in the database.

    Args:
        conn: DuckDB connection.

    Returns:
        Sorted list of table names (excludes system tables).
    """
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    ).fetchall()
    return [row[0] for row in rows]


def _truncate_cell(value: str) -> str:
    """Truncate a cell value to MAX_CELL_LENGTH and escape pipes.

    Requirements: 49-REQ-3.4
    """
    text = str(value)
    # Escape pipe characters
    text = text.replace("|", "\\|")
    # Truncate if too long
    if len(text) > MAX_CELL_LENGTH:
        text = text[:117] + "..."
    return text


def dump_table_md(conn: duckdb.DuckDBPyConnection, table: str) -> str:
    """Render a single table as a Markdown table.

    Args:
        conn: DuckDB connection.
        table: Table name.

    Returns:
        Markdown string with header row, separator, and data rows.

    Requirements: 49-REQ-3.1, 49-REQ-3.4
    """
    # Get column names
    result = conn.execute(f'SELECT * FROM "{table}" LIMIT 0')
    columns = [desc[0] for desc in result.description]

    # Get all rows
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()

    lines: list[str] = []
    lines.append(f"## {table}")
    lines.append("")

    if not columns:
        lines.append("_Empty table._")
        lines.append("")
        return "\n".join(lines)

    # Header
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines.append(header)
    lines.append(separator)

    # Data rows
    for row in rows:
        cells = [_truncate_cell(str(v) if v is not None else "") for v in row]
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    return "\n".join(lines)


def dump_all_tables_md(conn: duckdb.DuckDBPyConnection, output: Path) -> int:
    """Write all tables to a Markdown file.

    Args:
        conn: DuckDB connection.
        output: Output file path.

    Returns:
        Number of tables written.

    Requirements: 49-REQ-3.1
    """
    tables = discover_tables(conn)
    output.parent.mkdir(parents=True, exist_ok=True)

    parts: list[str] = ["# Knowledge Store Dump", ""]
    for table in tables:
        parts.append(dump_table_md(conn, table))

    output.write_text("\n".join(parts), encoding="utf-8")
    return len(tables)


def dump_all_tables_json(conn: duckdb.DuckDBPyConnection, output: Path) -> int:
    """Write all tables to a JSON file.

    Args:
        conn: DuckDB connection.
        output: Output file path.

    Returns:
        Number of tables written.

    Requirements: 49-REQ-3.2
    """
    tables = discover_tables(conn)
    output.parent.mkdir(parents=True, exist_ok=True)

    tables_dict: dict[str, list[dict]] = {}
    for table in tables:
        result = conn.execute(f'SELECT * FROM "{table}"')
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        tables_dict[table] = [{col: _serialize_value(val) for col, val in zip(columns, row)} for row in rows]

    data = {
        "tables": tables_dict,
        "generated": datetime.now(UTC).isoformat(),
    }
    output.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return len(tables)


def _serialize_value(val: object) -> object:
    """Convert a DuckDB value to a JSON-safe Python type."""
    if val is None:
        return None
    if isinstance(val, (int, float, bool)):
        return val
    if isinstance(val, (list, tuple)):
        return [_serialize_value(v) for v in val]
    return str(val)
