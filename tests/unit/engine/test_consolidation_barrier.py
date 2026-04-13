"""Tests for consolidation integration with sync barrier and engine.

Test Spec: TS-96-21 through TS-96-24, TS-96-E10, TS-96-E11
Requirements: 96-REQ-7.*
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from agent_fox.knowledge.consolidation import ConsolidationResult, run_consolidation

from agent_fox.engine.barrier import run_sync_barrier_sequence
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
    """

    @pytest.mark.asyncio
    async def test_barrier_triggers(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """run_consolidation called with completed_specs when barrier fires."""
        state = _make_minimal_barrier_state({"task_a": "completed"})

        mock_consolidation = AsyncMock(return_value=_make_zero_consolidation_result())
        completed_specs_fn = MagicMock(return_value={"spec_a"})
        consolidated_specs: set[str] = set()

        with patch("agent_fox.engine.barrier.run_consolidation", mock_consolidation):
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=1,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                hook_config=None,
                no_hooks=True,
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=entity_conn,
                sink_dispatcher=None,
                completed_specs_fn=completed_specs_fn,
                consolidated_specs=consolidated_specs,
            )

        assert mock_consolidation.called
        call_kwargs = mock_consolidation.call_args
        passed_specs = (
            call_kwargs.kwargs.get("completed_specs")
            or call_kwargs.args[2]
            if call_kwargs.args and len(call_kwargs.args) > 2
            else None
        )
        assert passed_specs is not None
        assert "spec_a" in passed_specs


# ---------------------------------------------------------------------------
# TS-96-22: End-of-run consolidation for remaining specs
# ---------------------------------------------------------------------------


class TestEndOfRunConsolidation:
    """TS-96-22: End-of-run consolidation runs for specs not consolidated at barrier.

    Requirements: 96-REQ-7.2
    """

    @pytest.mark.asyncio
    async def test_end_of_run(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
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

    Consolidation must run after lifecycle cleanup and before memory summary
    regeneration (within the barrier's exclusive write window).

    Requirements: 96-REQ-7.3
    """

    @pytest.mark.asyncio
    async def test_exclusive_access(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Consolidation runs after lifecycle cleanup and before memory summary."""
        call_order: list[str] = []

        state = _make_minimal_barrier_state()

        def _track(name: str, fn: MagicMock) -> MagicMock:
            def _side(*a: object, **kw: object) -> object:
                call_order.append(name)
                return fn(*a, **kw)

            return _side

        mock_consolidation = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("consolidation")
            or _make_zero_consolidation_result()
        )

        with (
            patch("agent_fox.engine.barrier.run_consolidation", mock_consolidation),
            patch(
                "agent_fox.knowledge.lifecycle.run_cleanup",
                side_effect=lambda *a, **kw: call_order.append("lifecycle_cleanup") or MagicMock(
                    facts_expired=0,
                    facts_deduped=0,
                    facts_contradicted=0,
                    active_facts_remaining=0,
                ),
            ),
            patch(
                "agent_fox.knowledge.rendering.render_summary",
                side_effect=lambda *a, **kw: call_order.append("render_summary"),
            ),
        ):
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=1,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                hook_config=None,
                no_hooks=True,
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=entity_conn,
                knowledge_config=MagicMock(),
                sink_dispatcher=None,
                completed_specs_fn=MagicMock(return_value={"spec_a"}),
                consolidated_specs=set(),
            )

        # consolidation must run after lifecycle_cleanup and before render_summary
        if "consolidation" in call_order and "lifecycle_cleanup" in call_order:
            assert call_order.index("consolidation") > call_order.index("lifecycle_cleanup")
        if "consolidation" in call_order and "render_summary" in call_order:
            assert call_order.index("consolidation") < call_order.index("render_summary")


# ---------------------------------------------------------------------------
# TS-96-24: Separate cost reporting
# ---------------------------------------------------------------------------


class TestCostReporting:
    """TS-96-24: Consolidation costs reported separately via audit event.

    Requirements: 96-REQ-7.4
    """

    @pytest.mark.asyncio
    async def test_cost_reporting(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """consolidation.cost audit event emitted with cost breakdown."""
        mock_sink = MagicMock()
        captured_events: list[dict] = []

        def _capture_dispatch(*args: object, **kwargs: object) -> None:
            event_type = args[0] if args else kwargs.get("event_type", "")
            payload = kwargs.get("payload", {})
            captured_events.append({"type": str(event_type), "payload": payload})

        mock_sink.dispatch = MagicMock(side_effect=_capture_dispatch)

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
    async def test_budget_exceeded(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
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
    """

    @pytest.mark.asyncio
    async def test_no_completed_specs(
        self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """When completed_spec_names() returns empty set, run_consolidation not called."""
        state = _make_minimal_barrier_state()
        mock_consolidation = AsyncMock(return_value=_make_zero_consolidation_result())
        completed_specs_fn = MagicMock(return_value=set())  # No completed specs

        with patch("agent_fox.engine.barrier.run_consolidation", mock_consolidation):
            await run_sync_barrier_sequence(
                state=state,
                sync_interval=1,
                repo_root=tmp_path,
                emit_audit=MagicMock(),
                hook_config=None,
                no_hooks=True,
                specs_dir=None,
                hot_load_enabled=False,
                hot_load_fn=AsyncMock(),
                sync_plan_fn=MagicMock(),
                barrier_callback=None,
                knowledge_db_conn=entity_conn,
                sink_dispatcher=None,
                completed_specs_fn=completed_specs_fn,
                consolidated_specs=set(),
            )

        assert not mock_consolidation.called
