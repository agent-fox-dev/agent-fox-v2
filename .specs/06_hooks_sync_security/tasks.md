# Implementation Plan: Hooks, Sync Barriers, and Security

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements hook script execution, command allowlist security, sync
barriers, and hot-loading. Task groups are ordered: tests first, then hook
runner, then security/allowlist, then sync barriers and hot-loading.

## Test Commands

- Unit tests: `uv run pytest tests/unit/hooks/ -q`
- Property tests: `uv run pytest tests/property/hooks/ -q`
- All tests: `uv run pytest tests/unit/hooks/ tests/property/hooks/ -q`
- Linter: `uv run ruff check agent_fox/hooks/ agent_fox/engine/hot_load.py`
- Type check: `uv run mypy agent_fox/hooks/ agent_fox/engine/hot_load.py`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test directory structure
    - Create `tests/unit/hooks/__init__.py`
    - Create `tests/unit/hooks/conftest.py` with shared fixtures:
      `tmp_hook_script` (creates executable temp scripts with controlled exit
      codes), `hook_context` (default HookContext), `hook_config` (default
      HookConfig), `tmp_specs_dir` (temp .specs/ directory)
    - Create `tests/property/hooks/__init__.py`

  - [ ] 1.2 Write hook runner tests
    - `tests/unit/hooks/test_runner.py`: TS-06-1 (pre-session order),
      TS-06-2 (post-session context), TS-06-3 (abort mode), TS-06-4 (warn
      mode), TS-06-5 (timeout), TS-06-6 (env vars), TS-06-7 (sync barrier
      context), TS-06-8 (no-hooks bypass)
    - _Test Spec: TS-06-1, TS-06-2, TS-06-3, TS-06-4, TS-06-5, TS-06-6,
      TS-06-7, TS-06-8_

  - [ ] 1.3 Write security / allowlist tests
    - `tests/unit/hooks/test_security.py`: TS-06-9 (default allowlist),
      TS-06-10 (allowed command), TS-06-11 (blocked command), TS-06-12
      (path prefix), TS-06-13 (custom allowlist), TS-06-14 (allowlist
      extend)
    - _Test Spec: TS-06-9, TS-06-10, TS-06-11, TS-06-12, TS-06-13, TS-06-14_

  - [ ] 1.4 Write hot-load tests
    - `tests/unit/hooks/test_hot_load.py`: TS-06-15 (discover and add new
      specs), TS-06-16 (no new specs is no-op)
    - _Test Spec: TS-06-15, TS-06-16_

  - [ ] 1.5 Write edge case tests
    - `tests/unit/hooks/test_runner.py` (append): TS-06-E1 (no hooks),
      TS-06-E2 (hook not found)
    - `tests/unit/hooks/test_security.py` (append): TS-06-E3 (empty command),
      TS-06-E4 (non-Bash tool passthrough), TS-06-E6 (both allowlist options)
    - `tests/unit/hooks/test_hot_load.py` (append): TS-06-E5 (invalid dep),
      TS-06-E7 (sync interval zero)
    - _Test Spec: TS-06-E1, TS-06-E2, TS-06-E3, TS-06-E4, TS-06-E5,
      TS-06-E6, TS-06-E7_

  - [ ] 1.6 Write property tests
    - `tests/property/hooks/test_security_props.py`: TS-06-P1 (enforcement
      completeness), TS-06-P2 (default stability)
    - `tests/property/hooks/test_runner_props.py`: TS-06-P3 (mode
      determinism)
    - `tests/property/hooks/test_hot_load_props.py`: TS-06-P4 (monotonicity)
    - _Test Spec: TS-06-P1, TS-06-P2, TS-06-P3, TS-06-P4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/hooks/ tests/property/hooks/`

- [ ] 2. Implement hook runner
  - [ ] 2.1 Create hook runner module
    - `agent_fox/hooks/__init__.py`
    - `agent_fox/hooks/runner.py`: `HookContext` and `HookResult` dataclasses,
      `build_hook_env()` function
    - _Requirements: 06-REQ-4.1, 06-REQ-4.2_

  - [ ] 2.2 Implement single hook execution
    - `run_hook()`: subprocess.run with timeout, env vars, cwd, stdout/stderr
      capture
    - Handle abort mode (raise HookError) and warn mode (log warning)
    - Handle timeout via subprocess.TimeoutExpired
    - Handle FileNotFoundError for missing scripts
    - _Requirements: 06-REQ-2.1, 06-REQ-2.2, 06-REQ-2.3, 06-REQ-3.1,
      06-REQ-3.2, 06-REQ-2.E1_

  - [ ] 2.3 Implement hook batch execution
    - `run_hooks()`: sequential execution of multiple scripts
    - `run_pre_session_hooks()`: delegates to run_hooks with pre_code list
    - `run_post_session_hooks()`: delegates to run_hooks with post_code list
    - `run_sync_barrier_hooks()`: builds __sync_barrier__ context, delegates
      to run_hooks with sync_barrier list
    - All respect the `no_hooks` flag
    - _Requirements: 06-REQ-1.1, 06-REQ-1.2, 06-REQ-5.1, 06-REQ-1.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/hooks/test_runner.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/hooks/test_runner_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/hooks/`
    - [ ] Requirements 06-REQ-1.*, 06-REQ-2.*, 06-REQ-3.*, 06-REQ-4.*,
      06-REQ-5.* acceptance criteria met

