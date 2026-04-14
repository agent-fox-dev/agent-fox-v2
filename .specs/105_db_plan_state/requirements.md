# Requirements Document

## Introduction

This spec replaces agent-fox's file-based plan and execution state management
(`plan.json`, `state.jsonl`) with DuckDB tables. The change eliminates
crash-divergence between state files, removes duplication between
`session_outcomes` and `SessionRecord`, and enables concurrent read access
for CLI commands while the orchestrator runs.

## Glossary

- **Plan node**: A unit of work in the execution graph, identified by
  `{spec_name}:{group_number}`. Maps to one agent session.
- **Plan edge**: A dependency relationship between two plan nodes. The source
  node must complete before the target node can start.
- **Content hash**: A SHA-256 digest of plan structural content (nodes without
  status, edges, topological order). Used to detect when specs have changed
  since the plan was built.
- **Node status**: The execution state of a plan node. One of: `pending`,
  `in_progress`, `completed`, `failed`, `blocked`, `skipped`,
  `cost_blocked`, `merge_blocked`.
- **Run**: A single invocation of `af run`. Tracks aggregate metrics (tokens,
  cost, session count) across all sessions dispatched in that invocation.
- **GraphSync**: The in-memory component that tracks node statuses and
  computes ready tasks. Uses a shared mutable dict loaded from DB.

## Requirements

### Requirement 1: Plan Structure Persistence

**User Story:** As the orchestrator, I want the plan DAG stored in DuckDB
tables, so that plan structure survives crashes without file-based I/O.

#### Acceptance Criteria

[105-REQ-1.1] WHEN the planner produces a `TaskGraph`, THE system SHALL
persist all nodes to a `plan_nodes` table, all edges to a `plan_edges`
table, and plan-level metadata to a `plan_meta` table, within a single
DuckDB transaction.

[105-REQ-1.2] WHEN the orchestrator starts, THE system SHALL load the plan
from DuckDB tables AND return a `TaskGraph` object identical in structure
to what was persisted.

[105-REQ-1.3] THE `plan_nodes` table SHALL store: id, spec_name,
group_number, title, body, archetype, mode, model_tier, status,
subtask_count, optional, instances, sort_position, blocked_reason,
created_at, updated_at.

[105-REQ-1.4] THE `plan_meta` table SHALL store the content hash of the
plan AND return it to the caller for change detection against current specs.

#### Edge Cases

[105-REQ-1.E1] IF no plan exists in the database, THEN `load_plan` SHALL
return `None` (same contract as the current file-based `load_plan`).

[105-REQ-1.E2] IF the plan tables exist but contain zero nodes, THEN
`load_plan` SHALL return a `TaskGraph` with empty nodes, edges, and order.

### Requirement 2: Node Status Management

**User Story:** As the orchestrator, I want node status transitions
persisted atomically to DuckDB, so that a crash never leaves state
inconsistent.

#### Acceptance Criteria

[105-REQ-2.1] WHEN a node's status changes (e.g., pending -> in_progress),
THE system SHALL UPDATE the corresponding `plan_nodes` row's status and
updated_at columns.

[105-REQ-2.2] THE system SHALL support the v3 node status set: `pending`,
`in_progress`, `completed`, `failed`, `blocked`, `skipped`,
`cost_blocked`, `merge_blocked`.

[105-REQ-2.3] WHEN a node is marked as blocked, THE system SHALL store the
blocked reason in the `plan_nodes.blocked_reason` column.

[105-REQ-2.4] THE `_sync_plan_statuses` method SHALL be removed — node
statuses are persisted on each transition, not batch-synced at shutdown.

#### Edge Cases

[105-REQ-2.E1] IF the orchestrator crashes mid-session, THEN on resume THE
system SHALL detect `in_progress` nodes in the database AND reset them to
`pending` (same behavior as the current `_reset_in_progress_tasks`).

### Requirement 3: Session History Unification

**User Story:** As a maintainer, I want session records stored in a single
table, so that there is one source of truth for session history.

#### Acceptance Criteria

