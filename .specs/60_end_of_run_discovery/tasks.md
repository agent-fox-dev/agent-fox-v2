# Implementation Plan: End-of-Run Spec Discovery

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into 3 task groups: (1) write failing tests,
(2) implement end-of-run discovery, (3) final verification checkpoint.

The change is small and focused: one new method on `Orchestrator` and a
three-line modification to the main loop's COMPLETED branch. All barrier and
hot-load logic is reused as-is.

## Test Commands

- Spec tests: `uv run pytest tests/unit/engine/test_end_of_run_discovery.py -q`
- Unit tests: `make test-unit`
- All tests: `make test`
- Linter: `make lint`
- Full check: `make check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file for end-of-run discovery
    - Create `tests/unit/engine/test_end_of_run_discovery.py`
    - Set up fixtures: `mock_barrier`, `mock_graph_sync`,
      `orchestrator_with_mocks`
    - Tests for TC-60-01 through TC-60-06 (discovery trigger, continuation,
      termination, repeated cycles, hot-load gate, barrier failure)
    - _Test Spec: TC-60-01, TC-60-02, TC-60-03, TC-60-04, TC-60-05, TC-60-06_

  - [x] 1.2 Create tests for terminal state exclusivity
    - Add tests for TC-60-07 through TC-60-11 (STALLED, COST_LIMIT,
      SESSION_LIMIT, BLOCK_LIMIT, INTERRUPTED do not trigger discovery)
    - _Test Spec: TC-60-07, TC-60-08, TC-60-09, TC-60-10, TC-60-11_

  - [x] 1.3 Create tests for barrier sequence reuse
    - Add tests for TC-60-12 through TC-60-14 (full barrier call with
      correct parameters, same hot-load function, same audit emitter)
    - _Test Spec: TC-60-12, TC-60-13, TC-60-14_

  - [x] 1.4 Create property tests
    - Create `tests/property/engine/test_end_of_run_discovery_props.py`
    - Property tests for TS-60-P1 through TS-60-P5 (discovery exclusivity,
      hot-load gate, barrier equivalence, graceful failure, loop continuation)
    - _Test Spec: TS-60-P1, TS-60-P2, TS-60-P3, TS-60-P4, TS-60-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Implement end-of-run discovery
  - [x] 2.1 Add `_try_end_of_run_discovery` method to `Orchestrator`
    - Add new async method to `agent_fox/engine/engine.py`
    - Guard on `self._config.hot_load` (return `False` if disabled)
    - Call `run_sync_barrier_sequence()` with same parameters as
      `_run_sync_barrier_if_needed()`
    - Wrap barrier call in try/except, log errors at `error` level
    - Check `self._graph_sync.ready_tasks()` after barrier
    - Return `True` if new ready tasks exist, `False` otherwise
    - _Requirements: 60-REQ-1.1, 60-REQ-1.E1, 60-REQ-1.E2, 60-REQ-3.1,
      60-REQ-3.2, 60-REQ-3.3_

  - [x] 2.2 Modify main loop COMPLETED branch
    - In `Orchestrator.run()`, after the `is_stalled()` check and before
      setting `RunStatus.COMPLETED`, add the discovery call
    - If `_try_end_of_run_discovery()` returns `True`, `continue` the
      main loop
    - Otherwise fall through to COMPLETED termination
    - _Requirements: 60-REQ-1.2, 60-REQ-1.3, 60-REQ-1.4, 60-REQ-2.1,
      60-REQ-2.2, 60-REQ-2.3, 60-REQ-2.4_

  - [x] 2.V Verify task group 2
    - [x] All spec tests pass (green)
    - [x] All existing tests pass: `make test`
    - [x] Linter passes: `make lint`
    - [x] Full check passes: `make check`

- [x] 3. Final verification checkpoint
  - [x] 3.1 Run full test suite
    - `make check` passes with no regressions
    - All 14 test contracts pass
    - _Requirements: all 60-REQ-*_

  - [x] 3.2 Verify traceability
    - Confirm every requirement in `requirements.md` has at least one
      passing test
    - Confirm every test contract in `test_spec.md` is implemented

  - [x] 3.V Verify task group 3
    - [x] All tests pass: `make check`
    - [x] Feature branch pushed to origin
    - [x] Clean working tree: `git status`

## Traceability

| Requirement | Task | Test Contract |
|-------------|------|---------------|
| 60-REQ-1.1 | 2.1 | TC-60-01 |
| 60-REQ-1.2 | 2.2 | TC-60-02 |
| 60-REQ-1.3 | 2.2 | TC-60-03 |
| 60-REQ-1.4 | 2.2 | TC-60-04 |
| 60-REQ-1.E1 | 2.1 | TC-60-05 |
| 60-REQ-1.E2 | 2.1 | TC-60-06 |
| 60-REQ-2.1 | 2.2 | TC-60-07 |
| 60-REQ-2.2 | 2.2 | TC-60-08, TC-60-09 |
| 60-REQ-2.3 | 2.2 | TC-60-10 |
| 60-REQ-2.4 | 2.2 | TC-60-11 |
| 60-REQ-3.1 | 2.1 | TC-60-12 |
| 60-REQ-3.2 | 2.1 | TC-60-13 |
| 60-REQ-3.3 | 2.1 | TC-60-14 |

## Notes

- This is a small, focused spec. Only `engine/engine.py` is modified.
- All barrier and hot-load logic is reused from existing code (spec 51).
- Property tests validate the five correctness properties from `design.md`.
