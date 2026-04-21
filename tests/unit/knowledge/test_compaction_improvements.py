"""Tests for compaction improvements: substring supersession and noise filtering.

Suite 5: Compaction and Noise Reduction (TS-5.1 through TS-5.5)

Requirements: 113-REQ-5.1, 113-REQ-5.2, 113-REQ-5.3, 113-REQ-5.E1
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest

from agent_fox.engine.knowledge_harvest import _filter_minimum_length

# Import the new functions — will fail with ImportError until implemented (tasks 2.3, 2.4).
from agent_fox.knowledge.compaction import _substring_supersede
from agent_fox.knowledge.facts import Fact


@pytest.fixture
def knowledge_conn_with_schema():
    """In-memory DuckDB with full production schema."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _make_fact(
    content: str,
    confidence: float = 0.8,
    fact_id: str | None = None,
    created_at: str = "2026-01-01T10:00:00+00:00",
) -> Fact:
    """Create a Fact with given content and confidence."""
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content,
        category="pattern",
        spec_name="test_spec",
        keywords=["test"],
        confidence=confidence,
        created_at=created_at,
        supersedes=None,
    )


# ---------------------------------------------------------------------------
# TS-5.1: Substring supersession
# ---------------------------------------------------------------------------


class TestSubstringSuperession:
    """TS-5.1: _substring_supersede identifies and supersedes substring facts."""

    def test_substring_fact_is_superseded(self) -> None:
        """TS-5.1: Fact A (substring of B with equal confidence) is superseded."""
        fact_a = _make_fact("Use retry logic", confidence=0.8)
        fact_b = _make_fact(
            "Use retry logic with exponential backoff for API calls", confidence=0.8
        )
        fact_c = _make_fact(
            "Database connections use connection pooling", confidence=0.7
        )

        surviving, superseded_count = _substring_supersede([fact_a, fact_b, fact_c])

        surviving_ids = {f.id for f in surviving}
        # Fact A is a substring of B → A should be superseded
        assert fact_a.id not in surviving_ids, "Fact A (substring of B) should be superseded"
        # Fact B survives
        assert fact_b.id in surviving_ids, "Fact B (superset) should survive"
        # Fact C is unrelated → survives
        assert fact_c.id in surviving_ids, "Fact C (unrelated) should survive"

    def test_superseded_count_is_one(self) -> None:
        """TS-5.1: Returns superseded_count == 1 for the substring case."""
        fact_a = _make_fact("Use retry logic", confidence=0.8)
        fact_b = _make_fact(
            "Use retry logic with exponential backoff for API calls", confidence=0.8
        )

        _surviving, superseded_count = _substring_supersede([fact_a, fact_b])

        assert superseded_count == 1

    def test_lower_confidence_substring_superseded(self) -> None:
        """TS-5.1: Lower-confidence fact that is substring of higher-confidence is superseded."""
        fact_short = _make_fact("Cache database queries", confidence=0.6)
        fact_long = _make_fact(
            "Cache database queries using Redis with a TTL of 60 seconds for performance",
            confidence=0.9,
        )

        surviving, superseded_count = _substring_supersede([fact_short, fact_long])

        surviving_ids = {f.id for f in surviving}
        assert fact_short.id not in surviving_ids
        assert fact_long.id in surviving_ids
        assert superseded_count == 1

    def test_no_supersession_when_no_substrings(self) -> None:
        """TS-5.1: No supersession when no content is a substring of another."""
        fact_a = _make_fact("Alpha beta gamma delta epsilon", confidence=0.8)
        fact_b = _make_fact("Zeta eta theta iota kappa", confidence=0.8)

        surviving, superseded_count = _substring_supersede([fact_a, fact_b])

        assert superseded_count == 0
        assert len(surviving) == 2

    def test_higher_confidence_substring_not_superseded_by_lower(self) -> None:
        """TS-5.1: A substring with HIGHER confidence is NOT superseded by
        a longer fact with lower confidence.
        """
        fact_short = _make_fact("Use retry logic", confidence=0.9)
        fact_long = _make_fact(
            "Use retry logic with exponential backoff for API calls", confidence=0.6
        )

        surviving, superseded_count = _substring_supersede([fact_short, fact_long])

        surviving_ids = {f.id for f in surviving}
        # fact_short has higher confidence so it must not be superseded
        assert fact_short.id in surviving_ids


