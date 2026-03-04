"""Tests for the CLI ask command.

Test Spec: TS-12-14 (renders answer), TS-12-E1 (empty store),
           TS-12-E2 (unavailable store)
Requirements: 12-REQ-5.1, 12-REQ-5.E1, 12-REQ-5.E2
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from agent_fox.cli.app import main
from agent_fox.knowledge.oracle import OracleAnswer
from agent_fox.knowledge.search import SearchResult


def _make_oracle_answer(
    *,
    answer: str = "DuckDB was chosen for columnar analytics.",
    confidence: str = "high",
    contradictions: list[str] | None = None,
) -> OracleAnswer:
    """Create a mock OracleAnswer."""
    return OracleAnswer(
        answer=answer,
        sources=[
            SearchResult(
                fact_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                content="DuckDB was chosen for columnar analytics",
                category="decision",
                spec_name="11_duckdb",
                session_id="11/1",
                commit_sha="a1b2c3d",
                similarity=0.85,
            ),
        ],
        contradictions=contradictions,
        confidence=confidence,
    )


class TestAskCommandRendersAnswer:
    """TS-12-14: Ask command renders answer.

    Requirement: 12-REQ-5.1
    """

    def test_renders_answer_text(self) -> None:
        """Verify ask command prints the answer text."""
        runner = CliRunner()
        mock_answer = _make_oracle_answer()

        with (
            patch("agent_fox.cli.ask.Oracle") as MockOracle,
            patch("agent_fox.cli.ask.open_knowledge_store") as mock_open,
            patch("agent_fox.cli.ask.EmbeddingGenerator"),
            patch("agent_fox.cli.ask.VectorSearch") as MockSearch,
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_open.return_value = mock_db
            mock_has = MagicMock(return_value=True)
            MockSearch.return_value = MagicMock(
                has_embeddings=mock_has,
            )
            MockOracle.return_value.ask.return_value = mock_answer

            result = runner.invoke(main, ["ask", "why did we choose DuckDB?"])

        assert result.exit_code == 0
        assert "DuckDB was chosen" in result.output

    def test_renders_confidence(self) -> None:
        """Verify ask command shows confidence indicator."""
        runner = CliRunner()
        mock_answer = _make_oracle_answer(confidence="high")

        with (
            patch("agent_fox.cli.ask.Oracle") as MockOracle,
            patch("agent_fox.cli.ask.open_knowledge_store") as mock_open,
            patch("agent_fox.cli.ask.EmbeddingGenerator"),
            patch("agent_fox.cli.ask.VectorSearch") as MockSearch,
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_open.return_value = mock_db
            mock_has = MagicMock(return_value=True)
            MockSearch.return_value = MagicMock(
                has_embeddings=mock_has,
            )
            MockOracle.return_value.ask.return_value = mock_answer

            result = runner.invoke(main, ["ask", "why did we choose DuckDB?"])

        assert result.exit_code == 0
        assert "high" in result.output.lower() or "confidence" in result.output.lower()


class TestAskCommandEmptyStore:
    """TS-12-E1: Ask with empty knowledge store.

    Requirement: 12-REQ-5.E1
    """

    def test_empty_store_message(self) -> None:
        """Verify informational message for empty knowledge store."""
        runner = CliRunner()

        with (
            patch("agent_fox.cli.ask.open_knowledge_store") as mock_open,
            patch("agent_fox.cli.ask.EmbeddingGenerator"),
            patch("agent_fox.cli.ask.VectorSearch") as MockSearch,
        ):
            mock_db = MagicMock()
            mock_db.connection = MagicMock()
            mock_open.return_value = mock_db
            MockSearch.return_value = MagicMock(
                has_embeddings=MagicMock(return_value=False)
            )

            result = runner.invoke(main, ["ask", "any question"])

        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no knowledge" in output_lower or "accumulated" in output_lower


class TestAskCommandUnavailableStore:
    """TS-12-E2: Ask with unavailable knowledge store.

    Requirement: 12-REQ-5.E2
    """

    def test_unavailable_store_error(self) -> None:
        """Verify error message when knowledge store is unavailable."""
        runner = CliRunner()

        with patch("agent_fox.cli.ask.open_knowledge_store") as mock_open:
            mock_open.return_value = None

            result = runner.invoke(main, ["ask", "any question"])

        assert result.exit_code == 1
        output_lower = result.output.lower()
        assert "unavailable" in output_lower or "knowledge store" in output_lower
