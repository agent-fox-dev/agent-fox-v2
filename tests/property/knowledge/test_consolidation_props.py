"""Property tests for DuckDB round-trip, export-import, and compaction.

Test Spec: TS-39-P2, TS-39-P3, TS-39-P4
Requirements: 39-REQ-2.1, 39-REQ-3.2, 39-REQ-3.3
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.unit.knowledge.conftest import create_schema

# -- Strategies ---------------------------------------------------------------

fact_content_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=200,
)

category_st = st.sampled_from(
    ["gotcha", "pattern", "decision", "convention", "anti_pattern", "fragile_area"]
)

spec_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=30,
)

confidence_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

keyword_st = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
    min_size=0,
    max_size=5,
)


class TestDuckDBRoundTrip:
    """TS-39-P2: Facts survive DuckDB write-read round-trip."""

    @given(
        content=fact_content_st,
        category=category_st,
        spec_name_val=spec_name_st,
        confidence=confidence_st,
        keywords=keyword_st,
    )
    @settings(max_examples=30, deadline=None)
    def test_round_trip_fidelity(
        self,
        content: str,
        category: str,
        spec_name_val: str,
        confidence: float,
        keywords: list[str],
    ) -> None:
        from agent_fox.knowledge.facts import Fact
        from agent_fox.knowledge.store import MemoryStore, load_all_facts

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        tmp = Path(tempfile.mkdtemp()) / "memory.jsonl"
        store = MemoryStore(jsonl_path=tmp, db_conn=conn)

        fact = Fact(
            id=str(uuid.uuid4()),
            content=content,
            category=category,
            spec_name=spec_name_val,
            keywords=keywords,
            confidence=confidence,
            created_at="2026-01-01T00:00:00Z",
        )
        store.write_fact(fact)

        loaded = load_all_facts(conn)
        assert len(loaded) == 1
        assert loaded[0].content == content
        assert loaded[0].category == category
        assert loaded[0].spec_name == spec_name_val

        conn.close()


class TestExportImportRoundTrip:
    """TS-39-P3: Exported JSONL matches DuckDB contents."""

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=15, deadline=None)
    def test_export_matches_duckdb(self, n: int) -> None:
        from agent_fox.knowledge.facts import Fact
        from agent_fox.knowledge.store import (
            MemoryStore,
            export_facts_to_jsonl,
            load_all_facts,
        )

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        tmp = Path(tempfile.mkdtemp()) / "memory.jsonl"
        store = MemoryStore(jsonl_path=tmp, db_conn=conn)

        fact_ids = []
        for i in range(n):
            fid = str(uuid.uuid4())
            fact_ids.append(fid)
            fact = Fact(
                id=fid,
                content=f"Property fact {i}",
                category="decision",
                spec_name="prop_spec",
                keywords=["test"],
                confidence=0.9,
                created_at="2026-01-01T00:00:00Z",
            )
            store.write_fact(fact)

        count = export_facts_to_jsonl(conn, tmp)
        assert count == n

        # Parse JSONL and verify IDs match
        lines = tmp.read_text().strip().split("\n")
        assert len(lines) == n

        exported_ids = {json.loads(line)["id"] for line in lines}
        db_facts = load_all_facts(conn)
        db_ids = {f.id for f in db_facts}

        assert exported_ids == db_ids

        conn.close()


class TestCompactionMonotonicity:
    """TS-39-P4: Compaction never increases fact count."""

    @given(
        n_unique=st.integers(min_value=1, max_value=10),
        n_duplicates=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=20, deadline=None)
    def test_compaction_reduces_count(self, n_unique: int, n_duplicates: int) -> None:
        from agent_fox.knowledge.compaction import compact

        conn = duckdb.connect(":memory:")
        create_schema(conn)

        tmp = Path(tempfile.mkdtemp()) / "memory.jsonl"

        total = n_unique + n_duplicates

        # Insert unique facts
        for i in range(n_unique):
            conn.execute(
                """
                INSERT INTO memory_facts (id, content, category, spec_name,
                                          confidence, created_at)
                VALUES (?::UUID, ?, 'decision', 'spec', 0.9, CURRENT_TIMESTAMP)
                """,
                [str(uuid.uuid4()), f"Unique fact {i}"],
            )

        # Insert duplicates (same content as first unique fact)
        for i in range(n_duplicates):
            conn.execute(
                """
                INSERT INTO memory_facts (id, content, category, spec_name,
                                          confidence, created_at)
                VALUES (?::UUID, ?, 'decision', 'spec', 0.9, CURRENT_TIMESTAMP)
                """,
                [str(uuid.uuid4()), "Unique fact 0"],
            )

        original, surviving = compact(conn, tmp)
        assert original == total
        assert surviving <= original
        assert surviving >= n_unique  # at least the unique facts survive

        conn.close()