# ---------------------------------------------------------------------------
# TS-5.2: Minimum content length filter
# ---------------------------------------------------------------------------


class TestFilterMinimumLength:
    """TS-5.2: _filter_minimum_length rejects facts shorter than 50 chars."""

    def test_filters_short_facts(self) -> None:
        """TS-5.2: Facts with content length 30 and 49 are filtered out."""
        facts = [
            _make_fact("A" * 30),   # 30 chars — below threshold
            _make_fact("B" * 49),   # 49 chars — below threshold (< 50)
            _make_fact("C" * 50),   # exactly 50 chars — passes
        ]

        passing, filtered_count = _filter_minimum_length(facts, min_length=50)

        assert len(passing) == 1
        assert passing[0].content == "C" * 50
        assert filtered_count == 2

    def test_filtered_count_is_two(self) -> None:
        """TS-5.2: filtered_count == 2 for the 30/49/50 scenario."""
        facts = [
            _make_fact("A" * 30),
            _make_fact("B" * 49),
            _make_fact("C" * 50),
        ]

        _passing, filtered_count = _filter_minimum_length(facts, min_length=50)

        assert filtered_count == 2

    def test_empty_input_returns_empty(self) -> None:
        """TS-5.2: Empty input → empty output, filtered_count=0."""
        passing, filtered_count = _filter_minimum_length([], min_length=50)
        assert passing == []
        assert filtered_count == 0

    def test_all_pass_when_all_long_enough(self) -> None:
        """TS-5.2: No filtering when all facts meet the threshold."""
        facts = [_make_fact("X" * 50), _make_fact("Y" * 100)]
        passing, filtered_count = _filter_minimum_length(facts, min_length=50)
        assert len(passing) == 2
        assert filtered_count == 0