[105-REQ-3.1] THE system SHALL extend the `session_outcomes` table with
columns: `run_id` (VARCHAR), `attempt` (INTEGER), `cost` (DOUBLE),
`model` (VARCHAR), `archetype` (VARCHAR), `commit_sha` (VARCHAR),
`error_message` (TEXT), `is_transport_error` (BOOLEAN).

[105-REQ-3.2] WHEN a session completes, THE system SHALL INSERT a row into
`session_outcomes` with all fields populated AND return the inserted record
for caller use.

[105-REQ-3.3] THE `SessionRecord` dataclass and `ExecutionState.session_history`
list SHALL be removed — `session_outcomes` is the sole session store.

#### Edge Cases

[105-REQ-3.E1] IF `error_message` is None (successful session), THEN THE
system SHALL store NULL in the column (not empty string).

### Requirement 4: Run Tracking

**User Story:** As an operator, I want per-run aggregate metrics stored in
the database, so that I can query execution history across runs.

#### Acceptance Criteria

[105-REQ-4.1] THE system SHALL create a `runs` table with columns: `id`
(VARCHAR PK), `plan_content_hash` (VARCHAR), `started_at` (TIMESTAMP),
`completed_at` (TIMESTAMP), `status` (VARCHAR), `total_input_tokens`
(BIGINT), `total_output_tokens` (BIGINT), `total_cost` (DOUBLE),
`total_sessions` (INTEGER).

[105-REQ-4.2] WHEN a run starts, THE system SHALL INSERT a row into `runs`
with status `running` AND return the run_id to the caller.

[105-REQ-4.3] WHEN a session completes, THE system SHALL UPDATE the
corresponding `runs` row to accumulate tokens, cost, and session count.

[105-REQ-4.4] WHEN a run finishes, THE system SHALL UPDATE the `runs` row
with `completed_at` and final status (`completed`, `interrupted`,
`cost_limit`, `session_limit`, `stalled`, `block_limit`).

#### Edge Cases

[105-REQ-4.E1] IF the orchestrator crashes, THEN the `runs` row SHALL
remain with status `running` and `completed_at` NULL. On resume, THE system
SHALL detect the incomplete run and update it rather than creating a
duplicate.

### Requirement 5: State File Removal

**User Story:** As a maintainer, I want `plan.json` and `state.jsonl`
removed from the codebase, so that there is a single state store.

#### Acceptance Criteria

[105-REQ-5.1] THE system SHALL remove the `PLAN_PATH` and `STATE_PATH`
constants from `agent_fox/core/paths.py`.

[105-REQ-5.2] THE system SHALL remove `save_plan(graph, path)` and
`load_plan(path)` file-based implementations from
`agent_fox/graph/persistence.py` AND replace them with DB-based equivalents
that accept a DuckDB connection instead of a file path.

[105-REQ-5.3] THE system SHALL remove the `StateManager` class and all
JSONL append/load logic from `agent_fox/engine/state.py`.

[105-REQ-5.4] THE system SHALL NOT create `plan.json` or `state.jsonl`
files during `af run`, `af plan`, or any other command.

#### Edge Cases

[105-REQ-5.E1] IF legacy `plan.json` or `state.jsonl` files exist on disk,
THEN THE system SHALL ignore them (no import, no error, no deletion).

### Requirement 6: CLI and Concurrent Access

**User Story:** As an operator, I want `af plan` and `af status` to read
state from DuckDB while the orchestrator is running, so that I can monitor
progress without interrupting execution.

#### Acceptance Criteria

[105-REQ-6.1] WHEN `af status` is invoked, THE system SHALL open a
read-only DuckDB connection AND query plan_nodes, session_outcomes, and
runs to render the status dashboard.

[105-REQ-6.2] WHEN `af plan` is invoked, THE system SHALL render a
human-readable view of the plan from DuckDB (no plan.json file needed).

[105-REQ-6.3] THE system SHALL support concurrent read access from CLI
commands while the orchestrator holds the write connection, without
blocking or corrupting either.

#### Edge Cases

[105-REQ-6.E1] IF the DuckDB file does not exist when `af status` is
invoked, THEN THE system SHALL display "No plan found" (not crash).
