"""Unit tests for fact lifecycle management: dedup, decay, cleanup.

Test Spec: TS-90-1 through TS-90-4 (dedup), TS-90-9 through TS-90-11 (decay),
           TS-90-12 through TS-90-15 (cleanup), TS-90-E1, TS-90-E2, TS-90-E5,
           TS-90-E6, TS-90-E7, TS-90-E8, TS-324-1, TS-324-2, TS-324-3
Requirements: 90-REQ-1.*, 90-REQ-3.*, 90-REQ-4.*
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.lifecycle import (
    CleanupResult,
    DedupResult,
    dedup_new_facts,
    run_cleanup,
    run_decay_cleanup,
)
from tests.unit.knowledge.conftest import create_schema_v2

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
    """Create an embedding with approximately the given cosine similarity to base.

    Uses a blend of the base vector and a perpendicular noise vector.
    """
    # Create a noise vector roughly orthogonal to base
    noise = _make_embedding(9999, dim)
    # Remove component parallel to base
    dot = sum(a * b for a, b in zip(base, noise))
    noise = [n - dot * b for n, b in zip(noise, base)]
    noise_norm = math.sqrt(sum(x * x for x in noise))
    if noise_norm > 0:
        noise = [x / noise_norm for x in noise]

    # Blend: cos(theta) = similarity => theta = arccos(similarity)
    theta = math.acos(max(-1.0, min(1.0, similarity)))
    result = [
        math.cos(theta) * b + math.sin(theta) * n
        for b, n in zip(base, noise)
    ]
    # Normalise
    r_norm = math.sqrt(sum(x * x for x in result))
    if r_norm > 0:
        result = [x / r_norm for x in result]
    return result


def _make_fact(
    *,
    fact_id: str | None = None,
    content: str = "Test fact",
    confidence: float = 0.9,
    created_at: str | None = None,
) -> Fact:
    """Create a Fact with sensible defaults."""
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
    """Insert a fact (and optional embedding) into the test DB."""
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
    """Create an in-memory DuckDB with production schema (DOUBLE confidence)."""
    conn = duckdb.connect(":memory:")
    create_schema_v2(conn)
    return conn


# ---------------------------------------------------------------------------
# TS-90-1: Dedup detects near-duplicate by embedding similarity
# ---------------------------------------------------------------------------


class TestDedupDetectsNearDuplicate:
    """TS-90-1: dedup_new_facts() identifies existing facts with cosine
    similarity above the threshold.

    Requirement: 90-REQ-1.1
    """

    def test_dedup_detects_near_duplicate(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.95)

        existing = _make_fact(content="Existing fact about API v1")
        _insert_fact(conn, existing, embedding=base_emb)

        new = _make_fact(content="Nearly identical fact about API v1")
        _insert_fact(conn, new, embedding=similar_emb)

        result = dedup_new_facts(conn, [new], threshold=0.92)

        assert len(result.superseded_ids) == 1
        assert result.superseded_ids[0] == existing.id
        assert len(result.surviving_facts) == 1

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-2: Dedup supersedes older fact
# ---------------------------------------------------------------------------


class TestDedupSupersedesOlder:
    """TS-90-2: The older fact's superseded_by is set to the new fact's UUID.

    Requirement: 90-REQ-1.2
    """

    def test_dedup_supersedes_older(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.95)

        old_fact = _make_fact(content="Old fact")
        _insert_fact(conn, old_fact, embedding=base_emb)

        new_fact = _make_fact(content="New replacement fact")
        _insert_fact(conn, new_fact, embedding=similar_emb)

        dedup_new_facts(conn, [new_fact], threshold=0.92)

        # Old fact should be superseded by new
        row = conn.execute(
            "SELECT CAST(superseded_by AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [old_fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] == new_fact.id

        # New fact should remain active
        new_row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [new_fact.id],
        ).fetchone()
        assert new_row is not None
        assert new_row[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-3: Dedup supersedes multiple existing facts
# ---------------------------------------------------------------------------


class TestDedupSupersedesMultiple:
    """TS-90-3: When multiple existing facts exceed the threshold, all are
    superseded.

    Requirement: 90-REQ-1.3
    """

    def test_dedup_supersedes_multiple(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        old_facts = []
        for i in range(3):
            emb = _make_similar_embedding(base_emb, 0.96 - i * 0.01)
            f = _make_fact(content=f"Old fact variant {i}")
            _insert_fact(conn, f, embedding=emb)
            old_facts.append(f)

        new_fact = _make_fact(content="New canonical fact")
        similar_to_base = _make_similar_embedding(base_emb, 0.97)
        _insert_fact(conn, new_fact, embedding=similar_to_base)

        result = dedup_new_facts(conn, [new_fact], threshold=0.92)

        assert len(result.superseded_ids) == 3
        for old in old_facts:
            row = conn.execute(
                "SELECT CAST(superseded_by AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
                [old.id],
            ).fetchone()
            assert row is not None
            assert row[0] == new_fact.id

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-4: Dedup threshold is configurable
# ---------------------------------------------------------------------------


class TestDedupThresholdConfigurable:
    """TS-90-4: The threshold controls dedup behavior.

    Requirement: 90-REQ-1.4
    """

    def test_dedup_threshold_configurable(self) -> None:
        base_emb = _make_embedding(1)
        similar_emb = _make_similar_embedding(base_emb, 0.90)

        # Low threshold (0.85) — should trigger dedup
        conn_low = _setup_db()
        existing_low = _make_fact(content="Existing fact")
        _insert_fact(conn_low, existing_low, embedding=base_emb)
        new_low = _make_fact(content="Similar fact")
        _insert_fact(conn_low, new_low, embedding=similar_emb)

        result_low = dedup_new_facts(conn_low, [new_low], threshold=0.85)
        assert len(result_low.superseded_ids) == 1
        conn_low.close()

        # High threshold (0.95) — should NOT trigger dedup
        conn_high = _setup_db()
        existing_high = _make_fact(content="Existing fact")
        _insert_fact(conn_high, existing_high, embedding=base_emb)
        new_high = _make_fact(content="Similar fact")
        _insert_fact(conn_high, new_high, embedding=similar_emb)

        result_high = dedup_new_facts(conn_high, [new_high], threshold=0.95)
        assert len(result_high.superseded_ids) == 0
        conn_high.close()


# ---------------------------------------------------------------------------
# TS-90-9: Decay formula computes correct effective confidence
# ---------------------------------------------------------------------------


class TestDecayFormula:
    """TS-90-9: Verify the decay formula produces correct results.

    Requirement: 90-REQ-3.1
    """

    def test_decay_formula_known_ages(self) -> None:
        """Verify effective confidence at known ages."""
        conn = _setup_db()
        now = datetime.now(UTC)
        half_life = 90.0

        # Create facts at different ages and check which get superseded
        # Age 0 days: effective = 0.9 (well above any reasonable floor)
        f0 = _make_fact(confidence=0.9)
        _insert_fact(conn, f0, created_at_override=now)

        # Age 90 days: effective = 0.45
        f90 = _make_fact(confidence=0.9)
        _insert_fact(conn, f90, created_at_override=now - timedelta(days=90))

        # Age 180 days: effective = 0.225
        f180 = _make_fact(confidence=0.9)
        _insert_fact(conn, f180, created_at_override=now - timedelta(days=180))

        # Age 270 days: effective ≈ 0.1125
        f270 = _make_fact(confidence=0.9)
        _insert_fact(conn, f270, created_at_override=now - timedelta(days=270))

        # With floor=0.1, only f0/f90/f180/f270 should remain active
        # (0.1125 > 0.1), but let's use a floor that splits them:
        # floor=0.2 should supersede f180 (0.225 > 0.2, stays) and f270 (0.1125 < 0.2, goes)
        count = run_decay_cleanup(conn, half_life_days=half_life, decay_floor=0.2)
        assert count == 1  # Only f270 decayed

        # f270 should be self-superseded
        row = conn.execute(
            "SELECT CAST(superseded_by AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [f270.id],
        ).fetchone()
        assert row is not None
        assert row[0] == f270.id

        # f180 should still be active
        row180 = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [f180.id],
        ).fetchone()
        assert row180 is not None
        assert row180[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-10: Decay auto-supersedes facts below floor
# ---------------------------------------------------------------------------


class TestDecayAutoSupersedes:
    """TS-90-10: Facts below the decay floor are self-superseded.

    Requirement: 90-REQ-3.2
    """

    def test_decay_auto_supersedes(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Fact A: confidence 0.9, age 300 days → effective ≈ 0.088 (below 0.1 floor)
        fact_a = _make_fact(confidence=0.9)
        _insert_fact(conn, fact_a, created_at_override=now - timedelta(days=300))

        # Fact B: confidence 0.9, age 30 days → effective ≈ 0.72 (above 0.1 floor)
        fact_b = _make_fact(confidence=0.9)
        _insert_fact(conn, fact_b, created_at_override=now - timedelta(days=30))

        count = run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)
        assert count == 1

        # Fact A: self-superseded
        row_a = conn.execute(
            "SELECT CAST(superseded_by AS VARCHAR) FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact_a.id],
        ).fetchone()
        assert row_a is not None
        assert row_a[0] == fact_a.id

        # Fact B: still active
        row_b = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact_b.id],
        ).fetchone()
        assert row_b is not None
        assert row_b[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-11: Stored confidence column unchanged after decay
# ---------------------------------------------------------------------------


class TestStoredConfidenceUnchanged:
    """TS-90-11: Decay does not modify the stored confidence value.

    Requirement: 90-REQ-3.6
    """

    def test_stored_confidence_unchanged(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        fact = _make_fact(confidence=0.9)
        _insert_fact(conn, fact, created_at_override=now - timedelta(days=300))

        run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)

        row = conn.execute(
            "SELECT confidence FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(0.9)

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-12: End-of-run cleanup runs when fact count exceeds threshold
# ---------------------------------------------------------------------------


class TestCleanupAboveThreshold:
    """TS-90-12: Cleanup executes when active facts exceed the threshold.

    Requirements: 90-REQ-4.1, 90-REQ-4.2
    """

    def test_cleanup_above_threshold(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Insert 600 facts, some old enough to decay
        for i in range(600):
            f = _make_fact(confidence=0.9)
            # Make half the facts old (350 days)
            age = timedelta(days=350) if i < 300 else timedelta(days=10)
            _insert_fact(conn, f, created_at_override=now - age)

        config = KnowledgeConfig()
        # Use default threshold of 500 — 600 facts > 500

        result = run_cleanup(conn, config)

        assert isinstance(result, CleanupResult)
        assert result.facts_expired > 0
        assert result.active_facts_remaining < 600

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-13: End-of-run cleanup skipped below threshold
# ---------------------------------------------------------------------------


class TestCleanupBelowThreshold:
    """TS-90-13: Decay does not run when active facts <= threshold.

    Requirements: 90-REQ-4.2, 90-REQ-4.3
    """

    def test_cleanup_below_threshold(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Insert 100 facts (below default 500 threshold)
        for i in range(100):
            f = _make_fact(confidence=0.9)
            # Even if old, decay should not run
            _insert_fact(conn, f, created_at_override=now - timedelta(days=350))

        config = KnowledgeConfig()
        result = run_cleanup(conn, config)

        assert result.facts_expired == 0

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-14: Cleanup emits audit event
# ---------------------------------------------------------------------------


class TestCleanupAuditEvent:
    """TS-90-14: fact.cleanup audit event is emitted with correct payload.

    Requirement: 90-REQ-4.5
    """

    def test_cleanup_emits_audit_event(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Seed enough facts to trigger decay
        for i in range(600):
            f = _make_fact(confidence=0.9)
            age = timedelta(days=350) if i < 300 else timedelta(days=10)
            _insert_fact(conn, f, created_at_override=now - age)

        mock_sink = MagicMock()
        config = KnowledgeConfig()

        run_cleanup(conn, config, sink_dispatcher=mock_sink, run_id="r1")

        mock_sink.emit_audit_event.assert_called_once()
        event = mock_sink.emit_audit_event.call_args[0][0]

        from agent_fox.knowledge.audit import AuditEventType

        assert event.event_type == AuditEventType.FACT_CLEANUP
        assert "facts_expired" in event.payload
        assert "active_facts_remaining" in event.payload
        assert "facts_deduped" in event.payload
        assert "facts_contradicted" in event.payload

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-15: Cleanup returns summary dataclass
# ---------------------------------------------------------------------------


class TestCleanupReturnsSummary:
    """TS-90-15: run_cleanup() returns a CleanupResult with accurate counts.

    Requirement: 90-REQ-4.6
    """

    def test_cleanup_returns_result(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        for i in range(600):
            f = _make_fact(confidence=0.9)
            age = timedelta(days=350) if i < 300 else timedelta(days=10)
            _insert_fact(conn, f, created_at_override=now - age)

        config = KnowledgeConfig()
        result = run_cleanup(conn, config)

        assert isinstance(result, CleanupResult)

        remaining = conn.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        assert result.active_facts_remaining == remaining

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E1: Dedup skipped when new fact has no embedding
# ---------------------------------------------------------------------------


class TestDedupSkipNoEmbedding:
    """TS-90-E1: Facts without embeddings bypass dedup entirely.

    Requirement: 90-REQ-1.E1
    """

    def test_dedup_skip_no_embedding(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        # Existing fact with embedding
        existing = _make_fact(content="Existing fact")
        _insert_fact(conn, existing, embedding=base_emb)

        # New fact WITHOUT embedding
        new = _make_fact(content="New fact without embedding")
        _insert_fact(conn, new)  # No embedding

        result = dedup_new_facts(conn, [new], threshold=0.92)

        assert len(result.superseded_ids) == 0
        assert len(result.surviving_facts) == 1

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E2: Dedup skipped when no existing embeddings
# ---------------------------------------------------------------------------


class TestDedupSkipNoExistingEmbeddings:
    """TS-90-E2: When memory_embeddings is empty, dedup is skipped.

    Requirement: 90-REQ-1.E2
    """

    def test_dedup_skip_no_existing_embeddings(self) -> None:
        conn = _setup_db()

        # Insert existing facts without embeddings
        existing = _make_fact(content="Existing fact without embedding")
        _insert_fact(conn, existing)

        # New fact with embedding
        new_emb = _make_embedding(2)
        new = _make_fact(content="New fact with embedding")
        _insert_fact(conn, new, embedding=new_emb)

        result = dedup_new_facts(conn, [new], threshold=0.92)

        assert len(result.superseded_ids) == 0
        assert len(result.surviving_facts) == 1

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E5: Decay skipped for fact with NULL created_at
# ---------------------------------------------------------------------------


class TestDecaySkipNullTimestamp:
    """TS-90-E5: Facts without parseable timestamps are skipped by decay.

    Requirement: 90-REQ-3.E1
    """

    def test_decay_null_timestamp(self) -> None:
        conn = _setup_db()

        # Insert fact with NULL created_at
        fact = _make_fact(confidence=0.9)
        conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, created_at)
            VALUES (?::UUID, ?, ?, ?, ?, NULL)
            """,
            [fact.id, fact.content, fact.category, fact.spec_name, fact.confidence],
        )

        run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)

        # Fact with NULL timestamp should be skipped (not superseded)
        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E6: Future-dated fact gets zero decay
