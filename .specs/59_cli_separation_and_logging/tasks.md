# Implementation Plan: CLI Separation and Logging Improvements

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into 7 task groups: (1) write failing tests, (2) command
renames, (3) extract export backing module, (4) extract lint-specs backing
module, (5) extract code backing module + remaining commands, (6) progress
display improvements, (7) final verification checkpoint.

The order ensures renames land first (simple, mechanical), then module extraction
(more involved), then UI changes (most visible).

## Test Commands

- Spec tests: `uv run pytest tests/unit/cli/ tests/unit/ui/ tests/property/ui/ -q`
- Unit tests: `make test-unit`
- Property tests: `make test-property`
- All tests: `make test`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file for command renames
    - Create `tests/unit/cli/test_command_renames.py`
    - Tests for TS-59-1 through TS-59-6 (export replaces dump, lint-specs
      replaces lint-spec, old names rejected)
    - Use Click's `CliRunner` for CLI invocations
    - _Test Spec: TS-59-1 through TS-59-6_

  - [x] 1.2 Create test file for backing module separation
    - Create `tests/unit/cli/test_backing_modules.py`
    - Tests for TS-59-7 through TS-59-19 (export, lint-specs, code, and
      remaining commands callable from code)
    - Tests for TS-59-29, TS-59-30 (CLI handler thinness)
    - _Test Spec: TS-59-7 through TS-59-19, TS-59-29, TS-59-30_

  - [x] 1.3 Create test file for progress display improvements
    - Create `tests/unit/ui/test_progress_events.py`
    - Tests for TS-59-20 through TS-59-28 (truncation, archetype labels,
      retry/escalation lines)
    - _Test Spec: TS-59-20 through TS-59-28_

  - [x] 1.4 Create property test file
    - Create `tests/property/ui/test_progress_events_props.py`
    - Property tests for TS-59-P1 through TS-59-P3 (truncation invariant,
      archetype label presence, event line format)
    - _Test Spec: TS-59-P1, TS-59-P2, TS-59-P3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Rename CLI commands
  - [x] 2.1 Rename dump → export
    - Rename `agent_fox/cli/dump.py` → `agent_fox/cli/export.py`
    - Change Click decorator from `@click.command("dump")` to
      `@click.command("export")`
    - Rename function `dump_cmd` → `export_cmd`
    - Update `app.py`: change import and `main.add_command` name
    - _Requirements: 59-REQ-1.1, 59-REQ-1.2_

  - [x] 2.2 Rename lint-spec → lint-specs
    - Rename `agent_fox/cli/lint_spec.py` → `agent_fox/cli/lint_specs.py`
    - Change Click decorator from `@click.command("lint-spec")` to
      `@click.command("lint-specs")`
    - Rename function `lint_spec` → `lint_specs_cmd`
    - Update `app.py`: change import and `main.add_command` name
    - _Requirements: 59-REQ-1.3, 59-REQ-1.4_

  - [x] 2.3 Remove old command registrations
    - Ensure `app.py` does NOT register `dump` or `lint-spec`
    - _Requirements: 59-REQ-1.E1, 59-REQ-1.E2_

  - [x] 2.4 Update all references
    - Update imports in test files that reference the old module names
    - Update `docs/cli-reference.md` with new command names
    - Update any references in `CLAUDE.md`, `docs/skills.md`, etc.
    - _Requirements: 59-REQ-1.1 through 59-REQ-1.4_

  - [x] 2.V Verify task group 2
    - [x] Spec tests TS-59-1 through TS-59-6 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 59-REQ-1.1 through 59-REQ-1.E2 met

- [x] 3. Extract export backing module
  - [x] 3.1 Create `agent_fox/knowledge/export.py`
    - Define `ExportResult` dataclass
    - Implement `export_memory(conn, output_path, *, json_mode)` → `ExportResult`
    - Implement `export_db(conn, output_path, *, json_mode)` → `ExportResult`
    - Move business logic from `cli/export.py` helper functions
    - _Requirements: 59-REQ-2.1, 59-REQ-2.2, 59-REQ-2.3_

  - [x] 3.2 Slim down `cli/export.py`
    - CLI handler calls `export_memory()` / `export_db()` and formats output
    - Remove business logic, keep only Click wiring + output formatting
    - _Requirements: 59-REQ-9.1, 59-REQ-9.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests TS-59-7 through TS-59-9 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 59-REQ-2.1 through 59-REQ-2.3 met

