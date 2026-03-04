"""Tests for the CLI ingest command.

Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.knowledge.ingest import IngestResult


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


class TestIngestCommandRegistered:
    """Verify ingest command is accessible via CLI."""

    def test_ingest_help(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "Ingest" in result.output


class TestIngestNoKnowledgeStore:
    """Verify ingest exits cleanly when KB is unavailable."""

    def test_unavailable_store(self, cli_runner: CliRunner) -> None:
        with patch(
            "agent_fox.cli.ingest.open_knowledge_store",
            return_value=None,
        ):
            result = cli_runner.invoke(main, ["ingest"])
        assert result.exit_code != 0
        assert "unavailable" in result.output.lower()


class TestIngestBothSources:
    """Verify ingest runs both ADRs and git commits by default."""

    def test_ingests_both(self, cli_runner: CliRunner) -> None:
        mock_db = MagicMock()
        mock_ingestor = MagicMock()
        mock_ingestor.ingest_adrs.return_value = IngestResult(
            source_type="adr",
            facts_added=3,
            facts_skipped=1,
            embedding_failures=0,
        )
        mock_ingestor.ingest_git_commits.return_value = IngestResult(
            source_type="git",
            facts_added=10,
            facts_skipped=5,
            embedding_failures=0,
        )

        with (
            patch(
                "agent_fox.cli.ingest.open_knowledge_store",
                return_value=mock_db,
            ),
            patch(
                "agent_fox.cli.ingest.EmbeddingGenerator",
            ),
            patch(
                "agent_fox.cli.ingest.KnowledgeIngestor",
                return_value=mock_ingestor,
            ),
        ):
            result = cli_runner.invoke(main, ["ingest"])

        assert result.exit_code == 0
        assert "3 added" in result.output
        assert "10 added" in result.output
        mock_ingestor.ingest_adrs.assert_called_once()
        mock_ingestor.ingest_git_commits.assert_called_once()
        mock_db.close.assert_called_once()


class TestIngestSkipAdrs:
    """Verify --no-adrs skips ADR ingestion."""

    def test_no_adrs(self, cli_runner: CliRunner) -> None:
        mock_db = MagicMock()
        mock_ingestor = MagicMock()
        mock_ingestor.ingest_git_commits.return_value = IngestResult(
            source_type="git",
            facts_added=5,
            facts_skipped=0,
            embedding_failures=0,
        )

        with (
            patch(
                "agent_fox.cli.ingest.open_knowledge_store",
                return_value=mock_db,
            ),
            patch("agent_fox.cli.ingest.EmbeddingGenerator"),
            patch(
                "agent_fox.cli.ingest.KnowledgeIngestor",
                return_value=mock_ingestor,
            ),
        ):
            result = cli_runner.invoke(main, ["ingest", "--no-adrs"])

        assert result.exit_code == 0
        mock_ingestor.ingest_adrs.assert_not_called()
        mock_ingestor.ingest_git_commits.assert_called_once()
