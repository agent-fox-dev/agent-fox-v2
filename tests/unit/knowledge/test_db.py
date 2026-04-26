"""Tests for DuckDB connection management and schema initialization.

Test Spec: TS-11-1 (opens and creates schema), TS-11-2 (version recorded),
           TS-11-3 (close releases connection), TS-11-4 (context manager),
           TS-11-6 (schema idempotent)
Edge cases: TS-11-E1 (parent dir created), TS-11-E2 (corrupted DB degrades)
Requirements: 11-REQ-1.1, 11-REQ-1.2, 11-REQ-1.3, 11-REQ-1.E1, 11-REQ-1.E2,
              11-REQ-2.1, 11-REQ-2.2, 11-REQ-2.3, 11-REQ-7.1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store

# -- Expected tables in the knowledge store schema ---------------------------

EXPECTED_TABLES = {
    "schema_version",
    "session_outcomes",
    "tool_calls",
    "tool_errors",
    "review_findings",
    "verification_results",
    "drift_findings",
    "audit_events",
    # Added by migration v11 (spec 105: DB-based plan state)
    "plan_nodes",
    "plan_edges",
    "plan_meta",
    "runs",
    # Added by migration v19 (issue #522: errata generation)
    "errata",
    # Added by migration v22 (spec 117: ADR ingestion)
    "adr_entries",
}


class TestDatabaseOpensAndCreatesSchema:
    """TS-11-1: Database opens and creates schema.

    Requirements: 11-REQ-1.1, 11-REQ-2.1
    """

    def test_creates_database_file(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify that opening a KnowledgeDB creates the database file."""
        db = KnowledgeDB(knowledge_config)
        db.open()
        assert Path(knowledge_config.store_path).exists()
        db.close()

    def test_creates_all_schema_tables(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify all schema tables are created on first open."""
        db = KnowledgeDB(knowledge_config)
        db.open()
        tables = db.connection.execute("SHOW TABLES").fetchall()
        table_names = {row[0] for row in tables}
        assert table_names == EXPECTED_TABLES
        db.close()


class TestSchemaVersionRecordedOnCreation:
    """TS-11-2: Schema version recorded on creation.

    Requirement: 11-REQ-2.2
    """

    def test_version_1_recorded(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify initial schema creation records version 1 and migrations run."""
        db = KnowledgeDB(knowledge_config)
        db.open()
        rows = db.connection.execute(
            "SELECT version, applied_at, description FROM schema_version ORDER BY version"
        ).fetchall()
        assert len(rows) == 22
        assert rows[0][0] == 1
        assert rows[0][1] is not None  # applied_at is a valid timestamp
        assert len(rows[0][2]) > 0  # description is non-empty
        for i, expected_version in enumerate(range(1, 22)):
            assert rows[i][0] == expected_version
        db.close()


class TestDatabaseConnectionClosesCleanly:
    """TS-11-3: Database connection closes cleanly.

    Requirement: 11-REQ-1.3
    """

    def test_close_releases_connection(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify close() releases connection and subsequent access raises."""
        db = KnowledgeDB(knowledge_config)
        db.open()
        db.close()
        with pytest.raises(KnowledgeStoreError):
            _ = db.connection


class TestContextManagerOpensAndCloses:
    """TS-11-4: Context manager opens and closes.

    Requirements: 11-REQ-1.1, 11-REQ-1.3
    """

    def test_with_block_provides_connection(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify connection is accessible inside the with block."""
        with KnowledgeDB(knowledge_config) as db:
            assert db.connection is not None
            tables = db.connection.execute("SHOW TABLES").fetchall()
            assert len(tables) > 0

    def test_connection_closed_after_block(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify KnowledgeStoreError raised after the block exits."""
        with KnowledgeDB(knowledge_config) as db:
            _ = db.connection  # should work inside block
        with pytest.raises(KnowledgeStoreError):
            _ = db.connection


class TestSchemaInitializationIdempotent:
    """TS-11-6: Schema initialization is idempotent.

    Requirements: 11-REQ-2.1, 11-REQ-2.2
    """

    def test_double_open_does_not_duplicate(self, knowledge_config: KnowledgeConfig) -> None:
        """Verify that opening twice does not duplicate version rows."""
        db1 = KnowledgeDB(knowledge_config)
        db1.open()
        db1.close()

        db2 = KnowledgeDB(knowledge_config)
        db2.open()
        count = db2.connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()
        assert count is not None
        assert count[0] == 22
        db2.close()


# -- Edge Case Tests ---------------------------------------------------------


class TestParentDirectoryCreatedAutomatically:
    """TS-11-E1: Parent directory created automatically.

    Requirement: 11-REQ-1.E1
    """

    def test_creates_nested_parent_dirs(self, tmp_path: Path) -> None:
        """Verify KnowledgeDB creates missing parent directories."""
        nested = tmp_path / "deep" / "nested" / "dir" / "knowledge.duckdb"
        config = KnowledgeConfig(store_path=str(nested))
        db = KnowledgeDB(config)
        db.open()
        assert nested.exists()
        db.close()


class TestCorruptedDatabaseDegradesGracefully:
    """TS-11-E2: Corrupted database degrades gracefully.

    Requirement: 11-REQ-7.1
    """

    def test_corrupted_db_raises(self, tmp_path: Path) -> None:
        """Verify corrupted database file causes open_knowledge_store to raise.

        Updated for 38-REQ-1.1: DuckDB is now a hard requirement.
        """
        db_path = tmp_path / "knowledge.duckdb"
        db_path.write_bytes(b"this is not a duckdb file")
        config = KnowledgeConfig(store_path=str(db_path))
        with pytest.raises(RuntimeError, match="Knowledge store initialization failed"):
            open_knowledge_store(config)


# -- Additional failure mode tests -------------------------------------------


class TestConnectionClosedRaisesError:
    """Accessing connection after close raises KnowledgeStoreError."""

    def test_connection_property_after_close(self, knowledge_config: KnowledgeConfig) -> None:
        """Accessing .connection after close raises KnowledgeStoreError."""
        db = KnowledgeDB(knowledge_config)
        db.open()
        db.close()
        with pytest.raises(KnowledgeStoreError, match="not open"):
            _ = db.connection

    def test_connection_property_before_open(self, knowledge_config: KnowledgeConfig) -> None:
        """Accessing .connection before open raises KnowledgeStoreError."""
        db = KnowledgeDB(knowledge_config)
        with pytest.raises(KnowledgeStoreError, match="not open"):
            _ = db.connection


class TestOpenKnowledgeStoreFailureModes:
    """open_knowledge_store raises RuntimeError on failure modes.

    Updated for 38-REQ-1.1: DuckDB is now a hard requirement.
    """

    def test_unwritable_path_raises(self, tmp_path: Path) -> None:
        """Database path in a non-existent root raises RuntimeError."""
        config = KnowledgeConfig(store_path="/nonexistent/deep/path/db.duckdb")
        with pytest.raises(RuntimeError, match="Knowledge store initialization failed"):
            open_knowledge_store(config)

    def test_double_close_is_safe(self, knowledge_config: KnowledgeConfig) -> None:
        """Calling close() twice does not raise."""
        db = KnowledgeDB(knowledge_config)
        db.open()
        db.close()
        db.close()  # should not raise
