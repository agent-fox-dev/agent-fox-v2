"""Tests for project model: module stability and active drift.

Test Spec: TS-39-17 through TS-39-22, TS-43-2, TS-43-4, TS-43-E1, TS-43-E2
Requirements: 39-REQ-6.1, 39-REQ-6.2, 39-REQ-7.2, 39-REQ-7.4
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_full_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the full schema including review and drift tables."""
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
def model_db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with full schema for project model tests."""
    conn = duckdb.connect(":memory:")
    _create_full_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# TS-39-17, TS-39-18: Cross-Group Finding Propagation
# ---------------------------------------------------------------------------


class TestFindingPropagation:
    """TS-39-17, TS-39-18: Cross-group finding propagation.

    Requirements: 39-REQ-6.1, 39-REQ-6.2
    """

    def test_cross_group_findings(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-17: Context for group N includes findings from groups 1..N-1.

        Requirement: 39-REQ-6.1
        """
        from agent_fox.session.prompt import get_prior_group_findings

        # Insert findings for groups 1 and 2
        conn = model_db
        conn.execute(
            """INSERT INTO review_findings
               (id, severity, description, requirement_ref, spec_name,
                task_group, session_id, created_at)
               VALUES
                (?::UUID, 'critical', 'group 1 finding text', '39-REQ-1.1',
                 'foo', '1', 'sess1', CURRENT_TIMESTAMP),
                (?::UUID, 'major', 'group 2 finding text', '39-REQ-2.1',
                 'foo', '2', 'sess2', CURRENT_TIMESTAMP)""",
            [str(uuid.uuid4()), str(uuid.uuid4())],
        )

        findings = get_prior_group_findings(conn, "foo", task_group=3)
        finding_texts = [f.description for f in findings]
        assert "group 1 finding text" in finding_texts
        assert "group 2 finding text" in finding_texts

    def test_prior_group_label(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-18: Propagated findings appear under 'Prior Group Findings'.

        Requirement: 39-REQ-6.2
        """
        from agent_fox.session.prompt import render_prior_group_findings

        conn = model_db
        conn.execute(
            """INSERT INTO review_findings
               (id, severity, description, requirement_ref, spec_name,
                task_group, session_id, created_at)
               VALUES (?::UUID, 'critical', 'a finding', '39-REQ-1.1',
                       'foo', '1', 'sess1', CURRENT_TIMESTAMP)""",
            [str(uuid.uuid4())],
        )

        from agent_fox.session.prompt import get_prior_group_findings

        findings = get_prior_group_findings(conn, "foo", task_group=2)
        rendered = render_prior_group_findings(findings)
        assert "Prior Group Findings" in rendered


# ---------------------------------------------------------------------------
# TS-39-20: Module stability
# ---------------------------------------------------------------------------


class TestProjectModel:
    """TS-39-20: Project model module stability.

    Requirement: 39-REQ-7.2
    """

    def test_module_stability(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-20: Module stability from finding density.

        Requirement: 39-REQ-7.2
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 3 session outcomes for foo
        for i in range(3):
            model_db.execute(
                """INSERT INTO session_outcomes
                   (id, spec_name, task_group, node_id, status, created_at)
                   VALUES (?::UUID, 'foo', '1', 'foo/1', 'completed', CURRENT_TIMESTAMP)""",
                [str(uuid.uuid4())],
            )

        # Insert 6 review findings for foo
        for i in range(6):
            model_db.execute(
                """INSERT INTO review_findings
                   (id, severity, description, requirement_ref, spec_name,
                    task_group, session_id, created_at)
                   VALUES (?::UUID, 'major', ?, NULL, 'foo', '1',
                           ?, CURRENT_TIMESTAMP)""",
                [str(uuid.uuid4()), f"Finding {i}", f"sess_{i}"],
            )

        model = build_project_model(model_db)
        # 6 findings / 3 sessions = 2.0 density
        assert model.module_stability["foo"] == pytest.approx(2.0)

    def test_status_output(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-22: Project model visible in status --model output.

        Requirement: 39-REQ-7.4
        """
        from agent_fox.knowledge.project_model import (
            build_project_model,
            format_project_model,
        )

        model = build_project_model(model_db)
        output = format_project_model(model)

        assert "module_stability" in output


# ---------------------------------------------------------------------------
# Spec 43: Project Model tests
# ---------------------------------------------------------------------------


class TestBuildProjectModel:
    """TS-43-2: Build project model with module stability.

    Requirement: 39-REQ-7.2
    """

    def test_module_stability(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-2: Module stability computed as finding density.

        Requirement: 39-REQ-7.2

        Preconditions: spec_a has 6 findings and 3 sessions.
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 3 session outcomes for spec_a
        for _ in range(3):
            model_db.execute(
                """INSERT INTO session_outcomes
                   (id, spec_name, task_group, node_id, status, created_at)
                   VALUES (?::UUID, 'spec_a', '1', 'spec_a/1', 'completed', CURRENT_TIMESTAMP)""",
                [str(uuid.uuid4())],
            )

        # Insert 6 review findings for spec_a
        for i in range(6):
            model_db.execute(
                """INSERT INTO review_findings
                   (id, severity, description, requirement_ref, spec_name,
                    task_group, session_id, created_at)
                   VALUES (?::UUID, 'major', ?, NULL, 'spec_a', '1',
                           ?, CURRENT_TIMESTAMP)""",
                [str(uuid.uuid4()), f"Finding {i}", f"sess_{i}"],
            )

        model = build_project_model(model_db)
        # 6 findings / 3 sessions = 2.0 density
        assert model.module_stability["spec_a"] == 2.0


class TestFormatProjectModel:
    """TS-43-4: Format project model output.

    Requirement: 39-REQ-7.4
    """

    def test_format_output(self) -> None:
        """TS-43-4: format_project_model produces human-readable output.

        Requirement: 39-REQ-7.4
        """
        from agent_fox.knowledge.project_model import (
            ProjectModel,
            format_project_model,
        )

        model = ProjectModel(
            module_stability={"spec_a": 2.0},
            active_drift_areas=["spec_b"],
        )

        output = format_project_model(model)
        assert "== Project Model ==" in output
        assert "module_stability:" in output


class TestProjectModelEdgeCases:
    """TS-43-E1, TS-43-E2: Project model edge cases.

    Requirements: 43-REQ-1.E1, 43-REQ-1.E2
    """

    def test_empty_database(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-E1: Empty database returns empty model.

        Requirement: 43-REQ-1.E1

        Preconditions: Tables created but no rows.
        """
        from agent_fox.knowledge.project_model import build_project_model

        model = build_project_model(model_db)
        assert model.module_stability == {}
        assert model.active_drift_areas == []

    def test_findings_without_sessions(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-E2: Findings without session outcomes uses density = findings / 1.

        Requirement: 43-REQ-1.E2

        Preconditions: spec_x has 4 review findings but no session outcomes.
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 4 review findings for spec_x (no session outcomes)
        for i in range(4):
            model_db.execute(
                """INSERT INTO review_findings
                   (id, severity, description, requirement_ref, spec_name,
                    task_group, session_id, created_at)
                   VALUES (?::UUID, 'major', ?, NULL, 'spec_x', '1',
                           ?, CURRENT_TIMESTAMP)""",
                [str(uuid.uuid4()), f"Finding {i}", f"sess_{i}"],
            )

        model = build_project_model(model_db)
        assert model.module_stability["spec_x"] == 4.0
