"""Tests for JSONL fact store helpers and DuckDB-backed load functions.

Test Spec: TS-05-4 (append/load round-trip), TS-05-5 (create file if missing),
           TS-05-12 (load by spec), TS-05-E4 (nonexistent file)
Requirements: 05-REQ-3.1, 05-REQ-3.3, 05-REQ-3.E1, 05-REQ-4.1, 05-REQ-4.E2
"""

from __future__ import annotations

import pytest

pytest.skip("Legacy function removed per spec 104-REQ-6", allow_module_level=True)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from agent_fox.knowledge.store import (  # noqa: E402
    append_facts,
    write_facts,
)
from tests.unit.knowledge.conftest import make_fact  # noqa: E402


class TestStoreAppendAndLoadRoundTrip:
    """TS-05-4: Store append and load round-trip via JSONL.

    Requirements: 05-REQ-3.1, 05-REQ-3.3
    """

    def test_append_and_load_three_facts(self, tmp_memory_path: Path) -> None:
        """Verify facts can be appended and read back from JSONL."""
        fact_a = make_fact(id="a", content="Fact A", category="gotcha")
        fact_b = make_fact(id="b", content="Fact B", category="pattern")
        fact_c = make_fact(id="c", content="Fact C", category="decision")

        append_facts([fact_a, fact_b, fact_c], path=tmp_memory_path)

        # Verify JSONL content
        lines = tmp_memory_path.read_text().strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0])["id"] == "a"
        assert json.loads(lines[1])["id"] == "b"
        assert json.loads(lines[2])["id"] == "c"

    def test_append_preserves_all_fields(self, tmp_memory_path: Path) -> None:
        """Verify all fields survive the append cycle to JSONL."""
        fact = make_fact(
            id="full-uuid",
            content="Full fact content.",
            category="convention",
            spec_name="02_planning_engine",
            keywords=["planning", "graph", "resolver"],
            confidence=0.6,
            created_at="2026-02-15T12:00:00+00:00",
            supersedes="old-uuid",
        )

        append_facts([fact], path=tmp_memory_path)

        lines = tmp_memory_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["id"] == fact.id
        assert data["content"] == fact.content
        assert data["category"] == fact.category
        assert data["spec_name"] == fact.spec_name
        assert data["keywords"] == fact.keywords
        assert data["confidence"] == fact.confidence
        assert data["created_at"] == fact.created_at
        assert data["supersedes"] == fact.supersedes

    def test_multiple_appends_accumulate(self, tmp_memory_path: Path) -> None:
        """Verify multiple appends add to the file without overwriting."""
        fact_a = make_fact(id="a", content="First batch")
        fact_b = make_fact(id="b", content="Second batch")

        append_facts([fact_a], path=tmp_memory_path)
        append_facts([fact_b], path=tmp_memory_path)

        lines = tmp_memory_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == "a"
        assert json.loads(lines[1])["id"] == "b"


class TestStoreCreatesFileIfMissing:
    """TS-05-5: Store append creates file if missing.

    Requirement: 05-REQ-3.E1
    """

    def test_append_creates_file(self, tmp_path: Path) -> None:
        """Verify appending to a nonexistent file creates it."""
        path = tmp_path / "subdir" / "new_memory.jsonl"
        assert not path.exists()

        fact = make_fact(id="new-fact")
        append_facts([fact], path=path)

        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == "new-fact"


class TestWriteFactsOverwrite:
    """Test write_facts overwrites JSONL file."""

    def test_write_facts_overwrites(self, tmp_memory_path: Path) -> None:
        """Verify write_facts replaces file contents."""
        fact_a = make_fact(id="a", content="First")
        fact_b = make_fact(id="b", content="Second")

        append_facts([fact_a], path=tmp_memory_path)
        write_facts([fact_b], path=tmp_memory_path)

        lines = tmp_memory_path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == "b"
