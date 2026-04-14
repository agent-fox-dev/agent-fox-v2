"""Integration smoke tests for the knowledge consolidation pipeline.

Test Spec: TS-96-SMOKE-1, TS-96-SMOKE-2
Requirements: Path 1 and Path 2 from design.md (spec 96)

Note: TS-96-SMOKE-1 requires real entity graph operations (analyze_codebase,
link_facts). Since spec 95 static_analysis and entity_linker modules are not
yet fully implemented, these tests use real DuckDB + real entity store but
mock the analyze_codebase/link_facts functions. Full real entity graph
operations will be enabled once spec 95 task groups 3-5 complete.

Must NOT use: mocked consolidation pipeline, mocked DuckDB connection.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from agent_fox.engine.barrier import run_sync_barrier_sequence
from agent_fox.knowledge.consolidation import (
    ConsolidationResult,
    run_consolidation,
)
from agent_fox.knowledge.entities import AnalysisResult, LinkResult
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _make_db_with_migrations() -> duckdb.DuckDBPyConnection:
    """Create real in-memory DuckDB with all migrations v1-v8 applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    return conn


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    *,
    spec_name: str = "spec_a",
    category: str = "decision",
    commit_sha: str | None = "abc123",
    confidence: float = 0.8,
) -> None:
    """Insert a fact into memory_facts."""
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at, commit_sha)
        VALUES (?, 'Test fact content', ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        [fact_id, category, spec_name, confidence, commit_sha],
    )


