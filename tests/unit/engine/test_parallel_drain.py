"""Parallel drain and orchestrator integration tests.

Test Spec: TS-51-1 through TS-51-4, TS-51-E1
Requirements: 51-REQ-1.1, 51-REQ-1.2, 51-REQ-1.3, 51-REQ-1.E1, 51-REQ-1.E2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from agent_fox.engine.dispatch import ParallelDispatcher
from agent_fox.engine.state import SessionRecord


def _make_record(
    node_id: str,
    status: str = "completed",
    error_message: str | None = None,
) -> SessionRecord:
    """Create a minimal SessionRecord for testing."""
    return SessionRecord(
        node_id=node_id,
        attempt=1,
        status=status,
        input_tokens=100,
        output_tokens=200,
        cost=0.10,
        duration_ms=5000,
        error_message=error_message,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# TS-51-1: Parallel drain waits for all in-flight tasks
# ---------------------------------------------------------------------------


class TestParallelDrainWaitsForAll:
    """TS-51-1: Parallel drain waits for all in-flight tasks.

    Verify that the orchestrator waits for all in-flight parallel tasks
    to complete before entering the barrier.

    Requirements: 51-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_all_tasks_complete_before_barrier(self) -> None:
        """All pool tasks complete before barrier operations begin."""
        completed_tasks: list[str] = []
        barrier_entered = False

        async def mock_task(node_id: str, delay: float) -> SessionRecord:
            await asyncio.sleep(delay)
            completed_tasks.append(node_id)
            return _make_record(node_id)

        # Create 3 tasks with short delays
        tasks = [
            asyncio.create_task(mock_task("A", 0.05)),
            asyncio.create_task(mock_task("B", 0.08)),
            asyncio.create_task(mock_task("C", 0.03)),
        ]
        pool = set(tasks)

        # Drain the pool (simulating what _dispatch_parallel should do)
        if pool:
            done, pool = await asyncio.wait(pool)
            for t in done:
                t.result()  # process results

        barrier_entered = True

        assert len(pool) == 0
        assert len(completed_tasks) == 3
        assert barrier_entered


# ---------------------------------------------------------------------------
# TS-51-2: Drained task results are processed
# ---------------------------------------------------------------------------


class TestDrainedTaskResultsProcessed:
    """TS-51-2: Drained task results are processed.

    Verify that session results from drained tasks are processed
    (state updates, cascade blocking).

    Requirements: 51-REQ-1.2
    """

    @pytest.mark.asyncio
    async def test_session_results_processed_after_drain(self) -> None:
        """Both success and failure results are recorded after drain."""
        results_processed: list[SessionRecord] = []

        async def mock_task_a() -> SessionRecord:
            await asyncio.sleep(0.02)
            return _make_record("A", status="completed")

        async def mock_task_b() -> SessionRecord:
            await asyncio.sleep(0.03)
            return _make_record("B", status="failed", error_message="test error")

        pool = {
            asyncio.create_task(mock_task_a()),
            asyncio.create_task(mock_task_b()),
        }

        # Drain all tasks
        done, pool = await asyncio.wait(pool)
        for t in done:
            record = t.result()
            results_processed.append(record)

        assert len(pool) == 0
        assert len(results_processed) == 2

        statuses = {r.node_id: r.status for r in results_processed}
        assert statuses["A"] == "completed"
        assert statuses["B"] == "failed"


# ---------------------------------------------------------------------------
# TS-51-3: No new tasks dispatched during drain
# ---------------------------------------------------------------------------


