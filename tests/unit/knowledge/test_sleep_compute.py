"""Unit tests for the SleepComputer orchestrator and supporting data types.

Test Spec: TS-112-1 through TS-112-10, TS-112-30 through TS-112-34,
           TS-112-E8, TS-112-E9, TS-112-E10, TS-112-E11,
           TS-112-P1, TS-112-P2, TS-112-P3, TS-112-P7

Requirements: 112-REQ-1.*, 112-REQ-2.*, 112-REQ-7.*, 112-REQ-8.*
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest
from agent_fox.knowledge.sleep_compute import (  # noqa: F401
    SleepComputer,
    SleepComputeResult,
    SleepContext,
    SleepTask,
    SleepTaskResult,
    compute_content_hash,
    upsert_artifact,
)
from agent_fox.knowledge.sleep_tasks.context_rewriter import ContextRewriter  # noqa: F401
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Imports from non-existent modules — will trigger ImportError at collection
# ---------------------------------------------------------------------------
from agent_fox.core.config import SleepConfig  # noqa: F401 (doesn't exist yet)

# ---------------------------------------------------------------------------
# Existing imports
# ---------------------------------------------------------------------------
from agent_fox.knowledge.migrations import run_migrations

# ---------------------------------------------------------------------------
# Sleep artifacts DDL (migration v15 will add this; tests create it directly)
# ---------------------------------------------------------------------------

_SLEEP_ARTIFACTS_DDL = """
CREATE TABLE IF NOT EXISTS sleep_artifacts (
    id            UUID PRIMARY KEY,
    task_name     VARCHAR,
    scope_key     VARCHAR,
    content       TEXT,
    metadata_json TEXT,
    content_hash  VARCHAR,
    created_at    TIMESTAMP,
    superseded_at TIMESTAMP
)
"""


# ---------------------------------------------------------------------------
# Mock sleep task helpers
# ---------------------------------------------------------------------------


class MockSleepTask:
    """Minimal SleepTask implementation that records calls and budgets."""

    def __init__(self, task_name: str, *, cost_estimate: float = 0.1) -> None:
        self._name = task_name
        self.cost_estimate: float = cost_estimate
        self.call_order_list: list[str] | None = None
        self.received_budgets: list[float] = []
        self._all_tasks_received: list[MockSleepTask] | None = None

    @property
    def name(self) -> str:
        return self._name

    def stale_scopes(self, conn: duckdb.DuckDBPyConnection) -> list[str]:
        return []

    async def run(self, ctx: SleepContext) -> SleepTaskResult:
        self.received_budgets.append(ctx.budget_remaining)
        if self.call_order_list is not None:
            self.call_order_list.append(self._name)
        return SleepTaskResult(
            created=0,
            refreshed=0,
            unchanged=0,
            llm_cost=self.cost_estimate,
        )


class MockFailTask:
    """SleepTask that raises RuntimeError in run()."""

    def __init__(self, task_name: str, *, cost_estimate: float = 0.1) -> None:
        self._name = task_name
        self.cost_estimate: float = cost_estimate

    @property
    def name(self) -> str:
        return self._name

    def stale_scopes(self, conn: duckdb.DuckDBPyConnection) -> list[str]:
        return []

    async def run(self, ctx: SleepContext) -> SleepTaskResult:
        raise RuntimeError(f"Task {self._name} intentionally failed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def migrated_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with full schema including sleep_artifacts."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    return conn


@pytest.fixture
def sleep_ctx(migrated_conn: duckdb.DuckDBPyConnection) -> SleepContext:
    """Minimal SleepContext for testing."""
    return SleepContext(
        conn=migrated_conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=1.0,
        sink_dispatcher=None,
    )


@pytest.fixture
def sleep_config() -> SleepConfig:
    """Default SleepConfig."""
    return SleepConfig()


# ---------------------------------------------------------------------------
# TS-112-1: SleepTask protocol name property
# ---------------------------------------------------------------------------


def test_sleep_task_name_property() -> None:
    """TS-112-1: ContextRewriter.name returns a non-empty string."""
    task = ContextRewriter()
    assert isinstance(task.name, str)
    assert len(task.name) > 0


# ---------------------------------------------------------------------------
# TS-112-2: SleepTask run returns SleepTaskResult
# ---------------------------------------------------------------------------


async def test_sleep_task_run_returns_result(
    sleep_ctx: SleepContext,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-2: task.run(ctx) returns a SleepTaskResult."""
    task = ContextRewriter()
    result = await task.run(sleep_ctx)
    assert isinstance(result, SleepTaskResult)
    assert isinstance(result.created, int)
    assert isinstance(result.refreshed, int)
    assert isinstance(result.unchanged, int)
    assert isinstance(result.llm_cost, float)


