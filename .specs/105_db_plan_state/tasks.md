# Implementation Plan: DB-Based Plan State

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation replaces file-based plan and execution state with DuckDB
tables in five groups: tests first, then schema migration, then persistence
layer swap, then CLI updates and file removal, and finally wiring
verification. The in-memory GraphSync pattern is preserved — only the
persistence backing changes.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_db_plan_state.py tests/unit/graph/test_db_persistence.py tests/property/engine/test_plan_state_props.py tests/integration/test_db_plan_state_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create unit test file for DB persistence
    - Create `tests/unit/graph/test_db_persistence.py`
    - Translate TS-105-1, TS-105-2, TS-105-3 into pytest tests
    - Tests import from `agent_fox.graph.persistence` (save_plan, load_plan
      with conn parameter — does not exist yet)
    - Use in-memory DuckDB fixtures with v9 schema
    - _Test Spec: TS-105-1, TS-105-2, TS-105-3_

  - [ ] 1.2 Create unit test file for DB state management
    - Create `tests/unit/engine/test_db_plan_state.py`
    - Translate TS-105-4 through TS-105-12 into pytest tests
    - Tests import from `agent_fox.engine.state` (new function signatures)
    - Include edge case tests TS-105-E1 through TS-105-E6
    - _Test Spec: TS-105-4 through TS-105-12, TS-105-E1 through TS-105-E6_

  - [ ] 1.3 Create property tests
    - Create `tests/property/engine/test_plan_state_props.py`
    - Translate TS-105-P1 through TS-105-P5
    - Use Hypothesis strategies for TaskGraph generation, status sequences,
      session records, token/cost delta sequences
    - _Test Spec: TS-105-P1 through TS-105-P5_

  - [ ] 1.4 Create integration smoke tests
    - Create `tests/integration/test_db_plan_state_smoke.py`
    - Translate TS-105-SMOKE-1 and TS-105-SMOKE-2
    - SMOKE-1 uses mock session runner with real DB persistence
    - SMOKE-2 uses file-based DuckDB for concurrent access testing
    - _Test Spec: TS-105-SMOKE-1, TS-105-SMOKE-2_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [ ] 2. Schema migration and data types
  - [ ] 2.1 Add v9 migration to `agent_fox/knowledge/migrations.py`
    - Create `plan_nodes`, `plan_edges`, `plan_meta`, `runs` tables
    - ALTER `session_outcomes` to add extended columns
    - Migration runs within a transaction
    - _Requirements: 1.3, 3.1, 4.1_

  - [ ] 2.2 Add v3 status values to `NodeStatus` enum
    - Add `COST_BLOCKED = "cost_blocked"` and
      `MERGE_BLOCKED = "merge_blocked"` to `agent_fox/graph/types.py`
    - _Requirements: 2.2_

  - [ ] 2.3 Create `SessionOutcomeRecord` dataclass
    - Define in `agent_fox/engine/state.py` (or a shared types module)
    - Unified record with all session_outcomes columns
    - _Requirements: 3.1, 3.2_

  - [ ] 2.4 Create `RunRecord` dataclass
    - Define alongside `SessionOutcomeRecord`
    - Matches `runs` table columns
    - _Requirements: 4.1_

  - [ ] 2.V Verify task group 2
    - [ ] Migration applies cleanly: `uv run pytest -q tests/unit/knowledge/ -k migration`
    - [ ] NodeStatus enum has all 8 values
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`

- [ ] 3. Plan and execution state persistence
  - [ ] 3.1 Implement DB-based `save_plan(graph, conn)`
    - DELETE existing plan data, INSERT nodes/edges/meta in one transaction
    - Compute and store content hash
    - Replaces file-based save_plan
    - _Requirements: 1.1, 1.4_

  - [ ] 3.2 Implement DB-based `load_plan(conn)`
    - SELECT from plan_nodes, plan_edges, plan_meta
    - Reconstruct TaskGraph with correct topological order
    - Return None if no plan exists
    - _Requirements: 1.2, 1.E1, 1.E2_

  - [ ] 3.3 Implement `persist_node_status(conn, node_id, status, blocked_reason)`
    - UPDATE plan_nodes SET status, updated_at, blocked_reason
    - _Requirements: 2.1, 2.3_

  - [ ] 3.4 Implement `record_session(conn, record)` and run functions
    - INSERT into session_outcomes with all extended fields
    - Implement `create_run`, `update_run_totals`, `complete_run`,
      `load_run`, `load_incomplete_run`
    - Implement `load_execution_state` (returns node_states dict)
    - _Requirements: 3.2, 4.2, 4.3, 4.4_

  - [ ] 3.5 Implement `reset_in_progress_nodes(conn)`
    - UPDATE plan_nodes SET status='pending' WHERE status='in_progress'
    - Used on resume after crash
    - _Requirements: 2.E1_

  - [ ] 3.V Verify task group 3
    - [ ] Plan round-trip tests pass: `uv run pytest -q tests/unit/graph/test_db_persistence.py`
    - [ ] State management tests pass: `uv run pytest -q tests/unit/engine/test_db_plan_state.py`
    - [ ] Property tests pass: `uv run pytest -q tests/property/engine/test_plan_state_props.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 1.*, 2.*, 3.*, 4.* acceptance criteria met

