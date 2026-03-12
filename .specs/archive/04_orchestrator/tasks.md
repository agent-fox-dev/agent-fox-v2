# Implementation Plan: Orchestrator

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the orchestrator execution engine. Task groups build
incrementally: tests first, then graph sync and state (foundational), then
serial execution, then circuit breaker, then parallel execution. Each group
makes a subset of tests green.

## Test Commands

- Unit tests: `uv run pytest tests/unit/engine/ -q`
- Property tests: `uv run pytest tests/property/engine/ -q`
- All engine tests: `uv run pytest tests/unit/engine/ tests/property/engine/ -q`
- Linter: `uv run ruff check agent_fox/engine/`
- Type check: `uv run mypy agent_fox/engine/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory structure
    - Create `tests/unit/engine/__init__.py`
    - Create `tests/unit/engine/conftest.py` with shared fixtures:
      mock session runner factory, mock plan builder, tmp state path
    - Create `tests/property/engine/__init__.py`

  - [x] 1.2 Write graph sync tests
    - `tests/unit/engine/test_sync.py`: TS-04-2 (ready tasks), TS-04-6
      (cascade blocking linear), TS-04-7 (cascade blocking diamond),
      TS-04-E10 (stall detection)
    - _Test Spec: TS-04-2, TS-04-6, TS-04-7, TS-04-E10_

  - [x] 1.3 Write state persistence tests
    - `tests/unit/engine/test_state.py`: TS-04-8 (persist after session),
      TS-04-9 (resume from state), TS-04-E3 (corrupted state),
      TS-04-E4 (plan hash mismatch)
    - _Test Spec: TS-04-8, TS-04-9, TS-04-E3, TS-04-E4_

  - [x] 1.4 Write circuit breaker tests
    - `tests/unit/engine/test_circuit.py`: TS-04-10 (cost limit),
      TS-04-11 (session limit), TS-04-5 (zero retries),
      TS-04-E8 (circuit denies at cost limit),
      TS-04-E9 (circuit denies at session limit)
    - _Test Spec: TS-04-10, TS-04-11, TS-04-5, TS-04-E8, TS-04-E9_

  - [x] 1.5 Write serial runner tests
    - `tests/unit/engine/test_serial.py`: TS-04-16 (inter-session delay),
      TS-04-E7 (zero delay)
    - _Test Spec: TS-04-16, TS-04-E7_

  - [x] 1.6 Write parallel runner tests
    - `tests/unit/engine/test_parallel.py`: TS-04-12 (concurrent dispatch),
      TS-04-13 (respects dependencies), TS-04-14 (serialized state writes),
      TS-04-E5 (parallelism clamped), TS-04-E6 (fewer tasks than parallelism)
    - _Test Spec: TS-04-12, TS-04-13, TS-04-14, TS-04-E5, TS-04-E6_

  - [x] 1.7 Write orchestrator integration tests
    - `tests/unit/engine/test_orchestrator.py`: TS-04-1 (linear chain),
      TS-04-3 (retry with error), TS-04-4 (blocked after retries),
      TS-04-15 (graceful shutdown), TS-04-17 (stalled execution),
      TS-04-18 (resume with in-progress task),
      TS-04-E1 (missing plan), TS-04-E2 (empty plan)
    - _Test Spec: TS-04-1, TS-04-3, TS-04-4, TS-04-15, TS-04-17,
      TS-04-18, TS-04-E1, TS-04-E2_

  - [x] 1.8 Write property tests
    - `tests/property/engine/test_sync_props.py`: TS-04-P1 (cascade
      completeness), TS-04-P2 (ready task correctness)
    - `tests/property/engine/test_circuit_props.py`: TS-04-P3 (retry bound),
      TS-04-P4 (cost limit enforcement)
    - `tests/property/engine/test_state_props.py`: TS-04-P5 (save/load
      roundtrip)
    - _Test Spec: TS-04-P1, TS-04-P2, TS-04-P3, TS-04-P4, TS-04-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/engine/ tests/property/engine/`

