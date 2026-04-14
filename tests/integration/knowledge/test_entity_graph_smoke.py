"""Integration smoke tests for entity graph execution paths.

Test Spec: TS-95-SMOKE-1 through TS-95-SMOKE-4
Requirements: All entity graph requirements (95-REQ-*)
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.entity_linker import link_facts
from agent_fox.knowledge.entity_query import find_related_facts
from agent_fox.knowledge.entity_store import (
    create_fact_entity_links,
    gc_stale_entities,
    upsert_edges,
    upsert_entities,
)
from agent_fox.knowledge.static_analysis import analyze_codebase

from agent_fox.knowledge.facts import Fact
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema + all migrations applied.

    Provides a real DuckDB connection with entity graph tables (via migration v8).
    """
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _make_file_entity(name: str, path: str) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=EntityType.FILE,
        entity_name=name,
        entity_path=path,
        created_at=datetime.now(tz=UTC).isoformat(),
        deleted_at=None,
    )


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    commit_sha: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at, commit_sha)
        VALUES (?, 'Smoke test fact', 'decision', 'test_spec', 0.9,
                CURRENT_TIMESTAMP, ?)
        """,
        [fact_id, commit_sha],
    )


# ---------------------------------------------------------------------------
# TS-95-SMOKE-1: Full codebase analysis end-to-end
# ---------------------------------------------------------------------------


class TestFullCodebaseAnalysis:
    """TS-95-SMOKE-1: Analyzing a small Python package populates entity graph.

    Execution Path 1 from design.md
    """

    def test_analysis_populates_entity_graph(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Real tree-sitter analysis of a Python package creates entities and edges."""
        # Set up a minimal Python package
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "models.py").write_text(
            """\
class User:
    def save(self) -> None:
        pass
"""
        )
        (pkg / "service.py").write_text(
            """\
from pkg.models import User


class Service:
    def create_user(self) -> User:
        return User()


def create_user() -> None:
    pass
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.entities_upserted >= 6, f"Expected >= 6 entities, got {result.entities_upserted}"
        assert result.edges_upserted >= 4, f"Expected >= 4 edges, got {result.edges_upserted}"

        entities = entity_conn.execute("SELECT entity_name FROM entity_graph").fetchall()
        names = {e[0] for e in entities}

        assert "User" in names, "Class entity 'User' should be present"
        assert "create_user" in names, "Function entity 'create_user' should be present"

    def test_analysis_creates_contains_edges(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """analyze_codebase creates contains edges from files to classes."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "models.py").write_text(
            """\
class User:
    def save(self) -> None:
        pass
"""
        )

        analyze_codebase(tmp_path, entity_conn)

        contains_edges = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE relationship = 'contains'"
        ).fetchone()[0]
        assert contains_edges > 0, "Contains edges should be created"


# ---------------------------------------------------------------------------
# TS-95-SMOKE-2: Fact-entity linking end-to-end
# ---------------------------------------------------------------------------


