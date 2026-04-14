"""Unit tests for the AdaptiveRetriever and supporting functions.

Test Spec: TS-104-1 through TS-104-16, TS-104-E4
Requirements: 104-REQ-1.*, 104-REQ-2.*, 104-REQ-3.*, 104-REQ-4.*, 104-REQ-5.*
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb

from agent_fox.core.config import KnowledgeConfig

# These imports will fail with ModuleNotFoundError until group 2 creates the module.
from agent_fox.knowledge.retrieval import (
    AdaptiveRetriever,
    IntentProfile,
    RetrievalConfig,
    RetrievalResult,
    ScoredFact,
    assemble_ranked_context,
    derive_intent_profile,
    weighted_rrf_fusion,
)
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    MOCK_EMBEDDING_1,
    MOCK_EMBEDDING_2,
    MOCK_EMBEDDING_3,
    create_schema,
    insert_fact_with_embedding,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FACT_X = "10101010-1010-1010-1010-101010101010"
FACT_Y = "20202020-3030-3030-3030-303030303030"
FACT_Z = "40404040-4040-4040-4040-404040404040"


def _make_scored_fact(
    fact_id: str,
    *,
    content: str = "A test fact.",
    spec_name: str = "myspec",
    confidence: float = 0.9,
    category: str = "pattern",
    created_at: str = "2026-01-01T00:00:00+00:00",
    score: float = 0.0,
) -> ScoredFact:
    """Create a ScoredFact with sensible defaults."""
    return ScoredFact(
        fact_id=fact_id,
        content=content,
        spec_name=spec_name,
        confidence=confidence,
        created_at=created_at,
        category=category,
        score=score,
    )


def _make_conn_with_facts() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with schema and a handful of facts."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    # Insert 5 facts: 2 matching spec "myspec", 3 with keyword overlap
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, spec_name, category, confidence, created_at, keywords)
        VALUES
            (?, 'Auth middleware validates JWT tokens', 'myspec', 'pattern', 0.9,
             '2026-01-01 10:00:00', ['auth', 'jwt', 'middleware']),
            (?, 'Session store uses Redis', 'myspec', 'decision', 0.8,
             '2026-01-02 10:00:00', ['session', 'redis', 'store']),
            (?, 'Auth layer must handle concurrent requests', 'other_spec', 'gotcha', 0.7,
             '2026-01-03 10:00:00', ['auth', 'concurrency', 'session']),
            (?, 'Database uses DuckDB for analytics', 'db_spec', 'decision', 0.6,
             '2025-12-01 10:00:00', ['duckdb', 'database', 'analytics']),
            (?, 'Logging format is structured JSON', 'logging_spec', 'convention', 0.9,
             '2025-11-01 10:00:00', ['logging', 'json', 'format'])
        """,
        [FACT_AAA, FACT_BBB, FACT_CCC, FACT_X, FACT_Y],
    )
    return conn


