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
the config field and audit event type. Task group 3 wires the CLI flags and
watch gate into the engine. Task group 4 implements the watch loop itself.
Task group 5 is a checkpoint to verify full coverage and update documentation.

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

- [x] 3. CLI wiring and watch gate
  - [x] 3.1 Add `--watch` and `--watch-interval` CLI options to `code_cmd`
    - `--watch`: boolean flag, default False
    - `--watch-interval`: int, default None (overrides config)
    - Pass values through to orchestrator config/constructor
    - File: `agent_fox/cli/code.py`
    - _Requirements: 1.1, 1.3, 3.3_

  - [x] 3.2 Wire `watch` flag from CLI through to Orchestrator
    - Store as `self._watch` on Orchestrator (passed via constructor or config)
    - File: `agent_fox/engine/engine.py`, `agent_fox/cli/code.py`
    - _Requirements: 1.1_

  - [x] 3.3 Add watch gate in COMPLETED branch of `Orchestrator.run()`
    - After `_try_end_of_run_discovery()` returns False, check watch mode
    - If watch enabled and hot_load disabled: log warning, return COMPLETED
    - If watch enabled and hot_load enabled: call `_watch_loop()` (stub that
      returns COMPLETED for now — full implementation in group 4)
    - Stall path remains unchanged (stall terminates before watch check)
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 1.1, 1.2, 4.1, 4.E1_

  - [x] 3.V Verify task group 3
    - [x] CLI tests pass: `uv run pytest -q tests/integration/test_watch_mode.py`
    - [x] Hot-load gate tests pass: `uv run pytest -q tests/unit/test_watch_mode.py -k "hot_load or HotLoadGate"`
    - [x] Stall override tests pass: `uv run pytest -q tests/unit/test_watch_mode.py -k "stall"`
    - [x] Property gate tests pass: `uv run pytest -q tests/property/test_watch_mode.py -k "hot_load or gate"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `ruff check agent_fox/cli/code.py agent_fox/engine/engine.py`
    - [x] Requirements 70-REQ-1.1, 70-REQ-1.2, 70-REQ-1.3, 70-REQ-3.3, 70-REQ-4.1, 70-REQ-4.E1 acceptance criteria met

- [x] 4. Fix watch loop test mocks (main loop discovery offset)
  - [x] 4.1 Fix TS-70-8 and TS-70-E2: use discovery mock to set interrupted
    - Both tests currently set `orch._signal.interrupted = True` before
      `orch.run()`, but the main loop's interrupt check at line 507 catches
      this before the watch gate is reached. Fix: set interrupted inside a
      `fake_discovery` side_effect so the flag is set after the main loop
      reaches the discovery call but before the watch loop starts.
    - TS-70-8: `test_watch_loop_checks_interruption_before_sleep`
    - TS-70-E2: `test_empty_plan_enters_watch_loop`
    - Files: `tests/unit/test_watch_mode.py`
    - _Test Spec: TS-70-8, TS-70-E2_

  - [x] 4.2 Fix TS-70-E3: raise exception on mock call 2 not call 1
    - The RuntimeError must occur on mock call 2 (first watch loop call),
      not call 1 (main loop call). The main loop does not catch exceptions
      from `_try_end_of_run_discovery` the same way the watch loop should.
    - File: `tests/unit/test_watch_mode.py`
    - _Test Spec: TS-70-E3_

  - [x] 4.3 Fix TS-70-12 and TS-70-E4: update config on mock call 2
    - Config change must happen on mock call 2 (first watch poll), not
      call 1 (main loop). Otherwise the config is already changed before
      the watch loop's first sleep, and both sleeps use the new value.
    - TS-70-12: `test_watch_interval_updated_mid_run`
    - TS-70-E4: `test_watch_interval_updated_via_hot_reload`
    - File: `tests/unit/test_watch_mode.py`
    - _Test Spec: TS-70-12, TS-70-E4_

  - [x] 4.4 Fix TS-70-6: account for re-entry after watch loop returns None
    - Mock must: return False on call 1 (main loop), True on call 2
      (watch poll finds tasks), then set interrupted on call 3+ to
      terminate the main loop after re-entry.
    - Change expected `state.run_status` from `"completed"` to
      `"interrupted"` (the run can't complete normally with mocked
      discovery that never adds real tasks to the graph).
    - File: `tests/unit/test_watch_mode.py`
    - _Test Spec: TS-70-6_

  - [x] 4.5 Fix TS-70-17: offset mock by 1, add termination condition
    - Mock must: return False on calls 1-2 (main loop + watch poll 1),
      True on call 3 (watch poll 2), then set interrupted on call 4+.
    - This gives 2 WATCH_POLL events: poll 1 (False) and poll 2 (True).
    - File: `tests/unit/test_watch_mode.py`
    - _Test Spec: TS-70-17_

  - [x] 4.V Verify task group 4
    - [x] All fixed tests are syntactically valid: `ruff check tests/unit/test_watch_mode.py`
    - [x] All fixed tests still FAIL (stub returns COMPLETED immediately)
    - [x] Previously passing tests still pass: `uv run pytest -q tests/unit/test_watch_mode.py -k "Config or AuditEnum or hot_load_false or stall or missing_plan or circuit_breaker_before"`
    - [x] No linter warnings: `ruff check tests/`

- [x] 5. Watch loop core implementation
  - [x] 5.1 Add `_watch_poll_count` instance variable
    - Initialize `self._watch_poll_count = 0` in `run()` (before the
      main while loop). This counter is run-scoped and persists across
      multiple `_watch_loop` invocations.
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 5.2_

  - [x] 5.2 Implement `_watch_loop()` skeleton: interrupt checks + sleep
    - Replace the stub with the loop structure from `design.md §
      Watch Loop Implementation Detail`.
    - Steps 1-3 only: check interrupt → emit WATCH_POLL → return if
      interrupted; sleep for `self._config.watch_interval`; check
      interrupt after sleep → emit WATCH_POLL → return if interrupted.
    - Return `state` (with INTERRUPTED status) on interrupt.
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 2.1, 2.5, 4.3_
    - _Test Spec: TS-70-4, TS-70-8, TS-70-15_

  - [x] 5.3 Add discovery call and return logic
    - Steps 5+7 from the design pseudocode: call
      `self._try_end_of_run_discovery(state)`, return `None` if True
      (new tasks), otherwise loop.
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 2.2, 2.3, 2.4_
    - _Test Spec: TS-70-5, TS-70-6, TS-70-7_

  - [x] 5.4 Add WATCH_POLL audit event emission
    - Step 6: emit `WATCH_POLL` after discovery with `poll_number` and
      `new_tasks_found` in payload. Use `emit_audit_event()`.
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 5.1, 5.2_
    - _Test Spec: TS-70-1, TS-70-16, TS-70-17, TS-70-P2_

  - [x] 5.5 Add circuit breaker check and barrier exception handling
    - Step 4: check `self._circuit.should_stop()` after sleep, return
      terminal state if tripped.
    - Step 5 exception handling: wrap `_try_end_of_run_discovery` in
      try/except, log and set `new_tasks = False` on error.
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 4.2, 2.E1_
    - _Test Spec: TS-70-14, TS-70-E3_

  - [x] 5.6 Handle empty plan entering watch loop
    - Verify the existing watch gate (group 3) already handles empty
      plans correctly: empty graph → no ready tasks → not stalled →
      discovery returns False → watch gate → `_watch_loop()`. If this
      flow already works, this subtask is a no-op. If not, adjust the
      watch gate condition.
    - File: `agent_fox/engine/engine.py`
    - _Requirements: 1.E2_
    - _Test Spec: TS-70-E2_

  - [x] 5.V Verify task group 5
    - [x] Watch loop tests pass: `uv run pytest -q tests/unit/test_watch_mode.py -k "WatchLoop or WatchActivation or Termination or AuditEvent or ConfigReload"`
    - [x] Edge case tests pass: `uv run pytest -q tests/unit/test_watch_mode.py -k "EdgeCase"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_watch_mode.py`
    - [x] All spec tests pass: `uv run pytest -q tests/unit/test_watch_mode.py tests/property/test_watch_mode.py tests/integration/test_watch_mode.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `ruff check agent_fox/engine/engine.py`
    - [x] Requirements 70-REQ-2.*, 70-REQ-1.E2, 70-REQ-4.2, 70-REQ-4.3, 70-REQ-5.1, 70-REQ-5.2 met

