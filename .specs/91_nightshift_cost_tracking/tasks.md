# Implementation Plan: Night-Shift Cost Tracking

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation wires the standard DuckDB audit pipeline into night-shift
operations in four phases: (1) write failing tests, (2) add SinkDispatcher
plumbing and fix session audit emission, (3) add auxiliary cost tracking and
remove JSONL audit, (4) wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_cost_tracking.py tests/integration/nightshift/test_cost_tracking_smoke.py tests/property/nightshift/test_cost_tracking_props.py`
- Unit tests: `uv run pytest -q tests/unit/nightshift/test_cost_tracking.py`
- Property tests: `uv run pytest -q tests/property/nightshift/test_cost_tracking_props.py`
- Integration tests: `uv run pytest -q tests/integration/nightshift/test_cost_tracking_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create unit test file
    - Create `tests/unit/nightshift/test_cost_tracking.py`
    - Add `__init__.py` if missing in `tests/unit/nightshift/`
    - Write test functions for TS-91-1 through TS-91-13
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-91-1 through TS-91-13_

  - [ ] 1.2 Create edge case tests
    - Add tests for TS-91-E1, TS-91-E2, TS-91-E3 in the unit test file
    - Tests MUST fail
    - _Test Spec: TS-91-E1, TS-91-E2, TS-91-E3_

  - [ ] 1.3 Create property tests
    - Create `tests/property/nightshift/test_cost_tracking_props.py`
    - Add `__init__.py` if missing in `tests/property/nightshift/`
    - Write property tests for TS-91-P1, TS-91-P2, TS-91-P3
    - _Test Spec: TS-91-P1, TS-91-P2, TS-91-P3_

  - [ ] 1.4 Create integration smoke tests
    - Create `tests/integration/nightshift/test_cost_tracking_smoke.py`
    - Add `__init__.py` if missing in `tests/integration/nightshift/`
    - Write smoke tests for TS-91-SMOKE-1, TS-91-SMOKE-2, TS-91-SMOKE-3
    - _Test Spec: TS-91-SMOKE-1, TS-91-SMOKE-2, TS-91-SMOKE-3_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [ ] 2. SinkDispatcher plumbing and fix session audit emission
  - [ ] 2.1 Add sink_dispatcher parameter to NightShiftEngine
    - Add optional `sink_dispatcher: SinkDispatcher | None = None` to `__init__`
    - Store as `self._sink`
    - Update `_process_fix()` to pass `sink_dispatcher` to FixPipeline
    - _Requirements: 91-REQ-1.1, 91-REQ-1.3_

  - [ ] 2.2 Add sink_dispatcher to FixPipeline
    - Add optional `sink_dispatcher` parameter to `__init__`, store as `self._sink`
    - Add `_run_id` instance attribute (initially empty)
    - In `process_issue()`, generate a fresh `run_id` via `generate_run_id()` and store as `self._run_id`
    - _Requirements: 91-REQ-2.1, 91-REQ-2.2_

  - [ ] 2.3 Pass sink and run_id to run_session
    - Update `_run_session()` to pass `sink_dispatcher=self._sink` and `run_id=self._run_id` to `run_session()`
    - _Requirements: 91-REQ-3.3_

  - [ ] 2.4 Emit session.complete / session.fail after each session
    - Create `_emit_session_event()` method on FixPipeline
    - Call it after every `_run_session()` call in `_run_triage()` and `_coder_review_loop()`
    - Calculate cost via `calculate_cost()` and include in payload
    - On exception in `_run_session()`, emit `session.fail`
    - _Requirements: 91-REQ-3.1, 91-REQ-3.2, 91-REQ-3.E1_

  - [ ] 2.5 Wire SinkDispatcher in CLI
    - In `night_shift_cmd()`, create `SinkDispatcher` backed by `DuckDBSink`
    - Pass it to `NightShiftEngine`
    - Close DB connection in the `finally` block
    - Handle DuckDB open failure gracefully (log warning, pass None)
    - _Requirements: 91-REQ-1.2, 91-REQ-1.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_cost_tracking.py -k "TS_91_1 or TS_91_2 or TS_91_3 or TS_91_4 or TS_91_5 or TS_91_6 or TS_91_7 or TS_91_8 or TS_91_E1 or TS_91_E2 or TS_91_E3"`
    - [ ] Smoke test TS-91-SMOKE-1 passes
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 91-REQ-1.*, 91-REQ-2.*, 91-REQ-3.* acceptance criteria met

- [ ] 3. Auxiliary cost tracking and JSONL audit removal
  - [ ] 3.1 Create cost_helpers module
    - Create `agent_fox/nightshift/cost_helpers.py` with `emit_auxiliary_cost()`
    - Function extracts tokens from API response, calculates cost, emits `session.complete`
    - No-op when sink is None or run_id is empty
    - _Requirements: 91-REQ-4.1, 91-REQ-4.E1_

  - [ ] 3.2 Wire auxiliary cost tracking into callers
    - Update `nightshift/critic.py: consolidate_findings` / `_run_critic` to accept and use `sink` + `run_id`, call `emit_auxiliary_cost` with archetype `hunt_critic`
    - Update `nightshift/triage.py: run_batch_triage` to accept and use `sink` + `run_id`, call `emit_auxiliary_cost` with archetype `batch_triage`
    - Update `nightshift/staleness.py: check_staleness` to accept and use `sink` + `run_id`, call `emit_auxiliary_cost` with archetype `staleness_check`
    - Update `nightshift/categories/quality_gate.py: _run_ai_analysis` to accept and use `sink` + `run_id`, call `emit_auxiliary_cost` with archetype `quality_gate`
    - Update call sites in `NightShiftEngine` to pass `self._sink` and appropriate run_id
    - _Requirements: 91-REQ-4.1, 91-REQ-4.2, 91-REQ-4.3, 91-REQ-4.4, 91-REQ-4.5_

  - [ ] 3.3 Remove nightshift/audit.py and migrate callers
    - Delete `agent_fox/nightshift/audit.py`
    - Update `NightShiftEngine` to import `emit_audit_event` from `engine/audit_helpers` instead
    - Update all operational event calls to pass `self._sink` and `run_id` as first two args
    - Update `DaemonRunner` to import from `engine/audit_helpers` and accept/pass `sink_dispatcher`
    - _Requirements: 91-REQ-5.1, 91-REQ-5.2, 91-REQ-5.3_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_cost_tracking.py -k "TS_91_9 or TS_91_10 or TS_91_11 or TS_91_12 or TS_91_13"`
    - [ ] Smoke tests TS-91-SMOKE-2 and TS-91-SMOKE-3 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 91-REQ-4.*, 91-REQ-5.* acceptance criteria met

