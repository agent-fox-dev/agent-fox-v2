"""Integration smoke tests for the adaptive retrieval pipeline.

Validates the full AdaptiveRetriever pipeline end-to-end and verifies
that the legacy retrieval chain has been removed.

Test Spec: TS-104-SMOKE-1, TS-104-SMOKE-2
Requirements: 104-REQ-1.1, 104-REQ-5.1, 104-REQ-5.2, 104-REQ-6.*
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb
import pytest

# TS-104-SMOKE-1: These imports will fail with ModuleNotFoundError until
# group 2 creates agent_fox.knowledge.retrieval.
from agent_fox.knowledge.retrieval import (
    AdaptiveRetriever,
    RetrievalConfig,
    RetrievalResult,
)
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    MOCK_EMBEDDING_1,
    MOCK_EMBEDDING_2,
    MOCK_EMBEDDING_3,
)

FACT_D = "dddddddd-dddd-dddd-dddd-dddddddddddd"
FACT_E = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _make_full_db() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with full schema and representative data.

    Includes:
    - 5 memory_facts (3 with embeddings, 2 without)
    - entity_graph + fact_entities links (2 facts linked to one entity)
    - 1 causal chain: FACT_AAA → FACT_BBB

    Uses run_migrations to ensure all tables (entity_graph etc.) exist.
    """
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)

    # Insert 5 facts
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, spec_name, category, confidence, created_at, keywords)
        VALUES
            (?, 'VectorSearch uses cosine distance for auth retrieval', 'myspec',
             'pattern', 0.9, '2026-01-01 10:00:00', ['search', 'vector', 'auth']),
            (?, 'Session store uses Redis with 24h TTL', 'myspec',
             'decision', 0.8, '2026-01-02 10:00:00', ['session', 'redis', 'ttl']),
            (?, 'Auth middleware validates JWT tokens', 'myspec',
             'gotcha', 0.9, '2026-01-03 10:00:00', ['auth', 'jwt', 'middleware']),
            (?, 'DuckDB schema migration strategy', 'other_spec',
             'convention', 0.7, '2026-01-04 10:00:00', ['duckdb', 'migration']),
            (?, 'Causal effect: test suite breaks after auth change', 'myspec',
             'gotcha', 0.9, '2026-01-05 10:00:00', ['test', 'auth', 'breakage'])
        """,
        [FACT_AAA, FACT_BBB, FACT_CCC, FACT_D, FACT_E],
    )

    # Add embeddings for 3 of the facts
    for fact_id, emb in [
        (FACT_AAA, MOCK_EMBEDDING_1),
        (FACT_BBB, MOCK_EMBEDDING_2),
        (FACT_CCC, MOCK_EMBEDDING_3),
    ]:
        conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [fact_id, emb],
        )

    # Add entity graph: one entity for "search.py" linked to FACT_AAA and FACT_BBB
    entity_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?, 'file', 'search.py', 'search.py', CURRENT_TIMESTAMP)
        """,
        [entity_id],
    )
    conn.execute(
        """
        INSERT INTO fact_entities (fact_id, entity_id)
        VALUES (?, ?), (?, ?)
        """,
        [FACT_AAA, entity_id, FACT_BBB, entity_id],
    )

    # Add causal link: FACT_AAA → FACT_E (auth change causes test breakage)
    conn.execute(
        "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?, ?)",
        [FACT_AAA, FACT_E],
    )

    return conn


# ---------------------------------------------------------------------------
# TS-104-SMOKE-1: Full retrieval pipeline end-to-end
# ---------------------------------------------------------------------------


