# Implementation Plan: Watch Mode

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Watch mode is a small, focused feature touching four modules: config, CLI,
engine, and audit. Task group 1 writes all failing tests. Task group 2 adds
the config field and audit event type. Task group 3 implements the engine
watch loop and CLI wiring. Task group 4 is a checkpoint to verify full
coverage and update documentation.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_watch_mode.py tests/property/test_watch_mode.py tests/integration/test_watch_mode.py`
- Unit tests: `uv run pytest -q tests/unit/test_watch_mode.py`
- Property tests: `uv run pytest -q tests/property/test_watch_mode.py`
- Integration tests: `uv run pytest -q tests/integration/test_watch_mode.py`
- All tests: `uv run pytest -q`
- Linter: `ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_watch_mode.py`
    - Test classes for config (TS-70-9, TS-70-10), audit enum (TS-70-18)
    - Test classes for watch loop behavior (TS-70-1, TS-70-2, TS-70-4,
      TS-70-5, TS-70-6, TS-70-7, TS-70-8)
    - Test classes for termination (TS-70-13, TS-70-14, TS-70-15)
    - Test classes for audit events (TS-70-16, TS-70-17)
    - Test class for config hot-reload (TS-70-12)
    - _Test Spec: TS-70-1 through TS-70-18_

  - [x] 1.2 Create edge case test file (in `tests/unit/test_watch_mode.py`)
    - TS-70-E1: No plan file with --watch
    - TS-70-E2: Empty plan enters watch loop
    - TS-70-E3: Barrier exception during watch poll
    - TS-70-E4: Watch interval updated via hot-reload
    - TS-70-E5: Watch interval at exact minimum
    - TS-70-E6: Circuit breaker before watch loop entry
    - _Test Spec: TS-70-E1 through TS-70-E6_

  - [x] 1.3 Create property test file `tests/property/test_watch_mode.py`
    - TS-70-P1: Watch interval clamping invariant
    - TS-70-P2: Poll number monotonicity
    - TS-70-P3: Hot-load gate invariant
    - TS-70-P4: Stall overrides watch invariant
    - _Test Spec: TS-70-P1 through TS-70-P4_

  - [x] 1.4 Create integration test file `tests/integration/test_watch_mode.py`
    - TS-70-3: --watch CLI flag accepted
    - TS-70-11: --watch-interval CLI option overrides config
    - _Test Spec: TS-70-3, TS-70-11_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `ruff check tests/unit/test_watch_mode.py tests/property/test_watch_mode.py tests/integration/test_watch_mode.py`

- [x] 2. Config and audit foundations
  - [x] 2.1 Add `watch_interval` field to `OrchestratorConfig`
    - Default: 60, clamping validator: min 10
    - File: `agent_fox/core/config.py`
    - _Requirements: 3.1, 3.2, 3.E1_

  - [x] 2.2 Add `WATCH_POLL` to `AuditEventType` enum
    - Value: `"watch.poll"`
    - File: `agent_fox/knowledge/audit.py`
    - _Requirements: 5.3_

  - [x] 2.3 Add `watch_interval` to config generator descriptions
    - File: `agent_fox/core/config_schema.py` (added to `_BOUNDS_MAP`)
    - _Requirements: 3.1_

  - [x] 2.4 Ensure `watch_interval` is included in config hot-reload mutable fields
    - `diff_configs()` in `agent_fox/engine/config_reload.py` automatically detects all `OrchestratorConfig` field changes; no special handling needed
    - _Requirements: 3.4_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_watch_mode.py -k "config or audit_enum or clamp or minimum"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `ruff check agent_fox/core/config.py agent_fox/knowledge/audit.py`
    - [x] Requirements 70-REQ-3.1, 70-REQ-3.2, 70-REQ-3.E1, 70-REQ-5.3 acceptance criteria met

- [ ] 3. Engine watch loop and CLI wiring
  - [ ] 3.1 Add `--watch` and `--watch-interval` CLI options to `code_cmd`
    - `--watch`: boolean flag, default False
    - `--watch-interval`: int, default None (overrides config)
    - Pass `watch` flag to orchestrator (or store on config)
    - File: `agent_fox/cli/code.py`
    - _Requirements: 1.1, 1.3, 3.3_

  - [ ] 3.2 Implement `_watch_loop()` method on `Orchestrator`
    - Sleep for `watch_interval`, check interruption, check circuit breaker
    - Call `_try_end_of_run_discovery()` on each cycle
    - Emit `WATCH_POLL` audit event with `poll_number` and `new_tasks_found`
    - Return `None` when new tasks found (caller continues), or terminal state
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2_

  - [ ] 3.3 Modify COMPLETED branch in `Orchestrator.run()` main loop
    - After `_try_end_of_run_discovery()` returns False, check watch mode
    - If watch enabled and hot_load enabled: call `_watch_loop()`
    - If watch enabled and hot_load disabled: log warning, return COMPLETED
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 1.1, 1.2, 4.1_

  - [ ] 3.4 Wire `watch` flag from CLI through to Orchestrator
    - Store as `self._watch` on Orchestrator (passed via constructor or config)
    - File: `agent_fox/engine/engine.py`, `agent_fox/cli/code.py`
    - _Requirements: 1.1_

  - [ ] 3.5 Handle empty plan with watch mode
    - Ensure empty graph enters watch loop instead of returning immediately
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 1.E2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/test_watch_mode.py tests/integration/test_watch_mode.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `ruff check agent_fox/cli/code.py agent_fox/engine/engine.py`
    - [ ] Requirements 70-REQ-1.*, 70-REQ-2.*, 70-REQ-4.*, 70-REQ-5.* acceptance criteria met

- [ ] 4. Checkpoint - Watch Mode Complete
  - [ ] 4.1 Run full test suite and verify all spec tests pass
    - `uv run pytest -q`
    - `ruff check agent_fox/ tests/`
  - [ ] 4.2 Update CLI reference documentation
    - Add `--watch` and `--watch-interval` to `docs/cli-reference.md`
  - [ ] 4.3 Verify traceability: all requirements covered by passing tests

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
| 70-REQ-1.1 | TS-70-1 | 3.1, 3.3, 3.4 | test_watch_mode.py::TestWatchActivation |
| 70-REQ-1.2 | TS-70-2 | 3.3 | test_watch_mode.py::TestHotLoadGate |
| 70-REQ-1.3 | TS-70-3 | 3.1 | test_watch_mode.py (integration) |
| 70-REQ-1.E1 | TS-70-E1 | 3.3 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-1.E2 | TS-70-E2 | 3.5 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-2.1 | TS-70-4 | 3.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.2 | TS-70-5 | 3.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.3 | TS-70-6 | 3.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.4 | TS-70-7 | 3.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.5 | TS-70-8 | 3.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.E1 | TS-70-E3 | 3.2 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-2.E2 | TS-70-E4 | 3.2 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-3.1 | TS-70-9 | 2.1 | test_watch_mode.py::TestConfig |
| 70-REQ-3.2 | TS-70-10 | 2.1 | test_watch_mode.py::TestConfig |
| 70-REQ-3.3 | TS-70-11 | 3.1 | test_watch_mode.py (integration) |
| 70-REQ-3.4 | TS-70-12 | 2.4 | test_watch_mode.py::TestConfigReload |
| 70-REQ-3.E1 | TS-70-E5 | 2.1 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-4.1 | TS-70-13 | 3.3 | test_watch_mode.py::TestTermination |
| 70-REQ-4.2 | TS-70-14 | 3.2 | test_watch_mode.py::TestTermination |
| 70-REQ-4.3 | TS-70-15 | 3.2 | test_watch_mode.py::TestTermination |
| 70-REQ-4.E1 | TS-70-E6 | 3.3 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-5.1 | TS-70-16 | 3.2 | test_watch_mode.py::TestAuditEvents |
| 70-REQ-5.2 | TS-70-17 | 3.2 | test_watch_mode.py::TestAuditEvents |
| 70-REQ-5.3 | TS-70-18 | 2.2 | test_watch_mode.py::TestAuditEnum |
| Property 1 | TS-70-P1 | 2.1 | test_watch_mode.py (property) |
| Property 2 | TS-70-P2 | 3.2 | test_watch_mode.py (property) |
| Property 3 | TS-70-P3 | 3.3 | test_watch_mode.py (property) |
| Property 4 | TS-70-P4 | 3.3 | test_watch_mode.py (property) |

## Notes

- Watch loop tests must mock `asyncio.sleep` to avoid real delays.
- Use `unittest.mock.AsyncMock` for barrier and discovery mocks.
- Existing orchestrator test fixtures can be extended with `watch` parameter.
- The `_signal.interrupted` check pattern already exists in the main loop and
  should be reused in the watch loop.
- Circuit breaker checks in the watch loop reuse `self._circuit.should_stop()`.
