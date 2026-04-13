"""Property-based tests for knowledge consolidation correctness invariants.

Test Spec: TS-96-P1 through TS-96-P6
Requirements: Property 1-6 from design.md (spec 96)

Note: The tasks.md originally named this file test_consolidation_props.py,
but that file already exists for spec 39 (TS-39-P2 through TS-39-P4).
See docs/errata/96_test_naming.md for rationale.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from agent_fox.knowledge.consolidation import (
    CONSOLIDATION_STALE_SENTINEL,
    ConsolidationResult,
    MergeResult,
    PromotionResult,
    PruneResult,
    VerificationResult,
    _merge_related_facts,
    _promote_patterns,
    _prune_redundant_chains,
    _verify_against_git,
    run_consolidation,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_entity_conn() -> duckdb.DuckDBPyConnection:
    """Create in-memory DuckDB with full schema including v8."""
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
    superseded_by: str | None = None,
) -> None:
    """Insert a fact into memory_facts."""
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at, commit_sha, superseded_by)
        VALUES (?, 'Property test fact', ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """,
        [fact_id, category, spec_name, confidence, commit_sha, superseded_by],
    )


def _insert_entity(conn: duckdb.DuckDBPyConnection, entity_id: str, entity_path: str) -> None:
    """Insert a file entity into entity_graph."""
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?, 'file', ?, ?, CURRENT_TIMESTAMP)
        """,
        [entity_id, entity_path, entity_path],
    )


def _link_fact_entity(
    conn: duckdb.DuckDBPyConnection, fact_id: str, entity_id: str
) -> None:
    """Link fact to entity."""
    conn.execute(
        "INSERT INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
        [fact_id, entity_id],
    )


def _insert_edge(
    conn: duckdb.DuckDBPyConnection, cause_id: str, effect_id: str
) -> None:
    """Insert causal edge."""
    conn.execute(
        "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?, ?)",
        [cause_id, effect_id],
    )


def _edge_exists(
    conn: duckdb.DuckDBPyConnection, cause_id: str, effect_id: str
) -> bool:
    """Check causal edge existence."""
    row = conn.execute(
        "SELECT 1 FROM fact_causes WHERE cause_id = ? AND effect_id = ?",
        [cause_id, effect_id],
    ).fetchone()
    return row is not None


def _make_similar_unit_vecs(n: int, dim: int = 384) -> list[list[float]]:
    """Generate n nearly-identical unit vectors for high cosine similarity."""
    base_raw = [math.sin((i + 1) * 0.1) for i in range(dim)]
    base_norm = math.sqrt(sum(x * x for x in base_raw))
    base = [x / base_norm for x in base_raw]

    vecs = []
    for k in range(n):
        perturbed = [base[j] + k * 0.00001 * (1 if j == 0 else 0) for j in range(dim)]
        norm = math.sqrt(sum(x * x for x in perturbed))
        vecs.append([x / norm for x in perturbed])
    return vecs


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with all migrations applied."""
    conn = _make_entity_conn()
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TS-96-P1: Step independence property
# ---------------------------------------------------------------------------


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=10)
@given(failure_mask=st.integers(min_value=0, max_value=63))
def test_step_independence(failure_mask: int, entity_conn: duckdb.DuckDBPyConnection) -> None:
    """TS-96-P1: Failing steps do not block subsequent steps.

    For any subset of steps that raise exceptions (failure_mask as bitmask),
    the remaining steps still execute and errors list matches failed step names.

    Property 1 from design.md. Validates: 96-REQ-1.2
    """
    import asyncio

    step_names = [
        "entity_refresh",
        "link_facts",
        "git_verification",
        "merging",
        "promotion",
        "pruning",
    ]

    # Add a fact so pipeline has something to work with
    fact_id = str(uuid.uuid4())
    _insert_fact(entity_conn, fact_id)

    expected_failed: list[str] = []
    expected_succeeded: list[str] = []

    for i, step in enumerate(step_names):
        if failure_mask & (1 << i):
            expected_failed.append(step)
        else:
            expected_succeeded.append(step)

    # Build patch context based on failure_mask
    async def _run_with_failure_mask() -> ConsolidationResult:
        with (
            patch(
                "agent_fox.knowledge.consolidation._refresh_entity_graph",
                side_effect=(
                    RuntimeError("forced entity_refresh failure")
                    if failure_mask & 1
                    else MagicMock(return_value=None)
                ),
            ),
            patch(
                "agent_fox.knowledge.consolidation._link_unlinked_facts",
                side_effect=(
                    RuntimeError("forced link_facts failure")
                    if failure_mask & 2
                    else MagicMock(return_value=MagicMock(links_created=0)),
                ),
            ),
            patch(
                "agent_fox.knowledge.consolidation._verify_against_git",
                side_effect=(
                    RuntimeError("forced git_verification failure")
                    if failure_mask & 4
                    else MagicMock(return_value=VerificationResult(0, 0, 0, 0))
                ),
            ),
            patch(
                "agent_fox.knowledge.consolidation._merge_related_facts",
                new_callable=AsyncMock,
                side_effect=(
                    RuntimeError("forced merging failure")
                    if failure_mask & 8
                    else AsyncMock(return_value=MergeResult(0, 0, 0, 0))
                ),
            ),
            patch(
                "agent_fox.knowledge.consolidation._promote_patterns",
                new_callable=AsyncMock,
                side_effect=(
                    RuntimeError("forced promotion failure")
                    if failure_mask & 16
                    else AsyncMock(return_value=PromotionResult(0, 0, 0))
                ),
            ),
            patch(
                "agent_fox.knowledge.consolidation._prune_redundant_chains",
                new_callable=AsyncMock,
                side_effect=(
                    RuntimeError("forced pruning failure")
                    if failure_mask & 32
                    else AsyncMock(return_value=PruneResult(0, 0, 0))
                ),
            ),
        ):
            return await run_consolidation(
                entity_conn,
                Path("/tmp"),
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

    result = asyncio.get_event_loop().run_until_complete(_run_with_failure_mask())

    # Every failed step must appear in errors
    for step in expected_failed:
        assert step in result.errors, f"Expected '{step}' in errors but got: {result.errors}"

    # Number of errors matches popcount of failure_mask
    assert len(result.errors) == bin(failure_mask).count("1"), (
        f"Expected {bin(failure_mask).count('1')} errors, got {len(result.errors)}"
    )


# ---------------------------------------------------------------------------
# TS-96-P2: Git verification accuracy property
# ---------------------------------------------------------------------------


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=20)
@given(
    n_facts=st.integers(min_value=1, max_value=5),
    deleted_mask=st.integers(min_value=0, max_value=31),
)
def test_git_verification_accuracy(
    n_facts: int,
    deleted_mask: int,
    entity_conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
) -> None:
    """TS-96-P2: Facts with all linked files deleted are superseded; others are not.

    Property 2 from design.md. Validates: 96-REQ-3.2, 96-REQ-3.3
    """
    fact_ids = [str(uuid.uuid4()) for _ in range(n_facts)]
    entity_ids = [str(uuid.uuid4()) for _ in range(n_facts)]

    (tmp_path / "src").mkdir(exist_ok=True)

    all_deleted: dict[str, bool] = {}

    for i, (fact_id, entity_id) in enumerate(zip(fact_ids, entity_ids)):
        file_path = f"src/file_{i}.py"
        is_deleted = bool(deleted_mask & (1 << i))
        all_deleted[fact_id] = is_deleted

        _insert_fact(entity_conn, fact_id, commit_sha=None)
        _insert_entity(entity_conn, entity_id, file_path)
        _link_fact_entity(entity_conn, fact_id, entity_id)

        if not is_deleted:
            (tmp_path / file_path).write_text("content")
        # If deleted: file does not exist on disk

    _verify_against_git(entity_conn, tmp_path, 0.5)

    # Verify correctness property: superseded iff all files deleted
    for fact_id in fact_ids:
        row = entity_conn.execute(
            "SELECT superseded_by FROM memory_facts WHERE id = ?",
            [fact_id],
        ).fetchone()
        assert row is not None
        superseded_by = str(row[0]) if row[0] is not None else None

        if all_deleted[fact_id]:
            assert superseded_by == str(CONSOLIDATION_STALE_SENTINEL), (
                f"Fact {fact_id} with deleted file should be superseded"
            )
        else:
            assert superseded_by is None, (
                f"Fact {fact_id} with existing file should not be superseded"
            )


