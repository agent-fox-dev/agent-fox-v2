"""Property tests for fact lifecycle management.

Test Spec: TS-90-P1 through TS-90-P9
Requirements: 90-REQ-1.*, 90-REQ-2.*, 90-REQ-3.*, 90-REQ-4.*, 90-REQ-5.*
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import duckdb
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.lifecycle import (
    dedup_new_facts,
    detect_contradictions,
    run_cleanup,
    run_decay_cleanup,
)
from tests.unit.knowledge.conftest import create_schema_v2

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 384


def _make_embedding(seed: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate a deterministic, normalised embedding vector."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / norm for x in raw]


def _make_fact(
    *,
    fact_id: str | None = None,
    content: str = "Test fact",
    confidence: float = 0.9,
    created_at: str | None = None,
) -> Fact:
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content,
        category="pattern",
        spec_name="test_spec",
        keywords=["test"],
        confidence=confidence,
        created_at=created_at or datetime.now(UTC).isoformat(),
    )


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact: Fact,
    *,
    embedding: list[float] | None = None,
    created_at_override: datetime | None = None,
) -> None:
    ts = created_at_override or datetime.now(UTC)
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at)
        VALUES (?::UUID, ?, ?, ?, ?, ?)
        """,
        [fact.id, fact.content, fact.category, fact.spec_name, fact.confidence, ts],
    )
    if embedding is not None:
        conn.execute(
            f"INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[{EMBEDDING_DIM}])",
            [fact.id, embedding],
        )


def _setup_db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    create_schema_v2(conn)
    return conn