- [x] 6. Checkpoint - Watch Mode Complete
  - [x] 6.1 Run full test suite and verify all spec tests pass
    - `uv run pytest -q`
    - `ruff check agent_fox/ tests/`
  - [x] 6.2 Update CLI reference documentation
    - Add `--watch` and `--watch-interval` to `docs/cli-reference.md`
  - [x] 6.3 Verify traceability: all requirements covered by passing tests

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
| 70-REQ-1.1 | TS-70-1 | 3.1, 3.2, 3.3 | test_watch_mode.py::TestWatchActivation |
| 70-REQ-1.2 | TS-70-2 | 3.3 | test_watch_mode.py::TestHotLoadGate |
| 70-REQ-1.3 | TS-70-3 | 3.1 | test_watch_mode.py (integration) |
| 70-REQ-1.E1 | TS-70-E1 | 3.3 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-1.E2 | TS-70-E2 | 4.1, 5.6 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-2.1 | TS-70-4 | 5.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.2 | TS-70-5 | 5.3 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.3 | TS-70-6 | 4.4, 5.3 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.4 | TS-70-7 | 5.3 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.5 | TS-70-8 | 4.1, 5.2 | test_watch_mode.py::TestWatchLoop |
| 70-REQ-2.E1 | TS-70-E3 | 4.2, 5.5 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-2.E2 | TS-70-E4 | 4.3 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-3.1 | TS-70-9 | 2.1 | test_watch_mode.py::TestConfig |
| 70-REQ-3.2 | TS-70-10 | 2.1 | test_watch_mode.py::TestConfig |
| 70-REQ-3.3 | TS-70-11 | 3.1 | test_watch_mode.py (integration) |
| 70-REQ-3.4 | TS-70-12 | 4.3 | test_watch_mode.py::TestConfigReload |
| 70-REQ-3.E1 | TS-70-E5 | 2.1 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-4.1 | TS-70-13 | 3.3 | test_watch_mode.py::TestTermination |
| 70-REQ-4.2 | TS-70-14 | 5.5 | test_watch_mode.py::TestTermination |
| 70-REQ-4.3 | TS-70-15 | 5.2 | test_watch_mode.py::TestTermination |
| 70-REQ-4.E1 | TS-70-E6 | 3.3 | test_watch_mode.py::TestEdgeCases |
| 70-REQ-5.1 | TS-70-16 | 5.4 | test_watch_mode.py::TestAuditEvents |
| 70-REQ-5.2 | TS-70-17 | 4.5, 5.4 | test_watch_mode.py::TestAuditEvents |
| 70-REQ-5.3 | TS-70-18 | 2.2 | test_watch_mode.py::TestAuditEnum |
| Property 1 | TS-70-P1 | 2.1 | test_watch_mode.py (property) |
| Property 2 | TS-70-P2 | 5.4 | test_watch_mode.py (property) |
| Property 3 | TS-70-P3 | 3.3 | test_watch_mode.py (property) |
| Property 4 | TS-70-P4 | 3.3 | test_watch_mode.py (property) |