- [ ] 3. Implement security / command allowlist
  - [ ] 3.1 Create security module
    - `agent_fox/hooks/security.py`: `DEFAULT_ALLOWLIST` frozenset with all
      ~46 commands
    - `build_effective_allowlist()`: handle bash_allowlist (replace),
      bash_allowlist_extend (add to default), both set (prefer allowlist, warn)
    - _Requirements: 06-REQ-8.3, 06-REQ-9.1, 06-REQ-9.2, 06-REQ-9.E1_

  - [ ] 3.2 Implement command extraction and checking
    - `extract_command_name()`: first token, strip path prefix to basename,
      raise SecurityError for empty/whitespace
    - `check_command_allowed()`: extract name, check membership, return
      (bool, message)
    - _Requirements: 06-REQ-8.1, 06-REQ-8.2, 06-REQ-8.E1_

  - [ ] 3.3 Implement PreToolUse hook factory
    - `make_pre_tool_use_hook()`: returns a callable that inspects Bash tool
      invocations and returns allow/block decisions
    - Non-Bash tools pass through without inspection
    - _Requirements: 06-REQ-8.1, 06-REQ-8.2, 06-REQ-8.E2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/hooks/test_security.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/hooks/test_security_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/hooks/security.py`
    - [ ] Requirements 06-REQ-8.*, 06-REQ-9.* acceptance criteria met

- [ ] 4. Implement sync barriers and hot-loading
  - [ ] 4.1 Create hot-load module
    - `agent_fox/engine/__init__.py` (if not already present)
    - `agent_fox/engine/hot_load.py`: `discover_new_specs()` function that
      compares `.specs/` contents against known spec names in graph
    - _Requirements: 06-REQ-6.3, 06-REQ-7.E2_

  - [ ] 4.2 Implement hot-load spec integration
    - `hot_load_specs()`: parse tasks.md for new specs, parse cross-spec deps
      from prd.md, create nodes and edges, re-compute topological ordering,
      persist updated plan
    - Handle invalid dependency references: log warning, skip spec
    - _Requirements: 06-REQ-7.1, 06-REQ-7.2, 06-REQ-7.3, 06-REQ-7.E1_

  - [ ] 4.3 Implement sync barrier trigger logic
    - Barrier check function: `should_trigger_barrier(completed_count,
      sync_interval)` returning bool
    - Integration point documentation for orchestrator: after each session
      completion, check barrier, if triggered run barrier hooks + regen
      memory + hot-load
    - _Requirements: 06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/hooks/test_hot_load.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/hooks/test_hot_load_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/engine/hot_load.py`
    - [ ] Requirements 06-REQ-6.*, 06-REQ-7.* acceptance criteria met

