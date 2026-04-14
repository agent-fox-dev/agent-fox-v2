"""Tests for causal traversal with review findings integration.

Test Spec: TS-39-8, TS-39-9, TS-39-10
Requirements: 39-REQ-3.1, 39-REQ-3.2, 39-REQ-3.3
"""

from __future__ import annotations

import inspect
import uuid

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_causal_review_db(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Set up schema and seed data for causal+review tests.

    Returns dict with fact and finding IDs for assertions.
    """
    create_schema(conn)

    # Add drift_findings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drift_findings (
            id UUID PRIMARY KEY,
            severity VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            spec_ref VARCHAR,
            artifact_ref VARCHAR,
            spec_name VARCHAR NOT NULL,
            task_group VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,
            superseded_by UUID,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    fact_id = str(uuid.uuid4())
    finding_id = str(uuid.uuid4())
    drift_id = str(uuid.uuid4())

    # Insert a memory fact with a keyword matching a requirement ID
    conn.execute(
        """INSERT INTO memory_facts
           (id, content, spec_name, session_id, category, confidence,
            created_at)
           VALUES (?::UUID, 'Duration ordering implemented', 'spec39',
                   'sess1', 'decision', 0.9, CURRENT_TIMESTAMP)""",
        [fact_id],
    )

    # Insert a review finding referencing the same requirement ID
    conn.execute(
        """INSERT INTO review_findings
           (id, severity, description, requirement_ref, spec_name,
            task_group, session_id, created_at)
           VALUES (?::UUID, 'critical', 'Duration ordering not tested',
                   '39-REQ-1.1', 'spec39', '1', 'sess1', CURRENT_TIMESTAMP)""",
        [finding_id],
    )

    # Insert a drift finding
    conn.execute(
        """INSERT INTO drift_findings
           (id, severity, description, spec_ref, artifact_ref, spec_name,
            task_group, session_id, created_at)
           VALUES (?::UUID, 'major', 'Config schema drifted', '39-REQ-1.1',
                   'config.toml', 'spec39', '1', 'sess1', CURRENT_TIMESTAMP)""",
        [drift_id],
    )

    return {
        "fact_id": fact_id,
        "finding_id": finding_id,
        "drift_id": drift_id,
    }


@pytest.fixture
def causal_review_db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with schema and review+causal seed data."""
    conn = duckdb.connect(":memory:")
    return conn


# ---------------------------------------------------------------------------
# TS-39-8: Causal Traversal Includes Review Findings
# ---------------------------------------------------------------------------


class TestCausalTraversalWithReviews:
    """TS-39-8, TS-39-9, TS-39-10: Causal traversal with review findings.

    Requirements: 39-REQ-3.1, 39-REQ-3.2, 39-REQ-3.3
    """

    def test_includes_review_findings(self, causal_review_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-8: Traversal includes linked review findings.

        Requirement: 39-REQ-3.1
        """
        from agent_fox.knowledge.causal import traverse_with_reviews
        from agent_fox.knowledge.review_store import ReviewFinding

        ids = _setup_causal_review_db(causal_review_db)
        results = traverse_with_reviews(causal_review_db, ids["fact_id"])

        # Should include both causal facts and review findings
        has_facts = any(hasattr(r, "fact_id") for r in results)
        has_findings = any(isinstance(r, ReviewFinding) for r in results)

        assert has_facts or len(results) > 0
        assert has_findings, "Review findings should be included in traversal"

    def test_function_exists(self) -> None:
        """TS-39-9: traverse_with_reviews function exists with correct signature.

        Requirement: 39-REQ-3.2
        """
        from agent_fox.knowledge.causal import traverse_with_reviews

        sig = inspect.signature(traverse_with_reviews)
        assert "conn" in sig.parameters
        assert "fact_id" in sig.parameters

    def test_requirement_id_linking(self, causal_review_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-10: Review findings linked via requirement ID are included.

        Requirement: 39-REQ-3.3
        """
        from agent_fox.knowledge.causal import traverse_with_reviews

        ids = _setup_causal_review_db(causal_review_db)
        results = traverse_with_reviews(causal_review_db, ids["fact_id"])

        # Review finding referencing '39-REQ-1.1' should appear
        has_req_finding = any(hasattr(r, "requirement_ref") and r.requirement_ref == "39-REQ-1.1" for r in results)
        assert has_req_finding, (
            "Review finding referencing requirement_id '39-REQ-1.1' should appear in traversal results"
        )