- [x] 4. Extract lint-specs backing module
  - [x] 4.1 Create `agent_fox/spec/lint.py`
    - Define `LintResult` dataclass
    - Implement `run_lint_specs(specs_dir, *, ai, fix, lint_all)` → `LintResult`
    - Move validation orchestration, AI merge, fix application from CLI
    - Do NOT move git operations — those stay in CLI handler
    - _Requirements: 59-REQ-3.1, 59-REQ-3.2, 59-REQ-3.3_

  - [x] 4.2 Slim down `cli/lint_specs.py`
    - CLI handler calls `run_lint_specs()`, formats output, handles git
    - Remove business logic (validation, AI merge, fix coordination)
    - _Requirements: 59-REQ-9.1, 59-REQ-9.2_

  - [x] 4.3 Handle missing specs dir
    - `run_lint_specs` raises `PlanError` when specs_dir doesn't exist
    - CLI handler catches `PlanError` and exits with code 1
    - _Requirements: 59-REQ-3.E1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests TS-59-10 through TS-59-13 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 59-REQ-3.1 through 59-REQ-3.E1 met

- [x] 5. Extract code and remaining command backing modules
  - [x] 5.1 Create `agent_fox/engine/run.py`
    - Implement `run_code(config, *, parallel, no_hooks, max_cost, ...)` →
      `ExecutionState`
    - Move orchestrator initialization, ingestion, fact cache setup from CLI
    - Handle KeyboardInterrupt → return interrupted state
    - _Requirements: 59-REQ-4.1, 59-REQ-4.2, 59-REQ-4.3, 59-REQ-4.E1_

  - [x] 5.2 Slim down `cli/code.py`
    - CLI handler calls `run_code()`, maps status to exit code, formats output
    - _Requirements: 59-REQ-9.1, 59-REQ-9.2_

  - [x] 5.3 Audit and formalize remaining 6 commands
    - Verify/create backing functions for: fix, plan, reset, init, status,
      standup
    - For commands already well-separated (status, standup, plan), ensure
      backing function signature is documented and importable
    - For commands with embedded logic (fix, reset), extract to backing modules
    - _Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3_

  - [x] 5.V Verify task group 5
    - [x] Spec tests TS-59-14 through TS-59-19, TS-59-29, TS-59-30 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 59-REQ-4.1 through 59-REQ-5.3 met

- [ ] 6. Progress display improvements
  - [ ] 6.1 Increase truncation default to 60
    - Change `abbreviate_arg` default `max_len` from 30 to 60
    - Update tests that assert on the old 30-char limit
    - _Requirements: 59-REQ-6.1, 59-REQ-6.2_

  - [ ] 6.2 Extend TaskEvent with archetype and retry fields
    - Add `archetype`, `attempt`, `escalated_from`, `escalated_to`,
      `predecessor_node` fields to `TaskEvent` dataclass
    - All new fields default to `None` for backward compatibility
    - _Requirements: 59-REQ-7.1 through 59-REQ-7.E1_

  - [ ] 6.3 Update `_format_task_line` for archetype display
    - Include `[{archetype}]` in task lines when archetype is not None
    - Add format branches for `status="retry"`, `status="disagreed"`
    - Include escalation suffix when `escalated_from` is set
    - _Requirements: 59-REQ-7.1 through 59-REQ-8.E1_

  - [ ] 6.4 Emit new task events from engine
    - In `result_handler.py`: emit `TaskEvent(status="disagreed")` on
      retry-predecessor reset
    - In `result_handler.py`: emit `TaskEvent(status="retry")` with attempt
      and optional escalation info
    - In `engine.py` or `session_lifecycle.py`: populate `archetype` field
      on existing completed/failed/blocked events
    - _Requirements: 59-REQ-8.1, 59-REQ-8.2, 59-REQ-8.3_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests TS-59-20 through TS-59-28 pass
    - [ ] Property tests TS-59-P1 through TS-59-P3 pass
    - [ ] All existing tests still pass: `make test`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 59-REQ-6.1 through 59-REQ-8.E1 met

