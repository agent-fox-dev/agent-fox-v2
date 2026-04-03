"""Property tests for duration-based task ordering.

Test Spec: TS-41-P1 through TS-41-P6
Correctness Properties: CP-1, CP-2, CP-3, CP-4, CP-6
"""

from __future__ import annotations

import json

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Node IDs: short alphanumeric strings
_node_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=10,
)

# Lists of unique node IDs (1-20 elements)
_node_ids_st = st.lists(
    _node_id_st,
    min_size=1,
    max_size=20,
    unique=True,
)

# Duration hints: positive integers
_duration_st = st.integers(min_value=1, max_value=10_000_000)


def _hints_for_subset(node_ids: list[str]) -> st.SearchStrategy[dict[str, int]]:
    """Generate a duration hints dict covering a random subset of node_ids."""
    return st.fixed_dictionaries(
        {},
        optional={nid: _duration_st for nid in node_ids},
    )


# ---------------------------------------------------------------------------
# TS-41-P1: Ordering Preserves Set Membership (CP-3)
# ---------------------------------------------------------------------------


class TestOrderingPreservesSetMembership:
    """TS-41-P1: order_by_duration() output contains exactly the same elements."""

    @given(data=st.data())
    @settings(max_examples=100)
    def test_preserves_set_membership(self, data: st.DataObject) -> None:
        from agent_fox.routing.duration import order_by_duration

        node_ids = data.draw(_node_ids_st)
        hints = data.draw(_hints_for_subset(node_ids))

        result = order_by_duration(node_ids, hints)
        assert set(result) == set(node_ids)
        assert len(result) == len(node_ids)


# ---------------------------------------------------------------------------
# TS-41-P2: Ordering Is Deterministic (CP-2)
# ---------------------------------------------------------------------------


class TestOrderingIsDeterministic:
    """TS-41-P2: Same inputs always produce same output."""

    @given(data=st.data())
    @settings(max_examples=100)
    def test_deterministic(self, data: st.DataObject) -> None:
        from agent_fox.routing.duration import order_by_duration

        node_ids = data.draw(_node_ids_st)
        hints = data.draw(_hints_for_subset(node_ids))

        result1 = order_by_duration(node_ids, hints)
        result2 = order_by_duration(node_ids, hints)
        assert result1 == result2


# ---------------------------------------------------------------------------
# TS-41-P3: Ordering Is Descending (CP-1)
# ---------------------------------------------------------------------------


class TestOrderingIsDescending:
    """TS-41-P3: Consecutive hinted pairs have duration >= next."""

    @given(data=st.data())
    @settings(max_examples=100)
    def test_descending_order(self, data: st.DataObject) -> None:
        from agent_fox.routing.duration import order_by_duration

        node_ids = data.draw(_node_ids_st)
        # All nodes have hints for this test
        hints = {nid: data.draw(_duration_st) for nid in node_ids}

        result = order_by_duration(node_ids, hints)
        for i in range(len(result) - 1):
            if result[i] in hints and result[i + 1] in hints:
                assert hints[result[i]] >= hints[result[i + 1]]


# ---------------------------------------------------------------------------
# TS-41-P4: Duration Predictions Are Positive (CP-4)
# ---------------------------------------------------------------------------


class TestDurationPredictionsArePositive:
    """TS-41-P4: DurationHint.predicted_ms is always >= 1."""

    @given(
        archetype=st.sampled_from(["coder", "skeptic", "oracle", "verifier", "librarian", "cartographer"]),
        tier=st.sampled_from(["STANDARD", "ADVANCED", "MAX"]),
        spec_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_positive_predictions(self, archetype: str, tier: str, spec_name: str) -> None:
        from agent_fox.routing.duration import get_duration_hint

        conn = duckdb.connect(":memory:")
        # Create minimal schema
        conn.execute("""
            CREATE TABLE complexity_assessments (
                id VARCHAR PRIMARY KEY,
                node_id VARCHAR NOT NULL,
                spec_name VARCHAR NOT NULL,
                task_group INTEGER NOT NULL,
                predicted_tier VARCHAR NOT NULL,
                confidence FLOAT NOT NULL,
                assessment_method VARCHAR NOT NULL,
                feature_vector JSON NOT NULL,
                tier_ceiling VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
            );
            CREATE TABLE execution_outcomes (
                id VARCHAR PRIMARY KEY,
                assessment_id VARCHAR NOT NULL,
                actual_tier VARCHAR NOT NULL,
                total_tokens INTEGER NOT NULL,
                total_cost FLOAT NOT NULL,
                duration_ms INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL,
                escalation_count INTEGER NOT NULL,
                outcome VARCHAR NOT NULL,
                files_touched_count INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
            );
        """)

        hint = get_duration_hint(conn, "node1", spec_name, archetype, tier)
        assert hint.predicted_ms >= 1
        conn.close()


# ---------------------------------------------------------------------------
# TS-41-P5: Preset Coverage (CP-6)
# ---------------------------------------------------------------------------


class TestPresetCoverage:
    """TS-41-P5: Every archetype has entries for all three tiers."""

    def test_preset_coverage(self) -> None:
        from agent_fox.routing.duration import DURATION_PRESETS

        archetypes = [
            "coder",
            "skeptic",
            "oracle",
            "verifier",
            "librarian",
            "cartographer",
        ]
        tiers = ["STANDARD", "ADVANCED", "MAX"]

        for arch in archetypes:
            for tier in tiers:
                assert DURATION_PRESETS[arch][tier] > 0


# ---------------------------------------------------------------------------
# TS-41-P6: Feature Vector Array Length
# ---------------------------------------------------------------------------


class TestFeatureVectorArrayLength:
    """TS-41-P6: _feature_vector_to_array() returns list of 5 floats or None."""

    @given(
        fv_dict=st.fixed_dictionaries(
            {},
            optional={
                "subtask_count": st.integers(min_value=0, max_value=100),
                "spec_word_count": st.integers(min_value=0, max_value=10000),
                "has_property_tests": st.booleans(),
                "edge_case_count": st.integers(min_value=0, max_value=50),
                "dependency_count": st.integers(min_value=0, max_value=20),
            },
        )
    )
    @settings(max_examples=100)
    def test_array_length(self, fv_dict: dict) -> None:
        from agent_fox.routing.duration import _feature_vector_to_array

        result = _feature_vector_to_array(json.dumps(fv_dict))
        assert result is None or (isinstance(result, list) and len(result) == 5)