- [x] 2. Implement graph sync and state persistence
  - [x] 2.1 Create engine package
    - `agent_fox/engine/__init__.py`

  - [x] 2.2 Implement graph sync
    - `agent_fox/engine/sync.py`: GraphSync class with ready_tasks(),
      mark_completed(), mark_failed(), mark_blocked() with BFS cascade,
      mark_in_progress(), is_stalled(), summary()
    - _Requirements: 04-REQ-1.1, 04-REQ-3.1, 04-REQ-3.2, 04-REQ-10.1,
      04-REQ-10.2_

  - [x] 2.3 Implement execution state data model
    - `agent_fox/engine/state.py`: RunStatus enum, SessionRecord dataclass,
      ExecutionState dataclass, JSON serialization/deserialization
    - _Requirements: 04-REQ-4.2_

  - [x] 2.4 Implement state manager
    - `agent_fox/engine/state.py`: StateManager class with load(), save(),
      record_session(), compute_plan_hash()
    - Handle corrupted state files (log warning, return None)
    - _Requirements: 04-REQ-4.1, 04-REQ-4.3_

  - [x] 2.V Verify task group 2
    - [x] Sync tests pass: `uv run pytest tests/unit/engine/test_sync.py -q`
    - [x] State tests pass: `uv run pytest tests/unit/engine/test_state.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/engine/test_sync_props.py tests/property/engine/test_state_props.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/`
    - [x] Requirements 04-REQ-3.*, 04-REQ-4.*, 04-REQ-10.* acceptance criteria met

- [x] 3. Implement serial execution and orchestrator core
  - [x] 3.1 Implement serial runner
    - `agent_fox/engine/serial.py`: SerialRunner class with execute()
      and delay() methods
    - Wire to SessionRunner protocol from spec 03 (or use a Protocol/ABC
      for now if spec 03 is not yet implemented)
    - _Requirements: 04-REQ-1.2, 04-REQ-9.1_

  - [x] 3.2 Implement orchestrator core loop
    - `agent_fox/engine/orchestrator.py`: Orchestrator class with run() method
    - Load plan, load/initialize state, plan hash verification
    - Main loop: pick ready tasks, dispatch via serial runner, update state,
      check for stall
    - Retry logic: on failure, re-queue with error context
    - Cascade blocking on retry exhaustion
    - Inter-session delay
    - _Requirements: 04-REQ-1.1, 04-REQ-1.2, 04-REQ-1.3, 04-REQ-1.4,
      04-REQ-2.1, 04-REQ-2.2, 04-REQ-2.3, 04-REQ-7.1, 04-REQ-7.2_

  - [x] 3.3 Implement SIGINT handler
    - Signal handler that sets `_interrupted` flag, saves state, prints
      resume instructions
    - Double-SIGINT exits immediately
    - _Requirements: 04-REQ-8.1, 04-REQ-8.3, 04-REQ-8.E1_

  - [x] 3.V Verify task group 3
    - [x] Serial tests pass: `uv run pytest tests/unit/engine/test_serial.py -q`
    - [x] Orchestrator tests pass: `uv run pytest tests/unit/engine/test_orchestrator.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/`
    - [x] Requirements 04-REQ-1.*, 04-REQ-2.*, 04-REQ-7.*, 04-REQ-8.*, 04-REQ-9.* met

