"""Tests for knowledge source ingestion.

Test Spec: TS-12-15 (ADR ingestion), TS-12-16 (git commit ingestion),
           TS-12-E4 (missing ADR directory), errata ingestion (issue #332)
Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb

from agent_fox.knowledge.ingest import IngestResult, KnowledgeIngestor, run_background_ingestion


def _create_adr_files(adr_dir: Path, filenames: list[str]) -> None:
    """Create mock ADR markdown files."""
    adr_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        content = f"# ADR: {name.replace('.md', '').replace('-', ' ')}\n\n"
        content += "## Status\n\nAccepted\n\n"
        content += "## Context\n\nThis is the context for the decision.\n\n"
        content += "## Decision\n\nWe decided to do this.\n"
        (adr_dir / name).write_text(content)


def _mock_git_log_output(commits: list[tuple[str, str, str]]) -> MagicMock:
    """Create a mock subprocess result for git log.

    Args:
        commits: List of (sha, date, message) tuples.
    """
    # Format as git log --format output (record-separator delimited)
    records = []
    for sha, date, message in commits:
        records.append(f"\x1e{sha}\x00{date}\x00{message}")
    output = "".join(records)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output
    return mock_result


class TestIngestADRs:
    """TS-12-15: Ingest ADRs creates facts with correct category.

    Requirements: 12-REQ-4.1, 12-REQ-4.3
    """

    def test_creates_adr_facts(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify ingesting ADRs creates facts with category='adr'."""
        adr_dir = tmp_path / "docs" / "adr"
        _create_adr_files(adr_dir, ["001-use-duckdb.md", "002-use-click.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_adrs(adr_dir=adr_dir)

        assert result.facts_added == 2
        assert result.source_type == "adr"

        rows = schema_conn.execute("SELECT * FROM memory_facts WHERE category = 'adr'").fetchall()
        assert len(rows) == 2

    def test_adr_facts_have_embeddings(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify ingested ADR facts have embeddings stored."""
        adr_dir = tmp_path / "docs" / "adr"
        _create_adr_files(adr_dir, ["001-use-duckdb.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        ingestor.ingest_adrs(adr_dir=adr_dir)

        emb_count = schema_conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()
        assert emb_count is not None
        assert emb_count[0] >= 1

    def test_default_adr_dir(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify default ADR directory is docs/adr/ under project root."""
        adr_dir = tmp_path / "docs" / "adr"
        _create_adr_files(adr_dir, ["001-use-duckdb.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_adrs()  # no explicit adr_dir

        assert result.facts_added == 1


class TestIngestGitCommits:
    """TS-12-16: Ingest git commits creates facts with commit SHA.

    Requirements: 12-REQ-4.2, 12-REQ-4.3
    """

    async def test_creates_git_facts(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify ingesting git commits creates facts with category='git'.

        Post-113: ingest_git_commits is async and uses LLM extraction.
        We mock the LLM call to return structured facts.
        """
        mock_git_result = _mock_git_log_output(
            [
                ("abc1234", "2025-11-01T10:00:00",
                 "feat: add user authentication with JWT tokens"),
                ("def5678", "2025-11-02T11:00:00",
                 "fix: correct password hashing to use bcrypt"),
                ("ghi9012", "2025-11-03T12:00:00",
                 "refactor: clean up auth module and extract helpers"),
            ]
        )

        # Mock LLM to return 3 facts (one per commit-like extraction)
        mock_llm_facts = [
            {
                "content": "JWT tokens are used for user authentication"
                " with session management support",
                "category": "decision",
                "confidence": "high",
                "keywords": ["jwt", "auth"],
            },
            {
                "content": "Bcrypt is preferred over md5 for password"
                " hashing due to security considerations",
                "category": "decision",
                "confidence": "high",
                "keywords": ["bcrypt", "security"],
            },
            {
                "content": "Auth module helper functions should be"
                " extracted for clarity and reusability",
                "category": "pattern",
                "confidence": "medium",
                "keywords": ["auth", "refactor"],
            },
        ]

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        llm_resp = (json.dumps(mock_llm_facts), None)
        with (
            patch(
                "agent_fox.knowledge.ingest.subprocess.run",
                return_value=mock_git_result,
            ),
            patch(
                "agent_fox.core.client.ai_call",
                new_callable=AsyncMock,
                return_value=llm_resp,
            ),
        ):
            result = await ingestor.ingest_git_commits(limit=10)

        assert result.facts_added == 3
        assert result.source_type == "git"

    async def test_git_facts_have_commit_sha(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify each git fact has commit_sha populated.

        Post-113: ingest_git_commits is async and uses LLM extraction.
        """
        mock_git_result = _mock_git_log_output(
            [
                ("abc1234", "2025-11-01T10:00:00",
                 "feat: add feature with comprehensive implementation"),
                ("def5678", "2025-11-02T11:00:00",
                 "fix: fix bug in the authentication pipeline"),
                ("ghi9012", "2025-11-03T12:00:00",
                 "refactor: cleanup of the database module"),
            ]
        )

        mock_llm_facts = [
            {
                "content": "Feature implementation should include"
                " comprehensive documentation for maintainability",
                "category": "convention",
                "confidence": "high",
                "keywords": ["docs"],
            },
            {
                "content": "Authentication pipeline requires special"
                " attention to edge cases in error handling",
                "category": "gotcha",
                "confidence": "medium",
                "keywords": ["auth"],
            },
            {
                "content": "Database module refactoring improves"
                " maintainability through separation of concerns",
                "category": "pattern",
                "confidence": "high",
                "keywords": ["database"],
            },
        ]

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        llm_resp = (json.dumps(mock_llm_facts), None)
        with (
            patch(
                "agent_fox.knowledge.ingest.subprocess.run",
                return_value=mock_git_result,
            ),
            patch(
                "agent_fox.core.client.ai_call",
                new_callable=AsyncMock,
                return_value=llm_resp,
            ),
        ):
            await ingestor.ingest_git_commits(limit=10)

        rows = schema_conn.execute("SELECT commit_sha FROM memory_facts WHERE category = 'git'").fetchall()
        assert len(rows) == 3
        assert all(row[0] is not None for row in rows)

    async def test_git_facts_have_category(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify git facts have category='git'.

        Post-113: ingest_git_commits is async and uses LLM extraction.
        """
        mock_git_result = _mock_git_log_output(
            [
                ("abc1234", "2025-11-01T10:00:00",
                 "feat: add feature with comprehensive details"),
            ]
        )

        mock_llm_facts = [
            {
                "content": "Feature implementation requires comprehensive"
                " details for proper code review and maintenance",
                "category": "convention",
                "confidence": "high",
                "keywords": ["feature"],
            },
        ]

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        llm_resp = (json.dumps(mock_llm_facts), None)
        with (
            patch(
                "agent_fox.knowledge.ingest.subprocess.run",
                return_value=mock_git_result,
            ),
            patch(
                "agent_fox.core.client.ai_call",
                new_callable=AsyncMock,
                return_value=llm_resp,
            ),
        ):
            await ingestor.ingest_git_commits(limit=10)

        rows = schema_conn.execute("SELECT category FROM memory_facts WHERE category = 'git'").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "git"


class TestIngestMissingADRDirectory:
    """TS-12-E4: Ingest ADRs with missing directory.

    Requirement: 12-REQ-4.1
    """

    def test_returns_zero_facts(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify returns IngestResult with 0 facts when dir missing."""
        # tmp_path has no docs/adr/ directory
        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_adrs()

        assert result.facts_added == 0
        assert result.facts_skipped == 0
        assert result.source_type == "adr"

    def test_no_exception_raised(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify no exception for missing ADR directory."""
        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        # Should not raise
        result = ingestor.ingest_adrs()
        assert isinstance(result, IngestResult)


def _create_errata_files(errata_dir: Path, filenames: list[str]) -> None:
    """Create mock errata markdown files."""
    errata_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        spec_num = name.split("_")[0] if "_" in name else "00"
        title = name.replace(".md", "").replace("_", " ")
        content = f"# Erratum: {title}\n\n"
        content += "## Divergence\n\nImplementation diverges from spec.\n\n"
        content += f"## Reason\n\nSpec {spec_num} design was not feasible due to technical constraints.\n"
        (errata_dir / name).write_text(content)


class TestIngestErrata:
    """AC-1, AC-2, AC-3, AC-7: Ingest errata creates facts with correct category.

    Issue: #332
    """

    def test_creates_errata_facts(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-1: Verify ingesting errata creates facts with category='errata'."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(
            errata_dir,
            ["93_ts93_4_placement.md", "28_github_issue_rest_api.md"],
        )

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_errata(errata_dir=errata_dir)

        assert result.source_type == "errata"
        assert result.facts_added == 2
        assert result.facts_skipped == 0

        rows = schema_conn.execute(
            "SELECT spec_name FROM memory_facts WHERE category = 'errata' ORDER BY spec_name"
        ).fetchall()
        assert len(rows) == 2
        spec_names = {row[0] for row in rows}
        assert "93_ts93_4_placement.md" in spec_names
        assert "28_github_issue_rest_api.md" in spec_names

    def test_errata_facts_have_embeddings(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-2: Verify ingested errata facts have embeddings stored."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(errata_dir, ["93_ts93_4_placement.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        ingestor.ingest_errata(errata_dir=errata_dir)

        count = schema_conn.execute(
            """
            SELECT COUNT(*)
            FROM memory_embeddings e
            JOIN memory_facts f ON e.id = f.id
            WHERE f.category = 'errata'
            """
        ).fetchone()
        assert count is not None
        assert count[0] == 1

    def test_ingest_result_fields(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-3: Verify IngestResult has correct source_type and counts."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(
            errata_dir,
            ["93_ts93_4_placement.md", "28_github_issue_rest_api.md"],
        )

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_errata(errata_dir=errata_dir)

        assert result.source_type == "errata"
        assert result.facts_added == 2
        assert result.facts_skipped == 0
        assert result.embedding_failures == 0

    def test_default_errata_dir(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-7: Verify default errata directory is docs/errata/ under project root."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(errata_dir, ["93_ts93_4_placement.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_errata()  # no explicit errata_dir

        assert result.facts_added == 1

    def test_custom_errata_dir(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-7: Verify errata_dir parameter overrides the default directory."""
        custom_dir = tmp_path / "custom_errata"
        _create_errata_files(custom_dir, ["93_ts93_4_placement.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_errata(errata_dir=custom_dir)

        assert result.facts_added == 1


class TestIngestErrataDeduplication:
    """AC-4, AC-5: Errata deduplication via _is_already_ingested.

    Issue: #332
    """

    def test_skips_already_ingested_errata(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-4: Verify second call skips already-ingested errata."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(errata_dir, ["93_ts93_4_placement.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)

        first_result = ingestor.ingest_errata(errata_dir=errata_dir)
        assert first_result.facts_added == 1
        assert first_result.facts_skipped == 0

        second_result = ingestor.ingest_errata(errata_dir=errata_dir)
        assert second_result.facts_added == 0
        assert second_result.facts_skipped == 1

        count = schema_conn.execute("SELECT COUNT(*) FROM memory_facts WHERE category = 'errata'").fetchone()
        assert count is not None
        assert count[0] == 1

    def test_is_already_ingested_errata_true(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-5: _is_already_ingested returns True for existing errata spec_name."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(errata_dir, ["93_ts93_4_placement.md"])

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        ingestor.ingest_errata(errata_dir=errata_dir)

        assert ingestor._is_already_ingested(category="errata", identifier="93_ts93_4_placement.md")

    def test_is_already_ingested_errata_false(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-5: _is_already_ingested returns False for nonexistent errata spec_name."""
        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)

        assert not ingestor._is_already_ingested(category="errata", identifier="nonexistent.md")


class TestIngestErrataMissingDirectory:
    """AC-6: Ingest errata with missing directory returns zero facts gracefully.

    Issue: #332
    """

    def test_returns_zero_facts_when_dir_missing(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-6: Verify returns IngestResult with 0 facts when errata dir missing."""
        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_errata()

        assert result.source_type == "errata"
        assert result.facts_added == 0
        assert result.facts_skipped == 0
        assert result.embedding_failures == 0

    def test_no_exception_raised_when_dir_missing(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-6: Verify no exception raised when errata directory is absent."""
        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        result = ingestor.ingest_errata()
        assert isinstance(result, IngestResult)


class TestRunBackgroundIngestionErrata:
    """AC-8, AC-9: run_background_ingestion includes errata ingestion.

    Issue: #332
    """

    def test_ingests_errata_alongside_adrs_and_git(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-8: Verify run_background_ingestion ingests errata facts."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(errata_dir, ["93_ts93_4_placement.md"])

        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = ""

        from agent_fox.core.config import KnowledgeConfig

        config = KnowledgeConfig(store_path=str(tmp_path / "knowledge.duckdb"))

        with (
            patch("agent_fox.knowledge.ingest.EmbeddingGenerator", return_value=mock_embedder),
            patch("agent_fox.knowledge.ingest.subprocess.run", return_value=mock_git_result),
        ):
            run_background_ingestion(schema_conn, config, tmp_path)

        count = schema_conn.execute("SELECT COUNT(*) FROM memory_facts WHERE category = 'errata'").fetchone()
        assert count is not None
        assert count[0] >= 1

    def test_emits_audit_event_for_errata(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """AC-9: Verify knowledge.ingested audit event emitted for errata."""
        errata_dir = tmp_path / "docs" / "errata"
        _create_errata_files(errata_dir, ["93_ts93_4_placement.md"])

        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = ""

        mock_sink = MagicMock()

        from agent_fox.core.config import KnowledgeConfig

        config = KnowledgeConfig(store_path=str(tmp_path / "knowledge.duckdb"))

        with (
            patch("agent_fox.knowledge.ingest.EmbeddingGenerator", return_value=mock_embedder),
            patch("agent_fox.knowledge.ingest.subprocess.run", return_value=mock_git_result),
            patch("agent_fox.knowledge.ingest._emit_knowledge_ingested") as mock_emit,
        ):
            run_background_ingestion(schema_conn, config, tmp_path, sink_dispatcher=mock_sink, run_id="test-run-1")

        # Check that _emit_knowledge_ingested was called with source_type='errata'
        errata_calls = [c for c in mock_emit.call_args_list if c.kwargs.get("source_type") == "errata"]
        assert len(errata_calls) == 1
        assert errata_calls[0].kwargs["item_count"] == 1
        assert "errata" in errata_calls[0].kwargs["source_path"]


class TestIngestResultSourceType:
    """AC-10: IngestResult.source_type documents 'errata' as a valid value.

    Issue: #332
    """

    def test_source_type_comment_includes_errata(self) -> None:
        """AC-10: Verify IngestResult.source_type comment includes 'errata'."""
        import inspect

        import agent_fox.knowledge.ingest as ingest_module

        source = inspect.getsource(ingest_module.IngestResult)
        assert "errata" in source