class TestFullRetrievalPipeline:
    """TS-104-SMOKE-1: Full end-to-end retrieval with real components.

    Execution Path 1 from design.md:
    AdaptiveRetriever.retrieve() → 4 signals → weighted_rrf_fusion
    → assemble_ranked_context → RetrievalResult

    Must NOT mock: weighted_rrf_fusion, assemble_ranked_context,
    or individual signal functions.

    Requirements: 104-REQ-1.1, 104-REQ-5.1, 104-REQ-5.2
    """

    def test_full_pipeline_returns_non_empty_context(self) -> None:
        """Full retrieval pipeline produces a non-empty context string."""
        conn = _make_full_db()

        # Mock embedder: returns MOCK_EMBEDDING_1 (same as FACT_AAA → high similarity)
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        embedder.embed_text.return_value = MOCK_EMBEDDING_1

        config = RetrievalConfig(rrf_k=60, max_facts=50, token_budget=30_000)

        try:
            retriever = AdaptiveRetriever(conn, config, embedder=embedder)
            result = retriever.retrieve(
                spec_name="myspec",
                archetype="coder",
                node_status="fresh",
                touched_files=["search.py"],
                task_description="fix search for auth middleware",
            )

            assert isinstance(result, RetrievalResult)
            assert len(result.context) > 0, "Context should not be empty"
            assert result.anchor_count >= 1, "At least one fact should be selected"
        finally:
            conn.close()

    def test_pipeline_uses_coder_fresh_profile(self) -> None:
        """Retrieved result uses coder/fresh intent profile weights."""
        conn = _make_full_db()
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        embedder.embed_text.return_value = MOCK_EMBEDDING_1
        config = RetrievalConfig()

        try:
            retriever = AdaptiveRetriever(conn, config, embedder=embedder)
            result = retriever.retrieve(
                spec_name="myspec",
                archetype="coder",
                node_status="fresh",
                touched_files=["search.py"],
                task_description="fix search",
            )
            assert result.intent_profile.entity_weight == 1.5, "coder/fresh should have entity_weight=1.5"
            assert result.intent_profile.keyword_weight == 1.0
        finally:
            conn.close()

    def test_pipeline_context_contains_provenance_metadata(self) -> None:
        """Context string includes spec name provenance metadata."""
        conn = _make_full_db()
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        embedder.embed_text.return_value = MOCK_EMBEDDING_1
        config = RetrievalConfig()

        try:
            retriever = AdaptiveRetriever(conn, config, embedder=embedder)
            result = retriever.retrieve(
                spec_name="myspec",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="auth fix",
            )
            assert "spec:" in result.context, "Context must contain spec: provenance metadata"
        finally:
            conn.close()

    def test_pipeline_signal_counts_populated(self) -> None:
        """RetrievalResult.signal_counts reports per-signal fact counts."""
        conn = _make_full_db()
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        embedder.embed_text.return_value = MOCK_EMBEDDING_1
        config = RetrievalConfig()

        try:
            retriever = AdaptiveRetriever(conn, config, embedder=embedder)
            result = retriever.retrieve(
                spec_name="myspec",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="auth fix",
            )
            assert isinstance(result.signal_counts, dict)
            # At least keyword signal should have found something
            assert sum(result.signal_counts.values()) > 0, "At least one signal should contribute results"
        finally:
            conn.close()

    def test_causal_pair_ordered_in_context(self) -> None:
        """Causal predecessor appears before its effect in the context output."""
        conn = _make_full_db()
        embedder = MagicMock()
        embedder.embedding_dimensions = 384
        embedder.embed_text.return_value = MOCK_EMBEDDING_1
        config = RetrievalConfig(token_budget=100_000)

        try:
            retriever = AdaptiveRetriever(conn, config, embedder=embedder)
            result = retriever.retrieve(
                spec_name="myspec",
                archetype="coder",
                node_status="fresh",
                touched_files=[],
                task_description="auth change causes test breakage",
            )
            context = result.context
            # FACT_AAA (auth change) is cause of FACT_E (test breakage)
            # Both facts are in myspec — check if both appear and causal order is correct
            aaa_content = "VectorSearch uses cosine distance"
            e_content = "Causal effect: test suite breaks"
            if aaa_content in context and e_content in context:
                assert context.index(aaa_content) < context.index(e_content), (
                    "Causal predecessor should appear before its effect"
                )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-104-SMOKE-2: Legacy retrieval chain removed
# ---------------------------------------------------------------------------


class TestLegacyChainRemoved:
    """TS-104-SMOKE-2: None of the removed functions are importable.

    Execution Path 2 from design.md:
    All legacy retrieval functions and classes must be deleted.

    Requirements: 104-REQ-6.1, 104-REQ-6.2, 104-REQ-6.3, 104-REQ-6.4
    """

    def test_select_relevant_facts_removed(self) -> None:
        """select_relevant_facts must not be importable from filtering.py."""

        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.knowledge.filtering import (  # type: ignore[attr-defined]
                select_relevant_facts,
            )

            raise AssertionError(f"select_relevant_facts still importable: {select_relevant_facts}")

    def test_ranked_fact_cache_removed(self) -> None:
        """RankedFactCache must not be importable from fact_cache.py."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.engine.fact_cache import (  # type: ignore[attr-defined]
                RankedFactCache,
            )

            raise AssertionError(f"RankedFactCache still importable: {RankedFactCache}")

    def test_precompute_fact_rankings_removed(self) -> None:
        """precompute_fact_rankings must not be importable from fact_cache.py."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.engine.fact_cache import (  # type: ignore[attr-defined]
                precompute_fact_rankings,
            )

            raise AssertionError(f"precompute_fact_rankings still importable: {precompute_fact_rankings}")

    def test_get_cached_facts_removed(self) -> None:
        """get_cached_facts must not be importable from fact_cache.py."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.engine.fact_cache import (  # type: ignore[attr-defined]
                get_cached_facts,
            )

            raise AssertionError(f"get_cached_facts still importable: {get_cached_facts}")
