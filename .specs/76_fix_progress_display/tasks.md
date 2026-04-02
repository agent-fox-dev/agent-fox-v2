# Implementation Plan: Fix Command Progress Display

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds progress visualization to the `fix` command by:
1. Defining two lightweight event dataclasses (`FixProgressEvent`, `CheckEvent`)
2. Adding callback parameters to `run_checks`, `run_fix_loop`, `run_improve_loop`
3. Wiring `ProgressDisplay` and callbacks in `fix_cmd`

Task group 1 writes failing tests. Task group 2 adds the event types and
callback parameters to the core functions. Task group 3 wires everything in
the CLI layer.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_fix_progress.py tests/property/test_fix_progress_props.py`
- Unit tests: `uv run pytest -q tests/unit/test_fix_progress.py`
- Property tests: `uv run pytest -q tests/property/test_fix_progress_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_fix_progress.py`
    - Scaffold test file with imports and fixtures
    - Write tests TS-76-1 through TS-76-3 (banner rendering/suppression)
    - Write tests TS-76-4 through TS-76-6 (ProgressDisplay lifecycle)
    - Write tests TS-76-7, TS-76-8 (activity callback wiring)
    - Write tests TS-76-9 through TS-76-14 (fix/improve loop events)
    - Write tests TS-76-15, TS-76-16 (check callback events)
    - Write tests TS-76-17 through TS-76-19 (signature inspection)
    - Write edge case tests TS-76-E1 through TS-76-E5
    - _Test Spec: TS-76-1 through TS-76-19, TS-76-E1 through TS-76-E5_

  - [x] 1.2 Create property test file `tests/property/test_fix_progress_props.py`
    - Write TS-76-P1 (quiet suppression invariant)
    - Write TS-76-P2 (lifecycle completeness)
    - Write TS-76-P3 (activity callback wiring invariant)
    - Write TS-76-P4 (backward compatibility)
    - Write TS-76-P5 (progress event completeness)
    - Write TS-76-P6 (check event pairing)
    - _Test Spec: TS-76-P1 through TS-76-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/test_fix_progress.py tests/property/test_fix_progress_props.py`

