"""Property-based tests for the multi-language entity graph.

Test Spec: TS-102-P1, TS-102-P2, TS-102-P3, TS-102-P4
Requirements: 102-REQ-2.2, 102-REQ-2.3, 102-REQ-3.1, 102-REQ-4.4, 102-REQ-1.4
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.entities import EntityType
from agent_fox.knowledge.static_analysis import analyze_codebase
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema and all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_python_source(class_name: str, method_name: str) -> str:
    """Generate a minimal Python source string with a class and method."""
    return f"class {class_name}:\n    def {method_name}(self):\n        pass\n"


def _make_go_source(struct_name: str, func_name: str) -> str:
    """Generate a minimal Go source string with a struct and function."""
    return f"package main\n\ntype {struct_name} struct {{}}\n\nfunc {func_name}() {{}}\n"


# Valid Python identifier strategy (uppercase first char for class, lowercase for func)
_class_name_strategy = st.from_regex(r"[A-Z][a-zA-Z0-9]{1,10}", fullmatch=True)
_func_name_strategy = st.from_regex(r"[a-z][a-zA-Z0-9]{1,10}", fullmatch=True)


# ---------------------------------------------------------------------------
# TS-102-P1: Entity validity
# ---------------------------------------------------------------------------


class TestEntityValidity:
    """TS-102-P1: extract_entities always produces valid entities for any supported language.

    Requirement: 102-REQ-2.2, 102-REQ-2.3
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_class_name_strategy, method_name=_func_name_strategy)
    def test_python_entities_always_valid(
        self,
        tmp_path: Path,
        class_name: str,
        method_name: str,
    ) -> None:
        """For any valid Python class name and method, extract_entities returns valid entities."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = _make_python_source(class_name, method_name)
        py_file = tmp_path / "gen.py"
        py_file.write_text(source)

        analyzer = PythonAnalyzer()
        tree = _parse_file(py_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.py")

        # All entities must have non-empty fields and valid types
        valid_types = set(EntityType)
        for entity in entities:
            assert isinstance(entity.entity_name, str)
            assert len(entity.entity_name) > 0, "entity_name must be non-empty"
            assert isinstance(entity.entity_path, str)
            assert len(entity.entity_path) > 0, "entity_path must be non-empty"
            assert entity.entity_type in valid_types, f"entity_type {entity.entity_type!r} is invalid"

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(struct_name=_class_name_strategy, func_name=_func_name_strategy)
    def test_go_entities_always_valid(
        self,
        tmp_path: Path,
        struct_name: str,
        func_name: str,
    ) -> None:
        """For any valid Go struct and function name, extract_entities returns valid entities."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = _make_go_source(struct_name, func_name)
        go_file = tmp_path / "gen.go"
        go_file.write_text(source)

        analyzer = GoAnalyzer()
        tree = _parse_file(go_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.go")

        valid_types = set(EntityType)
        for entity in entities:
            assert isinstance(entity.entity_name, str)
            assert len(entity.entity_name) > 0, "entity_name must be non-empty"
            assert isinstance(entity.entity_path, str)
            assert len(entity.entity_path) > 0, "entity_path must be non-empty"
            assert entity.entity_type in valid_types, f"entity_type {entity.entity_type!r} is invalid"


# ---------------------------------------------------------------------------
# TS-102-P2: Edge referential integrity
# ---------------------------------------------------------------------------


class TestEdgeReferentialIntegrity:
    """TS-102-P2: Every extracted edge references entities from the same extraction run.

    Requirement: 102-REQ-3.1
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_class_name_strategy, method_name=_func_name_strategy)
    def test_python_edge_ids_in_entity_set_or_sentinel(
        self,
        tmp_path: Path,
        class_name: str,
        method_name: str,
    ) -> None:
        """Python edge source/target IDs are entity IDs or well-formed sentinel strings."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = _make_python_source(class_name, method_name)
        py_file = tmp_path / "gen.py"
        py_file.write_text(source)

        analyzer = PythonAnalyzer()
        tree = _parse_file(py_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.py")
        entity_ids = {e.id for e in entities}

        edges = analyzer.extract_edges(tree, "gen.py", entities, {})

        for edge in edges:
            source_id = edge.source_id
            target_id = edge.target_id

            # source_id must be in entity_ids (placeholder IDs are UUIDs)
            assert source_id in entity_ids, (
                f"edge source_id {source_id!r} not in entity_ids"
            )
            # target_id must be in entity_ids or a known sentinel pattern
            is_entity = target_id in entity_ids
            is_path_sentinel = target_id.startswith("path:")
            is_class_sentinel = target_id.startswith("class:")
            assert is_entity or is_path_sentinel or is_class_sentinel, (
                f"edge target_id {target_id!r} is not an entity ID or sentinel"
            )

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(struct_name=_class_name_strategy, func_name=_func_name_strategy)
    def test_go_edge_ids_in_entity_set_or_sentinel(
        self,
        tmp_path: Path,
        struct_name: str,
        func_name: str,
    ) -> None:
        """Go edge source/target IDs are entity IDs or well-formed sentinel strings."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = _make_go_source(struct_name, func_name)
        go_file = tmp_path / "gen.go"
        go_file.write_text(source)

        analyzer = GoAnalyzer()
        tree = _parse_file(go_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.go")
        entity_ids = {e.id for e in entities}

        edges = analyzer.extract_edges(tree, "gen.go", entities, {})

        for edge in edges:
            source_id = edge.source_id
            target_id = edge.target_id

            assert source_id in entity_ids, (
                f"edge source_id {source_id!r} not in entity_ids"
            )
            is_entity = target_id in entity_ids
            is_path_sentinel = target_id.startswith("path:")
            is_class_sentinel = target_id.startswith("class:")
            assert is_entity or is_path_sentinel or is_class_sentinel, (
                f"edge target_id {target_id!r} is not an entity ID or sentinel"
            )


# ---------------------------------------------------------------------------
# TS-102-P3: Upsert idempotency
# ---------------------------------------------------------------------------


class TestUpsertIdempotency:
    """TS-102-P3: Running analyze_codebase twice produces the same entity count.

    Requirements: 102-REQ-4.4, Design CP-3
    """

    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_class_name_strategy, method_name=_func_name_strategy)
    def test_python_analysis_idempotent(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
        class_name: str,
        method_name: str,
    ) -> None:
        """Running analyze_codebase twice on the same Python repo produces the same count."""
        py_file = tmp_path / "gen.py"
        py_file.write_text(_make_python_source(class_name, method_name))

        result1 = analyze_codebase(tmp_path, entity_conn)
        result2 = analyze_codebase(tmp_path, entity_conn)

        assert result1.entities_upserted == result2.entities_upserted, (
            "Re-running analysis must produce the same entity count"
        )

        # No duplicate natural keys in DB
        rows = entity_conn.execute(
            "SELECT entity_type, entity_path, entity_name, COUNT(*) as cnt "
            "FROM entity_graph WHERE deleted_at IS NULL "
            "GROUP BY entity_type, entity_path, entity_name "
            "HAVING COUNT(*) > 1"
        ).fetchall()
        assert len(rows) == 0, f"Duplicate natural keys found: {rows}"

        # languages_analyzed must be present and include python (new in Spec-102)
        assert result1.languages_analyzed == ("python",), (
            f"Python-only analysis must return ('python',), got {result1.languages_analyzed!r}"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(struct_name=_class_name_strategy, func_name=_func_name_strategy)
    def test_multilang_analysis_idempotent(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
        struct_name: str,
        func_name: str,
    ) -> None:
        """Running analyze_codebase twice on a mixed-language repo produces the same count."""
        (tmp_path / "gen.py").write_text(_make_python_source(struct_name, func_name))
        (tmp_path / "gen.go").write_text(_make_go_source(struct_name, func_name))

        result1 = analyze_codebase(tmp_path, entity_conn)
        result2 = analyze_codebase(tmp_path, entity_conn)

        assert result1.entities_upserted == result2.entities_upserted, (
            "Re-running multi-language analysis must produce the same entity count"
        )

        # Both languages must appear in languages_analyzed (new in Spec-102)
        assert "python" in result1.languages_analyzed, "Python must appear in languages_analyzed"
        assert "go" in result1.languages_analyzed, "Go must appear in languages_analyzed"


# ---------------------------------------------------------------------------
# TS-102-P4: Scan subset
# ---------------------------------------------------------------------------


class TestScanSubset:
    """TS-102-P4: _scan_files returns a subset of files with the requested extensions.

    Requirement: 102-REQ-1.4
    """

    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        py_count=st.integers(min_value=0, max_value=5),
        go_count=st.integers(min_value=0, max_value=5),
        txt_count=st.integers(min_value=0, max_value=3),
    )
    def test_scan_files_returns_subset_with_correct_extensions(
        self,
        tmp_path: Path,
        py_count: int,
        go_count: int,
        txt_count: int,
    ) -> None:
        """_scan_files with {.py, .go} returns only .py and .go files."""
        from agent_fox.knowledge.lang.registry import _scan_files

        # Create files of different types
        for i in range(py_count):
            (tmp_path / f"file{i}.py").write_text("")
        for i in range(go_count):
            (tmp_path / f"file{i}.go").write_text("")
        for i in range(txt_count):
            (tmp_path / f"file{i}.txt").write_text("")

        extensions = {".py", ".go"}
        result = _scan_files(tmp_path, extensions)

        # Every returned file must have an extension in the requested set
        for path in result:
            assert path.suffix in extensions, (
                f"Returned path {path} has extension {path.suffix!r} not in {extensions}"
            )

        # Count must be <= total files with matching extensions
        expected_count = py_count + go_count
        assert len(result) == expected_count, (
            f"Expected {expected_count} files, got {len(result)}"
        )

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        filenames=st.lists(
            st.from_regex(r"[a-z]{1,8}", fullmatch=True),
            min_size=1,
            max_size=10,
            unique=True,
        )
    )
    def test_scan_files_result_is_sorted(self, tmp_path: Path, filenames: list[str]) -> None:
        """_scan_files always returns paths in alphabetical order."""
        from agent_fox.knowledge.lang.registry import _scan_files

        for name in filenames:
            (tmp_path / f"{name}.py").write_text("")

        result = _scan_files(tmp_path, {".py"})

        assert result == sorted(result), "Results must always be sorted alphabetically"