class TestShortFactsRejectedAtTranscriptIngestion:
    """TS-5.2b: Short facts are filtered before storage in extract_and_store_knowledge."""

    @pytest.mark.asyncio
    async def test_only_long_fact_stored(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-5.2b: Facts with content < 50 chars are not stored."""
        import uuid
        from unittest.mock import patch

        from agent_fox.engine.knowledge_harvest import extract_and_store_knowledge
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.facts import Fact

        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = knowledge_conn_with_schema

        short_fact_1 = Fact(
            id=str(uuid.uuid4()),
            content="A" * 30,  # 30 chars — below threshold
            category="gotcha",
            spec_name="test_spec",
            keywords=["short"],
            confidence=0.9,
            created_at="2026-01-01T10:00:00+00:00",
            supersedes=None,
        )
        short_fact_2 = Fact(
            id=str(uuid.uuid4()),
            content="B" * 49,  # 49 chars — below threshold
            category="pattern",
            spec_name="test_spec",
            keywords=["short"],
            confidence=0.9,
            created_at="2026-01-01T10:00:00+00:00",
            supersedes=None,
        )
        long_fact = Fact(
            id=str(uuid.uuid4()),
            content="C" * 60,  # 60 chars — above threshold
            category="decision",
            spec_name="test_spec",
            keywords=["long"],
            confidence=0.9,
            created_at="2026-01-01T10:00:00+00:00",
            supersedes=None,
        )

        transcript = "T" * 3000  # > 2000 chars so extraction proceeds

        async def fake_extract_facts(transcript, spec_name, *args, **kwargs):
            return [short_fact_1, short_fact_2, long_fact]

        with patch(
            "agent_fox.engine.knowledge_harvest.extract_facts",
            side_effect=fake_extract_facts,
        ):
            await extract_and_store_knowledge(
                transcript,
                "test_spec",
                "test/1",
                "SIMPLE",
                db,
            )

        # Only the 60-char fact should be in the DB
        rows = knowledge_conn_with_schema.execute(
            "SELECT content FROM memory_facts WHERE spec_name = 'test_spec'"
        ).fetchall()
        contents = [r[0] for r in rows]

        assert any(len(c) == 60 for c in contents), "60-char fact should be stored"
        assert not any(len(c) == 30 for c in contents), "30-char fact should not be stored"
        assert not any(len(c) == 49 for c in contents), "49-char fact should not be stored"


class TestShortFactsRejectedAtGitIngestion:
    """TS-5.2c: Short facts from git extraction are not stored."""

    @pytest.mark.asyncio
    async def test_only_long_git_fact_stored(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-5.2c: Git extraction: fact with content < 50 chars not stored."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.knowledge.ingest import KnowledgeIngestor

        mock_embedder = MagicMock()
        mock_embedder.embedding_dimensions = 384
        mock_embedder.embed_text.return_value = [0.0] * 384
        ingestor = KnowledgeIngestor(knowledge_conn_with_schema, mock_embedder, tmp_path)

        # Two commits: one valid for batching
        commits = [
            ("sha_long", "2026-01-01", "feat: implement comprehensive feature with full description"),
        ]
        git_output = "\x1e".join(
            f"{sha}\x00{date}\x00{msg}" for sha, date, msg in commits
        )

        llm_response = json.dumps(
            [
                {
                    "content": "A" * 40,  # 40 chars — below 50 threshold
                    "category": "gotcha",
                    "confidence": "medium",
                    "keywords": ["short"],
                },
                {
                    "content": "B" * 80,  # 80 chars — above threshold
                    "category": "decision",
                    "confidence": "high",
                    "keywords": ["long", "important"],
                },
            ]
        )

        with (
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout="\x1e" + git_output),
            ),
            patch(
                "agent_fox.core.client.ai_call",
                new=AsyncMock(return_value=(llm_response, MagicMock())),
            ),
        ):
            await ingestor.ingest_git_commits()

        rows = knowledge_conn_with_schema.execute(
            "SELECT content FROM memory_facts WHERE category = 'git'"
        ).fetchall()
        contents = [r[0] for r in rows]

        assert any(len(c) == 80 for c in contents), "80-char fact should be stored"
        assert not any(len(c) == 40 for c in contents), "40-char fact should not be stored"


# ---------------------------------------------------------------------------
# TS-5.3: Confidence-aware deduplication
# ---------------------------------------------------------------------------


class TestConfidenceAwareDeduplication:
    """TS-5.3: Higher-confidence fact survives when near-duplicates are found."""

    def test_lower_confidence_fact_superseded(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-5.3: Fact A (confidence=0.6) superseded by Fact B (confidence=0.8)
        when cosine similarity > 0.92.
        """
        from agent_fox.knowledge.compaction import compact

        conn = knowledge_conn_with_schema
        # Insert two very similar facts with different confidence
        fact_a_id = str(uuid.uuid4())
        fact_b_id = str(uuid.uuid4())

        # Same content hash → dedup will apply regardless of embedding
        same_content = "Use connection pooling for database access to improve performance"
        conn.execute(
            """
            INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)
            VALUES
                (?::UUID, ?, 'pattern', 'spec1', 0.6, '2026-01-01 10:00:00'),
                (?::UUID, ?, 'pattern', 'spec1', 0.8, '2026-01-01 11:00:00')
            """,
            [fact_a_id, same_content, fact_b_id, same_content + " and reduce latency"],
        )

        # Insert embedding vectors with high similarity for fact_a and fact_b
        # (near-identical vectors)
        import math

        def _unit_vec(seed: float, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1)) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        vec_a = _unit_vec(1.0)
        vec_b = _unit_vec(1.0001)  # Nearly identical → cosine similarity ≈ 1.0

        conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[384])",
            [fact_a_id, vec_a],
        )
        conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[384])",
            [fact_b_id, vec_b],
        )

        original, surviving = compact(conn)

        # After dedup: higher-confidence fact (b) survives, lower (a) is superseded
        surviving_row = conn.execute(
            "SELECT id::VARCHAR, superseded_by FROM memory_facts WHERE id = ?::UUID",
            [fact_a_id],
        ).fetchone()
        assert surviving_row is not None
        # fact_a should be superseded (lower confidence)
        assert surviving_row[1] is not None, (
            "Fact A (lower confidence=0.6) should be superseded by higher-confidence Fact B"
        )


