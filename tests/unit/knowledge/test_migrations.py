"""Tests for schema migration system.

Test Spec: TS-11-5 (applies pending migrations)
Edge cases: TS-11-E5 (migration failure raises KnowledgeStoreError)
Requirements: 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3, 11-REQ-3.E1
"""

from __future__ import annotations

import logging
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
            apply=lambda c: c.execute("ALTER TABLE session_outcomes ADD COLUMN test_col TEXT"),  # type: ignore[arg-type]
        )

        with patch(
            "agent_fox.knowledge.migrations.MIGRATIONS",
            [test_migration],
        ):
            apply_pending_migrations(conn)

        # Verify version 2 was recorded
        rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
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
            apply=lambda c: c.execute("INVALID SQL STATEMENT"),  # type: ignore[arg-type]
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


# -- Migration log message tests ---------------------------------------------


class TestMigrationLogMessages:
    """Verify log messages distinguish applied vs skipped schema changes.

    Issue #470: migrations v5 and v10 logged contradictory messages —
    "skipping" followed by "Applied" — when the schema change was already
    present. The fix is to return False from migration functions that skip
    the schema change, and log a distinct "already up to date" message.
    """

    def test_applied_log_emitted_when_migration_runs(self, caplog: pytest.LogCaptureFixture) -> None:
        """When a migration actually performs schema changes, 'Applied migration' is logged."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        ran = Migration(
            version=2,
            description="add test_col to session_outcomes",
            apply=lambda c: c.execute("ALTER TABLE session_outcomes ADD COLUMN test_col2 TEXT"),  # type: ignore[arg-type]
        )

        with patch("agent_fox.knowledge.migrations.MIGRATIONS", [ran]):
            with caplog.at_level(logging.INFO, logger="agent_fox.knowledge.migrations"):
                apply_pending_migrations(conn)

        messages = [r.message for r in caplog.records]
        assert any("Applied migration v2" in m for m in messages), messages
        assert not any("already up to date" in m for m in messages), messages
        conn.close()

    def test_already_applied_log_emitted_when_schema_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """When migration returns False (schema skipped), a distinct log is emitted."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        skipped = Migration(
            version=2,
            description="noop skipped migration",
            apply=lambda c: False,  # type: ignore[arg-type, return-value]
        )

        with patch("agent_fox.knowledge.migrations.MIGRATIONS", [skipped]):
            with caplog.at_level(logging.INFO, logger="agent_fox.knowledge.migrations"):
                apply_pending_migrations(conn)

        messages = [r.message for r in caplog.records]
        assert any("already up to date" in m for m in messages), messages
        assert not any(m.startswith("Applied migration v2") for m in messages), messages
        conn.close()

    def test_no_contradictory_messages_for_v5_on_already_numeric_db(self, caplog: pytest.LogCaptureFixture) -> None:
        """v5 must not log 'Applied' after logging 'skipping' on a numeric-confidence db.

        Regression test for issue #470: the schema already has DOUBLE confidence,
        so v5 should skip the schema change and log only the 'already up to date'
        message, never 'Applied migration v5'.
        """
        conn = duckdb.connect(":memory:")
        create_schema(conn)  # schema already has DOUBLE confidence

        from agent_fox.knowledge.migrations import MIGRATIONS

        v5 = next(m for m in MIGRATIONS if m.version == 5)

        with patch("agent_fox.knowledge.migrations.MIGRATIONS", [v5]):
            with caplog.at_level(logging.INFO, logger="agent_fox.knowledge.migrations"):
                apply_pending_migrations(conn)

        messages = [r.message for r in caplog.records]
        assert not any("Applied migration v5" in m for m in messages), (
            f"'Applied migration v5' should not appear when schema was skipped; got: {messages}"
        )
        assert any("already up to date" in m for m in messages), (
            f"Expected 'already up to date' in messages; got: {messages}"
        )
        conn.close()

    def test_no_contradictory_messages_for_v10_on_existing_keywords_db(self, caplog: pytest.LogCaptureFixture) -> None:
        """v10 must not log 'Applied' after logging 'skipping' when keywords column exists.

        Regression test for issue #470: the schema already has the keywords column,
        so v10 should skip the schema change and log only the 'already up to date'
        message, never 'Applied migration v10'.
        """
        conn = duckdb.connect(":memory:")
        create_schema(conn)  # schema already has keywords column

        from agent_fox.knowledge.migrations import MIGRATIONS

        v10 = next(m for m in MIGRATIONS if m.version == 10)

        with patch("agent_fox.knowledge.migrations.MIGRATIONS", [v10]):
            with caplog.at_level(logging.INFO, logger="agent_fox.knowledge.migrations"):
                apply_pending_migrations(conn)

        messages = [r.message for r in caplog.records]
        assert not any("Applied migration v10" in m for m in messages), (
            f"'Applied migration v10' should not appear when schema was skipped; got: {messages}"
        )
        assert any("already up to date" in m for m in messages), (
            f"Expected 'already up to date' in messages; got: {messages}"
        )
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
