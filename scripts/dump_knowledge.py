"""Dump the DuckDB knowledge store to a human-readable Markdown file.

Usage:
    python scripts/dump_knowledge.py

Output:
    .agent-fox/knowledge_dump.md
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.db import KnowledgeDB

OUTPUT_PATH = ".agent-fox/knowledge_dump.md"


def discover_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Return all table names in the database, sorted alphabetically."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    return [row[0] for row in rows]


def dump_table(conn: duckdb.DuckDBPyConnection, table: str) -> str:
    """Query all rows from *table* and return a formatted Markdown section."""
    result = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
    columns = [desc[0] for desc in conn.description]
    row_count = len(result)
    label = "row" if row_count == 1 else "rows"

    lines: list[str] = [f"## {table} ({row_count} {label})", ""]

    if row_count == 0:
        lines.append("No rows.")
    else:
        # Header
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        # Data rows — truncate long cells for readability
        for row in result:
            cells = []
            for v in row:
                cell = str(v) if v is not None else ""
                if len(cell) > 120:
                    cell = cell[:117] + "..."
                # Escape pipe characters inside cell values
                cell = cell.replace("|", "\\|")
                cells.append(cell)
            lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Entry point: open DB, discover tables, dump them all, write file."""
    config = KnowledgeConfig()
    db_path = Path(config.store_path)

    if not db_path.exists():
        print(f"Error: knowledge store not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    with KnowledgeDB(config) as db:
        tables = discover_tables(db.connection)

        if not tables:
            print("No tables found in knowledge store.", file=sys.stderr)
            sys.exit(1)

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        sections = [
            f"# Knowledge Store Dump\n\nGenerated: {now}\n\nTables: {len(tables)}\n"
        ]

        for table in tables:
            sections.append(dump_table(db.connection, table))

        output = Path(OUTPUT_PATH)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(sections))

    print(f"Dump written to {OUTPUT_PATH} ({len(tables)} tables)")


if __name__ == "__main__":
    main()
