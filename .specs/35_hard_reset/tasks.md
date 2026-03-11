# Implementation Plan: Hard Reset Command

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation is split into four task groups:

1. **Write failing tests** — translate test_spec.md into executable tests.
2. **Git revision tracking** — add `commit_sha` to `SessionRecord` and capture
   it during harvest.
3. **Hard reset engine** — implement `hard_reset_all()`, `hard_reset_task()`,
   rollback, affected-task detection, and artifact synchronization.
4. **CLI wiring and output** — add `--hard` flag, display results, JSON output.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_hard_reset.py tests/unit/engine/test_hard_reset_props.py tests/integration/test_hard_reset_git.py`
- Unit tests: `uv run pytest -q tests/unit/engine/test_hard_reset.py`
- Property tests: `uv run pytest -q tests/unit/engine/test_hard_reset_props.py`
- Integration tests: `uv run pytest -q tests/integration/test_hard_reset_git.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/engine/reset.py agent_fox/engine/state.py agent_fox/cli/reset.py agent_fox/engine/session_lifecycle.py && uv run ruff format --check agent_fox/engine/reset.py agent_fox/engine/state.py agent_fox/cli/reset.py agent_fox/engine/session_lifecycle.py`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create unit test file `tests/unit/engine/test_hard_reset.py`
    - Translate TS-35-2 through TS-35-9, TS-35-11, TS-35-13 through TS-35-18
    - Translate edge case tests TS-35-E1 through TS-35-E8
    - Use existing test helpers (`_make_plan_json`, `_write_plan`, `_write_state`)
      from `tests/unit/engine/test_reset.py` as reference
    - _Test Spec: TS-35-2, TS-35-3, TS-35-4, TS-35-5, TS-35-6, TS-35-7, TS-35-8, TS-35-9, TS-35-11, TS-35-13, TS-35-14, TS-35-15, TS-35-16, TS-35-17, TS-35-18, TS-35-E1, TS-35-E2, TS-35-E3, TS-35-E4, TS-35-E5, TS-35-E6, TS-35-E7, TS-35-E8_

  - [ ] 1.2 Create property test file `tests/unit/engine/test_hard_reset_props.py`
    - Translate TS-35-P1 through TS-35-P5
    - Use Hypothesis strategies for generating random ExecutionState objects
    - _Test Spec: TS-35-P1, TS-35-P2, TS-35-P3, TS-35-P4, TS-35-P5_

  - [ ] 1.3 Create integration test file `tests/integration/test_hard_reset_git.py`
    - Translate TS-35-1, TS-35-10, TS-35-12
    - Use `tmp_path` fixture to create real git repos with commit history
    - _Test Spec: TS-35-1, TS-35-10, TS-35-12_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/engine/test_hard_reset.py tests/unit/engine/test_hard_reset_props.py tests/integration/test_hard_reset_git.py && uv run ruff format --check tests/unit/engine/test_hard_reset.py tests/unit/engine/test_hard_reset_props.py tests/integration/test_hard_reset_git.py`

