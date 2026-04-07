"""Property tests for confidence normalization.

Test Spec: TS-37-P1 through TS-37-P6
Properties: 1-6 from design.md
Requirements: 37-REQ-1.*, 37-REQ-2.*, 37-REQ-3.*, 37-REQ-5.3
"""

from __future__ import annotations

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.facts import Fact


class TestConfidenceAlwaysInRange:
    """TS-37-P1: parse_confidence always returns [0.0, 1.0].

    Property 1 from design.md.
    Validates: 37-REQ-1.1, 37-REQ-1.3, 37-REQ-1.E1, 37-REQ-1.E2
    """

    @given(value=st.floats(allow_nan=False))
    def test_float_input(self, value: float) -> None:
        from agent_fox.knowledge.facts import parse_confidence

        result = parse_confidence(value)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    @given(value=st.integers(min_value=-1000, max_value=1000))
    def test_int_input(self, value: int) -> None:
        from agent_fox.knowledge.facts import parse_confidence

        result = parse_confidence(value)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    @given(value=st.text(max_size=20))
    def test_string_input(self, value: str) -> None:
        from agent_fox.knowledge.facts import parse_confidence

        result = parse_confidence(value)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_none_input(self) -> None:
        from agent_fox.knowledge.facts import parse_confidence

        result = parse_confidence(None)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestCanonicalMappingDeterministic:
    """TS-37-P2: Canonical strings always map to the same float.

    Property 2 from design.md.
    Validates: 37-REQ-1.2, 37-REQ-2.2, 37-REQ-3.2
    """

    @given(s=st.sampled_from(["high", "medium", "low"]))
    def test_canonical_mapping_consistent(self, s: str) -> None:
        from agent_fox.knowledge.facts import CONFIDENCE_MAP, parse_confidence

        assert parse_confidence(s) == CONFIDENCE_MAP[s]


class TestJsonlRoundTrip:
    """TS-37-P3: JSONL round-trip preserves confidence.

    Property 4 from design.md.
    Validates: 37-REQ-3.1, 37-REQ-3.3
    """

    @given(conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=50)
    def test_round_trip_preserves_confidence(self, conf: float) -> None:
        from agent_fox.knowledge.store import _dict_to_fact, _fact_to_dict

        fact = Fact(
            id="round-trip-test",
            content="test content",
            category="pattern",
            spec_name="test_spec",
            keywords=["test"],
            confidence=conf,
            created_at="2026-03-01T00:00:00+00:00",
        )
        data = _fact_to_dict(fact)
        loaded = _dict_to_fact(data)
        assert abs(loaded.confidence - conf) < 1e-9


class TestMigrationPreservesRowCount:
    """TS-37-P4: Migration never changes the number of rows.

    Property 3 from design.md.
    Validates: 37-REQ-2.1, 37-REQ-2.3
    """

    @given(
        confidences=st.lists(
            st.sampled_from(["high", "medium", "low", None]),
            min_size=0,
            max_size=20,
        )
    )
    @settings(max_examples=30)
    def test_row_count_unchanged(self, confidences: list[str | None]) -> None:
        import uuid

        from tests.unit.knowledge.conftest import create_schema

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        for conf in confidences:
            fid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO memory_facts (id, content, category, spec_name,
                                          confidence, created_at)
                VALUES (?::UUID, 'test', 'gotcha', 'test_spec', ?, CURRENT_TIMESTAMP)
                """,
                [fid, conf],
            )

        count_before = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]  # type: ignore[index]

        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)

        count_after = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]  # type: ignore[index]
        assert count_before == count_after

        conn.close()


class TestBackwardCompatStringLoading:
    """TS-37-P5: Old-format JSONL with string confidence loads correctly.

    Property 5 from design.md.
    Validates: 37-REQ-3.1, 37-REQ-3.2
    """

    @given(s=st.sampled_from(["high", "medium", "low"]))
    @settings(max_examples=10)
    def test_string_confidence_loaded_as_float(self, s: str) -> None:
        from agent_fox.knowledge.facts import CONFIDENCE_MAP
        from agent_fox.knowledge.store import _dict_to_fact

        entry = {
            "id": "compat-test",
            "content": "test content",
            "category": "pattern",
            "spec_name": "test_spec",
            "keywords": ["test"],
            "confidence": s,
            "created_at": "2026-03-01T00:00:00+00:00",
            "supersedes": None,
        }
        fact = _dict_to_fact(entry)
        assert fact.confidence == CONFIDENCE_MAP[s]


class TestThresholdFilterCorrectness:
    """TS-37-P6: Filtering at threshold 0.5 partitions correctly.

    Property 6 from design.md.
    Validates: 37-REQ-5.3
    """

    @given(
        confidences=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=0,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_filter_partitions_correctly(self, confidences: list[float]) -> None:
        from agent_fox.fix.analyzer import Improvement, filter_improvements

        improvements = [
            Improvement(
                id=f"IMP-{i}",
                tier="quick_win",
                title=f"Improvement {i}",
                description="desc",
                files=["test.py"],
                impact="medium",
                confidence=conf,
            )
            for i, conf in enumerate(confidences)
        ]

        filtered = filter_improvements(improvements)
        assert all(i.confidence >= 0.5 for i in filtered)

        filtered_ids = {i.id for i in filtered}
        excluded = [i for i in improvements if i.id not in filtered_ids]
        assert all(i.confidence < 0.5 for i in excluded)
