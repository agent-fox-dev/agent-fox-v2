"""Tests for block budget and skeptic/oracle blocking integration.

Covers:
- Block budget: run stops when blocked fraction exceeds max_blocked_fraction
- Block budget disabled by default (None)
- Skeptic blocking: critical findings above threshold block downstream tasks
- Oracle blocking: drift findings above threshold block downstream tasks
- Oracle advisory mode: no blocking when block_threshold is None
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.core.config import (
    ArchetypesConfig,
    OrchestratorConfig,
    ReviewerConfig,
)
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.state import RunStatus

from .conftest import (
    MockSessionOutcome,
    MockSessionRunner,
    write_plan_to_db,
)


def _wide_plan(n: int = 5) -> duckdb.DuckDBPyConnection:
    """Create a plan with n independent tasks (no dependencies)."""
    nodes = {f"spec_{i}:1": {"title": f"Task {i}"} for i in range(n)}
    return write_plan_to_db(nodes=nodes, edges=[])


def _chain_with_reviewer() -> duckdb.DuckDBPyConnection:
    """Create a plan: reviewer:pre-review -> coder -> verifier.

    reviewer node: spec_a:0:reviewer:pre-review
    coder node: spec_a:1
    verifier node: spec_a:1:verifier
    """
    return write_plan_to_db(
        nodes={
            "spec_a:0:reviewer:pre-review": {
                "title": "Reviewer (pre-review)",
                "spec_name": "spec_a",
                "group_number": 0,
                "archetype": "reviewer",
                "mode": "pre-review",
            },
            "spec_a:1": {
                "title": "Implement spec_a",
                "spec_name": "spec_a",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec_a:1:verifier": {
                "title": "Verify spec_a",
                "spec_name": "spec_a",
                "group_number": 1,
                "archetype": "verifier",
            },
        },
        edges=[
            {
                "source": "spec_a:0:reviewer:pre-review",
                "target": "spec_a:1",
                "kind": "intra_spec",
            },
            {
                "source": "spec_a:1",
                "target": "spec_a:1:verifier",
                "kind": "intra_spec",
            },
        ],
        order=["spec_a:0:reviewer:pre-review", "spec_a:1", "spec_a:1:verifier"],
    )


# -- Block Budget Tests -----------------------------------------------


class TestBlockBudget:
    """Tests for the max_blocked_fraction feature."""

    @pytest.mark.asyncio
    async def test_block_budget_disabled_by_default(
        self,
    ) -> None:
        """With default config (None), blocking never triggers budget."""
        db_conn = _wide_plan(n=5)

        runner = MockSessionRunner()
        # All tasks fail
        for i in range(5):
            runner.configure(
                f"spec_{i}:1",
                [MockSessionOutcome(f"spec_{i}:1", "failed", error_message="err")],
            )

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            max_retries=0,
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            knowledge_db_conn=db_conn,
        )

        state = await orch.run()

        # All blocked but run_status should be STALLED not BLOCK_LIMIT
        assert state.run_status != RunStatus.BLOCK_LIMIT

    @pytest.mark.asyncio
    async def test_block_budget_triggers_early_stop(
        self,
    ) -> None:
        """Run stops with BLOCK_LIMIT when blocked fraction exceeds budget."""
        db_conn = _wide_plan(n=4)

        runner = MockSessionRunner()
        # First two tasks fail (and block), last two succeed
        runner.configure(
            "spec_0:1",
            [MockSessionOutcome("spec_0:1", "failed", error_message="err")],
        )
        runner.configure(
            "spec_1:1",
            [MockSessionOutcome("spec_1:1", "failed", error_message="err")],
        )
        # spec_2 and spec_3 would succeed but shouldn't run

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            max_retries=0,
            max_blocked_fraction=0.4,  # 40% threshold
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            knowledge_db_conn=db_conn,
        )

        state = await orch.run()

        assert state.run_status == RunStatus.BLOCK_LIMIT
        # At least 2 of 4 tasks should be blocked (50% >= 40%)
        blocked = sum(1 for s in state.node_states.values() if s == "blocked")
        assert blocked >= 2

    @pytest.mark.asyncio
    async def test_block_budget_not_triggered_below_threshold(
        self,
    ) -> None:
        """Run continues when blocked fraction is below budget."""
        db_conn = _wide_plan(n=5)

        runner = MockSessionRunner()
        # Only one task fails
        runner.configure(
            "spec_0:1",
            [MockSessionOutcome("spec_0:1", "failed", error_message="err")],
        )

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            max_retries=0,
            max_blocked_fraction=0.5,  # 50% threshold
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            knowledge_db_conn=db_conn,
        )

        state = await orch.run()

        # 1/5 = 20% < 50%, should not trigger block limit
        assert state.run_status != RunStatus.BLOCK_LIMIT


# -- Skeptic Blocking Tests --------------------------------------------


class TestSkepticBlocking:
    """Tests for skeptic/oracle blocking integration in the engine."""

    @pytest.mark.asyncio
    async def test_reviewer_blocks_coder_on_critical_findings(
        self,
    ) -> None:
        """When skeptic finds criticals above threshold, coder is blocked.

        Uses the legacy skeptic archetype (no retry_predecessor) to test
        permanent blocking. Pre-review mode now has retry_predecessor=True
        and converts blocks to retries instead.
        """
        db_conn = write_plan_to_db(
            nodes={
                "spec_a:1:skeptic": {
                    "title": "Skeptic Review",
                    "spec_name": "spec_a",
                    "group_number": 1,
                    "archetype": "skeptic",
                },
                "spec_a:1": {
                    "title": "Implement spec_a",
                    "spec_name": "spec_a",
                    "group_number": 1,
                    "archetype": "coder",
                },
                "spec_a:1:verifier": {
                    "title": "Verify spec_a",
                    "spec_name": "spec_a",
                    "group_number": 1,
                    "archetype": "verifier",
                },
            },
            edges=[
                {"source": "spec_a:1", "target": "spec_a:1:skeptic", "kind": "intra_spec"},
                {"source": "spec_a:1", "target": "spec_a:1:verifier", "kind": "intra_spec"},
            ],
            order=["spec_a:1", "spec_a:1:skeptic", "spec_a:1:verifier"],
        )

        runner = MockSessionRunner()
        runner.configure(
            "spec_a:1",
            [MockSessionOutcome("spec_a:1", "completed", archetype="coder")],
        )
        runner.configure(
            "spec_a:1:skeptic",
            [MockSessionOutcome("spec_a:1:skeptic", "completed", archetype="skeptic")],
        )

        mock_findings = []
        for i in range(4):
            finding = MagicMock()
            finding.severity = "critical"
            finding.description = f"Critical issue {i}"
            mock_findings.append(finding)

        archetypes_config = ArchetypesConfig(
            reviewer_config=ReviewerConfig(pre_review_block_threshold=3),
        )

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            archetypes_config=archetypes_config,
            knowledge_db_conn=db_conn,
        )

        with patch(
            "agent_fox.knowledge.review_store.query_findings_by_session",
            return_value=mock_findings,
        ):
            state = await orch.run()

        # Coder should be blocked
        assert state.node_states["spec_a:1"] == "blocked"
        assert "spec_a:1" in state.blocked_reasons
        assert "critical" in state.blocked_reasons["spec_a:1"].lower()
        # Verifier should be cascade-blocked
        assert state.node_states["spec_a:1:verifier"] == "blocked"

    @pytest.mark.asyncio
    async def test_reviewer_does_not_block_below_threshold(
        self,
    ) -> None:
        """When critical count <= threshold, coder proceeds normally."""
        db_conn = _chain_with_reviewer()

        runner = MockSessionRunner()
        runner.configure(
            "spec_a:0:reviewer:pre-review",
            [
                MockSessionOutcome(
                    "spec_a:0:reviewer:pre-review",
                    "completed",
                    archetype="reviewer",
                )
            ],
        )
        # Coder and verifier succeed
        runner.configure(
            "spec_a:1",
            [MockSessionOutcome("spec_a:1", "completed")],
        )
        runner.configure(
            "spec_a:1:verifier",
            [MockSessionOutcome("spec_a:1:verifier", "completed")],
        )

        # Only 2 criticals (threshold is 3)
        mock_findings = []
        for i in range(2):
            finding = MagicMock()
            finding.severity = "critical"
            mock_findings.append(finding)

        archetypes_config = ArchetypesConfig(
            reviewer_config=ReviewerConfig(pre_review_block_threshold=3),
        )

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            archetypes_config=archetypes_config,
            knowledge_db_conn=db_conn,
        )

        with patch(
            "agent_fox.knowledge.review_store.query_findings_by_session",
            return_value=mock_findings,
        ):
            state = await orch.run()

        # Coder should have run and completed
        assert state.node_states["spec_a:1"] == "completed"

    @pytest.mark.asyncio
    async def test_drift_review_advisory_mode_does_not_block(
        self,
    ) -> None:
        """Drift-review with block_threshold=None is advisory-only."""
        db_conn = write_plan_to_db(
            nodes={
                "spec_a:0:reviewer:drift-review": {
                    "title": "Reviewer (drift-review)",
                    "spec_name": "spec_a",
                    "group_number": 0,
                    "archetype": "reviewer",
                    "mode": "drift-review",
                },
                "spec_a:1": {
                    "title": "Implement",
                    "spec_name": "spec_a",
                    "group_number": 1,
                    "archetype": "coder",
                },
            },
            edges=[
                {
                    "source": "spec_a:0:reviewer:drift-review",
                    "target": "spec_a:1",
                    "kind": "intra_spec",
                },
            ],
            order=["spec_a:0:reviewer:drift-review", "spec_a:1"],
        )

        runner = MockSessionRunner()
        runner.configure(
            "spec_a:0:reviewer:drift-review",
            [
                MockSessionOutcome(
                    "spec_a:0:reviewer:drift-review",
                    "completed",
                    archetype="reviewer",
                )
            ],
        )
        runner.configure(
            "spec_a:1",
            [MockSessionOutcome("spec_a:1", "completed")],
        )

        # Many criticals but drift-review is advisory (threshold=None)
        mock_findings = [MagicMock(severity="critical") for _ in range(10)]
        archetypes_config = ArchetypesConfig(
            reviewer_config=ReviewerConfig(drift_review_block_threshold=None),
        )

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            archetypes_config=archetypes_config,
            knowledge_db_conn=db_conn,
        )

        with patch(
            "agent_fox.knowledge.review_store.query_findings_by_session",
            return_value=mock_findings,
        ):
            state = await orch.run()

        # Coder should still complete despite critical findings
        assert state.node_states["spec_a:1"] == "completed"

    @pytest.mark.asyncio
    async def test_no_blocking_without_knowledge_db(
        self,
    ) -> None:
        """Without a knowledge DB connection, reviewer blocking is skipped."""
        db_conn = _chain_with_reviewer()

        runner = MockSessionRunner()
        runner.configure(
            "spec_a:0:reviewer:pre-review",
            [
                MockSessionOutcome(
                    "spec_a:0:reviewer:pre-review",
                    "completed",
                    archetype="reviewer",
                )
            ],
        )
        runner.configure(
            "spec_a:1",
            [MockSessionOutcome("spec_a:1", "completed")],
        )
        runner.configure(
            "spec_a:1:verifier",
            [MockSessionOutcome("spec_a:1:verifier", "completed")],
        )

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            sync_interval=0,
            hot_load=False,
        )
        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: runner,
            knowledge_db_conn=db_conn,
        )

        state = await orch.run()

        # Everything should complete normally
        assert state.node_states["spec_a:1"] == "completed"