- [x] 4. Implement parallel execution
  - [x] 4.1 Implement parallel runner
    - `agent_fox/engine/parallel.py`: ParallelRunner class with
      execute_batch(), cancel_all(), asyncio.Lock for state writes
    - Respect max_parallelism (capped at 8)
    - _Requirements: 04-REQ-6.1, 04-REQ-6.2, 04-REQ-6.3_

  - [x] 4.2 Wire parallel runner into orchestrator
    - Orchestrator selects serial or parallel runner based on config
    - Parallel mode: batch ready tasks up to parallelism, dispatch
      concurrently, update state via on_complete callback under lock
    - SIGINT in parallel mode: cancel all in-flight tasks
    - _Requirements: 04-REQ-6.1, 04-REQ-8.2_

  - [x] 4.3 Implement exactly-once guarantee for parallel mode
    - Ensure no task is dispatched twice even with concurrent completion
      callbacks re-evaluating ready tasks
    - Use the in_progress status as a dispatch lock
    - _Requirements: 04-REQ-7.1, 04-REQ-7.2_

  - [x] 4.V Verify task group 4
    - [x] Parallel tests pass: `uv run pytest tests/unit/engine/test_parallel.py -q`
    - [x] All orchestrator tests still pass: `uv run pytest tests/unit/engine/test_orchestrator.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/`
    - [x] Requirements 04-REQ-6.*, 04-REQ-7.* acceptance criteria met

- [x] 5. Implement circuit breaker and limits
  - [x] 5.1 Implement circuit breaker
    - `agent_fox/engine/circuit.py`: CircuitBreaker class with
      check_launch() and should_stop() methods
    - LaunchDecision dataclass
    - Cost ceiling check, session limit check, retry limit check
    - _Requirements: 04-REQ-5.1, 04-REQ-5.2, 04-REQ-5.3_

  - [x] 5.2 Wire circuit breaker into orchestrator
    - Call should_stop() before each dispatch cycle
    - Call check_launch() before each individual task dispatch
    - Set run_status to cost_limit or session_limit as appropriate
    - Allow in-flight sessions to complete when limit is reached
    - _Requirements: 04-REQ-5.1, 04-REQ-5.2, 04-REQ-5.3_

  - [x] 5.V Verify task group 5
    - [x] Circuit tests pass: `uv run pytest tests/unit/engine/test_circuit.py -q`
    - [x] All engine tests pass: `uv run pytest tests/unit/engine/ -q`
    - [x] Property tests pass: `uv run pytest tests/property/engine/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/`
    - [x] Type check passes: `uv run mypy agent_fox/engine/`
    - [x] Requirements 04-REQ-5.* acceptance criteria met

