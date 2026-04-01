# Implementation Plan: Configuration Hot-Reload at Sync Barriers

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Three implementation groups after failing tests: (1) core reload logic in
the orchestrator, (2) barrier integration and audit event, (3) checkpoint.
The change is focused on `engine.py` and `barrier.py` with a small addition
to the audit event type enum.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_config_reload.py tests/property/engine/test_config_reload_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for config reload
    - Create `tests/unit/engine/test_config_reload.py`
    - Tests for TS-66-1 (barrier trigger), TS-66-2 (no-op hash match),
      TS-66-3 (reload on hash change), TS-66-4 (field updates),
      TS-66-5 (CircuitBreaker rebuild), TS-66-6 (parallel immutable)
    - _Test Spec: TS-66-1, TS-66-2, TS-66-3, TS-66-4, TS-66-5, TS-66-6_

  - [x] 1.2 Create unit tests for auxiliary configs and audit
    - Tests for TS-66-7 (HookConfig), TS-66-8 (ArchetypesConfig),
      TS-66-9 (PlanningConfig), TS-66-10 (audit event),
      TS-66-11 (config path stored)
    - _Test Spec: TS-66-7, TS-66-8, TS-66-9, TS-66-10, TS-66-11_

  - [x] 1.3 Create edge case tests
    - Tests for TS-66-E1 (file missing), TS-66-E2 (invalid TOML),
      TS-66-E3 (I/O error), TS-66-E4 (sync_interval=0)
    - _Test Spec: TS-66-E1, TS-66-E2, TS-66-E3, TS-66-E4_

  - [x] 1.4 Create property tests
    - Create `tests/property/engine/test_config_reload_props.py`
    - Property tests for TS-66-P1 through TS-66-P6
    - _Test Spec: TS-66-P1, TS-66-P2, TS-66-P3, TS-66-P4, TS-66-P5, TS-66-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Implement core reload logic
  - [x] 2.1 Add `CONFIG_RELOADED` to `AuditEventType` enum
    - In `agent_fox/knowledge/audit.py`, add `CONFIG_RELOADED = "config.reloaded"`
    - _Requirements: 66-REQ-6.1_

  - [x] 2.2 Add `config_path` and `full_config` to Orchestrator.__init__
    - Add `config_path: Path | None = None` parameter
    - Add `full_config: AgentFoxConfig | None = None` parameter
    - Store as `self._config_path`, `self._full_config`
    - Initialize `self._config_hash = ""` (empty = first reload always fires)
    - _Requirements: 66-REQ-7.1, 66-REQ-7.2_

  - [x] 2.3 Implement `diff_configs` utility
    - Compare two `AgentFoxConfig` instances field-by-field
    - Return dict of `"section.field"` -> `{"old": ..., "new": ...}`
    - Handle nested Pydantic models by walking `model_fields`
    - _Requirements: 66-REQ-6.2_

  - [x] 2.4 Implement `_reload_config` method on Orchestrator
    - Read config file, compute SHA-256 hash, compare to stored hash
    - On hash match: return immediately (no-op)
    - On hash change: call `load_config`, diff against `self._full_config`,
      update `self._config` (preserving parallel), rebuild CircuitBreaker,
      update auxiliary configs, emit audit event, update stored hash
    - On error: catch exceptions, log warning, return without changes
    - _Requirements: 66-REQ-1.1, 66-REQ-1.2, 66-REQ-1.3, 66-REQ-2.1,
      66-REQ-2.2, 66-REQ-3.1, 66-REQ-3.2, 66-REQ-4.1, 66-REQ-4.2,
      66-REQ-4.3, 66-REQ-5.1, 66-REQ-6.1, 66-REQ-6.2_

  - [x] 2.V Verify task group 2
    - [x] Core reload tests pass: `uv run pytest -q tests/unit/engine/test_config_reload.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/engine/test_config_reload_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 66-REQ-1.*, 66-REQ-2.*, 66-REQ-3.*, 66-REQ-4.*,
          66-REQ-5.*, 66-REQ-6.*, 66-REQ-7.* met

- [ ] 3. Integrate reload into barrier sequence
  - [ ] 3.1 Add `reload_config_fn` parameter to `run_sync_barrier_sequence`
    - In `agent_fox/engine/barrier.py`, add optional callback parameter
    - Call it as the last step of the barrier sequence (after memory summary)
    - Wrap in try/except, log warning on failure
    - _Requirements: 66-REQ-1.1_

  - [ ] 3.2 Wire reload into `_run_sync_barrier_if_needed` and end-of-run
    - Pass `self._reload_config` as `reload_config_fn` to
      `run_sync_barrier_sequence` in both `_run_sync_barrier_if_needed`
      and `_try_end_of_run_discovery`
    - _Requirements: 66-REQ-1.1_

  - [ ] 3.3 Update CLI entry point to pass config_path and full_config
    - In `agent_fox/cli/code.py`, pass `config_path=Path(".agent-fox/config.toml")`
      and `full_config=config` to `Orchestrator()`
    - _Requirements: 66-REQ-7.1, 66-REQ-7.2_

  - [ ] 3.V Verify task group 3
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/engine/test_config_reload.py tests/property/engine/test_config_reload_props.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`

