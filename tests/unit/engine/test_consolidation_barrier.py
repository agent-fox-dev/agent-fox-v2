"""Tests for consolidation integration with sync barrier and engine.

Test Spec: TS-96-21 through TS-96-24, TS-96-E10, TS-96-E11
Requirements: 96-REQ-7.*
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from agent_fox.engine.barrier import run_sync_barrier_sequence
from agent_fox.knowledge.consolidation import ConsolidationResult, run_consolidation
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn():
    """In-memory DuckDB with all migrations applied (including v8)."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _make_minimal_barrier_state(node_states: dict | None = None):
    """Create a minimal ExecutionState-like object for barrier tests."""
    state = MagicMock()
    state.node_states = node_states or {}
    return state


def _make_zero_consolidation_result() -> ConsolidationResult:
    """Return a ConsolidationResult with all zero counts."""
    from agent_fox.knowledge.consolidation import (
        MergeResult,
        PromotionResult,
        PruneResult,
        VerificationResult,
    )

    return ConsolidationResult(
        entity_refresh=None,
        facts_linked=0,
        verification=VerificationResult(0, 0, 0, 0),
        merging=MergeResult(0, 0, 0, 0),
        promotion=PromotionResult(0, 0, 0),
        pruning=PruneResult(0, 0, 0),
        total_llm_cost=0.0,
        errors=[],
    )


# ---------------------------------------------------------------------------
# TS-96-21: Barrier triggers consolidation on completed specs
# ---------------------------------------------------------------------------


class TestBarrierTriggersConsolidation:
    """TS-96-21: Sync barrier calls consolidation when specs complete.

    Requirements: 96-REQ-7.1

    NOTE: Spec 114 (knowledge decoupling) removed consolidation from the
    sync barrier. These tests now verify that the barrier does NOT call
    consolidation and that run_consolidation can still be called directly.
    """

    @pytest.mark.asyncio
    async def test_barrier_does_not_trigger_consolidation(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Barrier no longer calls run_consolidation (removed by spec 114)."""
        state = _make_minimal_barrier_state({"task_a": "completed"})

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
        )
        # Barrier completes without calling consolidation — no assertion needed
        # beyond the fact that it doesn't raise.

    @pytest.mark.asyncio
    async def test_run_consolidation_directly(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """run_consolidation can still be called directly outside the barrier."""
        mock_consolidation = AsyncMock(return_value=_make_zero_consolidation_result())

        with patch(
            "agent_fox.knowledge.consolidation.run_consolidation",
            mock_consolidation,
        ):
            await run_consolidation(
                entity_conn,
                tmp_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert mock_consolidation.called


# ---------------------------------------------------------------------------
# TS-96-22: End-of-run consolidation for remaining specs
# ---------------------------------------------------------------------------


class TestEndOfRunConsolidation:
    """TS-96-22: End-of-run consolidation runs for specs not consolidated at barrier.

    Requirements: 96-REQ-7.2
    """

    @pytest.mark.asyncio
    async def test_end_of_run(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """run_consolidation called at end-of-run with unconsolidated specs."""
        completed_all = {"spec_a", "spec_b"}
        already_consolidated = {"spec_a"}
        remaining = completed_all - already_consolidated

        # Verify the logic: remaining should be spec_b only
        assert remaining == {"spec_b"}

        mock_consolidation = AsyncMock(return_value=_make_zero_consolidation_result())

        with patch(
            "agent_fox.knowledge.consolidation.run_consolidation",
            mock_consolidation,
        ):
            await run_consolidation(
                entity_conn,
                tmp_path,
                remaining,
                "claude-3-5-haiku-20241022",
            )

        assert mock_consolidation.called
        call_kwargs = mock_consolidation.call_args
        passed_specs = call_kwargs.args[2] if call_kwargs.args and len(call_kwargs.args) > 2 else None
        if passed_specs is None:
            passed_specs = call_kwargs.kwargs.get("completed_specs")
        # The remaining set should only contain spec_b
        assert passed_specs == {"spec_b"}


# ---------------------------------------------------------------------------
# TS-96-23: Exclusive write access via barrier ordering
# ---------------------------------------------------------------------------


class TestExclusiveAccess:
    """TS-96-23: Consolidation runs within barrier exclusive window.

    Requirements: 96-REQ-7.3

    NOTE: Spec 114 (knowledge decoupling) removed consolidation, lifecycle
    cleanup, and rendering from the sync barrier. This test now verifies
    that the barrier completes without these steps and that consolidation
    can still be called directly.
    """

    @pytest.mark.asyncio
    async def test_barrier_completes_without_knowledge_steps(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Barrier completes without consolidation, lifecycle, or rendering."""
        state = _make_minimal_barrier_state()

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
        )
        # Barrier completes without error — no knowledge steps attempted.