## Notes

- Watch loop tests must mock `asyncio.sleep` to avoid real delays.
- Use `unittest.mock.AsyncMock` for barrier and discovery mocks.
- Existing orchestrator test fixtures can be extended with `watch` parameter.
- The `_signal.interrupted` check pattern already exists in the main loop and
  should be reused in the watch loop.
- Circuit breaker checks in the watch loop reuse `self._circuit.should_stop()`.
- Group 3 used a stub `_watch_loop()` that returns COMPLETED — this is
  intentional. The stub lets CLI and gate tests pass without the full loop.
  Group 5 replaces the stub with the real implementation.
- **CRITICAL: Main loop discovery offset.** The main dispatch loop calls
  `_try_end_of_run_discovery(state)` once before the watch gate. All test
  mocks that count calls to this method must account for this offset. The
  first mock call corresponds to the main loop, not the watch loop. See
  `design.md § Watch Loop Implementation Detail` for the full offset table.
  This offset was the root cause of all previous implementation failures.
- **Do not set `orch._signal.interrupted = True` before `orch.run()`.** The
  main loop checks this flag at line 507 and shuts down before reaching the
  watch gate. Instead, set the flag inside a `fake_discovery` side_effect so
  it takes effect after the main loop's discovery call.
- `poll_number` is an instance variable (`self._watch_poll_count`) on the
  Orchestrator, initialized to 0 in `run()`. It persists across multiple
  `_watch_loop` invocations within the same run.
