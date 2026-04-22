"""Tests for context enhancement with causal facts and fact provenance.

Test Spec: TS-13-17, TS-13-18, TS-13-19
Requirements: 13-REQ-1.1, 13-REQ-1.2, 13-REQ-7.1, 13-REQ-7.2

Note: Causal traversal was removed in spec 114 (knowledge decoupling).
select_context_with_causal now returns keyword_facts trimmed to max_facts.
"""

from __future__ import annotations

import duckdb

from agent_fox.session.prompt import select_context_with_causal
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_EEE,
)


class TestContextEnhancementAddsCausal:
    """TS-13-17: Context enhancement returns keyword facts (causal removed by spec 114).

    Requirements: 13-REQ-7.1, 13-REQ-7.2 (causal portions removed)
    """

    def test_returns_keyword_facts(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """Context includes keyword fact aaa; causal traversal removed by spec 114."""
        result = select_context_with_causal(
            causal_db,
            "07_oauth",
            ["src/auth/user.py"],
            keyword_facts=[{"id": FACT_AAA, "content": "User.email changed"}],
            max_facts=50,
            causal_budget=10,
        )
        result_ids = {f["id"] for f in result}
        assert FACT_AAA in result_ids
        assert len(result) <= 50

    def test_total_does_not_exceed_max_facts(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """Total returned facts do not exceed max_facts."""
        result = select_context_with_causal(
            causal_db,
            "07_oauth",
            ["src/auth/user.py"],
            keyword_facts=[{"id": FACT_AAA, "content": "User.email changed"}],
            max_facts=50,
            causal_budget=10,
        )
        assert len(result) <= 50


class TestContextEnhancementRespectsBudget:
    """TS-13-18: Context enhancement respects budget.

    Requirement: 13-REQ-7.2
    """

    def test_budget_with_many_keyword_facts(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """Even with 45 keyword facts and causal links, total <= 50."""
        keyword_facts = [{"id": f"kw_{i:08d}-0000-0000-0000-000000000000", "content": f"fact {i}"} for i in range(45)]
        result = select_context_with_causal(
            causal_db,
            "test_spec",
            [],
            keyword_facts=keyword_facts,
            max_facts=50,
            causal_budget=10,
        )
        assert len(result) <= 50


class TestFactProvenance:
    """TS-13-19: Fact provenance populated on storage.

    Requirements: 13-REQ-1.1, 13-REQ-1.2
    """

    def test_provenance_fields_populated(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """Facts in memory_facts carry spec_name, session_id, commit_sha."""
        row = causal_db.execute(
            "SELECT spec_name, session_id, commit_sha FROM memory_facts WHERE id=?",
            [FACT_AAA],
        ).fetchone()
        assert row is not None
        assert row[0] == "07_oauth"
        assert row[1] == "07/3"
        assert row[2] == "a1b2c3d"

    def test_null_commit_sha_allowed(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """commit_sha can be NULL when provenance is unavailable."""
        row = causal_db.execute(
            "SELECT commit_sha FROM memory_facts WHERE id=?",
            [FACT_AAA.replace("a", "d")],  # FACT_DDD
        ).fetchone()
        assert row is not None
        assert row[0] is None