def _make_conn_with_embeddings() -> duckdb.DuckDBPyConnection:
    """Create in-memory DuckDB with schema, facts, and embeddings."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    insert_fact_with_embedding(
        conn,
        FACT_AAA,
        "Auth middleware validates JWT tokens",
        MOCK_EMBEDDING_1,
        spec_name="myspec",
    )
    insert_fact_with_embedding(
        conn,
        FACT_BBB,
        "Session store uses Redis",
        MOCK_EMBEDDING_2,
        spec_name="myspec",
    )
    insert_fact_with_embedding(
        conn,
        FACT_CCC,
        "Database concurrency patterns",
        MOCK_EMBEDDING_3,
        spec_name="other_spec",
    )
    return conn


def _make_conn_with_entities() -> duckdb.DuckDBPyConnection:
    """Create in-memory DuckDB with entity graph tables and linked facts.

    Uses knowledge_conn pattern (runs migrations) so entity_graph tables exist.
    """
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)

    entity_id = str(uuid.uuid4())

    # Insert entity for "agent_fox/knowledge/search.py"
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?, 'file', 'search.py', 'agent_fox/knowledge/search.py', CURRENT_TIMESTAMP)
        """,
        [entity_id],
    )

    # Insert 2 facts linked to this entity
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, spec_name, category, confidence, created_at, keywords)
        VALUES
            (?, 'VectorSearch uses cosine distance', 'myspec', 'pattern', 0.9,
             '2026-01-01 10:00:00', ['search', 'vector', 'cosine']),
            (?, 'Search results ordered by similarity', 'myspec', 'convention', 0.8,
             '2026-01-02 10:00:00', ['search', 'similarity', 'ordering'])
        """,
        [FACT_AAA, FACT_BBB],
    )
    conn.execute(
        """
        INSERT INTO fact_entities (fact_id, entity_id)
        VALUES (?, ?), (?, ?)
        """,
        [FACT_AAA, entity_id, FACT_BBB, entity_id],
    )
    return conn


def _make_conn_with_causal_chain() -> duckdb.DuckDBPyConnection:
    """Create in-memory DuckDB with a causal chain: A -> B -> C in 'myspec'."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, spec_name, category, confidence, created_at, keywords)
        VALUES
            (?, 'Root cause: nullable email', 'myspec', 'gotcha', 0.9,
             '2025-11-01 10:00:00', ['email', 'nullable']),
            (?, 'Effect: test assertions failed', 'myspec', 'gotcha', 0.8,
             '2025-11-02 10:00:00', ['test', 'assertion']),
            (?, 'Fix: migration added', 'myspec', 'pattern', 0.9,
             '2025-11-03 10:00:00', ['migration', 'fix'])
        """,
        [FACT_AAA, FACT_BBB, FACT_CCC],
    )
    conn.execute(
        """
        INSERT INTO fact_causes (cause_id, effect_id) VALUES
            (?, ?),
            (?, ?)
        """,
        [FACT_AAA, FACT_BBB, FACT_BBB, FACT_CCC],
    )
    return conn


# ---------------------------------------------------------------------------
# TS-104-1: Keyword signal returns ranked facts
# ---------------------------------------------------------------------------


class TestKeywordSignal:
    """TS-104-1: Keyword signal returns ranked facts.

    Requirements: 104-REQ-1.2
    """

    def test_returns_spec_matching_and_keyword_matching_facts(self) -> None:
        """Keyword signal returns facts matching spec name or keyword overlap."""
        from agent_fox.knowledge.retrieval import _keyword_signal

        conn = _make_conn_with_facts()
        try:
            results = _keyword_signal("myspec", ["auth", "session"], conn, 0.5)
            assert len(results) >= 2, "Should return at least spec-matching facts"
            assert all(r.score > 0 for r in results), "All results must have positive score"
            # Spec-matching facts should be present
            fact_ids = {r.fact_id for r in results}
            assert FACT_AAA in fact_ids or FACT_BBB in fact_ids, "Spec-matching facts from 'myspec' should appear"
        finally:
            conn.close()

    def test_results_ordered_by_score_descending(self) -> None:
        """Keyword signal results are ordered by score descending."""
        from agent_fox.knowledge.retrieval import _keyword_signal

        conn = _make_conn_with_facts()
        try:
            results = _keyword_signal("myspec", ["auth", "session"], conn, 0.5)
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), "Results should be ordered by descending score"
        finally:
            conn.close()

    def test_confidence_filtering_applied(self) -> None:
        """Facts below confidence threshold are excluded."""
        from agent_fox.knowledge.retrieval import _keyword_signal

        conn = _make_conn_with_facts()
        try:
            # Use high threshold to exclude most facts
            results = _keyword_signal("myspec", ["auth"], conn, 0.95)
            # Only high-confidence facts (0.9) matching 'auth' should appear
            for r in results:
                assert r.confidence >= 0.95, "All returned facts must meet confidence threshold"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-2: Vector signal returns similarity-ranked facts
# ---------------------------------------------------------------------------


class TestVectorSignal:
    """TS-104-2: Vector signal returns similarity-ranked facts.

    Requirements: 104-REQ-1.3
    """

    def test_returns_cosine_ranked_results(self) -> None:
        """Vector signal returns facts ordered by cosine similarity."""
        from agent_fox.knowledge.retrieval import _vector_signal

        conn = _make_conn_with_embeddings()
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        # Same as MOCK_EMBEDDING_1, so FACT_AAA should rank highest
        embedder.embed_text.return_value = MOCK_EMBEDDING_1

        try:
            config = KnowledgeConfig()
            results = _vector_signal("implement auth middleware", conn, embedder, config)
            assert len(results) >= 1, "Should return at least one result"
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), "Results should be ordered by descending score"
            # FACT_AAA has embedding=MOCK_EMBEDDING_1 matching query exactly
            assert results[0].fact_id == FACT_AAA, "Most similar fact should rank first"
        finally:
            conn.close()

    def test_empty_when_no_embeddings(self) -> None:
        """Vector signal returns empty list when no embeddings exist."""
        from agent_fox.knowledge.retrieval import _vector_signal

        conn = duckdb.connect(":memory:")
        create_schema(conn)
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        embedder.embed_text.return_value = MOCK_EMBEDDING_1
        config = KnowledgeConfig()

        try:
            results = _vector_signal("some query", conn, embedder, config)
            assert results == [], "Empty store should return empty list"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-3: Entity signal returns BFS-traversed facts
# ---------------------------------------------------------------------------


class TestEntitySignal:
    """TS-104-3: Entity signal returns BFS-traversed facts.

    Requirements: 104-REQ-1.4
    """

    def test_returns_entity_linked_facts(self) -> None:
        """Entity signal returns facts linked to entities for the touched files."""
        from agent_fox.knowledge.retrieval import _entity_signal

        conn = _make_conn_with_entities()
        try:
            results = _entity_signal(["agent_fox/knowledge/search.py"], conn)
            assert len(results) == 2, "Should return both facts linked to the file entity"
            result_ids = {r.fact_id for r in results}
            assert FACT_AAA in result_ids and FACT_BBB in result_ids
        finally:
            conn.close()

    def test_empty_for_unlinked_files(self) -> None:
        """Entity signal returns empty list when no entities match the touched files."""
        from agent_fox.knowledge.retrieval import _entity_signal

        conn = _make_conn_with_entities()
        try:
            results = _entity_signal(["nonexistent/path.py"], conn)
            assert results == [], "No linked entities means empty results"
        finally:
            conn.close()

    def test_empty_touched_files_returns_empty(self) -> None:
        """Entity signal returns empty list when touched_files is empty."""
        from agent_fox.knowledge.retrieval import _entity_signal

        conn = _make_conn_with_entities()
        try:
            results = _entity_signal([], conn)
            assert results == []
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-4: Causal signal returns depth-ordered facts
# ---------------------------------------------------------------------------


class TestCausalSignal:
    """TS-104-4: Causal signal returns depth-ordered facts.

    Requirements: 104-REQ-1.5
    """

    def test_returns_causally_linked_facts(self) -> None:
        """Causal signal traverses fact_causes and returns linked facts."""
        from agent_fox.knowledge.retrieval import _causal_signal

        conn = _make_conn_with_causal_chain()
        try:
            results = _causal_signal("myspec", conn, max_depth=3)
            assert len(results) >= 2, "Should return at least 2 causally linked facts"
        finally:
            conn.close()

    def test_returns_empty_for_spec_with_no_causal_links(self) -> None:
        """Causal signal returns empty list when no causal links exist for spec."""
        from agent_fox.knowledge.retrieval import _causal_signal

        conn = duckdb.connect(":memory:")
        create_schema(conn)
        try:
            results = _causal_signal("nonexistent_spec", conn, max_depth=3)
            assert results == []
        finally:
            conn.close()

    def test_proximity_ordering(self) -> None:
        """Facts closer to the spec root appear before deeper facts."""
        from agent_fox.knowledge.retrieval import _causal_signal

        conn = _make_conn_with_causal_chain()
        try:
            results = _causal_signal("myspec", conn, max_depth=3)
            # Find FACT_BBB (depth 1 from FACT_AAA) and FACT_CCC (depth 2)
            fact_ids = [r.fact_id for r in results]
            if FACT_BBB in fact_ids and FACT_CCC in fact_ids:
                pos_b = fact_ids.index(FACT_BBB)
                pos_c = fact_ids.index(FACT_CCC)
                assert pos_b < pos_c, "B (depth 1) should appear before C (depth 2)"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-5: Empty signal gracefully excluded
# ---------------------------------------------------------------------------


class TestEmptySignalExcluded:
    """TS-104-5: Empty signal gracefully excluded from RRF.

    Requirements: 104-REQ-1.E1
    """

    def test_fusion_works_with_two_empty_signals(self) -> None:
        """RRF proceeds when two signals return empty lists."""
        fact_a = _make_scored_fact(FACT_AAA, content="Fact A")
        fact_b = _make_scored_fact(FACT_BBB, content="Fact B")
        # fact_a appears in both keyword and entity; fact_b only in keyword
        signal_lists = {
            "keyword": [fact_a, fact_b],
            "vector": [],
            "entity": [fact_a],
            "causal": [],
        }
        profile = IntentProfile()  # all weights = 1.0
        result = weighted_rrf_fusion(signal_lists, profile, k=60)

        assert len(result) == 2, "Should produce results from non-empty signals"
        # fact_a appears in 2 signals → higher score
        assert result[0].fact_id == FACT_AAA, "Fact appearing in 2 signals should rank first"


# ---------------------------------------------------------------------------
# TS-104-6: All signals empty returns empty context
# ---------------------------------------------------------------------------


class TestAllSignalsEmpty:
    """TS-104-6: All signals empty → empty context.

    Requirements: 104-REQ-1.E2
    """

    def test_fusion_returns_empty_when_all_empty(self) -> None:
        """weighted_rrf_fusion returns [] when all signal lists are empty."""
        signal_lists = {"keyword": [], "vector": [], "entity": [], "causal": []}
        profile = IntentProfile()
        result = weighted_rrf_fusion(signal_lists, profile, k=60)
        assert result == []

    def test_context_is_empty_string_when_no_facts(self) -> None:
        """assemble_ranked_context returns empty string when anchors list is empty."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        config = RetrievalConfig()
        try:
            context = assemble_ranked_context([], conn, config)
            assert context == ""
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-7: Vector signal failure logged and skipped
# ---------------------------------------------------------------------------


