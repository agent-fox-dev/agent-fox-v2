# Test Specification: End-of-Run Spec Discovery

## Overview

Test contracts for end-of-run discovery (spec 60). All tests target the
orchestrator main loop and the new `_try_end_of_run_discovery()` method in
`engine/engine.py`.

## Test Environment

- **Framework:** pytest with pytest-asyncio
- **Mocking:** unittest.mock (AsyncMock for async callables)
- **Test location:** `tests/unit/engine/test_end_of_run_discovery.py`

## Fixtures

### `mock_barrier`

A fixture that provides an `AsyncMock` for `run_sync_barrier_sequence`. By
default it succeeds (returns `None`). Tests configure it to inject new specs
or raise exceptions via side effects.

### `mock_graph_sync`

A fixture that provides a mock `_graph_sync` object with configurable
`ready_tasks()` and `is_stalled()` return values.

### `orchestrator_with_mocks`

A fixture that creates an `Orchestrator` instance with mocked dependencies,
configurable `hot_load` flag, and patched barrier function.

---

## Test Cases

### TC-60-01: End-of-run discovery triggers on COMPLETED state

**Requirement:** 60-REQ-1.1

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]` (no ready tasks)
- `is_stalled()` returns `False`
- Barrier mock succeeds, does not add new specs
- After barrier, `ready_tasks()` still returns `[]`

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- `run_sync_barrier_sequence` was called exactly once.
- Method returns `False` (no new work found).
- Run terminates with `RunStatus.COMPLETED`.

---

### TC-60-02: New specs discovered — execution continues

**Requirement:** 60-REQ-1.2

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]` initially
- `is_stalled()` returns `False`
- Barrier mock succeeds and adds new specs (side effect: next
  `ready_tasks()` call returns `[task_a, task_b]`)

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- `run_sync_barrier_sequence` was called exactly once.
- Method returns `True` (new work found).
- The main loop continues (does not set `RunStatus.COMPLETED`).

---

### TC-60-03: No new specs — terminates with COMPLETED

**Requirement:** 60-REQ-1.3

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]` before and after barrier
- `is_stalled()` returns `False`
- Barrier mock succeeds, discovers no new specs

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `run_sync_barrier_sequence` was called (end-of-run discovery attempted).
- Final `state.run_status == RunStatus.COMPLETED`.

---

### TC-60-04: Repeated end-of-run discovery cycles

**Requirement:** 60-REQ-1.4

**Setup:**
- `hot_load_enabled = True`
- Barrier mock configured with a side-effect sequence:
  1. First call: adds specs, `ready_tasks()` returns tasks
  2. Tasks complete, `ready_tasks()` returns `[]` again
  3. Second call: adds more specs, `ready_tasks()` returns tasks
  4. Tasks complete, `ready_tasks()` returns `[]` again
  5. Third call: no new specs, `ready_tasks()` returns `[]`

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `run_sync_barrier_sequence` was called at least 3 times for end-of-run
  discovery (plus any mid-run barriers).
- Final `state.run_status == RunStatus.COMPLETED`.

---

### TC-60-12: Full barrier sequence is executed

**Requirement:** 60-REQ-3.1

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]`
- `is_stalled()` returns `False`

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- `run_sync_barrier_sequence` was called with ALL keyword arguments:
  `state`, `sync_interval`, `repo_root`, `emit_audit`, `hook_config`,
  `no_hooks`, `specs_dir`, `hot_load_enabled`, `hot_load_fn`,
  `sync_plan_fn`, `barrier_callback`, `knowledge_db_conn`.
- The arguments match those used by `_run_sync_barrier_if_needed()`.

---

### TC-60-13: Same three-gate pipeline applied

**Requirement:** 60-REQ-3.2

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]`
- `is_stalled()` returns `False`

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- The `hot_load_fn` passed to `run_sync_barrier_sequence` is
  `self._hot_load_new_specs` (the same function used by mid-run barriers).
- The `hot_load_enabled` parameter is `True`.

---

### TC-60-14: SYNC_BARRIER audit event emitted

**Requirement:** 60-REQ-3.3

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]`
- `is_stalled()` returns `False`

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- The `emit_audit` callable passed to `run_sync_barrier_sequence` is
  `self._emit_audit` (the same audit emitter used by mid-run barriers).

---

## Edge Case Tests

### TC-60-05: Hot-load disabled — skips discovery

**Requirement:** 60-REQ-1.E1

**Setup:**
- `hot_load_enabled = False`
- `ready_tasks()` returns `[]`
- `is_stalled()` returns `False`

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- `run_sync_barrier_sequence` was NOT called.
- Method returns `False`.
- Run terminates with `RunStatus.COMPLETED`.

---

### TC-60-06: Barrier failure — logs error and terminates

