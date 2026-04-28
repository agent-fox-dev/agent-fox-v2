"""CRUD operations for session_summaries table.

Provides insert, same-spec query, and cross-spec query for session
summaries.  Follows the same patterns as review_store.py: dataclass for
records, standalone functions for CRUD, DuckDB connection passed as the
first argument.

Requirements: 119-REQ-1.1, 119-REQ-1.3, 119-REQ-2.1, 119-REQ-2.3,
              119-REQ-2.4, 119-REQ-2.5, 119-REQ-2.6, 119-REQ-3.1,
              119-REQ-3.3, 119-REQ-3.4, 119-REQ-3.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb

logger = logging.getLogger(__name__)

# Column order used for SELECT queries and row conversion.
_SUMMARY_COLS = (
    "id, node_id, run_id, spec_name, task_group, "
    "archetype, attempt, summary, created_at"
)


@dataclass(frozen=True)
class SummaryRecord:
    """A stored session summary."""

    id: str  # UUID
    node_id: str  # e.g. "01_audit_hub:3"
    run_id: str  # Run identifier
    spec_name: str  # e.g. "01_audit_hub"
    task_group: str  # e.g. "3"
    archetype: str  # e.g. "coder"
    attempt: int  # 1-indexed
    summary: str  # The natural-language summary text
    created_at: str  # ISO 8601 timestamp


def _row_to_summary_record(row: tuple) -> SummaryRecord:
    """Convert a database row tuple to a SummaryRecord."""
    return SummaryRecord(
        id=str(row[0]),
        node_id=str(row[1]),
        run_id=str(row[2]),
        spec_name=str(row[3]),
        task_group=str(row[4]),
        archetype=str(row[5]),
        attempt=int(row[6]),
        summary=str(row[7]),
        created_at=str(row[8]),
    )


def insert_summary(
    conn: duckdb.DuckDBPyConnection,
    record: SummaryRecord,
) -> None:
    """Insert a session summary. No supersession -- append-only.

    Requirements: 119-REQ-1.1, 119-REQ-1.3
    """
    conn.execute(
        f"INSERT INTO session_summaries ({_SUMMARY_COLS}) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            record.id,
            record.node_id,
            record.run_id,
            record.spec_name,
            record.task_group,
            record.archetype,
            record.attempt,
            record.summary,
            record.created_at,
        ],
    )


def query_same_spec_summaries(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str,
    run_id: str,
    max_items: int = 5,
) -> list[SummaryRecord]:
    """Return coder summaries from prior task groups in the same spec/run.

    Filters: archetype='coder', task_group < current, latest attempt per group.
    Sorts by task_group ASC. Caps at max_items.

    Uses CAST(task_group AS INTEGER) for numeric comparison to avoid
    lexicographic ordering issues with VARCHAR (e.g. '2' > '10').

    Requirements: 119-REQ-2.1, 119-REQ-2.3, 119-REQ-2.4, 119-REQ-2.5,
                  119-REQ-2.6
    """
    try:
        rows = conn.execute(
            """
            WITH ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY task_group
                           ORDER BY attempt DESC
                       ) AS rn
                FROM session_summaries
                WHERE spec_name = ?
                  AND run_id = ?
                  AND archetype = 'coder'
                  AND CAST(task_group AS INTEGER) < CAST(? AS INTEGER)
            )
            SELECT id, node_id, run_id, spec_name, task_group,
                   archetype, attempt, summary, created_at
            FROM ranked
            WHERE rn = 1
            ORDER BY CAST(task_group AS INTEGER) ASC
            LIMIT ?
            """,
            [spec_name, run_id, task_group, max_items],
        ).fetchall()
    except duckdb.CatalogException:
        logger.debug(
            "session_summaries table not found; returning empty same-spec list"
        )
        return []
    except Exception:
        logger.debug(
            "Could not query same-spec summaries for %s", spec_name,
            exc_info=True,
        )
        return []

    return [_row_to_summary_record(row) for row in rows]


def query_cross_spec_summaries(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    run_id: str,
    max_items: int = 3,
) -> list[SummaryRecord]:
    """Return coder summaries from other specs in the same run.

    Filters: archetype='coder', spec_name != current, latest attempt per
    (spec, task_group). Sorts by created_at DESC. Caps at max_items.

    Requirements: 119-REQ-3.1, 119-REQ-3.3, 119-REQ-3.4, 119-REQ-3.5
    """
    try:
        rows = conn.execute(
            """
            WITH ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY spec_name, task_group
                           ORDER BY attempt DESC
                       ) AS rn
                FROM session_summaries
                WHERE run_id = ?
                  AND archetype = 'coder'
                  AND spec_name != ?
            )
            SELECT id, node_id, run_id, spec_name, task_group,
                   archetype, attempt, summary, created_at
            FROM ranked
            WHERE rn = 1
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [run_id, spec_name, max_items],
        ).fetchall()
    except duckdb.CatalogException:
        logger.debug(
            "session_summaries table not found; returning empty cross-spec list"
        )
        return []
    except Exception:
        logger.debug(
            "Could not query cross-spec summaries for %s", spec_name,
            exc_info=True,
        )
        return []

    return [_row_to_summary_record(row) for row in rows]


def truncate_for_audit(summary_text: str, max_len: int = 2000) -> str:
    """Truncate summary text for audit event payload.

    If *summary_text* exceeds *max_len* characters, truncate and append
    a ``...`` marker.  Returns the original text unchanged when it fits.

    Requirements: 119-REQ-4.E1
    """
    if len(summary_text) <= max_len:
        return summary_text
    return summary_text[:max_len] + "..."
