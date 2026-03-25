# Implementation Plan: Sync Barrier Hardening

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into 5 groups: (1) write failing tests, (2) implement
the barrier entry module (worktree verification + bidirectional develop sync),
(3) implement the hot-load gate pipeline (git-tracked, completeness, lint),
(4) integrate into the orchestrator engine (parallel drain + barrier sequence),
(5) final checkpoint and documentation.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_barrier.py tests/unit/engine/test_hot_load_gates.py`
- Unit tests: `make test-unit`
- Property tests: `make test-property`
- All tests: `make test`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file for barrier entry operations
    - Create `tests/unit/engine/test_barrier.py`
    - Tests for `verify_worktrees`: orphans found, no orphans, dir missing
      (TS-51-5, TS-51-6, TS-51-7)
    - Tests for `sync_develop_bidirectional`: success, pull fail skips push,
      push fail non-blocking, no origin skips sync
      (TS-51-8, TS-51-9, TS-51-10, TS-51-11)
    - _Test Spec: TS-51-5 through TS-51-11_

  - [x] 1.2 Create test file for hot-load gate functions
    - Create `tests/unit/engine/test_hot_load_gates.py`
    - Tests for `is_spec_tracked_on_develop`: tracked, untracked, fallback
      (TS-51-12, TS-51-13, TS-51-14)
    - Tests for `is_spec_complete`: all files, missing file, empty file
      (TS-51-15, TS-51-16, TS-51-17)
    - Tests for `lint_spec_gate`: clean, errors, exception
      (TS-51-18, TS-51-19, TS-51-20)
    - Tests for `discover_new_specs_gated`: full pipeline, re-evaluation
      (TS-51-21, TS-51-22)
    - _Test Spec: TS-51-12 through TS-51-22_

  - [x] 1.3 Create test file for parallel drain and orchestrator integration
    - Create `tests/unit/engine/test_parallel_drain.py`
    - Tests for parallel drain: waits for all, processes results, no new
      dispatch during drain, serial skips drain, SIGINT during drain
      (TS-51-1, TS-51-2, TS-51-3, TS-51-4, TS-51-E1)
    - _Test Spec: TS-51-1 through TS-51-4, TS-51-E1_

  - [x] 1.4 Create property test files
    - Create `tests/property/engine/test_barrier_props.py`
    - Property tests for worktree verification (TS-51-P2), develop sync
      (TS-51-P3)
    - Create `tests/property/engine/test_hot_load_gate_props.py`
    - Property tests for gate pipeline filtering (TS-51-P4), git-tracked
      gate (TS-51-P5), completeness gate (TS-51-P6), lint gate (TS-51-P7),
      stateless re-evaluation (TS-51-P8)
    - Add parallel drain property test (TS-51-P1) to
      `tests/property/engine/test_barrier_props.py`
    - _Test Spec: TS-51-P1 through TS-51-P8_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Implement barrier entry module
  - [x] 2.1 Create `agent_fox/engine/barrier.py`
    - Implement `verify_worktrees(repo_root) -> list[Path]`
    - Scan `.agent-fox/worktrees/` for subdirectories
    - Log WARNING for each orphaned path
    - Handle missing directory gracefully (51-REQ-2.E1)
    - _Requirements: 51-REQ-2.1, 51-REQ-2.2, 51-REQ-2.3, 51-REQ-2.E1_

  - [x] 2.2 Implement `sync_develop_bidirectional` in `agent_fox/engine/barrier.py`
    - Acquire MergeLock
    - Check if origin remote exists (skip if not — 51-REQ-3.E3)
    - Call `_sync_develop_with_remote` for pull direction (51-REQ-3.1)
    - On pull failure, log warning and skip push (51-REQ-3.E1)
    - Push local develop to origin (51-REQ-3.2)
    - On push failure, log warning and proceed (51-REQ-3.E2)
    - Release MergeLock
    - _Requirements: 51-REQ-3.1, 51-REQ-3.2, 51-REQ-3.3, 51-REQ-3.E1,
      51-REQ-3.E2, 51-REQ-3.E3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for barrier entry pass: `uv run pytest -q tests/unit/engine/test_barrier.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/engine/test_barrier_props.py`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 51-REQ-2.*, 51-REQ-3.* acceptance criteria met

- [x] 3. Implement hot-load gate pipeline
  - [x] 3.1 Add `is_spec_tracked_on_develop` to `agent_fox/engine/hot_load.py`
    - Use `run_git(["ls-tree", "develop", "--", ".specs/{spec_name}"])`
    - Return True if output is non-empty
    - On failure, return True (permissive fallback) and log warning
    - _Requirements: 51-REQ-4.1, 51-REQ-4.2, 51-REQ-4.E1_

  - [x] 3.2 Add `is_spec_complete` to `agent_fox/engine/hot_load.py`
    - Check all 5 EXPECTED_FILES exist and have size > 0
    - Return (passed, list_of_missing_or_empty)
    - _Requirements: 51-REQ-5.1, 51-REQ-5.2, 51-REQ-5.E1_

  - [x] 3.3 Add `lint_spec_gate` to `agent_fox/engine/hot_load.py`
    - Import and call `check_missing_files` plus other relevant validators
      from `agent_fox.spec.validator`
    - Filter findings for severity "error"
    - Return (passed, error_messages)
    - Catch exceptions and return (False, [error description])
    - _Requirements: 51-REQ-6.1, 51-REQ-6.2, 51-REQ-6.3, 51-REQ-6.E1_

  - [x] 3.4 Add `discover_new_specs_gated` to `agent_fox/engine/hot_load.py`
    - Call existing `discover_new_specs` for filesystem discovery
    - Filter through git-tracked gate
    - Filter through completeness gate
    - Filter through lint gate
    - Return only specs passing all three gates
    - Log skip reasons at appropriate levels (debug/info/warning)
    - _Requirements: 51-REQ-7.1, 51-REQ-7.2, 51-REQ-7.3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for gates pass: `uv run pytest -q tests/unit/engine/test_hot_load_gates.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/engine/test_hot_load_gate_props.py`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 51-REQ-4.*, 51-REQ-5.*, 51-REQ-6.*, 51-REQ-7.* acceptance criteria met

- [x] 4. Integrate into orchestrator engine
  - [x] 4.1 Modify `_dispatch_parallel` for barrier drain
    - When a completed task triggers a barrier, drain the remaining pool
      before running the barrier
    - Use `asyncio.wait(pool)` to wait for all in-flight tasks
    - Process all results from drained tasks
    - Do not fill pool with new tasks until barrier completes
    - Respect SIGINT during drain (cancel and shutdown)
    - _Requirements: 51-REQ-1.1, 51-REQ-1.2, 51-REQ-1.3, 51-REQ-1.E1,
      51-REQ-1.E2_

  - [x] 4.2 Update `_run_sync_barrier_if_needed` to call barrier entry
    - Make method async
    - Call `verify_worktrees` before hooks
    - Call `sync_develop_bidirectional` before hooks
    - Update callers to await the async method
    - _Requirements: 51-REQ-2.1, 51-REQ-3.1_

  - [x] 4.3 Update `_hot_load_new_specs` to use gated discovery
    - Replace `discover_new_specs` call with `discover_new_specs_gated`
    - Make method async (needed for git ls-tree calls)
    - Pass `repo_root` to the gated discovery function
    - _Requirements: 51-REQ-4.1, 51-REQ-5.1, 51-REQ-6.1_

  - [x] 4.4 Extend sync.barrier audit event payload
    - Add `orphaned_worktrees` (list of paths)
    - Add `develop_sync_status` ("success" | "pull_failed" | "push_failed" | "skipped")
    - Add `specs_skipped` (dict of spec_name → skip_reason)

  - [x] 4.V Verify task group 4
    - [x] Spec tests for drain pass: `uv run pytest -q tests/unit/engine/test_parallel_drain.py`
    - [x] All spec tests pass: `uv run pytest -q tests/unit/engine/test_barrier.py tests/unit/engine/test_hot_load_gates.py tests/unit/engine/test_parallel_drain.py`
    - [x] All property tests pass: `make test-property`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 51-REQ-1.* acceptance criteria met

- [x] 5. Checkpoint — Sync Barrier Hardening Complete
  - [x] 5.1 Full verification
    - [x] `make check` passes
    - [x] All 51-REQ-* requirements verified via tests
  - [x] 5.2 Update documentation
    - Update `docs/memory.md` if any new gotchas or patterns discovered
    - No CLI or config changes to document

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 51-REQ-1.1 | TS-51-1, TS-51-P1 | 4.1 | test_parallel_drain.py |
| 51-REQ-1.2 | TS-51-2, TS-51-P1 | 4.1 | test_parallel_drain.py |
| 51-REQ-1.3 | TS-51-3 | 4.1 | test_parallel_drain.py |
| 51-REQ-1.E1 | TS-51-4 | 4.1 | test_parallel_drain.py |
| 51-REQ-1.E2 | TS-51-E1 | 4.1 | test_parallel_drain.py |
| 51-REQ-2.1 | TS-51-5, TS-51-P2 | 2.1 | test_barrier.py |
| 51-REQ-2.2 | TS-51-5, TS-51-P2 | 2.1 | test_barrier.py |
| 51-REQ-2.3 | TS-51-6 | 2.1 | test_barrier.py |
| 51-REQ-2.E1 | TS-51-7, TS-51-P2 | 2.1 | test_barrier.py |
| 51-REQ-3.1 | TS-51-8, TS-51-P3 | 2.2 | test_barrier.py |
| 51-REQ-3.2 | TS-51-8, TS-51-P3 | 2.2 | test_barrier.py |
| 51-REQ-3.3 | TS-51-8 | 2.2 | test_barrier.py |
| 51-REQ-3.E1 | TS-51-9, TS-51-P3 | 2.2 | test_barrier.py |
| 51-REQ-3.E2 | TS-51-10, TS-51-P3 | 2.2 | test_barrier.py |
| 51-REQ-3.E3 | TS-51-11, TS-51-P3 | 2.2 | test_barrier.py |
| 51-REQ-4.1 | TS-51-12, TS-51-P5 | 3.1 | test_hot_load_gates.py |
| 51-REQ-4.2 | TS-51-13 | 3.1 | test_hot_load_gates.py |
| 51-REQ-4.E1 | TS-51-14, TS-51-P5 | 3.1 | test_hot_load_gates.py |
| 51-REQ-5.1 | TS-51-15, TS-51-P6 | 3.2 | test_hot_load_gates.py |
| 51-REQ-5.2 | TS-51-16 | 3.2 | test_hot_load_gates.py |
| 51-REQ-5.E1 | TS-51-17, TS-51-E2, TS-51-P6 | 3.2 | test_hot_load_gates.py |
| 51-REQ-6.1 | TS-51-18, TS-51-P7 | 3.3 | test_hot_load_gates.py |
| 51-REQ-6.2 | TS-51-19, TS-51-P7 | 3.3 | test_hot_load_gates.py |
| 51-REQ-6.3 | TS-51-18, TS-51-P7 | 3.3 | test_hot_load_gates.py |
| 51-REQ-6.E1 | TS-51-20, TS-51-E3, TS-51-P7 | 3.3 | test_hot_load_gates.py |
| 51-REQ-7.1 | TS-51-21, TS-51-P4 | 3.4 | test_hot_load_gates.py |
| 51-REQ-7.2 | TS-51-22, TS-51-P8 | 3.4 | test_hot_load_gates.py |
| 51-REQ-7.3 | TS-51-22, TS-51-P8 | 3.4 | test_hot_load_gates.py |

## Notes

- The `discover_new_specs_gated` function is async because the git-tracked
  gate requires subprocess calls. This makes `_hot_load_new_specs` and
  `_run_sync_barrier_if_needed` async as well — callers already operate in
  an async context so this is non-disruptive.
- The parallel drain modifies `_dispatch_parallel` rather than
  `_run_sync_barrier_if_needed` because the drain must happen before the
  barrier is entered, and it needs access to the pool variable which is
  local to `_dispatch_parallel`.
- The lint gate uses `validate_specs` from `agent_fox.spec.validator` which
  expects a list of `SpecInfo`. We construct a single-element list for the
  candidate spec to reuse the existing validation infrastructure.
