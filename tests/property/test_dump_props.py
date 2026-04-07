"""Property tests for the dump command.

Test Spec: TS-49-P1, TS-49-P2, TS-49-P3
Properties: 3, 4, 5 from design.md
Requirements: 49-REQ-2.1, 49-REQ-2.2, 49-REQ-3.1, 49-REQ-3.2
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from pathlib import Path

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.dump import (
    discover_tables,
    dump_all_tables_json,
    dump_all_tables_md,
)
from agent_fox.knowledge.facts import Category
from agent_fox.knowledge.rendering import render_summary, render_summary_json
from tests.unit.knowledge.conftest import SCHEMA_DDL

# -- Strategies --------------------------------------------------------------

CATEGORIES = [c.value for c in Category]


@st.composite
def fact_row(draw: st.DrawFn) -> dict:
    """Generate a random fact row for insertion into DuckDB."""
    return {
        "id": str(uuid.uuid4()),
        "content": draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\x00",
                ),
                min_size=1,
                max_size=100,
            )
        ),
        "category": draw(st.sampled_from(CATEGORIES)),
        "spec_name": draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                ),
                min_size=1,
                max_size=30,
            )
        ),
        "confidence": draw(st.sampled_from([0.9, 0.6, 0.3])),
    }


def _insert_facts(conn: duckdb.DuckDBPyConnection, facts: list[dict]) -> None:
    """Insert fact dicts into the memory_facts table."""
    for fact in facts:
        conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, created_at)
            VALUES (?::UUID, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                fact["id"],
                fact["content"],
                fact["category"],
                fact["spec_name"],
                fact["confidence"],
            ],
        )


# -- TS-49-P1: Memory fact count preservation --------------------------------


class TestFactCountPreservation:
    """TS-49-P1: Markdown output has exactly one bullet per active fact.

    Property 3 from design.md.
    Requirement: 49-REQ-2.1
    """

    @given(facts=st.lists(fact_row(), min_size=1, max_size=50))
    @settings(max_examples=50, deadline=None)
    def test_fact_count_preservation(self, facts: list[dict]) -> None:
        """Number of bullet lines equals number of input facts."""
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        _insert_facts(conn, facts)

        with tempfile.TemporaryDirectory() as td:
            output_path = Path(td) / "memory.md"
            render_summary(conn, output_path)

            content = output_path.read_text()
            bullet_count = sum(1 for line in content.splitlines() if line.startswith("- "))
            assert bullet_count == len(facts)
        conn.close()


# -- TS-49-P2: Memory JSON key completeness ----------------------------------


class TestJsonKeyCompleteness:
    """TS-49-P2: Every fact in JSON output has all required keys.

    Property 4 from design.md.
    Requirement: 49-REQ-2.2
    """

    @given(facts=st.lists(fact_row(), min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_json_key_completeness(self, facts: list[dict]) -> None:
        """Every fact object has id, content, category, spec_name, confidence."""
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)
        _insert_facts(conn, facts)

        with tempfile.TemporaryDirectory() as td:
            output_path = Path(td) / "memory.json"
            render_summary_json(conn, output_path)

            data = json.loads(output_path.read_text())
            assert len(data["facts"]) == len(facts)
            required_keys = {"id", "content", "category", "spec_name", "confidence"}
            for fact_obj in data["facts"]:
                assert required_keys <= set(fact_obj.keys())
        conn.close()


# -- TS-49-P3: DB dump table coverage ----------------------------------------


# Strategy for valid SQL table names
table_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),  # type: ignore[arg-type]
    min_size=3,
    max_size=15,
).filter(
    lambda s: (
        s
        not in (
            "memory_facts",
            "schema_version",
            "memory_embeddings",
            "session_outcomes",
            "fact_causes",
            "tool_calls",
            "tool_errors",
            "review_findings",
            "verification_results",
            "drift_findings",
        )
    )
)


class TestTableCoverage:
    """TS-49-P3: Output contains exactly as many table sections as DB has tables.

    Property 5 from design.md.
    Requirements: 49-REQ-3.1, 49-REQ-3.2
    """

    @given(
        extra_tables=st.lists(
            table_name_strategy,
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_table_coverage_markdown(self, extra_tables: list[str]) -> None:
        """Markdown output has N '## table_name' headings."""
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        # Create additional tables
        for tname in extra_tables:
            conn.execute(f'CREATE TABLE "{tname}" (id INTEGER, val TEXT)')
            conn.execute(f"INSERT INTO \"{tname}\" VALUES (1, 'test')")

        tables = discover_tables(conn)

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "dump.md"
            dump_all_tables_md(conn, output)

            content = output.read_text()
            heading_count = len(re.findall(r"^## .+$", content, re.MULTILINE))
            assert heading_count == len(tables)
        conn.close()

    @given(
        extra_tables=st.lists(
            table_name_strategy,
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_table_coverage_json(self, extra_tables: list[str]) -> None:
        """JSON output has N keys in tables dict."""
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL)

        for tname in extra_tables:
            conn.execute(f'CREATE TABLE "{tname}" (id INTEGER, val TEXT)')
            conn.execute(f"INSERT INTO \"{tname}\" VALUES (1, 'test')")

        tables = discover_tables(conn)

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "dump.json"
            dump_all_tables_json(conn, output)

            data = json.loads(output.read_text())
            assert len(data["tables"]) == len(tables)
        conn.close()
