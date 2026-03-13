"""Integration tests for drift findings DuckDB store operations.

Test Spec: TS-32-8, TS-32-9, TS-32-13
Requirements: 32-REQ-7.1, 32-REQ-7.2, 32-REQ-7.3, 32-REQ-7.4,
              32-REQ-4.1, 32-REQ-4.2
"""

from __future__ import annotations

import uuid

import duckdb
import pytest


def _create_drift_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create schema including drift_findings table."""
    from tests.unit.knowledge.conftest import create_schema

    create_schema(conn)
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


@pytest.fixture
def drift_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with drift_findings table."""
    conn = duckdb.connect(":memory:")
    _create_drift_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


def _make_drift_finding(
    severity: str = "major",
    description: str = "Test drift",
    spec_name: str = "test_spec",
    task_group: str = "0",
    session_id: str = "s1",
    spec_ref: str | None = None,
    artifact_ref: str | None = None,
):
    """Create a DriftFinding for testing."""
    from agent_fox.knowledge.review_store import DriftFinding

    return DriftFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        spec_ref=spec_ref,
        artifact_ref=artifact_ref,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# TS-32-8: Insert and Query Drift Findings
# Requirements: 32-REQ-7.1, 32-REQ-7.2, 32-REQ-7.4
# ---------------------------------------------------------------------------


class TestInsertAndQuery:
    """Insert drift findings and query active ones back."""

    def test_insert_query(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-32-8: Insert 3 findings, query returns all ordered by severity."""
        from agent_fox.knowledge.review_store import (
            insert_drift_findings,
            query_active_drift_findings,
        )

        findings = [
            _make_drift_finding(severity="major", description="Issue B"),
            _make_drift_finding(severity="critical", description="Issue A"),
            _make_drift_finding(severity="minor", description="Issue C"),
        ]
        count = insert_drift_findings(drift_conn, findings)
        assert count == 3

        result = query_active_drift_findings(drift_conn, "test_spec")
        assert len(result) == 3
        # Sorted by severity priority: critical, major, minor
        assert result[0].severity == "critical"
        assert result[1].severity == "major"
        assert result[2].severity == "minor"

    def test_query_filters_by_spec(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Findings for different specs are independent."""
        from agent_fox.knowledge.review_store import (
            insert_drift_findings,
            query_active_drift_findings,
        )

        f1 = _make_drift_finding(spec_name="spec_a")
        f2 = _make_drift_finding(spec_name="spec_b")
        insert_drift_findings(drift_conn, [f1])
        insert_drift_findings(drift_conn, [f2])

        result_a = query_active_drift_findings(drift_conn, "spec_a")
        assert len(result_a) == 1
        assert result_a[0].spec_name == "spec_a"

    def test_query_with_task_group_filter(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Task group filter narrows results."""
        from agent_fox.knowledge.review_store import (
            insert_drift_findings,
            query_active_drift_findings,
        )

        f1 = _make_drift_finding(task_group="0", session_id="s1")
        f2 = _make_drift_finding(task_group="1", session_id="s2")
        insert_drift_findings(drift_conn, [f1])
        insert_drift_findings(drift_conn, [f2])

        result = query_active_drift_findings(drift_conn, "test_spec", "0")
        assert len(result) == 1
        assert result[0].task_group == "0"


# ---------------------------------------------------------------------------
# TS-32-9: Supersession on Re-insert
# Requirement: 32-REQ-7.3
# ---------------------------------------------------------------------------


class TestSupersession:
    """Re-inserting findings supersedes previous ones."""

    def test_supersession(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-32-9: Batch 2 supersedes batch 1."""
        from agent_fox.knowledge.review_store import (
            insert_drift_findings,
            query_active_drift_findings,
        )

        batch_1 = [
            _make_drift_finding(
                severity="critical",
                description="Old 1",
                session_id="s1",
            ),
            _make_drift_finding(
                severity="major",
                description="Old 2",
                session_id="s1",
            ),
        ]
        insert_drift_findings(drift_conn, batch_1)

        batch_2 = [
            _make_drift_finding(
                severity="minor",
                description="New 1",
                session_id="s2",
            ),
        ]
        insert_drift_findings(drift_conn, batch_2)

        result = query_active_drift_findings(drift_conn, "test_spec", "0")
        assert len(result) == 1
        assert result[0].session_id == "s2"
        assert result[0].description == "New 1"

    def test_empty_insert_no_error(
        self,
        drift_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Inserting empty list returns 0 and does not error."""
        from agent_fox.knowledge.review_store import insert_drift_findings

        count = insert_drift_findings(drift_conn, [])
        assert count == 0


# ---------------------------------------------------------------------------
# TS-32-13: Hot-loaded Specs Get Oracle Nodes
# Requirements: 32-REQ-4.1, 32-REQ-4.2
# ---------------------------------------------------------------------------


class TestHotLoadOracleInjection:
    """Newly hot-loaded specs receive oracle nodes."""

    def test_hot_load_oracle_injection(self) -> None:
        """TS-32-13: Hot-loaded spec gets an oracle node in pending state.

        This test validates the graph structure after injection.
        Full hot-load integration depends on task group 4 implementation.
        For now, we verify the injection mechanism using build_graph directly.
        """
        from pathlib import Path

        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph
        from agent_fox.spec.discovery import SpecInfo
        from agent_fox.spec.parser import TaskGroupDef

        config = ArchetypesConfig(oracle=True)
        new_spec = SpecInfo(
            name="new_feature",
            prefix=99,
            path=Path(".specs/new_feature"),
            has_tasks=True,
            has_prd=False,
        )
        task_groups = {
            "new_feature": [
                TaskGroupDef(
                    number=1,
                    title="Task 1",
                    optional=False,
                    completed=False,
                    subtasks=(),
                    body="",
                ),
            ]
        }

        graph = build_graph(
            [new_spec],
            task_groups,
            [],
            archetypes_config=config,
        )

        # Oracle node should exist (suffixed because multiple auto_pre archetypes)
        assert "new_feature:0:oracle" in graph.nodes
        assert graph.nodes["new_feature:0:oracle"].archetype == "oracle"
        # Should start as pending
        from agent_fox.graph.types import NodeStatus

        assert graph.nodes["new_feature:0:oracle"].status == NodeStatus.PENDING
