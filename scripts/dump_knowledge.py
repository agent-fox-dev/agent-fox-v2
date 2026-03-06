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

TABLES_TO_DUMP: list[str] = [
    "schema_version",
    "memory_facts",
    "session_outcomes",
    "fact_causes",
    "tool_calls",
    "tool_errors",
]

OUTPUT_PATH = ".agent-fox/knowledge_dump.md"


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
        # Data rows
        for row in result:
            cells = [str(v) if v is not None else "" for v in row]
            lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Entry point: open DB, dump tables, write file, close DB."""
    config = KnowledgeConfig()
    db_path = Path(config.store_path)

    if not db_path.exists():
        print(f"Error: knowledge store not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    with KnowledgeDB(config) as db:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        sections = [f"# Knowledge Store Dump\n\nGenerated: {now}\n"]

        for table in TABLES_TO_DUMP:
            sections.append(dump_table(db.connection, table))

        output = Path(OUTPUT_PATH)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(sections))

    print(f"Dump written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
