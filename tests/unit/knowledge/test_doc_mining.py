"""Tests for agent_fox.knowledge.doc_mining — Spec 101.

Tests: TS-101-25, TS-101-26, TS-101-28, TS-101-29,
       TS-101-E10, TS-101-E11, TS-101-E12
Requirements: 101-REQ-6.1, 101-REQ-6.2, 101-REQ-6.4, 101-REQ-6.6,
              101-REQ-6.E1, 101-REQ-6.E2, 101-REQ-6.E3
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import duckdb
import pytest
from agent_fox.knowledge.doc_mining import (
    DocMiningResult,
    _collect_doc_files,
    mine_docs_with_llm,
)

from agent_fox.knowledge.store import load_facts_by_spec

_SAMPLE_LLM_RESPONSE = json.dumps(
    [
        {
            "content": "All PRs require two approvals before merge",
            "category": "convention",
            "confidence": "high",
            "keywords": ["PR", "review", "approval"],
        }
    ]
)


def _make_project(tmp_path: Path) -> None:
    """Create a minimal project structure with docs."""
    (tmp_path / "README.md").write_text("# Project\n\nThis is the README.")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nDeveloper guide.")
    adr = docs / "adr"
    adr.mkdir()
    (adr / "01-use-duckdb.md").write_text("# ADR 01: Use DuckDB")
    errata = docs / "errata"
    errata.mkdir()
    (errata / "e1.md").write_text("# Erratum 1")


class TestDocMiningResultFields:
    """TS-101-28: DocMiningResult has required fields with correct defaults.

    Requirement: 101-REQ-6.4
    """

    def test_all_count_fields_default_to_zero(self) -> None:
        """Verify all count fields default to zero."""
        r = DocMiningResult()
        assert r.facts_created == 0
        assert r.docs_analyzed == 0
        assert r.docs_skipped == 0

    def test_is_frozen_dataclass(self) -> None:
        """Verify DocMiningResult is immutable (frozen=True)."""
        r = DocMiningResult()
        with pytest.raises((AttributeError, TypeError)):
            r.facts_created = 1  # type: ignore[misc]


class TestCollectDocFiles:
    """TS-101-26: _collect_doc_files finds correct files and excludes ADR/errata.

    Requirement: 101-REQ-6.2
    """

    def test_finds_readme_at_root(self, tmp_path: Path) -> None:
        """Verify README.md at project root is included."""
        _make_project(tmp_path)
        files = _collect_doc_files(tmp_path)
        names = [f.name for f in files]
        assert "README.md" in names

    def test_finds_docs_subdirectory_markdown(self, tmp_path: Path) -> None:
        """Verify *.md files under docs/ (non-excluded) are included."""
        _make_project(tmp_path)
        files = _collect_doc_files(tmp_path)
        names = [f.name for f in files]
        assert "guide.md" in names

    def test_excludes_adr_directory(self, tmp_path: Path) -> None:
        """Verify docs/adr/ files are excluded."""
        _make_project(tmp_path)
        files = _collect_doc_files(tmp_path)
        names = [f.name for f in files]
        assert "01-use-duckdb.md" not in names

    def test_excludes_errata_directory(self, tmp_path: Path) -> None:
        """Verify docs/errata/ files are excluded."""
        _make_project(tmp_path)
        files = _collect_doc_files(tmp_path)
        names = [f.name for f in files]
        assert "e1.md" not in names

    def test_finds_contributing_md(self, tmp_path: Path) -> None:
        """Verify CONTRIBUTING.md at root is included."""
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing")
        files = _collect_doc_files(tmp_path)
        names = [f.name for f in files]
        assert "CONTRIBUTING.md" in names

    def test_finds_changelog_md(self, tmp_path: Path) -> None:
        """Verify CHANGELOG.md at root is included."""
        (tmp_path / "CHANGELOG.md").write_text("# Changelog")
        files = _collect_doc_files(tmp_path)
        names = [f.name for f in files]
        assert "CHANGELOG.md" in names

    def test_empty_project_returns_empty_list(self, tmp_path: Path) -> None:
        """Verify project with no markdown files returns empty list."""
        files = _collect_doc_files(tmp_path)
        assert files == []


class TestMineDocsWithLLM:
    """TS-101-25: mine_docs_with_llm creates facts from LLM output.

    Requirement: 101-REQ-6.1, 101-REQ-6.6
    """

    @pytest.mark.asyncio
    async def test_creates_facts_from_llm_response(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-25: Verify facts created and stored with fingerprint keywords."""
        (tmp_path / "README.md").write_text("# Project\n\nAll PRs need two reviews.")

        with patch(
            "agent_fox.knowledge.doc_mining.ai_call",
            new_callable=AsyncMock,
            return_value=(_SAMPLE_LLM_RESPONSE, None),
        ), patch(
            "agent_fox.knowledge.doc_mining._is_mining_fact_exists",
            return_value=False,
        ):
            result = await mine_docs_with_llm(tmp_path, knowledge_conn, model="STANDARD")

        assert result.facts_created >= 1
        assert result.docs_analyzed == 1
        facts = load_facts_by_spec("onboard", knowledge_conn)
        assert any("onboard:doc:" in kw for f in facts for kw in f.keywords)

    @pytest.mark.asyncio
    async def test_dedup_skips_previously_mined_docs(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-29: Documents with existing fingerprint keyword are skipped.

        Requirement: 101-REQ-6.6
        """
        (tmp_path / "README.md").write_text("# Project")

        with patch(
            "agent_fox.knowledge.doc_mining._is_mining_fact_exists",
            return_value=True,
        ):
            result = await mine_docs_with_llm(tmp_path, knowledge_conn)

        assert result.docs_skipped >= 1


class TestDocMiningEdgeCases:
    """TS-101-E10, TS-101-E11, TS-101-E12: Edge cases for doc mining.

    Requirements: 101-REQ-6.E1, 101-REQ-6.E2, 101-REQ-6.E3
    """

    @pytest.mark.asyncio
    async def test_llm_failure_per_doc_continues_to_next(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-E10: LLM failure for one doc doesn't block processing others."""
        (tmp_path / "README.md").write_text("# README")
        (tmp_path / "CONTRIBUTING.md").write_text("# CONTRIBUTING")

        valid_response = json.dumps(
            [{"content": "A convention", "category": "convention", "confidence": "high", "keywords": ["x"]}]
        )

        call_count = 0

        async def _side_effect(**kwargs: object) -> tuple[str, None]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM error")
            return (valid_response, None)

        with patch(
            "agent_fox.knowledge.doc_mining.ai_call",
            side_effect=_side_effect,
        ), patch(
            "agent_fox.knowledge.doc_mining._is_mining_fact_exists",
            return_value=False,
        ):
            result = await mine_docs_with_llm(tmp_path, knowledge_conn)

        assert result.docs_skipped == 1
        assert result.docs_analyzed == 1

    @pytest.mark.asyncio
    async def test_no_documentation_files_found(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-E11: Phase skips gracefully when no docs found."""
        # tmp_path has no markdown files
        result = await mine_docs_with_llm(tmp_path, knowledge_conn)

        assert result.docs_analyzed == 0
        assert result.docs_skipped == 0
        assert result.facts_created == 0

    @pytest.mark.asyncio
    async def test_unparseable_llm_response_skips_doc(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-E12: Unparseable LLM response increments docs_skipped."""
        (tmp_path / "README.md").write_text("# Project")

        with patch(
            "agent_fox.knowledge.doc_mining.ai_call",
            new_callable=AsyncMock,
            return_value=("not valid json {{{", None),
        ), patch(
            "agent_fox.knowledge.doc_mining._is_mining_fact_exists",
            return_value=False,
        ):
            result = await mine_docs_with_llm(tmp_path, knowledge_conn)

        assert result.docs_skipped >= 1
        assert result.facts_created == 0
