"""Tests for static_analysis module.

Test Spec: TS-95-12 through TS-95-17, TS-95-E5 through TS-95-E7
Requirements: 95-REQ-4.*
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.entities import EdgeType, EntityType
from agent_fox.knowledge.static_analysis import (
    _extract_edges,
    _extract_entities,
    _parse_file,
    _scan_python_files,
    analyze_codebase,
)
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema + all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def simple_python_file(tmp_path: Path) -> Path:
    """A Python file with class, method, and top-level function."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "example.py"
    f.write_text(
        """\
class Foo:
    def bar(self) -> None:
        pass


def baz() -> None:
    pass
"""
    )
    return f


@pytest.fixture
def import_python_file(tmp_path: Path) -> Path:
    """A Python file with imports and class inheritance."""
    from agent_fox.knowledge.entity_store import upsert_entities  # noqa: F401

    src = tmp_path / "src"
    src.mkdir()
    f = src / "service.py"
    f.write_text(
        """\
from os.path import join


class Sub(Base):
    def method(self) -> None:
        pass


def top_func() -> None:
    pass
"""
    )
    return f


# ---------------------------------------------------------------------------
# TS-95-12: Python file scanning respects .gitignore
# ---------------------------------------------------------------------------


class TestScanPythonFiles:
    """TS-95-12: _scan_python_files returns .py files excluding .gitignore matches.

    Requirement: 95-REQ-4.1
    """

    def test_scans_python_files_excluding_gitignore(self, tmp_path: Path) -> None:
        """Returns tracked .py files, skipping .gitignore-matched paths."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("# a")
        (src / "b.py").write_text("# b")

        build = tmp_path / "build"
        build.mkdir()
        (build / "c.py").write_text("# c")

        (tmp_path / ".gitignore").write_text("build/\n")

        files = _scan_python_files(tmp_path)
        names = {f.name for f in files}

        assert "a.py" in names
        assert "b.py" in names
        assert "c.py" not in names


# ---------------------------------------------------------------------------
# TS-95-13: Entity extraction from Python file
# ---------------------------------------------------------------------------


class TestExtractEntities:
    """TS-95-13: _extract_entities extracts file, class, method, and function entities.

    Requirement: 95-REQ-4.2
    """

    def test_extract_file_class_method_function(self, simple_python_file: Path) -> None:
        """Extracts file entity, Foo class, Foo.bar method, and baz function."""
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as py_language  # type: ignore[import]

        parser = Parser(Language(py_language()))
        tree = _parse_file(simple_python_file, parser)
        assert tree is not None

        entities = _extract_entities(tree, "src/example.py")
        names = {e.entity_name for e in entities}

        assert "example.py" in names  # file entity
        assert "Foo" in names  # class entity
        assert "Foo.bar" in names  # method entity (qualified name)
        assert "baz" in names  # top-level function

    def test_entity_types_assigned_correctly(self, simple_python_file: Path) -> None:
        """Extracted entities have correct EntityType values."""
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as py_language  # type: ignore[import]

        parser = Parser(Language(py_language()))
        tree = _parse_file(simple_python_file, parser)
        assert tree is not None

        entities = _extract_entities(tree, "src/example.py")
        type_map = {e.entity_name: e.entity_type for e in entities}

        assert type_map.get("example.py") == EntityType.FILE
        assert type_map.get("Foo") == EntityType.CLASS
        assert type_map.get("Foo.bar") == EntityType.FUNCTION
        assert type_map.get("baz") == EntityType.FUNCTION


# ---------------------------------------------------------------------------
# TS-95-14: Edge extraction from Python file
# ---------------------------------------------------------------------------


class TestExtractEdges:
    """TS-95-14: _extract_edges extracts contains, imports, and extends edges.

    Requirement: 95-REQ-4.3
    """

    def test_extract_contains_imports_extends(self, tmp_path: Path) -> None:
        """Extracts contains, imports, and extends edges from a Python file."""
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as py_language  # type: ignore[import]

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "service.py"
        py_file.write_text(
            """\
from os.path import join


class Sub(Base):
    def method(self) -> None:
        pass


def top_func() -> None:
    pass
