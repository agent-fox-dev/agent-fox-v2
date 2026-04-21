"""Tests for LLM-powered git commit knowledge extraction.

Suite 2: LLM-Powered Git Commit Extraction (TS-2.1 through TS-2.5)

Requirements: 113-REQ-2.1, 113-REQ-2.2, 113-REQ-2.3,
              113-REQ-2.E1, 113-REQ-2.E2
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from agent_fox.knowledge.ingest import KnowledgeIngestor


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


@pytest.fixture
def mock_embedder():
    """Mock embedder that returns dummy embeddings."""
    embedder = MagicMock()
    embedder.embedding_dimensions = 384
    embedder.embed_text.return_value = [0.0] * 384
    return embedder


@pytest.fixture
def ingestor(knowledge_conn_with_schema, mock_embedder, tmp_path):
    """KnowledgeIngestor with in-memory DB."""
    return KnowledgeIngestor(knowledge_conn_with_schema, mock_embedder, tmp_path)


# ---------------------------------------------------------------------------
# TS-2.1: Extract structured facts from commit batch
# ---------------------------------------------------------------------------


_SAMPLE_LLM_RESPONSE = json.dumps(
    [
        {
            "content": "The team decided to use async/await throughout the codebase for consistency.",
            "category": "decision",
            "confidence": "high",
            "keywords": ["async", "await", "consistency"],
        },
        {
            "content": "Use exponential backoff with jitter for retry logic in API calls.",
            "category": "pattern",
            "confidence": "medium",
            "keywords": ["retry", "backoff", "api"],
        },
        {
            "content": "DuckDB's FLOAT[] type requires explicit casting when inserting embeddings.",
            "category": "gotcha",
            "confidence": "low",
            "keywords": ["duckdb", "float", "embedding"],
        },
    ]
)


class TestExtractGitFactsLlm:
    """TS-2.1: _extract_git_facts_llm returns structured Fact objects."""

    @pytest.mark.asyncio
    async def test_returns_facts_with_correct_structure(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """TS-2.1: Returns 3 Fact objects with correct confidence values."""
        batch = [
            ("abc123", "feat: add async retry with exponential backoff", "2026-01-01"),
            ("def456", "fix: cast embedding to FLOAT[] before DuckDB insert", "2026-01-02"),
            (
                "ghi789",
                "chore: migrate entire codebase to async/await pattern",
                "2026-01-03",
            ),
            ("jkl012", "refactor: extract helper for date parsing to reduce duplication", "2026-01-04"),
            ("mno345", "test: add integration tests for knowledge harvest pipeline", "2026-01-05"),
        ]

        with patch(
            "agent_fox.core.client.ai_call",
            new=AsyncMock(return_value=(_SAMPLE_LLM_RESPONSE, MagicMock())),
        ):
            facts = await ingestor._extract_git_facts_llm(batch)

        assert len(facts) == 3

    @pytest.mark.asyncio
    async def test_confidence_values_are_mapped_correctly(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """TS-2.1, 113-REQ-2.3: confidence high=0.9, medium=0.6, low=0.3."""
        batch = [
            ("sha1", "feat: implement comprehensive logging strategy", "2026-01-01"),
        ]

        with patch(
            "agent_fox.core.client.ai_call",
            new=AsyncMock(return_value=(_SAMPLE_LLM_RESPONSE, MagicMock())),
        ):
            facts = await ingestor._extract_git_facts_llm(batch)

        confidences = {f.confidence for f in facts}
        assert confidences <= {0.9, 0.6, 0.3}, f"Unexpected confidence values: {confidences}"
        # Verify the specific mapping
        high_fact = next(f for f in facts if f.confidence == 0.9)
        med_fact = next(f for f in facts if f.confidence == 0.6)
        low_fact = next(f for f in facts if f.confidence == 0.3)
        assert high_fact is not None
        assert med_fact is not None
        assert low_fact is not None

    @pytest.mark.asyncio
    async def test_categories_are_valid(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """TS-2.1: Each fact category is in {decision, pattern, gotcha, convention}."""
        batch = [
            ("sha1", "feat: implement comprehensive logging strategy", "2026-01-01"),
        ]
        valid_git_categories = {"decision", "pattern", "gotcha", "convention"}

        with patch(
            "agent_fox.core.client.ai_call",
            new=AsyncMock(return_value=(_SAMPLE_LLM_RESPONSE, MagicMock())),
        ):
            facts = await ingestor._extract_git_facts_llm(batch)

        for fact in facts:
            assert fact.category in valid_git_categories, (
                f"Category {fact.category!r} not in {valid_git_categories}"
            )

    @pytest.mark.asyncio
    async def test_keywords_are_non_empty(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """TS-2.1: Each fact has a non-empty keywords list."""
        batch = [
            ("sha1", "feat: implement comprehensive logging strategy", "2026-01-01"),
        ]

        with patch(
            "agent_fox.core.client.ai_call",
            new=AsyncMock(return_value=(_SAMPLE_LLM_RESPONSE, MagicMock())),
        ):
            facts = await ingestor._extract_git_facts_llm(batch)

        for fact in facts:
            assert fact.keywords, f"Fact {fact.id} has empty keywords"


# ---------------------------------------------------------------------------
# TS-2.2: Zero facts from LLM yields no storage
# ---------------------------------------------------------------------------


class TestZeroFactsYieldsNoStorage:
    """TS-2.2: When LLM returns [], no rows inserted with category='git'."""

    @pytest.mark.asyncio
    async def test_empty_llm_response_stores_nothing(
        self,
        ingestor: KnowledgeIngestor,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        """TS-2.2: LLM returns [] → no git facts stored."""
        commits = [
            ("aaa111", "2026-01-01", "chore: bump version"),
            ("bbb222", "2026-01-02", "chore: update dependencies"),
            ("ccc333", "2026-01-03", "chore: fix typo in changelog"),
        ]
        # Patch git log to return boilerplate commits
        git_output = "\x1e".join(
            f"{sha}\x00{date}\x00{msg}" for sha, date, msg in commits
        )

        with (
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout="\x1e" + git_output),
            ),
            patch(
                "agent_fox.core.client.ai_call",
                new=AsyncMock(return_value=("[]", MagicMock())),
            ),
        ):
            result = await ingestor.ingest_git_commits()

        row = knowledge_conn_with_schema.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE category = 'git'"
        ).fetchone()
        assert row[0] == 0
        assert result.facts_added == 0

    @pytest.mark.asyncio
    async def test_ingest_git_commits_is_async(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """113-REQ-2.1: ingest_git_commits must be an async method."""
        import inspect
        assert inspect.iscoroutinefunction(ingestor.ingest_git_commits), (
            "ingest_git_commits must be an async (coroutine) function"
        )


# ---------------------------------------------------------------------------
# TS-2.3: LLM failure skips batch
# ---------------------------------------------------------------------------


class TestLlmFailureSkipsBatch:
    """TS-2.3: On LLM failure, batch is skipped and warning is logged."""

    @pytest.mark.asyncio
    async def test_first_batch_failure_skipped_second_succeeds(
        self,
        ingestor: KnowledgeIngestor,
        knowledge_conn_with_schema: duckdb.DuckDBPyConnection,
    ) -> None:
        """TS-2.3: Timeout on first batch → warning logged, second batch yields 2 facts."""
        # Create 40 commits: first 20 fail, second 20 succeed
        commits = []
        for i in range(40):
            sha = f"{'a' * 7}{i:02d}"
            msg = f"feat: implement feature number {i + 1} with comprehensive description"
            commits.append((sha, "2026-01-01", msg))

        git_output = "\x1e".join(
            f"{sha}\x00{date}\x00{msg}" for sha, date, msg in commits
        )

        two_facts_response = json.dumps(
            [
                {
                    "content": "Always use context managers for database connections in tests.",
                    "category": "convention",
                    "confidence": "high",
                    "keywords": ["context", "manager", "database"],
                },
                {
                    "content": "Parameterized SQL prevents injection attacks in DuckDB queries.",
                    "category": "pattern",
                    "confidence": "medium",
                    "keywords": ["sql", "injection", "security"],
                },
            ]
        )

        call_count = 0

        async def mock_ai_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("LLM timeout on first batch")
            return (two_facts_response, MagicMock())

        with (
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout="\x1e" + git_output),
            ),
            patch("agent_fox.core.client.ai_call", side_effect=mock_ai_call),
        ):
            result = await ingestor.ingest_git_commits()

        assert result.facts_added == 2


# ---------------------------------------------------------------------------
# TS-2.4: Short commit messages excluded
# ---------------------------------------------------------------------------


class TestShortCommitMessagesExcluded:
    """TS-2.4: Commit messages shorter than 20 chars are excluded from LLM batch."""

    @pytest.mark.asyncio
    async def test_short_messages_not_in_llm_prompt(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """TS-2.4: Only messages >= 20 chars are sent to the LLM batch."""
        # Three commits: two short (< 20 chars), one long
        commits = [
            ("sha001", "2026-01-01", "fix typo"),         # 9 chars — excluded
            ("sha002", "2026-01-02", "ok"),                # 2 chars — excluded
            (
                "sha003",
                "2026-01-03",
                "refactor: extract helper function for date parsing to reduce duplication",
            ),  # 60+ chars — included
        ]
        git_output = "\x1e".join(
            f"{sha}\x00{date}\x00{msg}" for sha, date, msg in commits
        )

        captured_calls: list[str] = []

        async def capture_ai_call(*args, **kwargs):
            messages = kwargs.get("messages") or (args[2] if len(args) > 2 else [])
            for msg in messages:
                captured_calls.append(msg.get("content", ""))
            return (
                json.dumps(
                    [
                        {
                            "content": "Extract helpers to reduce code duplication in date parsing logic.",
                            "category": "pattern",
                            "confidence": "medium",
                            "keywords": ["refactor", "helper", "date"],
                        }
                    ]
                ),
                MagicMock(),
            )

        with (
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout="\x1e" + git_output),
            ),
            patch("agent_fox.core.client.ai_call", side_effect=capture_ai_call),
        ):
            await ingestor.ingest_git_commits()

        # The short messages ("fix typo", "ok") must not appear in the LLM prompt
        all_prompt_content = " ".join(captured_calls)
        assert "fix typo" not in all_prompt_content, "Short message 'fix typo' leaked into LLM prompt"
        assert "ok" not in all_prompt_content.split(), "Short message 'ok' leaked into LLM prompt"
        # The long message should be present
        assert "date parsing" in all_prompt_content or "reduce duplication" in all_prompt_content


# ---------------------------------------------------------------------------
# TS-2.5: Batch size limit of 20
# ---------------------------------------------------------------------------


class TestBatchSizeLimit:
    """TS-2.5: 25 commits → LLM called twice (batch of 20, batch of 5)."""

    @pytest.mark.asyncio
    async def test_llm_called_twice_for_25_commits(
        self,
        ingestor: KnowledgeIngestor,
    ) -> None:
        """TS-2.5: ingest_git_commits batches in groups of 20."""
        # 25 valid commits (all > 20 chars)
        commits = []
        for i in range(25):
            sha = f"{i:040x}"[:40]
            msg = f"feat: implement feature number {i + 1} with a comprehensive description"
            commits.append((sha, "2026-01-01", msg))

        git_output = "\x1e".join(
            f"{sha}\x00{date}\x00{msg}" for sha, date, msg in commits
        )

        ai_call_count = 0

        async def counting_ai_call(*args, **kwargs):
            nonlocal ai_call_count
            ai_call_count += 1
            return ("[]", MagicMock())

        with (
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout="\x1e" + git_output),
            ),
            patch("agent_fox.core.client.ai_call", side_effect=counting_ai_call),
        ):
            await ingestor.ingest_git_commits()

        assert ai_call_count == 2, (
            f"Expected 2 LLM calls for 25 commits (batch of 20 + batch of 5), got {ai_call_count}"
        )
