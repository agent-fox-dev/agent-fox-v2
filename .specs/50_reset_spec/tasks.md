# Implementation Plan: Spec-Scoped Reset

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

Spec: **50_reset_spec**
Source: [Test Spec](test_spec.md) | [Design](design.md) | [Requirements](requirements.md)

---

## Overview

This plan adds a `--spec` option to the reset command. Task group 1 writes
failing tests. Task group 2 implements `reset_spec()` in the engine. Task
group 3 wires it into the CLI. Task group 4 is a checkpoint.

## Test Commands

- Spec tests: `uv run pytest tests/unit/engine/test_reset_spec.py tests/unit/cli/test_reset_spec.py tests/property/engine/test_reset_spec_props.py -v`
- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/property/ -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

## Tasks

- [x] 1. Write Failing Spec Tests
  - [x] 1.1 Create unit test file for engine reset_spec
    - Create `tests/unit/engine/test_reset_spec.py`
    - Implement TS-50-1 (all spec nodes to pending)
    - Implement TS-50-2 (archetype nodes included)
    - Implement TS-50-3 (other specs unchanged)
    - Implement TS-50-4 (worktrees and branches cleaned)
    - Implement TS-50-5 (tasks.md checkboxes reset)
    - Implement TS-50-6 (plan.json statuses reset)
    - Implement TS-50-7 (no git rollback)
    - Implement TS-50-12 (session history preserved)
    - _Test Spec: TS-50-1 through TS-50-7, TS-50-12_
  - [x] 1.2 Create edge case tests
    - Implement TS-50-E1 (unknown spec name)
    - Implement TS-50-E2 (missing plan file)
    - Implement TS-50-E3 (missing state file)
    - Implement TS-50-E4 (all nodes already pending)
    - _Test Spec: TS-50-E1 through TS-50-E4_
  - [x] 1.3 Create CLI tests
    - Create `tests/unit/cli/test_reset_spec.py`
    - Implement TS-50-8 (mutual exclusivity with --hard)
    - Implement TS-50-9 (mutual exclusivity with task_id)
    - Implement TS-50-10 (confirmation required)
    - Implement TS-50-11 (JSON output)
    - _Test Spec: TS-50-8 through TS-50-11_
  - [x] 1.4 Create property tests
    - Create `tests/property/engine/test_reset_spec_props.py`
    - Implement TS-50-P1 (spec isolation)
    - Implement TS-50-P2 (complete spec coverage)
    - Implement TS-50-P3 (preservation)
    - Implement TS-50-P4 (artifact synchronization)
    - _Test Spec: TS-50-P1 through TS-50-P4_
  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/`

- [x] 2. Implement reset_spec Engine Function
  - [x] 2.1 Add `reset_spec()` to `agent_fox/engine/reset.py`
    - Load plan and state, validate spec_name exists
    - Collect all node IDs where `node.spec_name == spec_name`
    - Reset matching node_states to `pending`
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 Clean worktrees and branches for spec nodes
    - Call `_cleanup_task()` for each spec node
    - Populate `cleaned_worktrees` and `cleaned_branches` in result
    - _Requirements: 1.4_
  - [x] 2.3 Synchronize tasks.md and plan.json
    - Call `reset_tasks_md_checkboxes()` with spec node IDs
    - Call `reset_plan_statuses()` with spec node IDs
    - _Requirements: 1.5, 1.6_
  - [x] 2.4 Implement error handling
    - Raise `AgentFoxError` for unknown spec with valid spec list
    - Raise `AgentFoxError` for missing plan/state files
    - Return empty result when all nodes already pending
    - _Requirements: 1.E1, 1.E2, 1.E3, 1.E4_
  - [x] 2.V Verify task group 2
    - [x] Engine unit tests pass: `uv run pytest tests/unit/engine/test_reset_spec.py -v`
    - [x] Property tests pass: `uv run pytest tests/property/engine/test_reset_spec_props.py -v`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Requirements 1.1-1.8, 1.E1-1.E4, 4.1, 4.2 met

- [x] 3. Wire --spec into CLI
  - [x] 3.1 Add `--spec` option to `reset_cmd` in `agent_fox/cli/reset.py`
    - Add Click option `--spec` with `filter_spec` parameter name
    - Add mutual exclusivity checks against `--hard` and `task_id`
    - _Requirements: 2.1, 2.2_
  - [x] 3.2 Implement confirmation and dispatch
    - Add confirmation prompt (skipped with `--yes` or `--json`)
    - Dispatch to `reset_spec()` when `--spec` is provided
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 3.3 Implement output formatting
    - Display human-readable summary (reset count, cleaned artifacts)
    - Implement JSON output mode with `reset_tasks`, `cleaned_worktrees`,
      `cleaned_branches` keys
    - _Requirements: 3.4, 3.5_
  - [x] 3.V Verify task group 3
    - [x] CLI tests pass: `uv run pytest tests/unit/cli/test_reset_spec.py -v`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Requirements 2.1, 2.2, 3.1-3.5 met

- [x] 4. Checkpoint - Spec-Scoped Reset Complete
  - Ensure all tests pass: `uv run pytest -q`
  - Run linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`
  - Ask the user if questions arise

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 50-REQ-1.1 | TS-50-1 | 2.1 | test_reset_sets_all_spec_nodes_to_pending |
| 50-REQ-1.2 | TS-50-2 | 2.1 | test_reset_includes_archetype_nodes |
| 50-REQ-1.3 | TS-50-3 | 2.1 | test_other_specs_unchanged |
| 50-REQ-1.4 | TS-50-4 | 2.2 | test_worktrees_and_branches_cleaned |
| 50-REQ-1.5 | TS-50-5 | 2.3 | test_tasks_md_checkboxes_reset |
| 50-REQ-1.6 | TS-50-6 | 2.3 | test_plan_json_statuses_reset |
| 50-REQ-1.7 | TS-50-7 | 2.1 | test_no_git_rollback |
| 50-REQ-1.8 | — | 2.1 | (verified by absence of compaction call) |
| 50-REQ-1.E1 | TS-50-E1 | 2.4 | test_unknown_spec_name |
| 50-REQ-1.E2 | TS-50-E2 | 2.4 | test_missing_plan_file |
| 50-REQ-1.E3 | TS-50-E3 | 2.4 | test_missing_state_file |
| 50-REQ-1.E4 | TS-50-E4 | 2.4 | test_all_nodes_already_pending |
| 50-REQ-2.1 | TS-50-8 | 3.1 | test_mutual_exclusivity_hard |
| 50-REQ-2.2 | TS-50-9 | 3.1 | test_mutual_exclusivity_task_id |
| 50-REQ-3.1 | TS-50-10 | 3.2 | test_confirmation_required |
| 50-REQ-3.2 | TS-50-10 | 3.2 | test_confirmation_required |
| 50-REQ-3.3 | — | 3.2 | (verified via --yes flag in other tests) |
| 50-REQ-3.4 | TS-50-11 | 3.3 | test_json_output |
| 50-REQ-3.5 | — | 3.3 | (verified via human-readable output in TS-50-1) |
| 50-REQ-4.1 | TS-50-12 | 2.1 | test_session_history_preserved |
| 50-REQ-4.2 | TS-50-12 | 2.1 | test_session_history_preserved |
| Property 1 | TS-50-P1 | 2.1 | test_spec_isolation |
| Property 2 | TS-50-P2 | 2.1 | test_complete_spec_coverage |
| Property 4 | TS-50-P3 | 2.1 | test_preservation |
| Property 5 | TS-50-P4 | 2.3 | test_artifact_synchronization |

## Notes

- Reuse existing `_cleanup_task()`, `reset_tasks_md_checkboxes()`, and
  `reset_plan_statuses()` from `agent_fox/engine/reset.py`.
- Reuse existing `ResetResult` dataclass — no new data models needed.
- The `reset_spec()` function loads the plan to get node metadata (spec_name),
  which is not available from state.jsonl alone.
- Test fixtures should create plans with multiple specs to verify isolation.
