"""Tests for duration-based ordering in graph_sync, config, and orchestrator.

Test Spec: TS-41-1, TS-41-2, TS-41-3, TS-41-4, TS-41-16, TS-41-17, TS-41-18
Edge Cases: TS-41-E1, TS-41-E2, TS-41-E6, TS-41-E7, TS-41-E8
Requirements: 41-REQ-1.1 through 41-REQ-1.E2, 41-REQ-5.1, 41-REQ-5.2,
              41-REQ-5.E1, 41-REQ-5.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# TS-41-1, TS-41-2, TS-41-3: order_by_duration()
# ---------------------------------------------------------------------------


class TestOrderByDuration:
    """Tests for the order_by_duration() sorting function.

    Test Spec: TS-41-1, TS-41-2, TS-41-3
    """

    def test_descending_duration_ordering(self) -> None:
        """TS-41-1: Tasks sorted by predicted duration descending.

        Requirement: 41-REQ-1.1
        """
        from agent_fox.routing.duration import order_by_duration

        result = order_by_duration(["a", "b", "c"], {"a": 100, "b": 500, "c": 300})
        assert result == ["b", "c", "a"]

    def test_alphabetical_tie_breaking(self) -> None:
        """TS-41-2: Alphabetical tie-breaking when durations are equal.

        Requirement: 41-REQ-1.2
        """
        from agent_fox.routing.duration import order_by_duration

        result = order_by_duration(
            ["alpha", "beta", "gamma"],
            {"alpha": 200, "beta": 200, "gamma": 500},
        )
        assert result == ["gamma", "alpha", "beta"]

    def test_tasks_without_hints_placed_last(self) -> None:
        """TS-41-3: Tasks without hints placed after hinted tasks.

        Requirement: 41-REQ-1.3
        """
        from agent_fox.routing.duration import order_by_duration

        result = order_by_duration(["d", "c", "b", "a"], {"a": 100, "c": 300})
        assert result == ["c", "a", "b", "d"]


# ---------------------------------------------------------------------------
# TS-41-4, TS-41-18: ready_tasks() with duration hints
# ---------------------------------------------------------------------------


class TestReadyTasksOrdering:
    """Tests for GraphSync.ready_tasks() with duration hints.

    Test Spec: TS-41-4, TS-41-18
    """

    def test_no_hints_returns_alphabetical(self) -> None:
        """TS-41-4: Alphabetical order when no duration hints provided.

        Requirement: 41-REQ-1.4
        """
        from agent_fox.engine.graph_sync import GraphSync

        gs = GraphSync({"c": "pending", "a": "pending", "b": "pending"}, {})
        result = gs.ready_tasks(duration_hints=None)
        assert result == ["a", "b", "c"]

    def test_duration_hints_passed_to_ready_tasks(self) -> None:
        """TS-41-18: ready_tasks uses duration hints for ordering.

        Requirement: 41-REQ-5.3
        """
        from agent_fox.engine.graph_sync import GraphSync

        gs = GraphSync({"a": "pending", "b": "pending", "c": "pending"}, {})
        result = gs.ready_tasks(duration_hints={"a": 500, "b": 100, "c": 300})
        assert result == ["a", "c", "b"]

    def test_empty_hints_dict_treated_as_none(self) -> None:
        """TS-41-E2: Empty hints dict treated as None (alphabetical).

        Requirement: 41-REQ-1.E2
        """
        from agent_fox.engine.graph_sync import GraphSync

        gs = GraphSync({"c": "pending", "a": "pending", "b": "pending"}, {})
        result = gs.ready_tasks(duration_hints={})
        assert result == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# TS-41-16: PlanningConfig Defaults
# ---------------------------------------------------------------------------


class TestPlanningConfig:
    """Tests for PlanningConfig duration-related fields.

    Test Spec: TS-41-16, TS-41-17
    """

    def test_planning_config_defaults(self) -> None:
        """TS-41-16: Default PlanningConfig values.

        Requirement: 41-REQ-5.1
        """
        from agent_fox.core.config import PlanningConfig

        config = PlanningConfig()
        assert config.duration_ordering is True
        assert config.min_outcomes_for_historical == 10
        assert config.min_outcomes_for_regression == 30

    def test_duration_ordering_disabled_returns_none(self) -> None:
        """TS-41-17: No duration hints computed when ordering is disabled.

        Requirement: 41-REQ-5.2

        Note: This test verifies the config flag. Full orchestrator integration
        is tested in task group 3.
        """
        from agent_fox.core.config import PlanningConfig

        config = PlanningConfig(duration_ordering=False)
        assert config.duration_ordering is False


# ---------------------------------------------------------------------------
# TS-41-E6, TS-41-E7: Config Clamping
# ---------------------------------------------------------------------------


class TestConfigClamping:
    """Tests for PlanningConfig value clamping.

    Test Spec: TS-41-E6, TS-41-E7
    """

    def test_historical_min_clamped_low(self) -> None:
        """TS-41-E6: min_outcomes_for_historical clamped to 1 when too low.

        Requirement: 41-REQ-5.E1
        """
        from agent_fox.core.config import PlanningConfig

        c = PlanningConfig(min_outcomes_for_historical=0)
        assert c.min_outcomes_for_historical == 1

    def test_historical_min_clamped_high(self) -> None:
        """TS-41-E6: min_outcomes_for_historical clamped to 1000 when too high.

        Requirement: 41-REQ-5.E1
        """
        from agent_fox.core.config import PlanningConfig

        c = PlanningConfig(min_outcomes_for_historical=5000)
        assert c.min_outcomes_for_historical == 1000

    def test_regression_min_clamped_low(self) -> None:
        """TS-41-E7: min_outcomes_for_regression clamped to 5 when too low.

        Requirement: 41-REQ-5.E1
        """
        from agent_fox.core.config import PlanningConfig

        c = PlanningConfig(min_outcomes_for_regression=2)
        assert c.min_outcomes_for_regression == 5

    def test_regression_min_clamped_high(self) -> None:
        """TS-41-E7: min_outcomes_for_regression clamped to 10000 when too high.

        Requirement: 41-REQ-5.E1
        """
        from agent_fox.core.config import PlanningConfig

        c = PlanningConfig(min_outcomes_for_regression=50000)
        assert c.min_outcomes_for_regression == 10000


# ---------------------------------------------------------------------------
# TS-41-17, TS-41-E1, TS-41-E8: Orchestrator _compute_duration_hints()
# ---------------------------------------------------------------------------


class TestComputeDurationHints:
    """Tests for Orchestrator._compute_duration_hints() integration.

    Test Spec: TS-41-17, TS-41-E1, TS-41-E8
    """

    def _make_orchestrator(
        self,
        tmp_path: Path,
        *,
        duration_ordering: bool = True,
        pipeline: object | None = None,
    ) -> object:
        """Create an Orchestrator with minimal plan for testing."""
        from agent_fox.core.config import OrchestratorConfig, PlanningConfig
        from agent_fox.engine.engine import Orchestrator

        from .conftest import write_plan_file

        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = write_plan_file(
            plan_dir,
            nodes={"a:1": {"title": "Task A"}, "b:1": {"title": "Task B"}},
            edges=[],
            order=["a:1", "b:1"],
        )
        state_path = plan_dir / "state.jsonl"

        planning_config = PlanningConfig(duration_ordering=duration_ordering)
        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orch = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=state_path,
            session_runner_factory=lambda nid, **kw: MagicMock(),
            planning_config=planning_config,
            assessment_pipeline=pipeline,
        )
        return orch

    def test_duration_ordering_disabled_returns_none(self, tmp_path: Path) -> None:
        """TS-41-17: _compute_duration_hints() returns None when disabled.

        Requirement: 41-REQ-5.2
        """
        orch = self._make_orchestrator(tmp_path, duration_ordering=False)
        result = orch._compute_duration_hints()
        assert result is None

    def test_pipeline_unavailable_returns_none(self, tmp_path: Path) -> None:
        """TS-41-E8: _compute_duration_hints() returns None when pipeline is None.

        Requirement: 41-REQ-5.E2
        """
        orch = self._make_orchestrator(tmp_path, pipeline=None)
        result = orch._compute_duration_hints()
        assert result is None

    def test_db_exception_returns_none(self, tmp_path: Path) -> None:
        """TS-41-E1: _compute_duration_hints() returns None on DB exception.

        Requirement: 41-REQ-1.E1
        """
        from agent_fox.engine.graph_sync import GraphSync

        # Create a pipeline mock with a _db that raises on execute
        mock_pipeline = MagicMock()
        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("DB connection failed")
        mock_pipeline._db = mock_db
        mock_pipeline.duration_model = None

        orch = self._make_orchestrator(tmp_path, pipeline=mock_pipeline)
        # Set up graph_sync with pending nodes so the loop iterates
        orch._graph_sync = GraphSync({"a:1": "pending", "b:1": "pending"}, {})
        result = orch._compute_duration_hints()
        assert result is None