class TestConfidenceTieBreakingByRecency:
    """TS-5.4: When confidences are equal, more recent fact survives."""

    def test_older_fact_superseded_when_equal_confidence(
        self, knowledge_conn_with_schema: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-5.4: Same confidence=0.7 → more recent fact (T2) survives."""
        from agent_fox.knowledge.compaction import compact

        conn = knowledge_conn_with_schema
        fact_a_id = str(uuid.uuid4())  # Older
        fact_b_id = str(uuid.uuid4())  # More recent

        same_content = "Always validate input data before processing in the pipeline"
        conn.execute(
            """
            INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)
            VALUES
                (?::UUID, ?, 'convention', 'spec1', 0.7, '2026-01-01 10:00:00'),
                (?::UUID, ?, 'convention', 'spec1', 0.7, '2026-01-02 10:00:00')
            """,
            [fact_a_id, same_content, fact_b_id, same_content],
        )

        compact(conn)

        # fact_a (older) should be superseded; fact_b (more recent) should survive
        row_a = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE id = ?::UUID",
            [fact_a_id],
        ).fetchone()
        row_b = conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE id = ?::UUID",
            [fact_b_id],
        ).fetchone()

        assert row_a is not None and row_a[0] is not None, (
            "Fact A (older, equal confidence) should be superseded"
        )
        assert row_b is not None and row_b[0] is None, (
            "Fact B (more recent, equal confidence) should survive"
        )


# ---------------------------------------------------------------------------
# TS-5.5: Large compaction logs info message
# ---------------------------------------------------------------------------


class TestLargeCompactionLogged:
    """TS-5.5: Info log emitted when compaction reduces facts by more than 50%."""

    def test_info_log_emitted_for_large_reduction(
        self,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-5.5: 10 facts → 4 survivors → logs info with before/after counts."""
        import logging

        from agent_fox.knowledge.compaction import compact

        conn = knowledge_conn_with_schema
        # Insert 10 facts: 6 duplicates and 4 unique
        unique_content_base = "Unique fact about the system design decision number {i}"
        dup_content = "Duplicate fact content for compaction test scenario reduction"

        for i in range(4):
            conn.execute(
                """
                INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)
                VALUES (?::UUID, ?, 'decision', 'spec_test', 0.8, CURRENT_TIMESTAMP)
                """,
                [str(uuid.uuid4()), unique_content_base.format(i=i)],
            )

        for _ in range(6):
            conn.execute(
                """
                INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)
                VALUES (?::UUID, ?, 'pattern', 'spec_test', 0.7, CURRENT_TIMESTAMP)
                """,
                [str(uuid.uuid4()), dup_content],
            )

        with caplog.at_level(logging.INFO, logger="agent_fox.knowledge.compaction"):
            original, surviving = compact(conn)

        # Reduction > 50% should trigger info log with before/after counts
        assert original == 10
        assert surviving <= 5  # At least 50% reduction
        assert any(
            str(original) in record.message and str(surviving) in record.message
            for record in caplog.records
        ), f"Expected info log with before/after counts. Log records: {[r.message for r in caplog.records]}"
