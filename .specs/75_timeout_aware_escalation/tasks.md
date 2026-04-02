# Implementation Plan: Timeout-Aware Escalation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Three implementation phases after test scaffolding:
1. Configuration fields and validation (REQ-4.*)
2. Timeout detection, counter, and parameter extension (REQ-1.*, 2.*, 3.*)
3. Observability and integration wiring (REQ-5.*)

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_timeout_escalation.py tests/unit/core/test_timeout_config.py tests/integration/test_timeout_escalation.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for config validation
    - `tests/unit/core/test_timeout_config.py`
    - Tests for TS-75-16 through TS-75-20 (config defaults, validation)
    - _Test Spec: TS-75-16, TS-75-17, TS-75-18, TS-75-19, TS-75-20_

  - [x] 1.2 Create unit test file for result handler timeout logic
    - `tests/unit/engine/test_timeout_escalation.py`
    - Tests for TS-75-1 through TS-75-15 (detection, counter, extension)
    - Tests for TS-75-21 through TS-75-23 (observability)
    - _Test Spec: TS-75-1 through TS-75-15, TS-75-21 through TS-75-23_

  - [x] 1.3 Create property test file
    - `tests/property/test_timeout_escalation_props.py`
    - Property tests: TS-75-P1 through TS-75-P6
    - _Test Spec: TS-75-P1, TS-75-P2, TS-75-P3, TS-75-P4, TS-75-P5, TS-75-P6_

  - [x] 1.4 Create integration test file
    - `tests/integration/test_timeout_escalation.py`
    - Tests for TS-75-E1, TS-75-E2
    - _Test Spec: TS-75-E1, TS-75-E2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Configuration fields and validation
  - [x] 2.1 Add max_timeout_retries field to RoutingConfig
    - `agent_fox/core/config.py`
    - Type int, default 2, validator clamps to >= 0
    - _Requirements: 75-REQ-4.1, 75-REQ-4.4_

  - [x] 2.2 Add timeout_multiplier field to RoutingConfig
    - Type float, default 1.5, validator clamps to >= 1.0
    - _Requirements: 75-REQ-4.2, 75-REQ-4.5_

  - [x] 2.3 Add timeout_ceiling_factor field to RoutingConfig
    - Type float, default 2.0, validator clamps to >= 1.0
    - _Requirements: 75-REQ-4.3, 75-REQ-4.6_

  - [x] 2.4 Add field descriptions to config_schema.py
    - Add entries to `_DEFAULT_DESCRIPTIONS` and `_BOUNDS_MAP`
    - _Requirements: 75-REQ-4.1, 75-REQ-4.2, 75-REQ-4.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: TS-75-16 through TS-75-20
    - [x] Property tests pass: TS-75-P6
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 75-REQ-4.* acceptance criteria met

- [x] 3. Timeout detection, counter, and parameter extension
  - [x] 3.1 Add timeout state tracking to SessionResultHandler
    - `_timeout_retries: dict[str, int]`
    - `_node_max_turns: dict[str, int | None]`
    - `_node_timeout: dict[str, int]`
    - Wire `max_timeout_retries`, `timeout_multiplier`,
      `timeout_ceiling_factor` from config
    - _Requirements: 75-REQ-2.1_

  - [x] 3.2 Add timeout branch in process()
    - Check `record.status == "timeout"` before calling `_handle_failure()`
    - Route to new `_handle_timeout()` method
    - _Requirements: 75-REQ-1.1, 75-REQ-1.2, 75-REQ-1.3, 75-REQ-1.E1_

  - [x] 3.3 Implement _handle_timeout()
    - Check timeout retry counter against max
    - If below max: increment counter, extend params, reset to pending
    - If at max: fall through to `_handle_failure()`
    - _Requirements: 75-REQ-2.2, 75-REQ-2.3, 75-REQ-2.4, 75-REQ-2.E1,
      75-REQ-2.E2_

  - [x] 3.4 Implement _extend_node_params()
    - Multiply max_turns by multiplier (ceil), skip if None
    - Multiply session_timeout by multiplier (ceil), clamp to ceiling
    - Store in per-node override dicts
    - _Requirements: 75-REQ-3.1, 75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.4,
      75-REQ-3.5, 75-REQ-3.E1, 75-REQ-3.E2_

  - [x] 3.5 Wire per-node overrides into session dispatch
    - Read `_node_timeout` and `_node_max_turns` when launching sessions
    - Pass overrides to `run_session()` via session_lifecycle
    - _Requirements: 75-REQ-3.5_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: TS-75-1 through TS-75-15
    - [x] Property tests pass: TS-75-P1, TS-75-P2, TS-75-P3, TS-75-P4, TS-75-P5
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 75-REQ-1.* through 75-REQ-3.* acceptance criteria met

