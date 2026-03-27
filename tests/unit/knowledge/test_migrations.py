"""Tests for schema migration system.

Test Spec: TS-11-5 (applies pending migrations)
Edge cases: TS-11-E5 (migration failure raises KnowledgeStoreError)
Requirements: 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3, 11-REQ-3.E1
"""

from __future__ import annotations

from unittest.mock import patch

import duckdb
import pytest

from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.knowledge.migrations import (
    Migration,
    apply_pending_migrations,
)
from tests.unit.knowledge.conftest import create_schema


class TestMigrationAppliesPendingMigrations:
    """TS-11-5: Migration applies pending migrations.

    Requirements: 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3
    """

    def test_migration_adds_column_and_records_version(self) -> None:
        """Verify a registered migration is applied and version recorded."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        test_migration = Migration(
            version=2,
            description="add test_col to session_outcomes",
            apply=lambda c: c.execute(
                "ALTER TABLE session_outcomes ADD COLUMN test_col TEXT"
            ),
        )

        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            [test_migration],
        ):
            apply_pending_migrations(conn)

        # Verify version 2 was recorded
        rows = conn.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall()
        assert (2,) in rows

        # Verify column exists
        cols = conn.execute("DESCRIBE session_outcomes").fetchall()
        col_names = {row[0] for row in cols}
        assert "test_col" in col_names
        conn.close()

    def test_migration_skips_already_applied(self) -> None:
        """Verify migrations already applied are not re-applied."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        call_count = 0

        def counting_migration(c: duckdb.DuckDBPyConnection) -> None:
            nonlocal call_count
            call_count += 1
            c.execute("ALTER TABLE session_outcomes ADD COLUMN extra TEXT")

        test_migration = Migration(
            version=2,
            description="counting migration",
            apply=counting_migration,
        )

        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            [test_migration],
        ):
            apply_pending_migrations(conn)

        # Calling again with the same migration should skip it
        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            [test_migration],
        ):
            apply_pending_migrations(conn)

        assert call_count == 1
        conn.close()


# -- Edge Case Tests ---------------------------------------------------------


class TestMigrationFailureRaisesKnowledgeStoreError:
    """TS-11-E5: Migration failure raises KnowledgeStoreError.

    Requirement: 11-REQ-3.E1
    """

    def test_bad_sql_raises_knowledge_store_error(self) -> None:
        """Verify invalid migration SQL raises KnowledgeStoreError with version."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        bad_migration = Migration(
            version=2,
            description="bad migration",
            apply=lambda c: c.execute("INVALID SQL STATEMENT"),
        )

        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            [bad_migration],
        ):
            with pytest.raises(KnowledgeStoreError) as exc_info:
                apply_pending_migrations(conn)

        # Error should mention the version number
        error_msg = str(exc_info.value)
        assert "2" in error_msg or "version" in error_msg.lower()
        conn.close()


# -- H4: Dimension Allowlist Tests -------------------------------------------


class TestEmbeddingDimensionAllowlist:
    """H4: Embedding dimension is restricted to an allowlist."""

    def test_valid_dimension_384(self) -> None:
        """Dimension 384 (MiniLM) is accepted."""
        from agent_fox.knowledge.migrations import _sanitize_embedding_dim

        assert _sanitize_embedding_dim(384) == 384

    def test_valid_dimension_768(self) -> None:
        """Dimension 768 (base BERT) is accepted."""
        from agent_fox.knowledge.migrations import _sanitize_embedding_dim

        assert _sanitize_embedding_dim(768) == 768

    def test_valid_dimension_1536(self) -> None:
        """Dimension 1536 (OpenAI ada-002) is accepted."""
        from agent_fox.knowledge.migrations import _sanitize_embedding_dim

        assert _sanitize_embedding_dim(1536) == 1536

    def test_invalid_dimension_defaults_to_384(self) -> None:
        """An unexpected dimension falls back to 384."""
        from agent_fox.knowledge.migrations import _sanitize_embedding_dim

        assert _sanitize_embedding_dim(999) == 384

    def test_zero_dimension_defaults_to_384(self) -> None:
        """Zero dimension falls back to 384."""
        from agent_fox.knowledge.migrations import _sanitize_embedding_dim

        assert _sanitize_embedding_dim(0) == 384
