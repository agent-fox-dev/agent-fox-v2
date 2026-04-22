"""Unit tests for errata store CRUD operations.

Test Spec: TS-115-16, TS-115-17, TS-115-18, TS-115-19
Requirements: 115-REQ-5.1, 115-REQ-5.2, 115-REQ-5.3, 115-REQ-5.4
"""

from __future__ import annotations

from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.knowledge.errata_store import (
    ErrataEntry,
    query_errata,
    register_errata,
    unregister_errata,
)
from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# DDL for errata_index table (matches migration v17 design)
# ---------------------------------------------------------------------------

_ERRATA_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS errata_index (
    spec_name  VARCHAR NOT NULL,
    file_path  VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (spec_name, file_path)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def errata_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full schema + errata_index table for errata store tests."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    conn.execute(_ERRATA_INDEX_DDL)
    yield conn
    conn.close()


# ===========================================================================
# TS-115-16: Errata Storage
# ===========================================================================


class TestErrataStorage:
    """Verify errata entries stored as (spec_name, file_path) pairs.

    Requirements: 115-REQ-5.1
    """

    def test_register_stores_entry(self, errata_conn) -> None:
        entry = register_errata(
            errata_conn,
            "spec_28",
            "docs/errata/28_github_issue_rest_api.md",
        )

        row = errata_conn.execute(
            "SELECT spec_name, file_path FROM errata_index "
            "WHERE spec_name = 'spec_28'"
        ).fetchone()

        assert row is not None
        assert row[0] == "spec_28"
        assert row[1] == "docs/errata/28_github_issue_rest_api.md"
        assert entry.spec_name == "spec_28"
        assert entry.file_path == "docs/errata/28_github_issue_rest_api.md"


# ===========================================================================
# TS-115-17: Errata Retrieval
# ===========================================================================


class TestErrataRetrieval:
    """Verify retrieve() includes errata for the given spec.

    Requirements: 115-REQ-5.2
    """

    def test_query_returns_errata(self, errata_conn) -> None:
        register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )

        result = query_errata(errata_conn, "spec_28")

        assert len(result) == 1
        assert result[0].startswith("[ERRATA]")


# ===========================================================================
# TS-115-18: Errata Prefix
# ===========================================================================


class TestErrataPrefix:
    """Verify each errata string has [ERRATA] prefix and includes file path.

    Requirements: 115-REQ-5.3
    """

    def test_prefix_and_path(self, errata_conn) -> None:
        register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )

        result = query_errata(errata_conn, "spec_28")

        assert len(result) == 1
        assert result[0].startswith("[ERRATA] ")
        assert "docs/errata/28_fix.md" in result[0]


# ===========================================================================
# TS-115-19: Register and Unregister Errata
# ===========================================================================


class TestRegisterUnregister:
    """Verify errata can be registered and unregistered, and register returns
    the registered entry.

    Requirements: 115-REQ-5.4
    """

    def test_register_returns_entry(self, errata_conn) -> None:
        entry = register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )

        assert isinstance(entry, ErrataEntry)
        assert entry.spec_name == "spec_28"
        assert entry.file_path == "docs/errata/28_fix.md"

    def test_register_then_query(self, errata_conn) -> None:
        register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )

        rows = errata_conn.execute(
            "SELECT * FROM errata_index WHERE spec_name = 'spec_28'"
        ).fetchall()
        assert len(rows) == 1

    def test_unregister_removes_entry(self, errata_conn) -> None:
        register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )

        removed = unregister_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )
        assert removed is True

        rows = errata_conn.execute(
            "SELECT * FROM errata_index WHERE spec_name = 'spec_28'"
        ).fetchall()
        assert len(rows) == 0

    def test_unregister_nonexistent_returns_false(self, errata_conn) -> None:
        removed = unregister_errata(
            errata_conn, "spec_99", "docs/errata/99_nonexistent.md"
        )
        assert removed is False

    def test_register_idempotent(self, errata_conn) -> None:
        """Registering the same entry twice should not raise."""
        entry1 = register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )
        entry2 = register_errata(
            errata_conn, "spec_28", "docs/errata/28_fix.md"
        )

        rows = errata_conn.execute(
            "SELECT * FROM errata_index WHERE spec_name = 'spec_28'"
        ).fetchall()
        assert len(rows) == 1
        # created_at must be stable across idempotent re-registration
        assert entry1.created_at == entry2.created_at


# ===========================================================================
# AC-2: RuntimeError on missing row after INSERT OR IGNORE
# ===========================================================================


class TestRegisterNoneGuard:
    """Verify RuntimeError is raised when fetchone() returns None after INSERT.

    Guards against None-dereference on line 69 (issue #515).
    """

    def test_fetchone_none_raises_runtime_error(self, errata_conn) -> None:
        """When the SELECT after INSERT returns no row, a RuntimeError is raised."""
        # DuckDB's execute() is read-only on the C extension object, so we
        # wrap the real connection in a MagicMock that delegates the first
        # call (INSERT OR IGNORE) to the real connection and returns a fake
        # cursor whose fetchone() returns None for the second call (SELECT).
        fake_result = MagicMock()
        fake_result.fetchone.return_value = None

        call_count = 0
        original_execute = errata_conn.execute

        def fake_execute(sql, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_execute(sql, params) if params is not None else original_execute(sql)
            return fake_result

        mock_conn = MagicMock(spec=duckdb.DuckDBPyConnection)
        mock_conn.execute.side_effect = fake_execute

        with pytest.raises(RuntimeError, match="no row found"):
            register_errata(mock_conn, "spec_28", "docs/errata/28_fix.md")
