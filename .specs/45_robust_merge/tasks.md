# Implementation Plan: Robust Git Merging

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan implements file-based merge locking and agent-based conflict
resolution in four task groups: tests first, then the lock module, then the
merge agent, then integration into harvest/workspace flows.

## Test Commands

- Spec tests: `uv run pytest tests/unit/workspace/test_merge_lock.py tests/unit/workspace/test_merge_agent.py tests/unit/workspace/test_harvest_locking.py -q`
- Unit tests: `uv run pytest tests/unit/workspace/ -q`
- Property tests: `uv run pytest tests/property/workspace/test_merge_lock_props.py -q`
- Integration tests: `uv run pytest tests/integration/test_cross_process_lock.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/workspace/ tests/unit/workspace/ tests/property/workspace/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create merge lock unit tests
    - Create `tests/unit/workspace/test_merge_lock.py`
    - Tests for: lock acquisition, queuing, timeout, stale detection, release,
      missing directory, release of already-removed lock
    - _Test Spec: TS-45-1 through TS-45-3, TS-45-E1 through TS-45-E4_

  - [x] 1.2 Create merge agent unit tests
    - Create `tests/unit/workspace/test_merge_agent.py`
    - Tests for: agent spawned on failure, uses ADVANCED model, conflict-only
      prompt, receives conflict output, resolution completes merge
    - _Test Spec: TS-45-9 through TS-45-13_

  - [x] 1.3 Create harvest/workspace locking tests
    - Create `tests/unit/workspace/test_harvest_locking.py`
    - Tests for: lock covers harvest + post-harvest, lock covers develop-sync,
      lock released on success and failure, no -X theirs/ours
    - _Test Spec: TS-45-5 through TS-45-8, TS-45-E5 through TS-45-E9_

  - [x] 1.4 Create property tests
    - Create `tests/property/workspace/test_merge_lock_props.py`
    - Tests for: mutual exclusion, lock always released, stale recovery,
      no blind strategy options
    - _Test Spec: TS-45-P1 through TS-45-P4_

  - [x] 1.5 Create integration test stub
    - Create `tests/integration/test_cross_process_lock.py`
    - Test for: cross-process lock serialization
    - _Test Spec: TS-45-4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/workspace/test_merge_lock.py tests/unit/workspace/test_merge_agent.py tests/unit/workspace/test_harvest_locking.py tests/property/workspace/test_merge_lock_props.py`

- [x] 2. Implement MergeLock
  - [x] 2.1 Create `agent_fox/workspace/merge_lock.py`
    - Implement `MergeLock` class with file-based locking
    - Atomic creation via `os.open(O_CREAT | O_EXCL)`
    - Internal `asyncio.Lock` for within-process serialization
    - Stale lock detection and breaking
    - Async context manager protocol
    - _Requirements: 45-REQ-1.1, 45-REQ-1.2, 45-REQ-1.3, 45-REQ-1.4,
      45-REQ-1.E1, 45-REQ-1.E2, 45-REQ-1.E3, 45-REQ-2.1, 45-REQ-2.2,
      45-REQ-2.E1_

  - [x] 2.V Verify task group 2
    - [x] Lock tests pass: `uv run pytest tests/unit/workspace/test_merge_lock.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/workspace/test_merge_lock_props.py -q`
    - [x] Integration test passes: `uv run pytest tests/integration/test_cross_process_lock.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/workspace/merge_lock.py`
    - [x] Requirements 45-REQ-1.*, 45-REQ-2.* met

- [x] 3. Implement merge agent
  - [x] 3.1 Create `agent_fox/workspace/merge_agent.py`
    - Implement `run_merge_agent()` function
    - Build system prompt restricting agent to conflict resolution only
    - Pass conflict output and worktree path as context
    - Use `resolve_model_id("ADVANCED")` for model selection
    - Check resolution via `git diff --check` after agent completes
    - _Requirements: 45-REQ-4.1, 45-REQ-4.2, 45-REQ-4.3, 45-REQ-4.4,
      45-REQ-4.5, 45-REQ-4.E1, 45-REQ-4.E2_

  - [x] 3.V Verify task group 3
    - [x] Agent tests pass: `uv run pytest tests/unit/workspace/test_merge_agent.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/workspace/merge_agent.py`
    - [x] Requirements 45-REQ-4.* met

- [x] 4. Integrate lock and agent into harvest/workspace
  - [x] 4.1 Modify `harvest()` in `agent_fox/workspace/harvest.py`
    - Wrap entire harvest + post-harvest in `async with MergeLock(...)`
    - Replace `-X theirs` fallback with `run_merge_agent()` call
    - On agent failure, raise IntegrationError
    - _Requirements: 45-REQ-3.1, 45-REQ-4.1, 45-REQ-6.1_

  - [x] 4.2 Modify `_sync_develop_with_remote()` in `agent_fox/workspace/workspace.py`
    - Wrap develop-sync in `async with MergeLock(...)`
    - Replace `-X ours` fallback with `run_merge_agent()` call
    - On agent failure, log warning and leave develop as-is
    - _Requirements: 45-REQ-3.2, 45-REQ-5.1, 45-REQ-5.2, 45-REQ-5.E1,
      45-REQ-6.2_

  - [x] 4.3 Modify `_push_develop_if_pushable()` in `agent_fox/workspace/harvest.py`
    - Ensure it runs inside the merge lock (already covered by harvest lock
      scope, but verify the develop-sync call within it is also locked)
    - _Requirements: 45-REQ-3.1, 45-REQ-3.2_

  - [x] 4.V Verify task group 4
    - [x] Harvest locking tests pass: `uv run pytest tests/unit/workspace/test_harvest_locking.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/workspace/harvest.py agent_fox/workspace/workspace.py`
    - [x] Requirements 45-REQ-3.*, 45-REQ-5.*, 45-REQ-6.* met