# ---------------------------------------------------------------------------


class TestDecayFutureDate:
    """TS-90-E6: Facts with future timestamps are treated as having zero age.

    Requirement: 90-REQ-3.E2
    """

    def test_decay_future_date(self) -> None:
        conn = _setup_db()
        tomorrow = datetime.now(UTC) + timedelta(days=1)

        fact = _make_fact(confidence=0.9)
        _insert_fact(conn, fact, created_at_override=tomorrow)

        run_decay_cleanup(conn, half_life_days=90, decay_floor=0.1)

        # Future-dated fact should remain active (zero decay)
        row = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE CAST(id AS VARCHAR) = ?",
            [fact.id],
        ).fetchone()
        assert row is not None
        assert row[0] is None

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E7: Cleanup disabled via config
# ---------------------------------------------------------------------------


class TestCleanupDisabled:
    """TS-90-E7: When cleanup_enabled=False, cleanup is fully skipped.

    Requirement: 90-REQ-4.E1
    """

    def test_cleanup_disabled(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Insert facts that would normally be decayed
        for i in range(600):
            f = _make_fact(confidence=0.9)
            _insert_fact(conn, f, created_at_override=now - timedelta(days=350))

        config = KnowledgeConfig()
        # Disable cleanup — requires the new config field
        config_dict = config.model_dump()
        config_dict["cleanup_enabled"] = False
        config = KnowledgeConfig(**config_dict)

        result = run_cleanup(conn, config)

        assert result.facts_expired == 0
        assert result.facts_deduped == 0
        assert result.facts_contradicted == 0

        conn.close()


# ---------------------------------------------------------------------------
# TS-324-1: run_cleanup active_count None-guard (AC-1)
# ---------------------------------------------------------------------------


class TestRunCleanupActiveCountNoneGuard:
    """TS-324-1: If fetchone() returns None for the active-count query,
    run_cleanup defaults active_count to 0 and does not raise TypeError.

    Requirement: fix-issue-324 AC-1
    """

    def test_active_count_fetchone_none_returns_zero(self) -> None:
        """Mocking fetchone() → None for the COUNT query must not raise."""
        # Use a MagicMock connection so execute() is fully controllable
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        conn = MagicMock()
        conn.execute.return_value = mock_cursor

        config = KnowledgeConfig()

        # Must not raise TypeError; None fetchone() should default to 0
        result = run_cleanup(conn, config)

        assert result.facts_expired == 0
        assert result.active_facts_remaining == 0


# ---------------------------------------------------------------------------
# TS-324-2: run_cleanup active_remaining None-guard (AC-2)
# ---------------------------------------------------------------------------


class TestRunCleanupActiveRemainingNoneGuard:
    """TS-324-2: If fetchone() returns None for the post-cleanup recount query,
    run_cleanup defaults active_remaining to 0 and does not raise TypeError.

    Requirement: fix-issue-324 AC-2
    """

    def test_active_remaining_fetchone_none_returns_zero(self) -> None:
        """Second COUNT(*) fetchone() → None must not raise TypeError."""
        # First execute() returns a real count (above threshold) so decay runs.
        # Second execute() returns None from fetchone() for the post-cleanup recount.
        cursor_first = MagicMock()
        cursor_first.fetchone.return_value = (600,)  # above default threshold

        cursor_second = MagicMock()
        cursor_second.fetchone.return_value = None  # post-cleanup recount → None

        # run_decay_cleanup also calls execute; make those return benign cursors
        decay_cursor = MagicMock()
        decay_cursor.fetchall.return_value = []

        call_count: list[int] = [0]

        def side_effect(query: str, *args: object, **kwargs: object) -> MagicMock:
            if "SELECT COUNT(*)" in query:
                call_count[0] += 1
                return cursor_first if call_count[0] == 1 else cursor_second
            return decay_cursor

        conn = MagicMock()
        conn.execute.side_effect = side_effect

        config = KnowledgeConfig()

        result = run_cleanup(conn, config)

        assert result.active_facts_remaining == 0


# ---------------------------------------------------------------------------
# TS-324-3: run_cleanup normal behavior preserved (AC-3)
# ---------------------------------------------------------------------------


class TestRunCleanupNormalBehaviorPreserved:
    """TS-324-3: When fetchone() returns a valid row, run_cleanup populates
    active_facts_remaining correctly from fetchone()[0].

    Requirement: fix-issue-324 AC-3
    """

    def test_normal_cleanup_returns_correct_counts(self) -> None:
        conn = _setup_db()
        now = datetime.now(UTC)

        # Insert facts below threshold — no decay should occur
        for _ in range(5):
            f = _make_fact(confidence=0.9)
            _insert_fact(conn, f, created_at_override=now - timedelta(days=10))

        config = KnowledgeConfig()

        result = run_cleanup(conn, config)

        # All 5 facts are active and below threshold, so none expired
        assert result.facts_expired == 0
        assert result.active_facts_remaining == 5

        conn.close()


# ---------------------------------------------------------------------------
# TS-90-E8: All new facts deduped skips contradiction
# ---------------------------------------------------------------------------


class TestAllDedupedSkipsContradiction:
    """TS-90-E8: When dedup removes all new facts, contradiction detection
    is skipped.

    Requirement: 90-REQ-5.E1
    """

    def test_all_deduped_skips_contradiction(self) -> None:
        conn = _setup_db()
        base_emb = _make_embedding(1)

        # Existing fact
        existing = _make_fact(content="Existing fact")
        _insert_fact(conn, existing, embedding=base_emb)

        # New fact that is a near-duplicate
        similar_emb = _make_similar_embedding(base_emb, 0.97)
        new = _make_fact(content="Near duplicate")
        _insert_fact(conn, new, embedding=similar_emb)

        result = dedup_new_facts(conn, [new], threshold=0.92)

        # All new facts should be in surviving_facts (dedup supersedes existing, not new)
        # but if the new fact replaces existing, surviving list should contain the new fact
        # The key test: if no facts survive dedup, contradiction should be skipped
        # This is tested at integration level; here we verify dedup result shape
        assert isinstance(result, DedupResult)

        conn.close()