- [ ] 4. CLI updates, orchestrator wiring, and file removal
  - [ ] 4.1 Update `engine/engine.py` orchestrator
    - `_init_run`: use `load_plan(conn)` instead of `load_plan(plan_path)`
    - `_init_run`: use `create_run(conn, ...)` instead of StateManager
    - Remove `_sync_plan_statuses` method entirely
    - Pass conn through to result handler for `persist_node_status` and
      `record_session` calls
    - Update `_load_or_init_state` to use `load_execution_state(conn)`
    - _Requirements: 2.4, 5.2, 5.3_

  - [ ] 4.2 Update `cli/plan.py`
    - Use `save_plan(graph, conn)` with DuckDB connection
    - Render plan summary from DB, not from file
    - _Requirements: 5.2, 6.2_

  - [ ] 4.3 Update `cli/status.py`
    - Open read-only DuckDB connection for status queries
    - Query plan_nodes, session_outcomes, runs instead of files
    - Handle missing DB gracefully
    - _Requirements: 6.1, 6.E1_

  - [ ] 4.4 Remove file-based state code
    - Remove `PLAN_PATH` and `STATE_PATH` from `core/paths.py`
    - Remove file-based `save_plan(graph, path)` and `load_plan(path)` if
      still present (replaced by DB versions in 3.1/3.2)
    - Remove `StateManager` class and JSONL logic from `engine/state.py`
    - Remove `SessionRecord` dataclass and `ExecutionState.session_history`
    - Remove `compute_plan_hash(path)` (replaced by
      `compute_plan_hash(graph)`)
    - _Requirements: 5.1, 5.3_

  - [ ] 4.5 Update all remaining imports and tests
    - Search for imports of removed classes/functions across codebase
    - Update or remove imports in test files and production code
    - Update existing orchestrator tests to use DB fixtures instead of
      file-based state
    - _Requirements: 5.4, 5.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Integration smoke tests pass: `uv run pytest -q tests/integration/test_db_plan_state_smoke.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] `grep -r "PLAN_PATH\|STATE_PATH\|StateManager\|state\.jsonl\|plan\.json" agent_fox/` returns zero matches (excluding comments)
    - [ ] Requirements 5.*, 6.* acceptance criteria met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1: `plan_cmd` -> `build_plan` -> `save_plan(graph, conn)` ->
      DuckDB tables populated. Confirm no file I/O.
    - Path 2: `_init_run` -> `load_plan(conn)` -> `create_run(conn)` ->
      `GraphSync(node_states)`. Confirm state loaded from DB.
    - Path 3: session complete -> `mark_completed` ->
      `persist_node_status(conn)` -> `record_session(conn)` ->
      `update_run_totals(conn)`. Confirm DB updated.
    - Path 4: `status_cmd` -> read-only conn -> SELECT queries. Confirm
      no file reads.
    - Path 5: resume -> `load_plan(conn)` -> compare content hash with
      `plan_meta.content_hash`. Confirm works without plan.json.
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - `load_plan(conn)` returns `TaskGraph` consumed by orchestrator
    - `load_execution_state(conn)` returns `dict[str, str]` consumed by
      GraphSync
    - `compute_plan_hash(graph)` returns hash consumed by plan_meta
      comparison
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-105-SMOKE-*` tests pass using real components
    - _Test Spec: TS-105-SMOKE-1, TS-105-SMOKE-2_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be justified or replaced
    - _Requirements: all_

  - [ ] 5.5 Cross-spec entry point verification
    - `save_plan` is called from `cli/plan.py` and `engine/engine.py`
    - `load_plan` is called from `engine/engine.py`
    - `persist_node_status` is called from result handler
    - `record_session` is called from result handler
    - Verify all callers pass DuckDB connection, not file path
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No `plan.json` or `state.jsonl` files created by any test or
      production code

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 105-REQ-1.1 | TS-105-1, TS-105-2 | 3.1 | `tests/unit/graph/test_db_persistence.py::test_plan_round_trip` |
| 105-REQ-1.2 | TS-105-1 | 3.2 | `tests/unit/graph/test_db_persistence.py::test_plan_round_trip` |
| 105-REQ-1.3 | TS-105-1 | 2.1, 3.1 | `tests/unit/graph/test_db_persistence.py::test_plan_round_trip` |
| 105-REQ-1.4 | TS-105-3 | 3.1 | `tests/unit/graph/test_db_persistence.py::test_content_hash_stored` |
| 105-REQ-1.E1 | TS-105-E1 | 3.2 | `tests/unit/graph/test_db_persistence.py::test_no_plan_returns_none` |
| 105-REQ-1.E2 | TS-105-E2 | 3.2 | `tests/unit/graph/test_db_persistence.py::test_empty_plan` |
| 105-REQ-2.1 | TS-105-4 | 3.3 | `tests/unit/engine/test_db_plan_state.py::test_status_persisted` |
| 105-REQ-2.2 | TS-105-5 | 2.2 | `tests/unit/engine/test_db_plan_state.py::test_v3_statuses` |
| 105-REQ-2.3 | TS-105-6 | 3.3 | `tests/unit/engine/test_db_plan_state.py::test_blocked_reason` |
| 105-REQ-2.4 | TS-105-4 | 4.1 | `tests/unit/engine/test_db_plan_state.py::test_status_persisted` |
| 105-REQ-2.E1 | TS-105-E3 | 3.5 | `tests/unit/engine/test_db_plan_state.py::test_crash_recovery` |
| 105-REQ-3.1 | TS-105-7 | 2.1, 2.3 | `tests/unit/engine/test_db_plan_state.py::test_session_extended_fields` |
| 105-REQ-3.2 | TS-105-7 | 3.4 | `tests/unit/engine/test_db_plan_state.py::test_session_extended_fields` |
| 105-REQ-3.3 | TS-105-9 | 4.4 | `tests/unit/engine/test_db_plan_state.py::test_plan_path_removed` |
| 105-REQ-3.E1 | TS-105-E4 | 3.4 | `tests/unit/engine/test_db_plan_state.py::test_null_error_message` |
| 105-REQ-4.1 | TS-105-8 | 2.1, 2.4 | `tests/unit/engine/test_db_plan_state.py::test_run_lifecycle` |
| 105-REQ-4.2 | TS-105-8 | 3.4 | `tests/unit/engine/test_db_plan_state.py::test_run_lifecycle` |
| 105-REQ-4.3 | TS-105-8 | 3.4 | `tests/unit/engine/test_db_plan_state.py::test_run_lifecycle` |
| 105-REQ-4.4 | TS-105-8 | 3.4 | `tests/unit/engine/test_db_plan_state.py::test_run_lifecycle` |
| 105-REQ-4.E1 | TS-105-E5 | 3.4 | `tests/unit/engine/test_db_plan_state.py::test_incomplete_run_resume` |
| 105-REQ-5.1 | TS-105-9 | 4.4 | `tests/unit/engine/test_db_plan_state.py::test_plan_path_removed` |
| 105-REQ-5.2 | TS-105-1 | 3.1, 3.2, 4.4 | `tests/unit/graph/test_db_persistence.py::test_plan_round_trip` |
| 105-REQ-5.3 | TS-105-9 | 4.4 | `tests/unit/engine/test_db_plan_state.py::test_plan_path_removed` |
| 105-REQ-5.4 | TS-105-10 | 4.1, 4.4 | `tests/integration/test_db_plan_state_smoke.py::test_full_orchestration_cycle` |
| 105-REQ-5.E1 | TS-105-11 | 3.2 | `tests/unit/graph/test_db_persistence.py::test_legacy_files_ignored` |
| 105-REQ-6.1 | TS-105-12 | 4.3 | `tests/integration/test_db_plan_state_smoke.py::test_concurrent_status_read` |
| 105-REQ-6.2 | TS-105-SMOKE-1 | 4.2 | `tests/integration/test_db_plan_state_smoke.py::test_full_orchestration_cycle` |
| 105-REQ-6.3 | TS-105-12, TS-105-SMOKE-2 | 4.3 | `tests/integration/test_db_plan_state_smoke.py::test_concurrent_status_read` |
| 105-REQ-6.E1 | TS-105-E6 | 4.3 | `tests/unit/engine/test_db_plan_state.py::test_missing_db_status` |
| Property 1 | TS-105-P1 | 3.1, 3.2 | `tests/property/engine/test_plan_state_props.py::test_plan_round_trip` |
| Property 2 | TS-105-P2 | 3.3 | `tests/property/engine/test_plan_state_props.py::test_status_atomicity` |
| Property 3 | TS-105-P3 | 3.1, 3.2 | `tests/property/engine/test_plan_state_props.py::test_content_hash_stability` |
| Property 4 | TS-105-P4 | 3.4 | `tests/property/engine/test_plan_state_props.py::test_session_completeness` |
| Property 5 | TS-105-P5 | 3.4 | `tests/property/engine/test_plan_state_props.py::test_run_aggregate_accuracy` |

## Notes

- The `GraphSync` class continues to use a shared in-memory `node_states`
  dict for fast ready-task detection. The dict is loaded from
  `plan_nodes.status` on startup and written back to DB after each
  transition. This preserves the current O(n) ready-task scan without
  requiring per-query DB round-trips.
- The `compute_plan_hash` function now takes a `TaskGraph` object instead
  of a file `Path`. The algorithm (SHA-256 of canonical JSON excluding
  status) is unchanged.
- Existing tests that mock `StateManager` or read/write `plan.json` /
  `state.jsonl` will need updating in task 4.5. Key test files:
  `tests/unit/engine/test_orchestrator.py`,
  `tests/unit/engine/test_state.py`,
  `tests/unit/graph/test_persistence.py`.
- The v9 migration extends `session_outcomes` with ALTER TABLE ADD COLUMN.
  Existing rows get NULL/default for new columns. This is backward
  compatible — no data migration needed.
- The `plan_meta` table uses a single-row constraint (`id = 1`) to ensure
  only one plan exists at a time. `save_plan` deletes existing rows before
  inserting. This matches the current behavior where `plan.json` is
  overwritten on each plan.