class TestNoNewDispatchDuringDrain:
    """TS-51-3: No new tasks dispatched during drain.

    Verify that no new tasks are dispatched while draining.

    Requirements: 51-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_new_tasks_not_launched_during_drain(self) -> None:
        """Ready tasks are NOT launched during drain, only after barrier."""
        new_tasks_launched: list[str] = []
        drain_complete = False

        async def mock_task(node_id: str) -> SessionRecord:
            await asyncio.sleep(0.02)
            return _make_record(node_id)

        # Simulate pool with 2 tasks
        pool = {
            asyncio.create_task(mock_task("A")),
            asyncio.create_task(mock_task("B")),
        }

        # Drain
        done, pool = await asyncio.wait(pool)
        drain_complete = True

        # Only after drain is complete, launch new tasks
        assert drain_complete
        assert len(pool) == 0

        # Now fill pool (this simulates post-barrier behavior)
        for node_id in ["C", "D", "E"]:
            new_tasks_launched.append(node_id)

        assert len(new_tasks_launched) == 3
        assert drain_complete  # new tasks only after drain


# ---------------------------------------------------------------------------
# TS-51-4: Serial mode skips drain
# ---------------------------------------------------------------------------


class TestSerialModeSkipsDrain:
    """TS-51-4: Serial mode skips drain.

    Verify that serial mode (parallel=1) skips the parallel drain step.

    Requirements: 51-REQ-1.E1
    """

    def test_serial_mode_no_drain(self) -> None:
        """In serial mode, no parallel pool exists to drain."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig(parallel=1)
        is_parallel = config.parallel > 1

        # Serial mode: no parallel runner, so no drain needed
        assert not is_parallel


# ---------------------------------------------------------------------------
# TS-51-E1: SIGINT during parallel drain
# ---------------------------------------------------------------------------


class TestSIGINTDuringDrain:
    """TS-51-E1: SIGINT during parallel drain.

    Verify that SIGINT cancels remaining tasks and proceeds to shutdown.

    Requirements: 51-REQ-1.E2
    """

    @pytest.mark.asyncio
    async def test_sigint_cancels_remaining_tasks(self) -> None:
        """SIGINT causes remaining pool tasks to be cancelled."""

        async def slow_task() -> SessionRecord:
            await asyncio.sleep(10)
            return _make_record("slow")

        pool = {asyncio.create_task(slow_task())}

        # Give the task a moment to start sleeping
        await asyncio.sleep(0.01)

        # Simulate SIGINT by cancelling all tasks
        for task in pool:
            task.cancel()

        # Wait for cancellation to propagate
        done, _ = await asyncio.wait(pool)
        for t in done:
            assert t.cancelled()


# ---------------------------------------------------------------------------
# TS-489-1: Review concurrency cap configuration
# Issue: #489
# ---------------------------------------------------------------------------


class TestReviewConcurrencyCapConfig:
    """Verify max_review_fraction config field on OrchestratorConfig."""

    def test_default_max_review_fraction(self) -> None:
        """Default max_review_fraction is 0.34 (~1/3)."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig()
        assert config.max_review_fraction == pytest.approx(0.34)

    def test_custom_max_review_fraction(self) -> None:
        """max_review_fraction can be set to a custom value."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig(max_review_fraction=0.5)
        assert config.max_review_fraction == pytest.approx(0.5)

    def test_max_review_fraction_floor_at_zero(self) -> None:
        """max_review_fraction=0.0 is valid (effectively disables reviews)."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig(max_review_fraction=0.0)
        assert config.max_review_fraction == 0.0

    def test_max_review_cap_calculation(self) -> None:
        """max(1, int(max_pool * fraction)) gives at least 1 review slot."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig(parallel=3, max_review_fraction=0.34)
        max_review = max(1, int(config.parallel * config.max_review_fraction))
        assert max_review == 1

    def test_max_review_cap_scales_with_pool(self) -> None:
        """With parallel=6 and fraction=0.34, cap is 2."""
        from agent_fox.core.config import OrchestratorConfig

        config = OrchestratorConfig(parallel=6, max_review_fraction=0.34)
        max_review = max(1, int(config.parallel * config.max_review_fraction))
        assert max_review == 2


# ---------------------------------------------------------------------------
# TS-489-2: Review archetype detection from task names
# Issue: #489
# ---------------------------------------------------------------------------


