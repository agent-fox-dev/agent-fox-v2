"""DuckDB CRUD for the errata_index table.

Provides registration, unregistration, and query of errata entries
that map spec names to errata document file paths.

Requirements: 115-REQ-5.1, 115-REQ-5.2, 115-REQ-5.3, 115-REQ-5.4,
              115-REQ-5.E1, 115-REQ-5.E2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrataEntry:
    """An errata entry mapping a spec to its errata document.

    Attributes:
        spec_name: The specification name (e.g. 'spec_28').
        file_path: Path to the errata document (e.g. 'docs/errata/28_fix.md').
        created_at: UTC timestamp when the entry was registered.
    """

    spec_name: str
    file_path: str
    created_at: datetime


def register_errata(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    file_path: str,
) -> ErrataEntry:
    """Register an errata entry. Idempotent (skips if already exists).

    Stores the ``(spec_name, file_path)`` pair in the errata_index table.
    If the entry already exists (same primary key), the insert is silently
    skipped and the existing entry is returned.

    The file referenced by ``file_path`` is NOT checked for existence on
    disk — it may exist in a different worktree or branch (115-REQ-5.E2).

    Args:
        conn: DuckDB connection with the errata_index table.
        spec_name: Spec name to associate the errata with.
        file_path: Path to the errata document.

    Returns:
        The registered (or existing) ErrataEntry.
    """
    conn.execute(
        "INSERT OR IGNORE INTO errata_index (spec_name, file_path, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        [spec_name, file_path],
    )

    # Query back to get the actual created_at (whether newly inserted or existing)
    row = conn.execute(
        "SELECT spec_name, file_path, created_at FROM errata_index WHERE spec_name = ? AND file_path = ?",
        [spec_name, file_path],
    ).fetchone()

    return ErrataEntry(spec_name=row[0], file_path=row[1], created_at=row[2])


def unregister_errata(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    file_path: str,
) -> bool:
    """Remove an errata entry.

    Args:
        conn: DuckDB connection with the errata_index table.
        spec_name: Spec name of the entry to remove.
        file_path: File path of the entry to remove.

    Returns:
        True if a row was deleted, False if the entry did not exist.
    """
    # Check existence first
    existing = conn.execute(
        "SELECT 1 FROM errata_index WHERE spec_name = ? AND file_path = ?",
        [spec_name, file_path],
    ).fetchone()

    if existing is None:
        return False

    conn.execute(
        "DELETE FROM errata_index WHERE spec_name = ? AND file_path = ?",
        [spec_name, file_path],
    )
    return True


def query_errata(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> list[str]:
    """Query errata entries for a spec.

    Returns formatted strings prefixed with ``[ERRATA] `` and including
    the file path. Returns an empty list if no errata exist for the spec
    (115-REQ-5.E1).

    Args:
        conn: DuckDB connection with the errata_index table.
        spec_name: Spec name to filter by.

    Returns:
        List of formatted strings prefixed with ``[ERRATA] ``.
    """
    rows = conn.execute(
        "SELECT file_path FROM errata_index WHERE spec_name = ? ORDER BY created_at",
        [spec_name],
    ).fetchall()
    return [f"[ERRATA] {row[0]}" for row in rows]
