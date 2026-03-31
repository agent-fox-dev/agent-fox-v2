"""Backing module for knowledge store export.

Provides functions to export memory summaries and database dumps
that can be called from code without the CLI framework.

Requirements: 59-REQ-2.1, 59-REQ-2.2, 59-REQ-2.3
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from agent_fox.knowledge.dump import (
    discover_tables,
    dump_all_tables_json,
    dump_all_tables_md,
)
from agent_fox.knowledge.rendering import render_summary, render_summary_json


@dataclass(frozen=True)
class ExportResult:
    """Result of an export operation.

    Attributes:
        count: Number of items exported (facts for memory, tables for db).
        output_path: Path to the written output file.
    """

    count: int
    output_path: Path


def export_memory(
    conn: duckdb.DuckDBPyConnection,
    output_path: Path,
    *,
    json_mode: bool = False,
) -> ExportResult:
    """Export memory summary to a file.

    Args:
        conn: DuckDB connection to the knowledge store.
        output_path: Path to write the output file.
        json_mode: If True, write JSON format; otherwise Markdown.

    Returns:
        ExportResult with the fact count and output path.

    Requirements: 59-REQ-2.1, 59-REQ-2.3
    """
    if json_mode:
        count = render_summary_json(conn, output_path)
    else:
        render_summary(conn, output_path)
        from agent_fox.knowledge.store import read_all_facts

        facts = read_all_facts(conn)
        count = len(facts)

    return ExportResult(count=count, output_path=output_path)


def export_db(
    conn: duckdb.DuckDBPyConnection,
    output_path: Path,
    *,
    json_mode: bool = False,
) -> ExportResult:
    """Export all database tables to a file.

    Args:
        conn: DuckDB connection to the knowledge store.
        output_path: Path to write the output file.
        json_mode: If True, write JSON format; otherwise Markdown.

    Returns:
        ExportResult with the table count and output path.

    Requirements: 59-REQ-2.2, 59-REQ-2.3
    """
    tables = discover_tables(conn)
    if not tables:
        return ExportResult(count=0, output_path=output_path)

    if json_mode:
        table_count = dump_all_tables_json(conn, output_path)
    else:
        table_count = dump_all_tables_md(conn, output_path)

    return ExportResult(count=table_count, output_path=output_path)