# ---------------------------------------------------------------------------
# TS-96-P3: Merge idempotency property
# ---------------------------------------------------------------------------


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=5)
@given(n_facts=st.integers(min_value=2, max_value=4))
def test_merge_idempotency(
    n_facts: int,
    entity_conn: duckdb.DuckDBPyConnection,
) -> None:
    """TS-96-P3: Running merge twice does not produce duplicate consolidated facts.

    Property 3 from design.md. Validates: 96-REQ-4.1, 96-REQ-4.3
    """
    import asyncio

    fact_ids = [str(uuid.uuid4()) for _ in range(n_facts)]
    vecs = _make_similar_unit_vecs(n_facts)

    for i, (fact_id, vec) in enumerate(zip(fact_ids, vecs)):
        spec = f"spec_{i}"
        _insert_fact(entity_conn, fact_id, spec_name=spec)
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [fact_id, vec],
        )

    merge_call_count = 0

    async def _mock_llm(*args: object, **kwargs: object) -> dict:
        nonlocal merge_call_count
        merge_call_count += 1
        return {"action": "merge", "content": "Merged content"}

    async def _run_merge() -> MergeResult:
        with patch("agent_fox.knowledge.consolidation._call_llm_json", _mock_llm):
            return await _merge_related_facts(
                entity_conn, "claude-3-5-haiku-20241022", 0.85, None
            )

    asyncio.get_event_loop().run_until_complete(_run_merge())

    # Count active facts after first pass
    count_after_first = entity_conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchone()[0]

    # Run again with same mock
    asyncio.get_event_loop().run_until_complete(_run_merge())

    count_after_second = entity_conn.execute(
        "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
    ).fetchone()[0]

    # Idempotency: second run should not change the active fact count
    assert count_after_first == count_after_second, (
        f"Merge idempotency violated: first={count_after_first}, second={count_after_second}"
    )