class TestFactEntityLinkingSmoke:
    """TS-95-SMOKE-2: Facts are linked to entities via git diff.

    Execution Path 2 from design.md
    """

    def test_link_facts_creates_fact_entity_rows(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """link_facts creates two fact_entities rows for two matching files."""
        # Populate entity graph with file entities
        foo = _make_file_entity("foo.py", "src/foo.py")
        bar = _make_file_entity("bar.py", "src/bar.py")
        foo_id = upsert_entities(entity_conn, [foo])[0]  # noqa: F841
        bar_id = upsert_entities(entity_conn, [bar])[0]  # noqa: F841

        # Insert fact
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id, commit_sha="abc123")

        fact = Fact(
            id=fact_id,
            content="Smoke test fact",
            category="decision",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            supersedes=None,
            session_id="test/1",
            commit_sha="abc123",
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/foo.py\nsrc/bar.py\n"

        with patch("subprocess.run", return_value=mock_result):
            result = link_facts(entity_conn, [fact], tmp_path)

        assert result.links_created == 2, f"Expected 2 links, got {result.links_created}"

        rows = entity_conn.execute("SELECT COUNT(*) FROM fact_entities WHERE fact_id = ?", [fact_id]).fetchone()[0]
        assert rows == 2, f"Expected 2 fact_entities rows, got {rows}"


# ---------------------------------------------------------------------------
# TS-95-SMOKE-3: Graph query for related facts end-to-end
# ---------------------------------------------------------------------------


class TestGraphQueryForRelatedFacts:
    """TS-95-SMOKE-3: Traversing from a file path returns associated facts.

    Execution Path 3 from design.md
    """

    def test_find_related_facts_returns_neighbor_facts(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """find_related_facts returns facts linked to file and neighboring entities."""
        # Set up entity graph
        file_entity = _make_file_entity("foo.py", "src/foo.py")
        class_entity = Entity(
            id=str(uuid.uuid4()),
            entity_type=EntityType.CLASS,
            entity_name="Foo",
            entity_path="src/foo.py",
            created_at=datetime.now(tz=UTC).isoformat(),
            deleted_at=None,
        )
        bar_entity = _make_file_entity("bar.py", "src/bar.py")

        file_id = upsert_entities(entity_conn, [file_entity])[0]
        class_id = upsert_entities(entity_conn, [class_entity])[0]
        bar_id = upsert_entities(entity_conn, [bar_entity])[0]

        # File contains class
        upsert_edges(
            entity_conn,
            [EntityEdge(source_id=file_id, target_id=class_id, relationship=EdgeType.CONTAINS)],
        )
        # bar.py imports foo.py
        upsert_edges(
            entity_conn,
            [EntityEdge(source_id=bar_id, target_id=file_id, relationship=EdgeType.IMPORTS)],
        )

        # Insert facts and link to entities
        f1_id = str(uuid.uuid4())
        f2_id = str(uuid.uuid4())
        f3_id = str(uuid.uuid4())
        _insert_fact(entity_conn, f1_id)
        _insert_fact(entity_conn, f2_id)
        _insert_fact(entity_conn, f3_id)

        create_fact_entity_links(entity_conn, f1_id, [file_id])
        create_fact_entity_links(entity_conn, f2_id, [class_id])
        create_fact_entity_links(entity_conn, f3_id, [bar_id])

        facts = find_related_facts(entity_conn, "src/foo.py", max_depth=1)
        fact_ids = {f.id for f in facts}

        assert f1_id in fact_ids, "F1 (linked to foo.py file entity) should be returned"
        assert f2_id in fact_ids, "F2 (linked to Foo class, contained by foo.py) should be returned"
        assert f3_id in fact_ids, "F3 (linked to bar.py, which imports foo.py) should be returned"


# ---------------------------------------------------------------------------
# TS-95-SMOKE-4: Garbage collection end-to-end
# ---------------------------------------------------------------------------


class TestGarbageCollectionSmoke:
    """TS-95-SMOKE-4: GC removes stale entities and cascades to edges and links.

    Execution Path 4 from design.md
    """

    def test_gc_removes_stale_preserves_active(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """GC removes E1 (stale) with its edges/links and preserves E2 (active)."""
        # E1: stale entity with edge and fact link
        e1 = _make_file_entity("stale.py", "src/stale.py")
        e2 = _make_file_entity("active.py", "src/active.py")
        e3 = _make_file_entity("other.py", "src/other.py")

        e1_id = upsert_entities(entity_conn, [e1])[0]
        e2_id = upsert_entities(entity_conn, [e2])[0]
        e3_id = upsert_entities(entity_conn, [e3])[0]

        # Edge from E1 to E3
        upsert_edges(
            entity_conn,
            [EntityEdge(source_id=e1_id, target_id=e3_id, relationship=EdgeType.CONTAINS)],
        )

        # Fact linked to E1
        fact_id = str(uuid.uuid4())
        _insert_fact(entity_conn, fact_id)
        create_fact_entity_links(entity_conn, fact_id, [e1_id])

        # Soft-delete E1 30 days ago
        old_ts = datetime.now(tz=UTC) - timedelta(days=30)
        entity_conn.execute(
            "UPDATE entity_graph SET deleted_at = ? WHERE id = ?",
            [old_ts, e1_id],
        )

        removed = gc_stale_entities(entity_conn, retention_days=7)

        assert removed == 1, f"Expected 1 entity removed, got {removed}"

        # E1 should be gone
        e1_row = entity_conn.execute("SELECT id FROM entity_graph WHERE id = ?", [e1_id]).fetchone()
        assert e1_row is None, "E1 should be removed by GC"

        # E2 should still be there
        e2_row = entity_conn.execute("SELECT id FROM entity_graph WHERE id = ?", [e2_id]).fetchone()
        assert e2_row is not None, "E2 (active) should not be removed by GC"

        # Edge referencing E1 should be gone
        edge_count = entity_conn.execute(
            "SELECT COUNT(*) FROM entity_edges WHERE source_id = ? OR target_id = ?",
            [e1_id, e1_id],
        ).fetchone()[0]
        assert edge_count == 0, "Edges referencing removed E1 should be cascade-deleted"

        # Fact link referencing E1 should be gone
        link_count = entity_conn.execute("SELECT COUNT(*) FROM fact_entities WHERE entity_id = ?", [e1_id]).fetchone()[
            0
        ]
        assert link_count == 0, "Fact links referencing removed E1 should be cascade-deleted"
