"""Tests for project model and cross-group finding propagation.

Test Spec: TS-39-17 through TS-39-22, TS-43-1 through TS-43-E2
Requirements: 39-REQ-6.1, 39-REQ-6.2, 39-REQ-7.1, 39-REQ-7.2,
              39-REQ-7.3, 39-REQ-7.4,
              43-REQ-1.1, 43-REQ-1.2, 43-REQ-1.3, 43-REQ-1.4,
              43-REQ-1.E1, 43-REQ-1.E2
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
    """Create the full schema including routing tables."""
    create_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complexity_assessments (
            id              VARCHAR PRIMARY KEY,
            node_id         VARCHAR NOT NULL,
            spec_name       VARCHAR NOT NULL,
            task_group      INTEGER NOT NULL,
            predicted_tier  VARCHAR NOT NULL,
            confidence      FLOAT NOT NULL,
            assessment_method VARCHAR NOT NULL,
            feature_vector  JSON NOT NULL,
            tier_ceiling    VARCHAR NOT NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp
        );

        CREATE TABLE IF NOT EXISTS execution_outcomes (
            id                  VARCHAR PRIMARY KEY,
            assessment_id       VARCHAR NOT NULL REFERENCES complexity_assessments(id),
            actual_tier         VARCHAR NOT NULL,
            total_tokens        INTEGER NOT NULL,
            total_cost          FLOAT NOT NULL,
            duration_ms         INTEGER NOT NULL,
            attempt_count       INTEGER NOT NULL,
            escalation_count    INTEGER NOT NULL,
            outcome             VARCHAR NOT NULL,
            files_touched_count INTEGER NOT NULL,
            created_at          TIMESTAMP NOT NULL DEFAULT current_timestamp
        );

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


def _insert_outcome(
    conn: duckdb.DuckDBPyConnection,
    *,
    spec_name: str,
    archetype: str = "coder",
    cost: float = 1.0,
    duration_ms: int = 100_000,
    outcome: str = "completed",
) -> None:
    """Insert an assessment+outcome pair."""
    aid = str(uuid.uuid4())
    fv = (
        '{"subtask_count": 5, "spec_word_count": 200, '
        '"has_property_tests": false, "edge_case_count": 1, '
        '"dependency_count": 0, "archetype": "' + archetype + '"}'
    )
    conn.execute(
        """INSERT INTO complexity_assessments
           (id, node_id, spec_name, task_group, predicted_tier,
            confidence, assessment_method, feature_vector, tier_ceiling)
           VALUES (?, ?, ?, 1, 'STANDARD', 0.8, 'heuristic', ?, 'MAX')""",
        [aid, f"{spec_name}/1", spec_name, fv],
    )
    conn.execute(
        """INSERT INTO execution_outcomes
           (id, assessment_id, actual_tier, total_tokens, total_cost,
            duration_ms, attempt_count, escalation_count, outcome,
            files_touched_count)
           VALUES (?, ?, 'STANDARD', 1000, ?, ?, 1, 0, ?, 3)""",
        [str(uuid.uuid4()), aid, cost, duration_ms, outcome],
    )


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
# TS-39-19 through TS-39-22: Project Model
# ---------------------------------------------------------------------------


class TestProjectModel:
    """TS-39-19, TS-39-20, TS-39-21, TS-39-22: Project model.

    Requirements: 39-REQ-7.1, 39-REQ-7.2, 39-REQ-7.3, 39-REQ-7.4
    """

    def test_spec_metrics(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-19: Project model aggregates spec-level metrics.

        Requirement: 39-REQ-7.1
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 3 outcomes: costs [1.0, 2.0, 3.0], durations [100, 200, 300]
        _insert_outcome(model_db, spec_name="foo", cost=1.0, duration_ms=100_000)
        _insert_outcome(model_db, spec_name="foo", cost=2.0, duration_ms=200_000)
        _insert_outcome(
            model_db,
            spec_name="foo",
            cost=3.0,
            duration_ms=300_000,
            outcome="failed",
        )

        model = build_project_model(model_db)
        metrics = model.spec_outcomes["foo"]
        assert metrics.avg_cost == pytest.approx(2.0)
        assert metrics.avg_duration_ms == 200_000
        assert metrics.failure_rate == pytest.approx(1 / 3)
        assert metrics.session_count == 3

    def test_module_stability(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-20: Module stability from finding density.

        Requirement: 39-REQ-7.2
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 3 outcomes for foo (3 sessions)
        for _ in range(3):
            _insert_outcome(model_db, spec_name="foo")

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

    def test_archetype_effectiveness(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-21: Archetype effectiveness as success rate per archetype.

        Requirement: 39-REQ-7.3
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Coder: 8 success, 2 fail
        for _ in range(8):
            _insert_outcome(
                model_db,
                spec_name="spec_c",
                archetype="coder",
                outcome="completed",
            )
        for _ in range(2):
            _insert_outcome(
                model_db,
                spec_name="spec_c",
                archetype="coder",
                outcome="failed",
            )

        # Skeptic: 9 success, 1 fail
        for _ in range(9):
            _insert_outcome(
                model_db,
                spec_name="spec_s",
                archetype="skeptic",
                outcome="completed",
            )
        _insert_outcome(
            model_db,
            spec_name="spec_s",
            archetype="skeptic",
            outcome="failed",
        )

        model = build_project_model(model_db)
        assert model.archetype_effectiveness["coder"] == pytest.approx(0.8)
        assert model.archetype_effectiveness["skeptic"] == pytest.approx(0.9)

    def test_status_output(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-22: Project model visible in status --model output.

        Requirement: 39-REQ-7.4
        """
        from agent_fox.knowledge.project_model import (
            build_project_model,
            format_project_model,
        )

        _insert_outcome(model_db, spec_name="foo")
        model = build_project_model(model_db)
        output = format_project_model(model)

        assert "spec_outcomes" in output or "avg_cost" in output
        assert "archetype_effectiveness" in output