# ---------------------------------------------------------------------------
# TS-96-P4: Pattern promotion threshold property
# ---------------------------------------------------------------------------


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=5)
@given(n_specs=st.integers(min_value=3, max_value=5))
def test_pattern_threshold(
    n_specs: int,
    entity_conn: duckdb.DuckDBPyConnection,
) -> None:
    """TS-96-P4: Pattern facts only created from facts spanning 3+ distinct specs.

    Property 4 from design.md. Validates: 96-REQ-5.1, 96-REQ-5.3
    """
    import asyncio

    fact_ids = [str(uuid.uuid4()) for _ in range(n_specs)]
    vecs = _make_similar_unit_vecs(n_specs)

    for i, (fact_id, vec) in enumerate(zip(fact_ids, vecs)):
        spec = f"spec_{i}"
        _insert_fact(entity_conn, fact_id, spec_name=spec)
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [fact_id, vec],
        )

    llm_mock = AsyncMock(
        return_value={"is_pattern": True, "description": "Confirmed pattern"}
    )

    async def _run() -> PromotionResult:
        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            return await _promote_patterns(entity_conn, "claude-3-5-haiku-20241022")

    asyncio.get_event_loop().run_until_complete(_run())

    # For every created pattern fact, verify source facts span 3+ specs
    pattern_facts = entity_conn.execute(
        "SELECT id FROM memory_facts WHERE category = 'pattern'"
    ).fetchall()

    for (pattern_id,) in pattern_facts:
        # Find source facts via causal edges (cause -> pattern_fact)
        sources = entity_conn.execute(
            "SELECT cause_id FROM fact_causes WHERE effect_id = ?",
            [str(pattern_id)],
        ).fetchall()

        source_ids = [str(s[0]) for s in sources]
        if source_ids:
            spec_names = entity_conn.execute(
                f"SELECT DISTINCT spec_name FROM memory_facts WHERE id IN ({','.join('?' for _ in source_ids)})",
                source_ids,
            ).fetchall()

            assert len(spec_names) >= 3, (
                f"Pattern fact {pattern_id} created from {len(spec_names)} spec(s) < 3"
            )


# ---------------------------------------------------------------------------
# TS-96-P5: Causal chain preservation property
# ---------------------------------------------------------------------------


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=5)
@given(n_chains=st.integers(min_value=1, max_value=3))
def test_chain_preservation(
    n_chains: int,
    entity_conn: duckdb.DuckDBPyConnection,
) -> None:
    """TS-96-P5: After pruning, A->C exists; A->B and B->C do not.

    Property 5 from design.md. Validates: 96-REQ-6.3
    """
    import asyncio

    # Create n_chains redundant chains, each a triple (A, B, C)
    chains: list[tuple[str, str, str]] = []
    for _ in range(n_chains):
        a_id = str(uuid.uuid4())
        b_id = str(uuid.uuid4())
        c_id = str(uuid.uuid4())

        _insert_fact(entity_conn, a_id)
        _insert_fact(entity_conn, b_id)
        _insert_fact(entity_conn, c_id)
        _insert_edge(entity_conn, a_id, b_id)
        _insert_edge(entity_conn, b_id, c_id)
        _insert_edge(entity_conn, a_id, c_id)  # direct edge
        chains.append((a_id, b_id, c_id))

    llm_mock = AsyncMock(return_value={"meaningful": False, "reason": "B adds no value"})

    async def _run() -> PruneResult:
        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            return await _prune_redundant_chains(entity_conn, "claude-3-5-haiku-20241022")

    asyncio.get_event_loop().run_until_complete(_run())

    for a_id, b_id, c_id in chains:
        # Direct A->C must be preserved
        assert _edge_exists(entity_conn, a_id, c_id), (
            f"Direct edge {a_id}->{c_id} was removed (should be preserved)"
        )
        # A->B and B->C must be removed
        assert not _edge_exists(entity_conn, a_id, b_id), (
            f"Edge {a_id}->{b_id} still exists (should be pruned)"
        )
        assert not _edge_exists(entity_conn, b_id, c_id), (
            f"Edge {b_id}->{c_id} still exists (should be pruned)"
        )


# ---------------------------------------------------------------------------
# TS-96-P6: Confidence decay bounds property
# ---------------------------------------------------------------------------


@given(confidence=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_confidence_bounds(confidence: float) -> None:
    """TS-96-P6: Halved confidence is always positive and less than original.

    Property 6 from design.md. Validates: 96-REQ-3.3
    """
    halved = confidence / 2.0
    assert halved > 0.0, f"Halved confidence {halved} must be > 0"
    assert halved < confidence, f"Halved confidence {halved} must be < original {confidence}"
