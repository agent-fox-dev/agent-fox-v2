"""Execution state persistence: data models, save/load, plan hash, runner utils.

Requirements: 04-REQ-4.1, 04-REQ-4.2, 04-REQ-4.3,
              105-REQ-2.1, 105-REQ-2.3, 105-REQ-2.E1,
              105-REQ-3.2, 105-REQ-3.E1,
              105-REQ-4.2, 105-REQ-4.3, 105-REQ-4.4, 105-REQ-4.E1
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


class RunStatus(StrEnum):
    """Overall orchestrator run status."""

    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    COST_LIMIT = "cost_limit"
    SESSION_LIMIT = "session_limit"
    STALLED = "stalled"
    BLOCK_LIMIT = "block_limit"


@dataclass
class SessionRecord:
    """Record of a single session attempt."""

    node_id: str
    attempt: int  # 1-indexed attempt number
    status: str  # "completed" | "failed"
    input_tokens: int
    output_tokens: int
    cost: float
    duration_ms: int
    error_message: str | None
    timestamp: str  # ISO 8601
    model: str = ""  # Model ID used for this session
    files_touched: list[str] = field(default_factory=list)
    archetype: str = "coder"  # Archetype name; defaults for backward compat
    commit_sha: str = ""  # develop HEAD after harvest (empty if no code merged)
    is_transport_error: bool = False  # True when failure was a transient connection error


@dataclass
class SessionOutcomeRecord:
    """Unified session record written directly to the session_outcomes DB table.

    Replaces the legacy SessionRecord + ExecutionState.session_history pattern.
    All fields map 1:1 to session_outcomes columns (including the extended
    columns added by the v11 migration).

    Requirements: 105-REQ-3.1, 105-REQ-3.2
    """

    id: str
    spec_name: str
    task_group: str
    node_id: str
    touched_path: str  # comma-separated or first file
    status: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    created_at: str  # ISO 8601
    run_id: str
    attempt: int
    cost: float
    model: str
    archetype: str
    commit_sha: str
    error_message: str | None  # SQL NULL for successful sessions (REQ-3.E1)
    is_transport_error: bool


@dataclass
class RunRecord:
    """Record of a single orchestrator run, persisted to the runs DB table.

    Requirements: 105-REQ-4.1
    """

    id: str
    plan_content_hash: str
    started_at: str  # ISO 8601
    completed_at: str | None  # None until run finishes
    status: str  # RunStatus value
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    total_sessions: int


@dataclass
class ExecutionState:
    """Full execution state, persisted after every session."""

    plan_hash: str  # SHA-256 of plan.json
    node_states: dict[str, str]  # node_id -> NodeStatus value
    session_history: list[SessionRecord] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_sessions: int = 0
    started_at: str = ""  # ISO 8601
    updated_at: str = ""  # ISO 8601
    run_status: str = "running"
    blocked_reasons: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Runner invocation helper (used by serial and parallel runners)
# ---------------------------------------------------------------------------


async def invoke_runner(
    runner: Any,
    node_id: str,
    attempt: int,
    previous_error: str | None,
) -> SessionRecord:
    """Invoke a session runner and normalise the result to SessionRecord.

    Supports runners that expose an ``execute()`` method as well as
    plain callables.  If the return value is already a SessionRecord
    it is returned unchanged; otherwise a conversion is attempted.
    """
    if hasattr(runner, "execute") and callable(runner.execute):
        result = await runner.execute(node_id, attempt, previous_error)
    else:
        result = await runner(node_id, attempt, previous_error)

    if isinstance(result, SessionRecord):
        return result

    return SessionRecord(
        node_id=result.node_id,
        attempt=attempt,
        status=result.status,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost=result.cost,
        duration_ms=result.duration_ms,
        error_message=result.error_message,
        timestamp=getattr(result, "timestamp", ""),
        model=getattr(result, "model", ""),
        files_touched=getattr(result, "files_touched", []),
        archetype=getattr(result, "archetype", "coder"),
        is_transport_error=getattr(result, "is_transport_error", False),
    )


# ---------------------------------------------------------------------------
# Standalone state functions (replacing StateManager — 105-REQ-5.3)
# ---------------------------------------------------------------------------


def update_state_with_session(
    state: ExecutionState,
    record: SessionRecord,
) -> ExecutionState:
    """Update in-memory state with a completed session record.

    Standalone replacement for ``StateManager.record_session()``.
    Flushes auxiliary token accumulator and adds to totals.

    Requirements: 34-REQ-1.3, 34-REQ-1.4, 105-REQ-5.3
    """
    from agent_fox.core.config import PricingConfig
    from agent_fox.core.models import calculate_cost
    from agent_fox.core.token_tracker import flush_auxiliary_usage

    aux_entries = flush_auxiliary_usage()
    aux_input = sum(e.input_tokens for e in aux_entries)
    aux_output = sum(e.output_tokens for e in aux_entries)
    aux_cost = 0.0
    if aux_entries:
        pricing = PricingConfig()
        for entry in aux_entries:
            aux_cost += calculate_cost(
                entry.input_tokens,
                entry.output_tokens,
                entry.model,
                pricing,
            )

    state.session_history.append(record)
    state.total_input_tokens += record.input_tokens + aux_input
    state.total_output_tokens += record.output_tokens + aux_output
    state.total_cost += record.cost + aux_cost
    state.total_sessions += 1
    state.updated_at = datetime.now(UTC).isoformat()
    return state


def compute_plan_hash_from_file(plan_path: Path) -> str:
    """Compute SHA-256 hash of plan.json structural content.

    Standalone replacement for ``StateManager.compute_plan_hash()``.
    Hashes only structural fields (node IDs, edges, order), excluding
    mutable fields like node ``status``.

    Requirements: 105-REQ-5.3
    """
    data = json.loads(plan_path.read_text(encoding="utf-8"))

    nodes = data.get("nodes", {})
    structural_nodes = {}
    for nid, node in sorted(nodes.items()):
        structural_nodes[nid] = {k: v for k, v in sorted(node.items()) if k != "status"}

    canonical = {
        "nodes": structural_nodes,
        "edges": data.get("edges", []),
        "order": data.get("order", []),
    }
    from agent_fox.core.models import content_hash

    content = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return content_hash(content)


def load_state_from_db(
    conn: duckdb.DuckDBPyConnection,
) -> ExecutionState | None:
    """Reconstruct an ExecutionState from DB tables.

    Loads node_states from plan_nodes, session history from
    session_outcomes, blocked reasons, and run totals. Returns None
    if no plan data exists in the database.

    Requirements: 105-REQ-5.3
    """
    # Load node states from plan_nodes
    try:
        rows = conn.sql("SELECT id, status FROM plan_nodes").fetchall()
    except Exception:
        return None
    if not rows:
        return None
    node_states = {row[0]: row[1] for row in rows}

    # Load blocked reasons
    blocked_reasons: dict[str, str] = {}
    try:
        br_rows = conn.sql("SELECT id, blocked_reason FROM plan_nodes WHERE blocked_reason IS NOT NULL").fetchall()
        blocked_reasons = {row[0]: row[1] for row in br_rows}
    except Exception:
        pass

    # Load session history from session_outcomes
    session_history: list[SessionRecord] = []
    try:
        so_rows = conn.sql(
            """
            SELECT node_id, attempt, status, input_tokens, output_tokens,
                   cost, duration_ms, error_message, created_at, model,
                   touched_path, archetype, commit_sha, is_transport_error
            FROM session_outcomes
            ORDER BY created_at
            """
        ).fetchall()
        for row in so_rows:
            files = row[10].split(",") if row[10] else []
            ts = str(row[8]) if row[8] else ""
            if hasattr(row[8], "isoformat"):
                ts = row[8].isoformat()
            session_history.append(
                SessionRecord(
                    node_id=row[0],
                    attempt=row[1] or 1,
                    status=row[2],
                    input_tokens=row[3] or 0,
                    output_tokens=row[4] or 0,
                    cost=row[5] or 0.0,
                    duration_ms=row[6] or 0,
                    error_message=row[7],
                    timestamp=ts,
                    model=row[9] or "",
                    files_touched=files,
                    archetype=row[11] or "coder",
                    commit_sha=row[12] or "",
                    is_transport_error=bool(row[13]),
                )
            )
    except Exception:
        pass

    # Load run totals from most recent run
    plan_hash = ""
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    total_sessions = 0
    started_at = ""
    updated_at = ""
    run_status = "running"

    try:
        run_row = conn.sql(
            """
            SELECT plan_content_hash, started_at, completed_at, status,
                   total_input_tokens, total_output_tokens, total_cost,
                   total_sessions
            FROM runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        if run_row:
            plan_hash = run_row[0] or ""
            sa = run_row[1]
            started_at = sa.isoformat() if hasattr(sa, "isoformat") else str(sa or "")
            ca = run_row[2]
            updated_at = ca.isoformat() if hasattr(ca, "isoformat") else (str(ca) if ca else started_at)
            run_status = run_row[3] or "running"
            total_input_tokens = run_row[4] or 0
            total_output_tokens = run_row[5] or 0
            total_cost = run_row[6] or 0.0
            total_sessions = run_row[7] or 0
    except Exception:
        pass

    # Try plan_meta for plan_hash if not available from runs
    if not plan_hash:
        try:
            meta_row = conn.sql("SELECT content_hash FROM plan_meta LIMIT 1").fetchone()
            if meta_row:
                plan_hash = meta_row[0] or ""
        except Exception:
            pass

    return ExecutionState(
        plan_hash=plan_hash,
        node_states=node_states,
        session_history=session_history,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at=started_at,
        updated_at=updated_at,
        run_status=run_status,
        blocked_reasons=blocked_reasons,
    )


