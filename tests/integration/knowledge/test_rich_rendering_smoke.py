"""Integration smoke tests for rich memory rendering.

Test Spec: TS-111-SMOKE-1, TS-111-SMOKE-2
Requirements: All 111-REQ-*
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.migrations import apply_pending_migrations
from agent_fox.knowledge.rendering import render_summary
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rich_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with full schema including entity graph tables."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    fact_id: str,
    content: str,
    category: str = "gotcha",
    spec_name: str = "test_spec",
    confidence: float = 0.90,
    created_at: str,
    superseded_by: str | None = None,
) -> None:
    """Insert a memory fact into the database."""
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name,
                                  confidence, created_at, superseded_by)
        VALUES (?::UUID, ?, ?, ?, ?, ?::TIMESTAMP, ?::UUID)
        """,
        [fact_id, content, category, spec_name, confidence, created_at, superseded_by],
    )


# ---------------------------------------------------------------------------
# TS-111-SMOKE-1: End-to-end rich rendering
# ---------------------------------------------------------------------------


class TestEndToEndRichRendering:
    """TS-111-SMOKE-1: Full rendering pipeline with seeded enrichment data.

    Requirements: All 111-REQ-*
    """

    def test_end_to_end_rich_rendering(
        self, rich_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Render 5 facts with causal links, entity associations, and supersession."""
        output_path = tmp_path / "memory.md"

        fact1_id = str(uuid.uuid4())
        fact2_id = str(uuid.uuid4())
        fact3_id = str(uuid.uuid4())
        fact4_id = str(uuid.uuid4())
        fact5_id = str(uuid.uuid4())
        old_fact_id = str(uuid.uuid4())
        entity1_id = str(uuid.uuid4())
        entity2_id = str(uuid.uuid4())
        entity3_id = str(uuid.uuid4())

        # Insert 5 active facts across 3 categories
        _insert_fact(
            rich_conn,
            fact_id=fact1_id,
            content="DuckDB gotcha about FK constraints",
            category="gotcha",
            confidence=0.90,
            created_at="2026-04-01T10:00:00",
        )
        _insert_fact(
            rich_conn,
            fact_id=fact2_id,
            content="Use asyncio.run for async CLI boundaries",
            category="pattern",
            confidence=0.85,
            created_at="2026-04-05T10:00:00",
        )
        _insert_fact(
            rich_conn,
            fact_id=fact3_id,
            content="Always run make check before commit",
            category="convention",
            confidence=0.80,
            created_at="2026-04-10T10:00:00",
        )
        _insert_fact(
            rich_conn,
            fact_id=fact4_id,
            content="Another gotcha about DuckDB ordering",
            category="gotcha",
            confidence=0.70,
            created_at="2026-04-12T10:00:00",
        )
        _insert_fact(
            rich_conn,
            fact_id=fact5_id,
            content="Third fact in gotcha category",
            category="gotcha",
            confidence=0.60,
            created_at="2026-04-13T10:00:00",
        )

        # Insert old superseded fact (not active -- superseded_by=fact1_id)
        _insert_fact(
            rich_conn,
            fact_id=old_fact_id,
            content="Old content that was superseded by fact1",
            category="gotcha",
            confidence=0.50,
            created_at="2026-03-01T10:00:00",
            superseded_by=fact1_id,
        )

        # Causal links: fact2 -> fact1, fact1 -> fact3
        rich_conn.execute(
            """
            INSERT INTO fact_causes (cause_id, effect_id)
            VALUES (?::UUID, ?::UUID), (?::UUID, ?::UUID)
            """,
            [fact2_id, fact1_id, fact1_id, fact3_id],
        )

        # Entity graph (lowercase 'file' per EntityType.FILE = "file")
        rich_conn.execute(
            """
            INSERT INTO entity_graph (id, entity_type, entity_name, entity_path)
            VALUES
                (?::UUID, 'file', 'db', 'agent_fox/knowledge/db.py'),
                (?::UUID, 'file', 'rendering', 'agent_fox/knowledge/rendering.py'),
                (?::UUID, 'file', 'migrations', 'agent_fox/knowledge/migrations.py')
            """,
            [entity1_id, entity2_id, entity3_id],
        )

        # Associate all 3 entities with fact1
        rich_conn.execute(
            """
            INSERT INTO fact_entities (fact_id, entity_id)
            VALUES (?::UUID, ?::UUID), (?::UUID, ?::UUID), (?::UUID, ?::UUID)
            """,
            [fact1_id, entity1_id, fact1_id, entity2_id, fact1_id, entity3_id],
        )

        render_summary(conn=rich_conn, output_path=output_path)

        assert output_path.exists()
        content = output_path.read_text()

        # Valid markdown
        assert content.startswith("# Agent-Fox Memory")

        # Summary header shows 5 active facts (old_fact_id is superseded, excluded)
        # Most recent active fact is fact5_id at 2026-04-13
        assert "_5 facts | last updated: 2026-04-13_" in content

        # Correct sort within gotcha category: fact1 (0.90) > fact4 (0.70) > fact5 (0.60)
        pos_fact1 = content.index("DuckDB gotcha about FK constraints")
        pos_fact4 = content.index("Another gotcha about DuckDB ordering")
        pos_fact5 = content.index("Third fact in gotcha category")
        assert pos_fact1 < pos_fact4 < pos_fact5

        # At least one fact has cause sub-bullet (fact1 is caused by fact2)
        assert "  - cause:" in content

        # At least one fact has files sub-bullet (fact1 has 3 entities)
        assert "  - files:" in content

        # At least one fact has replaces sub-bullet (fact1 superseded old_fact_id)
        assert "  - replaces:" in content

        # All facts have age indicators in their metadata
        assert "ago" in content


# ---------------------------------------------------------------------------
# TS-111-SMOKE-2: Rendering with empty enrichment tables
# ---------------------------------------------------------------------------


class TestRenderingEmptyEnrichments:
    """TS-111-SMOKE-2: Rendering with no enrichment data produces clean output.

    Requirement: 111-REQ-7.E1
    """

    def test_rendering_empty_enrichments(
        self, rich_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Render 3 facts with no causal links, entities, or superseded facts."""
        output_path = tmp_path / "memory.md"

        fact1_id = str(uuid.uuid4())
        fact2_id = str(uuid.uuid4())
        fact3_id = str(uuid.uuid4())

        _insert_fact(
            rich_conn,
            fact_id=fact1_id,
            content="First fact in gotcha",
            category="gotcha",
            confidence=0.90,
            created_at="2026-04-10T10:00:00",
        )
        _insert_fact(
            rich_conn,
            fact_id=fact2_id,
            content="Second fact in pattern",
            category="pattern",
            confidence=0.80,
            created_at="2026-04-09T10:00:00",
        )
        _insert_fact(
            rich_conn,
            fact_id=fact3_id,
            content="Third fact in gotcha",
            category="gotcha",
            confidence=0.70,
            created_at="2026-04-08T10:00:00",
        )

        render_summary(conn=rich_conn, output_path=output_path)

        assert output_path.exists()
        content = output_path.read_text()

        # All 3 facts are rendered
        assert "First fact in gotcha" in content
        assert "Second fact in pattern" in content
        assert "Third fact in gotcha" in content

        # No enrichment sub-bullets
        assert "  - cause:" not in content
        assert "  - effect:" not in content
        assert "  - files:" not in content
        assert "  - replaces:" not in content

        # Summary header shows 3 facts and most recent date
        assert "_3 facts | last updated: 2026-04-10_" in content

        # Correct sort within gotcha: First (0.90) before Third (0.70)
        pos_first = content.index("First fact in gotcha")
        pos_third = content.index("Third fact in gotcha")
        assert pos_first < pos_third