- [ ] 4. Checkpoint — Config Hot-Reload Complete
  - Ensure `make check` passes (lint + all tests).
  - Verify no stale test fixtures reference old Orchestrator signature
    without `config_path`.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|---|---|---|---|
| 66-REQ-1.1 | TS-66-1 | 2.4, 3.1, 3.2 | test_config_reload::test_reload_triggered_at_barrier |
| 66-REQ-1.2 | TS-66-2 | 2.4 | test_config_reload::test_noop_when_hash_matches |
| 66-REQ-1.3 | TS-66-3 | 2.4 | test_config_reload::test_reload_when_hash_differs |
| 66-REQ-1.E1 | TS-66-E1 | 2.4 | test_config_reload::test_missing_file_keeps_config |
| 66-REQ-2.1 | TS-66-4 | 2.4 | test_config_reload::test_orch_fields_updated |
| 66-REQ-2.2 | TS-66-5 | 2.4 | test_config_reload::test_circuit_breaker_rebuilt |
| 66-REQ-2.E1 | TS-66-E4 | 2.4 | test_config_reload::test_sync_interval_zero |
| 66-REQ-3.1 | TS-66-6 | 2.4 | test_config_reload::test_parallel_change_warned |
| 66-REQ-3.2 | TS-66-6 | 2.4 | test_config_reload::test_parallel_change_warned |
| 66-REQ-4.1 | TS-66-7 | 2.4 | test_config_reload::test_hook_config_updated |
| 66-REQ-4.2 | TS-66-8 | 2.4 | test_config_reload::test_archetypes_config_updated |
| 66-REQ-4.3 | TS-66-9 | 2.4 | test_config_reload::test_planning_config_updated |
| 66-REQ-5.1 | TS-66-E2 | 2.4 | test_config_reload::test_invalid_toml_keeps_config |
| 66-REQ-5.E1 | TS-66-E3 | 2.4 | test_config_reload::test_io_error_keeps_config |
| 66-REQ-6.1 | TS-66-10 | 2.4 | test_config_reload::test_audit_event_emitted |
| 66-REQ-6.2 | TS-66-10 | 2.3, 2.4 | test_config_reload::test_audit_event_emitted |
| 66-REQ-6.E1 | TS-66-2 | 2.4 | test_config_reload::test_noop_when_hash_matches |
| 66-REQ-7.1 | TS-66-11 | 2.2 | test_config_reload::test_config_path_stored |
| 66-REQ-7.2 | TS-66-11 | 2.2 | test_config_reload::test_config_path_stored |
| Property 1 | TS-66-P1 | 2.4 | test_config_reload_props::test_noop_unchanged |
| Property 2 | TS-66-P2 | 2.4 | test_config_reload_props::test_mutable_fields_updated |
| Property 3 | TS-66-P3 | 2.4 | test_config_reload_props::test_circuit_breaker_rebuilt |
| Property 4 | TS-66-P4 | 2.4 | test_config_reload_props::test_parallel_immutable |
| Property 5 | TS-66-P5 | 2.4 | test_config_reload_props::test_errors_preserve_config |
| Property 6 | TS-66-P6 | 2.3, 2.4 | test_config_reload_props::test_audit_exact_diff |

## Notes

- The `config_path` parameter is optional on `Orchestrator.__init__` to avoid
  breaking existing callers and tests. When `None`, `_reload_config` is a no-op.
- The `diff_configs` utility compares Pydantic models field-by-field. For
  nested models (HookConfig, etc.), it walks `model_fields` recursively.
  Complex types (lists, dicts) are compared by equality.
- The `parallel` field is preserved by overwriting it on the new
  `OrchestratorConfig` before assigning to `self._config`. This is simpler
  than skipping it during the update.
