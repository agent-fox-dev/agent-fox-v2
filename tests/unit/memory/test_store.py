"""Tests for JSONL fact store: append, load, round-trip.

Test Spec: TS-05-4 (append/load round-trip), TS-05-5 (create file if missing),
           TS-05-12 (load by spec), TS-05-E4 (nonexistent file)
Requirements: 05-REQ-3.1, 05-REQ-3.3, 05-REQ-3.E1, 05-REQ-4.1, 05-REQ-4.E2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.memory.memory import (
    append_facts,
    load_all_facts,
    load_facts_by_spec,
)
from agent_fox.memory.types import Fact
from tests.unit.memory.conftest import make_fact


class TestStoreAppendAndLoadRoundTrip:
    """TS-05-4: Store append and load round-trip.

    Requirements: 05-REQ-3.1, 05-REQ-3.3
    """

    def test_append_and_load_three_facts(self, tmp_memory_path: Path) -> None:
        """Verify facts can be appended and loaded back identically."""
        fact_a = make_fact(id="a", content="Fact A", category="gotcha")
        fact_b = make_fact(id="b", content="Fact B", category="pattern")
        fact_c = make_fact(id="c", content="Fact C", category="decision")

        append_facts([fact_a, fact_b, fact_c], path=tmp_memory_path)
        loaded = load_all_facts(path=tmp_memory_path)

        assert len(loaded) == 3
        assert loaded[0].id == fact_a.id
        assert loaded[0].content == fact_a.content
        assert loaded[1].id == fact_b.id
        assert loaded[2].id == fact_c.id

    def test_append_preserves_all_fields(self, tmp_memory_path: Path) -> None:
        """Verify all fields survive the append/load cycle."""
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
        loaded = load_all_facts(path=tmp_memory_path)

        assert len(loaded) == 1
        restored = loaded[0]
        assert restored.id == fact.id
        assert restored.content == fact.content
        assert restored.category == fact.category
        assert restored.spec_name == fact.spec_name
        assert restored.keywords == fact.keywords
        assert restored.confidence == fact.confidence
        assert restored.created_at == fact.created_at
        assert restored.supersedes == fact.supersedes

    def test_multiple_appends_accumulate(self, tmp_memory_path: Path) -> None:
        """Verify multiple appends add to the file without overwriting."""
        fact_a = make_fact(id="a", content="First batch")
        fact_b = make_fact(id="b", content="Second batch")

        append_facts([fact_a], path=tmp_memory_path)
        append_facts([fact_b], path=tmp_memory_path)

        loaded = load_all_facts(path=tmp_memory_path)
        assert len(loaded) == 2
        assert loaded[0].id == "a"
        assert loaded[1].id == "b"


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
        loaded = load_all_facts(path=path)
        assert len(loaded) == 1
        assert loaded[0].id == "new-fact"


class TestLoadFactsBySpec:
    """TS-05-12: Load facts by spec name.

    Requirement: 05-REQ-4.1
    """

    def test_load_facts_by_spec_filters_correctly(
        self,
        tmp_memory_path: Path,
        sample_facts: list[Fact],
    ) -> None:
        """Verify load_facts_by_spec returns only matching facts."""
        append_facts(sample_facts, path=tmp_memory_path)

        result = load_facts_by_spec("spec_02", path=tmp_memory_path)

        assert len(result) == 1
        assert result[0].spec_name == "spec_02"

    def test_load_facts_by_spec_returns_empty_for_unknown(
        self,
        tmp_memory_path: Path,
        sample_facts: list[Fact],
    ) -> None:
        """Verify returns empty list when no facts match spec."""
        append_facts(sample_facts, path=tmp_memory_path)

        result = load_facts_by_spec("unknown_spec", path=tmp_memory_path)

        assert result == []


class TestLoadFromNonexistentFile:
    """TS-05-E4: Load from nonexistent memory file.

    Requirement: 05-REQ-4.E2
    """

    def test_load_from_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        """Verify loading from a nonexistent file returns empty list."""
        result = load_all_facts(path=tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_load_by_spec_from_nonexistent_file_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Verify load_facts_by_spec from nonexistent file returns empty."""
        result = load_facts_by_spec("spec_01", path=tmp_path / "nonexistent.jsonl")
        assert result == []