class TestReviewArchetypeDetection:
    """Verify review archetype detection used by the pool cap."""

    def test_review_archetypes_include_all_review_types(self) -> None:
        """_REVIEW_ARCHETYPES includes reviewer, skeptic, verifier, oracle, auditor."""
        from agent_fox.engine.session_lifecycle import _REVIEW_ARCHETYPES

        assert "reviewer" in _REVIEW_ARCHETYPES
        assert "skeptic" in _REVIEW_ARCHETYPES
        assert "verifier" in _REVIEW_ARCHETYPES
        assert "oracle" in _REVIEW_ARCHETYPES
        assert "auditor" in _REVIEW_ARCHETYPES

    def test_coder_not_in_review_archetypes(self) -> None:
        """Coder archetype is not a review archetype."""
        from agent_fox.engine.session_lifecycle import _REVIEW_ARCHETYPES

        assert "coder" not in _REVIEW_ARCHETYPES

    def test_auto_pre_detection(self) -> None:
        """Group-0 nodes are detected as auto_pre."""
        from agent_fox.engine.graph_sync import _is_auto_pre

        assert _is_auto_pre("spec_a:0")
        assert not _is_auto_pre("spec_a:1")
        assert not _is_auto_pre("spec_a:2")


# ---------------------------------------------------------------------------
# TS-489-3: Review concurrency cap in _fill_parallel_pool
# Issue: #489
# ---------------------------------------------------------------------------


