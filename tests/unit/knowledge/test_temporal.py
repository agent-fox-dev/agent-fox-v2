"""Tests for temporal query and timeline rendering.

Requirements: 13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3
"""

from __future__ import annotations

from agent_fox.knowledge.query import Timeline, TimelineNode, temporal_query
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    MOCK_EMBEDDING_1,
    MOCK_QUERY_EMBEDDING,
    create_empty_db,
    insert_fact_with_embedding,
    make_deterministic_embedding,
)


class TestTimelineRendering:
    """13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3: Timeline rendering."""

    def test_renders_indented_text(self) -> None:
        """Root at depth 0, effects indented."""
        nodes = [
            TimelineNode(
                fact_id=FACT_AAA,
                content="User.email changed to nullable",
                spec_name="07_oauth",
                session_id="07/3",
                commit_sha="a1b2c3d",
                timestamp="2025-11-03T14:22:00",
                relationship="root",
                depth=0,
            ),
            TimelineNode(
                fact_id=FACT_BBB,
                content="test_user_model.py assertions failed",
                spec_name="09_user_tests",
                session_id="09/1",
                commit_sha="e4f5g6h",
                timestamp="2025-11-17T09:15:00",
                relationship="effect",
                depth=1,
            ),
        ]
        tl = Timeline(nodes=nodes, query="test")
        text = tl.render(use_color=False)

        assert "** User.email changed to nullable" in text
        assert "  -> test_user_model.py assertions failed" in text
        assert "[2025-11-03T14:22:00]" in text
        assert "spec:07_oauth" in text
        assert "commit:a1b2c3d" in text

    def test_depth_controls_indentation(self) -> None:
        """13-REQ-6.2: Indentation depth matches node depth."""
        node = TimelineNode(
            fact_id="x",
            content="deep effect",
            spec_name="s",
            session_id="s/1",
            commit_sha=None,
            timestamp="2025-01-01",
            relationship="effect",
            depth=3,
        )
        tl = Timeline(nodes=[node], query="test")
        text = tl.render(use_color=False)
        # 3 levels of indentation (2 spaces each) = 6 spaces
        assert "      -> deep effect" in text

    def test_plain_text_no_ansi(self) -> None:
        """13-REQ-6.3: No ANSI escape codes in plain text mode."""
        node = TimelineNode(
            fact_id="x",
            content="fact",
            spec_name="s",
            session_id="s/1",
            commit_sha=None,
            timestamp=None,
            relationship="root",
            depth=0,
        )
        tl = Timeline(nodes=[node], query="test")
        text = tl.render(use_color=False)
        assert "\x1b[" not in text

    def test_empty_timeline_message(self) -> None:
        """Empty timeline produces informational message."""
        tl = Timeline(nodes=[], query="test")
        text = tl.render()
        assert "No causal timeline" in text

    def test_missing_provenance_shows_na(self) -> None:
        """Missing provenance fields show n/a."""
        node = TimelineNode(
            fact_id="x",
            content="fact",
            spec_name=None,
            session_id=None,
            commit_sha=None,
            timestamp=None,
            relationship="root",
            depth=0,
        )
        tl = Timeline(nodes=[node], query="test")
        text = tl.render(use_color=False)
        assert "spec:n/a" in text
        assert "commit:n/a" in text


class TestTemporalQuery:
    """13-REQ-4.1: Temporal query combines vector search + causal traversal."""

    def test_finds_causal_chain_from_vector_search(self) -> None:
        """Vector search seed expands through causal graph."""
        conn = create_empty_db()
        try:
            # Install VSS extension for vector search
            conn.execute("INSTALL vss; LOAD vss;")
            conn.execute(
                "CREATE INDEX emb_idx ON memory_embeddings "
                "USING HNSW (embedding) WITH (metric = 'cosine');"
            )
        except Exception:
            conn.close()
            return  # Skip if VSS not available

        try:
            # Insert facts with embeddings
            emb1 = MOCK_EMBEDDING_1
            emb2 = make_deterministic_embedding(2)
            emb3 = make_deterministic_embedding(3)

            insert_fact_with_embedding(
                conn,
                FACT_AAA,
                "User.email changed to nullable",
                emb1,
                spec_name="07_oauth",
                session_id="07/3",
                commit_sha="a1b2c3d",
            )
            insert_fact_with_embedding(
                conn,
                FACT_BBB,
                "test assertions failed",
                emb2,
                spec_name="09_user_tests",
                session_id="09/1",
                commit_sha="e4f5g6h",
            )
            insert_fact_with_embedding(
                conn,
                FACT_CCC,
                "Added migration for nullable email",
                emb3,
                spec_name="12_auth_fix",
                session_id="12/2",
                commit_sha="i7j8k9l",
            )

            # Add causal links: AAA -> BBB -> CCC
            conn.execute(
                "INSERT INTO fact_causes VALUES (?::UUID, ?::UUID), (?::UUID, ?::UUID)",
                [FACT_AAA, FACT_BBB, FACT_BBB, FACT_CCC],
            )

            tl = temporal_query(
                conn,
                "What happened with the email field?",
                MOCK_QUERY_EMBEDDING,
                top_k=5,
                max_depth=5,
            )

            assert len(tl.nodes) >= 1
            ids = {n.fact_id for n in tl.nodes}
            # The seed should find AAA (most similar to query embedding),
            # and traversal should follow the chain
            assert FACT_AAA in ids
        finally:
            conn.close()

    def test_empty_store_returns_empty_timeline(self) -> None:
        """Empty knowledge store returns empty timeline."""
        conn = create_empty_db()
        try:
            conn.execute("INSTALL vss; LOAD vss;")
            conn.execute(
                "CREATE INDEX emb_idx ON memory_embeddings "
                "USING HNSW (embedding) WITH (metric = 'cosine');"
            )
        except Exception:
            conn.close()
            return

        try:
            tl = temporal_query(
                conn,
                "anything",
                MOCK_QUERY_EMBEDDING,
                top_k=5,
            )
            assert len(tl.nodes) == 0
        finally:
            conn.close()