- [ ] 7. Checkpoint — Final Verification
  - [ ] 7.1 Run full test suite
    - `make check` passes with zero failures
  - [ ] 7.2 Update documentation
    - Update `docs/cli-reference.md` with new command names and signatures
    - Update `CLAUDE.md` if it references `dump` or `lint-spec`
  - [ ] 7.3 Verify clean working tree
    - All changes committed, feature branch pushed

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 59-REQ-1.1 | TS-59-1 | 2.1 | tests/unit/cli/test_command_renames.py |
| 59-REQ-1.2 | TS-59-2 | 2.1 | tests/unit/cli/test_command_renames.py |
| 59-REQ-1.3 | TS-59-3 | 2.2 | tests/unit/cli/test_command_renames.py |
| 59-REQ-1.4 | TS-59-4 | 2.2 | tests/unit/cli/test_command_renames.py |
| 59-REQ-1.E1 | TS-59-5 | 2.3 | tests/unit/cli/test_command_renames.py |
| 59-REQ-1.E2 | TS-59-6 | 2.3 | tests/unit/cli/test_command_renames.py |
| 59-REQ-2.1 | TS-59-7 | 3.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-2.2 | TS-59-8 | 3.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-2.3 | TS-59-9 | 3.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-3.1 | TS-59-10 | 4.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-3.2 | TS-59-11 | 4.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-3.3 | TS-59-12 | 4.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-3.E1 | TS-59-13 | 4.3 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-4.1 | TS-59-14 | 5.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-4.2 | TS-59-15 | 5.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-4.3 | TS-59-15b | 5.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-4.E1 | TS-59-16 | 5.1 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-5.1 | TS-59-17 | 5.3 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-5.2 | TS-59-18 | 5.3 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-5.3 | TS-59-19 | 5.3 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-6.1 | TS-59-20 | 6.1 | tests/unit/ui/test_progress_events.py |
| 59-REQ-6.2 | TS-59-21 | 6.1 | tests/unit/ui/test_progress_events.py |
| 59-REQ-7.1 | TS-59-22 | 6.3 | tests/unit/ui/test_progress_events.py |
| 59-REQ-7.2 | TS-59-23 | 6.3 | tests/unit/ui/test_progress_events.py |
| 59-REQ-7.3 | TS-59-24 | 6.3 | tests/unit/ui/test_progress_events.py |
| 59-REQ-7.E1 | TS-59-24 | 6.3 | tests/unit/ui/test_progress_events.py |
| 59-REQ-8.1 | TS-59-25 | 6.4 | tests/unit/ui/test_progress_events.py |
| 59-REQ-8.2 | TS-59-26 | 6.4 | tests/unit/ui/test_progress_events.py |
| 59-REQ-8.3 | TS-59-27 | 6.4 | tests/unit/ui/test_progress_events.py |
| 59-REQ-8.E1 | TS-59-28 | 6.4 | tests/unit/ui/test_progress_events.py |
| 59-REQ-9.1 | TS-59-29 | 3.2, 4.2, 5.2 | tests/unit/cli/test_backing_modules.py |
| 59-REQ-9.2 | TS-59-30 | 3.2, 4.2, 5.2 | tests/unit/cli/test_backing_modules.py |
| Property 1 | TS-59-P1 | 6.1 | tests/property/ui/test_progress_props.py |
| Property 2 | TS-59-P2 | 6.3 | tests/property/ui/test_progress_props.py |
| Property 3 | TS-59-P3 | 6.4 | tests/property/ui/test_progress_props.py |

## Notes

- Task group 2 (renames) is a breaking change. No aliases or deprecation
  period per user decision.
- Task group 5.3 covers 6 commands but most are already well-separated.
  The work is primarily formalizing existing separation (adding return types,
  removing `sys.exit` calls) rather than major refactoring.
- Git operations for lint-specs `--fix` remain in the CLI handler (they are
  CLI-specific concerns). The backing module only applies fixes to files.
- The `run_code` backing function is async. The CLI handler wraps it with
  `asyncio.run()`.
