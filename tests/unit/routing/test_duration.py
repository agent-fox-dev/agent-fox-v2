"""Tests for duration-based task ordering and duration hints.

Test Spec: TS-41-5 through TS-41-15, TS-41-E1 through TS-41-E5, TS-41-E8
Requirements: 41-REQ-1.1 through 41-REQ-5.E2
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_routing_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the routing-related tables needed for duration tests."""
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
    """)


def _insert_assessment(
    conn: duckdb.DuckDBPyConnection,
    *,
    assessment_id: str,
    spec_name: str = "foo",
    archetype: str = "coder",
    task_group: int = 1,
    feature_vector: str | None = None,
) -> str:
    """Insert a complexity assessment and return its id."""
    if feature_vector is None:
        feature_vector = json.dumps(
            {
                "subtask_count": 5,
                "spec_word_count": 200,
                "has_property_tests": False,
                "edge_case_count": 1,
                "dependency_count": 0,
                "archetype": archetype,
            }
        )
    conn.execute(
        """INSERT INTO complexity_assessments
           (id, node_id, spec_name, task_group, predicted_tier,
            confidence, assessment_method, feature_vector, tier_ceiling, created_at)
           VALUES (?, ?, ?, ?, 'STANDARD', 0.8, 'heuristic', ?, 'MAX', ?)""",
        [
            assessment_id,
            f"{spec_name}/{task_group}",
            spec_name,
            task_group,
            feature_vector,
            datetime.now().isoformat(),
        ],
    )
    return assessment_id


def _insert_outcome(
    conn: duckdb.DuckDBPyConnection,
    *,
    assessment_id: str,
    duration_ms: int,
    outcome: str = "completed",
) -> None:
    """Insert an execution outcome."""
    conn.execute(
        """INSERT INTO execution_outcomes
           (id, assessment_id, actual_tier, total_tokens, total_cost,
            duration_ms, attempt_count, escalation_count, outcome,
            files_touched_count, created_at)
           VALUES (?, ?, 'STANDARD', 1000, 0.5, ?, 1, 0, ?, 3, ?)""",
        [
            str(uuid.uuid4()),
            assessment_id,
            duration_ms,
            outcome,
            datetime.now().isoformat(),
        ],
    )


@pytest.fixture
def duration_db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with routing schema for duration tests."""
    conn = duckdb.connect(":memory:")
    _create_routing_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# TS-41-5: Historical Median With Sufficient Data
# ---------------------------------------------------------------------------


