"""Tests for multi-language codebase analysis orchestration and schema.

Test Spec: TS-102-15 through TS-102-21, TS-102-E5, TS-102-E6
Requirements: 102-REQ-4.1, 102-REQ-4.2, 102-REQ-4.3, 102-REQ-4.4, 102-REQ-4.5,
              102-REQ-4.E1, 102-REQ-4.E2, 102-REQ-5.1, 102-REQ-5.2, 102-REQ-5.3,
              102-REQ-6.1, 102-REQ-6.3
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

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


@pytest.fixture
def v8_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with schema up to but NOT including migration v9.

    Used to test the v9 migration itself.
    """
    from agent_fox.knowledge.migrations import MIGRATIONS, record_version

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    # Apply all migrations strictly less than v9
    for migration in MIGRATIONS:
        if migration.version >= 9:
            continue
        migration.apply(conn)
        record_version(conn, migration.version, migration.description)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TS-102-15: Mixed-language analysis
# ---------------------------------------------------------------------------


class TestMixedLanguageAnalysis:
    """TS-102-15: analyze_codebase on a mixed-language repo produces entities from all languages.

    Requirements: 102-REQ-4.1, 102-REQ-4.2
    """

    def test_mixed_language_entities_aggregated(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Entities from Python and Go files are both included in the result."""
        (tmp_path / "main.py").write_text(
            """\
class PyClass:
    def py_method(self):
        pass
"""
        )
        (tmp_path / "main.go").write_text(
            """\
package main

type GoStruct struct{}

func GoFunc() {}
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        rows = entity_conn.execute(
            "SELECT entity_type, entity_name, language FROM entity_graph WHERE deleted_at IS NULL"
        ).fetchall()

        languages_in_db = {r[2] for r in rows if r[2] is not None}
        assert "python" in languages_in_db, "Python entities must be in the graph"
        assert "go" in languages_in_db, "Go entities must be in the graph"
        assert result.entities_upserted > 2, "Entities from both languages must be counted"

    def test_mixed_language_result_has_languages_analyzed(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """AnalysisResult.languages_analyzed includes both languages."""
        (tmp_path / "main.py").write_text("def foo(): pass\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")

        result = analyze_codebase(tmp_path, entity_conn)

        # languages_analyzed must be a sorted tuple of analyzed language names
        assert hasattr(result, "languages_analyzed"), "AnalysisResult must have languages_analyzed field"
        assert "go" in result.languages_analyzed
        assert "python" in result.languages_analyzed


# ---------------------------------------------------------------------------
# TS-102-16: Languages analyzed field
# ---------------------------------------------------------------------------


class TestLanguagesAnalyzedField:
    """TS-102-16: AnalysisResult.languages_analyzed lists exactly the languages analyzed.

    Requirement: 102-REQ-4.3
    """

    def test_python_only_repo_returns_python_tuple(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Python-only repo: languages_analyzed == ('python',)."""
        (tmp_path / "app.py").write_text("def hello(): pass\n")

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.languages_analyzed == ("python",)

    def test_mixed_repo_returns_sorted_tuple(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Mixed Python+Go repo: languages_analyzed is a sorted tuple."""
        (tmp_path / "app.py").write_text("def hello(): pass\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")

        result = analyze_codebase(tmp_path, entity_conn)

        assert sorted(result.languages_analyzed) == list(result.languages_analyzed), (
            "languages_analyzed must be sorted alphabetically"
        )
        assert "go" in result.languages_analyzed
        assert "python" in result.languages_analyzed

    def test_no_files_returns_empty_tuple(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """No source files: languages_analyzed == ()."""
        (tmp_path / "README.md").write_text("# Docs\n")

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.languages_analyzed == (), f"Expected (), got {result.languages_analyzed!r}"

    def test_languages_analyzed_default_is_empty_tuple(self) -> None:
        """AnalysisResult default languages_analyzed is empty tuple (backward compat)."""
        from agent_fox.knowledge.entities import AnalysisResult

        result = AnalysisResult(entities_upserted=0, edges_upserted=0, entities_soft_deleted=0)
        assert result.languages_analyzed == ()


# ---------------------------------------------------------------------------
# TS-102-17: Soft-delete across languages
# ---------------------------------------------------------------------------


class TestSoftDeleteAcrossLanguages:
    """TS-102-17: Entities from removed files are soft-deleted regardless of language.

    Requirement: 102-REQ-4.4
    """

    def test_go_entities_soft_deleted_when_file_removed(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Go file entities are soft-deleted when the file is removed between runs."""
        py_file = tmp_path / "app.py"
        go_file = tmp_path / "main.go"
        py_file.write_text("def hello(): pass\n")
        go_file.write_text("package main\nfunc main() {}\n")

        # First analysis: both files present
        analyze_codebase(tmp_path, entity_conn)

        # Remove the Go file
        go_file.unlink()

        # Second analysis: only Python file
        result2 = analyze_codebase(tmp_path, entity_conn)

        assert result2.entities_soft_deleted >= 1, "Go entities must be soft-deleted after file removal"

        # Verify Go entities have deleted_at set
        rows = entity_conn.execute("SELECT entity_name, deleted_at FROM entity_graph WHERE language = 'go'").fetchall()
        if rows:  # Only check if Go entities were created in the first run
            assert all(r[1] is not None for r in rows), "All Go entities must be soft-deleted"

    def test_python_entities_survive_go_file_removal(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Python entities remain active when only a Go file is removed."""
        py_file = tmp_path / "app.py"
        go_file = tmp_path / "main.go"
        py_file.write_text("class MyClass: pass\n")
        go_file.write_text("package main\nfunc main() {}\n")

        analyze_codebase(tmp_path, entity_conn)
        go_file.unlink()
        analyze_codebase(tmp_path, entity_conn)

        # Python entities must remain active
        rows = entity_conn.execute(
            "SELECT entity_name FROM entity_graph WHERE language = 'python' AND deleted_at IS NULL"
        ).fetchall()
        assert len(rows) > 0, "Python entities must remain active after Go file removal"


# ---------------------------------------------------------------------------
# TS-102-18: Migration v9
# ---------------------------------------------------------------------------


class TestMigrationV9:
    """TS-102-18: Migration v9 adds a nullable language VARCHAR column to entity_graph.

    Requirements: 102-REQ-5.1, 102-REQ-5.E1
    """

    def test_v9_adds_language_column(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """After all migrations (including v9), entity_graph has a language column."""
        columns = {
            row[0]
            for row in entity_conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'entity_graph'"
            ).fetchall()
        }
        assert "language" in columns, "Migration v9 must add a 'language' column to entity_graph"

    def test_v9_language_column_is_nullable(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """The language column must be nullable (VARCHAR, no NOT NULL constraint)."""
        rows = entity_conn.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'entity_graph' AND column_name = 'language'"
        ).fetchall()
        assert len(rows) == 1, "language column must exist in entity_graph"
        is_nullable = rows[0][0]
        assert is_nullable in ("YES", True, 1), "language column must be nullable"

    def test_v9_migration_applied(self, v8_conn: duckdb.DuckDBPyConnection) -> None:
        """Applying migration v9 to a v8 database adds the language column."""
        from agent_fox.knowledge.migrations import MIGRATIONS

        # Find and apply migration v9
        v9_migration = next((m for m in MIGRATIONS if m.version == 9), None)
        assert v9_migration is not None, "Migration v9 must be registered in MIGRATIONS"

        v9_migration.apply(v8_conn)

        columns = {
            row[0]
            for row in v8_conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'entity_graph'"
            ).fetchall()
        }
        assert "language" in columns


# ---------------------------------------------------------------------------
# TS-102-19: Language column backfill
# ---------------------------------------------------------------------------


class TestLanguageColumnBackfill:
    """TS-102-19: Migration v9 backfills existing entities with language = 'python'.

    Requirement: 102-REQ-5.2
    """

    def test_existing_entities_backfilled_with_python(self, v8_conn: duckdb.DuckDBPyConnection) -> None:
        """After v9, all pre-existing entities have language = 'python'."""
        import uuid

        from agent_fox.knowledge.migrations import MIGRATIONS, record_version

        # Insert 3 entities before v9 (v8 schema has no language column)
        for i in range(3):
            v8_conn.execute(
                "INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at) "
                "VALUES (?, 'file', ?, ?, CURRENT_TIMESTAMP)",
                [str(uuid.uuid4()), f"file{i}.py", f"file{i}.py"],
            )

        # Apply v9 migration
        v9_migration = next((m for m in MIGRATIONS if m.version == 9), None)
        assert v9_migration is not None
        v9_migration.apply(v8_conn)
        record_version(v8_conn, 9, "test: add language column")

        # All 3 entities should now have language = 'python'
        rows = v8_conn.execute("SELECT language FROM entity_graph WHERE language IS NOT NULL").fetchall()
        assert len(rows) == 3, "All pre-existing entities must be backfilled"
        assert all(r[0] == "python" for r in rows), "All backfilled entities must have language = 'python'"

    def test_backfill_is_noop_for_empty_table(self, v8_conn: duckdb.DuckDBPyConnection) -> None:
        """Migration v9 completes without error when entity_graph is empty."""
        from agent_fox.knowledge.migrations import MIGRATIONS

        v9_migration = next((m for m in MIGRATIONS if m.version == 9), None)
        assert v9_migration is not None

        # Should not raise any exception
        v9_migration.apply(v8_conn)

        rows = v8_conn.execute("SELECT COUNT(*) FROM entity_graph").fetchone()
        assert rows is not None and rows[0] == 0


# ---------------------------------------------------------------------------
# TS-102-20: New entity language tag
# ---------------------------------------------------------------------------


class TestNewEntityLanguageTag:
    """TS-102-20: New entities created after v9 have the correct language value.

    Requirements: 102-REQ-5.3, 102-REQ-2.4
    """

    def test_go_entities_tagged_with_go_language(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Go file entities have language = 'go' in entity_graph."""
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")

        analyze_codebase(tmp_path, entity_conn)

        rows = entity_conn.execute(
            "SELECT language FROM entity_graph WHERE entity_path = 'main.go' AND deleted_at IS NULL"
        ).fetchall()
        assert len(rows) > 0, "main.go entity must exist"
        assert all(r[0] == "go" for r in rows), "Go entities must have language = 'go'"

    def test_python_entities_tagged_with_python_language(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Python file entities have language = 'python' in entity_graph."""
        (tmp_path / "app.py").write_text("def hello(): pass\n")

        analyze_codebase(tmp_path, entity_conn)

        rows = entity_conn.execute(
            "SELECT language FROM entity_graph WHERE entity_path = 'app.py' AND deleted_at IS NULL"
        ).fetchall()
        assert len(rows) > 0, "app.py entity must exist"
        assert all(r[0] == "python" for r in rows), "Python entities must have language = 'python'"

    def test_mixed_repo_entities_have_correct_languages(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Go and Python entities in a mixed repo each have their own language tag."""
        (tmp_path / "app.py").write_text("def hello(): pass\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")

        analyze_codebase(tmp_path, entity_conn)

        langs = {
            row[0]
            for row in entity_conn.execute(
                "SELECT DISTINCT language FROM entity_graph WHERE deleted_at IS NULL AND language IS NOT NULL"
            ).fetchall()
        }
        assert "python" in langs
        assert "go" in langs


# ---------------------------------------------------------------------------
# TS-102-21: Python backward compatibility
# ---------------------------------------------------------------------------


class TestPythonBackwardCompatibility:
    """TS-102-21: Python-only codebase produces identical entities and edges as pre-Spec-102.

    Requirements: 102-REQ-6.1, 102-REQ-6.2, 102-REQ-4.5
    """

    def test_python_only_result_languages_analyzed(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Python-only repo returns languages_analyzed == ('python',)."""
        (tmp_path / "models.py").write_text(
            """\
class User:
    def validate(self):
        pass
"""
        )
        result = analyze_codebase(tmp_path, entity_conn)
        assert result.languages_analyzed == ("python",)

    def test_python_entities_unchanged(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Python entities have the same natural keys as the pre-Spec-102 output."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "models.py").write_text(
            """\
class User:
    def save(self):
        pass

def helper():
    pass
"""
        )
        (pkg / "views.py").write_text(
            """\
from pkg.models import User

class UserView(User):
    def render(self):
        pass
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        rows = entity_conn.execute(
            "SELECT entity_type, entity_path, entity_name FROM entity_graph WHERE deleted_at IS NULL"
        ).fetchall()
        natural_keys = {(r[0], r[1], r[2]) for r in rows}

        # Expected entities from pre-Spec-102 behavior:
        assert ("file", "pkg/__init__.py", "__init__.py") in natural_keys
        assert ("file", "pkg/models.py", "models.py") in natural_keys
        assert ("file", "pkg/views.py", "views.py") in natural_keys
        assert ("class", "pkg/models.py", "User") in natural_keys
        assert ("function", "pkg/models.py", "User.save") in natural_keys
        assert ("function", "pkg/models.py", "helper") in natural_keys
        assert ("class", "pkg/views.py", "UserView") in natural_keys
        assert ("function", "pkg/views.py", "UserView.render") in natural_keys

        assert result.entities_upserted > 0
        assert result.edges_upserted >= 0
        # languages_analyzed must be present (new in Spec-102)
        assert result.languages_analyzed == ("python",)

    def test_analyze_codebase_signature_unchanged(self) -> None:
        """analyze_codebase signature remains (repo_root, conn) -> AnalysisResult."""
        import inspect

        from agent_fox.knowledge.entities import AnalysisResult

        sig = inspect.signature(analyze_codebase)
        params = list(sig.parameters.keys())
        assert "repo_root" in params, "analyze_codebase must have repo_root parameter"
        assert "conn" in params, "analyze_codebase must have conn parameter"

        anno = sig.return_annotation
        assert anno is AnalysisResult or anno == "AnalysisResult", "analyze_codebase must return AnalysisResult"
        # AnalysisResult must have languages_analyzed field (new in Spec-102)
        default_result = AnalysisResult(entities_upserted=0, edges_upserted=0, entities_soft_deleted=0)
        assert hasattr(default_result, "languages_analyzed"), "AnalysisResult must have languages_analyzed field"


# ---------------------------------------------------------------------------
# TS-102-E5: No source files found
# ---------------------------------------------------------------------------


class TestNoSourceFilesFound:
    """TS-102-E5: When no registered extensions match any files, analysis returns zero counts.

    Requirement: 102-REQ-4.E1
    """

    def test_no_source_files_returns_zero_counts(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Only .txt and .md files: AnalysisResult is all zeros."""
        (tmp_path / "README.md").write_text("# Docs\n")
        (tmp_path / "notes.txt").write_text("notes")

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.entities_upserted == 0
        assert result.edges_upserted == 0
        assert result.languages_analyzed == ()


# ---------------------------------------------------------------------------
# TS-102-E6: Analyzer crash isolation
# ---------------------------------------------------------------------------


class TestAnalyzerCrashIsolation:
    """TS-102-E6: A crash in one language analyzer does not stop other languages.

    Requirement: 102-REQ-4.E2
    """

    def test_go_crash_does_not_stop_python(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If GoAnalyzer raises RuntimeError, Python entities are still extracted."""
        (tmp_path / "app.py").write_text("def hello(): pass\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")

        with patch("agent_fox.knowledge.lang.go_lang.GoAnalyzer.extract_entities", side_effect=RuntimeError("crash")):
            with caplog.at_level(logging.ERROR, logger="agent_fox"):
                result = analyze_codebase(tmp_path, entity_conn)

        # Python entities must still be created
        rows = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'python' AND deleted_at IS NULL"
        ).fetchone()
        assert rows is not None and rows[0] > 0, "Python entities must be created despite Go crash"

        # Go crash must be logged
        assert "go" in caplog.text.lower() or "crash" in caplog.text.lower()

        # Go must not appear in languages_analyzed
        assert "go" not in result.languages_analyzed