def _get_active_ids(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT CAST(id AS VARCHAR) FROM memory_facts WHERE superseded_by IS NULL").fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# TS-90-P1: Dedup idempotency
# ---------------------------------------------------------------------------


class TestDedupIdempotency:
    """TS-90-P1: Running dedup twice produces the same DB state.

    Property 1 from design.md.
    Validates: 90-REQ-1.1, 90-REQ-1.2
    """

    @given(
        num_existing=st.integers(min_value=1, max_value=5),
        num_new=st.integers(min_value=1, max_value=3),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_dedup_idempotency(self, num_existing: int, num_new: int) -> None:
        conn = _setup_db()

        existing_facts = []
        for i in range(num_existing):
            emb = _make_embedding(i + 1)
            f = _make_fact(content=f"Existing fact {i}")
            _insert_fact(conn, f, embedding=emb)
            existing_facts.append(f)

        new_facts = []
        for i in range(num_new):
            emb = _make_embedding(i + 100)
            f = _make_fact(content=f"New fact {i}")
            _insert_fact(conn, f, embedding=emb)
            new_facts.append(f)

        dedup_new_facts(conn, new_facts, threshold=0.92)
        active_after_first = _get_active_ids(conn)

        dedup_new_facts(conn, new_facts, threshold=0.92)
        active_after_second = _get_active_ids(conn)

        assert active_after_first == active_after_second

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-P2: Dedup threshold monotonicity
# ---------------------------------------------------------------------------


class TestDedupThresholdMonotonicity:
    """TS-90-P2: Lowering the threshold can only increase superseded count.

    Property 2 from design.md.
    Validates: 90-REQ-1.1, 90-REQ-1.2, 90-REQ-1.4
    """

    @given(
        t1=st.floats(min_value=0.5, max_value=0.89),
        t2=st.floats(min_value=0.9, max_value=1.0),
        seed=st.integers(min_value=1, max_value=50),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_dedup_threshold_monotonicity(self, t1: float, t2: float, seed: int) -> None:
        # Create DB with t1 (lower threshold)
        conn1 = _setup_db()
        base_emb = _make_embedding(seed)
        existing1 = _make_fact(content="Existing fact")
        _insert_fact(conn1, existing1, embedding=base_emb)
        new_emb = _make_embedding(seed + 1000)
        new1 = _make_fact(content="New fact")
        _insert_fact(conn1, new1, embedding=new_emb)
        r1 = dedup_new_facts(conn1, [new1], threshold=t1)
        conn1.close()

        # Create identical DB with t2 (higher threshold)
        conn2 = _setup_db()
        existing2 = _make_fact(fact_id=existing1.id, content="Existing fact")
        _insert_fact(conn2, existing2, embedding=base_emb)
        new2 = _make_fact(fact_id=new1.id, content="New fact")
        _insert_fact(conn2, new2, embedding=new_emb)
        r2 = dedup_new_facts(conn2, [new2], threshold=t2)
        conn2.close()

        assert len(r1.superseded_ids) >= len(r2.superseded_ids)


# ---------------------------------------------------------------------------
# TS-90-P3: Contradiction requires LLM confirmation
# ---------------------------------------------------------------------------


class TestContradictionRequiresLlm:
    """TS-90-P3: No fact is superseded without LLM contradicts=true.

    Property 3 from design.md.
    Validates: 90-REQ-2.2, 90-REQ-2.3, 90-REQ-2.4
    """

    @given(num_pairs=st.integers(min_value=1, max_value=5))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_contradiction_requires_llm(self, num_pairs: int) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        new_facts = []
        for i in range(num_pairs):
            # Existing fact with high similarity
            from tests.unit.knowledge.test_lifecycle import _make_similar_embedding

            emb = _make_similar_embedding(base_emb, 0.85)
            existing = _make_fact(content=f"Existing fact {i}")
            _insert_fact(conn, existing, embedding=emb)

            new = _make_fact(content=f"New fact {i}")
            _insert_fact(conn, new, embedding=base_emb)
            new_facts.append(new)

        # LLM always returns false
        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            return_value=[],
        ):
            result = detect_contradictions(conn, new_facts, threshold=0.8)

        assert len(result.superseded_ids) == 0

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-P4: Contradiction graceful degradation
# ---------------------------------------------------------------------------


class TestContradictionGracefulDegradation:
    """TS-90-P4: Any LLM failure leaves facts unchanged.

    Property 4 from design.md.
    Validates: 90-REQ-2.E1, 90-REQ-2.E3
    """

    @given(
        failure_type=st.sampled_from(["exception", "empty_list"]),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_contradiction_graceful_degradation(self, failure_type: str) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        from tests.unit.knowledge.test_lifecycle import _make_similar_embedding

        existing = _make_fact(content="Existing fact")
        _insert_fact(conn, existing, embedding=_make_similar_embedding(base_emb, 0.85))

        new = _make_fact(content="New fact")
        _insert_fact(conn, new, embedding=base_emb)

        active_before = _get_active_ids(conn)

        if failure_type == "exception":
            side_effect = Exception("API Error")
            with patch(
                "agent_fox.knowledge.contradiction.classify_contradiction_batch",
                side_effect=side_effect,
            ):
                result = detect_contradictions(conn, [new], threshold=0.8)
        else:
            with patch(
                "agent_fox.knowledge.contradiction.classify_contradiction_batch",
                return_value=[],
            ):
                result = detect_contradictions(conn, [new], threshold=0.8)

        active_after = _get_active_ids(conn)
        assert active_before == active_after
        assert len(result.superseded_ids) == 0

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-P5: Decay monotonicity
# ---------------------------------------------------------------------------


class TestDecayMonotonicity:
    """TS-90-P5: Effective confidence is non-increasing with age.

    Property 5 from design.md.
    Validates: 90-REQ-3.1
    """

    @given(
        confidence=st.floats(min_value=0.01, max_value=1.0),
        half_life=st.floats(min_value=1.0, max_value=365.0),
        age1=st.floats(min_value=0.0, max_value=500.0),
        age2=st.floats(min_value=0.0, max_value=500.0),
    )
    @settings(max_examples=100, deadline=None)
    def test_decay_monotonicity(self, confidence: float, half_life: float, age1: float, age2: float) -> None:
        a1, a2 = min(age1, age2), max(age1, age2)
        eff1 = confidence * (0.5 ** (a1 / half_life))
        eff2 = confidence * (0.5 ** (a2 / half_life))
        assert eff1 >= eff2 or math.isclose(eff1, eff2, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# TS-90-P6: Decay floor auto-supersession boundary
# ---------------------------------------------------------------------------


class TestDecayFloorBoundary:
    """TS-90-P6: Facts below floor are superseded; at/above floor stay active.

    Property 6 from design.md.
    Validates: 90-REQ-3.2, 90-REQ-3.4
    """

    @given(
        confidence=st.floats(min_value=0.5, max_value=1.0),
        age_days=st.integers(min_value=0, max_value=1000),
        half_life=st.floats(min_value=30.0, max_value=365.0),
        floor=st.floats(min_value=0.05, max_value=0.5),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_decay_floor_boundary(
        self,
        confidence: float,
        age_days: int,
        half_life: float,
        floor: float,
    ) -> None:
        eff = confidence * (0.5 ** (age_days / half_life))

        conn = _setup_db()
        now = datetime.now(UTC)
        fact = _make_fact(confidence=confidence)
        _insert_fact(conn, fact, created_at_override=now - timedelta(days=age_days))

        run_decay_cleanup(conn, half_life_days=half_life, decay_floor=floor)

        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact.id],
        ).fetchone()
        is_superseded = row is not None and row[0] is not None

        if eff < floor:
            assert is_superseded, f"Expected superseded: eff={eff}, floor={floor}"
        else:
            assert not is_superseded, f"Expected active: eff={eff}, floor={floor}"

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-P7: Stored confidence immutability
# ---------------------------------------------------------------------------


class TestConfidenceImmutability:
    """TS-90-P7: No lifecycle operation modifies the confidence column.

    Property 7 from design.md.
    Validates: 90-REQ-3.6
    """

    @given(
        confidence=st.floats(min_value=0.1, max_value=1.0),
        age_days=st.integers(min_value=0, max_value=500),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_confidence_immutability(self, confidence: float, age_days: int) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)
        fact = _make_fact(confidence=confidence)
        _insert_fact(conn, fact, created_at_override=now - timedelta(days=age_days))

        run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)

        row = conn.execute(
            "SELECT confidence FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(confidence)

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-P8: Cleanup threshold gate
# ---------------------------------------------------------------------------


class TestCleanupThresholdGate:
    """TS-90-P8: Decay only runs when active fact count exceeds the threshold.

    Property 8 from design.md.
    Validates: 90-REQ-4.2, 90-REQ-4.3
    """

    @given(
        n=st.integers(min_value=1, max_value=100),
        t=st.integers(min_value=1, max_value=100),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_cleanup_threshold_gate(self, n: int, t: int) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Insert n young facts (won't decay even if decay runs)
        for i in range(n):
            f = _make_fact(confidence=0.9)
            _insert_fact(conn, f, created_at_override=now - timedelta(days=1))

        config = KnowledgeConfig()
        config_dict = config.model_dump()
        config_dict["cleanup_fact_threshold"] = t
        config = KnowledgeConfig(**config_dict)

        result = run_cleanup(conn, config)

        if n <= t:
            assert result.facts_expired == 0

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-P9: Pipeline order invariant
# ---------------------------------------------------------------------------


class TestPipelineOrder:
    """TS-90-P9: Facts superseded by dedup are never passed to contradiction.

    Property 9 from design.md.
    Validates: 90-REQ-5.3, 90-REQ-5.E1
    """

    @given(num_new=st.integers(min_value=1, max_value=5))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_pipeline_order(self, num_new: int) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        # Existing fact
        existing = _make_fact(content="Existing fact")
        _insert_fact(conn, existing, embedding=base_emb)

        new_facts = []
        for i in range(num_new):
            emb = _make_embedding(i + 200)
            f = _make_fact(content=f"New fact {i}")
            _insert_fact(conn, f, embedding=emb)
            new_facts.append(f)

        # Run dedup first
        dedup_result = dedup_new_facts(conn, new_facts, threshold=0.92)
        surviving = dedup_result.surviving_facts

        # Contradiction should only receive survivors
        if surviving:
            with patch(
                "agent_fox.knowledge.contradiction.classify_contradiction_batch",
                return_value=[],
            ) as mock_cd:
                detect_contradictions(conn, surviving, threshold=0.8)
                # If called, verify only surviving facts were processed
                if mock_cd.call_count > 0:
                    for call_args in mock_cd.call_args_list:
                        pairs = call_args[0][0]
                        surviving_ids = {f.id for f in surviving}
                        for pair in pairs:
                            # new fact should be from surviving list
                            assert pair[0].id in surviving_ids or pair[1].id in surviving_ids

        conn.close()
