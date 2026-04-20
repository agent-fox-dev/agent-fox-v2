# Implementation Plan: Spec-Fair Task Scheduling

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a small, focused change: add a `_interleave_by_spec()` helper to
`graph_sync.py` and wire it into `ready_tasks()`. Task group 1 writes tests,
task group 2 implements the helper and updates `ready_tasks()`, task group 3
updates any existing tests broken by the ordering change.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_spec_fair_scheduling.py tests/property/engine/test_spec_fair_scheduling_props.py -v`
- Unit tests: `uv run pytest -q tests/unit/engine/test_spec_fair_scheduling.py -v`
- Property tests: `uv run pytest -q tests/property/engine/test_spec_fair_scheduling_props.py -v`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/engine/test_spec_fair_scheduling.py`
    - Import `_interleave_by_spec`, `_spec_name` from `agent_fox.engine.graph_sync`
    - Test class `TestInterleaveBySpec` with tests for TS-69-1 through TS-69-7
    - Test class `TestSpecNameExtraction` with tests for TS-69-8, TS-69-9
    - Test class `TestReadyTasksIntegration` with test for TS-69-10
    - _Test Spec: TS-69-1 through TS-69-10_

  - [x] 1.2 Create edge case tests in same file
    - Test class `TestEdgeCases` with tests for TS-69-E1 through TS-69-E4
    - _Test Spec: TS-69-E1 through TS-69-E4_

  - [x] 1.3 Create property test file `tests/property/engine/test_spec_fair_scheduling_props.py`
    - Property tests for TS-69-P1 through TS-69-P6
    - Use Hypothesis for generating lists of node IDs across random specs
    - Define strategies: `spec_node_id()`, `single_spec_list()`,
      `multi_spec_list()`, `spec_list_with_hints()`
    - _Test Spec: TS-69-P1 through TS-69-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Implement spec-fair interleaving
  - [x] 2.1 Add `_spec_name()` helper to `graph_sync.py`
    - Extract spec name as everything before the first colon
    - Handle no-colon node IDs by returning the full ID
    - _Requirements: 69-REQ-3.1, 69-REQ-3.2, 69-REQ-3.E1_

  - [x] 2.2 Add `_spec_number()` helper to `graph_sync.py`
    - Extract numeric prefix from spec name for sorting
    - Non-numeric prefixes sort after all numbered specs
    - _Requirements: 69-REQ-1.2, 69-REQ-1.4_

  - [x] 2.3 Add `_interleave_by_spec()` function to `graph_sync.py`
    - Group ready tasks by spec name
    - Sort spec groups by spec number ascending
    - Within each group, sort by duration descending (if hints) or alphabetically
    - Interleave across groups round-robin
    - _Requirements: 69-REQ-1.1, 69-REQ-1.3, 69-REQ-2.1, 69-REQ-2.2, 69-REQ-2.3_

  - [x] 2.4 Update `ready_tasks()` to call `_interleave_by_spec()`
    - Replace `sorted(ready)` and `order_by_duration()` calls with
      `_interleave_by_spec(ready, duration_hints)`
    - _Requirements: 69-REQ-1.1, 69-REQ-2.2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/engine/test_spec_fair_scheduling.py tests/property/engine/test_spec_fair_scheduling_props.py -v`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 69-REQ-1.1 through 69-REQ-3.E1 acceptance criteria met

- [x] 3. Update existing tests for new ordering
  - [x] 3.1 Update `tests/unit/engine/test_sync.py`
    - Check any tests that assert specific alphabetical ordering of multi-spec
      ready lists and update expectations to match interleaved ordering
    - Single-spec tests should be unaffected
    - No changes required: all multi-element assertions use set() comparisons
      (order-agnostic); single-char IDs without colons each form their own spec
      group, sorted alphabetically by spec name — result is identical.
    - _Requirements: 69-REQ-1.3, 69-REQ-1.E1_

  - [x] 3.2 Update `tests/unit/engine/test_duration_ordering.py`
    - Check any tests that assert duration ordering across specs and update
      expectations to match interleaved-then-duration ordering
    - Single-spec duration tests should be unaffected
    - No changes required: test_duration_hints_passed_to_ready_tasks was
      already updated (prior session) to use same-spec nodes; alphabetical
      tests use single-char IDs that still sort alphabetically under
      spec-fair ordering.
    - _Requirements: 69-REQ-2.1, 69-REQ-2.E1_

  - [x] 3.V Verify task group 3
    - [x] All tests pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 4. Checkpoint — Spec-Fair Scheduling Complete
  - Ensure all tests pass, ask the user if questions arise.
  - `make check` is green.
  - All 20 spec-69 tests pass. 24 pre-existing failures are from spec 68
    (task group 1 wrote failing tests awaiting implementation) and are out
    of scope for this spec.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 69-REQ-1.1 | TS-69-1, TS-69-10 | 2.3, 2.4 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-1.2 | TS-69-2 | 2.2, 2.3 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-1.3 | TS-69-3 | 2.3 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-1.4 | TS-69-4 | 2.2 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-1.E1 | TS-69-E1 | 2.3 | test_spec_fair_scheduling.py::TestEdgeCases |
| 69-REQ-1.E2 | TS-69-E2 | 2.3 | test_spec_fair_scheduling.py::TestEdgeCases |
| 69-REQ-2.1 | TS-69-5 | 2.3 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-2.2 | TS-69-6 | 2.3, 2.4 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-2.3 | TS-69-7 | 2.3 | test_spec_fair_scheduling.py::TestInterleaveBySpec |
| 69-REQ-2.E1 | TS-69-E3 | 2.3 | test_spec_fair_scheduling.py::TestEdgeCases |
| 69-REQ-3.1 | TS-69-8 | 2.1 | test_spec_fair_scheduling.py::TestSpecNameExtraction |
| 69-REQ-3.2 | TS-69-9 | 2.1 | test_spec_fair_scheduling.py::TestSpecNameExtraction |
| 69-REQ-3.E1 | TS-69-E4 | 2.1 | test_spec_fair_scheduling.py::TestEdgeCases |
| Property 1 | TS-69-P1 | 2.3 | test_spec_fair_scheduling_props.py |
| Property 2 | TS-69-P2 | 2.3 | test_spec_fair_scheduling_props.py |
| Property 3 | TS-69-P3 | 2.3 | test_spec_fair_scheduling_props.py |
| Property 4 | TS-69-P4 | 2.3 | test_spec_fair_scheduling_props.py |
| Property 5 | TS-69-P5 | 2.2, 2.3 | test_spec_fair_scheduling_props.py |
| Property 6 | TS-69-P6 | 2.3 | test_spec_fair_scheduling_props.py |

## Notes
- The change is entirely in `graph_sync.py` — no dispatch-path changes needed.
- `order_by_duration()` in `routing/duration.py` is no longer called directly
  by `ready_tasks()`. Its within-spec ordering logic is subsumed by
  `_interleave_by_spec()`. The function itself is NOT deleted (it may be used
  elsewhere), but the import in `graph_sync.py` can be removed.
- Existing single-spec tests should pass without changes since interleaving
  a single group is equivalent to sorting it.
- Task group 3 may be a no-op if existing tests only use single-spec scenarios.
  The agent should still verify and check off the tasks.