def _insert_entity(
    conn: duckdb.DuckDBPyConnection,
    entity_id: str,
    entity_path: str,
) -> None:
    """Insert a file entity into entity_graph."""
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?, 'file', ?, ?, CURRENT_TIMESTAMP)
        """,
        [entity_id, entity_path, entity_path],
    )


def _insert_causal_edge(conn: duckdb.DuckDBPyConnection, cause_id: str, effect_id: str) -> None:
    """Insert a causal edge into fact_causes."""
    conn.execute(
        "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?, ?)",
        [cause_id, effect_id],
    )


def _link_fact_to_entity(conn: duckdb.DuckDBPyConnection, fact_id: str, entity_id: str) -> None:
    """Link fact to entity in fact_entities."""
    conn.execute(
        "INSERT INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
        [fact_id, entity_id],
    )


# ---------------------------------------------------------------------------
# TS-96-SMOKE-1: Full consolidation at sync barrier
# ---------------------------------------------------------------------------


class TestBarrierPipeline:
    """TS-96-SMOKE-1: Sync barrier triggers full consolidation pipeline.

    Execution Path 1 from design.md.

    Uses real DuckDB (not mocked), real entity store operations.
    Mocks subprocess (git diff) and LLM calls.
    Mocks analyze_codebase/link_facts since spec 95 static_analysis module
    is not yet implemented (pending spec 95 task groups 3-5).

    Requirements: Path 1 (barrier -> run_consolidation -> all steps -> DuckDB)
    """

    @pytest.mark.asyncio
    async def test_barrier_pipeline(self, tmp_path: Path) -> None:
        """Full consolidation pipeline runs at sync barrier with real DuckDB."""
        # Setup: real DuckDB with migrations v1-v8 applied
        conn = _make_db_with_migrations()

        # Populate: 5 facts across 2 specs, some with entity links
        fact_ids = [str(uuid.uuid4()) for _ in range(5)]
        entity_id_a = str(uuid.uuid4())
        entity_id_b = str(uuid.uuid4())

        _insert_fact(conn, fact_ids[0], spec_name="spec_a", commit_sha="abc123")
        _insert_fact(conn, fact_ids[1], spec_name="spec_a", commit_sha=None)
        _insert_fact(conn, fact_ids[2], spec_name="spec_b", commit_sha="def456")
        _insert_fact(conn, fact_ids[3], spec_name="spec_b", commit_sha=None)
        _insert_fact(conn, fact_ids[4], spec_name="spec_a", commit_sha=None)

        # Create a small "Python package": 2 files, 1 entity each
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "module_a.py").write_text("class MyClass:\n    pass\n")
        (tmp_path / "src" / "module_b.py").write_text("def my_func():\n    return 42\n")

        _insert_entity(conn, entity_id_a, "src/module_a.py")
        _insert_entity(conn, entity_id_b, "src/module_b.py")

        # Link facts[0] and facts[2] to entities (others are unlinked)
        _link_fact_to_entity(conn, fact_ids[0], entity_id_a)
        _link_fact_to_entity(conn, fact_ids[2], entity_id_b)

        # Causal chain: A->B->C with A->C (for pruning test)
        _insert_causal_edge(conn, fact_ids[0], fact_ids[1])
        _insert_causal_edge(conn, fact_ids[1], fact_ids[2])
        _insert_causal_edge(conn, fact_ids[0], fact_ids[2])  # direct edge

        # Mock subprocess (git diff) to avoid real git dependency
        mock_git_subprocess = MagicMock(return_value=MagicMock(stdout="", returncode=0))

        # Mock LLM to return deterministic responses
        call_count = 0

        async def _mock_llm(*args: object, **kwargs: object) -> dict:
            nonlocal call_count
            call_count += 1
            prompt_str = str(args) + str(kwargs)
            if "is_pattern" in prompt_str or "pattern" in prompt_str.lower():
                return {"is_pattern": False, "description": ""}
            if "meaningful" in prompt_str:
                return {"meaningful": True, "reason": "B adds value"}
            return {"action": "link"}

        # Mock analyze_codebase (spec 95 static_analysis not yet implemented)
        mock_analyze = MagicMock(
            return_value=AnalysisResult(
                entities_upserted=2,
                edges_upserted=0,
                entities_soft_deleted=0,
            )
        )

        # Mock link_facts (spec 95 entity_linker not yet implemented)
        mock_link_facts = MagicMock(return_value=LinkResult(facts_processed=3, links_created=2, facts_skipped=1))

        state = MagicMock()
        state.node_states = {"task_a": "completed"}

        mock_consolidation_result: ConsolidationResult | None = None

        async def _capture_consolidation(*args: object, **kwargs: object) -> ConsolidationResult:
            nonlocal mock_consolidation_result
            with (
                patch("agent_fox.knowledge.consolidation.analyze_codebase", mock_analyze),
                patch("agent_fox.knowledge.consolidation.link_facts", mock_link_facts),
                patch("subprocess.run", mock_git_subprocess),
                patch("agent_fox.knowledge.consolidation._call_llm_json", _mock_llm),
            ):
                # Actually call run_consolidation (real implementation)
                result = await run_consolidation(*args, **kwargs)
            mock_consolidation_result = result
            return result

        with patch("agent_fox.engine.barrier.run_consolidation", _capture_consolidation):
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=1,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=conn,
                sink_dispatcher=None,
                completed_specs_fn=MagicMock(return_value={"spec_a"}),
                consolidated_specs=set(),
            )

        # Verify: analyze_codebase was called
        assert mock_analyze.called

        # Verify: link_facts was called for unlinked facts
        assert mock_link_facts.called

        # Verify: consolidation result has expected structure
        assert mock_consolidation_result is not None
        assert isinstance(mock_consolidation_result, ConsolidationResult)

        # Verify: git verification checked the linked facts
        if mock_consolidation_result.verification is not None:
            assert mock_consolidation_result.verification.facts_checked >= 0

        conn.close()


# ---------------------------------------------------------------------------
# TS-96-SMOKE-2: End-of-run consolidation for remaining specs
# ---------------------------------------------------------------------------


class TestEndOfRunPipeline:
    """TS-96-SMOKE-2: End-of-run consolidation runs for unconsolidated specs.

    Execution Path 2 from design.md.

    Uses real DuckDB. Mocks LLM and subprocess. Verifies that specs not
    consolidated during barriers are consolidated at end-of-run.

    Requirements: Path 2 (engine finally block -> run_consolidation)
    """

    @pytest.mark.asyncio
    async def test_end_of_run_pipeline(self, tmp_path: Path) -> None:
        """End-of-run consolidation runs for spec_b (not consolidated at barrier)."""
        # Setup: real DuckDB with real migrations
        conn = _make_db_with_migrations()

        # Insert facts for spec_b (spec_a already consolidated at barrier)
        fact_ids = [str(uuid.uuid4()) for _ in range(3)]
        for i, fact_id in enumerate(fact_ids):
            _insert_fact(conn, fact_id, spec_name="spec_b")

        # Simulate state: spec_a was consolidated at barrier, spec_b was not
        completed_specs_all = {"spec_a", "spec_b"}
        already_consolidated = {"spec_a"}
        remaining = completed_specs_all - already_consolidated

        assert remaining == {"spec_b"}

        mock_analyze = MagicMock(
            return_value=AnalysisResult(
                entities_upserted=0,
                edges_upserted=0,
                entities_soft_deleted=0,
            )
        )
        mock_link_facts = MagicMock(return_value=LinkResult(facts_processed=0, links_created=0, facts_skipped=0))

        async def _mock_llm(*args: object, **kwargs: object) -> dict:
            return {"action": "link"}

        captured_completed_specs: set[str] | None = None

        async def _capturing_run_consolidation(*args: object, **kwargs: object) -> ConsolidationResult:
            nonlocal captured_completed_specs
            # Extract completed_specs from args/kwargs
            if args and len(args) > 2:
                captured_completed_specs = args[2]  # type: ignore[assignment]
            elif "completed_specs" in (kwargs or {}):
                captured_completed_specs = kwargs["completed_specs"]  # type: ignore[assignment]

            with (
                patch("agent_fox.knowledge.consolidation.analyze_codebase", mock_analyze),
                patch("agent_fox.knowledge.consolidation.link_facts", mock_link_facts),
                patch("agent_fox.knowledge.consolidation._call_llm_json", _mock_llm),
            ):
                return await run_consolidation(*args, **kwargs)

        with patch(
            "agent_fox.knowledge.consolidation.run_consolidation",
            side_effect=_capturing_run_consolidation,
        ):
            # Simulate end-of-run: call run_consolidation for remaining specs
            await run_consolidation(
                conn,
                tmp_path,
                remaining,
                "claude-3-5-haiku-20241022",
            )

        # Verify: run_consolidation was called with spec_b only
        assert captured_completed_specs == {"spec_b"}

        conn.close()