# ---------------------------------------------------------------------------
# Spec 43: Project Model tests
# ---------------------------------------------------------------------------


class TestBuildProjectModel:
    """TS-43-1, TS-43-2, TS-43-3: Build project model with outcomes.

    Requirements: 43-REQ-1.1, 43-REQ-1.2, 43-REQ-1.3
    """

    def test_spec_outcomes(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-1: Build project model returns SpecMetrics from execution history.

        Requirement: 43-REQ-1.1

        Preconditions: Two specs with sessions: spec_a (2 completed, 1 failed)
        and spec_b (1 completed).
        """
        from agent_fox.knowledge.project_model import build_project_model

        # spec_a: 2 completed, 1 failed
        _insert_outcome(model_db, spec_name="spec_a", outcome="completed")
        _insert_outcome(model_db, spec_name="spec_a", outcome="completed")
        _insert_outcome(model_db, spec_name="spec_a", outcome="failed")

        # spec_b: 1 completed
        _insert_outcome(model_db, spec_name="spec_b", outcome="completed")

        model = build_project_model(model_db)

        assert "spec_a" in model.spec_outcomes
        assert model.spec_outcomes["spec_a"].session_count == 3
        assert abs(model.spec_outcomes["spec_a"].failure_rate - 1 / 3) < 0.01
        assert model.spec_outcomes["spec_b"].session_count == 1
        assert model.spec_outcomes["spec_b"].failure_rate == 0.0

    def test_module_stability(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-2: Module stability computed as finding density.

        Requirement: 43-REQ-1.2

        Preconditions: spec_a has 6 findings and 3 sessions.
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 3 sessions for spec_a
        for _ in range(3):
            _insert_outcome(model_db, spec_name="spec_a")

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

    def test_archetype_effectiveness(self, model_db: duckdb.DuckDBPyConnection) -> None:
        """TS-43-3: Archetype effectiveness as success rate per archetype.

        Requirement: 43-REQ-1.3

        Preconditions: "coder" 8 completed + 2 failed.
        "reviewer" 3 completed + 0 failed.
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Coder: 8 completed, 2 failed
        for _ in range(8):
            _insert_outcome(
                model_db,
                spec_name="spec_c",
                archetype="coder",
                outcome="completed",
            )
        for _ in range(2):
            _insert_outcome(
                model_db,
                spec_name="spec_c",
                archetype="coder",
                outcome="failed",
            )

        # Reviewer: 3 completed, 0 failed
        for _ in range(3):
            _insert_outcome(
                model_db,
                spec_name="spec_r",
                archetype="reviewer",
                outcome="completed",
            )

        model = build_project_model(model_db)
        assert abs(model.archetype_effectiveness["coder"] - 0.8) < 0.01
        assert model.archetype_effectiveness["reviewer"] == 1.0


class TestFormatProjectModel:
    """TS-43-4: Format project model output.

    Requirement: 43-REQ-1.4
    """

    def test_format_output(self) -> None:
        """TS-43-4: format_project_model produces human-readable output.

        Requirement: 43-REQ-1.4
        """
        from agent_fox.knowledge.project_model import (
            ProjectModel,
            SpecMetrics,
            format_project_model,
        )

        model = ProjectModel(
            spec_outcomes={
                "spec_a": SpecMetrics(
                    spec_name="spec_a",
                    avg_cost=1.5,
                    avg_duration_ms=150_000,
                    failure_rate=0.2,
                    session_count=5,
                ),
            },
            module_stability={"spec_a": 2.0},
            archetype_effectiveness={"coder": 0.8},
            active_drift_areas=["spec_b"],
        )

        output = format_project_model(model)
        assert "== Project Model ==" in output
        assert "spec_outcomes:" in output
        assert "module_stability:" in output
        assert "archetype_effectiveness:" in output


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
        assert model.spec_outcomes == {}
        assert model.module_stability == {}
        assert model.archetype_effectiveness == {}
        assert model.active_drift_areas == []

    def test_findings_without_outcomes(
        self, model_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-43-E2: Findings without outcomes uses density = findings / 1.

        Requirement: 43-REQ-1.E2

        Preconditions: spec_x has 4 review findings but no execution outcomes.
        """
        from agent_fox.knowledge.project_model import build_project_model

        # Insert 4 review findings for spec_x (no execution outcomes)
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
