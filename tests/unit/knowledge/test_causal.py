"""Tests for causal graph operations.

Test Spec: TS-13-1 through TS-13-8, TS-13-E1
Requirements: 13-REQ-3.1, 13-REQ-3.2, 13-REQ-3.3, 13-REQ-3.4,
              13-REQ-3.E1, 13-REQ-2.E2
"""

from __future__ import annotations

import duckdb

from agent_fox.knowledge.causal import (
    add_causal_link,
    get_causes,
    get_effects,
    traverse_causal_chain,
)
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    FACT_DDD,
    FACT_EEE,
)


class TestAddCausalLink:
    """TS-13-1: Add causal link succeeds.

    Requirement: 13-REQ-3.1
    """

    def test_add_link_between_existing_facts(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """A causal link between two existing facts is inserted."""
        result = add_causal_link(causal_db, cause_id=FACT_DDD, effect_id=FACT_AAA)
        assert result is True
        rows = causal_db.execute(
            "SELECT * FROM fact_causes WHERE cause_id=? AND effect_id=?",
            [FACT_DDD, FACT_AAA],
        ).fetchall()
        assert len(rows) == 1


class TestAddCausalLinkRejectsNonExistent:
    """TS-13-2: Add causal link rejects non-existent fact.

    Requirements: 13-REQ-3.1, 13-REQ-2.E2
    """

    def test_rejects_nonexistent_effect(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """A link referencing a non-existent effect_id is rejected."""
        nonexistent = "99999999-9999-9999-9999-999999999999"
        result = add_causal_link(causal_db, cause_id=FACT_AAA, effect_id=nonexistent)
        assert result is False
        rows = causal_db.execute(
            "SELECT * FROM fact_causes WHERE effect_id=?",
            [nonexistent],
        ).fetchall()
        assert len(rows) == 0

    def test_rejects_nonexistent_cause(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """A link referencing a non-existent cause_id is rejected."""
        nonexistent = "99999999-9999-9999-9999-999999999999"
        result = add_causal_link(causal_db, cause_id=nonexistent, effect_id=FACT_AAA)
        assert result is False


class TestGetCauses:
    """TS-13-3: Get direct causes.

    Requirement: 13-REQ-3.2
    """

    def test_returns_direct_causes(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Querying causes of bbb returns aaa."""
        causes = get_causes(causal_db, fact_id=FACT_BBB)
        assert len(causes) == 1
        assert causes[0].fact_id == FACT_AAA
        assert causes[0].content == "User.email changed to nullable"

    def test_returns_empty_for_root_fact(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """A root fact (aaa) has no causes."""
        causes = get_causes(causal_db, fact_id=FACT_AAA)
        assert len(causes) == 0


class TestGetEffects:
    """TS-13-4: Get direct effects.

    Requirement: 13-REQ-3.3
    """

    def test_returns_direct_effects(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Querying effects of aaa returns bbb and eee."""
        effects = get_effects(causal_db, fact_id=FACT_AAA)
        assert len(effects) == 2
        effect_ids = {e.fact_id for e in effects}
        assert FACT_BBB in effect_ids
        assert FACT_EEE in effect_ids

    def test_returns_empty_for_leaf_fact(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """A leaf fact (ccc) has no effects."""
        effects = get_effects(causal_db, fact_id=FACT_CCC)
        assert len(effects) == 0


class TestTraverseCausalChainForward:
    """TS-13-5: Traverse causal chain forward.

    Requirement: 13-REQ-3.4
    """

    def test_traverses_full_downstream_chain(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Traversing effects from aaa returns the full chain."""
        chain = traverse_causal_chain(
            causal_db, fact_id=FACT_AAA, direction="effects"
        )
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
        chain = traverse_causal_chain(
            causal_db, fact_id=FACT_CCC, direction="causes"
        )
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


class TestDuplicateCausalLinkIdempotent:
    """TS-13-E1: Duplicate causal link is idempotent.

    Requirement: 13-REQ-3.E1
    """

    def test_duplicate_link_no_error(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Inserting a duplicate link does not raise and returns False."""
        # aaa -> bbb already exists in seeded data
        result = add_causal_link(causal_db, FACT_AAA, FACT_BBB)
        assert result is False
        count = causal_db.execute(
            "SELECT COUNT(*) FROM fact_causes WHERE cause_id=? AND effect_id=?",
            [FACT_AAA, FACT_BBB],
        ).fetchone()
        assert count is not None
        assert count[0] == 1
