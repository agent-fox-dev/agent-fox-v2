"""Integration tests for quality gate and historical median.

Test Spec: TS-54-6, TS-54-11
Requirements: 54-REQ-2.3, 54-REQ-6.1
"""

from __future__ import annotations

import json
import textwrap
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from agent_fox.routing.features import extract_features

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def integration_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with routing tables for integration tests."""
    conn = duckdb.connect(":memory:")
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
        )
    """)
    conn.execute("""
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
        )
    """)
    yield conn
    conn.close()


@pytest.fixture
def simple_spec_dir(tmp_path: Path) -> Path:
    """Minimal spec dir for integration tests."""
    sd = tmp_path / ".specs" / "03_api"
    sd.mkdir(parents=True)

    tasks_md = textwrap.dedent("""\
    # Tasks

    ## Task Group 2

    - [ ] 2.1 Implement endpoint
    """)
    (sd / "tasks.md").write_text(tasks_md)
    (sd / "requirements.md").write_text("# Requirements\n")
    (sd / "design.md").write_text("# Design\n")
    (sd / "test_spec.md").write_text("# Test Spec\n")
    return sd


def _insert_outcome(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    duration_ms: int,
    outcome: str = "completed",
) -> None:
    """Insert a fake assessment + outcome pair."""
    aid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    fv_json = json.dumps(
        {
            "subtask_count": 1,
            "spec_word_count": 100,
            "has_property_tests": False,
            "edge_case_count": 0,
            "dependency_count": 0,
            "archetype": "coder",
        }
    )
    conn.execute(
        """INSERT INTO complexity_assessments
           (id, node_id, spec_name, task_group, predicted_tier,
            confidence, assessment_method, feature_vector, tier_ceiling, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            aid,
            f"{spec_name}:1",
            spec_name,
            1,
            "STANDARD",
            0.6,
            "heuristic",
            fv_json,
            "ADVANCED",
            datetime.now(UTC),
        ],
    )
    conn.execute(
        """INSERT INTO execution_outcomes
           (id, assessment_id, actual_tier, total_tokens, total_cost,
            duration_ms, attempt_count, escalation_count, outcome,
            files_touched_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            oid,
            aid,
            "STANDARD",
            1000,
            0.01,
            duration_ms,
            1,
            0,
            outcome,
            3,
            datetime.now(UTC),
        ],
    )


# ---------------------------------------------------------------------------
# TS-54-6: Gate failure does not block next session
# ---------------------------------------------------------------------------


class TestGateDoesNotBlock:
    """TS-54-6: A quality gate failure does not prevent the next session."""

    def test_gate_failure_returns_result_not_exception(self) -> None:
        """TS-54-6: Gate failure returns a result, never raises.

        Requirement: 54-REQ-2.3
        """
        import subprocess
        from unittest.mock import patch

        from agent_fox.core.config import OrchestratorConfig
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="failing_cmd")

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args="failing_cmd", returncode=1, stdout="", stderr="error\n"
            )
            result = run_quality_gate(config, project_root="/tmp/project")

        # The function returns a result — it does not raise
        assert result is not None
        assert result.passed is False

        # Next session can proceed — run_quality_gate does not throw
        # This verifies the contract: gate failure is informational only


# ---------------------------------------------------------------------------
# TS-54-11: Historical median duration
# ---------------------------------------------------------------------------


class TestHistoricalMedianDuration:
    """TS-54-11: Historical median computed from prior outcomes."""

    @pytest.mark.integration
    def test_median_of_three_outcomes(
        self,
        simple_spec_dir: Path,
        integration_db: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-54-11: Three outcomes (100, 200, 300) → median=200.

        Requirement: 54-REQ-6.1
        """
        _insert_outcome(integration_db, "03_api", 100)
        _insert_outcome(integration_db, "03_api", 200)
        _insert_outcome(integration_db, "03_api", 300)

        fv = extract_features(
            simple_spec_dir,
            task_group=2,
            archetype="coder",
            conn=integration_db,
            spec_name="03_api",
        )
        assert fv.historical_median_duration_ms == 200

    @pytest.mark.integration
    def test_only_successful_outcomes(
        self,
        simple_spec_dir: Path,
        integration_db: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-54-11: Failed outcomes are excluded from median.

        Requirement: 54-REQ-6.1
        """
        _insert_outcome(integration_db, "03_api", 100)
        _insert_outcome(integration_db, "03_api", 200)
        _insert_outcome(integration_db, "03_api", 999999, outcome="failed")

        fv = extract_features(
            simple_spec_dir,
            task_group=2,
            archetype="coder",
            conn=integration_db,
            spec_name="03_api",
        )
        # Median of [100, 200] = 150
        assert fv.historical_median_duration_ms == 150

    @pytest.mark.integration
    def test_different_spec_names_isolated(
        self,
        simple_spec_dir: Path,
        integration_db: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-54-11: Outcomes from other specs are not included.

        Requirement: 54-REQ-6.1
        """
        _insert_outcome(integration_db, "03_api", 500)
        _insert_outcome(integration_db, "other_spec", 9999)

        fv = extract_features(
            simple_spec_dir,
            task_group=2,
            archetype="coder",
            conn=integration_db,
            spec_name="03_api",
        )
        assert fv.historical_median_duration_ms == 500