class TestVectorSignalFailure:
    """TS-104-7: Vector signal failure is logged and retrieval continues.

    Requirements: 104-REQ-1.E3
    """

    def test_retriever_does_not_raise_on_embedder_failure(self) -> None:
        """AdaptiveRetriever continues when vector signal raises RuntimeError."""
        conn = _make_conn_with_facts()
        config = RetrievalConfig()

        # Embedder that always raises
        failing_embedder = MagicMock()
        failing_embedder.embedding_dimensions = 384
        failing_embedder.embed_text.side_effect = RuntimeError("embedding backend down")

        retriever = AdaptiveRetriever(conn, config, embedder=failing_embedder)
        try:
            # Must not raise
            result = retriever.retrieve(
                spec_name="myspec",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="fix auth middleware",
            )
            assert isinstance(result, RetrievalResult)
            # Vector signal should be excluded or count 0
            assert result.signal_counts.get("vector", 0) == 0, (
                "Vector signal should produce 0 results when embedder fails"
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-8: RRF formula produces correct scores
# ---------------------------------------------------------------------------


class TestRrfFormula:
    """TS-104-8: RRF formula produces correct weighted scores.

    Requirements: 104-REQ-2.1, 104-REQ-2.2, 104-REQ-3.2
    """

    def test_weighted_rrf_ordering(self) -> None:
        """Verify weighted RRF scoring produces correct ordering: B > C > A."""
        # keyword = [A(rank1), B(rank2)], entity = [B(rank1), C(rank2)]
        # Profile: keyword_weight=1.0, entity_weight=2.0
        # A: 1.0/(60+1) ≈ 0.01639
        # B: 1.0/(60+2) + 2.0/(60+1) ≈ 0.01613 + 0.03279 = 0.04892
        # C: 2.0/(60+2) ≈ 0.03226
        fact_a = _make_scored_fact(FACT_AAA, content="Fact A")
        fact_b = _make_scored_fact(FACT_BBB, content="Fact B")
        fact_c = _make_scored_fact(FACT_CCC, content="Fact C")

        signal_lists = {
            "keyword": [fact_a, fact_b],  # A=rank1, B=rank2
            "entity": [fact_b, fact_c],  # B=rank1, C=rank2
            "vector": [],
            "causal": [],
        }
        profile = IntentProfile(
            keyword_weight=1.0,
            vector_weight=1.0,
            entity_weight=2.0,
            causal_weight=1.0,
        )
        result = weighted_rrf_fusion(signal_lists, profile, k=60)

        assert len(result) == 3
        assert result[0].fact_id == FACT_BBB, "B should rank first (highest score)"
        assert result[1].fact_id == FACT_CCC, "C should rank second"
        assert result[2].fact_id == FACT_AAA, "A should rank third"

    def test_rrf_score_values(self) -> None:
        """Verify exact score values for the weighted RRF formula."""
        fact_a = _make_scored_fact(FACT_AAA)
        fact_b = _make_scored_fact(FACT_BBB)
        fact_c = _make_scored_fact(FACT_CCC)

        signal_lists = {
            "keyword": [fact_a, fact_b],
            "entity": [fact_b, fact_c],
            "vector": [],
            "causal": [],
        }
        profile = IntentProfile(keyword_weight=1.0, vector_weight=1.0, entity_weight=2.0, causal_weight=1.0)
        result = weighted_rrf_fusion(signal_lists, profile, k=60)

        result_by_id = {r.fact_id: r for r in result}

        expected_b = 1.0 / (60 + 2) + 2.0 / (60 + 1)
        expected_c = 2.0 / (60 + 2)
        expected_a = 1.0 / (60 + 1)

        assert abs(result_by_id[FACT_BBB].score - expected_b) < 1e-10
        assert abs(result_by_id[FACT_CCC].score - expected_c) < 1e-10
        assert abs(result_by_id[FACT_AAA].score - expected_a) < 1e-10


# ---------------------------------------------------------------------------
# TS-104-9: RRF deduplication
# ---------------------------------------------------------------------------


class TestRrfDeduplication:
    """TS-104-9: RRF deduplication - same fact in multiple signals → one entry.

    Requirements: 104-REQ-2.3
    """

    def test_same_fact_in_multiple_signals_one_output_entry(self) -> None:
        """Fact X appearing in keyword (rank 1) and vector (rank 3) → one entry."""
        fact_x = _make_scored_fact(FACT_X, content="Fact X")
        fact_y = _make_scored_fact(FACT_Y, content="Fact Y")
        fact_z = _make_scored_fact(FACT_Z, content="Fact Z")

        signal_lists = {
            "keyword": [fact_x, fact_y],
            "vector": [fact_z, fact_y, fact_x],  # X appears at rank 3
            "entity": [],
            "causal": [],
        }
        profile = IntentProfile()
        result = weighted_rrf_fusion(signal_lists, profile, k=60)

        x_entries = [r for r in result if r.fact_id == FACT_X]
        assert len(x_entries) == 1, "Fact X should appear exactly once in output"

    def test_aggregated_score_greater_than_single_signal(self) -> None:
        """Fact in 2 signals gets score higher than if it only appeared in one."""
        fact_x = _make_scored_fact(FACT_X)
        fact_y = _make_scored_fact(FACT_Y)

        signal_lists_two = {
            "keyword": [fact_x],
            "vector": [fact_x, fact_y],
            "entity": [],
            "causal": [],
        }
        signal_lists_one = {
            "keyword": [fact_x],
            "vector": [fact_y],
            "entity": [],
            "causal": [],
        }
        profile = IntentProfile()
        result_two = weighted_rrf_fusion(signal_lists_two, profile, k=60)
        result_one = weighted_rrf_fusion(signal_lists_one, profile, k=60)

        score_two = next(r.score for r in result_two if r.fact_id == FACT_X)
        score_one = next(r.score for r in result_one if r.fact_id == FACT_X)

        assert score_two > score_one, "Score should increase when fact appears in more signals"


# ---------------------------------------------------------------------------
# TS-104-10: Intent profile for coder/retry
# ---------------------------------------------------------------------------


class TestIntentProfileCoderRetry:
    """TS-104-10: Intent profile for coder/retry session.

    Requirements: 104-REQ-3.1, 104-REQ-3.3
    """

    def test_coder_retry_has_high_causal_weight(self) -> None:
        """coder/retry profile has causal_weight=2.0 and other weights lower."""
        profile = derive_intent_profile("coder", "retry")
        assert profile.causal_weight == 2.0
        assert profile.keyword_weight == 0.8
        assert profile.entity_weight == 1.0
        assert profile.vector_weight == 0.6

    def test_coder_fresh_has_high_entity_weight(self) -> None:
        """coder/fresh profile has entity_weight=1.5."""
        profile = derive_intent_profile("coder", "fresh")
        assert profile.entity_weight == 1.5
        assert profile.keyword_weight == 1.0
        assert profile.vector_weight == 0.8
        assert profile.causal_weight == 1.0

    def test_auditor_has_high_entity_weight(self) -> None:
        """auditor profile (any status) has entity_weight=2.0."""
        profile = derive_intent_profile("auditor", "fresh")
        assert profile.entity_weight == 2.0
        assert profile.keyword_weight == 0.6

    def test_reviewer_has_high_vector_weight(self) -> None:
        """reviewer profile has vector_weight=1.5."""
        profile = derive_intent_profile("reviewer", "fresh")
        assert profile.vector_weight == 1.5

    def test_verifier_profile(self) -> None:
        """verifier profile has causal_weight=1.5 and entity_weight=1.5."""
        profile = derive_intent_profile("verifier", "fresh")
        assert profile.causal_weight == 1.5
        assert profile.entity_weight == 1.5


# ---------------------------------------------------------------------------
# TS-104-11: Unknown archetype falls back to default
# ---------------------------------------------------------------------------


class TestUnknownArchetypeFallback:
    """TS-104-11: Unknown archetype produces balanced default profile.

    Requirements: 104-REQ-3.E1
    """

    def test_unknown_archetype_all_weights_one(self) -> None:
        """Unknown archetype returns all weights = 1.0."""
        profile = derive_intent_profile("unknown_thing", "fresh")
        assert profile.keyword_weight == 1.0
        assert profile.vector_weight == 1.0
        assert profile.entity_weight == 1.0
        assert profile.causal_weight == 1.0

    def test_missing_node_status_fallback(self) -> None:
        """Unknown archetype with arbitrary node_status still returns default profile."""
        profile = derive_intent_profile("mystery_archetype", "unknown_status")
        assert profile == IntentProfile(1.0, 1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# TS-104-12: Context ordered by causal precedence
# ---------------------------------------------------------------------------


class TestCausalOrdering:
    """TS-104-12: Context assembled with causal predecessors before effects.

    Requirements: 104-REQ-4.1
    """

    def test_causal_predecessor_appears_before_effect(self) -> None:
        """Fact A appears before fact B in output when A→B is a causal edge."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        try:
            # Insert two facts and a causal link A → B
            conn.execute(
                """
                INSERT INTO memory_facts
                    (id, content, spec_name, category, confidence, created_at, keywords)
                VALUES
                    (?, 'A content: root cause', 'myspec', 'gotcha', 0.9,
                     '2026-01-01 10:00:00', []),
                    (?, 'B content: downstream effect', 'myspec', 'pattern', 0.9,
                     '2026-01-02 10:00:00', [])
                """,
                [FACT_AAA, FACT_BBB],
            )
            conn.execute(
                "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?, ?)",
                [FACT_AAA, FACT_BBB],
            )

            # B has higher score than A — without causal ordering, B would appear first
            anchors = [
                _make_scored_fact(FACT_BBB, content="B content: downstream effect", score=0.9),
                _make_scored_fact(FACT_AAA, content="A content: root cause", score=0.5),
            ]
            config = RetrievalConfig()
            context = assemble_ranked_context(anchors, conn, config)

            pos_a = context.index("A content: root cause")
            pos_b = context.index("B content: downstream effect")
            assert pos_a < pos_b, "Causal predecessor A should appear before effect B"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-13: Provenance metadata in output
# ---------------------------------------------------------------------------


class TestProvenanceMetadata:
    """TS-104-13: Each fact in output includes spec name, confidence, salience tier.

    Requirements: 104-REQ-4.2
    """

    def test_output_contains_spec_confidence_and_tier(self) -> None:
        """Output contains spec name, confidence, and salience tier for each fact."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        try:
            fact = _make_scored_fact(
                FACT_AAA,
                content="JWT token validation prevents CSRF attacks",
                spec_name="03_auth",
                confidence=0.9,
                score=1.0,  # top score → [high] tier
            )
            config = RetrievalConfig()
            context = assemble_ranked_context([fact], conn, config)

            assert "spec: 03_auth" in context, "Context must include spec name"
            assert "confidence: 0.9" in context, "Context must include confidence value"
            assert "[high]" in context, "Single fact should be classified as high salience"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-14: Token budget respected
# ---------------------------------------------------------------------------


class TestTokenBudget:
    """TS-104-14: Output does not exceed configured token budget.

    Requirements: 104-REQ-4.3
    """

    def test_output_length_within_budget(self) -> None:
        """assemble_ranked_context output length ≤ token_budget."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        config = RetrievalConfig(token_budget=500)

        # Create 20 facts with large content
        anchors = [
            _make_scored_fact(
                str(uuid.uuid4()),
                content="X" * 200,  # 200-char content each
                score=1.0 / (i + 1),
            )
            for i in range(20)
        ]

        try:
            context = assemble_ranked_context(anchors, conn, config)
            assert len(context) <= 500, f"Output length {len(context)} exceeds token budget 500"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-15: Under-budget renders all facts fully
# ---------------------------------------------------------------------------


class TestUnderBudgetFullRender:
    """TS-104-15: Under-budget renders all selected facts at full detail.

    Requirements: 104-REQ-4.E1
    """

    def test_all_facts_rendered_when_budget_allows(self) -> None:
        """When total content fits within budget, all facts are fully rendered."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        config = RetrievalConfig(token_budget=30_000)

        anchors = [
            _make_scored_fact(FACT_AAA, content="Small fact A (unique A marker)", score=0.9),
            _make_scored_fact(FACT_BBB, content="Small fact B (unique B marker)", score=0.6),
            _make_scored_fact(FACT_CCC, content="Small fact C (unique C marker)", score=0.3),
        ]

        try:
            context = assemble_ranked_context(anchors, conn, config)
            assert "omitted" not in context.lower(), "No facts should be omitted under budget"
            assert "Small fact A" in context
            assert "Small fact B" in context
            assert "Small fact C" in context
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-16: Config defaults used when section absent
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    """TS-104-16: RetrievalConfig defaults are used when config section absent.

    Requirements: 104-REQ-5.3, 104-REQ-5.E1
    """

    def test_knowledge_config_has_retrieval_field_with_defaults(self) -> None:
        """KnowledgeConfig().retrieval has rrf_k=60, max_facts=50, token_budget=30000."""
        config = KnowledgeConfig()
        assert config.retrieval.rrf_k == 60
        assert config.retrieval.max_facts == 50
        assert config.retrieval.token_budget == 30_000

    def test_retrieval_config_standalone_defaults(self) -> None:
        """RetrievalConfig() has correct default values."""
        config = RetrievalConfig()
        assert config.rrf_k == 60
        assert config.max_facts == 50
        assert config.token_budget == 30_000


# ---------------------------------------------------------------------------
# TS-104-E4: Single signal fact scoring
# ---------------------------------------------------------------------------


class TestSingleSignalScoring:
    """TS-104-E4: Single-signal fact gets score = weight / (k + rank).

    Requirements: 104-REQ-2.E1
    """

    def test_single_signal_score_formula(self) -> None:
        """Fact X in keyword signal at rank 1 with weight 1.5 → score = 1.5/61."""
        fact_x = _make_scored_fact(FACT_X)
        signal_lists = {
            "keyword": [fact_x],
            "vector": [],
            "entity": [],
            "causal": [],
        }
        profile = IntentProfile(keyword_weight=1.5, vector_weight=1.0, entity_weight=1.0, causal_weight=1.0)
        result = weighted_rrf_fusion(signal_lists, profile, k=60)

        assert len(result) == 1
        expected_score = 1.5 / (60 + 1)
        assert abs(result[0].score - expected_score) < 1e-10, f"Expected score {expected_score}, got {result[0].score}"