- [ ] 5. Checkpoint — Robust Merge Complete
  - Ensure all tests pass: `uv run pytest -q`
  - Ensure linting passes: `uv run ruff check agent_fox/workspace/`
  - Verify no `-X theirs` or `-X ours` in harvest.py or workspace.py

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

Tasks are **required by default**. Mark optional tasks with `*` after checkbox: `- [ ]* Optional task`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 45-REQ-1.1 | TS-45-1 | 2.1 | `test_merge_lock.py::test_lock_acquired_before_merge` |
| 45-REQ-1.2 | TS-45-2 | 2.1 | `test_merge_lock.py::test_lock_queues_concurrent_callers` |
| 45-REQ-1.3 | TS-45-3 | 2.1 | `test_merge_lock.py::test_lock_timeout_raises` |
| 45-REQ-1.4 | TS-45-4 | 2.1 | `test_cross_process_lock.py::test_cross_process_serialization` |
| 45-REQ-1.E1 | TS-45-E1 | 2.1 | `test_merge_lock.py::test_stale_lock_broken` |
| 45-REQ-1.E2 | TS-45-E2 | 2.1 | `test_merge_lock.py::test_missing_agent_fox_dir` |
| 45-REQ-1.E3 | TS-45-E3 | 2.1 | `test_merge_lock.py::test_concurrent_stale_lock_break` |
| 45-REQ-2.1 | TS-45-5 | 2.1 | `test_harvest_locking.py::test_lock_release_on_success` |
| 45-REQ-2.2 | TS-45-6 | 2.1 | `test_harvest_locking.py::test_lock_release_on_failure` |
| 45-REQ-2.E1 | TS-45-E4 | 2.1 | `test_merge_lock.py::test_release_missing_lock_file` |
| 45-REQ-3.1 | TS-45-7 | 4.1, 4.3 | `test_harvest_locking.py::test_lock_covers_post_harvest` |
| 45-REQ-3.2 | TS-45-8 | 4.2 | `test_harvest_locking.py::test_develop_sync_uses_lock` |
| 45-REQ-4.1 | TS-45-9 | 3.1, 4.1 | `test_merge_agent.py::test_agent_spawned_on_merge_failure` |
| 45-REQ-4.2 | TS-45-10 | 3.1 | `test_merge_agent.py::test_agent_uses_advanced_model` |
| 45-REQ-4.3 | TS-45-11 | 3.1 | `test_merge_agent.py::test_agent_prompt_conflict_only` |
| 45-REQ-4.4 | TS-45-12 | 3.1 | `test_merge_agent.py::test_agent_receives_conflict_output` |
| 45-REQ-4.5 | TS-45-13 | 3.1, 4.1 | `test_merge_agent.py::test_agent_resolution_completes_merge` |
| 45-REQ-4.E1 | TS-45-E5 | 4.1 | `test_harvest_locking.py::test_agent_failure_aborts_harvest` |
| 45-REQ-4.E2 | TS-45-E6 | 3.1 | `test_merge_agent.py::test_agent_api_error_treated_as_failure` |
| 45-REQ-5.1 | TS-45-9 | 4.2 | `test_harvest_locking.py::test_develop_sync_agent_fallback` |
| 45-REQ-5.2 | TS-45-13 | 4.2 | `test_harvest_locking.py::test_develop_sync_agent_completes` |
| 45-REQ-5.E1 | TS-45-E7 | 4.2 | `test_harvest_locking.py::test_develop_sync_agent_failure_warns` |
| 45-REQ-6.1 | TS-45-E8 | 4.1 | `test_harvest_locking.py::test_no_x_theirs_in_harvest` |
| 45-REQ-6.2 | TS-45-E9 | 4.2 | `test_harvest_locking.py::test_no_x_ours_in_develop_sync` |
| Property 1 | TS-45-P1 | 2.1 | `test_merge_lock_props.py::test_mutual_exclusion` |
| Property 2 | TS-45-P2 | 2.1 | `test_merge_lock_props.py::test_lock_always_released` |
| Property 3 | TS-45-P3 | 2.1 | `test_merge_lock_props.py::test_stale_lock_recovery` |
| Property 4 | TS-45-P4 | 4.1, 4.2 | `test_merge_lock_props.py::test_no_blind_strategy_options` |

## Notes

- The merge lock file is ephemeral and should be added to `.gitignore` (it's
  under `.agent-fox/` which is already ignored).
- The merge agent uses `run_session` from the existing session runner — no new
  agent framework needed.
- Property test TS-45-P4 is a static analysis test (reads source code), not
  a Hypothesis-generated test.
- The integration test (TS-45-4) spawns real subprocesses and needs a temporary
  git repository. Use `pytest-tmp-files` or `tmp_path` fixture.
