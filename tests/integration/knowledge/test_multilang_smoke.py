"""Smoke tests for end-to-end multi-language entity graph analysis.

Test Spec: TS-102-SMOKE-1, TS-102-SMOKE-2, TS-102-SMOKE-3
Requirements: All
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

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


# ---------------------------------------------------------------------------
# TS-102-SMOKE-1: Full multi-language analysis
# ---------------------------------------------------------------------------


class TestFullMultiLanguageAnalysis:
    """TS-102-SMOKE-1: End-to-end analysis of Python + Go + TypeScript repository.

    Requirements: All
    """

    def test_full_mixed_language_analysis(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Analyze a repo with Python, Go, and TypeScript files; verify entities and edges."""
        # app.py: class, function, import
        (tmp_path / "app.py").write_text(
            """\
class Application:
    def run(self):
        pass

def start():
    pass
"""
        )

        # server.go: struct, function
        (tmp_path / "server.go").write_text(
            """\
package main

type Server struct{}

func NewServer() *Server { return nil }
"""
        )

        # client.ts: class, function, import
        (tmp_path / "client.ts").write_text(
            """\
import { Base } from './base';

class Client extends Base {
    connect(): void {}
}

export function createClient(): Client { return new Client(); }
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        # Entity count: at minimum 3 FILE + 3 classes/structs + 4+ functions
        assert result.entities_upserted >= 7, (
            f"Expected at least 7 entities, got {result.entities_upserted}"
        )

        # Edge count: at minimum the CONTAINS edges
        assert result.edges_upserted >= 3, (
            f"Expected at least 3 edges (CONTAINS), got {result.edges_upserted}"
        )

        # languages_analyzed must include all three
        assert "python" in result.languages_analyzed
        assert "go" in result.languages_analyzed
        assert "typescript" in result.languages_analyzed

        # DB language column populated correctly
        lang_rows = entity_conn.execute(
            "SELECT DISTINCT language FROM entity_graph WHERE deleted_at IS NULL AND language IS NOT NULL"
        ).fetchall()
        languages_in_db = {r[0] for r in lang_rows}
        assert "python" in languages_in_db
        assert "go" in languages_in_db
        assert "typescript" in languages_in_db

    def test_full_analysis_db_language_column_populated(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """After full analysis, no entity has a NULL language value."""
        (tmp_path / "app.py").write_text("def hello(): pass\n")
        (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")

        analyze_codebase(tmp_path, entity_conn)

        null_lang_rows = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language IS NULL AND deleted_at IS NULL"
        ).fetchone()
        assert null_lang_rows is not None
        assert null_lang_rows[0] == 0, "All active entities must have a non-NULL language value"


# ---------------------------------------------------------------------------
# TS-102-SMOKE-2: Python backward compatibility end-to-end
# ---------------------------------------------------------------------------


class TestPythonBackwardCompatibilityEndToEnd:
    """TS-102-SMOKE-2: Python-only repo produces DB state matching pre-Spec-102 behavior.

    Requirement: 102-REQ-6.1
    """

    def test_python_package_analysis_produces_correct_db_state(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """A Python package analysis produces correct entity natural keys and edge triples."""
        # Create a Python package with 3 files
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "models.py").write_text(
            """\
class Base:
    def validate(self):
        pass

class User(Base):
    def save(self):
        pass
"""
        )
        (pkg / "views.py").write_text(
            """\
from mypkg.models import User

class UserView(User):
    def render(self):
        pass

def index():
    pass
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        # Verify entity natural keys
        rows = entity_conn.execute(
            "SELECT entity_type, entity_path, entity_name FROM entity_graph WHERE deleted_at IS NULL"
        ).fetchall()
        natural_keys = {(r[0], r[1], r[2]) for r in rows}

        # File entities
        assert ("file", "mypkg/__init__.py", "__init__.py") in natural_keys
        assert ("file", "mypkg/models.py", "models.py") in natural_keys
        assert ("file", "mypkg/views.py", "views.py") in natural_keys

        # Class entities
        assert ("class", "mypkg/models.py", "Base") in natural_keys
        assert ("class", "mypkg/models.py", "User") in natural_keys
        assert ("class", "mypkg/views.py", "UserView") in natural_keys

        # Function entities (qualified names)
        assert ("function", "mypkg/models.py", "Base.validate") in natural_keys
        assert ("function", "mypkg/models.py", "User.save") in natural_keys
        assert ("function", "mypkg/views.py", "UserView.render") in natural_keys
        assert ("function", "mypkg/views.py", "index") in natural_keys

        # Result fields
        assert result.entities_upserted > 0
        assert result.edges_upserted >= 0
        assert result.languages_analyzed == ("python",)

    def test_python_analysis_edges_present(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Python analysis produces CONTAINS, IMPORTS, and EXTENDS edges in the DB."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "base.py").write_text("class Base:\n    pass\n")
        (pkg / "derived.py").write_text(
            "from pkg.base import Base\n\nclass Derived(Base):\n    def method(self):\n        pass\n"
        )

        analyze_codebase(tmp_path, entity_conn)

        edge_types = {
            row[0]
            for row in entity_conn.execute(
                "SELECT DISTINCT relationship FROM entity_edges"
            ).fetchall()
        }

        assert "contains" in edge_types, "CONTAINS edges must be present"
        assert "imports" in edge_types, "IMPORTS edges must be present"
        assert "extends" in edge_types, "EXTENDS edges must be present"

        # Verify language column is populated (new in Spec-102)
        lang_rows = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language IS NULL AND deleted_at IS NULL"
        ).fetchone()
        assert lang_rows is not None
        assert lang_rows[0] == 0, "All active entities must have a non-NULL language value after Spec-102"


# ---------------------------------------------------------------------------
# TS-102-SMOKE-3: Incremental analysis with language changes
# ---------------------------------------------------------------------------


class TestIncrementalAnalysisWithLanguageChanges:
    """TS-102-SMOKE-3: Adding/removing language files updates the entity graph correctly.

    Requirement: 102-REQ-4.4
    """

    def test_adding_go_file_adds_entities(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Adding a Go file in run 2 adds Go entities without disrupting Python entities."""
        py_file = tmp_path / "app.py"
        py_file.write_text("class App:\n    def run(self):\n        pass\n")

        # Run 1: Python only
        result1 = analyze_codebase(tmp_path, entity_conn)
        py_entity_count_run1 = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'python' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]

        assert "python" in result1.languages_analyzed
        assert "go" not in result1.languages_analyzed

        # Add a Go file
        (tmp_path / "server.go").write_text(
            "package main\n\ntype Server struct{}\n\nfunc NewServer() *Server { return nil }\n"
        )

        # Run 2: Python + Go
        result2 = analyze_codebase(tmp_path, entity_conn)

        py_entity_count_run2 = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'python' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]

        # Python entity count unchanged
        assert py_entity_count_run2 == py_entity_count_run1, (
            "Python entity count must not change after adding a Go file"
        )

        # Go entities added
        go_entity_count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'go' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]
        assert go_entity_count > 0, "Go entities must be added in run 2"

        assert "python" in result2.languages_analyzed
        assert "go" in result2.languages_analyzed

    def test_removing_go_file_soft_deletes_go_entities(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Removing the Go file in run 3 soft-deletes Go entities; Python entities stay."""
        py_file = tmp_path / "app.py"
        go_file = tmp_path / "server.go"
        py_file.write_text("class App:\n    def run(self):\n        pass\n")
        go_file.write_text(
            "package main\n\ntype Server struct{}\n\nfunc NewServer() *Server { return nil }\n"
        )

        # Run 1: both files
        analyze_codebase(tmp_path, entity_conn)

        # Run 2: remove Go file
        go_file.unlink()
        result3 = analyze_codebase(tmp_path, entity_conn)

        # Go entities must be soft-deleted
        go_active = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'go' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]
        assert go_active == 0, "All Go entities must be soft-deleted after file removal"

        go_deleted = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'go' AND deleted_at IS NOT NULL"
        ).fetchone()[0]  # type: ignore[index]
        assert go_deleted > 0, "Go entities must exist in soft-deleted state"

        # Python entities must remain active
        py_active = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'python' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]
        assert py_active > 0, "Python entities must remain active after Go file removal"

        assert result3.entities_soft_deleted >= 1
        assert "go" not in result3.languages_analyzed
        assert "python" in result3.languages_analyzed

    def test_full_incremental_cycle(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Full incremental cycle: add Python, add Go, remove Go — correct state at each step."""
        py_file = tmp_path / "app.py"
        go_file = tmp_path / "main.go"

        # Step 1: Python only
        py_file.write_text("def hello(): pass\n")
        r1 = analyze_codebase(tmp_path, entity_conn)
        assert "python" in r1.languages_analyzed
        assert r1.entities_upserted > 0

        # Step 2: Add Go file
        go_file.write_text("package main\nfunc main() {}\n")
        r2 = analyze_codebase(tmp_path, entity_conn)
        assert "python" in r2.languages_analyzed
        assert "go" in r2.languages_analyzed

        # Step 3: Remove Go file
        go_file.unlink()
        r3 = analyze_codebase(tmp_path, entity_conn)
        assert "python" in r3.languages_analyzed
        assert "go" not in r3.languages_analyzed
        assert r3.entities_soft_deleted >= 1

        # Final DB state: Python entities active, Go entities soft-deleted
        py_count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'python' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]
        go_count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_graph WHERE language = 'go' AND deleted_at IS NULL"
        ).fetchone()[0]  # type: ignore[index]

        assert py_count > 0, "Python entities must remain active at end of cycle"
        assert go_count == 0, "Go entities must be soft-deleted at end of cycle"
