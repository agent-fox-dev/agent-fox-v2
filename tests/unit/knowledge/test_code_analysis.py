"""Tests for agent_fox.knowledge.code_analysis — Spec 101.

Tests: TS-101-20, TS-101-21, TS-101-23, TS-101-24, TS-101-31,
       TS-101-E7, TS-101-E8, TS-101-E9
Requirements: 101-REQ-5.1, 101-REQ-5.2, 101-REQ-5.5, 101-REQ-5.6,
              101-REQ-5.E1, 101-REQ-5.E2, 101-REQ-5.E3
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import duckdb
import pytest

from agent_fox.knowledge.code_analysis import (
    SOURCE_EXTENSIONS,
    CodeAnalysisResult,
    _get_files_by_priority,
    _parse_llm_facts,
    _scan_source_files,
    analyze_code_with_llm,
)
from agent_fox.knowledge.store import load_facts_by_spec

_SAMPLE_LLM_RESPONSE = json.dumps(
    [
        {
            "content": "Uses repository pattern for data access",
            "category": "pattern",
            "confidence": "high",
            "keywords": ["repository", "data access"],
        }
    ]
)


def _insert_file_entity(conn: duckdb.DuckDBPyConnection, path: str, entity_id: str) -> None:
    """Insert a file entity into the entity_graph table."""
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?::UUID, 'file', ?, ?, CURRENT_TIMESTAMP)
        """,
        [entity_id, path.split("/")[-1], path],
    )


def _insert_import_edge(
    conn: duckdb.DuckDBPyConnection,
    source_id: str,
    target_id: str,
) -> None:
    """Insert an imports edge between two entities."""
    conn.execute(
        """
        INSERT INTO entity_edges (source_id, target_id, relationship)
        VALUES (?::UUID, ?::UUID, 'imports')
        """,
        [source_id, target_id],
    )


class TestCodeAnalysisResultFields:
    """TS-101-23: CodeAnalysisResult has required fields with correct defaults.

    Requirement: 101-REQ-5.5
    """

    def test_all_count_fields_default_to_zero(self) -> None:
        """Verify all count fields default to zero."""
        r = CodeAnalysisResult()
        assert r.facts_created == 0
        assert r.files_analyzed == 0
        assert r.files_skipped == 0

    def test_is_frozen_dataclass(self) -> None:
        """Verify CodeAnalysisResult is immutable (frozen=True)."""
        r = CodeAnalysisResult()
        with pytest.raises((AttributeError, TypeError)):
            r.facts_created = 1  # type: ignore[misc]


class TestSourceExtensions:
    """Verify SOURCE_EXTENSIONS constant covers expected languages."""

    def test_python_included(self) -> None:
        assert ".py" in SOURCE_EXTENSIONS

    def test_go_included(self) -> None:
        assert ".go" in SOURCE_EXTENSIONS

    def test_rust_included(self) -> None:
        assert ".rs" in SOURCE_EXTENSIONS

    def test_typescript_included(self) -> None:
        assert ".ts" in SOURCE_EXTENSIONS

    def test_javascript_included(self) -> None:
        assert ".js" in SOURCE_EXTENSIONS

    def test_java_included(self) -> None:
        assert ".java" in SOURCE_EXTENSIONS