class TestGetDurationHint:
    """Tests for get_duration_hint() source precedence and behavior.

    Test Spec: TS-41-5, TS-41-6, TS-41-10, TS-41-14, TS-41-15
    """

    def test_historical_median_with_sufficient_data(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-5: Historical median used when >= min_outcomes exist.

        Requirement: 41-REQ-2.1
        """
        from agent_fox.routing.duration import DurationHint, get_duration_hint

        # Insert 15 outcomes with durations [100, 200, ..., 1500]
        aid = _insert_assessment(duration_db, assessment_id="a1", spec_name="myspec")
        for i in range(1, 16):
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=i * 100)

        hint = get_duration_hint(duration_db, "node1", "myspec", "coder", "STANDARD", min_outcomes=10)
        assert isinstance(hint, DurationHint)
        assert hint.source == "historical"
        assert hint.predicted_ms == 800  # median of 100..1500

    def test_historical_median_insufficient_data(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-6: Fallthrough when fewer than min_outcomes exist.

        Requirement: 41-REQ-2.2
        """
        from agent_fox.routing.duration import get_duration_hint

        # Insert only 5 outcomes
        aid = _insert_assessment(duration_db, assessment_id="a2", spec_name="myspec")
        for i in range(1, 6):
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=i * 100)

        hint = get_duration_hint(duration_db, "node1", "myspec", "coder", "STANDARD", min_outcomes=10)
        assert hint.source != "historical"

    def test_default_fallback_unknown_archetype(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-10: Default fallback when no preset matches.

        Requirement: 41-REQ-3.3
        """
        from agent_fox.routing.duration import DEFAULT_DURATION_MS, get_duration_hint

        hint = get_duration_hint(duration_db, "node1", "spec", "unknown_arch", "UNKNOWN_TIER")
        assert hint.source == "default"
        assert hint.predicted_ms == DEFAULT_DURATION_MS
        assert hint.predicted_ms == 300_000

    def test_regression_takes_precedence_over_historical(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-14: Regression source used when model is available.

        Requirement: 41-REQ-4.4
        """
        from agent_fox.routing.duration import get_duration_hint, train_duration_model

        # Insert enough outcomes for both historical and regression
        for i in range(35):
            aid = str(uuid.uuid4())
            _insert_assessment(
                duration_db,
                assessment_id=aid,
                spec_name=f"spec_{i % 5}",
                archetype="coder",
                task_group=i % 3 + 1,
            )
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=(i + 1) * 10_000)

        model = train_duration_model(duration_db, min_outcomes=10)
        assert model is not None

        hint = get_duration_hint(
            duration_db,
            "node1",
            "spec_0",
            "coder",
            "STANDARD",
            min_outcomes=10,
            model=model,
        )
        assert hint.source == "regression"

    def test_regression_prediction_clamped_to_minimum(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-15: Regression predictions clamped to minimum 1 ms.

        Requirement: 41-REQ-4.5
        """
        from agent_fox.routing.duration import get_duration_hint

        # Insert an assessment so _predict_from_model can find a feature vector
        _insert_assessment(duration_db, assessment_id="neg1", spec_name="spec", archetype="coder")

        # Mock model that returns a negative prediction
        import numpy as np

        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([-50.0])

        hint = get_duration_hint(
            duration_db,
            "node1",
            "spec",
            "coder",
            "STANDARD",
            model=mock_model,
        )
        assert hint.predicted_ms >= 1


# ---------------------------------------------------------------------------
# TS-41-7, TS-41-8: Historical Median Computation
# ---------------------------------------------------------------------------


class TestHistoricalMedian:
    """Tests for _get_historical_median() median calculation.

    Test Spec: TS-41-7, TS-41-8
    """

    def test_median_odd_count(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-7: Median of odd count returns middle value.

        Requirement: 41-REQ-2.3
        """
        from agent_fox.routing.duration import _get_historical_median

        aid = _insert_assessment(duration_db, assessment_id="med_odd", spec_name="spec")
        # 11 outcomes with durations [10, 20, ..., 110]
        for i in range(1, 12):
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=i * 10)

        median = _get_historical_median(duration_db, "spec", "coder", min_outcomes=5)
        assert median == 60  # 6th value in sorted [10..110]

    def test_median_even_count(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-8: Median of even count returns integer average of two middle values.

        Requirement: 41-REQ-2.3
        """
        from agent_fox.routing.duration import _get_historical_median

        aid = _insert_assessment(duration_db, assessment_id="med_even", spec_name="spec")
        # 10 outcomes with durations [10, 20, ..., 100]
        for i in range(1, 11):
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=i * 10)

        median = _get_historical_median(duration_db, "spec", "coder", min_outcomes=5)
        assert median == 55  # (50 + 60) // 2


# ---------------------------------------------------------------------------
# TS-41-13: Feature Vector Extraction
# ---------------------------------------------------------------------------


class TestFeatureVector:
    """Tests for _feature_vector_to_array() JSON parsing.

    Test Spec: TS-41-13
    """

    def test_feature_vector_extraction(self) -> None:
        """TS-41-13: Feature vector extraction produces correct array.

        Requirement: 41-REQ-4.3
        """
        from agent_fox.routing.duration import _feature_vector_to_array

        fv_json = json.dumps(
            {
                "subtask_count": 4,
                "spec_word_count": 200,
                "has_property_tests": True,
                "edge_case_count": 3,
                "dependency_count": 2,
            }
        )
        result = _feature_vector_to_array(fv_json)
        assert result == [4.0, 200.0, 1.0, 3.0, 2.0]


# ---------------------------------------------------------------------------
# TS-41-11, TS-41-12: Regression Model Training
# ---------------------------------------------------------------------------


class TestTrainDurationModel:
    """Tests for train_duration_model() function.

    Test Spec: TS-41-11, TS-41-12
    """

    def _populate_outcomes(
        self,
        conn: duckdb.DuckDBPyConnection,
        n: int = 35,
    ) -> None:
        """Insert n execution outcomes with feature vectors and durations."""
        for i in range(n):
            aid = str(uuid.uuid4())
            _insert_assessment(
                conn,
                assessment_id=aid,
                spec_name=f"spec_{i % 5}",
                archetype="coder",
                task_group=i % 3 + 1,
            )
            _insert_outcome(conn, assessment_id=aid, duration_ms=(i + 1) * 10_000)

    def test_model_training_success(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-11: Model training succeeds with sufficient outcomes.

        Requirement: 41-REQ-4.1
        """
        from sklearn.linear_model import LinearRegression  # type: ignore[import-untyped]

        from agent_fox.routing.duration import train_duration_model

        self._populate_outcomes(duration_db, n=35)
        model = train_duration_model(duration_db, min_outcomes=30)
        assert model is not None
        assert isinstance(model, LinearRegression)

    def test_model_training_insufficient_data(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-12: Model returns None with insufficient outcomes.

        Requirement: 41-REQ-4.2
        """
        from agent_fox.routing.duration import train_duration_model

        self._populate_outcomes(duration_db, n=10)
        model = train_duration_model(duration_db, min_outcomes=30)
        assert model is None


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for duration hint computation.

    Test Spec: TS-41-E3, TS-41-E4, TS-41-E5
    """

    def test_duckdb_query_failure_in_historical(self) -> None:
        """TS-41-E3: None returned on DuckDB query error.

        Requirement: 41-REQ-2.E1
        """
        from agent_fox.routing.duration import _get_historical_median

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = duckdb.Error("query failed")

        result = _get_historical_median(mock_conn, "spec", "coder", 10)
        assert result is None

    def test_regression_predict_failure_fallthrough(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-41-E4: Fallthrough to historical when model.predict() fails.

        Requirement: 41-REQ-4.E1
        """
        from agent_fox.routing.duration import get_duration_hint

        # Insert enough data for historical median
        aid = _insert_assessment(duration_db, assessment_id="ep1", spec_name="spec", archetype="coder")
        for i in range(15):
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=(i + 1) * 100)

        # Mock model whose predict() raises
        broken_model = MagicMock()
        broken_model.predict.side_effect = RuntimeError("predict failed")

        hint = get_duration_hint(
            duration_db,
            "node1",
            "spec",
            "coder",
            "STANDARD",
            model=broken_model,
            min_outcomes=5,
        )
        assert hint.source != "regression"

    def test_unparseable_feature_vector(self) -> None:
        """TS-41-E5: None returned for malformed feature vector JSON.

        Requirement: 41-REQ-4.E3
        """
        from agent_fox.routing.duration import _feature_vector_to_array

        result = _feature_vector_to_array("not valid json")
        assert result is None

    @pytest.fixture
    def duration_db(self) -> duckdb.DuckDBPyConnection:
        """In-memory DuckDB for edge case tests."""
        conn = duckdb.connect(":memory:")
        _create_routing_schema(conn)
        return conn
