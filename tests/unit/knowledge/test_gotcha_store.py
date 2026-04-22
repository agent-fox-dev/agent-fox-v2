"""Unit tests for gotcha store CRUD operations.

Test Spec: TS-115-7, TS-115-9, TS-115-10, TS-115-11, TS-115-12,
           TS-115-23, TS-115-24, TS-115-E2
Requirements: 115-REQ-2.4, 115-REQ-2.E1, 115-REQ-3.1, 115-REQ-3.2,
              115-REQ-3.3, 115-REQ-3.4, 115-REQ-7.1, 115-REQ-7.2
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from agent_fox.knowledge.gotcha_extraction import GotchaCandidate
from agent_fox.knowledge.gotcha_store import (
    query_gotchas,
    store_gotchas,
)

from agent_fox.knowledge.migrations import apply_pending_migrations
from tests.unit.knowledge.conftest import SCHEMA_DDL

# ---------------------------------------------------------------------------
# DDL for gotchas table (matches migration v17 design)
# ---------------------------------------------------------------------------

_GOTCHAS_DDL = """
CREATE TABLE IF NOT EXISTS gotchas (
    id           VARCHAR PRIMARY KEY,
    spec_name    VARCHAR NOT NULL,
    category     VARCHAR NOT NULL DEFAULT 'gotcha',
    text         VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    session_id   VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gotcha_conn() -> duckdb.DuckDBPyConnection:
    """DuckDB with full schema + gotchas table for store tests."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    conn.execute(_GOTCHAS_DDL)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_gotcha_raw(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    text: str,
    *,
    days_ago: int = 0,
    session_id: str = "s1",
) -> None:
    """Insert a gotcha directly into the DB for test setup."""
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    created_at = datetime.now(UTC) - timedelta(days=days_ago)
    conn.execute(
        "INSERT INTO gotchas (id, spec_name, category, text, content_hash, "
        "session_id, created_at) VALUES (?, ?, 'gotcha', ?, ?, ?, ?)",
        [str(uuid.uuid4()), spec_name, text, content_hash, session_id, created_at],
    )


def _make_candidate(text: str) -> GotchaCandidate:
    """Create a GotchaCandidate with computed content hash."""
    normalized = " ".join(text.lower().split())
    content_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return GotchaCandidate(text=text, content_hash=content_hash)


# ===========================================================================
# TS-115-7: Gotcha Record Fields
# ===========================================================================


class TestRecordFields:
    """Verify stored gotcha has all required fields.

    Requirements: 115-REQ-2.4
    """

    def test_stored_gotcha_has_all_fields(self, gotcha_conn) -> None:
        candidates = [_make_candidate("DuckDB ON CONFLICT needs explicit column list")]
        store_gotchas(gotcha_conn, "spec_01", "session-1", candidates)

        row = gotcha_conn.execute(
            "SELECT id, spec_name, category, text, content_hash, session_id, "
            "created_at FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchone()

        assert row is not None
        assert row[1] == "spec_01"  # spec_name
        assert row[2] == "gotcha"  # category
        assert row[3] is not None and len(row[3]) > 0  # text
        assert row[4] is not None and len(row[4]) == 64  # SHA-256 hex
        assert row[5] == "session-1"  # session_id
        assert row[6] is not None  # created_at


# ===========================================================================
# TS-115-9: Gotcha Retrieval by Spec
# ===========================================================================


class TestQueryBySpec:
    """Verify retrieve returns gotchas filtered by spec_name, ordered by recency.

    Requirements: 115-REQ-3.1
    """

    def test_query_by_spec_filters_correctly(self, gotcha_conn) -> None:
        _insert_gotcha_raw(gotcha_conn, "spec_01", "Gotcha A", days_ago=2)
        _insert_gotcha_raw(gotcha_conn, "spec_01", "Gotcha B", days_ago=1)
        _insert_gotcha_raw(gotcha_conn, "spec_01", "Gotcha C", days_ago=0)
        _insert_gotcha_raw(gotcha_conn, "spec_02", "Other spec gotcha")
        _insert_gotcha_raw(gotcha_conn, "spec_02", "Other spec gotcha 2")

        result = query_gotchas(gotcha_conn, "spec_01", ttl_days=90, limit=5)

        assert len(result) == 3
        # All should be for spec_01 only, most recent first
        for g in result:
            assert g.startswith("[GOTCHA]")


# ===========================================================================
# TS-115-10: Gotcha TTL Exclusion
# ===========================================================================


class TestTTLExclusion:
    """Verify gotchas older than TTL are excluded from retrieval.

    Requirements: 115-REQ-3.2
    """

    def test_old_gotcha_excluded(self, gotcha_conn) -> None:
        _insert_gotcha_raw(
            gotcha_conn, "spec_01", "Old gotcha", days_ago=100
        )
        _insert_gotcha_raw(
            gotcha_conn, "spec_01", "Recent gotcha", days_ago=10
        )

        result = query_gotchas(gotcha_conn, "spec_01", ttl_days=90, limit=5)

        assert len(result) == 1
        assert "Recent gotcha" in result[0]


# ===========================================================================
# TS-115-11: Max 5 Gotchas Per Retrieval
# ===========================================================================


class TestMaxFiveGotchas:
    """Verify at most 5 gotchas are returned.

    Requirements: 115-REQ-3.3
    """

    def test_max_five(self, gotcha_conn) -> None:
        for i in range(8):
            _insert_gotcha_raw(gotcha_conn, "spec_01", f"Gotcha {i}")

        result = query_gotchas(gotcha_conn, "spec_01", ttl_days=90, limit=5)

        assert len(result) <= 5


# ===========================================================================
# TS-115-12: Gotcha Prefix
# ===========================================================================


class TestGotchaPrefix:
    """Verify each gotcha string is prefixed with [GOTCHA] .

    Requirements: 115-REQ-3.4
    """

    def test_gotcha_prefix(self, gotcha_conn) -> None:
        _insert_gotcha_raw(gotcha_conn, "spec_01", "Some gotcha text")

        result = query_gotchas(gotcha_conn, "spec_01", ttl_days=90, limit=5)

        assert len(result) == 1
        assert result[0].startswith("[GOTCHA] ")


# ===========================================================================
# TS-115-23: Gotcha TTL Retrieval Exclusion (config-level)
# ===========================================================================


class TestTTLConfig:
    """Verify gotchas older than configured TTL are excluded.

    Requirements: 115-REQ-7.1
    """

    def test_ttl_91_days_excluded(self, gotcha_conn) -> None:
        _insert_gotcha_raw(
            gotcha_conn, "spec_01", "Old gotcha", days_ago=91
        )

        result = query_gotchas(gotcha_conn, "spec_01", ttl_days=90, limit=5)

        assert len(result) == 0


# ===========================================================================
# TS-115-24: Expired Gotchas Not Deleted
# ===========================================================================


class TestExpiredNotDeleted:
    """Verify expired gotchas remain in the database (excluded from queries only).

    Requirements: 115-REQ-7.2
    """

    def test_expired_not_deleted(self, gotcha_conn) -> None:
        _insert_gotcha_raw(
            gotcha_conn, "spec_01", "Old gotcha", days_ago=100
        )

        # Not returned by query
        result = query_gotchas(gotcha_conn, "spec_01", ttl_days=90, limit=5)
        assert len(result) == 0

        # But still exists in DB
        rows = gotcha_conn.execute(
            "SELECT * FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchall()
        assert len(rows) == 1


# ===========================================================================
# TS-115-E2: Duplicate Gotcha Hash
# ===========================================================================


class TestDuplicateHash:
    """Verify duplicate gotchas are skipped silently (content-hash dedup).

    Requirements: 115-REQ-2.E1
    """

    def test_dedup_same_hash(self, gotcha_conn) -> None:
        candidate = _make_candidate("Same gotcha text")

        store_gotchas(gotcha_conn, "spec_01", "s1", [candidate])
        store_gotchas(gotcha_conn, "spec_01", "s2", [candidate])

        rows = gotcha_conn.execute(
            "SELECT * FROM gotchas WHERE spec_name = 'spec_01'"
        ).fetchall()
        assert len(rows) == 1