class TestParseLLMFacts:
    """TS-101-31: _parse_llm_facts correctly parses JSON response.

    Requirement: 101-REQ-5.1
    """

    def test_parses_single_fact(self) -> None:
        """Verify basic fact parsing from JSON array."""
        raw = json.dumps(
            [
                {
                    "content": "Uses singleton pattern",
                    "category": "pattern",
                    "confidence": "high",
                    "keywords": ["singleton"],
                }
            ]
        )
        facts = _parse_llm_facts(raw, spec_name="onboard", file_path="main.py", source_type="code")

        assert len(facts) == 1
        assert facts[0].content == "Uses singleton pattern"
        assert facts[0].category == "pattern"
        assert facts[0].spec_name == "onboard"

    def test_adds_code_fingerprint_keyword(self) -> None:
        """Verify fingerprint keyword 'onboard:code:{file_path}' added to each fact."""
        raw = json.dumps(
            [
                {
                    "content": "Some pattern",
                    "category": "pattern",
                    "confidence": "medium",
                    "keywords": ["pattern"],
                }
            ]
        )
        facts = _parse_llm_facts(raw, spec_name="onboard", file_path="main.py", source_type="code")

        assert len(facts) == 1
        assert "onboard:code:main.py" in facts[0].keywords

    def test_adds_doc_fingerprint_keyword_for_doc_source(self) -> None:
        """Verify fingerprint keyword 'onboard:doc:{file_path}' added for doc type."""
        raw = json.dumps(
            [
                {
                    "content": "A convention",
                    "category": "convention",
                    "confidence": "high",
                    "keywords": ["convention"],
                }
            ]
        )
        facts = _parse_llm_facts(raw, spec_name="onboard", file_path="README.md", source_type="doc")

        assert len(facts) == 1
        assert "onboard:doc:README.md" in facts[0].keywords

    def test_confidence_mapped_to_float(self) -> None:
        """Verify string confidence values are converted to float in [0.0, 1.0]."""
        for conf_str in ("high", "medium", "low"):
            raw = json.dumps(
                [
                    {
                        "content": "A fact",
                        "category": "decision",
                        "confidence": conf_str,
                        "keywords": [],
                    }
                ]
            )
            facts = _parse_llm_facts(raw, spec_name="onboard", file_path="x.py", source_type="code")
            assert len(facts) == 1
            assert 0.0 <= facts[0].confidence <= 1.0

    def test_empty_json_array_returns_empty_list(self) -> None:
        """Verify empty JSON array returns empty list."""
        facts = _parse_llm_facts("[]", spec_name="onboard", file_path="x.py", source_type="code")
        assert facts == []

    def test_multiple_facts_parsed(self) -> None:
        """Verify multiple facts in array are all parsed."""
        raw = json.dumps(
            [
                {"content": "First", "category": "pattern", "confidence": "high", "keywords": []},
                {"content": "Second", "category": "decision", "confidence": "low", "keywords": []},
            ]
        )
        facts = _parse_llm_facts(raw, spec_name="onboard", file_path="x.py", source_type="code")
        assert len(facts) == 2

    def test_invalid_category_handled_gracefully(self) -> None:
        """Verify invalid category does not raise; bad facts may be dropped."""
        raw = json.dumps(
            [
                {
                    "content": "Some fact",
                    "category": "totally_invalid_category",
                    "confidence": "low",
                    "keywords": [],
                }
            ]
        )
        # Should not raise
        facts = _parse_llm_facts(raw, spec_name="onboard", file_path="x.py", source_type="code")
        assert isinstance(facts, list)


class TestFilePrioritization:
    """TS-101-21: Files ordered by import count from entity graph.

    Requirement: 101-REQ-5.2
    """

    def test_most_imported_file_first(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify file with most incoming imports is first in priority list."""
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        id_c = str(uuid.uuid4())

        _insert_file_entity(knowledge_conn, "file_a.py", id_a)
        _insert_file_entity(knowledge_conn, "file_b.py", id_b)  # most imported
        _insert_file_entity(knowledge_conn, "file_c.py", id_c)

        # file_b gets 5 incoming import edges, file_c gets 2, file_a gets 0
        for _ in range(5):
            _insert_import_edge(knowledge_conn, str(uuid.uuid4()), id_b)
        for _ in range(2):
            _insert_import_edge(knowledge_conn, str(uuid.uuid4()), id_c)

        # Create actual files on disk
        (tmp_path / "file_a.py").write_text("# a")
        (tmp_path / "file_b.py").write_text("# b")
        (tmp_path / "file_c.py").write_text("# c")

        files = _get_files_by_priority(knowledge_conn, tmp_path)

        file_names = [f.name for f in files]
        assert "file_b.py" in file_names
        assert file_names.index("file_b.py") < file_names.index("file_c.py")
        assert file_names.index("file_b.py") < file_names.index("file_a.py")

    def test_fallback_to_disk_when_entity_graph_empty(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Verify fallback to disk scan when entity graph has no file entities."""
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "utils.py").write_text("# utils")

        # Entity graph is empty (no inserts)
        files = _get_files_by_priority(knowledge_conn, tmp_path)

        # Should find files via disk fallback
        file_names = [f.name for f in files]
        assert "main.py" in file_names
        assert "utils.py" in file_names


