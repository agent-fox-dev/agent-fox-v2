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

import duckdb  # noqa: F401

logger = logging.getLogger(__name__)


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


def insert_summary(
    conn: duckdb.DuckDBPyConnection,
    record: SummaryRecord,
) -> None:
    """Insert a session summary. No supersession -- append-only.

    Requirements: 119-REQ-1.1, 119-REQ-1.3
    """
    raise NotImplementedError("insert_summary not yet implemented")


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

    Requirements: 119-REQ-2.1, 119-REQ-2.3, 119-REQ-2.4, 119-REQ-2.5,
                  119-REQ-2.6
    """
    raise NotImplementedError("query_same_spec_summaries not yet implemented")


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
    raise NotImplementedError("query_cross_spec_summaries not yet implemented")
