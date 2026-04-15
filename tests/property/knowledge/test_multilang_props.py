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


# Valid identifier strategies (uppercase first char for class, lowercase for func)
_class_name_strategy = st.from_regex(r"[A-Z][a-zA-Z0-9]{1,10}", fullmatch=True)
_base_func_name_strategy = st.from_regex(r"[a-z][a-zA-Z0-9]{1,10}", fullmatch=True)

# Filter out language keywords — using them as identifiers produces unparseable source.
import keyword as _keyword  # noqa: E402

_py_func_name_strategy = _base_func_name_strategy.filter(lambda n: not _keyword.iskeyword(n))

_GO_KEYWORDS = frozenset(
    {
        "break",
        "case",
        "chan",
        "const",
        "continue",
        "default",
        "defer",
        "else",
        "fallthrough",
        "for",
        "func",
        "go",
        "goto",
        "if",
        "import",
        "interface",
        "map",
        "package",
        "range",
        "return",
        "select",
        "struct",
        "switch",
        "type",
        "var",
    }
)
_go_func_name_strategy = _base_func_name_strategy.filter(lambda n: n not in _GO_KEYWORDS)


# ---------------------------------------------------------------------------
# TS-102-P1: Entity validity
# ---------------------------------------------------------------------------


class TestEntityValidity:
    """TS-102-P1: extract_entities always produces valid entities for any supported language.

    Requirement: 102-REQ-2.2, 102-REQ-2.3
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_class_name_strategy, method_name=_py_func_name_strategy)
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
    @given(struct_name=_class_name_strategy, func_name=_go_func_name_strategy)
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
    @given(class_name=_class_name_strategy, method_name=_py_func_name_strategy)
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
            assert source_id in entity_ids, f"edge source_id {source_id!r} not in entity_ids"
            # target_id must be in entity_ids or a known sentinel pattern
            is_entity = target_id in entity_ids
            is_path_sentinel = target_id.startswith("path:")
            is_class_sentinel = target_id.startswith("class:")
            assert is_entity or is_path_sentinel or is_class_sentinel, (
                f"edge target_id {target_id!r} is not an entity ID or sentinel"
            )

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(struct_name=_class_name_strategy, func_name=_go_func_name_strategy)
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

            assert source_id in entity_ids, f"edge source_id {source_id!r} not in entity_ids"
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
    @given(class_name=_class_name_strategy, method_name=_py_func_name_strategy)
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
    @given(struct_name=_class_name_strategy, func_name=_go_func_name_strategy)
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
        import shutil

        from agent_fox.knowledge.lang.registry import _scan_files

        # Hypothesis shares tmp_path across all examples within a test invocation.
        # Use a fresh subdirectory each example to prevent file accumulation.
        scan_dir = tmp_path / "scan"
        if scan_dir.exists():
            shutil.rmtree(scan_dir)
        scan_dir.mkdir()

        # Create files of different types
        for i in range(py_count):
            (scan_dir / f"file{i}.py").write_text("")
        for i in range(go_count):
            (scan_dir / f"file{i}.go").write_text("")
        for i in range(txt_count):
            (scan_dir / f"file{i}.txt").write_text("")

        extensions = {".py", ".go"}
        result = _scan_files(scan_dir, extensions)

        # Every returned file must have an extension in the requested set
        for path in result:
            assert path.suffix in extensions, f"Returned path {path} has extension {path.suffix!r} not in {extensions}"

        # Count must match total files with matching extensions
        expected_count = py_count + go_count
        assert len(result) == expected_count, f"Expected {expected_count} files, got {len(result)}"

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


# ---------------------------------------------------------------------------
# Keyword filters for new language strategies (TS-107-P2, P3, P4, P5)
# ---------------------------------------------------------------------------

_CS_KEYWORDS = frozenset(
    {
        "abstract",
        "as",
        "base",
        "bool",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "checked",
        "class",
        "const",
        "continue",
        "decimal",
        "default",
        "delegate",
        "do",
        "double",
        "else",
        "enum",
        "event",
        "explicit",
        "extern",
        "false",
        "finally",
        "fixed",
        "float",
        "for",
        "foreach",
        "goto",
        "if",
        "implicit",
        "in",
        "int",
        "interface",
        "internal",
        "is",
        "lock",
        "long",
        "namespace",
        "new",
        "null",
        "object",
        "operator",
        "out",
        "override",
        "params",
        "private",
        "protected",
        "public",
        "readonly",
        "ref",
        "return",
        "sbyte",
        "sealed",
        "short",
        "sizeof",
        "stackalloc",
        "static",
        "string",
        "struct",
        "switch",
        "this",
        "throw",
        "true",
        "try",
        "typeof",
        "uint",
        "ulong",
        "unchecked",
        "unsafe",
        "ushort",
        "using",
        "virtual",
        "void",
        "volatile",
        "while",
    }
)

_KT_KEYWORDS = frozenset(
    {
        "as",
        "break",
        "class",
        "continue",
        "do",
        "else",
        "false",
        "for",
        "fun",
        "if",
        "in",
        "interface",
        "is",
        "null",
        "object",
        "package",
        "return",
        "super",
        "this",
        "throw",
        "true",
        "try",
        "typealias",
        "typeof",
        "val",
        "var",
        "when",
        "while",
    }
)

_DART_KEYWORDS = frozenset(
    {
        "abstract",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "continue",
        "covariant",
        "default",
        "deferred",
        "do",
        "dynamic",
        "else",
        "enum",
        "export",
        "extends",
        "extension",
        "external",
        "factory",
        "false",
        "final",
        "finally",
        "for",
        "Function",
        "get",
        "hide",
        "if",
        "implements",
        "import",
        "in",
        "interface",
        "is",
        "late",
        "library",
        "mixin",
        "new",
        "null",
        "on",
        "operator",
        "part",
        "required",
        "rethrow",
        "return",
        "set",
        "show",
        "static",
        "super",
        "switch",
        "sync",
        "this",
        "throw",
        "true",
        "try",
        "typedef",
        "var",
        "void",
        "while",
        "with",
        "yield",
    }
)

_ELIXIR_KEYWORDS = frozenset(
    {
        "after",
        "and",
        "catch",
        "defmodule",
        "defp",
        "def",
        "do",
        "else",
        "end",
        "fn",
        "in",
        "not",
        "or",
        "receive",
        "rescue",
        "true",
        "false",
        "nil",
        "when",
        "with",
    }
)

_cs_class_strategy = _class_name_strategy.filter(lambda n: n not in _CS_KEYWORDS)
_cs_method_strategy = _base_func_name_strategy.filter(lambda n: n not in _CS_KEYWORDS)

_kt_class_strategy = _class_name_strategy.filter(lambda n: n not in _KT_KEYWORDS)
_kt_func_strategy = _base_func_name_strategy.filter(lambda n: n not in _KT_KEYWORDS)

_dart_class_strategy = _class_name_strategy.filter(lambda n: n not in _DART_KEYWORDS)
_dart_method_strategy = _base_func_name_strategy.filter(lambda n: n not in _DART_KEYWORDS)

_elixir_module_strategy = _class_name_strategy.filter(lambda n: n not in _ELIXIR_KEYWORDS)
_elixir_func_strategy = _base_func_name_strategy.filter(lambda n: n not in _ELIXIR_KEYWORDS)


# ---------------------------------------------------------------------------
# TS-107-P1: Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance107:
    """TS-107-P1: All four new analyzers satisfy the LanguageAnalyzer protocol.

    Property: Property 1 from design.md
    Requirements: 107-REQ-1.1, 107-REQ-2.1, 107-REQ-3.1, 107-REQ-4.1
    """

    def test_protocol_conformance_all_new_analyzers(self) -> None:
        """All four new analyzers satisfy LanguageAnalyzer protocol."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        from agent_fox.knowledge.lang.base import LanguageAnalyzer

        for AnalyzerCls in [CSharpAnalyzer, ElixirAnalyzer, KotlinAnalyzer, DartAnalyzer]:
            analyzer = AnalyzerCls()
            assert isinstance(analyzer, LanguageAnalyzer), (
                f"{AnalyzerCls.__name__} must implement LanguageAnalyzer protocol"
            )
            assert len(analyzer.language_name) > 0, f"{AnalyzerCls.__name__}.language_name must be non-empty"
            assert len(analyzer.file_extensions) > 0, f"{AnalyzerCls.__name__}.file_extensions must be non-empty"