- [ ] 2. Add event types and callback parameters
  - [ ] 2.1 Define `FixProgressEvent` and `CheckEvent` dataclasses
    - Add to `agent_fox/fix/events.py` (new file)
    - Define `FixProgressCallback` and `CheckCallback` type aliases
    - _Requirements: 76-REQ-6.1, 76-REQ-6.2, 76-REQ-6.3_

  - [ ] 2.2 Add `check_callback` parameter to `run_checks`
    - Add optional `check_callback: CheckCallback | None = None` parameter
    - Emit `CheckEvent(stage="start")` before each check
    - Emit `CheckEvent(stage="done", passed=..., exit_code=...)` after each check
    - Handle timeout case (passed=False)
    - _Requirements: 76-REQ-5.1, 76-REQ-5.2, 76-REQ-6.3, 76-REQ-6.E2_

  - [ ] 2.3 Add `progress_callback` and `check_callback` to `run_fix_loop`
    - Add optional callback parameters to signature
    - Emit events: checks_start, all_passed, clusters_found, session_start,
      session_done, session_error, cost_limit
    - Forward `check_callback` to `run_checks` calls
    - _Requirements: 76-REQ-4.1, 76-REQ-4.2, 76-REQ-4.3, 76-REQ-4.4,
      76-REQ-4.E1, 76-REQ-4.E2, 76-REQ-6.1, 76-REQ-6.E1_

  - [ ] 2.4 Add `progress_callback` to `run_improve_loop`
    - Add optional callback parameter to signature
    - Emit events: analyzer_start, analyzer_done, coder_start, coder_done,
      verifier_start, verifier_done/verifier_pass/verifier_fail, converged,
      cost_limit
    - _Requirements: 76-REQ-4.5, 76-REQ-4.6, 76-REQ-6.2, 76-REQ-6.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/test_fix_progress.py -k "signature or callback_none or check_callback or fix_loop_emit or improve_loop_emit"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/fix/`

- [ ] 3. Wire CLI layer and session runners
  - [ ] 3.1 Add `activity_callback` parameter to session runner builders
    - Update `_build_fix_session_runner` to accept and forward `activity_callback`
    - Update `_build_improve_session_runner` to accept and forward `activity_callback`
    - _Requirements: 76-REQ-3.1, 76-REQ-3.2_

  - [ ] 3.2 Add `ProgressDisplay` lifecycle to `fix_cmd`
    - Create `AppTheme` via `create_theme(config.theme)`
    - Create `ProgressDisplay(theme, quiet=quiet or json_mode)`
    - Call `progress.start()` before fix loop
    - Call `progress.stop()` in finally block
    - _Requirements: 76-REQ-2.1, 76-REQ-2.2, 76-REQ-2.3, 76-REQ-2.E1_

  - [ ] 3.3 Add banner rendering to `fix_cmd`
    - Call `render_banner(theme)` when not quiet and not JSON mode
    - _Requirements: 76-REQ-1.1, 76-REQ-1.2, 76-REQ-1.3_

  - [ ] 3.4 Wire progress and check callbacks in `fix_cmd`
    - Create `on_fix_progress` handler that converts `FixProgressEvent` to
      milestone lines via `progress.on_task_event` or direct console print
    - Create `on_check` handler that updates spinner on start and prints
      milestone on done
    - Pass callbacks to `run_fix_loop` and `run_improve_loop`
    - Pass `activity_callback` to session runner builders
    - _Requirements: 76-REQ-3.3, 76-REQ-4.1 through 76-REQ-4.6, 76-REQ-5.1,
      76-REQ-5.2_

  - [ ] 3.V Verify task group 3
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/test_fix_progress.py tests/property/test_fix_progress_props.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 76-REQ-1.* through 76-REQ-6.* acceptance criteria met

- [ ] 4. Checkpoint — Fix Progress Display Complete
  - Ensure all tests pass: `make check`
  - Create or update documentation if needed
  - Verify no regressions in existing fix command behavior

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 76-REQ-1.1 | TS-76-1 | 3.3 | test_banner_rendered |
| 76-REQ-1.2 | TS-76-2 | 3.3 | test_banner_suppressed_quiet |
| 76-REQ-1.3 | TS-76-3 | 3.3 | test_banner_suppressed_json |
| 76-REQ-2.1 | TS-76-4 | 3.2 | test_progress_created_and_started |
| 76-REQ-2.2 | TS-76-5 | 3.2 | test_progress_stopped_on_error |
| 76-REQ-2.3 | TS-76-6 | 3.2 | test_progress_quiet_when_quiet |
| 76-REQ-2.E1 | TS-76-E1 | 3.2 | test_progress_stopped_on_interrupt |
| 76-REQ-3.1 | TS-76-7 | 3.1 | test_fix_runner_passes_activity_callback |
| 76-REQ-3.2 | TS-76-8 | 3.1 | test_improve_runner_passes_activity_callback |
| 76-REQ-3.3 | TS-76-7, TS-76-8 | 3.4 | (covered by callback wiring tests) |
| 76-REQ-4.1 | TS-76-9 | 2.3 | test_fix_loop_emits_pass_start |
| 76-REQ-4.2 | TS-76-10 | 2.3 | test_fix_loop_emits_all_passed |
| 76-REQ-4.3 | TS-76-11 | 2.3 | test_fix_loop_emits_clusters_found |
| 76-REQ-4.4 | TS-76-12 | 2.3 | test_fix_loop_emits_session_start |
| 76-REQ-4.5 | TS-76-13 | 2.4 | test_improve_loop_emits_pass_start |
| 76-REQ-4.6 | TS-76-14 | 2.4 | test_improve_loop_emits_role_events |
| 76-REQ-4.E1 | TS-76-E2 | 2.3 | test_cost_limit_milestone |
| 76-REQ-4.E2 | TS-76-E3 | 2.3 | test_session_error_milestone |
| 76-REQ-5.1 | TS-76-15 | 2.2 | test_check_callback_start |
| 76-REQ-5.2 | TS-76-16 | 2.2 | test_check_callback_done |
| 76-REQ-6.1 | TS-76-17 | 2.3 | test_fix_loop_signature |
| 76-REQ-6.2 | TS-76-18 | 2.4 | test_improve_loop_signature |
| 76-REQ-6.3 | TS-76-19 | 2.2 | test_run_checks_signature |
| 76-REQ-6.E1 | TS-76-E4 | 2.3 | test_fix_loop_none_callback |
| 76-REQ-6.E2 | TS-76-E5 | 2.2 | test_run_checks_none_callback |
| Property 1 | TS-76-P1 | 3.2 | test_quiet_suppression_invariant |
| Property 2 | TS-76-P2 | 3.2 | test_lifecycle_completeness |
| Property 3 | TS-76-P3 | 3.1 | test_callback_wiring_invariant |
| Property 4 | TS-76-P4 | 2.2, 2.3 | test_backward_compatibility |
| Property 5 | TS-76-P5 | 2.3 | test_event_completeness |
| Property 6 | TS-76-P6 | 2.2 | test_check_event_pairing |

## Notes

- All new callback parameters default to `None` for full backward compatibility.
- No changes to `ProgressDisplay` or `render_banner` are needed — only wiring.
- The `FixProgressEvent` and `CheckEvent` types live in a new
  `agent_fox/fix/events.py` module to avoid circular imports between
  `fix/fix.py` and `ui/progress.py`.
- Session runner builders gain an `activity_callback` parameter but their
  return type (`FixSessionRunner`) is unchanged — the callback is captured
  in the closure.
