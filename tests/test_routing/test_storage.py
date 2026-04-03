"""Tests for DuckDB storage CRUD and schema.

Test Spec: TS-30-6, TS-30-12, TS-30-13, TS-30-23, TS-30-24, TS-30-25,
           TS-30-E6, TS-30-E10
Requirements: 30-REQ-1.6, 30-REQ-3.1, 30-REQ-3.2, 30-REQ-3.E1,
              30-REQ-6.1, 30-REQ-6.2, 30-REQ-6.3, 30-REQ-6.E1
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.core.models import ModelTier
from agent_fox.routing.core import (
    ComplexityAssessment,
    ExecutionOutcome,
    FeatureVector,
    persist_assessment,
    persist_outcome,
)


def _make_assessment(**overrides) -> ComplexityAssessment:
    """Create a test ComplexityAssessment with defaults."""
    defaults = {
        "id": str(uuid.uuid4()),
        "node_id": "test_spec:1",
        "spec_name": "test_spec",
        "task_group": 1,
        "predicted_tier": ModelTier.SIMPLE,
        "confidence": 0.6,
        "assessment_method": "heuristic",
        "feature_vector": FeatureVector(
            subtask_count=3,
            spec_word_count=200,
            has_property_tests=False,
            edge_case_count=1,
            dependency_count=1,
            archetype="coder",
        ),
        "tier_ceiling": ModelTier.ADVANCED,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ComplexityAssessment(**defaults)


def _make_outcome(assessment_id: str, **overrides) -> ExecutionOutcome:
    """Create a test ExecutionOutcome with defaults."""
    defaults = {
        "id": str(uuid.uuid4()),
        "assessment_id": assessment_id,
        "actual_tier": ModelTier.STANDARD,
        "total_tokens": 5000,
        "total_cost": 0.05,
        "duration_ms": 3000,
        "attempt_count": 3,
        "escalation_count": 1,
        "outcome": "completed",
        "files_touched_count": 5,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ExecutionOutcome(**defaults)


class TestAssessmentTableSchema:
    """TS-30-23: Verify complexity_assessments table schema."""

    @pytest.mark.integration
    def test_assessment_table_schema(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-23: Table exists with all 10 columns, correct types.

        Requirement: 30-REQ-6.1
        """
        cols = routing_db.execute("DESCRIBE complexity_assessments").fetchall()
        col_names = [c[0] for c in cols]

        assert "id" in col_names
        assert "node_id" in col_names
        assert "spec_name" in col_names
        assert "task_group" in col_names
        assert "predicted_tier" in col_names
        assert "confidence" in col_names
        assert "assessment_method" in col_names
        assert "feature_vector" in col_names
        assert "tier_ceiling" in col_names
        assert "created_at" in col_names
        assert len(col_names) == 10


class TestOutcomeTableSchema:
    """TS-30-24: Verify execution_outcomes table schema."""

    @pytest.mark.integration
    def test_outcome_table_schema(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-24: Table exists with all 11 columns.

        Requirement: 30-REQ-6.2
        """
        cols = routing_db.execute("DESCRIBE execution_outcomes").fetchall()
        col_names = [c[0] for c in cols]

        assert "id" in col_names
        assert "assessment_id" in col_names
        assert "actual_tier" in col_names
        assert "total_tokens" in col_names
        assert "total_cost" in col_names
        assert "duration_ms" in col_names
        assert "attempt_count" in col_names
        assert "escalation_count" in col_names
        assert "outcome" in col_names
        assert "files_touched_count" in col_names
        assert "created_at" in col_names
        assert len(col_names) == 11


class TestMigration:
    """TS-30-25: Migration via existing system."""

    @pytest.mark.integration
    def test_migration(self) -> None:
        """TS-30-25: Tables created through the migration system.

        Requirement: 30-REQ-6.3
        """
        from agent_fox.knowledge.migrations import apply_pending_migrations

        conn = duckdb.connect(":memory:")
        # Create schema_version and base facts table first
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL,
                description TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL
            )
        """)

        apply_pending_migrations(conn)

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "complexity_assessments" in table_names
        assert "execution_outcomes" in table_names
        assert "facts" in table_names  # existing table still present

        conn.close()


class TestMigrationIdempotency:
    """TS-30-E10: Migration idempotency."""

    @pytest.mark.integration
    def test_migration_idempotency(self) -> None:
        """TS-30-E10: Re-applying migration doesn't error.

        Requirement: 30-REQ-6.E1
        """
        from agent_fox.knowledge.migrations import apply_pending_migrations

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL,
                description TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        apply_pending_migrations(conn)  # first time
        apply_pending_migrations(conn)  # second time — should be no-op

        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "complexity_assessments" in table_names

        conn.close()


class TestAssessmentPersisted:
    """TS-30-6: Assessment persisted to DuckDB."""

    @pytest.mark.integration
    def test_assessment_persisted(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-6: Verify assessment is written to DuckDB.

        Requirement: 30-REQ-1.6
        """
        assessment = _make_assessment()
        persist_assessment(routing_db, assessment)

        rows = routing_db.execute(
            "SELECT * FROM complexity_assessments WHERE id = ?",
            [assessment.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == assessment.node_id  # node_id column


class TestOutcomeRecorded:
    """TS-30-12: Execution outcome recorded."""

    @pytest.mark.integration
    def test_outcome_recorded(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-12: Verify outcome is persisted to DuckDB.

        Requirement: 30-REQ-3.1
        """
        assessment = _make_assessment()
        persist_assessment(routing_db, assessment)

        outcome = _make_outcome(assessment.id)
        persist_outcome(routing_db, outcome)

        rows = routing_db.execute(
            "SELECT * FROM execution_outcomes WHERE assessment_id = ?",
            [assessment.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "STANDARD"  # actual_tier
        assert rows[0][8] == "completed"  # outcome


class TestOutcomeLinked:
    """TS-30-13: Outcome linked to assessment."""

    @pytest.mark.integration
    def test_outcome_linked(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-13: Verify FK link via JOIN.

        Requirement: 30-REQ-3.2
        """
        assessment = _make_assessment()
        persist_assessment(routing_db, assessment)

        outcome = _make_outcome(assessment.id)
        persist_outcome(routing_db, outcome)

        rows = routing_db.execute(
            """
            SELECT o.*, a.predicted_tier
            FROM execution_outcomes o
            JOIN complexity_assessments a ON o.assessment_id = a.id
            WHERE o.assessment_id = ?
            """,
            [assessment.id],
        ).fetchall()
        assert len(rows) == 1


class TestDbFailureOnOutcome:
    """TS-30-E6: DuckDB unavailable during outcome recording."""

    def test_db_failure_on_outcome(self) -> None:
        """TS-30-E6: Outcome recording failure doesn't raise.

        Requirement: 30-REQ-3.E1
        """
        assessment = _make_assessment()
        outcome = _make_outcome(assessment.id)

        # Create a mock that raises on execute
        failing_db = MagicMock()
        failing_db.execute.side_effect = RuntimeError("DB down")

        # Should not raise
        persist_outcome(failing_db, outcome)
