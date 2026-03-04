"""Tests for causal graph traversal.

Test Spec: TS-13-5 through TS-13-8
Requirements: 13-REQ-3.4
"""

from __future__ import annotations

import duckdb

from agent_fox.knowledge.causal import traverse_causal_chain
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    FACT_DDD,
    FACT_EEE,
)


class TestTraverseCausalChainForward:
    """TS-13-5: Traverse causal chain forward.

    Requirement: 13-REQ-3.4
    """

    def test_traverses_full_downstream_chain(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Traversing effects from aaa returns the full chain."""
        chain = traverse_causal_chain(causal_db, fact_id=FACT_AAA, direction="effects")
        assert len(chain) == 4
        depths = {f.fact_id: f.depth for f in chain}
        assert depths[FACT_AAA] == 0
        assert depths[FACT_BBB] == 1
        assert depths[FACT_CCC] == 2
        assert depths[FACT_EEE] == 1


class TestTraverseCausalChainBackward:
    """TS-13-6: Traverse causal chain backward.

    Requirement: 13-REQ-3.4
    """

    def test_traverses_upstream_chain(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Traversing causes from ccc returns the upstream chain."""
        chain = traverse_causal_chain(causal_db, fact_id=FACT_CCC, direction="causes")
        assert len(chain) == 3
        depths = {f.fact_id: f.depth for f in chain}
        assert depths[FACT_CCC] == 0
        assert depths[FACT_BBB] == -1
        assert depths[FACT_AAA] == -2


class TestTraverseRespectsMaxDepth:
    """TS-13-7: Traverse respects max depth.

    Requirement: 13-REQ-3.4
    """

    def test_excludes_facts_beyond_max_depth(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Traversal with max_depth=1 excludes ccc (depth 2)."""
        chain = traverse_causal_chain(
            causal_db, fact_id=FACT_AAA, max_depth=1, direction="effects"
        )
        fact_ids = {f.fact_id for f in chain}
        assert FACT_AAA in fact_ids
        assert FACT_BBB in fact_ids
        assert FACT_EEE in fact_ids
        assert FACT_CCC not in fact_ids


class TestTraverseIsolatedFact:
    """TS-13-8: Traverse isolated fact returns only itself.

    Requirement: 13-REQ-3.4
    """

    def test_isolated_fact_returns_self_only(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """A fact with no causal links returns only itself."""
        chain = traverse_causal_chain(causal_db, fact_id=FACT_DDD)
        assert len(chain) == 1
        assert chain[0].fact_id == FACT_DDD
        assert chain[0].depth == 0
        assert chain[0].relationship == "root"
