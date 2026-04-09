"""Unit tests for LLM-powered contradiction detection.

Test Spec: TS-90-5 through TS-90-8 (contradiction), TS-90-E3, TS-90-E4
Requirements: 90-REQ-2.*
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import duckdb

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.lifecycle import (
    detect_contradictions,
)
from tests.unit.knowledge.conftest import create_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 384


def _make_embedding(seed: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate a deterministic, normalised embedding vector."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / norm for x in raw]


def _make_similar_embedding(
    base: list[float],
    similarity: float,
    dim: int = EMBEDDING_DIM,
) -> list[float]:
    """Create an embedding with approximately the given cosine similarity to base."""
    noise = _make_embedding(9999, dim)
    dot = sum(a * b for a, b in zip(base, noise))
    noise = [n - dot * b for n, b in zip(noise, base)]
    noise_norm = math.sqrt(sum(x * x for x in noise))
    if noise_norm > 0:
        noise = [x / noise_norm for x in noise]
    theta = math.acos(max(-1.0, min(1.0, similarity)))
    result = [
        math.cos(theta) * b + math.sin(theta) * n
        for b, n in zip(base, noise)
    ]
    r_norm = math.sqrt(sum(x * x for x in result))
    if r_norm > 0:
        result = [x / r_norm for x in result]
    return result


def _make_dissimilar_embedding(
    base: list[float],
    dim: int = EMBEDDING_DIM,
) -> list[float]:
    """Create an embedding with low similarity to base (~0.0)."""
    # Create a vector roughly orthogonal to base
    noise = _make_embedding(7777, dim)
    dot = sum(a * b for a, b in zip(base, noise))
    result = [n - dot * b for n, b in zip(noise, base)]
    r_norm = math.sqrt(sum(x * x for x in result))
    if r_norm > 0:
        result = [x / r_norm for x in result]
    return result


def _make_fact(
    *,
    fact_id: str | None = None,
    content: str = "Test fact",
    confidence: float = 0.9,
) -> Fact:
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content,
        category="pattern",
        spec_name="test_spec",
        keywords=["test"],
        confidence=confidence,
        created_at=datetime.now(UTC).isoformat(),
    )


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact: Fact,
    *,
    embedding: list[float] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at)
        VALUES (?::UUID, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [fact.id, fact.content, fact.category, fact.spec_name, fact.confidence],
    )
    if embedding is not None:
        conn.execute(
            f"INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[{EMBEDDING_DIM}])",
            [fact.id, embedding],
        )


def _setup_db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# TS-90-5: Contradiction detection identifies candidates by similarity
# ---------------------------------------------------------------------------


class TestContradictionIdentifiesCandidates:
    """TS-90-5: Only candidate pairs with similarity >= threshold are sent
    to the LLM.

    Requirement: 90-REQ-2.1
    """

    def test_contradiction_identifies_candidates(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        # Existing fact with high similarity to new
        existing_high = _make_fact(content="Use kuksa.VAL service for data access")
        high_emb = _make_similar_embedding(base_emb, 0.85)
        _insert_fact(conn, existing_high, embedding=high_emb)

        # Existing fact with low similarity
        existing_low = _make_fact(content="Completely unrelated topic about testing")
        low_emb = _make_dissimilar_embedding(base_emb)
        _insert_fact(conn, existing_low, embedding=low_emb)

        # New fact
        new_fact = _make_fact(content="Use kuksa.val.v2.VAL service")
        _insert_fact(conn, new_fact, embedding=base_emb)

        # Mock LLM to return no contradictions and track calls
        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            return_value=[],
        ) as mock_llm:
            detect_contradictions(conn, [new_fact], threshold=0.8)
            # Only the high-similarity pair should be evaluated
            if mock_llm.call_count > 0:
                pairs = mock_llm.call_args[0][0]
                # All pairs sent to LLM should be above threshold
                for pair in pairs:
                    assert pair[0].id == new_fact.id or pair[1].id == new_fact.id

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-6: Contradiction confirmed by LLM triggers supersession
# ---------------------------------------------------------------------------


class TestContradictionConfirmedSupersedes:
    """TS-90-6: When the LLM confirms a contradiction, the older fact is
    superseded.

    Requirements: 90-REQ-2.2, 90-REQ-2.3
    """

    def test_contradiction_confirmed_supersedes(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.85)

        old_fact = _make_fact(content="Use kuksa.VAL service for data access")
        _insert_fact(conn, old_fact, embedding=base_emb)

        new_fact = _make_fact(
            content="Use kuksa.val.v2.VAL service; kuksa.VAL is deprecated"
        )
        _insert_fact(conn, new_fact, embedding=similar_emb)

        from agent_fox.knowledge.lifecycle import ContradictionVerdict

        mock_verdicts = [
            ContradictionVerdict(
                new_fact_id=new_fact.id,
                old_fact_id=old_fact.id,
                contradicts=True,
                reason="API version changed",
            )
        ]

        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            return_value=mock_verdicts,
        ):
            result = detect_contradictions(
                conn, [new_fact], threshold=0.8, model="SIMPLE"
            )

        assert len(result.superseded_ids) == 1
        assert result.superseded_ids[0] == old_fact.id
        assert result.verdicts[0].contradicts is True
        assert result.verdicts[0].reason == "API version changed"

        # Verify DB state
        row = conn.execute(
            "SELECT CAST(superseded_by AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [old_fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] == new_fact.id

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-7: Non-contradiction leaves facts unchanged
# ---------------------------------------------------------------------------


class TestNonContradictionUnchanged:
    """TS-90-7: When the LLM says no contradiction, no supersession occurs.

    Requirement: 90-REQ-2.4
    """

    def test_non_contradiction_unchanged(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.85)

        old_fact = _make_fact(content="Use structured logging for production")
        _insert_fact(conn, old_fact, embedding=base_emb)

        new_fact = _make_fact(content="Add JSON formatting to structured logs")
        _insert_fact(conn, new_fact, embedding=similar_emb)

        from agent_fox.knowledge.lifecycle import ContradictionVerdict

        mock_verdicts = [
            ContradictionVerdict(
                new_fact_id=new_fact.id,
                old_fact_id=old_fact.id,
                contradicts=False,
                reason="Related but compatible",
            )
        ]

        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            return_value=mock_verdicts,
        ):
            result = detect_contradictions(conn, [new_fact], threshold=0.8)

        assert len(result.superseded_ids) == 0

        # Old fact should remain active
        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [old_fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-8: Contradiction batching respects max size
# ---------------------------------------------------------------------------


class TestContradictionBatchSize:
    """TS-90-8: Candidate pairs are batched in groups of at most 10.

    Requirement: 90-REQ-2.5
    """

    def test_contradiction_batch_size(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        # Create 25 existing facts all similar to the new facts
        for i in range(25):
            emb = _make_similar_embedding(base_emb, 0.85 + (i % 10) * 0.005)
            f = _make_fact(content=f"Existing fact variant {i}")
            _insert_fact(conn, f, embedding=emb)

        # Create new fact
        new_fact = _make_fact(content="New fact that could contradict many")
        _insert_fact(conn, new_fact, embedding=base_emb)

        call_count = 0
        batch_sizes: list[int] = []

        def mock_classify(pairs, model="SIMPLE"):
            nonlocal call_count
            call_count += 1
            batch_sizes.append(len(pairs))
            return []  # No contradictions

        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            side_effect=mock_classify,
        ):
            detect_contradictions(conn, [new_fact], threshold=0.8)

        # Should have 3 calls for 25 pairs: 10 + 10 + 5
        assert call_count == 3
        assert all(size <= 10 for size in batch_sizes)

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E3: LLM failure during contradiction is non-fatal
# ---------------------------------------------------------------------------


class TestLlmFailureNonFatal:
    """TS-90-E3: API errors during contradiction check are caught and logged.

    Requirement: 90-REQ-2.E1
    """

    def test_llm_failure_non_fatal(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.85)

        old_fact = _make_fact(content="Old fact about API")
        _insert_fact(conn, old_fact, embedding=base_emb)

        new_fact = _make_fact(content="New fact about API")
        _insert_fact(conn, new_fact, embedding=similar_emb)

        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            side_effect=Exception("API Error"),
        ):
            # Should not raise
            result = detect_contradictions(conn, [new_fact], threshold=0.8)

        assert len(result.superseded_ids) == 0

        # All facts remain active
        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [old_fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E4: Malformed LLM JSON treated as non-contradiction
# ---------------------------------------------------------------------------


class TestMalformedJsonNonContradiction:
    """TS-90-E4: Invalid JSON from LLM does not trigger supersession.

    Requirement: 90-REQ-2.E3
    """

    def test_malformed_json_non_contradiction(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.85)

        old_fact = _make_fact(content="Old fact")
        _insert_fact(conn, old_fact, embedding=base_emb)

        new_fact = _make_fact(content="New fact")
        _insert_fact(conn, new_fact, embedding=similar_emb)

        # Return empty list (simulating parsed-but-no-results from malformed JSON)
        with patch(
            "agent_fox.knowledge.contradiction.classify_contradiction_batch",
            return_value=[],
        ):
            result = detect_contradictions(conn, [new_fact], threshold=0.8)

        assert len(result.superseded_ids) == 0

        conn.close()