- [x] 4. Observability and integration
  - [x] 4.1 Add SESSION_TIMEOUT_RETRY audit event type
    - In `agent_fox/knowledge/audit.py`
    - _Requirements: 75-REQ-5.1_
    - Note: Implemented in group 3 as required by _handle_timeout()

  - [x] 4.2 Emit SESSION_TIMEOUT_RETRY in _handle_timeout()
    - Payload: timeout_retry_count, max_timeout_retries,
      original/extended max_turns, original/extended timeout
    - _Requirements: 75-REQ-5.1, 75-REQ-5.3_
    - Note: Implemented in group 3

  - [x] 4.3 Add exhaustion warning log
    - Log warning when timeout retries exhausted, before falling through
    - _Requirements: 75-REQ-5.2_
    - Note: Implemented in group 3

  - [x] 4.4 Integration test: timeout → retry → success
    - Mock backend with timeout then success
    - Verify extended params used on retry
    - _Test Spec: TS-75-E1_

  - [x] 4.5 Integration test: exhaustion → escalation → success
    - Mock backend with repeated timeouts then success at higher tier
    - Verify escalation occurs after timeout exhaustion
    - _Test Spec: TS-75-E2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for this group pass: TS-75-21 through TS-75-23, TS-75-E1, TS-75-E2
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 75-REQ-5.* acceptance criteria met

- [ ] 5. Checkpoint — Timeout-Aware Escalation Complete
  - [ ] All spec tests pass
  - [ ] All property tests pass
  - [ ] Full test suite passes: `make check`
  - [ ] Update documentation if needed

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 75-REQ-1.1 | TS-75-1, TS-75-P1 | 3.2 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-1.2 | TS-75-2 | 3.2 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-1.3 | TS-75-3 | 3.2 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-1.E1 | TS-75-4 | 3.2 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-2.1 | TS-75-5, TS-75-P2 | 3.1, 3.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-2.2 | TS-75-5, TS-75-P1 | 3.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-2.3 | TS-75-6, TS-75-E1 | 3.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-2.4 | TS-75-7, TS-75-P4, TS-75-E2 | 3.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-2.E1 | TS-75-8, TS-75-P2 | 3.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-2.E2 | TS-75-9 | 3.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-3.1 | TS-75-10 | 3.4 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-3.2 | TS-75-11, TS-75-P3 | 3.4 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-3.3 | TS-75-12, TS-75-P3 | 3.4 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-3.4 | TS-75-13, TS-75-P5 | 3.4 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-3.5 | TS-75-14 | 3.4, 3.5 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-3.E1 | TS-75-15, TS-75-P3 | 3.4 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-4.1 | TS-75-16 | 2.1 | tests/unit/core/test_timeout_config.py |
| 75-REQ-4.2 | TS-75-16 | 2.2 | tests/unit/core/test_timeout_config.py |
| 75-REQ-4.3 | TS-75-16 | 2.3 | tests/unit/core/test_timeout_config.py |
| 75-REQ-4.4 | TS-75-17, TS-75-P6 | 2.1 | tests/unit/core/test_timeout_config.py |
| 75-REQ-4.5 | TS-75-18, TS-75-P6 | 2.2 | tests/unit/core/test_timeout_config.py |
| 75-REQ-4.6 | TS-75-19, TS-75-P6 | 2.3 | tests/unit/core/test_timeout_config.py |
| 75-REQ-4.E1 | TS-75-20 | 3.4 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-5.1 | TS-75-21 | 4.1, 4.2 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-5.2 | TS-75-22 | 4.3 | tests/unit/engine/test_timeout_escalation.py |
| 75-REQ-5.3 | TS-75-23 | 4.2 | tests/unit/engine/test_timeout_escalation.py |

## Notes

- Task group 2 (config) is isolated — only config.py and config_schema.py change.
- Task group 3 is the core logic change in result_handler.py. The wiring to
  session dispatch (3.5) may require understanding how `NodeSessionRunner`
  resolves parameters — check `session_lifecycle.py` and `sdk_params.py`.
- The `run_session()` function already accepts `max_turns` and uses
  `config.orchestrator.session_timeout`. Per-node timeout overrides need
  to be threaded through the dispatch layer.
- Existing `_handle_failure()` is not modified — timeout handling is a new
  branch in `process()` that runs BEFORE the failure path.