- [ ] 2. Git revision tracking (SessionRecord.commit_sha)
  - [ ] 2.1 Add `commit_sha` field to `SessionRecord`
    - Add `commit_sha: str = ""` field to the dataclass in `state.py`
    - Verify `_deserialize_state` handles missing key via existing `.get()` pattern
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 2.2 Capture develop HEAD after harvest in `session_lifecycle.py`
    - After successful `harvest()` call in `_run_and_harvest()`, run
      `git rev-parse develop` via `run_git()` to get the current HEAD SHA
    - Store the SHA in the `SessionRecord` constructor call
    - Wrap in try/except: on failure, log warning and use `commit_sha=""`
    - _Requirements: 1.1, 1.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_hard_reset.py -k "commit_sha or backward_compat or deserialization or rev_parse_fail"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/engine/state.py agent_fox/engine/session_lifecycle.py && uv run ruff format --check agent_fox/engine/state.py agent_fox/engine/session_lifecycle.py`
    - [ ] Requirements 1.1, 1.2, 1.3, 1.E1 acceptance criteria met

- [ ] 3. Hard reset engine
  - [ ] 3.1 Implement `find_rollback_target()` in `reset.py`
    - For full reset: find earliest non-empty commit_sha in session_history,
      compute its first-parent predecessor using `git rev-parse {sha}^1`
    - For partial reset: compute first-parent predecessor of the given commit_sha
    - Return None if no valid commit_sha exists or if git resolution fails
    - _Requirements: 3.5, 4.1_

  - [ ] 3.2 Implement `rollback_develop()` in `reset.py`
    - Checkout develop and run `git reset --hard <target_sha>`
    - Raise AgentFoxError if the SHA cannot be resolved
    - _Requirements: 3.5, 4.1_

  - [ ] 3.3 Implement `find_affected_tasks()` in `reset.py`
    - For each completed SessionRecord with a non-empty commit_sha, check
      `git merge-base --is-ancestor {commit_sha} {new_head}`
    - Return task IDs where the commit is NOT an ancestor (affected by rollback)
    - _Requirements: 4.3_

  - [ ] 3.4 Implement `reset_tasks_md_checkboxes()` and `reset_plan_statuses()` in `reset.py`
    - `reset_tasks_md_checkboxes()`: for each affected task ID, parse
      spec_name and group_number, find `.specs/{spec_name}/tasks.md`, replace
      top-level checkbox `[x]` or `[-]` with `[ ]` for that group number
    - `reset_plan_statuses()`: load plan.json, set status to "pending" for
      affected node IDs, write back. Skip if plan.json missing.
    - _Requirements: 7.1, 7.2, 7.3, 7.E1, 7.E2_

  - [ ] 3.5 Implement `hard_reset_all()` in `reset.py`
    - Load state and plan
    - Find rollback target from session history (skip if None)
    - Execute rollback via `rollback_develop()`
    - Reset ALL node_states to pending
    - Clean ALL worktrees and branches
    - Call `compact()` on memory
    - Reset tasks.md checkboxes and plan.json statuses for all tasks
    - Preserve counters and session history
    - Save updated state
    - Return `HardResetResult`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.E1, 3.E2, 7.1, 7.2, 7.3_

  - [ ] 3.6 Implement `hard_reset_task()` in `reset.py`
    - Load state and plan, validate task_id
    - Find commit_sha for target task from session history
    - Find rollback target (skip if no commit_sha)
    - Execute rollback via `rollback_develop()`
    - Find affected tasks via `find_affected_tasks()`
    - Reset target + affected tasks to pending
    - Clean worktrees and branches for affected tasks
    - Call `compact()` on memory
    - Reset tasks.md checkboxes and plan.json statuses for affected tasks
    - Save updated state
    - Return `HardResetResult`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.E1, 4.E2, 7.1, 7.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_hard_reset.py -k "hard_reset" tests/integration/test_hard_reset_git.py`
    - [ ] Property tests pass: `uv run pytest -q tests/unit/engine/test_hard_reset_props.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/engine/reset.py && uv run ruff format --check agent_fox/engine/reset.py`
    - [ ] Requirements 3.1-3.7, 3.E1, 3.E2, 4.1-4.5, 4.E1, 4.E2, 7.1-7.3, 7.E1, 7.E2 acceptance criteria met

