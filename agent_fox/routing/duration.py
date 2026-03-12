"""Duration hint computation: historical median, preset fallback, regression.

Provides predicted execution durations for task nodes to enable
duration-based task ordering in the dispatch system.

Requirements: 39-REQ-1.1, 39-REQ-1.2, 39-REQ-1.3, 39-REQ-1.4, 39-REQ-1.E1,
              39-REQ-2.1, 39-REQ-2.2
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import duckdb

from agent_fox.routing.duration_presets import DEFAULT_DURATION_MS, DURATION_PRESETS

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from sklearn.linear_model import LinearRegression
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    LinearRegression = None  # type: ignore[assignment,misc]


@dataclass
class DurationHint:
    """Predicted duration for a task node.

    Attributes:
        node_id: The task node identifier.
        predicted_ms: Predicted execution duration in milliseconds.
        source: Origin of the prediction — one of
            ``"historical"``, ``"regression"``, ``"preset"``, ``"default"``.
    """

    node_id: str
    predicted_ms: int
    source: str  # "historical" | "regression" | "preset" | "default"


def get_duration_hint(
    conn: duckdb.DuckDBPyConnection,
    node_id: str,
    spec_name: str,
    archetype: str,
    tier: str,
    min_outcomes: int = 10,
    model: object | None = None,
) -> DurationHint:
    """Get predicted duration for a task node.

    Source precedence: regression > historical median > preset > default.

    Args:
        conn: DuckDB connection with execution_outcomes table.
        node_id: Task node identifier.
        spec_name: Specification name for historical lookup.
        archetype: Archetype name (e.g. "coder", "skeptic").
        tier: Complexity tier (e.g. "STANDARD", "ADVANCED").
        min_outcomes: Minimum historical outcomes required to use
            historical median (default: 10).
        model: Optional trained regression model. If provided and valid,
            regression predictions take highest priority.

    Returns:
        A DurationHint with the predicted duration and its source.

    Requirements: 39-REQ-1.2, 39-REQ-1.4, 39-REQ-1.E1, 39-REQ-2.2
    """
    # 1. Try regression model (highest priority)
    if model is not None and LinearRegression is not None:
        prediction = _predict_from_model(conn, model, spec_name, archetype)
        if prediction is not None:
            return DurationHint(
                node_id=node_id,
                predicted_ms=max(1, int(prediction)),
                source="regression",
            )

    # 2. Try historical median
    historical = _get_historical_median(conn, spec_name, archetype, min_outcomes)
    if historical is not None:
        return DurationHint(
            node_id=node_id,
            predicted_ms=historical,
            source="historical",
        )

    # 3. Try presets
    preset = DURATION_PRESETS.get(archetype, {}).get(tier)
    if preset is not None:
        return DurationHint(
            node_id=node_id,
            predicted_ms=preset,
            source="preset",
        )

    # 4. Default fallback
    return DurationHint(
        node_id=node_id,
        predicted_ms=DEFAULT_DURATION_MS,
        source="default",
    )


def _get_historical_median(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    archetype: str,
    min_outcomes: int,
) -> int | None:
    """Query historical median duration for a spec+archetype pair.

    Returns None if fewer than min_outcomes exist.
    """
    try:
        result = conn.execute(
            """
            SELECT eo.duration_ms
            FROM execution_outcomes eo
            JOIN complexity_assessments ca ON eo.assessment_id = ca.id
            WHERE ca.spec_name = ?
              AND json_extract_string(ca.feature_vector, '$.archetype') = ?
            ORDER BY eo.duration_ms
            """,
            [spec_name, archetype],
        ).fetchall()
    except duckdb.Error:
        return None

    if len(result) < min_outcomes:
        return None

    durations = sorted(row[0] for row in result)
    n = len(durations)
    if n % 2 == 1:
        return durations[n // 2]
    return (durations[n // 2 - 1] + durations[n // 2]) // 2


def _predict_from_model(
    conn: duckdb.DuckDBPyConnection,
    model: object,
    spec_name: str,
    archetype: str,
) -> float | None:
    """Use a trained regression model to predict duration.

    Extracts a feature vector from the most recent assessment for the
    spec+archetype and feeds it to the model.
    """
    if np is None or LinearRegression is None:
        return None  # pragma: no cover

    try:
        row = conn.execute(
            """
            SELECT ca.feature_vector
            FROM complexity_assessments ca
            WHERE ca.spec_name = ?
              AND json_extract_string(ca.feature_vector, '$.archetype') = ?
            ORDER BY ca.created_at DESC
            LIMIT 1
            """,
            [spec_name, archetype],
        ).fetchone()
    except duckdb.Error:
        return None

    if row is None:
        return None

    fv = _feature_vector_to_array(row[0])
    if fv is None:
        return None

    try:
        prediction = model.predict(np.array([fv]))[0]  # type: ignore[union-attr]
        return float(prediction)
    except Exception:
        logger.warning("Regression prediction failed", exc_info=True)
        return None


def _feature_vector_to_array(fv_raw: str | dict) -> list[float] | None:
    """Convert a JSON feature vector to a numeric array for regression."""
    if isinstance(fv_raw, str):
        try:
            fv = json.loads(fv_raw)
        except json.JSONDecodeError:
            return None
    else:
        fv = fv_raw

    try:
        return [
            float(fv.get("subtask_count", 0)),
            float(fv.get("spec_word_count", 0)),
            float(1 if fv.get("has_property_tests") else 0),
            float(fv.get("edge_case_count", 0)),
            float(fv.get("dependency_count", 0)),
        ]
    except (TypeError, ValueError):
        return None


def train_duration_model(
    conn: duckdb.DuckDBPyConnection,
    min_outcomes: int = 30,
) -> LinearRegression | None:
    """Train a duration regression model from execution outcomes.

    Extracts feature vectors from complexity_assessments and pairs them
    with actual durations from execution_outcomes. Returns None if fewer
    than min_outcomes records exist or if scikit-learn is unavailable.

    Args:
        conn: DuckDB connection.
        min_outcomes: Minimum outcomes required to train (default: 30).

    Returns:
        A trained LinearRegression model, or None.

    Requirements: 39-REQ-2.1
    """
    if np is None or LinearRegression is None:
        return None  # pragma: no cover

    try:
        rows = conn.execute(
            """
            SELECT ca.feature_vector, eo.duration_ms
            FROM execution_outcomes eo
            JOIN complexity_assessments ca ON eo.assessment_id = ca.id
            """
        ).fetchall()
    except duckdb.Error:
        return None

    if len(rows) < min_outcomes:
        return None

    features = []
    targets = []
    for fv_raw, duration_ms in rows:
        arr = _feature_vector_to_array(fv_raw)
        if arr is not None:
            features.append(arr)
            targets.append(float(duration_ms))

    if len(features) < min_outcomes:
        return None

    X = np.array(features)
    y = np.array(targets)

    model = LinearRegression()
    model.fit(X, y)
    return model


def order_by_duration(
    node_ids: list[str],
    duration_hints: dict[str, int],
) -> list[str]:
    """Sort task node IDs by predicted duration descending.

    Nodes with higher predicted durations come first. Ties are broken
    alphabetically. Nodes without hints are placed last, sorted
    alphabetically.

    Args:
        node_ids: List of task node identifiers.
        duration_hints: Mapping of node_id to predicted duration in ms.

    Returns:
        Sorted list of node IDs.

    Requirements: 39-REQ-1.1, 39-REQ-1.3
    """
    # Partition into nodes with and without hints
    with_hints = [
        (nid, duration_hints[nid]) for nid in node_ids if nid in duration_hints
    ]
    without_hints = sorted(nid for nid in node_ids if nid not in duration_hints)

    # Sort by duration descending, then alphabetically for ties
    with_hints.sort(key=lambda t: (-t[1], t[0]))

    return [nid for nid, _ in with_hints] + without_hints
