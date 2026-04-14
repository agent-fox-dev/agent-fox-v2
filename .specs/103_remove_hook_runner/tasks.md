# Implementation Plan: Remove Hook Runner

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a removal/refactoring spec. The approach is:

1. Write tests that assert the desired end state (hook runner gone, security
   relocated, ReloadResult dataclass exists).
2. Relocate the security module and create the new package.
3. Remove the hook runner, HookConfig, HookError, CLI flag, and all threading.
4. Update engine modules (ConfigReloader, barrier, session_lifecycle).
5. Clean up tests, fixtures, docs, and config_gen.
6. Wiring verification.

Groups 2-4 are the core changes and are ordered to minimize broken-import
windows: relocate security first (so nothing breaks when hooks/ is deleted),
then delete hooks/, then clean up the engine.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/security/ tests/property/security/ tests/unit/hooks/test_hot_load.py -x`
- Unit tests: `uv run pytest -q tests/unit/ -x`
- Property tests: `uv run pytest -q tests/property/ -x`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/ && uv run ruff format --check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory structure
    - Create `tests/unit/security/__init__.py`
    - Create `tests/unit/security/conftest.py` with `security_config` fixture
    - Create `tests/property/security/__init__.py`
    - _Test Spec: TS-103-1 through TS-103-7, TS-103-E1, TS-103-E2_

  - [x] 1.2 Write unit tests for removal assertions
    - `tests/unit/security/test_removal.py`:
      - TS-103-1: HookConfig absent from AgentFoxConfig
      - TS-103-2: HookError absent from errors module
      - TS-103-3: TOML with [hooks] section parses successfully
      - TS-103-7: config_gen has no HookConfig references
    - _Test Spec: TS-103-1, TS-103-2, TS-103-3, TS-103-7_

  - [x] 1.3 Write unit tests for relocation and ReloadResult
    - `tests/unit/security/test_relocation.py`:
      - TS-103-4: Security module importable at new path
      - TS-103-E1: Old hooks package import fails
    - `tests/unit/engine/test_reload_result.py`:
      - TS-103-5: ReloadResult dataclass fields
      - TS-103-6: ConfigReloader returns ReloadResult
    - _Test Spec: TS-103-4, TS-103-5, TS-103-6, TS-103-E1_

  - [x] 1.4 Write property tests
    - `tests/property/security/test_removal_props.py`:
      - TS-103-P1: Security module functional equivalence
      - TS-103-P2: Hook runner absence in production code
      - TS-103-P3: ReloadResult field access by name
      - TS-103-P4: TOML backward compatibility
    - _Test Spec: TS-103-P1, TS-103-P2, TS-103-P3, TS-103-P4_

  - [x] 1.5 Write integration smoke test
    - `tests/unit/security/test_smoke.py`:
      - TS-103-SMOKE-1: Security allowlist enforcement end-to-end
    - _Test Spec: TS-103-SMOKE-1_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Relocate security module
  - [x] 2.1 Create `agent_fox/security/` package
    - Create `agent_fox/security/__init__.py`
    - Move `agent_fox/hooks/security.py` to `agent_fox/security/security.py`
    - Update the module's logger name from `agent_fox.hooks.security` to
      `agent_fox.security.security`
    - _Requirements: 103-REQ-2.1_

  - [x] 2.2 Update all import sites in production code
    - `agent_fox/session/session.py`: update import path
    - _Requirements: 103-REQ-2.2_

  - [x] 2.3 Update all import sites in test code
    - `tests/unit/session/test_security.py`
    - `tests/property/session/test_security_props.py`
    - `tests/property/test_mode_properties.py`
    - `tests/unit/engine/test_sdk_params_modes.py`
    - _Requirements: 103-REQ-2.2_

  - [x] 2.4 Relocate existing security tests
    - Move `tests/unit/hooks/test_security.py` to
      `tests/unit/security/test_security.py`
    - Move `tests/property/hooks/test_security_props.py` to
      `tests/property/security/test_security_props.py`
    - Update imports within moved test files
    - _Requirements: 103-REQ-2.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests TS-103-4, TS-103-SMOKE-1 pass
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [x] Requirements 103-REQ-2.1, 103-REQ-2.2, 103-REQ-2.3 met

- [ ] 3. Remove hook runner and config types
  - [ ] 3.1 Delete hook runner module and old hooks package
    - Delete `agent_fox/hooks/hooks.py`
    - Delete `agent_fox/hooks/__init__.py`
    - Remove `agent_fox/hooks/` directory
    - _Requirements: 103-REQ-1.1_

  - [ ] 3.2 Remove HookConfig and HookError
    - Remove `HookConfig` class from `agent_fox/core/config.py`
    - Remove `hooks` field from `AgentFoxConfig`
    - Remove `HookError` class from `agent_fox/core/errors.py`
    - Remove HookConfig entries from `agent_fox/core/config_gen.py`
    - _Requirements: 103-REQ-1.2, 103-REQ-1.3, 103-REQ-4.3_

  - [ ] 3.3 Remove `--no-hooks` CLI flag
    - Remove `--no-hooks` option from `agent_fox/cli/code.py`
    - Remove `no_hooks` parameter from `code_cmd` function signature
    - _Requirements: 103-REQ-1.5_

  - [ ] 3.4 Remove hook_config/no_hooks from engine modules
    - `agent_fox/engine/session_lifecycle.py`: remove `hook_config`,
      `no_hooks`, `_build_hook_context`, pre/post hook calls, HookConfig
      and HookContext imports
    - `agent_fox/engine/barrier.py`: remove `hook_config`, `no_hooks`
      params from `run_sync_barrier_sequence`; remove sync barrier hook
      call and its import
    - `agent_fox/engine/engine.py`: remove `_hook_config`, `_no_hooks`
      from `Orchestrator`; remove `hook_config`/`no_hooks` from
      `__init__` params and barrier calls
    - `agent_fox/engine/run.py`: remove `hook_config` and `no_hooks` from
      `orch_kwargs`, `session_runner_factory`, and `_setup_infrastructure`
    - _Requirements: 103-REQ-1.6_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests TS-103-1, TS-103-2, TS-103-3, TS-103-7, TS-103-E1 pass
    - [ ] Spec tests TS-103-P2, TS-103-P4 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 103-REQ-1.* met

- [ ] 4. ConfigReloader modernization and test/doc cleanup
  - [ ] 4.1 Add ReloadResult dataclass to engine.py
    - Define `ReloadResult` as a frozen dataclass with fields: `config`,
      `circuit`, `archetypes`, `planning`
    - Update `ConfigReloader.reload()` return type to `ReloadResult | None`
    - Update `ConfigReloader.reload()` to return `ReloadResult(...)` instead
      of a tuple
    - Update `_apply_reloaded_config` to unpack by field name
    - _Requirements: 103-REQ-3.1, 103-REQ-3.2, 103-REQ-3.3_

  - [ ] 4.2 Delete hook runner test files
    - Delete `tests/unit/hooks/test_runner.py`
    - Delete `tests/property/hooks/test_runner_props.py`
    - _Requirements: 103-REQ-4.1_

  - [ ] 4.3 Clean up conftest and update engine tests
    - Remove `hook_context`, `hook_config`, `tmp_hook_script`, `marker_file`
      fixtures from `tests/unit/hooks/conftest.py`
    - Remove `HookConfig`/`HookContext` imports from conftest
    - Keep `security_config` fixture only if still needed by remaining
      tests in `tests/unit/hooks/`; otherwise move to
      `tests/unit/security/conftest.py`
    - Update engine tests that reference `hook_config`/`no_hooks`:
      `test_config_reload.py`, `test_orchestrator.py`, `test_barrier.py`,
      `test_consolidation_barrier.py`, `test_end_of_run_discovery.py`,
      `test_end_of_run_discovery_props.py`,
      `test_consolidation_smoke.py`,
      `test_prompt_injection_sanitization.py`
    - _Requirements: 103-REQ-4.2, 103-REQ-4.E1_

  - [ ] 4.4 Update documentation
    - Remove `[hooks]` section from `docs/config-reference.md`
    - Remove `--no-hooks` from `docs/cli-reference.md` (if mentioned)
    - _Requirements: 103-REQ-4.4_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests TS-103-5, TS-103-6, TS-103-P3, TS-103-E2 pass
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/security/ tests/property/security/ -x`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 103-REQ-3.*, 103-REQ-4.* met

