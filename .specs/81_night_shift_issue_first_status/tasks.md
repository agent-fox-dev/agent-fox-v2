# Implementation Plan: Night Shift — Issue-First Ordering & Console Status Output

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Five task groups: (1) write failing tests, (2) implement issue-first gate
in the engine, (3) add callback plumbing to engine and fix pipeline,
(4) integrate ProgressDisplay in CLI and add phase/idle display,
(5) wiring verification.

Groups 2 and 3 are independent and could be parallelized, but group 4
depends on both. The test-first approach ensures all behaviour is validated
before and after implementation.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/ tests/unit/ui/test_progress.py -k "test_81"`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file for issue-first gate logic
    - Create `tests/unit/nightshift/test_issue_first_gate.py`
    - Translate TS-81-1 through TS-81-5 (gate behaviour tests)
    - Translate TS-81-E1, TS-81-E2, TS-81-E3 (gate edge cases)
    - Translate TS-81-P1, TS-81-P2, TS-81-P3 (gate property tests)
    - _Test Spec: TS-81-1, TS-81-2, TS-81-3, TS-81-4, TS-81-5, TS-81-E1, TS-81-E2, TS-81-E3_

  - [ ] 1.2 Create test file for callback plumbing
    - Create `tests/unit/nightshift/test_nightshift_callbacks.py`
    - Translate TS-81-8, TS-81-9, TS-81-17, TS-81-18, TS-81-19 (callback tests)
    - Translate TS-81-E6 (None callbacks)
    - Translate TS-81-P4, TS-81-P7 (callback property tests)
    - _Test Spec: TS-81-8, TS-81-9, TS-81-17, TS-81-18, TS-81-19, TS-81-E6_

  - [ ] 1.3 Create test file for display integration
    - Create `tests/unit/nightshift/test_nightshift_display.py`
    - Translate TS-81-6, TS-81-7 (CLI display lifecycle)
    - Translate TS-81-10 through TS-81-16 (phase lines and idle display)
    - Translate TS-81-E4, TS-81-E5, TS-81-E7, TS-81-E8 (display edge cases)
    - Translate TS-81-P5, TS-81-P6, TS-81-P8 (display property tests)
    - _Test Spec: TS-81-6, TS-81-7, TS-81-10, TS-81-11, TS-81-12, TS-81-13, TS-81-14, TS-81-15, TS-81-16, TS-81-E4, TS-81-E5, TS-81-E7, TS-81-E8_

  - [ ] 1.4 Create test file for ProgressDisplay.print_status
    - Add tests to `tests/unit/ui/test_progress.py` (extend existing file)
    - Test print_status in TTY mode, non-TTY mode, and quiet mode
    - _Test Spec: TS-81-E4, TS-81-E5_

  - [ ] 1.5 Create integration smoke test file
    - Create `tests/integration/nightshift/test_nightshift_smoke.py`
    - Translate TS-81-SMOKE-1, TS-81-SMOKE-2, TS-81-SMOKE-3
    - _Test Spec: TS-81-SMOKE-1, TS-81-SMOKE-2, TS-81-SMOKE-3_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Implement issue-first gate in engine
  - [x] 2.1 Add `_drain_issues` method to NightShiftEngine
    - Calls `_run_issue_check` and loops until no `af:fix` issues remain
    - Respects shutdown flag and cost/session limits between iterations
    - _Requirements: 81-REQ-1.1, 81-REQ-1.4_

  - [x] 2.2 Modify startup sequence in `run()`
    - Replace direct `_run_issue_check` + `_run_hunt_scan` with
      `_drain_issues` → `_run_hunt_scan` → `_drain_issues`
    - _Requirements: 81-REQ-1.2, 81-REQ-1.3_

  - [x] 2.3 Modify timed loop in `run()`
    - When hunt timer fires: call `_drain_issues` first, then
      `_run_hunt_scan`, then `_drain_issues` again
    - When only issue timer fires: call `_run_issue_check` as before
    - _Requirements: 81-REQ-1.4, 81-REQ-1.5_

  - [x] 2.4 Handle pre-hunt drain failure (fail-open)
    - If `_drain_issues` raises (platform API failure), log warning
      and proceed with hunt scan
    - _Requirements: 81-REQ-1.E1, 81-REQ-1.E2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_issue_first_gate.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 81-REQ-1.1 through 81-REQ-1.5, 81-REQ-1.E1 through 81-REQ-1.E3 met

- [x] 3. Add callback plumbing to engine and fix pipeline
  - [x] 3.1 Add callback parameters to NightShiftEngine constructor
    - Add `activity_callback`, `task_callback`, `status_callback` parameters
    - Store as private attributes, default to None
    - _Requirements: 81-REQ-5.1_

  - [x] 3.2 Add callback parameters to FixPipeline constructor
    - Add `activity_callback`, `task_callback` parameters
    - Store as private attributes, default to None
    - _Requirements: 81-REQ-5.2_

  - [x] 3.3 Pass activity_callback from FixPipeline to run_session
    - In `_run_session`, pass `activity_callback` kwarg to `run_session()`
    - _Requirements: 81-REQ-5.2_

  - [x] 3.4 Emit TaskEvent from FixPipeline per archetype
    - Wrap each archetype call in `process_issue` with timing
    - On completion: emit TaskEvent(status="completed", archetype=..., duration_s=...)
    - On failure: emit TaskEvent(status="failed", archetype=..., ...)
    - _Requirements: 81-REQ-5.3_

  - [x] 3.5 Pass callbacks from engine to FixPipeline in `_process_fix`
    - When constructing FixPipeline, pass through the stored callbacks
    - _Requirements: 81-REQ-5.1, 81-REQ-5.E1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_nightshift_callbacks.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 81-REQ-5.1 through 81-REQ-5.3, 81-REQ-5.E1 met

- [x] 4. Integrate ProgressDisplay in CLI and add phase/idle display
  - [x] 4.1 Add `print_status` method to ProgressDisplay
    - Add `print_status(text: str, style: str = "bold cyan")` method
    - Respects quiet mode and non-TTY mode
    - _Requirements: 81-REQ-3.1 (enables phase line rendering)_

  - [x] 4.2 Create and wire ProgressDisplay in `night_shift_cmd`
    - Create `ProgressDisplay` with `AppTheme` from config
    - Start before engine run, stop in finally block
    - Pass `activity_callback`, `task_callback`, and `status_callback`
      (mapped to `print_status`) to `NightShiftEngine`
    - _Requirements: 81-REQ-2.1, 81-REQ-2.2_

  - [x] 4.3 Emit phase lines from engine methods
    - `_run_issue_check`: emit "Checking for af:fix issues…" on entry
    - `_run_hunt_scan`: emit "Starting hunt scan…" on entry, summary on exit
    - `_process_fix`: emit issue number/title on entry, result on exit
    - _Requirements: 81-REQ-3.1, 81-REQ-3.2, 81-REQ-3.3, 81-REQ-3.4, 81-REQ-3.5_

  - [x] 4.4 Implement idle spinner updates in event loop
    - After each tick, calculate next action time from remaining intervals
    - Format time in local timezone using `datetime.now().astimezone()`
    - Update spinner via `activity_callback` with a synthetic ActivityEvent
      or a dedicated idle-update mechanism
    - Show earlier of the two timers per 81-REQ-4.E1
    - _Requirements: 81-REQ-4.1, 81-REQ-4.2, 81-REQ-4.E1_

  - [x] 4.5 Update exit summary to match code command format
    - Ensure summary includes scans, issues fixed, cost
    - Keep existing format (already matches requirement)
    - _Requirements: 81-REQ-2.2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_nightshift_display.py tests/unit/ui/test_progress.py -k "test_81 or test_print_status"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 81-REQ-2.1 through 81-REQ-2.4, 81-REQ-3.1 through 81-REQ-3.5, 81-REQ-4.1, 81-REQ-4.2, 81-REQ-2.E1, 81-REQ-2.E2, 81-REQ-3.E1, 81-REQ-4.E1 met

- [x] 5. Wiring verification

  - [x] 5.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_

  - [x] 5.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_

  - [x] 5.3 Run the integration smoke tests
    - All `TS-81-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-81-SMOKE-1, TS-81-SMOKE-2, TS-81-SMOKE-3_

  - [x] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale
    - Audit results: all `return []` in hunt.py/critic.py/categories/ are error-path
      fallbacks returning empty finding lists (intentional). `pass` in
      cli/nightshift.py:122 and ui/progress.py:233 are exception-suppression in
      cleanup code (intentional). `return None` in dedup.py:76 is Optional return
      (intentional). No stubs, TODOs, or NotImplementedError found in touched files.

  - [x] 5.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
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
| 81-REQ-1.1 | TS-81-1 | 2.1 | `test_issue_first_gate.py::test_hunt_suppressed_while_issues_exist` |
| 81-REQ-1.2 | TS-81-2 | 2.2 | `test_issue_first_gate.py::test_startup_issues_before_hunt` |
| 81-REQ-1.3 | TS-81-3 | 2.2 | `test_issue_first_gate.py::test_post_hunt_issue_drain` |
| 81-REQ-1.4 | TS-81-4 | 2.3 | `test_issue_first_gate.py::test_hunt_timer_with_pending_issues` |
| 81-REQ-1.5 | TS-81-5 | 2.3 | `test_issue_first_gate.py::test_hunt_fires_when_no_issues` |
| 81-REQ-1.E1 | TS-81-E1 | 2.4 | `test_issue_first_gate.py::test_platform_failure_fail_open` |
| 81-REQ-1.E2 | TS-81-E2 | 2.4 | `test_issue_first_gate.py::test_fix_failure_continues` |
| 81-REQ-1.E3 | TS-81-E3 | 2.2, 2.3 | `test_issue_first_gate.py::test_auto_mode_post_hunt_drain` |
| 81-REQ-2.1 | TS-81-6 | 4.2 | `test_nightshift_display.py::test_progress_display_created` |
| 81-REQ-2.2 | TS-81-7 | 4.2, 4.5 | `test_nightshift_display.py::test_exit_summary` |
| 81-REQ-2.3 | TS-81-8 | 3.3, 3.5 | `test_nightshift_callbacks.py::test_activity_forwarded` |
| 81-REQ-2.4 | TS-81-9 | 3.4 | `test_nightshift_callbacks.py::test_task_event_per_archetype` |
| 81-REQ-2.E1 | TS-81-E4 | 4.2 | `test_progress.py::test_print_status_non_tty` |
| 81-REQ-2.E2 | TS-81-E5 | 4.2 | `test_progress.py::test_print_status_quiet` |
| 81-REQ-3.1 | TS-81-10 | 4.3 | `test_nightshift_display.py::test_phase_line_issue_check` |
| 81-REQ-3.2 | TS-81-11 | 4.3 | `test_nightshift_display.py::test_phase_line_hunt_scan` |
| 81-REQ-3.3 | TS-81-12 | 4.3 | `test_nightshift_display.py::test_phase_line_hunt_complete` |
| 81-REQ-3.4 | TS-81-13 | 4.3 | `test_nightshift_display.py::test_phase_line_fix_complete` |
| 81-REQ-3.5 | TS-81-14 | 4.3 | `test_nightshift_display.py::test_phase_line_fix_failed` |
| 81-REQ-3.E1 | TS-81-E7 | 4.3 | `test_nightshift_display.py::test_phase_lines_quiet` |
| 81-REQ-4.1 | TS-81-15 | 4.4 | `test_nightshift_display.py::test_idle_spinner_shows_time` |
| 81-REQ-4.2 | TS-81-16 | 4.4 | `test_nightshift_display.py::test_idle_clears_on_phase` |
| 81-REQ-4.E1 | TS-81-E8 | 4.4 | `test_nightshift_display.py::test_idle_shows_earlier_timer` |
| 81-REQ-5.1 | TS-81-17 | 3.1 | `test_nightshift_callbacks.py::test_constructor_accepts_callbacks` |
| 81-REQ-5.2 | TS-81-18 | 3.2, 3.3 | `test_nightshift_callbacks.py::test_callback_passed_to_session` |
| 81-REQ-5.3 | TS-81-19 | 3.4 | `test_nightshift_callbacks.py::test_task_event_fields` |
| 81-REQ-5.E1 | TS-81-E6 | 3.5 | `test_nightshift_callbacks.py::test_none_callbacks` |
| Property 1 | TS-81-P1 | 2.1, 2.3 | `test_issue_first_gate.py::test_prop_hunt_gate_invariant` |
| Property 2 | TS-81-P2 | 2.2 | `test_issue_first_gate.py::test_prop_post_hunt_drain` |
| Property 3 | TS-81-P3 | 2.2 | `test_issue_first_gate.py::test_prop_startup_order` |
| Property 4 | TS-81-P4 | 3.4 | `test_nightshift_callbacks.py::test_prop_callback_propagation` |
| Property 5 | TS-81-P5 | 4.4 | `test_nightshift_display.py::test_prop_idle_accuracy` |
| Property 6 | TS-81-P6 | 4.2 | `test_nightshift_display.py::test_prop_display_lifecycle` |
| Property 7 | TS-81-P7 | 3.5 | `test_nightshift_callbacks.py::test_prop_backward_compat` |
| Property 8 | TS-81-P8 | 4.3 | `test_nightshift_display.py::test_prop_phase_line_emission` |
| Path 1 | TS-81-SMOKE-1 | 5.3 | `test_nightshift_smoke.py::test_startup_issue_first_display` |
| Path 2 | TS-81-SMOKE-2 | 5.3 | `test_nightshift_smoke.py::test_fix_session_activity_display` |
| Path 3 | TS-81-SMOKE-3 | 5.3 | `test_nightshift_smoke.py::test_idle_state_display` |

## Notes

- Property tests for gate invariants (TS-81-P1, P2, P3) should use
  `hypothesis.given` with strategies generating sequences of tick counts
  and issue counts. Keep `max_examples` moderate (100) to avoid slow CI.
- The `_drain_issues` method should have a safety valve (max iterations)
  to prevent infinite loops if issues are continuously created faster than
  they are fixed. This is not in the requirements but is a defensive measure.
- Task groups 2 and 3 are independent and can be parallelized by separate
  agents working in isolated worktrees.
