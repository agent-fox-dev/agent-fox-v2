"""Verify that legacy retrieval functions have been removed.

These tests assert the desired *end state* after task group 4 removes
the old retrieval chain. They deliberately FAIL in the current state
(before group 4 removes the functions) because the functions are still
importable and present in the codebase.

Test Spec: TS-104-17, TS-104-18, TS-104-E8
Requirements: 104-REQ-6.1, 104-REQ-6.2, 104-REQ-6.3, 104-REQ-6.4, 104-REQ-6.E1
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-104-17: select_relevant_facts removed
# ---------------------------------------------------------------------------


class TestSelectRelevantFactsRemoved:
    """TS-104-17: select_relevant_facts is not importable.

    Requirements: 104-REQ-6.1
    """

    def test_select_relevant_facts_not_importable(self) -> None:
        """Importing select_relevant_facts from filtering.py must raise ImportError."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.knowledge.filtering import (  # type: ignore[attr-defined]
                select_relevant_facts,
            )

            # If import succeeded, the function still exists — force failure
            raise AssertionError(f"select_relevant_facts still importable: {select_relevant_facts}")

    def test_compute_relevance_score_not_importable(self) -> None:
        """_compute_relevance_score (helper) must also be removed."""
        module = importlib.import_module("agent_fox.knowledge.filtering")
        assert not hasattr(module, "_compute_relevance_score"), (
            "_compute_relevance_score should have been deleted from filtering.py"
        )


# ---------------------------------------------------------------------------
# TS-104-18: RankedFactCache removed
# ---------------------------------------------------------------------------


class TestRankedFactCacheRemoved:
    """TS-104-18: RankedFactCache and related functions not importable.

    Requirements: 104-REQ-6.4
    """

    def test_ranked_fact_cache_not_importable(self) -> None:
        """RankedFactCache must not be importable from agent_fox.engine.fact_cache."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.engine.fact_cache import (  # type: ignore[attr-defined]
                RankedFactCache,
            )

            raise AssertionError(f"RankedFactCache still importable: {RankedFactCache}")

    def test_precompute_fact_rankings_not_importable(self) -> None:
        """precompute_fact_rankings must not be importable from fact_cache."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.engine.fact_cache import (  # type: ignore[attr-defined]
                precompute_fact_rankings,
            )

            raise AssertionError(f"precompute_fact_rankings still importable: {precompute_fact_rankings}")

    def test_get_cached_facts_not_importable(self) -> None:
        """get_cached_facts must not be importable from fact_cache."""
        with pytest.raises((ImportError, AttributeError)):
            from agent_fox.engine.fact_cache import (  # type: ignore[attr-defined]
                get_cached_facts,
            )

            raise AssertionError(f"get_cached_facts still importable: {get_cached_facts}")


# ---------------------------------------------------------------------------
# TS-104-E8: No remaining imports of removed functions in agent_fox/
# ---------------------------------------------------------------------------


class TestNoLegacyImports:
    """TS-104-E8: No remaining references to removed functions in production code.

    Requirements: 104-REQ-6.E1
    """

    # Names that must not appear anywhere in agent_fox/**/*.py after removal
    _REMOVED_NAMES = [
        "select_relevant_facts",
        "enhance_with_causal",
        "_retrieve_cross_spec_facts",
        "RankedFactCache",
        "precompute_fact_rankings",
        "get_cached_facts",
        "export_facts_to_jsonl",
        "load_facts_from_jsonl",
        "MEMORY_PATH",
    ]

    def _find_references(self, name: str) -> list[str]:
        """Return list of 'file:line' strings where name appears in agent_fox/."""
        repo_root = Path(__file__).parent.parent.parent.parent
        agent_fox_dir = repo_root / "agent_fox"
        matches = []
        for py_file in sorted(agent_fox_dir.rglob("*.py")):
            for lineno, line in enumerate(py_file.read_text(errors="replace").splitlines(), 1):
                if name in line:
                    matches.append(f"{py_file.relative_to(repo_root)}:{lineno}: {line.strip()}")
        return matches

    def test_select_relevant_facts_not_referenced(self) -> None:
        """select_relevant_facts must not appear in any agent_fox/*.py file."""
        refs = self._find_references("select_relevant_facts")
        assert refs == [], "select_relevant_facts still referenced in production code:\n" + "\n".join(refs)

    def test_enhance_with_causal_not_referenced(self) -> None:
        """enhance_with_causal must not appear in any agent_fox/*.py file."""
        refs = self._find_references("enhance_with_causal")
        assert refs == [], "enhance_with_causal still referenced:\n" + "\n".join(refs)

    def test_ranked_fact_cache_not_referenced(self) -> None:
        """RankedFactCache must not appear in any agent_fox/*.py file."""
        refs = self._find_references("RankedFactCache")
        assert refs == [], "RankedFactCache still referenced:\n" + "\n".join(refs)

    def test_precompute_fact_rankings_not_referenced(self) -> None:
        """precompute_fact_rankings must not appear in any agent_fox/*.py file."""
        refs = self._find_references("precompute_fact_rankings")
        assert refs == [], "precompute_fact_rankings still referenced:\n" + "\n".join(refs)

    def test_export_facts_to_jsonl_not_referenced(self) -> None:
        """export_facts_to_jsonl must not appear in any agent_fox/*.py file."""
        refs = self._find_references("export_facts_to_jsonl")
        assert refs == [], "export_facts_to_jsonl still referenced:\n" + "\n".join(refs)

    def test_load_facts_from_jsonl_not_referenced(self) -> None:
        """load_facts_from_jsonl must not appear in any agent_fox/*.py file."""
        refs = self._find_references("load_facts_from_jsonl")
        assert refs == [], "load_facts_from_jsonl still referenced:\n" + "\n".join(refs)

    def test_memory_path_not_referenced(self) -> None:
        """MEMORY_PATH must not appear in any agent_fox/*.py file."""
        refs = self._find_references("MEMORY_PATH")
        assert refs == [], "MEMORY_PATH still referenced:\n" + "\n".join(refs)