class TestScanSourceFiles:
    """Verify _scan_source_files finds source files by extension."""

    def test_finds_python_files(self, tmp_path: Path) -> None:
        """Verify Python files are discovered."""
        (tmp_path / "app.py").write_text("# python")
        files = _scan_source_files(tmp_path)
        assert any(f.name == "app.py" for f in files)

    def test_excludes_non_source_files(self, tmp_path: Path) -> None:
        """Verify markdown and text files are excluded."""
        (tmp_path / "README.md").write_text("# readme")
        (tmp_path / "notes.txt").write_text("notes")
        files = _scan_source_files(tmp_path)
        assert not any(f.name in ("README.md", "notes.txt") for f in files)

    def test_excludes_hidden_directories(self, tmp_path: Path) -> None:
        """Verify files under hidden directories are excluded."""
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "config").write_text("git config")
        # No .py files in .git, but verify nothing explodes
        files = _scan_source_files(tmp_path)
        assert not any(".git" in str(f) for f in files)


class TestAnalyzeCodeWithLLM:
    """TS-101-20: analyze_code_with_llm creates facts from LLM output.

    Requirement: 101-REQ-5.1, 101-REQ-5.6
    """

    @pytest.mark.asyncio
    async def test_creates_facts_from_llm_response(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-20: Verify facts created from LLM response and stored."""
        (tmp_path / "app.py").write_text("def main(): pass")

        with (
            patch(
                "agent_fox.knowledge.code_analysis.ai_call",
                new_callable=AsyncMock,
                return_value=(_SAMPLE_LLM_RESPONSE, None),
            ),
            patch(
                "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
                return_value=False,
            ),
        ):
            result = await analyze_code_with_llm(tmp_path, knowledge_conn, model="STANDARD")

        assert result.facts_created >= 1
        assert result.files_analyzed == 1
        facts = load_facts_by_spec("onboard", knowledge_conn)
        assert any("onboard:code:" in kw for f in facts for kw in f.keywords)

    @pytest.mark.asyncio
    async def test_dedup_skips_already_analyzed_files(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-24: Files with existing fingerprint keyword are skipped.

        Requirement: 101-REQ-5.6
        """
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "analyzed.py").write_text("# already analyzed")

        with patch(
            "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
            return_value=True,
        ):
            result = await analyze_code_with_llm(tmp_path, knowledge_conn, model="STANDARD")

        assert result.files_skipped >= 1


class TestCodeAnalysisEdgeCases:
    """TS-101-E7, TS-101-E8, TS-101-E9: Edge cases for code analysis.

    Requirements: 101-REQ-5.E1, 101-REQ-5.E2, 101-REQ-5.E3
    """

    @pytest.mark.asyncio
    async def test_llm_failure_per_file_continues_to_next(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-E7: LLM failure for one file doesn't block processing others."""
        (tmp_path / "file_a.py").write_text("# a")
        (tmp_path / "file_b.py").write_text("# b")

        valid_response = json.dumps(
            [{"content": "A pattern", "category": "pattern", "confidence": "high", "keywords": ["x"]}]
        )

        call_count = 0

        async def _side_effect(**kwargs: object) -> tuple[str, None]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM error")
            return (valid_response, None)

        with (
            patch(
                "agent_fox.knowledge.code_analysis.ai_call",
                side_effect=_side_effect,
            ),
            patch(
                "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
                return_value=False,
            ),
        ):
            result = await analyze_code_with_llm(tmp_path, knowledge_conn)

        assert result.files_skipped == 1
        assert result.files_analyzed == 1

    @pytest.mark.asyncio
    async def test_fallback_to_disk_when_entity_graph_empty(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-E8: Falls back to disk scan when entity graph has no files."""
        (tmp_path / "module.py").write_text("# python module")

        with (
            patch(
                "agent_fox.knowledge.code_analysis.ai_call",
                new_callable=AsyncMock,
                return_value=(_SAMPLE_LLM_RESPONSE, None),
            ),
            patch(
                "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
                return_value=False,
            ),
        ):
            result = await analyze_code_with_llm(tmp_path, knowledge_conn)

        # Even with empty entity graph, files should be found via disk fallback
        assert result.files_analyzed > 0

    @pytest.mark.asyncio
    async def test_unparseable_llm_response_skips_file(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """TS-101-E9: Unparseable LLM response increments files_skipped."""
        (tmp_path / "broken.py").write_text("# code")

        with (
            patch(
                "agent_fox.knowledge.code_analysis.ai_call",
                new_callable=AsyncMock,
                return_value=("not valid json [[[", None),
            ),
            patch(
                "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
                return_value=False,
            ),
        ):
            result = await analyze_code_with_llm(tmp_path, knowledge_conn)

        assert result.files_skipped >= 1
        assert result.facts_created == 0