- [x] 6. Checkpoint -- Orchestrator Complete
  - Ensure all tests pass: `uv run pytest tests/unit/engine/ tests/property/engine/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/engine/ tests/unit/engine/ tests/property/engine/`
  - Ensure type check clean: `uv run mypy agent_fox/engine/`
  - Verify serial execution end-to-end with mock session runner
  - Verify parallel execution end-to-end with mock session runner
  - Verify resume from interrupted state with mock session runner

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 04-REQ-1.1 | TS-04-1, TS-04-2 | 3.2 | tests/unit/engine/test_orchestrator.py, test_sync.py |
| 04-REQ-1.2 | TS-04-1 | 3.1, 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-1.3 | TS-04-1 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-1.4 | TS-04-17 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-1.E1 | TS-04-E1 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-1.E2 | TS-04-E2 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-2.1 | TS-04-3, TS-04-4 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-2.2 | TS-04-3 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-2.3 | TS-04-4 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-2.E1 | TS-04-5 | 3.2 | tests/unit/engine/test_circuit.py |
| 04-REQ-3.1 | TS-04-6 | 2.2 | tests/unit/engine/test_sync.py |
| 04-REQ-3.2 | TS-04-6 | 2.2 | tests/unit/engine/test_sync.py |
| 04-REQ-3.E1 | TS-04-7 | 2.2 | tests/unit/engine/test_sync.py |
| 04-REQ-4.1 | TS-04-8 | 2.4 | tests/unit/engine/test_state.py |
| 04-REQ-4.2 | TS-04-8 | 2.3, 2.4 | tests/unit/engine/test_state.py |
| 04-REQ-4.3 | TS-04-9 | 2.4 | tests/unit/engine/test_state.py |
| 04-REQ-4.E1 | TS-04-E4 | 2.4 | tests/unit/engine/test_state.py |
| 04-REQ-4.E2 | TS-04-E3 | 2.4 | tests/unit/engine/test_state.py |
| 04-REQ-5.1 | TS-04-10, TS-04-E8 | 5.1, 5.2 | tests/unit/engine/test_circuit.py, test_orchestrator.py |
| 04-REQ-5.2 | TS-04-10 | 5.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-5.3 | TS-04-11, TS-04-E9 | 5.1, 5.2 | tests/unit/engine/test_circuit.py, test_orchestrator.py |
| 04-REQ-5.E1 | TS-04-10 | 5.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-6.1 | TS-04-12, TS-04-13 | 4.1, 4.2 | tests/unit/engine/test_parallel.py |
| 04-REQ-6.2 | TS-04-E5 | 4.1 | tests/unit/engine/test_parallel.py |
| 04-REQ-6.3 | TS-04-14 | 4.1 | tests/unit/engine/test_parallel.py |
| 04-REQ-6.E1 | TS-04-E6 | 4.1 | tests/unit/engine/test_parallel.py |
| 04-REQ-7.1 | TS-04-1, TS-04-9 | 3.2, 4.3 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-7.2 | TS-04-9 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-7.E1 | TS-04-18 | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-8.1 | TS-04-15 | 3.3 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-8.2 | TS-04-15 | 4.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-8.3 | TS-04-15 | 3.3 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-8.E1 | (manual) | 3.3 | manual verification |
| 04-REQ-9.1 | TS-04-16 | 3.1 | tests/unit/engine/test_serial.py |
| 04-REQ-9.2 | (implicit) | 3.2 | tests/unit/engine/test_orchestrator.py |
| 04-REQ-9.E1 | TS-04-E7 | 3.1 | tests/unit/engine/test_serial.py |
| 04-REQ-10.1 | TS-04-2 | 2.2 | tests/unit/engine/test_sync.py |
| 04-REQ-10.2 | TS-04-6 | 2.2 | tests/unit/engine/test_sync.py |
| 04-REQ-10.E1 | TS-04-17, TS-04-E10 | 2.2, 3.2 | tests/unit/engine/test_sync.py, test_orchestrator.py |
| Property 1 | TS-04-P5 | 2.4 | tests/property/engine/test_state_props.py |
| Property 2 | TS-04-P1 | 2.2 | tests/property/engine/test_sync_props.py |
| Property 3 | TS-04-P4 | 5.1 | tests/property/engine/test_circuit_props.py |
| Property 4 | TS-04-1, TS-04-9 | 3.2, 4.3 | tests/unit/engine/test_orchestrator.py |
| Property 5 | TS-04-P2 | 2.2 | tests/property/engine/test_sync_props.py |
| Property 6 | TS-04-P3 | 5.1 | tests/property/engine/test_circuit_props.py |
| Property 7 | TS-04-14 | 4.1 | tests/unit/engine/test_parallel.py |

## Notes

- All tests mock `SessionRunner`. The orchestrator never makes LLM calls, so
  tests need only verify scheduling, state management, and error handling.
- Use `asyncio` test fixtures (`pytest-asyncio`) for async tests.
- For parallel execution tests, use `asyncio.Event` and controlled delays
  to simulate concurrent session completion.
- For SIGINT tests, mock `signal.signal` or use `os.kill(os.getpid(), SIGINT)`
  from a scheduled callback.
- The orchestrator depends on spec 02's `TaskGraph` for plan loading. If spec 02
  is not yet implemented, use a minimal plan dict structure that matches the
  expected `plan.json` schema.
- The orchestrator depends on spec 03's `SessionRunner` for session dispatch.
  Use a Protocol or ABC to define the interface, enabling mock implementations
  in tests.