# ---------------------------------------------------------------------------
# TS-107-P2: C# entity validity
# ---------------------------------------------------------------------------


class TestCSharpEntityValidity:
    """TS-107-P2: For any valid C# source, entities have non-empty names and valid types.

    Property: Property 2 from design.md
    Requirements: 107-REQ-1.3
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_cs_class_strategy, method_name=_cs_method_strategy)
    def test_csharp_entities_always_valid(
        self,
        tmp_path: Path,
        class_name: str,
        method_name: str,
    ) -> None:
        """For any valid C# class and method name, extract_entities returns valid entities."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = f"namespace Ns {{ class {class_name} {{ void {method_name}() {{}} }} }}"
        cs_file = tmp_path / "gen.cs"
        cs_file.write_text(source)

        analyzer = CSharpAnalyzer()
        tree = _parse_file(cs_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.cs")
        valid_types = set(EntityType)
        for entity in entities:
            assert isinstance(entity.entity_name, str)
            assert len(entity.entity_name) > 0, "entity_name must be non-empty"
            assert isinstance(entity.entity_path, str)
            assert len(entity.entity_path) > 0, "entity_path must be non-empty"
            assert entity.entity_type in valid_types, f"entity_type {entity.entity_type!r} is invalid"


# ---------------------------------------------------------------------------
# TS-107-P3: Kotlin entity validity
# ---------------------------------------------------------------------------


class TestKotlinEntityValidity:
    """TS-107-P3: For any valid Kotlin source, entities have valid types and names.

    Property: Property 2 from design.md
    Requirements: 107-REQ-3.3
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_kt_class_strategy, func_name=_kt_func_strategy)
    def test_kotlin_entities_always_valid(
        self,
        tmp_path: Path,
        class_name: str,
        func_name: str,
    ) -> None:
        """For any valid Kotlin class and function name, extract_entities returns valid entities."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = f"class {class_name} {{ fun {func_name}() {{}} }}"
        kt_file = tmp_path / "gen.kt"
        kt_file.write_text(source)

        analyzer = KotlinAnalyzer()
        tree = _parse_file(kt_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.kt")
        valid_types = set(EntityType)
        for entity in entities:
            assert isinstance(entity.entity_name, str)
            assert len(entity.entity_name) > 0, "entity_name must be non-empty"
            assert entity.entity_type in valid_types, f"entity_type {entity.entity_type!r} is invalid"


# ---------------------------------------------------------------------------
# TS-107-P4: Dart entity validity
# ---------------------------------------------------------------------------


class TestDartEntityValidity:
    """TS-107-P4: For any valid Dart source, entities have valid types and names.

    Property: Property 2 from design.md
    Requirements: 107-REQ-4.3
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(class_name=_dart_class_strategy, method_name=_dart_method_strategy)
    def test_dart_entities_always_valid(
        self,
        tmp_path: Path,
        class_name: str,
        method_name: str,
    ) -> None:
        """For any valid Dart class and method name, extract_entities returns valid entities."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = f"class {class_name} {{ void {method_name}() {{}} }}"
        dart_file = tmp_path / "gen.dart"
        dart_file.write_text(source)

        analyzer = DartAnalyzer()
        tree = _parse_file(dart_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.dart")
        valid_types = set(EntityType)
        for entity in entities:
            assert isinstance(entity.entity_name, str)
            assert len(entity.entity_name) > 0, "entity_name must be non-empty"
            assert entity.entity_type in valid_types, f"entity_type {entity.entity_type!r} is invalid"


# ---------------------------------------------------------------------------
# TS-107-P5: Elixir no-class invariant
# ---------------------------------------------------------------------------


class TestElixirNoClassInvariant:
    """TS-107-P5: Elixir analyzer never produces CLASS entities or EXTENDS edges.

    Property: Property 7 from design.md
    Requirements: 107-REQ-2.4
    """

    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(module_name=_elixir_module_strategy, func_name=_elixir_func_strategy)
    def test_elixir_never_class_or_extends(
        self,
        tmp_path: Path,
        module_name: str,
        func_name: str,
    ) -> None:
        """For any Elixir module and function, no CLASS or EXTENDS appears."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        from agent_fox.knowledge.static_analysis import _parse_file

        source = f"defmodule {module_name} do\n  def {func_name}(x), do: x\nend"
        ex_file = tmp_path / "gen.ex"
        ex_file.write_text(source)

        analyzer = ElixirAnalyzer()
        tree = _parse_file(ex_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "gen.ex")
        assert not any(e.entity_type == EntityType.CLASS for e in entities), "Elixir must never produce CLASS entities"

        edges = analyzer.extract_edges(tree, "gen.ex", entities, {})
        from agent_fox.knowledge.entities import EdgeType

        assert not any(e.relationship == EdgeType.EXTENDS for e in edges), "Elixir must never produce EXTENDS edges"


# ---------------------------------------------------------------------------
# TS-107-P6: Extension uniqueness
# ---------------------------------------------------------------------------


class TestExtensionUniqueness107:
    """TS-107-P6: No two registered analyzers share a file extension.

    Property: Property 4 from design.md
    Requirements: 107-REQ-5.2
    """

    def test_all_extensions_unique(self) -> None:
        """All registered file extensions are pairwise disjoint."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        all_exts: list[str] = []
        for analyzer in registry.all_analyzers():
            for ext in analyzer.file_extensions:
                assert ext not in all_exts, f"Extension {ext!r} is claimed by multiple analyzers"
                all_exts.append(ext)


# ---------------------------------------------------------------------------
# TS-107-P7: Module map path format
# ---------------------------------------------------------------------------


class TestModuleMapPathFormat107:
    """TS-107-P7: Module map values are POSIX-style repo-relative paths.

    Property: Property 6 from design.md
    Requirements: 107-REQ-1.5, 107-REQ-2.6, 107-REQ-3.5, 107-REQ-4.5
    """

    def _write_cs_file(self, tmp_path: Path) -> list:
        """Create a C# source file."""
        cs_dir = tmp_path / "src"
        cs_dir.mkdir(exist_ok=True)
        f = cs_dir / "Foo.cs"
        f.write_text("namespace App { class Foo { } }\n")
        return [f]

    def _write_ex_file(self, tmp_path: Path) -> list:
        """Create an Elixir source file."""
        lib = tmp_path / "lib"
        lib.mkdir(exist_ok=True)
        f = lib / "foo.ex"
        f.write_text("defmodule App.Foo do\n  def bar, do: :ok\nend\n")
        return [f]

    def _write_kt_file(self, tmp_path: Path) -> list:
        """Create a Kotlin source file."""
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        f = src / "Foo.kt"
        f.write_text("package app\nclass Foo { fun bar() {} }\n")
        return [f]

    def _write_dart_file(self, tmp_path: Path) -> list:
        """Create a Dart source file."""
        lib = tmp_path / "lib"
        lib.mkdir(exist_ok=True)
        f = lib / "foo.dart"
        f.write_text("class Foo {}\n")
        return [f]

    def test_csharp_module_map_paths_are_posix(self, tmp_path: Path) -> None:
        """CSharpAnalyzer module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        files = self._write_cs_file(tmp_path)
        analyzer = CSharpAnalyzer()
        mm = analyzer.build_module_map(tmp_path, files)
        for val in mm.values():
            assert len(val) > 0
            assert "\\" not in val
            assert not val.startswith("/")

    def test_elixir_module_map_paths_are_posix(self, tmp_path: Path) -> None:
        """ElixirAnalyzer module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        files = self._write_ex_file(tmp_path)
        analyzer = ElixirAnalyzer()
        mm = analyzer.build_module_map(tmp_path, files)
        for val in mm.values():
            assert len(val) > 0
            assert "\\" not in val
            assert not val.startswith("/")

    def test_kotlin_module_map_paths_are_posix(self, tmp_path: Path) -> None:
        """KotlinAnalyzer module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        files = self._write_kt_file(tmp_path)
        analyzer = KotlinAnalyzer()
        mm = analyzer.build_module_map(tmp_path, files)
        for val in mm.values():
            assert len(val) > 0
            assert "\\" not in val
            assert not val.startswith("/")

    def test_dart_module_map_paths_are_posix(self, tmp_path: Path) -> None:
        """DartAnalyzer module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        files = self._write_dart_file(tmp_path)
        analyzer = DartAnalyzer()
        mm = analyzer.build_module_map(tmp_path, files)
        for val in mm.values():
            assert len(val) > 0
            assert "\\" not in val
            assert not val.startswith("/")