- [ ] 4. CLI wiring, output, and documentation
  - [ ] 4.1 Add `--hard` flag to `reset_cmd` in `cli/reset.py`
    - Add `@click.option("--hard", is_flag=True)` to the command
    - When `--hard` is set, dispatch to `hard_reset_all()` or `hard_reset_task()`
    - When `--hard` is not set, preserve existing soft-reset behavior
    - _Requirements: 2.1, 2.2_

  - [ ] 4.2 Implement confirmation flow for hard reset
    - Show summary of what will happen (task count, rollback info)
    - Prompt for confirmation unless `--yes` or `--json`
    - _Requirements: 5.1, 5.2, 5.3, 5.E1_

  - [ ] 4.3 Implement display and JSON output for `HardResetResult`
    - Human-readable summary: tasks reset, worktrees cleaned, branches deleted,
      compaction stats, rollback target
    - JSON envelope with all fields
    - _Requirements: 6.1, 6.2_

  - [ ] 4.4 Update CLI reference documentation
    - Add `--hard` flag to `docs/cli-reference.md` reset command section
    - Document partial rollback behavior

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_hard_reset.py -k "cli or flag or confirm or json_output or soft_reset"`
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/engine/test_hard_reset.py tests/unit/engine/test_hard_reset_props.py tests/integration/test_hard_reset_git.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/cli/reset.py && uv run ruff format --check agent_fox/cli/reset.py`
    - [ ] Requirements 2.1, 2.2, 5.1-5.3, 5.E1, 6.1, 6.2 acceptance criteria met

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 35-REQ-1.1 | TS-35-1 | 2.2 | `test_hard_reset_git.py::test_commit_sha_captured` |
| 35-REQ-1.2 | TS-35-2 | 2.1 | `test_hard_reset.py::test_commit_sha_empty_on_failure` |
| 35-REQ-1.3 | TS-35-3 | 2.1 | `test_hard_reset.py::test_backward_compat_deserialization` |
| 35-REQ-1.E1 | TS-35-E1 | 2.2 | `test_hard_reset.py::test_rev_parse_fail_graceful` |
| 35-REQ-2.1 | TS-35-4 | 4.1 | `test_hard_reset.py::test_hard_flag_accepted` |
| 35-REQ-2.2 | TS-35-5 | 4.1 | `test_hard_reset.py::test_soft_reset_unchanged` |
| 35-REQ-3.1 | TS-35-6 | 3.5 | `test_hard_reset.py::test_full_hard_reset_all_tasks` |
| 35-REQ-3.2 | TS-35-7 | 3.5 | `test_hard_reset.py::test_full_hard_reset_cleans_worktrees` |
| 35-REQ-3.3 | TS-35-8 | 3.5 | `test_hard_reset.py::test_full_hard_reset_deletes_branches` |
| 35-REQ-3.4 | TS-35-9 | 3.5 | `test_hard_reset.py::test_full_hard_reset_compacts_kb` |
| 35-REQ-3.5 | TS-35-10 | 3.1, 3.2, 3.5 | `test_hard_reset_git.py::test_full_hard_reset_rollback` |
| 35-REQ-3.6 | TS-35-11 | 3.5 | `test_hard_reset.py::test_full_hard_reset_preserves_counters` |
| 35-REQ-3.7 | TS-35-9 | 3.5 | `test_hard_reset.py::test_full_hard_reset_compacts_kb` |
| 35-REQ-3.E1 | TS-35-E2 | 3.5 | `test_hard_reset.py::test_no_commit_shas_skips_rollback` |
| 35-REQ-3.E2 | TS-35-E3 | 3.1 | `test_hard_reset.py::test_unresolvable_sha_skips_rollback` |
| 35-REQ-4.1 | TS-35-12 | 3.6 | `test_hard_reset_git.py::test_partial_hard_reset_rollback` |
| 35-REQ-4.2 | TS-35-12 | 3.6 | `test_hard_reset_git.py::test_partial_hard_reset_rollback` |
| 35-REQ-4.3 | TS-35-13 | 3.3, 3.6 | `test_hard_reset.py::test_find_affected_tasks` |
| 35-REQ-4.4 | TS-35-14 | 3.6 | `test_hard_reset.py::test_partial_hard_reset_cleans_affected` |
| 35-REQ-4.5 | TS-35-9 | 3.6 | `test_hard_reset.py::test_full_hard_reset_compacts_kb` |
| 35-REQ-4.E1 | TS-35-E5 | 3.6 | `test_hard_reset.py::test_partial_no_commit_sha` |
| 35-REQ-4.E2 | TS-35-E4 | 3.6 | `test_hard_reset.py::test_unknown_task_id_error` |
| 35-REQ-5.1 | TS-35-15 | 4.2 | `test_hard_reset.py::test_confirmation_required` |
| 35-REQ-5.2 | TS-35-4 | 4.2 | `test_hard_reset.py::test_hard_flag_accepted` |
| 35-REQ-5.3 | TS-35-16 | 4.2 | `test_hard_reset.py::test_json_output` |
| 35-REQ-5.E1 | TS-35-E6 | 4.2 | `test_hard_reset.py::test_user_declines` |
| 35-REQ-6.1 | TS-35-6 | 4.3 | `test_hard_reset.py::test_full_hard_reset_all_tasks` |
| 35-REQ-6.2 | TS-35-16 | 4.3 | `test_hard_reset.py::test_json_output` |
| 35-REQ-7.1 | TS-35-17 | 3.4 | `test_hard_reset.py::test_reset_tasks_md_checkboxes` |
| 35-REQ-7.2 | TS-35-18 | 3.4 | `test_hard_reset.py::test_reset_plan_statuses` |
| 35-REQ-7.3 | TS-35-17 | 3.4 | `test_hard_reset.py::test_reset_tasks_md_checkboxes` |
| 35-REQ-7.E1 | TS-35-E7 | 3.4 | `test_hard_reset.py::test_tasks_md_missing` |
| 35-REQ-7.E2 | TS-35-E8 | 3.4 | `test_hard_reset.py::test_plan_json_missing` |
| Property 1 | TS-35-P1 | 3.5 | `test_hard_reset_props.py::test_total_task_reset` |
| Property 2 | TS-35-P2 | 3.5 | `test_hard_reset_props.py::test_counter_preservation` |
| Property 6 | TS-35-P3 | 3.5 | `test_hard_reset_props.py::test_graceful_degradation` |
| Property 8 | TS-35-P5 | 3.4 | `test_hard_reset_props.py::test_artifact_sync` |
| Property 7 | TS-35-P4 | 2.1 | `test_hard_reset_props.py::test_backward_compat_deser` |

## Notes

- Integration tests (TS-35-1, TS-35-10, TS-35-12) require creating real git
  repos in temporary directories. Use `subprocess.run(["git", ...])` directly
  in test setup rather than importing workspace helpers, to keep test
  dependencies minimal.
- Property tests should use `@settings(suppress_health_check=[HealthCheck.too_slow])`
  since generating ExecutionState objects with session histories can be slow.
- The `compact()` function is synchronous. Since hard reset also calls
  synchronous git operations (via `subprocess.run`), the entire hard reset
  engine is synchronous — no async needed.
- Existing soft-reset tests in `test_reset.py` must continue passing without
  modification.
