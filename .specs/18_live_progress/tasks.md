# Implementation Plan: Live Progress Line

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds test-first: write failing tests, then build the event
types + abbreviation, then the progress display, then wire into the session
runner, then wire into the orchestrator, and finally integrate into `code_cmd`.

## Test Commands

- Spec tests: `uv run pytest tests/unit/ui/test_progress.py tests/unit/ui/test_events.py tests/unit/session/test_runner.py -q`
- Property tests: `uv run pytest tests/property/ui/test_progress_props.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file `tests/unit/ui/test_events.py`
    - Tests for `abbreviate_arg()`: basename extraction, truncation with ellipsis, idempotence
    - Tests for `ActivityEvent` and `TaskEvent` construction
    - _Test Spec: TS-18-6, TS-18-7_

  - [ ] 1.2 Create test file `tests/unit/ui/test_progress.py`
    - Tests for `ProgressDisplay` lifecycle (start/stop)
    - Tests for `on_activity()` updating display text
    - Tests for `on_task_event()` printing permanent lines (completed, failed, blocked)
    - Tests for quiet mode suppression
    - Tests for non-TTY behavior
    - _Test Spec: TS-18-1, TS-18-2, TS-18-3, TS-18-4, TS-18-5, TS-18-E1, TS-18-E2, TS-18-E4_

  - [ ] 1.3 Create test file `tests/property/ui/test_progress_props.py`
    - Property: spinner line never exceeds terminal width
    - Property: abbreviation idempotence
    - Property: quiet mode produces no output
    - Property: permanent lines contain node ID
    - _Test Spec: TS-18-P1, TS-18-P2, TS-18-P3, TS-18-P4_

  - [ ] 1.4 Add activity callback tests to `tests/unit/session/test_runner.py`
    - Test: callback invoked for tool-use messages
    - Test: session works without callback
    - Test: callback exception does not crash session
    - _Test Spec: TS-18-8, TS-18-9, TS-18-E3_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Implement event types and abbreviation
  - [ ] 2.1 Create `agent_fox/ui/events.py`
    - Define `ActivityEvent` frozen dataclass (node_id, tool_name, argument)
    - Define `TaskEvent` frozen dataclass (node_id, status, duration_s, error_message)
    - Define `ActivityCallback` and `TaskCallback` type aliases
    - _Requirements: 18-REQ-2.1, 18-REQ-4.1_

  - [ ] 2.2 Implement `abbreviate_arg()` in `agent_fox/ui/events.py`
    - Detect file paths (contains `/` or `\`), return `os.path.basename()`
    - Truncate remaining strings to `max_len` with `...` suffix
    - Handle empty strings
    - _Requirements: 18-REQ-2.E2, 18-REQ-2.E3_

  - [ ] 2.3 Implement `format_duration()` in `agent_fox/ui/events.py`
    - `< 60s` -> `"Xs"`, `>= 60s` -> `"Xm Ys"`
    - _Requirements: 18-REQ-4.1_

  - [ ] 2.V Verify task group 2
    - [ ] Event and abbreviation tests pass: `uv run pytest tests/unit/ui/test_events.py -q`
    - [ ] Property tests for abbreviation pass: `uv run pytest tests/property/ui/test_progress_props.py::TestAbbreviationIdempotence -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ui/events.py`

- [ ] 3. Implement ProgressDisplay
  - [ ] 3.1 Create `agent_fox/ui/progress.py`
    - `ProgressDisplay.__init__(theme, quiet)`: store theme, quiet flag, create asyncio.Lock
    - Detect TTY via `theme.console.is_terminal`
    - _Requirements: 18-REQ-1.E1, 18-REQ-1.E2_

  - [ ] 3.2 Implement `start()` and `stop()`
    - TTY mode: create and start `rich.live.Live` with a `Spinner("dots")`
    - Non-TTY/quiet: no-op
    - `stop()`: stop Live, clear line
    - _Requirements: 18-REQ-1.1, 18-REQ-1.3_

  - [ ] 3.3 Implement `on_activity(event)`
    - Acquire lock, update stored activity text
    - Format: `[{node_id}] {tool_name} {argument}`
    - Truncate to terminal width (default 80 if unknown)
    - Refresh the Live renderable
    - _Requirements: 18-REQ-3.1, 18-REQ-3.2, 18-REQ-3.3, 18-REQ-3.4, 18-REQ-3.E1, 18-REQ-6.1, 18-REQ-6.2_

  - [ ] 3.4 Implement `on_task_event(event)`
    - Acquire lock, format permanent line with icon + node_id + status + duration
    - TTY: print above Live area via `live.console.print()`
    - Non-TTY: plain `console.print()` without ANSI
    - _Requirements: 18-REQ-4.1, 18-REQ-4.2, 18-REQ-4.3, 18-REQ-4.4, 18-REQ-4.E1, 18-REQ-6.E1_

  - [ ] 3.V Verify task group 3
    - [ ] Progress display tests pass: `uv run pytest tests/unit/ui/test_progress.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/ui/test_progress_props.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ui/progress.py`

- [ ] 4. Wire activity callback into session runner
  - [ ] 4.1 Add `activity_callback` parameter to `run_session()` and `_execute_query()`
    - Optional `ActivityCallback | None = None`, default None
    - Thread through to the SDK message loop
    - _Requirements: 18-REQ-2.3_

  - [ ] 4.2 Implement `_extract_activity()` in `agent_fox/session/runner.py`
    - Inspect SDK message: if tool-use, extract tool name + first arg
    - Call `abbreviate_arg()` on the argument
    - If unknown message type, return thinking event
    - _Requirements: 18-REQ-2.1, 18-REQ-2.2_

  - [ ] 4.3 Call activity callback in the message loop
    - For non-result messages, call `_extract_activity()` and invoke callback
    - Wrap callback invocation in try/except to prevent session disruption
    - _Requirements: 18-REQ-2.1, 18-REQ-2.E1_

  - [ ] 4.4 Thread callback through `NodeSessionRunner`
    - Add `activity_callback` parameter to `NodeSessionRunner.__init__()`
    - Pass to `run_session()` in `_run_and_harvest()`
    - _Requirements: 18-REQ-5.3_

  - [ ] 4.V Verify task group 4
    - [ ] Runner callback tests pass: `uv run pytest tests/unit/session/test_runner.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/session/runner.py agent_fox/engine/session_lifecycle.py`

- [ ] 5. Wire task callback into orchestrator and code command
  - [ ] 5.1 Add `task_callback` parameter to `Orchestrator.__init__()`
    - Optional `TaskCallback | None = None`
    - _Requirements: 18-REQ-5.4_

  - [ ] 5.2 Emit `TaskEvent` from `_process_session_result()` and `_block_task()`
    - On completion: emit `TaskEvent(node_id, "completed", duration_s)`
    - On final failure: emit `TaskEvent(node_id, "failed", duration_s, error_message)`
    - On cascade block: emit `TaskEvent(node_id, "blocked", 0, reason)`
    - _Requirements: 18-REQ-5.4_

  - [ ] 5.3 Integrate `ProgressDisplay` into `code_cmd`
    - Create `ProgressDisplay(theme, quiet=quiet)`
    - Pass `progress.activity_callback` through `session_runner_factory`
    - Pass `progress.task_callback` to `Orchestrator`
    - Wrap `asyncio.run(orchestrator.run())` with `progress.start()` / `progress.stop()` in `try/finally`
    - _Requirements: 18-REQ-5.1, 18-REQ-5.2, 18-REQ-5.3, 18-REQ-5.E1_

  - [ ] 5.V Verify task group 5
    - [ ] All spec tests pass: `uv run pytest tests/unit/ui/ tests/unit/session/test_runner.py tests/property/ui/ -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/`

- [ ] 6. Checkpoint -- Live Progress Complete
  - Ensure all 977+ existing tests still pass plus all new tests
  - Run full linter check
  - Manual smoke test: `agent-fox code --quiet` (no spinner), regular run (spinner visible)

- [ ] 7. Write failing tests for path truncation update
  - [ ] 7.1 Add unit tests for trailing path component abbreviation
    - Test: long absolute path abbreviated to trailing components with `…/` prefix
    - Test: path where only basename fits falls back to basename
    - Test: path that already fits within max_len returned as-is
    - Test: path with many components keeps maximum context
    - _Test Spec: TS-18-6, TS-18-11, TS-18-12, TS-18-13_

  - [ ] 7.2 Add property test for path abbreviation length invariant
    - For any path containing `/` and any `max_len >= 4`, result length <= max_len
    - _Test Spec: TS-18-P6_

  - [ ] 7.V Verify task group 7
    - [ ] New tests exist and are syntactically valid
    - [ ] New tests FAIL against current basename-only implementation
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 8. Implement trailing path component abbreviation
  - [ ] 8.1 Rewrite `abbreviate_arg()` path handling in `agent_fox/ui/events.py`
    - Split path on separator, collect components from the right
    - Build candidate with `…/` prefix, dropping leftmost components until it fits
    - If path already fits within max_len, return it as-is
    - Fall back to basename only when even `…/parent/basename` exceeds max_len
    - _Requirements: 18-REQ-2.E2_

  - [ ] 8.2 Verify idempotence still holds with new algorithm
    - Abbreviated path containing `…/` must remain stable when re-abbreviated
    - _Property 2: Abbreviation Idempotence_

  - [ ] 8.V Verify task group 8
    - [ ] New path truncation tests pass: `uv run pytest tests/unit/ui/test_events.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/ui/test_progress_props.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ui/events.py`
    - [ ] Requirements 18-REQ-2.E2 acceptance criteria met

- [ ] 9. Checkpoint -- Path Truncation Update Complete
  - Ensure all tests pass (existing + new)
  - Run full linter check
  - Verify abbreviation idempotence property still holds

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 18-REQ-1.1 | TS-18-1 | 3.2 | tests/unit/ui/test_progress.py |
| 18-REQ-1.2 | TS-18-1 | 3.2 | tests/unit/ui/test_progress.py |
| 18-REQ-1.3 | TS-18-1 | 3.2 | tests/unit/ui/test_progress.py |
| 18-REQ-1.E1 | TS-18-E1 | 3.1 | tests/unit/ui/test_progress.py |
| 18-REQ-1.E2 | TS-18-E2 | 3.1 | tests/unit/ui/test_progress.py |
| 18-REQ-2.1 | TS-18-2, TS-18-8 | 4.2, 4.3 | tests/unit/session/test_runner.py |
| 18-REQ-2.2 | TS-18-3 | 4.2 | tests/unit/ui/test_progress.py |
| 18-REQ-2.3 | TS-18-9 | 4.1 | tests/unit/session/test_runner.py |
| 18-REQ-2.E1 | TS-18-E3 | 4.3 | tests/unit/session/test_runner.py |
| 18-REQ-2.E2 | TS-18-6, TS-18-11, TS-18-12, TS-18-13, TS-18-P6 | 8.1 | tests/unit/ui/test_events.py, tests/property/ui/test_progress_props.py |
| 18-REQ-2.E3 | TS-18-7 | 2.2 | tests/unit/ui/test_events.py |
| 18-REQ-3.1 | TS-18-2 | 3.3 | tests/unit/ui/test_progress.py |
| 18-REQ-3.2 | TS-18-2 | 3.3 | tests/unit/ui/test_progress.py |
| 18-REQ-3.3 | TS-18-P1 | 3.3 | tests/property/ui/test_progress_props.py |
| 18-REQ-3.4 | TS-18-2 | 3.3 | tests/unit/ui/test_progress.py |
| 18-REQ-3.E1 | TS-18-E4 | 3.3 | tests/unit/ui/test_progress.py |
| 18-REQ-4.1 | TS-18-4 | 3.4 | tests/unit/ui/test_progress.py |
| 18-REQ-4.2 | TS-18-5 | 3.4 | tests/unit/ui/test_progress.py |
| 18-REQ-4.3 | TS-18-4 | 3.4 | tests/unit/ui/test_progress.py |
| 18-REQ-4.4 | TS-18-4 | 3.4 | tests/unit/ui/test_progress.py |
| 18-REQ-4.E1 | TS-18-E2 | 3.4 | tests/unit/ui/test_progress.py |
| 18-REQ-5.1 | TS-18-10 | 5.3 | tests/unit/cli/test_code.py |
| 18-REQ-5.2 | TS-18-10 | 5.3 | tests/unit/cli/test_code.py |
| 18-REQ-5.3 | TS-18-8 | 5.3 | tests/unit/session/test_runner.py |
| 18-REQ-5.4 | TS-18-10 | 5.1, 5.2 | tests/unit/cli/test_code.py |
| 18-REQ-5.E1 | TS-18-E5 | 5.3 | tests/unit/cli/test_code.py |
| 18-REQ-6.1 | TS-18-2 | 3.3 | tests/unit/ui/test_progress.py |
| 18-REQ-6.2 | TS-18-2 | 3.3 | tests/unit/ui/test_progress.py |
| 18-REQ-6.E1 | TS-18-4 | 3.4 | tests/unit/ui/test_progress.py |
| Property 1 | TS-18-P1 | 3.3 | tests/property/ui/test_progress_props.py |
| Property 2 | TS-18-P2 | 2.2 | tests/property/ui/test_progress_props.py |
| Property 3 | TS-18-P3 | 3.1 | tests/property/ui/test_progress_props.py |
| Property 4 | TS-18-P4 | 3.4 | tests/property/ui/test_progress_props.py |
| Property 5 | TS-18-P5 | 4.1 | tests/unit/session/test_runner.py |
| Property 6 | TS-18-P6 | 8.1 | tests/property/ui/test_progress_props.py |