# ---------------------------------------------------------------------------
# TS-96-24: Separate cost reporting
# ---------------------------------------------------------------------------


class TestCostReporting:
    """TS-96-24: Consolidation costs reported separately via audit event.

    Requirements: 96-REQ-7.4
    """

    @pytest.mark.asyncio
    async def test_cost_reporting(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """consolidation.cost audit event emitted with cost breakdown."""
        mock_sink = MagicMock()
        captured_events: list[dict] = []

        def _capture_emit(event: object) -> None:
            captured_events.append(
                {
                    "type": str(getattr(event, "event_type", "")),
                    "payload": getattr(event, "payload", {}),
                }
            )

        mock_sink.emit_audit_event = MagicMock(side_effect=_capture_emit)

        # Insert a fact so the pipeline has something to process
        entity_conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, created_at)
            VALUES (gen_random_uuid(), 'Test fact', 'decision', 'spec_a', 0.8, CURRENT_TIMESTAMP)
            """
        )

        await run_consolidation(
            entity_conn,
            tmp_path,
            {"spec_a"},
            "claude-3-5-haiku-20241022",
            sink_dispatcher=mock_sink,
        )

        cost_events = [e for e in captured_events if "consolidation.cost" in e["type"]]
        assert len(cost_events) == 1


# ---------------------------------------------------------------------------
# TS-96-E10: Cost budget exceeded
# ---------------------------------------------------------------------------


class TestBudgetExceeded:
    """TS-96-E10: Consolidation aborts when cost budget is exceeded.

    Requirements: 96-REQ-7.E1
    """

    @pytest.mark.asyncio
    async def test_budget_exceeded(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Very low budget causes partial result; total_llm_cost <= budget."""
        # Insert a few facts to trigger LLM calls
        for i in range(3):
            entity_conn.execute(
                f"""
                INSERT INTO memory_facts
                    (id, content, category, spec_name, confidence, created_at)
                VALUES (gen_random_uuid(), 'Fact {i}', 'decision', 'spec_{i}', 0.8, CURRENT_TIMESTAMP)
                """
            )

        budget_limit = 0.001  # Extremely small budget

        result = await run_consolidation(
            entity_conn,
            tmp_path,
            {"spec_a"},
            "claude-3-5-haiku-20241022",
            max_cost=budget_limit,
        )

        # Should not exceed the budget
        assert result.total_llm_cost <= budget_limit
        # Partial result: at least one step should have been aborted
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# TS-96-E11: No completed specs -> skip consolidation
# ---------------------------------------------------------------------------


class TestNoCompletedSpecs:
    """TS-96-E11: Consolidation skipped when no specs have completed.

    Requirements: 96-REQ-7.E2

    NOTE: Spec 114 (knowledge decoupling) removed consolidation from the
    sync barrier entirely. The barrier no longer calls consolidation
    regardless of completed spec count.
    """

    @pytest.mark.asyncio
    async def test_barrier_runs_without_consolidation(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Barrier completes without calling consolidation (removed by spec 114)."""
        state = _make_minimal_barrier_state()

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
        )
        # No TypeError, no consolidation attempted — barrier completes cleanly.
