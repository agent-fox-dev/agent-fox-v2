"""Tests for knowledge source ingestion.

Test Spec: TS-12-15 (ADR ingestion), TS-12-16 (git commit ingestion),
           TS-12-E4 (missing ADR directory)
Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb

from agent_fox.knowledge.ingest import IngestResult, KnowledgeIngestor


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

        rows = schema_conn.execute(
            "SELECT * FROM memory_facts WHERE category = 'adr'"
        ).fetchall()
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

        emb_count = schema_conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings"
        ).fetchone()
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

    def test_creates_git_facts(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify ingesting git commits creates facts with category='git'."""
        mock_git_result = _mock_git_log_output(
            [
                ("abc1234", "2025-11-01T10:00:00", "feat: add user authentication"),
                ("def5678", "2025-11-02T11:00:00", "fix: correct password hashing"),
                ("ghi9012", "2025-11-03T12:00:00", "refactor: clean up auth module"),
            ]
        )

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        with patch(
            "agent_fox.knowledge.ingest.subprocess.run",
            return_value=mock_git_result,
        ):
            result = ingestor.ingest_git_commits(limit=10)

        assert result.facts_added == 3
        assert result.source_type == "git"

    def test_git_facts_have_commit_sha(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify each git fact has commit_sha populated."""
        mock_git_result = _mock_git_log_output(
            [
                ("abc1234", "2025-11-01T10:00:00", "feat: add feature"),
                ("def5678", "2025-11-02T11:00:00", "fix: fix bug"),
                ("ghi9012", "2025-11-03T12:00:00", "refactor: cleanup"),
            ]
        )

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        with patch(
            "agent_fox.knowledge.ingest.subprocess.run",
            return_value=mock_git_result,
        ):
            ingestor.ingest_git_commits(limit=10)

        rows = schema_conn.execute(
            "SELECT commit_sha FROM memory_facts WHERE category = 'git'"
        ).fetchall()
        assert len(rows) == 3
        assert all(row[0] is not None for row in rows)

    def test_git_facts_have_category(
        self,
        tmp_path: Path,
        schema_conn: duckdb.DuckDBPyConnection,
        mock_embedder: MagicMock,
    ) -> None:
        """Verify git facts have category='git'."""
        mock_git_result = _mock_git_log_output(
            [
                ("abc1234", "2025-11-01T10:00:00", "feat: add feature"),
            ]
        )

        ingestor = KnowledgeIngestor(schema_conn, mock_embedder, tmp_path)
        with patch(
            "agent_fox.knowledge.ingest.subprocess.run",
            return_value=mock_git_result,
        ):
            ingestor.ingest_git_commits(limit=10)

        rows = schema_conn.execute(
            "SELECT category FROM memory_facts WHERE category = 'git'"
        ).fetchall()
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