# ---------------------------------------------------------------------------
# DB-based state management (new API — 105 spec)
# ---------------------------------------------------------------------------


def persist_node_status(
    conn: duckdb.DuckDBPyConnection,
    node_id: str,
    status: str,
    blocked_reason: str | None = None,
) -> None:
    """UPDATE plan_nodes SET status, updated_at (and optionally blocked_reason).

    Requirements: 105-REQ-2.1, 105-REQ-2.3
    """
    conn.execute(
        """
        UPDATE plan_nodes
        SET status = ?,
            updated_at = CURRENT_TIMESTAMP,
            blocked_reason = ?
        WHERE id = ?
        """,
        [status, blocked_reason, node_id],
    )


def load_execution_state(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Load node_states dict from plan_nodes for GraphSync initialization.

    Returns a mapping of node_id -> status string.  Returns an empty dict
    if the plan_nodes table is empty or the table does not exist.

    Requirements: 105-REQ-1.E1, 105-REQ-1.E2
    """
    try:
        rows = conn.sql("SELECT id, status FROM plan_nodes").fetchall()
    except Exception:
        return {}
    return {row[0]: row[1] for row in rows}


def reset_in_progress_nodes(conn: duckdb.DuckDBPyConnection) -> None:
    """Reset all in_progress nodes to pending (crash recovery on resume).

    Requirements: 105-REQ-2.E1
    """
    conn.execute(
        """
        UPDATE plan_nodes
        SET status = 'pending',
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'in_progress'
        """
    )


def record_session(
    conn: duckdb.DuckDBPyConnection,
    record: SessionOutcomeRecord,
) -> None:
    """INSERT a session outcome row into session_outcomes with all extended fields.

    Stores NULL for error_message when the session succeeded (not empty string).

    Requirements: 105-REQ-3.2, 105-REQ-3.E1
    """
    conn.execute(
        """
        INSERT INTO session_outcomes (
            id, spec_name, task_group, node_id, touched_path,
            status, input_tokens, output_tokens, duration_ms, created_at,
            run_id, attempt, cost, model, archetype,
            commit_sha, error_message, is_transport_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            record.id,
            record.spec_name,
            record.task_group,
            record.node_id,
            record.touched_path,
            record.status,
            record.input_tokens,
            record.output_tokens,
            record.duration_ms,
            record.created_at,
            record.run_id,
            record.attempt,
            record.cost,
            record.model,
            record.archetype,
            record.commit_sha,
            record.error_message,  # None -> SQL NULL (REQ-3.E1)
            record.is_transport_error,
        ],
    )


