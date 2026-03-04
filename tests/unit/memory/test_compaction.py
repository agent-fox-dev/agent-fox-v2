"""Tests for knowledge base compaction: dedup and supersession.

Test Spec: TS-05-9 (dedup by content hash), TS-05-10 (supersession chain),
           TS-05-E6 (empty knowledge base)
Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.E1
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.memory.compaction import compact
from agent_fox.memory.store import load_all_facts, write_facts
from tests.unit.memory.conftest import make_fact


class TestCompactionDeduplicatesByContentHash:
    """TS-05-9: Compaction removes duplicates by content hash.

    Requirement: 05-REQ-5.1
    """

    def test_removes_duplicate_content(self, tmp_memory_path: Path) -> None:
        """Verify compaction removes facts with identical content."""
        early = make_fact(
            id="early-id",
            content="same content",
            created_at="2026-01-01T00:00:00+00:00",
        )
        late = make_fact(
            id="late-id",
            content="same content",
            created_at="2026-03-01T00:00:00+00:00",
        )

        write_facts([late, early], path=tmp_memory_path)
        original, surviving = compact(path=tmp_memory_path)

        assert original == 2
        assert surviving == 1

        facts = load_all_facts(path=tmp_memory_path)
        assert len(facts) == 1
        # Should keep the earliest by created_at
        assert facts[0].created_at == "2026-01-01T00:00:00+00:00"

    def test_keeps_facts_with_different_content(self, tmp_memory_path: Path) -> None:
        """Verify facts with different content are all kept."""
        fact_a = make_fact(id="a", content="content A")
        fact_b = make_fact(id="b", content="content B")

        write_facts([fact_a, fact_b], path=tmp_memory_path)
        original, surviving = compact(path=tmp_memory_path)

        assert original == 2
        assert surviving == 2


class TestCompactionSupersessionChain:
    """TS-05-10: Compaction resolves supersession chains.

    Requirement: 05-REQ-5.2
    """

    def test_chain_a_b_c_keeps_only_c(self, tmp_memory_path: Path) -> None:
        """Verify only the terminal fact in a chain survives."""
        a = make_fact(
            id="a-id",
            content="original fact",
            supersedes=None,
        )
        b = make_fact(
            id="b-id",
            content="updated fact",
            supersedes="a-id",
        )
        c = make_fact(
            id="c-id",
            content="final fact",
            supersedes="b-id",
        )

        write_facts([a, b, c], path=tmp_memory_path)
        original, surviving = compact(path=tmp_memory_path)

        assert surviving == 1
        facts = load_all_facts(path=tmp_memory_path)
        assert len(facts) == 1
        assert facts[0].id == "c-id"

    def test_single_supersession(self, tmp_memory_path: Path) -> None:
        """Verify a simple A->B supersession keeps only B."""
        a = make_fact(id="a-id", content="old", supersedes=None)
        b = make_fact(id="b-id", content="new", supersedes="a-id")

        write_facts([a, b], path=tmp_memory_path)
        original, surviving = compact(path=tmp_memory_path)

        assert surviving == 1
        facts = load_all_facts(path=tmp_memory_path)
        assert facts[0].id == "b-id"

    def test_independent_facts_not_affected(self, tmp_memory_path: Path) -> None:
        """Verify facts without supersession links are kept."""
        a = make_fact(id="a-id", content="fact A", supersedes=None)
        b = make_fact(id="b-id", content="fact B", supersedes=None)

        write_facts([a, b], path=tmp_memory_path)
        original, surviving = compact(path=tmp_memory_path)

        assert surviving == 2


class TestCompactionEmptyKnowledgeBase:
    """TS-05-E6: Compaction on empty knowledge base.

    Requirement: 05-REQ-5.E1
    """

    def test_nonexistent_file_returns_zero_zero(self, tmp_path: Path) -> None:
        """Verify compaction on nonexistent file returns (0, 0)."""
        path = tmp_path / "nonexistent.jsonl"
        original, surviving = compact(path=path)
        assert original == 0
        assert surviving == 0

    def test_empty_file_returns_zero_zero(self, tmp_memory_path: Path) -> None:
        """Verify compaction on empty file returns (0, 0)."""
        tmp_memory_path.write_text("")
        original, surviving = compact(path=tmp_memory_path)
        assert original == 0
        assert surviving == 0
