"""Analyzer tests.

Test Spec: TS-31-6 through TS-31-13, TS-31-29, TS-31-30
Requirements: 31-REQ-3.2, 31-REQ-3.3, 31-REQ-3.4, 31-REQ-3.5,
              31-REQ-3.E1, 31-REQ-4.1, 31-REQ-4.2, 31-REQ-4.3, 31-REQ-4.E1
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.analyzer import (
    build_analyzer_prompt,
    filter_improvements,
    parse_analyzer_response,
    query_oracle_context,
)

from .conftest import make_improvement


class TestBuildAnalyzerPrompt:
    """TS-31-6, TS-31-7, TS-31-8: Analyzer prompt building."""

    def test_prompt_includes_conventions(
        self, tmp_path: Path, mock_config: AgentFoxConfig
    ) -> None:
        """TS-31-6: Prompt includes content from CLAUDE.md."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("Use ruff for formatting")

        system_prompt, task_prompt = build_analyzer_prompt(
            tmp_path, mock_config
        )

        assert "ruff" in system_prompt
        assert "formatting" in system_prompt

    def test_prompt_includes_oracle_context(
        self, tmp_path: Path, mock_config: AgentFoxConfig
    ) -> None:
        """TS-31-7: Oracle context is included in the prompt."""
        system_prompt, _ = build_analyzer_prompt(
            tmp_path,
            mock_config,
            oracle_context="ADR-001: Use dataclasses for models",
        )

        assert "## Project Knowledge" in system_prompt
        assert "ADR-001" in system_prompt

    def test_prompt_omits_oracle_when_unavailable(
        self, tmp_path: Path, mock_config: AgentFoxConfig
    ) -> None:
        """TS-31-8: Prompt works without oracle context."""
        system_prompt, _ = build_analyzer_prompt(
            tmp_path, mock_config, oracle_context=""
        )

        assert "## Project Knowledge" not in system_prompt


class TestParseAnalyzerResponse:
    """TS-31-9, TS-31-10, TS-31-11: Analyzer response parsing."""

    def test_parse_valid_json(self, valid_analyzer_json: str) -> None:
        """TS-31-9: Valid JSON is parsed correctly."""
        result = parse_analyzer_response(valid_analyzer_json)

        assert len(result.improvements) == 2
        assert result.improvements[0].tier == "quick_win"
        assert result.improvements[1].confidence == "medium"
        assert result.diminishing_returns is False

    def test_parse_invalid_json(self) -> None:
        """TS-31-10: Invalid JSON raises ValueError."""
        with pytest.raises(ValueError):
            parse_analyzer_response("This is not JSON")

    def test_parse_missing_required_fields(self) -> None:
        """TS-31-11: Missing required fields raise ValueError."""
        with pytest.raises(ValueError):
            parse_analyzer_response('{"improvements": []}')


class TestFilterImprovements:
    """TS-31-12, TS-31-13: Improvement filtering."""

    def test_filter_excludes_low_confidence(self) -> None:
        """TS-31-12: Low-confidence improvements are filtered out."""
        high_imp = make_improvement(id="H1", confidence="high")
        medium_imp = make_improvement(id="M1", confidence="medium")
        low_imp = make_improvement(id="L1", confidence="low")

        filtered = filter_improvements([high_imp, medium_imp, low_imp])

        assert len(filtered) == 2
        assert all(i.confidence in ("high", "medium") for i in filtered)

    def test_filter_sorts_by_tier_priority(self) -> None:
        """TS-31-13: Filtered improvements sorted by tier priority."""
        design_imp = make_improvement(
            id="D1", tier="design_level", confidence="high"
        )
        quick_imp = make_improvement(
            id="Q1", tier="quick_win", confidence="high"
        )
        structural_imp = make_improvement(
            id="S1", tier="structural", confidence="high"
        )

        filtered = filter_improvements(
            [design_imp, quick_imp, structural_imp]
        )

        assert filtered[0].tier == "quick_win"
        assert filtered[1].tier == "structural"
        assert filtered[2].tier == "design_level"


class TestQueryOracleContext:
    """TS-31-29, TS-31-30: Oracle context queries."""

    def test_oracle_returns_formatted_facts(
        self, mock_config: AgentFoxConfig
    ) -> None:
        """TS-31-29: Oracle returns formatted context with provenance."""
        mock_result = MagicMock()
        mock_result.content = "Use dataclasses for models"
        mock_result.metadata = {"spec": "01"}

        with patch(
            "agent_fox.fix.analyzer._query_oracle_facts",
            return_value=[mock_result],
        ):
            context = query_oracle_context(mock_config)

        assert len(context) > 0
        assert "dataclasses" in context

    def test_oracle_propagates_error_when_unavailable(
        self, mock_config: AgentFoxConfig
    ) -> None:
        """TS-31-30 (superseded by 38-REQ-3.1): Oracle errors propagate."""
        with patch(
            "agent_fox.fix.analyzer._query_oracle_facts",
            side_effect=Exception("Knowledge store unavailable"),
        ):
            with pytest.raises(Exception, match="Knowledge store unavailable"):
                query_oracle_context(mock_config)