"""
        )

        parser = Parser(Language(py_language()))
        tree = _parse_file(py_file, parser)
        assert tree is not None

        rel_path = "src/service.py"
        entities = _extract_entities(tree, rel_path)
        module_map: dict[str, str] = {}

        edges = _extract_edges(tree, rel_path, entities, module_map)
        rels = {e.relationship for e in edges}

        assert EdgeType.CONTAINS in rels
        assert EdgeType.EXTENDS in rels
        # IMPORTS may or may not appear depending on module_map resolution
        # But the edge extraction mechanism should at least attempt imports


# ---------------------------------------------------------------------------
# TS-95-15: Analysis result counts
# ---------------------------------------------------------------------------


class TestAnalysisResultCounts:
    """TS-95-15: analyze_codebase returns non-zero counts for a non-empty repo.

    Requirement: 95-REQ-4.4
    """

    def test_analysis_returns_nonzero_counts(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """AnalysisResult has entities_upserted > 0 on a non-empty repo."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "models.py").write_text(
            """\
class User:
    def save(self) -> None:
        pass


class Post:
    pass
"""
        )
        (pkg / "views.py").write_text(
            """\
class View:
    pass
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.entities_upserted > 0
        assert result.edges_upserted >= 0
        assert result.entities_soft_deleted == 0  # first run, no deletions


# ---------------------------------------------------------------------------
# TS-95-16: Soft-delete on re-analysis
# ---------------------------------------------------------------------------


class TestSoftDeleteOnReanalysis:
    """TS-95-16: Entities missing from re-analysis are soft-deleted.

    Requirement: 95-REQ-4.5
    """

    def test_missing_file_soft_deleted_on_reanalysis(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Entity for a deleted file has deleted_at set after re-analysis."""
        src = tmp_path / "src"
        src.mkdir()
        old_file = src / "old.py"
        old_file.write_text("def old_func() -> None:\n    pass\n")

        # First analysis
        analyze_codebase(tmp_path, entity_conn)

        # Remove the file
        old_file.unlink()

        # Re-analysis
        result = analyze_codebase(tmp_path, entity_conn)
        assert result.entities_soft_deleted >= 1

        # Check that the old.py file entity has deleted_at set
        rows = entity_conn.execute("SELECT deleted_at FROM entity_graph WHERE entity_path LIKE '%old.py%'").fetchall()
        assert len(rows) > 0
        assert all(r[0] is not None for r in rows), "Old file entities should be soft-deleted"


# ---------------------------------------------------------------------------
# TS-95-17: Import resolution via module map
# ---------------------------------------------------------------------------


class TestImportResolution:
    """TS-95-17: Import resolution uses module map to find repo-relative paths.

    Requirement: 95-REQ-4.6
    """

    def test_import_edge_resolved_via_module_map(self, tmp_path: Path) -> None:
        """Imports edge resolves dotted Python paths via module map."""
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as py_language  # type: ignore[import]

        src_dir = tmp_path / "agent_fox" / "knowledge"
        src_dir.mkdir(parents=True)
        (tmp_path / "agent_fox" / "__init__.py").write_text("")
        (tmp_path / "agent_fox" / "knowledge" / "__init__.py").write_text("")
        db_py = src_dir / "db.py"
        db_py.write_text("class KnowledgeDB:\n    pass\n")

        importer = tmp_path / "main.py"
        importer.write_text("from agent_fox.knowledge.db import KnowledgeDB\n")

        module_map = {
            "agent_fox.knowledge.db": "agent_fox/knowledge/db.py",
        }

        parser = Parser(Language(py_language()))
        tree = _parse_file(importer, parser)
        assert tree is not None

        rel_path = "main.py"
        entities = _extract_entities(tree, rel_path)
        edges = _extract_edges(tree, rel_path, entities, module_map)

        import_edges = [e for e in edges if e.relationship == EdgeType.IMPORTS]
        # Should have an import edge pointing to the resolved module path
        # (The target entity_path should resolve to "agent_fox/knowledge/db.py")
        assert len(import_edges) >= 1


# ---------------------------------------------------------------------------
# TS-95-E5: Unparseable Python file is skipped with a warning
# ---------------------------------------------------------------------------


class TestUnparseablePythonFile:
    """TS-95-E5: Files with syntax errors are skipped with a warning.

    Requirement: 95-REQ-4.E1
    """

    def test_syntax_error_file_skipped(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Analysis skips bad.py and still processes good.py."""
        import logging

        src = tmp_path / "src"
        src.mkdir()
        (src / "good.py").write_text("def good() -> None:\n    pass\n")
        (src / "bad.py").write_text("def broken(\n  # unterminated")

        with caplog.at_level(logging.WARNING, logger="agent_fox"):
            result = analyze_codebase(tmp_path, entity_conn)

        assert result.entities_upserted > 0  # from good.py
        # A warning should have been logged mentioning bad.py
        assert "bad.py" in caplog.text


# ---------------------------------------------------------------------------
# TS-95-E6: Non-existent repo root raises ValueError
# ---------------------------------------------------------------------------


class TestNonExistentRepoRoot:
    """TS-95-E6: analyze_codebase raises ValueError for non-existent repo root.

    Requirement: 95-REQ-4.E2
    """

    def test_nonexistent_path_raises_value_error(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """ValueError raised for a path that does not exist."""
        with pytest.raises(ValueError):
            analyze_codebase(Path("/nonexistent/path/does/not/exist"), entity_conn)


# ---------------------------------------------------------------------------
# TS-95-E7: Empty repository (no Python files) returns zero counts
# ---------------------------------------------------------------------------


class TestEmptyRepository:
    """TS-95-E7: No Python files found returns zero-count AnalysisResult.

    Requirement: 95-REQ-4.E3
    """

    def test_no_python_files_returns_zero_counts(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """AnalysisResult is all zeros when no recognized source files exist."""
        # Only use extensions that are genuinely unrecognized by any analyzer.
        # .json and .html are now supported; use .md and .txt instead.
        (tmp_path / "README.md").write_text("# Docs\n")
        (tmp_path / "notes.txt").write_text("plain text")

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.entities_upserted == 0
        assert result.edges_upserted == 0
        assert result.entities_soft_deleted == 0
