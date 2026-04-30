"""Analyzer tests.

Test Spec: TS-31-6 through TS-31-13, TS-31-29, TS-31-30
Requirements: 31-REQ-3.2, 31-REQ-3.3, 31-REQ-3.4, 31-REQ-3.5,
              31-REQ-3.E1, 31-REQ-4.1, 31-REQ-4.2, 31-REQ-4.3, 31-REQ-4.E1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.analyzer import (
    build_analyzer_prompt,
    filter_improvements,
    parse_analyzer_response,
)

from .conftest import make_improvement


class TestBuildAnalyzerPrompt:
    """TS-31-6, TS-31-7, TS-31-8: Analyzer prompt building."""

    def test_prompt_includes_conventions(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-6: Prompt includes content from CLAUDE.md."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("Use ruff for formatting")

        system_prompt, task_prompt = build_analyzer_prompt(tmp_path, mock_config)

        assert "ruff" in system_prompt
        assert "formatting" in system_prompt

    def test_prompt_includes_oracle_context(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-7: Oracle context is included in the prompt."""
        system_prompt, _ = build_analyzer_prompt(
            tmp_path,
            mock_config,
            oracle_context="ADR-001: Use dataclasses for models",
        )

        assert "## Project Knowledge" in system_prompt
        assert "ADR-001" in system_prompt

    def test_prompt_omits_oracle_when_unavailable(self, tmp_path: Path, mock_config: AgentFoxConfig) -> None:
        """TS-31-8: Prompt works without oracle context."""
        system_prompt, _ = build_analyzer_prompt(tmp_path, mock_config, oracle_context="")

        assert "## Project Knowledge" not in system_prompt


class TestParseAnalyzerResponse:
    """TS-31-9, TS-31-10, TS-31-11: Analyzer response parsing."""

    def test_parse_valid_json(self, valid_analyzer_json: str) -> None:
        """TS-31-9: Valid JSON is parsed correctly."""
        result = parse_analyzer_response(valid_analyzer_json)

        assert len(result.improvements) == 2
        assert result.improvements[0].tier == "quick_win"
        assert result.improvements[1].confidence == 0.6
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
        high_imp = make_improvement(id="H1", confidence=0.9)
        medium_imp = make_improvement(id="M1", confidence=0.6)
        low_imp = make_improvement(id="L1", confidence=0.3)

        filtered = filter_improvements([high_imp, medium_imp, low_imp])

        assert len(filtered) == 2
        assert all(i.confidence >= 0.5 for i in filtered)

    def test_filter_sorts_by_tier_priority(self) -> None:
        """TS-31-13: Filtered improvements sorted by tier priority."""
        design_imp = make_improvement(id="D1", tier="design_level", confidence=0.9)
        quick_imp = make_improvement(id="Q1", tier="quick_win", confidence=0.9)
        structural_imp = make_improvement(id="S1", tier="structural", confidence=0.9)

        filtered = filter_improvements([design_imp, quick_imp, structural_imp])

        assert filtered[0].tier == "quick_win"
        assert filtered[1].tier == "structural"
        assert filtered[2].tier == "design_level"


# ---------------------------------------------------------------------------
# Symlink rejection in _load_conventions (issue #586, CWE-59)
# ---------------------------------------------------------------------------


class TestLoadConventionsSymlinkRejection:
    """AC-3, AC-4, AC-5: _load_conventions() rejects symlinks."""

    def test_symlinked_claude_md_is_skipped(self, tmp_path: Path) -> None:
        """AC-3: _load_conventions() skips CLAUDE.md when it is a symlink.

        The function must not return content from a symlink target.
        """
        from agent_fox.fix.analyzer import _load_conventions

        external = tmp_path / "external.md"
        external.write_text("INJECTED_SECRET")

        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "CLAUDE.md").symlink_to(external)

        result = _load_conventions(project_root)

        assert "INJECTED_SECRET" not in result

    def test_symlink_skipped_falls_through_to_next_candidate(self, tmp_path: Path) -> None:
        """AC-4: When first convention file is a symlink, the search continues.

        CLAUDE.md is a symlink (skipped); AGENTS.md is a real file and must be
        returned.
        """
        from agent_fox.fix.analyzer import _load_conventions

        external = tmp_path / "external.md"
        external.write_text("SHOULD_NOT_APPEAR")

        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "CLAUDE.md").symlink_to(external)
        (project_root / "AGENTS.md").write_text("real-conventions")

        result = _load_conventions(project_root)

        assert "real-conventions" in result
        assert "SHOULD_NOT_APPEAR" not in result

    def test_regular_claude_md_loads_correctly(self, tmp_path: Path) -> None:
        """AC-5 (conventions): Non-symlinked CLAUDE.md loads correctly after the fix."""
        from agent_fox.fix.analyzer import _load_conventions

        (tmp_path / "CLAUDE.md").write_text("project-conventions")

        result = _load_conventions(tmp_path)

        assert "project-conventions" in result