- [ ] 5. Checkpoint -- Hooks, Sync Barriers, and Security Complete
  - Ensure all tests pass: `uv run pytest tests/unit/hooks/ tests/property/hooks/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/hooks/ agent_fox/engine/hot_load.py`
  - Ensure type check clean: `uv run mypy agent_fox/hooks/ agent_fox/engine/hot_load.py`
  - Verify all requirements from 06-REQ-1 through 06-REQ-9 are satisfied
  - Verify no regressions in existing tests: `uv run pytest tests/ -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 06-REQ-1.1 | TS-06-1 | 2.3 | tests/unit/hooks/test_runner.py |
| 06-REQ-1.2 | TS-06-2 | 2.3 | tests/unit/hooks/test_runner.py |
| 06-REQ-1.E1 | TS-06-E1 | 2.3 | tests/unit/hooks/test_runner.py |
| 06-REQ-2.1 | TS-06-3 | 2.2 | tests/unit/hooks/test_runner.py |
| 06-REQ-2.2 | TS-06-4 | 2.2 | tests/unit/hooks/test_runner.py |
| 06-REQ-2.3 | TS-06-3 | 2.2 | tests/unit/hooks/test_runner.py |
| 06-REQ-2.E1 | TS-06-E2 | 2.2 | tests/unit/hooks/test_runner.py |
| 06-REQ-3.1 | TS-06-5 | 2.2 | tests/unit/hooks/test_runner.py |
| 06-REQ-3.2 | TS-06-5 | 2.2 | tests/unit/hooks/test_runner.py |
| 06-REQ-4.1 | TS-06-6 | 2.1 | tests/unit/hooks/test_runner.py |
| 06-REQ-4.2 | TS-06-7 | 2.3 | tests/unit/hooks/test_runner.py |
| 06-REQ-5.1 | TS-06-8 | 2.3 | tests/unit/hooks/test_runner.py |
| 06-REQ-6.1 | TS-06-7 | 4.3 | tests/unit/hooks/test_runner.py |
| 06-REQ-6.2 | — | 4.3 | (orchestrator integration) |
| 06-REQ-6.3 | TS-06-15 | 4.1 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-6.E1 | TS-06-E7 | 4.3 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-7.1 | TS-06-15 | 4.2 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-7.2 | TS-06-15 | 4.2 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-7.3 | TS-06-15 | 4.2 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-7.E1 | TS-06-E5 | 4.2 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-7.E2 | TS-06-16 | 4.1 | tests/unit/hooks/test_hot_load.py |
| 06-REQ-8.1 | TS-06-10, TS-06-12 | 3.2 | tests/unit/hooks/test_security.py |
| 06-REQ-8.2 | TS-06-10, TS-06-11 | 3.2 | tests/unit/hooks/test_security.py |
| 06-REQ-8.3 | TS-06-9 | 3.1 | tests/unit/hooks/test_security.py |
| 06-REQ-8.E1 | TS-06-E3 | 3.2 | tests/unit/hooks/test_security.py |
| 06-REQ-8.E2 | TS-06-E4 | 3.3 | tests/unit/hooks/test_security.py |
| 06-REQ-9.1 | TS-06-13 | 3.1 | tests/unit/hooks/test_security.py |
| 06-REQ-9.2 | TS-06-14 | 3.1 | tests/unit/hooks/test_security.py |
| 06-REQ-9.E1 | TS-06-E6 | 3.1 | tests/unit/hooks/test_security.py |
| Property 1 | TS-06-P1 | 3.2 | tests/property/hooks/test_security_props.py |
| Property 3 | TS-06-P2 | 3.1 | tests/property/hooks/test_security_props.py |
| Property 4 | TS-06-P3 | 2.2 | tests/property/hooks/test_runner_props.py |
| Property 5 | TS-06-P4 | 4.2 | tests/property/hooks/test_hot_load_props.py |

## Notes

- Hook scripts in tests should use `#!/bin/sh` for portability across macOS
  and Linux.
- Hook timeout tests should use short timeouts (1-2 seconds) with scripts
  that sleep longer, to keep test execution fast.
- The `tmp_hook_script` fixture should set executable permissions (`chmod +x`)
  on the created scripts.
- Hot-load tests need to create valid `tasks.md` files in temp spec folders.
  Use a minimal format: `- [ ] 1. Test task\n  - [ ] 1.1 Subtask`.
- The PreToolUse hook factory returns a plain callable, not a class. This
  matches the claude-code-sdk hook registration API.
- The `agent_fox/engine/` directory may already exist from spec 04. Check
  before creating `__init__.py`.