def create_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    plan_hash: str,
) -> None:
    """INSERT a new run row with status='running'.

    Requirements: 105-REQ-4.2
    """
    conn.execute(
        """
        INSERT INTO runs (id, plan_content_hash, status)
        VALUES (?, ?, 'running')
        """,
        [run_id, plan_hash],
    )


def update_run_totals(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
) -> None:
    """UPDATE runs to accumulate token and cost counters.

    Requirements: 105-REQ-4.3
    """
    conn.execute(
        """
        UPDATE runs
        SET total_input_tokens  = total_input_tokens  + ?,
            total_output_tokens = total_output_tokens + ?,
            total_cost          = total_cost          + ?,
            total_sessions      = total_sessions      + 1
        WHERE id = ?
        """,
        [input_tokens, output_tokens, cost, run_id],
    )


def complete_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    status: str,
) -> None:
    """UPDATE runs SET completed_at, status to mark a run as finished.

    Requirements: 105-REQ-4.4
    """
    conn.execute(
        """
        UPDATE runs
        SET completed_at = CURRENT_TIMESTAMP,
            status = ?
        WHERE id = ?
        """,
        [status, run_id],
    )


def load_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str | None = None,
) -> RunRecord | None:
    """Load the most recent run, or a specific run by ID.

    Requirements: 105-REQ-4.1
    """
    if run_id is not None:
        row = conn.execute(
            """
            SELECT id, plan_content_hash, started_at, completed_at, status,
                   total_input_tokens, total_output_tokens, total_cost, total_sessions
            FROM runs WHERE id = ?
            """,
            [run_id],
        ).fetchone()
    else:
        row = conn.sql(
            """
            SELECT id, plan_content_hash, started_at, completed_at, status,
                   total_input_tokens, total_output_tokens, total_cost, total_sessions
            FROM runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    def _ts(v: Any) -> str | None:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    return RunRecord(
        id=row[0],
        plan_content_hash=row[1],
        started_at=_ts(row[2]) or "",
        completed_at=_ts(row[3]),
        status=row[4],
        total_input_tokens=row[5],
        total_output_tokens=row[6],
        total_cost=row[7],
        total_sessions=row[8],
    )


def load_incomplete_run(
    conn: duckdb.DuckDBPyConnection,
) -> RunRecord | None:
    """Load the most recent run that has status='running' and no completed_at.

    Used on orchestrator resume to detect a crashed run.

    Requirements: 105-REQ-4.E1
    """
    row = conn.sql(
        """
        SELECT id, plan_content_hash, started_at, completed_at, status,
               total_input_tokens, total_output_tokens, total_cost, total_sessions
        FROM runs
        WHERE status = 'running' AND completed_at IS NULL
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    def _ts(v: Any) -> str | None:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    return RunRecord(
        id=row[0],
        plan_content_hash=row[1],
        started_at=_ts(row[2]) or "",
        completed_at=_ts(row[3]),
        status=row[4],
        total_input_tokens=row[5],
        total_output_tokens=row[6],
        total_cost=row[7],
        total_sessions=row[8],
    )