**Requirement:** 60-REQ-1.E2

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]`
- `is_stalled()` returns `False`
- Barrier mock raises `RuntimeError("git sync failed")`

**Action:** Call `_try_end_of_run_discovery(state)`.

**Assertions:**
- `run_sync_barrier_sequence` was called exactly once.
- Method returns `False`.
- The error is logged at `error` level.
- Run terminates with `RunStatus.COMPLETED` (not a crash).

---

### TC-60-07: STALLED status — no end-of-run discovery

**Requirement:** 60-REQ-2.1

**Setup:**
- `hot_load_enabled = True`
- `ready_tasks()` returns `[]`
- `is_stalled()` returns `True`

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `_try_end_of_run_discovery` was NOT called.
- Final `state.run_status == RunStatus.STALLED`.

---

### TC-60-08: COST_LIMIT status — no end-of-run discovery

**Requirement:** 60-REQ-2.2

**Setup:**
- `hot_load_enabled = True`
- Circuit breaker triggers `RunStatus.COST_LIMIT` before tasks complete

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `_try_end_of_run_discovery` was NOT called.
- Final `state.run_status == RunStatus.COST_LIMIT`.

---

### TC-60-09: SESSION_LIMIT status — no end-of-run discovery

**Requirement:** 60-REQ-2.2

**Setup:**
- `hot_load_enabled = True`
- Circuit breaker triggers `RunStatus.SESSION_LIMIT` before tasks complete

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `_try_end_of_run_discovery` was NOT called.
- Final `state.run_status == RunStatus.SESSION_LIMIT`.

---

### TC-60-10: BLOCK_LIMIT status — no end-of-run discovery

**Requirement:** 60-REQ-2.3

**Setup:**
- `hot_load_enabled = True`
- Block budget exceeded, triggering `RunStatus.BLOCK_LIMIT`

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `_try_end_of_run_discovery` was NOT called.
- Final `state.run_status == RunStatus.BLOCK_LIMIT`.

---

### TC-60-11: INTERRUPTED status — no end-of-run discovery

**Requirement:** 60-REQ-2.4

**Setup:**
- `hot_load_enabled = True`
- SIGINT received during execution

**Action:** Run the orchestrator main loop to completion.

**Assertions:**
- `_try_end_of_run_discovery` was NOT called.
- Final `state.run_status == RunStatus.INTERRUPTED`.

---

## Property Test Cases

### TS-60-P1: Discovery Only on COMPLETED

**Property:** 1 (Discovery Only on COMPLETED)

*For any* terminal state other than COMPLETED, end-of-run discovery SHALL NOT
be attempted.

**Strategy:** Generate random sequences of terminal states from the set
{STALLED, COST_LIMIT, SESSION_LIMIT, BLOCK_LIMIT, INTERRUPTED}. For each,
verify that `_try_end_of_run_discovery` is never called.

---

### TS-60-P2: Hot-Load Gate Respected

**Property:** 2 (Hot-Load Gate Respected)

*For any* call to `_try_end_of_run_discovery` with `hot_load_enabled=False`,
the barrier function SHALL NOT be invoked.

**Strategy:** Generate random `ExecutionState` values and call
`_try_end_of_run_discovery` with `hot_load=False`. Assert that
`run_sync_barrier_sequence` is never called and return value is always `False`.

---

### TS-60-P3: Full Barrier Equivalence

**Property:** 3 (Full Barrier Equivalence)

*For any* call to `_try_end_of_run_discovery`, the keyword arguments passed to
`run_sync_barrier_sequence` SHALL match those used by
`_run_sync_barrier_if_needed()`.

**Strategy:** Capture barrier call kwargs from both `_run_sync_barrier_if_needed`
and `_try_end_of_run_discovery` invocations. Assert the keyword argument names
and bound values are identical (excluding `sync_interval` trigger logic).

---

### TS-60-P4: Graceful Failure

**Property:** 4 (Graceful Failure)

*For any* exception type raised during the barrier sequence, the method SHALL
return `False` and not propagate the exception.

**Strategy:** Generate random exception types (RuntimeError, OSError, IOError,
ValueError). For each, configure the barrier mock to raise it. Assert return
value is `False` and no exception propagates.

---

### TS-60-P5: Loop Continuation

**Property:** 5 (Loop Continuation)

*For any* end-of-run discovery that produces ready tasks, the main loop SHALL
continue execution rather than terminating.

**Strategy:** Generate random counts of new tasks (1-10). After barrier, mock
`ready_tasks()` to return that many tasks. Assert
`_try_end_of_run_discovery` returns `True`.

---

## Coverage Matrix

| Requirement | Test Cases | Property Tests |
|-------------|-----------|----------------|
| 60-REQ-1.1 | TC-60-01 | TS-60-P1 |
| 60-REQ-1.2 | TC-60-02 | TS-60-P5 |
| 60-REQ-1.3 | TC-60-03 | — |
| 60-REQ-1.4 | TC-60-04 | TS-60-P5 |
| 60-REQ-1.E1 | TC-60-05 | TS-60-P2 |
| 60-REQ-1.E2 | TC-60-06 | TS-60-P4 |
| 60-REQ-2.1 | TC-60-07 | TS-60-P1 |
| 60-REQ-2.2 | TC-60-08, TC-60-09 | TS-60-P1 |
| 60-REQ-2.3 | TC-60-10 | TS-60-P1 |
| 60-REQ-2.4 | TC-60-11 | TS-60-P1 |
| 60-REQ-3.1 | TC-60-12 | TS-60-P3 |
| 60-REQ-3.2 | TC-60-13 | TS-60-P3 |
| 60-REQ-3.3 | TC-60-14 | TS-60-P3 |

## Notes

- TC-60-04 (repeated cycles) is the most complex test and may require
  careful orchestration of mock side effects to simulate multiple rounds
  of discovery.
- Property tests TS-60-P1 through TS-60-P5 map directly to the five
  correctness properties in `design.md`.