- [ ] 5. Wiring verification
  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1 (security allowlist enforcement): verify
      `session/session.py` imports from `agent_fox.security.security` and
      the import resolves at runtime
    - Path 2 (config hot-reload): verify `ConfigReloader.reload()` returns
      `ReloadResult` and `_apply_reloaded_config` unpacks by field name
    - Path 3 (sync barrier): verify `run_sync_barrier_sequence` no longer
      references hook_config or run_sync_barrier_hooks
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - Confirm `make_pre_tool_use_hook` return value is used by
      `_permission_callback` in `session.py`
    - Confirm `ReloadResult` fields are applied to orchestrator attributes
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-103-SMOKE-*` tests pass using real components
    - _Test Spec: TS-103-SMOKE-1_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Verify no orphaned imports or unused variables from the removal
    - _Requirements: all_

  - [ ] 5.5 Cross-spec entry point verification
    - Verify `make_pre_tool_use_hook` is called from production code
      (`session/session.py`), not just tests
    - Verify `ReloadResult` is constructed in production code
      (`ConfigReloader.reload`), not just tests
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] `make check` passes

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 103-REQ-1.1 | TS-103-P2 | 3.1 | `test_removal_props.py::test_hook_runner_absent` |
| 103-REQ-1.2 | TS-103-1, TS-103-P2 | 3.2 | `test_removal.py::test_hookconfig_absent`, `test_removal_props.py` |
| 103-REQ-1.3 | TS-103-2, TS-103-P2 | 3.2 | `test_removal.py::test_hookerror_absent`, `test_removal_props.py` |
| 103-REQ-1.4 | TS-103-3, TS-103-P4 | 3.2 | `test_removal.py::test_toml_hooks_ignored`, `test_removal_props.py` |
| 103-REQ-1.5 | TS-103-P2 | 3.3 | `test_removal_props.py` |
| 103-REQ-1.6 | TS-103-P2 | 3.4 | `test_removal_props.py` |
| 103-REQ-1.E1 | TS-103-3, TS-103-P4 | 3.2 | `test_removal.py::test_toml_hooks_ignored` |
| 103-REQ-2.1 | TS-103-4, TS-103-P1 | 2.1 | `test_relocation.py::test_new_import_path` |
| 103-REQ-2.2 | TS-103-P1, TS-103-SMOKE-1 | 2.2, 2.3 | `test_smoke.py`, `test_removal_props.py` |
| 103-REQ-2.3 | TS-103-E2 | 2.4 | `test_hot_load.py` (hot_load suite still passes) |
| 103-REQ-2.E1 | TS-103-E1 | 3.1 | `test_relocation.py::test_old_import_fails` |
| 103-REQ-3.1 | TS-103-5, TS-103-6, TS-103-P3 | 4.1 | `test_reload_result.py` |
| 103-REQ-3.2 | TS-103-6, TS-103-P3 | 4.1 | `test_reload_result.py` |
| 103-REQ-3.3 | TS-103-6 | 4.1 | `test_reload_result.py` |
| 103-REQ-4.1 | TS-103-P2 | 4.2 | `test_removal_props.py` |
| 103-REQ-4.2 | TS-103-E2 | 4.3 | engine test suite passes |
| 103-REQ-4.3 | TS-103-7 | 3.2 | `test_removal.py::test_config_gen_no_hookconfig` |
| 103-REQ-4.4 | -- | 4.4 | manual doc review |
| 103-REQ-4.E1 | TS-103-E2 | 4.3 | `test_hot_load.py` suite passes |

## Notes

- Task group 2 (relocate security) must complete before group 3 (delete
  hooks/) to avoid breaking imports.
- Groups 3 and 4 could theoretically be merged, but separating them keeps
  the "delete" and "refactor/cleanup" concerns isolated.
- Engine test updates in 4.3 may be the most tedious subtask -- many test
  files pass `hook_config=` or `no_hooks=` as kwargs to factories or
  constructors. Each must be read and updated carefully.
- The `security_config` fixture currently lives in
  `tests/unit/hooks/conftest.py`. After relocation, it should live in
  `tests/unit/security/conftest.py`.
