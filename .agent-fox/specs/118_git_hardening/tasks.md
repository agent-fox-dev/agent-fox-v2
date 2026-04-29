# Implementation Plan: Git Stack Hardening

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in six groups: (1) failing tests, (2) workspace health
module and force-clean, (3) non-retryable error classification and pre-session
guard, (4) run lifecycle and cascade blocking improvements, (5) develop sync
audit trail and error diagnostics, (6) wiring verification.

Groups are ordered so that the new `health.py` module lands first (group 2),
then consumers that depend on it (groups 3-5). The error classification in
group 3 modifies `errors.py`, `harvest.py`, `result_handler.py`, and
`dispatch.py` together to keep the non-retryable path internally consistent.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/workspace/test_health.py tests/unit/workspace/test_harvester.py tests/unit/engine/test_result_handler.py tests/unit/engine/test_graph_sync.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q -m property`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file for workspace health module
    - Create `tests/unit/workspace/test_health.py`
    - Write test functions for TS-118-1, TS-118-2, TS-118-3, TS-118-4,
      TS-118-5, TS-118-18
    - Tests import from `agent_fox.workspace.health` (module does not exist yet)
    - All tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-118-1, TS-118-2, TS-118-3, TS-118-4, TS-118-5, TS-118-18_

  - [x] 1.2 Write harvest and error classification tests
    - Add test functions to `tests/unit/workspace/test_harvester.py` for
      TS-118-6, TS-118-7, TS-118-9, TS-118-17
    - Tests for `force_clean` parameter on `_clean_conflicting_untracked` and
      `harvest`
    - Tests for `retryable` attribute on `IntegrationError`
    - _Test Spec: TS-118-6, TS-118-7, TS-118-9, TS-118-17_

  - [x] 1.3 Write result handler and dispatch tests
    - Add test functions to `tests/unit/engine/test_result_handler.py` for
      TS-118-8
    - Add test functions for TS-118-10 (pre-session check in dispatch)
    - _Test Spec: TS-118-8, TS-118-10_

  - [x] 1.4 Write cascade blocking tests
    - Add test functions to `tests/unit/engine/test_graph_sync.py` for
      TS-118-15, TS-118-16
    - _Test Spec: TS-118-15, TS-118-16_

  - [x] 1.5 Write run lifecycle and develop sync tests
    - Write tests for TS-118-11, TS-118-12, TS-118-13, TS-118-14
    - _Test Spec: TS-118-11, TS-118-12, TS-118-13, TS-118-14_

  - [x] 1.6 Write edge case and property tests
    - Write edge case tests: TS-118-E1 through TS-118-E10
    - Write property tests: TS-118-P1 through TS-118-P7
    - _Test Spec: TS-118-E1 through TS-118-E10, TS-118-P1 through TS-118-P7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Workspace health module and force-clean
  - [x] 2.1 Create `agent_fox/workspace/health.py`
    - Implement `HealthReport` dataclass
    - Implement `check_workspace_health(repo_root)` using `run_git`
      (`git ls-files --others --exclude-standard` for untracked files,
      `git diff --cached --name-only` for dirty index)
    - Fail-open on git command errors (return empty report, log WARNING)
    - _Requirements: 118-REQ-1.1, 118-REQ-1.3, 118-REQ-1.E1, 118-REQ-1.E2_

  - [x] 2.2 Implement `force_clean_workspace`
    - Remove untracked files listed in the report
    - Reset dirty index via `git checkout -- .`
    - Handle permission errors per file (log WARNING, keep in report)
    - Return updated `HealthReport`
    - _Requirements: 118-REQ-2.1, 118-REQ-2.E1, 118-REQ-2.E2_

  - [x] 2.3 Implement `format_health_diagnostic`
    - Format file list (truncate at 20 with "... and N more")
    - Include `git clean -fd` remediation command
    - Include `--force-clean` suggestion
    - _Requirements: 118-REQ-8.1, 118-REQ-8.2, 118-REQ-8.E1_

  - [x] 2.4 Add `--force-clean` CLI flag and config option
    - Add flag to the `code` command CLI entry point
    - Add `workspace.force_clean` config key
    - CLI flag takes precedence over config
    - _Requirements: 118-REQ-2.2_

  - [x] 2.5 Integrate health gate into engine startup
    - Call `check_workspace_health` at the start of `Orchestrator.run()`
    - If dirty and not force-clean: abort run with formatted diagnostics
    - If dirty and force-clean: call `force_clean_workspace`, proceed
    - If clean: log INFO, proceed
    - Emit `workspace.health_check` audit event
    - _Requirements: 118-REQ-1.2, 118-REQ-1.3, 118-REQ-2.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: TS-118-1, TS-118-2, TS-118-3, TS-118-4, TS-118-5,
          TS-118-18, TS-118-E1, TS-118-E2, TS-118-E3, TS-118-E4, TS-118-E10
    - [x] Property tests pass: TS-118-P1, TS-118-P2, TS-118-P6, TS-118-P7
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] 118-REQ-1.1, 1.2, 1.3, 1.E1, 1.E2, 2.1, 2.2, 2.E1, 2.E2, 8.1,
          8.2, 8.E1 acceptance criteria met

- [x] 3. Non-retryable error classification and pre-session guard
  - [x] 3.1 Add `retryable` attribute to `IntegrationError`
    - Modify `agent_fox/core/errors.py`
    - Add `retryable: bool = True` parameter to `__init__`
    - Store as instance attribute
    - Backward-compatible: default is `True`
    - _Requirements: 118-REQ-3.1_

  - [x] 3.2 Mark harvest untracked-file errors as non-retryable
    - Modify `_clean_conflicting_untracked` in `harvest.py`
    - Set `retryable=False` on the IntegrationError for divergent files
    - Add remediation hints to the error message
    - _Requirements: 118-REQ-3.1, 118-REQ-8.1_

  - [x] 3.3 Thread `force_clean` through harvest
    - Add `force_clean` parameter to `harvest()` and
      `_clean_conflicting_untracked()`
    - When `force_clean=True`: remove divergent files instead of raising
    - Log WARNING listing removed files
    - Emit `workspace.force_clean` audit event
    - _Requirements: 118-REQ-2.3_

  - [x] 3.4 Add `is_non_retryable` to SessionRecord and propagate
    - Add `is_non_retryable: bool = False` field to `SessionRecord`
    - In `_harvest_and_integrate`: check `exc.retryable` on caught
      `IntegrationError`, set `is_non_retryable` accordingly
    - _Requirements: 118-REQ-3.1, 118-REQ-3.2_

  - [x] 3.5 Update result handler to check non-retryable flag
    - In `_handle_failure`: check `record.is_non_retryable`
    - If True: block immediately with "workspace-state" in reason,
      skip escalation ladder
    - _Requirements: 118-REQ-3.2, 118-REQ-3.3_

  - [x] 3.6 Add pre-session workspace check in dispatch
    - In `prepare_launch` (or the dispatch entry point): call
      `check_workspace_health` before creating worktree
    - If dirty: return None (skip dispatch), block node with diagnostics
    - Fail-open on git errors
    - _Requirements: 118-REQ-4.1, 118-REQ-4.2, 118-REQ-4.3, 118-REQ-4.E1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: TS-118-6, TS-118-7, TS-118-8, TS-118-9,
          TS-118-10, TS-118-17, TS-118-E5
    - [x] Property tests pass: TS-118-P3
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] 118-REQ-3.1, 3.2, 3.3, 3.E1, 4.1, 4.2, 4.3, 4.E1, 2.3 acceptance
          criteria met

- [x] 4. Run lifecycle and cascade blocking improvements
  - [x] 4.1 Implement stale run detection
    - Add `detect_and_clean_stale_runs(conn)` function
    - Query runs with status "running", transition to "stalled"
    - Emit `run.stale_detected` audit event per stale run
    - Return count of cleaned runs
    - Call from `Orchestrator.run()` at startup
    - _Requirements: 118-REQ-6.1, 118-REQ-6.E2_

  - [x] 4.2 Register cleanup handler for run lifecycle
    - Register `atexit` handler that transitions current run to "stalled"
    - Handle DB write failures gracefully (log WARNING)
    - Verify terminal status on normal exit
    - _Requirements: 118-REQ-6.2, 118-REQ-6.3, 118-REQ-6.E1_

  - [x] 4.3 Make cascade blocking idempotent
    - Modify `mark_blocked` in `graph_sync.py`
    - Skip transition for already-blocked nodes (no warning, no audit event)
    - Skip transition for completed nodes
    - Log DEBUG for in-progress nodes (skip transition)
    - _Requirements: 118-REQ-7.1, 118-REQ-7.2, 118-REQ-7.E1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: TS-118-13, TS-118-14, TS-118-15, TS-118-16,
          TS-118-E7, TS-118-E8, TS-118-E9
    - [x] Property tests pass: TS-118-P4, TS-118-P5
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] 118-REQ-6.1, 6.2, 6.3, 6.E1, 6.E2, 7.1, 7.2, 7.E1 acceptance
          criteria met

- [x] 5. Develop sync audit trail and run summary diagnostics
  - [x] 5.1 Add audit events to develop sync
    - Modify `_sync_develop_under_lock` in `develop.py`
    - Emit `develop.sync` event on success with method and commit counts
    - Emit `develop.sync_failed` event on failure with reason
    - Log commit counts at INFO before reconciliation
    - _Requirements: 118-REQ-5.1, 118-REQ-5.2, 118-REQ-5.3_

  - [x] 5.2 Add fetch failure audit event
    - Modify `ensure_develop` in `develop.py`
    - Emit `develop.fetch_failed` event when remote is unreachable
    - _Requirements: 118-REQ-5.E1_

  - [x] 5.3 Add workspace-state classification to run summary
    - When run stalls/fails due to workspace-state errors, include
      classification and original error in final summary output
    - _Requirements: 118-REQ-8.3_

  - [x] 5.V Verify task group 5
    - [x] Spec tests pass: TS-118-11, TS-118-12, TS-118-E6
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] 118-REQ-5.1, 5.2, 5.3, 5.E1, 8.3 acceptance criteria met

- [x] 6. Wiring verification

  - [x] 6.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [x] 6.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - Key flows: `check_workspace_health` → `HealthReport` → engine,
      `IntegrationError.retryable` → `SessionRecord.is_non_retryable` →
      result handler, `detect_and_clean_stale_runs` → count → engine log
    - _Requirements: all_

  - [x] 6.3 Run the integration smoke tests
    - All `TS-118-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-118-SMOKE-1 through TS-118-SMOKE-4_

  - [x] 6.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [x] 6.5 Cross-spec entry point verification
    - Verify that `check_workspace_health` is called from `Orchestrator.run()`
      (not just from tests)
    - Verify that `force_clean` flag flows from CLI → config → engine →
      harvest
    - Verify that `detect_and_clean_stale_runs` is called from engine startup
    - Verify that pre-session check is called from dispatch
    - _Requirements: all_

  - [x] 6.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All cross-spec entry points are called from production code
    - [x] All existing tests still pass: `uv run pytest -q`

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
| 118-REQ-1.1 | TS-118-1 | 2.1 | `test_health.py::test_detects_untracked` |
| 118-REQ-1.2 | TS-118-3 | 2.5 | `test_health.py::test_aborts_on_dirty` |
| 118-REQ-1.3 | TS-118-2 | 2.5 | `test_health.py::test_clean_repo` |
| 118-REQ-1.E1 | TS-118-E1 | 2.1 | `test_health.py::test_dirty_index` |
| 118-REQ-1.E2 | TS-118-E2 | 2.1 | `test_health.py::test_git_error_failopen` |
| 118-REQ-2.1 | TS-118-4 | 2.2 | `test_health.py::test_force_clean` |
| 118-REQ-2.2 | TS-118-5 | 2.4 | `test_health.py::test_cli_flag` |
| 118-REQ-2.3 | TS-118-6 | 3.3 | `test_harvester.py::test_force_clean_harvest` |
| 118-REQ-2.E1 | TS-118-E3 | 2.2 | `test_health.py::test_force_clean_dirty_index` |
| 118-REQ-2.E2 | TS-118-E4 | 2.2 | `test_health.py::test_force_clean_permission` |
| 118-REQ-3.1 | TS-118-7 | 3.1, 3.2 | `test_harvester.py::test_nonretryable_error` |
| 118-REQ-3.2 | TS-118-8 | 3.5 | `test_result_handler.py::test_nonretryable_block` |
| 118-REQ-3.3 | TS-118-8 | 3.5 | `test_result_handler.py::test_nonretryable_block` |
| 118-REQ-3.E1 | TS-118-9 | 3.2 | `test_harvester.py::test_merge_conflict_retryable` |
| 118-REQ-4.1 | TS-118-10 | 3.6 | `test_dispatch.py::test_presession_check` |
| 118-REQ-4.2 | TS-118-10 | 3.6 | `test_dispatch.py::test_presession_block` |
| 118-REQ-4.3 | TS-118-10 | 3.6 | `test_dispatch.py::test_presession_pass` |
| 118-REQ-4.E1 | TS-118-E5 | 3.6 | `test_dispatch.py::test_presession_git_error` |
| 118-REQ-5.1 | TS-118-11 | 5.1 | `test_develop.py::test_sync_audit_success` |
| 118-REQ-5.2 | TS-118-12 | 5.1 | `test_develop.py::test_sync_audit_failure` |
| 118-REQ-5.3 | TS-118-11 | 5.1 | `test_develop.py::test_sync_log_divergence` |
| 118-REQ-5.E1 | TS-118-E6 | 5.2 | `test_develop.py::test_fetch_failed_audit` |
| 118-REQ-6.1 | TS-118-13 | 4.1 | `test_engine.py::test_stale_run_detection` |
| 118-REQ-6.2 | TS-118-14 | 4.2 | `test_engine.py::test_cleanup_handler` |
| 118-REQ-6.3 | TS-118-14 | 4.2 | `test_engine.py::test_terminal_status` |
| 118-REQ-6.E1 | TS-118-E7 | 4.2 | `test_engine.py::test_cleanup_db_failure` |
| 118-REQ-6.E2 | TS-118-E8 | 4.1 | `test_engine.py::test_multiple_stale_runs` |
| 118-REQ-7.1 | TS-118-15 | 4.3 | `test_graph_sync.py::test_idempotent_blocked` |
| 118-REQ-7.2 | TS-118-16 | 4.3 | `test_graph_sync.py::test_skip_completed` |
| 118-REQ-7.E1 | TS-118-E9 | 4.3 | `test_graph_sync.py::test_skip_in_progress` |
| 118-REQ-8.1 | TS-118-17 | 3.2, 2.3 | `test_harvester.py::test_error_diagnostics` |
| 118-REQ-8.2 | TS-118-18 | 2.3 | `test_health.py::test_diagnostic_format` |
| 118-REQ-8.3 | TS-118-3 | 5.3 | `test_engine.py::test_run_summary_classification` |
| 118-REQ-8.E1 | TS-118-E10 | 2.3 | `test_health.py::test_file_truncation` |
| Property 1 | TS-118-P1 | 2.1 | `test_health.py::test_completeness_property` |
| Property 2 | TS-118-P2 | 2.2 | `test_health.py::test_force_clean_safety_property` |
| Property 3 | TS-118-P3 | 3.2 | `test_harvester.py::test_retryable_classification` |
| Property 4 | TS-118-P4 | 4.3 | `test_graph_sync.py::test_idempotent_property` |
| Property 5 | TS-118-P5 | 4.1 | `test_engine.py::test_lifecycle_completeness` |
| Property 6 | TS-118-P6 | 2.3 | `test_health.py::test_message_completeness` |
| Property 7 | TS-118-P7 | 2.1 | `test_health.py::test_monotonicity_property` |
| Path 1 | TS-118-SMOKE-1 | 6.3 | `test_integration.py::test_health_gate_blocks` |
| Path 1+2 | TS-118-SMOKE-2 | 6.3 | `test_integration.py::test_force_clean_harvest` |
| Path 2 | TS-118-SMOKE-3 | 6.3 | `test_integration.py::test_nonretryable_skip` |
| Path 5 | TS-118-SMOKE-4 | 6.3 | `test_integration.py::test_stale_run_cleanup` |

## Notes

- All git operations use the existing `run_git` wrapper from
  `agent_fox/workspace/git.py` for consistency and timeout handling.
- The `force_clean` flag is opt-in and defaults to `False` everywhere to
  preserve the existing conservative behavior.
- Property tests use `hypothesis` with `@given` strategies generating file
  paths and repo states. Each property test creates a temporary git repo via
  `tmp_path`.
- Integration smoke tests use real git repositories and real harvest/health
  modules. Only the coding session itself and the audit event sink are mocked.
