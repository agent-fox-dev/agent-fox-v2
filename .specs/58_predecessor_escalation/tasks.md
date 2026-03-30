# Implementation Plan: Predecessor Escalation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a focused change to one code path in `engine/engine.py`. The
`retry_predecessor` branch in `_process_session_result` gains ~15 lines: look
up (or create) the predecessor's escalation ladder, record a failure, and
either reset the predecessor or block it depending on exhaustion state.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_predecessor_escalation.py tests/property/test_predecessor_escalation_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_predecessor_escalation.py`
    - Tests for TS-58-1: reviewer failure records on predecessor ladder
    - Tests for TS-58-2: predecessor reset to pending
    - Tests for TS-58-3: predecessor escalates after retries exhausted at tier
    - Tests for TS-58-4: predecessor blocks on ladder exhaustion
    - Tests for TS-58-5: outcome recorded on predecessor block
    - Tests for TS-58-6: neither node reset when predecessor blocks
    - Tests for TS-58-7: multiple reviewers share predecessor ladder
    - Tests for TS-58-8: cumulative escalation decision
    - Tests for TS-58-E1: predecessor has no ladder (defensive creation)
    - Tests for TS-58-E2: predecessor at ADVANCED ceiling blocks
    - _Test Spec: TS-58-1 through TS-58-8, TS-58-E1, TS-58-E2_

  - [x] 1.2 Create property test file `tests/property/test_predecessor_escalation_props.py`
    - Tests for TS-58-P1: reviewer resets accumulate on predecessor ladder
    - Tests for TS-58-P2: predecessor escalates after N+1 failures
    - Tests for TS-58-P3: exhausted predecessor is blocked
    - Tests for TS-58-P4: missing ladder created defensively
    - _Test Spec: TS-58-P1 through TS-58-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/test_predecessor_escalation.py tests/property/test_predecessor_escalation_props.py`

- [x] 2. Implement predecessor escalation
  - [x] 2.1 Modify `retry_predecessor` branch in `engine/engine.py:_process_session_result`
    - Look up predecessor's ladder from `self._routing.ladders`
    - If missing, create one with archetype default tier and ADVANCED ceiling
    - Call `pred_ladder.record_failure()`
    - If exhausted: call `_record_node_outcome`, `_block_task`, and return
    - If not exhausted: proceed with existing reset logic
    - _Requirements: 58-REQ-1.1, 58-REQ-1.2, 58-REQ-1.3, 58-REQ-1.E1, 58-REQ-2.1, 58-REQ-2.2, 58-REQ-2.3_

  - [x] 2.2 Add necessary imports
    - Import `EscalationLadder` from `routing.escalation` in `engine.py` (if not already imported)
    - Import `ModelTier` (if not already imported)
    - _Requirements: 58-REQ-1.E1_

  - [x] 2.3 Verify no existing tests break
    - Run full test suite to check for regressions
    - Update any tests that mock the `retry_predecessor` path if needed
    - _Requirements: 58-REQ-3.1, 58-REQ-3.2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_predecessor_escalation.py tests/property/test_predecessor_escalation_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/engine/engine.py`
    - [x] Requirements 58-REQ-1.1 through 58-REQ-3.2 acceptance criteria met

- [ ] 3. Checkpoint - Final verification
  - [ ] 3.1 Verify end-to-end escalation behavior
    - Confirm a STANDARD coder escalates to ADVANCED after reviewer-triggered resets
    - Confirm an ADVANCED coder blocks after reviewer-triggered resets exhaust the ladder
    - Confirm multiple reviewers accumulate on the same ladder

  - [ ] 3.V Verify task group 3
    - [ ] Full test suite passes: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 58-REQ-1.1 | TS-58-1 | 2.1 | `test_predecessor_escalation.py::test_reviewer_failure_records_on_pred_ladder` |
| 58-REQ-1.2 | TS-58-2 | 2.1 | `test_predecessor_escalation.py::test_predecessor_reset_to_pending` |
| 58-REQ-1.3 | TS-58-3 | 2.1 | `test_predecessor_escalation.py::test_predecessor_escalates_after_retries` |
| 58-REQ-1.E1 | TS-58-E1 | 2.1 | `test_predecessor_escalation.py::test_no_ladder_created_defensively` |
| 58-REQ-2.1 | TS-58-4 | 2.1 | `test_predecessor_escalation.py::test_predecessor_blocks_on_exhaustion` |
| 58-REQ-2.2 | TS-58-5 | 2.1 | `test_predecessor_escalation.py::test_outcome_recorded_on_block` |
| 58-REQ-2.3 | TS-58-6 | 2.1 | `test_predecessor_escalation.py::test_neither_node_reset_on_block` |
| 58-REQ-2.E1 | TS-58-E2 | 2.1 | `test_predecessor_escalation.py::test_advanced_ceiling_blocks` |
| 58-REQ-3.1 | TS-58-7 | 2.1 | `test_predecessor_escalation.py::test_multiple_reviewers_share_ladder` |
| 58-REQ-3.2 | TS-58-8 | 2.1 | `test_predecessor_escalation.py::test_cumulative_escalation_decision` |
| Property 1 | TS-58-P1 | 2.1 | `test_predecessor_escalation_props.py::test_resets_accumulate` |
| Property 2 | TS-58-P2 | 2.1 | `test_predecessor_escalation_props.py::test_escalates_after_n_plus_1` |
| Property 3 | TS-58-P3 | 2.1 | `test_predecessor_escalation_props.py::test_exhausted_means_blocked` |
| Property 4 | TS-58-P4 | 2.1 | `test_predecessor_escalation_props.py::test_missing_ladder_created` |

## Notes

- The implementation is ~15 lines of new code in one method.
- The `EscalationLadder` class already handles counter resets on escalation and
  exhaustion detection — no changes needed there.
- Tests will need to mock the orchestrator's internal state (graph_sync,
  routing.ladders, state_manager) to exercise the retry_predecessor path.
- This spec depends on spec 57 (tier ceiling always ADVANCED). If spec 57 is
  not yet implemented, the defensive ladder creation in 58-REQ-1.E1 hardcodes
  `ModelTier.ADVANCED` as ceiling regardless.
