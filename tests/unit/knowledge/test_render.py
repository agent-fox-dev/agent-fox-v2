"""Tests for human-readable summary rendering via DuckDB.

Test Spec: TS-05-11 (markdown generation), TS-05-E7 (create docs dir),
           TS-05-E8 (empty knowledge base)
Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.E1, 05-REQ-6.E2
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.rendering import render_summary
from tests.unit.knowledge.conftest import create_schema


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    content: str,
    category: str,
    spec_name: str,
    confidence: float = 0.9,
) -> None:
    """Insert a fact into DuckDB for testing."""
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name,
                                  confidence, created_at)
        VALUES (?::UUID, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [str(uuid.uuid4()), content, category, spec_name, confidence],
    )


@pytest.fixture
def schema_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB connection with schema."""
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    yield conn  # type: ignore[misc]
    try:
        conn.close()
    except Exception:
        pass


class TestRenderMarkdownByCategory:
    """TS-05-11: Render generates markdown organized by category.

    Requirements: 05-REQ-6.1, 05-REQ-6.2
    """

    def test_renders_sections_by_category(self, schema_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify output has section headings for each populated category."""
        output_path = tmp_path / "docs" / "memory.md"

        _insert_fact(
            schema_conn,
            content="A gotcha about testing.",
            category="gotcha",
            spec_name="01_core_foundation",
        )
        _insert_fact(
            schema_conn,
            content="A useful pattern.",
            category="pattern",
            spec_name="02_planning_engine",
            confidence=0.6,
        )

        render_summary(conn=schema_conn, output_path=output_path)

        content = output_path.read_text()
        assert "## Gotchas" in content
        assert "## Patterns" in content

    def test_renders_fact_content_and_attribution(self, schema_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify each fact includes content, spec name, and confidence."""
        output_path = tmp_path / "docs" / "memory.md"

        _insert_fact(
            schema_conn,
            content="A gotcha about testing.",
            category="gotcha",
            spec_name="01_core_foundation",
            confidence=0.9,
        )

        render_summary(conn=schema_conn, output_path=output_path)

        content = output_path.read_text()
        assert "A gotcha about testing." in content
        assert "spec: 01_core_foundation" in content
        assert "confidence: 0.90" in content


class TestRenderCreatesDocsDir:
    """TS-05-E7: Render creates docs directory.

    Requirement: 05-REQ-6.E1
    """

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """Verify render creates the output directory if missing."""
        output_path = tmp_path / "docs" / "memory.md"

        # Ensure docs/ doesn't exist
        assert not output_path.parent.exists()

        # No conn means empty summary
        render_summary(conn=None, output_path=output_path)

        assert output_path.exists()


class TestRenderEmptyKnowledgeBase:
    """TS-05-E8: Render with empty knowledge base.

    Requirement: 05-REQ-6.E2
    """

    def test_renders_no_facts_message(self, schema_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify render produces 'no facts' summary when DB is empty."""
        output_path = tmp_path / "docs" / "memory.md"

        render_summary(conn=schema_conn, output_path=output_path)

        content = output_path.read_text()
        assert "No facts have been recorded yet" in content

    def test_renders_no_facts_when_fallbacks_empty(self, tmp_path: Path) -> None:
        """Verify render produces 'no facts' when conn is None and
        fallbacks find nothing.

        Patches the fallback paths so they point to non-existent files,
        ensuring read_all_facts returns an empty list.
        """
        from unittest.mock import patch

        output_path = tmp_path / "docs" / "memory.md"

        with patch(
            "agent_fox.knowledge.rendering.read_all_facts",
            return_value=[],
        ):
            render_summary(conn=None, output_path=output_path)

        content = output_path.read_text()
        assert "No facts have been recorded yet" in content