- [ ] 4. Wiring verification
  - [ ] 4.1 Trace every execution path from design.md end-to-end
    - For each path (fix session, auxiliary cost, operational event), verify the
      entry point actually calls the next function in the chain
    - Confirm no function in the chain is a stub that was never replaced
    - _Requirements: all_

  - [ ] 4.2 Verify return values propagate correctly
    - For every function that returns data consumed by a caller, confirm the
      caller receives and uses the return value
    - Grep for callers of `emit_auxiliary_cost`, `_emit_session_event`, etc.
    - _Requirements: all_

  - [ ] 4.3 Run the integration smoke tests
    - All TS-91-SMOKE-* tests pass using real DuckDB (no stub bypass)
    - _Test Spec: TS-91-SMOKE-1, TS-91-SMOKE-2, TS-91-SMOKE-3_

  - [ ] 4.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be justified or replaced
    - Document any intentional stubs with rationale

  - [ ] 4.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 91-REQ-1.1 | TS-91-1 | 2.1 | test_engine_accepts_sink |
| 91-REQ-1.2 | TS-91-3 | 2.5 | test_cli_creates_sink |
| 91-REQ-1.3 | TS-91-2 | 2.1 | test_engine_defaults_none_sink |
| 91-REQ-1.E1 | TS-91-E1 | 2.5 | test_cli_duckdb_unavailable |
| 91-REQ-2.1 | TS-91-5 | 2.2 | test_process_issue_generates_run_id |
| 91-REQ-2.2 | TS-91-4 | 2.2 | test_pipeline_accepts_sink |
| 91-REQ-2.E1 | TS-91-E3 | 2.2 | test_empty_run_id_skips_emission |
| 91-REQ-3.1 | TS-91-7 | 2.4 | test_session_complete_emitted |
| 91-REQ-3.2 | TS-91-8 | 2.4 | test_session_fail_emitted |
| 91-REQ-3.3 | TS-91-6 | 2.3 | test_run_session_passes_sink_and_run_id |
| 91-REQ-3.E1 | TS-91-E2 | 2.4 | test_audit_write_failure_continues |
| 91-REQ-4.1 | TS-91-9 | 3.1, 3.2 | test_emit_auxiliary_cost |
| 91-REQ-4.2 | TS-91-9 | 3.2 | test_emit_auxiliary_cost |
| 91-REQ-4.3 | TS-91-9 | 3.2 | test_emit_auxiliary_cost |
| 91-REQ-4.4 | TS-91-9 | 3.2 | test_emit_auxiliary_cost |
| 91-REQ-4.E1 | TS-91-10 | 3.1 | test_auxiliary_noop_none_sink |
| 91-REQ-5.1 | TS-91-11 | 3.3 | test_jsonl_audit_removed |
| 91-REQ-5.2 | TS-91-12 | 3.3 | test_engine_uses_standard_audit |
| 91-REQ-5.3 | TS-91-13 | 3.3 | test_daemon_uses_standard_audit |
| 91-REQ-5.E1 | TS-91-E3 | 3.3 | test_empty_run_id_skips_emission |
| 91-REQ-6.1 | TS-91-SMOKE-1 | 2.4 | test_smoke_fix_costs_in_status |
| 91-REQ-6.2 | TS-91-SMOKE-1 | 2.4 | test_smoke_fix_costs_in_status |
| 91-REQ-6.3 | TS-91-SMOKE-2 | 3.1 | test_smoke_auxiliary_costs_in_status |

## Notes

- FixPipeline has many `_run_session()` call sites (triage, coder, reviewer,
  reviewer retry). Each must emit a session event. Use `_emit_session_event()`
  consistently after each call.
- The `_run_id` on FixPipeline is set at the start of `process_issue()` and
  used by all sessions within that invocation. It is NOT shared across
  invocations.
- Auxiliary callers (critic, triage, staleness, quality gate) need the sink
  and run_id threaded through from the engine. The engine generates a per-fix
  run_id for fix-related auxiliary calls. For hunt-scan auxiliary calls
  (critic, quality gate), the engine generates a per-scan run_id.
- The `nightshift/audit.py` removal affects `engine.py` and `daemon.py`.
  All references to `_emit_audit_event` from that module must be replaced
  with the standard `emit_audit_event(sink, run_id, event_type, ...)`.
- Existing tests for night-shift modules may need import updates after
  `nightshift/audit.py` is deleted.
