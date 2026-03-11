"""Tests for duration-based task ordering and duration hints.

Test Spec: TS-39-1 through TS-39-7, TS-39-E1
Requirements: 39-REQ-1.1 through 39-REQ-1.E1, 39-REQ-2.1 through 39-REQ-2.3
"""

from __future__ import annotations

import uuid
from datetime import datetime

import duckdb
import pytest

from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_routing_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the routing-related tables needed for duration tests."""
    create_schema(conn)
    # Ensure complexity_assessments and execution_outcomes tables exist
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
) -> str:
    """Insert a complexity assessment and return its id."""
    fv = (
        '{"subtask_count": 5, "spec_word_count": 200, '
        '"has_property_tests": false, "edge_case_count": 1, '
        '"dependency_count": 0, "archetype": "' + archetype + '"}'
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
            fv,
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
# TS-39-1: Duration Ordering Descending
# ---------------------------------------------------------------------------


class TestDurationOrdering:
    """TS-39-1: Verify ready tasks are sorted by predicted duration descending.

    Requirement: 39-REQ-1.1
    """

    def test_descending_order(self) -> None:
        """Order is [B, C, A] for durations 180s, 120s, 60s."""
        from agent_fox.routing.duration import order_by_duration

        hints = {"A": 60_000, "B": 180_000, "C": 120_000}
        ordered = order_by_duration(["A", "B", "C"], hints)
        assert ordered == ["B", "C", "A"]

    def test_ties_broken_alphabetically(self) -> None:
        """Equal durations are ordered alphabetically."""
        from agent_fox.routing.duration import order_by_duration

        hints = {"Z": 100_000, "A": 100_000, "M": 100_000}
        ordered = order_by_duration(["Z", "A", "M"], hints)
        assert ordered == ["A", "M", "Z"]

    def test_missing_hints_sorted_last_alphabetically(self) -> None:
        """Nodes without hints go after nodes with hints, alphabetically."""
        from agent_fox.routing.duration import order_by_duration

        hints = {"B": 180_000}
        ordered = order_by_duration(["A", "B", "C"], hints)
        assert ordered[0] == "B"
        # A and C have no hints, should be sorted alphabetically after B
        assert ordered[1:] == ["A", "C"]


# ---------------------------------------------------------------------------
# TS-39-2: Duration Hint From Historical Median
# ---------------------------------------------------------------------------


class TestDurationHints:
    """TS-39-2, TS-39-3, TS-39-4, TS-39-E1: Duration hint sources."""

    def test_historical_median(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-2: Historical median used when >= min_outcomes exist.

        Requirement: 39-REQ-1.2
        """
        from agent_fox.routing.duration import DurationHint, get_duration_hint

        # Insert 15 outcomes with durations for median calculation
        aid = _insert_assessment(duration_db, assessment_id="a1", spec_name="foo")
        durations = [100, 200, 300, 400, 500] * 3  # 15 outcomes, median = 300
        for d in durations:
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=d * 1000)

        hint = get_duration_hint(
            duration_db, "node1", "foo", "coder", "STANDARD", min_outcomes=10
        )
        assert isinstance(hint, DurationHint)
        assert hint.predicted_ms == 300_000
        assert hint.source == "historical"

    def test_preset_fallback(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-3: Preset fallback when no historical data.

        Requirement: 39-REQ-1.3
        """
        from agent_fox.routing.duration import DurationHint, get_duration_hint
        from agent_fox.routing.duration_presets import DURATION_PRESETS

        hint = get_duration_hint(
            duration_db, "node1", "foo", "coder", "STANDARD"
        )
        assert isinstance(hint, DurationHint)
        assert hint.predicted_ms == DURATION_PRESETS["coder"]["STANDARD"]
        assert hint.source == "preset"

    def test_returns_duration_hint(
        self, duration_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-39-4: get_duration_hint returns a DurationHint dataclass.

        Requirement: 39-REQ-1.4
        """
        from agent_fox.routing.duration import DurationHint, get_duration_hint

        hint = get_duration_hint(
            duration_db, "node1", "foo", "coder", "STANDARD"
        )
        assert isinstance(hint, DurationHint)
        assert isinstance(hint.predicted_ms, int)
        assert hint.predicted_ms > 0
        assert hint.source in ("historical", "regression", "preset", "default")

    def test_insufficient_outcomes(
        self, duration_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-39-E1: Fewer than min_outcomes uses presets.

        Requirement: 39-REQ-1.E1
        """
        from agent_fox.routing.duration import get_duration_hint
        from agent_fox.routing.duration_presets import DURATION_PRESETS

        # Insert only 5 outcomes (below default threshold of 10)
        aid = _insert_assessment(duration_db, assessment_id="a2", spec_name="foo")
        for d in [100, 200, 300, 400, 500]:
            _insert_outcome(duration_db, assessment_id=aid, duration_ms=d * 1000)

        hint = get_duration_hint(
            duration_db, "node1", "foo", "coder", "STANDARD", min_outcomes=10
        )
        assert hint.source == "preset"
        assert hint.predicted_ms == DURATION_PRESETS["coder"]["STANDARD"]

    def test_default_fallback_unknown_archetype(
        self, duration_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Default fallback for unknown archetype/tier not in presets."""
        from agent_fox.routing.duration import get_duration_hint
        from agent_fox.routing.duration_presets import DEFAULT_DURATION_MS

        hint = get_duration_hint(
            duration_db, "node1", "foo", "unknown_archetype", "UNKNOWN_TIER"
        )
        assert hint.source == "default"
        assert hint.predicted_ms == DEFAULT_DURATION_MS


# ---------------------------------------------------------------------------
# TS-39-5, TS-39-6, TS-39-7: Duration Regression Model
# ---------------------------------------------------------------------------


class TestDurationRegression:
    """TS-39-5, TS-39-6, TS-39-7: Regression model tests.

    Requirements: 39-REQ-2.1, 39-REQ-2.2, 39-REQ-2.3
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
            # Duration varies with some pattern for regression
            _insert_outcome(
                conn, assessment_id=aid, duration_ms=(i + 1) * 10_000
            )

    def test_model_training(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-5: Regression model trains with sufficient outcomes.

        Requirement: 39-REQ-2.1
        """
        from agent_fox.routing.duration import train_duration_model
        from sklearn.linear_model import LinearRegression

        self._populate_outcomes(duration_db, n=35)
        model = train_duration_model(duration_db, min_outcomes=30)
        assert model is not None
        assert isinstance(model, LinearRegression)

    def test_model_returns_none_insufficient(
        self, duration_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Model returns None when fewer than min_outcomes exist."""
        from agent_fox.routing.duration import train_duration_model

        self._populate_outcomes(duration_db, n=10)
        model = train_duration_model(duration_db, min_outcomes=30)
        assert model is None

    def test_regression_priority(
        self, duration_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-39-6: Regression prediction used when model available.

        Requirement: 39-REQ-2.2
        """
        from agent_fox.routing.duration import get_duration_hint, train_duration_model

        self._populate_outcomes(duration_db, n=35)
        model = train_duration_model(duration_db, min_outcomes=30)
        assert model is not None

        # get_duration_hint should use regression when model is available
        hint = get_duration_hint(
            duration_db,
            "node1",
            "spec_0",
            "coder",
            "STANDARD",
            model=model,
        )
        assert hint.source == "regression"
        assert hint.predicted_ms > 0

    def test_retraining(self, duration_db: duckdb.DuckDBPyConnection) -> None:
        """TS-39-7: Retrained model predictions differ from original.

        Requirement: 39-REQ-2.3
        """
        from agent_fox.routing.duration import train_duration_model

        self._populate_outcomes(duration_db, n=35)
        model_v1 = train_duration_model(duration_db, min_outcomes=30)
        assert model_v1 is not None

        # Add more outcomes with different durations
        for i in range(5):
            aid = str(uuid.uuid4())
            _insert_assessment(
                duration_db,
                assessment_id=aid,
                spec_name="spec_new",
                archetype="coder",
                task_group=1,
            )
            _insert_outcome(
                duration_db, assessment_id=aid, duration_ms=999_999
            )

        model_v2 = train_duration_model(duration_db, min_outcomes=30)
        assert model_v2 is not None

        # Models should give different predictions on the same input
        import numpy as np

        feature_vector = np.array([[5, 200, 0, 1, 0]])
        pred_v1 = model_v1.predict(feature_vector)[0]
        pred_v2 = model_v2.predict(feature_vector)[0]
        assert pred_v1 != pytest.approx(pred_v2, rel=0.01)