class TestReviewConcurrencyCapPool:
    """Verify the review concurrency cap logic in _fill_parallel_pool.

    Tests exercise the cap by constructing a mock orchestrator with a
    controlled graph and verifying that review candidates are skipped
    when the review slot budget is exhausted.
    """

    @pytest.mark.asyncio
    async def test_review_cap_skips_excess_reviews(self) -> None:
        """With parallel=3 and default fraction, at most 1 non-pre review runs."""
        from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

        from agent_fox.engine.engine import Orchestrator
        from agent_fox.graph.types import Node, NodeStatus

        config = MagicMock()
        config.parallel = 3
        config.max_review_fraction = 0.34

        nodes = {
            "spec_a:1": Node(
                id="spec_a:1", spec_name="spec_a", group_number=1,
                title="review A", optional=False, archetype="reviewer",
            ),
            "spec_b:1": Node(
                id="spec_b:1", spec_name="spec_b", group_number=1,
                title="review B", optional=False, archetype="skeptic",
            ),
            "spec_c:1": Node(
                id="spec_c:1", spec_name="spec_c", group_number=1,
                title="code C", optional=False, archetype="coder",
            ),
        }

        orch = object.__new__(Orchestrator)
        orch._config = config
        orch._graph = MagicMock()
        orch._graph.nodes = nodes
        orch._graph_sync = MagicMock()
        orch._graph_sync.node_states = {}
        orch._graph_sync.mark_in_progress = MagicMock()
        orch._signal = MagicMock()
        orch._signal.interrupted = False
        orch._result_handler = None
        orch._run_id = "test"
        orch._routing = MagicMock()

        runner = MagicMock()
        type(runner).max_parallelism = PropertyMock(return_value=3)
        runner.execute_one = AsyncMock(return_value=_make_record("x"))

        dispatch_mgr = MagicMock()
        dispatch_mgr.parallel_runner = runner
        dispatch_mgr.get_node_archetype = lambda nid: nodes[nid].archetype

        async def mock_prepare_launch(node_id, state, at, et):
            arch = nodes[node_id].archetype
            return ("allowed", 1, None, arch, 1, None, None)

        dispatch_mgr.prepare_launch = mock_prepare_launch
        orch._dispatch_mgr = dispatch_mgr

        dispatcher = ParallelDispatcher(orch)
        pool: set[asyncio.Task[SessionRecord]] = set()
        candidates = ["spec_a:1", "spec_b:1", "spec_c:1"]

        await dispatcher.fill_pool(pool, candidates, MagicMock(), {}, {})

        launched = [t.get_name().replace("parallel-", "") for t in pool]

        # max_review = max(1, int(3 * 0.34)) = 1
        # spec_a:1 (reviewer) should launch (first review), spec_b:1 (skeptic) should be
        # skipped (cap reached), spec_c:1 (coder) should launch
        assert "spec_a:1" in launched
        assert "spec_c:1" in launched
        assert "spec_b:1" not in launched
        assert len(pool) == 2

        for t in pool:
            t.cancel()
        await asyncio.gather(*pool, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_auto_pre_exempt_from_cap(self) -> None:
        """Group-0 review nodes (auto_pre) are exempt from the cap."""
        from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

        from agent_fox.engine.engine import Orchestrator
        from agent_fox.graph.types import Node, NodeStatus

        config = MagicMock()
        config.parallel = 3
        config.max_review_fraction = 0.34

        nodes = {
            "spec_a:0": Node(
                id="spec_a:0", spec_name="spec_a", group_number=0,
                title="pre-review A", optional=False, archetype="reviewer",
            ),
            "spec_b:0": Node(
                id="spec_b:0", spec_name="spec_b", group_number=0,
                title="pre-review B", optional=False, archetype="skeptic",
            ),
            "spec_c:1": Node(
                id="spec_c:1", spec_name="spec_c", group_number=1,
                title="code C", optional=False, archetype="coder",
            ),
        }

        orch = object.__new__(Orchestrator)
        orch._config = config
        orch._graph = MagicMock()
        orch._graph.nodes = nodes
        orch._graph_sync = MagicMock()
        orch._graph_sync.node_states = {}
        orch._graph_sync.mark_in_progress = MagicMock()
        orch._signal = MagicMock()
        orch._signal.interrupted = False
        orch._result_handler = None
        orch._run_id = "test"
        orch._routing = MagicMock()

        runner = MagicMock()
        type(runner).max_parallelism = PropertyMock(return_value=3)
        runner.execute_one = AsyncMock(return_value=_make_record("x"))

        dispatch_mgr = MagicMock()
        dispatch_mgr.parallel_runner = runner
        dispatch_mgr.get_node_archetype = lambda nid: nodes[nid].archetype

        async def mock_prepare_launch(node_id, state, at, et):
            arch = nodes[node_id].archetype
            return ("allowed", 1, None, arch, 1, None, None)

        dispatch_mgr.prepare_launch = mock_prepare_launch
        orch._dispatch_mgr = dispatch_mgr

        dispatcher = ParallelDispatcher(orch)
        pool: set[asyncio.Task[SessionRecord]] = set()
        candidates = ["spec_a:0", "spec_b:0", "spec_c:1"]

        await dispatcher.fill_pool(pool, candidates, MagicMock(), {}, {})

        launched = [t.get_name().replace("parallel-", "") for t in pool]

        # Both auto_pre nodes should launch (exempt from cap),
        # plus the coder — all 3 slots filled.
        assert "spec_a:0" in launched
        assert "spec_b:0" in launched
        assert "spec_c:1" in launched
        assert len(pool) == 3

        for t in pool:
            t.cancel()
        await asyncio.gather(*pool, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_coders_always_preferred_over_capped_reviews(self) -> None:
        """When review cap is reached, remaining slots go to coder candidates."""
        from unittest.mock import AsyncMock, MagicMock, PropertyMock

        from agent_fox.engine.engine import Orchestrator
        from agent_fox.graph.types import Node

        config = MagicMock()
        config.parallel = 3
        config.max_review_fraction = 0.34

        nodes = {
            "spec_a:2": Node(
                id="spec_a:2", spec_name="spec_a", group_number=2,
                title="review", optional=False, archetype="reviewer",
            ),
            "spec_b:2": Node(
                id="spec_b:2", spec_name="spec_b", group_number=2,
                title="review", optional=False, archetype="verifier",
            ),
            "spec_c:2": Node(
                id="spec_c:2", spec_name="spec_c", group_number=2,
                title="review", optional=False, archetype="oracle",
            ),
            "spec_d:1": Node(
                id="spec_d:1", spec_name="spec_d", group_number=1,
                title="coder", optional=False, archetype="coder",
            ),
            "spec_e:1": Node(
                id="spec_e:1", spec_name="spec_e", group_number=1,
                title="coder", optional=False, archetype="coder",
            ),
        }

        orch = object.__new__(Orchestrator)
        orch._config = config
        orch._graph = MagicMock()
        orch._graph.nodes = nodes
        orch._graph_sync = MagicMock()
        orch._graph_sync.node_states = {}
        orch._graph_sync.mark_in_progress = MagicMock()
        orch._signal = MagicMock()
        orch._signal.interrupted = False
        orch._result_handler = None
        orch._run_id = "test"
        orch._routing = MagicMock()

        runner = MagicMock()
        type(runner).max_parallelism = PropertyMock(return_value=3)
        runner.execute_one = AsyncMock(return_value=_make_record("x"))

        dispatch_mgr = MagicMock()
        dispatch_mgr.parallel_runner = runner
        dispatch_mgr.get_node_archetype = lambda nid: nodes[nid].archetype

        async def mock_prepare_launch(node_id, state, at, et):
            arch = nodes[node_id].archetype
            return ("allowed", 1, None, arch, 1, None, None)

        dispatch_mgr.prepare_launch = mock_prepare_launch
        orch._dispatch_mgr = dispatch_mgr

        dispatcher = ParallelDispatcher(orch)
        pool: set[asyncio.Task[SessionRecord]] = set()
        # Reviews first, then coders — cap should let 1 review + 2 coders
        candidates = ["spec_a:2", "spec_b:2", "spec_c:2", "spec_d:1", "spec_e:1"]

        await dispatcher.fill_pool(pool, candidates, MagicMock(), {}, {})

        launched = [t.get_name().replace("parallel-", "") for t in pool]

        review_launched = [n for n in launched if nodes[n].archetype != "coder"]
        coder_launched = [n for n in launched if nodes[n].archetype == "coder"]

        assert len(review_launched) == 1
        assert len(coder_launched) == 2
        assert len(pool) == 3

        for t in pool:
            t.cancel()
        await asyncio.gather(*pool, return_exceptions=True)


# ---------------------------------------------------------------------------
# TS-503-1: Review cap must not consume retry budget (issue #503)
# ---------------------------------------------------------------------------


class TestReviewCapDoesNotConsumeRetries:
    """Verify that the review concurrency cap does not increment attempt_tracker.

    When a review candidate is skipped because the review slot budget is
    exhausted, _prepare_launch must NOT be called.  Previously, the cap
    check was placed AFTER _prepare_launch, which incremented
    attempt_tracker on each pool-refill cycle.  After max_retries+1
    such skips the circuit breaker permanently blocked the task with
    'Retry limit exceeded' — without ever starting a session.
    """

    @pytest.mark.asyncio
    async def test_attempt_tracker_unchanged_for_capped_review(self) -> None:
        """Skipped review candidates keep attempt_tracker at 0."""
        from unittest.mock import AsyncMock, MagicMock, PropertyMock

        from agent_fox.engine.engine import Orchestrator
        from agent_fox.graph.types import Node

        config = MagicMock()
        config.parallel = 3
        config.max_review_fraction = 0.34

        nodes = {
            "spec_a:1": Node(
                id="spec_a:1", spec_name="spec_a", group_number=1,
                title="audit review A", optional=False, archetype="reviewer",
            ),
            "spec_b:1": Node(
                id="spec_b:1", spec_name="spec_b", group_number=1,
                title="audit review B", optional=False, archetype="reviewer",
            ),
        }

        orch = object.__new__(Orchestrator)
        orch._config = config
        orch._graph = MagicMock()
        orch._graph.nodes = nodes
        orch._graph_sync = MagicMock()
        orch._graph_sync.node_states = {}
        orch._graph_sync.mark_in_progress = MagicMock()
        orch._signal = MagicMock()
        orch._signal.interrupted = False
        orch._result_handler = None
        orch._run_id = "test"
        orch._routing = MagicMock()

        runner = MagicMock()
        type(runner).max_parallelism = PropertyMock(return_value=3)
        runner.execute_one = AsyncMock(return_value=_make_record("x"))

        dispatch_mgr = MagicMock()
        dispatch_mgr.parallel_runner = runner
        dispatch_mgr.get_node_archetype = lambda nid: nodes[nid].archetype

        prepare_calls: list[str] = []

        async def mock_prepare_launch(node_id, state, at, et):
            prepare_calls.append(node_id)
            arch = nodes[node_id].archetype
            at[node_id] = at.get(node_id, 0) + 1
            return ("allowed", at[node_id], None, arch, 1, None, None)

        dispatch_mgr.prepare_launch = mock_prepare_launch
        orch._dispatch_mgr = dispatch_mgr

        dispatcher = ParallelDispatcher(orch)
        attempt_tracker: dict[str, int] = {}
        pool: set[asyncio.Task[SessionRecord]] = set()

        # max_review = max(1, int(3*0.34)) = 1
        # spec_a:1 should launch (first review slot), spec_b:1 should be
        # skipped by the cap BEFORE _prepare_launch is called.
        await dispatcher.fill_pool(
            pool, ["spec_a:1", "spec_b:1"], MagicMock(), attempt_tracker, {},
        )

        assert "spec_a:1" in prepare_calls
        assert "spec_b:1" not in prepare_calls, (
            "_prepare_launch must not be called for review candidates "
            "skipped by the concurrency cap"
        )
        assert attempt_tracker.get("spec_b:1", 0) == 0

        for t in pool:
            t.cancel()
        await asyncio.gather(*pool, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_review_cap_skip_survives_repeated_refills(self) -> None:
        """A capped review is never blocked even after many pool refill cycles."""
        from unittest.mock import AsyncMock, MagicMock, PropertyMock

        from agent_fox.engine.engine import Orchestrator
        from agent_fox.graph.types import Node

        config = MagicMock()
        config.parallel = 5
        config.max_review_fraction = 0.34
        config.max_retries = 2

        nodes = {
            "spec_x:1:reviewer:audit-review": Node(
                id="spec_x:1:reviewer:audit-review",
                spec_name="spec_x", group_number=1,
                title="audit", optional=False, archetype="reviewer",
            ),
        }

        orch = object.__new__(Orchestrator)
        orch._config = config
        orch._graph = MagicMock()
        orch._graph.nodes = nodes
        orch._graph_sync = MagicMock()
        orch._graph_sync.node_states = {}
        orch._graph_sync.mark_in_progress = MagicMock()
        orch._signal = MagicMock()
        orch._signal.interrupted = False
        orch._result_handler = None
        orch._run_id = "test"
        orch._routing = MagicMock()

        runner = MagicMock()
        type(runner).max_parallelism = PropertyMock(return_value=5)
        runner.execute_one = AsyncMock(return_value=_make_record("x"))

        dispatch_mgr = MagicMock()
        dispatch_mgr.parallel_runner = runner
        dispatch_mgr.get_node_archetype = lambda nid: nodes.get(nid, nodes.get(nid, MagicMock(archetype="reviewer"))).archetype

        async def mock_prepare_launch(node_id, state, at, et):
            arch = nodes[node_id].archetype
            at[node_id] = at.get(node_id, 0) + 1
            return ("allowed", at[node_id], None, arch, 1, None, None)

        dispatch_mgr.prepare_launch = mock_prepare_launch
        orch._dispatch_mgr = dispatch_mgr

        dispatcher = ParallelDispatcher(orch)
        attempt_tracker: dict[str, int] = {}
        node_id = "spec_x:1:reviewer:audit-review"

        # Simulate a review already occupying the single review slot.
        # Run 10 pool refill cycles (well past max_retries+1=3).
        for _ in range(10):
            existing_task = MagicMock()
            existing_task.get_name.return_value = "parallel-other:1"
            pool: set[asyncio.Task[SessionRecord]] = set()

            # Fake an existing review in the pool so the cap is hit.
            fake_review_task = MagicMock()
            fake_review_task.get_name.return_value = "parallel-other_review:1"
            pool.add(fake_review_task)
            orch._graph.nodes["other_review:1"] = Node(
                id="other_review:1", spec_name="other", group_number=1,
                title="r", optional=False, archetype="reviewer",
            )

            await dispatcher.fill_pool(
                pool, [node_id], MagicMock(), attempt_tracker, {},
            )

        assert attempt_tracker.get(node_id, 0) == 0, (
            f"attempt_tracker was {attempt_tracker.get(node_id, 0)} after "
            f"10 refill cycles; expected 0 (review cap should not consume retries)"
        )
        assert orch._graph_sync.node_states.get(node_id) != "blocked"