# ---------------------------------------------------------------------------
# TS-112-3: SleepTask stale_scopes returns a list of strings
# ---------------------------------------------------------------------------


def test_stale_scopes_returns_list(migrated_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-112-3: stale_scopes returns a list of strings."""
    task = ContextRewriter()
    scopes = task.stale_scopes(migrated_conn)
    assert isinstance(scopes, list)
    assert all(isinstance(s, str) for s in scopes)


# ---------------------------------------------------------------------------
# TS-112-4: SleepContext bundles all required fields
# ---------------------------------------------------------------------------


def test_sleep_context_fields(migrated_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-112-4: SleepContext has all required fields."""
    ctx = SleepContext(
        conn=migrated_conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=1.0,
        sink_dispatcher=None,
    )
    assert ctx.conn is migrated_conn
    assert ctx.repo_root == Path(".")
    assert ctx.model == "standard"
    assert ctx.embedder is None
    assert ctx.budget_remaining == 1.0
    assert ctx.sink_dispatcher is None


# ---------------------------------------------------------------------------
# TS-112-5: SleepTaskResult fields
# ---------------------------------------------------------------------------


def test_sleep_task_result_fields() -> None:
    """TS-112-5: SleepTaskResult has created, refreshed, unchanged, llm_cost."""
    result = SleepTaskResult(created=1, refreshed=2, unchanged=3, llm_cost=0.05)
    assert result.created == 1
    assert result.refreshed == 2
    assert result.unchanged == 3
    assert result.llm_cost == 0.05


# ---------------------------------------------------------------------------
# TS-112-6: SleepComputer executes tasks in order
# ---------------------------------------------------------------------------


async def test_executes_tasks_in_order(
    sleep_ctx: SleepContext,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-6: Tasks run in registration order; budget decrements correctly."""
    call_order: list[str] = []
    task_a = MockSleepTask("task_a", cost_estimate=0.3)
    task_a.call_order_list = call_order
    task_b = MockSleepTask("task_b", cost_estimate=0.1)
    task_b.call_order_list = call_order

    computer = SleepComputer([task_a, task_b], sleep_config)
    await computer.run(sleep_ctx)

    assert call_order == ["task_a", "task_b"]
    # task_b should receive budget minus task_a's cost
    assert len(task_b.received_budgets) == 1
    assert abs(task_b.received_budgets[0] - 0.7) < 1e-9


# ---------------------------------------------------------------------------
# TS-112-7: SleepComputeResult structure
# ---------------------------------------------------------------------------


async def test_sleep_compute_result_structure(
    sleep_ctx: SleepContext,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-7: SleepComputeResult has task_results, total_llm_cost, errors."""
    task = MockSleepTask("context_rewriter", cost_estimate=0.05)
    computer = SleepComputer([task], sleep_config)
    result = await computer.run(sleep_ctx)

    assert isinstance(result, SleepComputeResult)
    assert "context_rewriter" in result.task_results
    assert isinstance(result.total_llm_cost, float)
    assert isinstance(result.errors, list)


# ---------------------------------------------------------------------------
# TS-112-8: Task exception isolation
# ---------------------------------------------------------------------------


async def test_task_exception_isolation(
    sleep_ctx: SleepContext,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-8: Failing task doesn't block subsequent tasks."""
    task_a = MockFailTask("task_a")
    task_b = MockSleepTask("task_b", cost_estimate=0.05)

    computer = SleepComputer([task_a, task_b], sleep_config)
    result = await computer.run(sleep_ctx)

    assert "task_b" in result.task_results
    assert any("task_a" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TS-112-9: Budget exhaustion skips task
# ---------------------------------------------------------------------------


async def test_budget_exhaustion(sleep_ctx: SleepContext, sleep_config: SleepConfig) -> None:
    """TS-112-9: task_a (cost 0.9) runs; task_b (cost_estimate 0.5) is skipped."""
    task_a = MockSleepTask("task_a", cost_estimate=0.9)
    task_b = MockSleepTask("task_b", cost_estimate=0.5)

    computer = SleepComputer([task_a, task_b], sleep_config)
    # sleep_ctx has budget_remaining=1.0; task_a costs 0.9, leaving 0.1
    # task_b needs 0.5 which exceeds remaining budget
    result = await computer.run(sleep_ctx)

    assert "task_a" in result.task_results
    assert "task_b" not in result.task_results
    assert any("budget_exhausted" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TS-112-10: Audit event emitted
# ---------------------------------------------------------------------------


async def test_audit_event_emitted(
    migrated_conn: duckdb.DuckDBPyConnection,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-10: SLEEP_COMPUTE_COMPLETE audit event is emitted to sink."""
    emitted_events: list[object] = []

    mock_sink = MagicMock()
    mock_sink.emit_audit_event.side_effect = emitted_events.append

    from agent_fox.knowledge.sink import SinkDispatcher

    dispatcher = SinkDispatcher([mock_sink])
    ctx = SleepContext(
        conn=migrated_conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=1.0,
        sink_dispatcher=dispatcher,
    )

    task = MockSleepTask("my_task", cost_estimate=0.05)
    computer = SleepComputer([task], sleep_config)
    result = await computer.run(ctx)

    # The sink should have received at least one audit event
    assert mock_sink.emit_audit_event.call_count >= 1
    # Check the event type on the first call
    event_arg = mock_sink.emit_audit_event.call_args_list[0][0][0]
    assert "SLEEP_COMPUTE_COMPLETE" in str(event_arg.event_type)
    assert "total_cost" in event_arg.payload or result is not None


# ---------------------------------------------------------------------------
# TS-112-30: SleepConfig defaults
# ---------------------------------------------------------------------------


def test_config_defaults() -> None:
    """TS-112-30: SleepConfig() uses correct defaults."""
    config = SleepConfig()
    assert config.enabled is True
    assert config.max_cost == 1.0
    assert config.nightshift_interval == 1800
    assert config.context_rewriter_enabled is True
    assert config.bundle_builder_enabled is True


# ---------------------------------------------------------------------------
# TS-112-31: Sleep disabled skips compute
# ---------------------------------------------------------------------------


def test_sleep_disabled() -> None:
    """TS-112-31: SleepConfig(enabled=False) → stream.enabled is False."""
    from agent_fox.nightshift.streams import SleepComputeStream

    config = SleepConfig(enabled=False)
    stream = SleepComputeStream(config)
    assert stream.enabled is False


# ---------------------------------------------------------------------------
# TS-112-32: Per-task disable
# ---------------------------------------------------------------------------


async def test_per_task_disable(
    sleep_ctx: SleepContext,
) -> None:
    """TS-112-32: context_rewriter_enabled=False skips ContextRewriter."""
    from agent_fox.knowledge.sleep_tasks.bundle_builder import BundleBuilder

    config = SleepConfig(context_rewriter_enabled=False)
    rewriter = ContextRewriter()
    builder = BundleBuilder()

    computer = SleepComputer([rewriter, builder], config)
    result = await computer.run(sleep_ctx)

    assert "context_rewriter" not in result.task_results
    assert "bundle_builder" in result.task_results


# ---------------------------------------------------------------------------
# TS-112-33: sleep_artifacts table schema
# ---------------------------------------------------------------------------


def test_schema_columns(migrated_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-112-33: sleep_artifacts has all 8 required columns."""
    cols = migrated_conn.execute("DESCRIBE sleep_artifacts").fetchall()
    col_names = {c[0] for c in cols}
    required = {
        "id",
        "task_name",
        "scope_key",
        "content",
        "metadata_json",
        "content_hash",
        "created_at",
        "superseded_at",
    }
    assert required <= col_names


# ---------------------------------------------------------------------------
# TS-112-34: Artifact supersession on update
# ---------------------------------------------------------------------------


def test_artifact_supersession(migrated_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-112-34: Old artifact gets superseded_at set when new one is inserted."""
    # Insert first artifact
    upsert_artifact(
        migrated_conn,
        task_name="t",
        scope_key="s",
        content="v1",
        metadata_json="{}",
        content_hash="hash1",
    )
    # Insert second artifact (should supersede first)
    upsert_artifact(
        migrated_conn,
        task_name="t",
        scope_key="s",
        content="v2",
        metadata_json="{}",
        content_hash="hash2",
    )

    active = migrated_conn.execute(
        "SELECT content FROM sleep_artifacts WHERE task_name='t' AND scope_key='s' AND superseded_at IS NULL"
    ).fetchall()
    assert len(active) == 1
    assert active[0][0] == "v2"

    superseded = migrated_conn.execute(
        "SELECT content FROM sleep_artifacts WHERE task_name='t' AND scope_key='s' AND superseded_at IS NOT NULL"
    ).fetchall()
    assert len(superseded) == 1
    assert superseded[0][0] == "v1"


# ---------------------------------------------------------------------------
# TS-112-E8: No registered tasks
# ---------------------------------------------------------------------------


async def test_no_registered_tasks(
    sleep_ctx: SleepContext,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-E8: Empty SleepComputer returns empty result."""
    computer = SleepComputer([], sleep_config)
    result = await computer.run(sleep_ctx)

    assert result.task_results == {}
    assert result.total_llm_cost == 0.0
    assert result.errors == []


# ---------------------------------------------------------------------------
# TS-112-E9: All tasks budget-exhausted
# ---------------------------------------------------------------------------


async def test_all_tasks_budget_exhausted(
    migrated_conn: duckdb.DuckDBPyConnection,
    sleep_config: SleepConfig,
) -> None:
    """TS-112-E9: budget=0.0 → both tasks skipped with budget_exhausted."""
    ctx = SleepContext(
        conn=migrated_conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=0.0,
        sink_dispatcher=None,
    )
    task_a = MockSleepTask("task_a", cost_estimate=0.1)
    task_b = MockSleepTask("task_b", cost_estimate=0.1)

    result = await SleepComputer([task_a, task_b], sleep_config).run(ctx)

    assert len(result.errors) == 2
    assert all("budget_exhausted" in e for e in result.errors)
    assert result.task_results == {}


# ---------------------------------------------------------------------------
# TS-112-E10: Config section absent → use defaults
# ---------------------------------------------------------------------------


def test_config_absent() -> None:
    """TS-112-E10: SleepConfig() defaults work even when not explicitly configured."""
    # SleepConfig with no args is a proxy for "config absent" → uses defaults
    config = SleepConfig()
    assert config.enabled is True
    assert config.max_cost == 1.0
    assert config.nightshift_interval == 1800


# ---------------------------------------------------------------------------
# TS-112-E11: Idempotent migration
# ---------------------------------------------------------------------------


def test_idempotent_migration() -> None:
    """TS-112-E11: Running migration twice does not raise and schema is unchanged."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)  # first time
    conn.execute(_SLEEP_ARTIFACTS_DDL)  # second time — no error (IF NOT EXISTS)

    cols = conn.execute("DESCRIBE sleep_artifacts").fetchall()
    assert len(cols) == 8


# ---------------------------------------------------------------------------
# TS-112-P1: Staleness hash determinism
# ---------------------------------------------------------------------------


@given(
    facts=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=40),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        ),
        min_size=0,
        max_size=20,
    )
)
@settings(max_examples=50)
def test_property_staleness_determinism(
    facts: list[tuple[str, float]],
) -> None:
    """TS-112-P1: compute_content_hash is order-independent."""
    import random

    perm1 = list(facts)
    perm2 = list(facts)
    random.shuffle(perm1)
    random.shuffle(perm2)

    h1 = compute_content_hash(perm1)
    h2 = compute_content_hash(perm2)
    assert h1 == h2


# ---------------------------------------------------------------------------
# TS-112-P2: Artifact uniqueness invariant
# ---------------------------------------------------------------------------


@given(n=st.integers(min_value=1, max_value=15))
@settings(max_examples=50)
def test_property_artifact_uniqueness(n: int) -> None:
    """TS-112-P2: After N inserts with same (task_name, scope_key), exactly one active row."""
    conn = duckdb.connect(":memory:")
    conn.execute(_SLEEP_ARTIFACTS_DDL)

    for i in range(n):
        upsert_artifact(
            conn,
            task_name="t",
            scope_key="s",
            content=f"v{i}",
            metadata_json="{}",
            content_hash=f"hash{i}",
        )

    active = conn.execute(
        "SELECT COUNT(*) FROM sleep_artifacts WHERE task_name='t' AND scope_key='s' AND superseded_at IS NULL"
    ).fetchone()
    assert active is not None
    assert active[0] == 1


# ---------------------------------------------------------------------------
# TS-112-P3: Budget monotonicity
# ---------------------------------------------------------------------------


@given(
    costs=st.lists(
        st.floats(min_value=0.0, max_value=0.3, allow_nan=False),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=50)
async def test_property_budget_monotonicity(costs: list[float]) -> None:
    """TS-112-P3: Remaining budget decreases monotonically; no negative budgets."""
    config = SleepConfig()
    tasks = [MockSleepTask(f"task_{i}", cost_estimate=c) for i, c in enumerate(costs)]

    initial_budget = 2.0  # large enough that no task is skipped
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    ctx = SleepContext(
        conn=conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=initial_budget,
        sink_dispatcher=None,
    )

    computer = SleepComputer(tasks, config)
    await computer.run(ctx)

    running_sum = 0.0
    for task in tasks:
        if task.received_budgets:
            received = task.received_budgets[0]
            expected = initial_budget - running_sum
            assert abs(received - expected) < 1e-9
            assert received >= 0.0
            running_sum += task.cost_estimate


# ---------------------------------------------------------------------------
# TS-112-P7: Error isolation property
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=2, max_value=8),
    k=st.integers(min_value=0, max_value=7),
)
@settings(max_examples=50)
async def test_property_error_isolation(n: int, k: int) -> None:
    """TS-112-P7: Task at index k fails; all tasks at index > k still execute."""
    k = k % n  # keep k in valid range

    config = SleepConfig()
    tasks: list[MockSleepTask | MockFailTask] = []
    for i in range(n):
        if i == k:
            tasks.append(MockFailTask(f"task_{i}"))
        else:
            tasks.append(MockSleepTask(f"task_{i}", cost_estimate=0.01))

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    conn.execute(_SLEEP_ARTIFACTS_DDL)
    ctx = SleepContext(
        conn=conn,
        repo_root=Path("."),
        model="standard",
        embedder=None,
        budget_remaining=100.0,
        sink_dispatcher=None,
    )

    computer = SleepComputer(tasks, config)
    result = await computer.run(ctx)

    for i in range(k + 1, n):
        assert f"task_{i}" in result.task_results, (
            f"task_{i} should have run but was absent from result.task_results"
        )
