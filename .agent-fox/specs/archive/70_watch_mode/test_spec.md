# Test Specification: Watch Mode

## Overview

Tests are organized into three categories: acceptance criterion tests
(TS-70-N), property tests (TS-70-PN), and edge case tests (TS-70-EN). All
tests validate behavior against the requirements and correctness properties
defined in the spec. The watch loop is tested with mocked barriers, signals,
and circuit breakers to avoid real sleeps or I/O.

### Critical: Main Loop Discovery Offset

All tests that mock `_try_end_of_run_discovery` via `patch.object` must
account for the main dispatch loop calling this method **once** before the
watch gate is reached. The mock's call counter will be at 1 by the time
`_watch_loop` starts. See `design.md § Watch Loop Implementation Detail`
for the full offset table.

**Key rule for mock design:** If you want the watch loop's Nth poll to
trigger a specific behavior, set the mock to trigger on call `N + 1`
(not call `N`).

Failure to account for this offset is the primary reason previous
implementation attempts failed — mocks fired one call too early, causing
wrong behavior and infinite loops.

## Test Cases

### TS-70-1: Watch flag activates watch loop

**Requirement:** 70-REQ-1.1
**Type:** unit
**Description:** Verify that when watch mode is enabled, the orchestrator
enters the watch loop instead of returning COMPLETED.

**Preconditions:**
- Orchestrator with `watch=True`, `hot_load=True`
- Empty task graph (no tasks to dispatch)
- Barrier returns no new tasks on first poll, then new tasks on second poll

**Input:**
- Call `orchestrator.run()`

**Expected:**
- The watch loop is entered (WATCH_POLL audit event emitted)
- Execution resumes when the barrier finds new tasks

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, hot_load=True)
mock_barrier to return no_tasks then new_tasks
state = orchestrator.run()
ASSERT WATCH_POLL audit event was emitted
ASSERT state.run_status == "completed" or tasks were dispatched
```

### TS-70-2: Watch disabled with hot_load=False

**Requirement:** 70-REQ-1.2
**Type:** unit
**Description:** Verify that watch mode is skipped when hot_load is disabled.

**Preconditions:**
- Orchestrator with `watch=True`, `hot_load=False`
- All tasks complete

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Warning logged about hot_load being disabled
- Run terminates with COMPLETED status
- No WATCH_POLL events emitted

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, hot_load=False)
state = orchestrator.run()
ASSERT state.run_status == "completed"
ASSERT no WATCH_POLL events emitted
ASSERT warning logged containing "hot_load"
```

### TS-70-3: Watch flag is boolean CLI option

**Requirement:** 70-REQ-1.3
**Type:** integration
**Description:** Verify `--watch` is accepted by the CLI and defaults to
false.

**Preconditions:**
- CLI runner available

**Input:**
- Invoke `code` command with `--watch` flag
- Invoke `code` command without `--watch` flag

**Expected:**
- `--watch` is accepted without error
- Without `--watch`, watch mode is not activated

**Assertion pseudocode:**
```
result = cli_runner.invoke(code_cmd, ["--watch", ...])
ASSERT result.exit_code != 2  # not a usage error
result = cli_runner.invoke(code_cmd, [...])  # no --watch
ASSERT watch mode is not activated
```

### TS-70-4: Watch loop sleeps for watch_interval

**Requirement:** 70-REQ-2.1
**Type:** unit
**Description:** Verify the watch loop sleeps for the configured interval.

**Preconditions:**
- Orchestrator with `watch=True`, `watch_interval=30`
- Barrier always returns no new tasks
- SIGINT after first poll to terminate

**Input:**
- Call `orchestrator.run()`

**Expected:**
- `asyncio.sleep` called with 30

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, watch_interval=30)
mock asyncio.sleep
trigger SIGINT after first poll
state = orchestrator.run()
ASSERT asyncio.sleep was called with 30
```

### TS-70-5: Watch poll runs full barrier sequence

**Requirement:** 70-REQ-2.2
**Type:** unit
**Description:** Verify each watch poll executes the full sync barrier.

**Preconditions:**
- Orchestrator with `watch=True`
- Mock `_try_end_of_run_discovery` to track calls

**Input:**
- Run two poll cycles, then SIGINT

**Expected:**
- `_try_end_of_run_discovery` called on each poll cycle

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True)
mock _try_end_of_run_discovery to return False twice
trigger SIGINT after second poll
state = orchestrator.run()
ASSERT _try_end_of_run_discovery.call_count >= 2
```

### TS-70-6: Watch loop resumes dispatch on new tasks

**Requirement:** 70-REQ-2.3
**Type:** unit
**Description:** Verify the watch loop exits and dispatch resumes when new
tasks are found. After re-entry, the main loop calls discovery again; the
test terminates via interrupt.

**Preconditions:**
- Orchestrator with `watch=True`
- Mock discovery accounting for main loop offset:
  - Call 1 (main loop): returns False (enters watch gate)
  - Call 2 (watch poll 1): returns True (new tasks found → watch loop
    returns None → main loop re-enters dispatch)
  - Call 3+ (main loop re-entry): set interrupted, return False

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Watch loop returned None (verified by main loop re-entry: poll_count >= 3)
- At least 1 WATCH_POLL event emitted with `new_tasks_found=True`
- Run terminates with INTERRUPTED (via signal set on re-entry)

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True)
poll_count = 0
mock _try_end_of_run_discovery:
    poll_count += 1
    IF poll_count == 2: RETURN True   # watch poll finds tasks
    IF poll_count >= 3: set interrupted  # terminate after re-entry
    RETURN False
state = orchestrator.run()
ASSERT poll_count >= 3  # main loop re-entered after watch exit
ASSERT state.run_status == "interrupted"
```

### TS-70-7: Watch loop re-enters on no tasks

**Requirement:** 70-REQ-2.4
**Type:** unit
**Description:** Verify the watch loop continues polling when no tasks found.

**Preconditions:**
- Orchestrator with `watch=True`
- Barrier returns no tasks for 3 consecutive polls
- SIGINT after third poll

**Input:**
- Call `orchestrator.run()`

**Expected:**
- 3 WATCH_POLL audit events emitted
- Run terminates with INTERRUPTED

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True)
mock barrier to return no tasks 3 times
trigger SIGINT after 3rd poll
state = orchestrator.run()
ASSERT count(WATCH_POLL events) == 3
ASSERT state.run_status == "interrupted"
```

### TS-70-8: Watch loop checks interruption before sleep

**Requirement:** 70-REQ-2.5
**Type:** unit
**Description:** Verify SIGINT is checked before each sleep in the watch
loop. The interrupt must be set via the discovery mock (not directly before
`run()`) so the main loop's interrupt check at the top of the while loop
does not catch it first.

**Preconditions:**
- Orchestrator with `watch=True`
- Mock discovery sets `interrupted=True` on call 1 (main loop), returns False
- This causes the watch loop to see `interrupted=True` on entry

**Input:**
- Call `orchestrator.run()`

**Expected:**
- No sleep occurs in the watch loop
- Run terminates with INTERRUPTED

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True)
mock _try_end_of_run_discovery:
    set interrupted = True
    RETURN False
state = orchestrator.run()
ASSERT asyncio.sleep was NOT called in watch loop
ASSERT state.run_status == "interrupted"
```

### TS-70-9: Watch interval default is 60

**Requirement:** 70-REQ-3.1
**Type:** unit
**Description:** Verify the default watch_interval is 60.

**Preconditions:**
- Default OrchestratorConfig

**Input:**
- Create `OrchestratorConfig()`

**Expected:**
- `watch_interval == 60`

**Assertion pseudocode:**
```
config = OrchestratorConfig()
ASSERT config.watch_interval == 60
```

### TS-70-10: Watch interval clamped below 10

**Requirement:** 70-REQ-3.2
**Type:** unit
**Description:** Verify values below 10 are clamped.

**Preconditions:**
- None

**Input:**
- Create `OrchestratorConfig(watch_interval=5)`
- Create `OrchestratorConfig(watch_interval=1)`

**Expected:**
- Both result in `watch_interval == 10`

**Assertion pseudocode:**
```
config = OrchestratorConfig(watch_interval=5)
ASSERT config.watch_interval == 10
config = OrchestratorConfig(watch_interval=1)
ASSERT config.watch_interval == 10
```

### TS-70-11: CLI --watch-interval overrides config

**Requirement:** 70-REQ-3.3
**Type:** integration
**Description:** Verify CLI option overrides config file value.

**Preconditions:**
- Config file with `watch_interval = 120`

**Input:**
- Invoke `code --watch --watch-interval 30`

**Expected:**
- Orchestrator uses `watch_interval=30`

**Assertion pseudocode:**
```
result = cli_runner.invoke(code_cmd, ["--watch", "--watch-interval", "30"])
ASSERT orchestrator config watch_interval == 30
```

### TS-70-12: Watch interval mutable via hot-reload

**Requirement:** 70-REQ-3.4
**Type:** unit
**Description:** Verify watch_interval changes take effect after config reload.
The config change must happen on mock call 2 (first watch poll discovery),
not call 1 (main loop discovery), to ensure the first watch sleep uses the
original interval.

**Preconditions:**
- Orchestrator with `watch=True`, `watch_interval=60`
- Mock discovery: call 2 (first watch poll) updates config to
  `watch_interval=20`, returns False
- Mock sleep: tracks args, sets interrupted after 2 calls

**Input:**
- Call `orchestrator.run()`

**Expected:**
- First sleep uses 60 (original), second sleep uses 20 (hot-reloaded)

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, watch_interval=60)
poll_count = 0
mock _try_end_of_run_discovery:
    poll_count += 1
    IF poll_count == 2:  # first watch poll, not main loop
        update config.watch_interval = 20
    RETURN False
mock asyncio.sleep to track args, set interrupted after 2 calls
state = orchestrator.run()
ASSERT sleep_args[0] == 60
ASSERT sleep_args[1] == 20
```

### TS-70-13: Stall terminates in watch mode

**Requirement:** 70-REQ-4.1
**Type:** unit
**Description:** Verify stalls cause immediate termination even with watch.

**Preconditions:**
- Orchestrator with `watch=True`
- Graph with stalled tasks

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Run terminates with STALLED
- No WATCH_POLL events

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, stalled_graph=True)
state = orchestrator.run()
ASSERT state.run_status == "stalled"
ASSERT no WATCH_POLL events emitted
```

### TS-70-14: Circuit breaker stops watch loop

**Requirement:** 70-REQ-4.2
**Type:** unit
**Description:** Verify cost limit stops the watch loop.

**Preconditions:**
- Orchestrator with `watch=True`, `max_cost=10.0`
- `total_cost` at 10.0 when entering watch loop

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Run terminates with COST_LIMIT
- No sleep occurs after cost limit

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, max_cost=10.0)
state.total_cost = 10.0
state = orchestrator.run()
ASSERT state.run_status == "cost_limit"
```

### TS-70-15: SIGINT during watch sleep

**Requirement:** 70-REQ-4.3
**Type:** unit
**Description:** Verify SIGINT during sleep causes graceful shutdown.

**Preconditions:**
- Orchestrator with `watch=True`
- SIGINT delivered during asyncio.sleep

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Run terminates with INTERRUPTED

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True)
mock asyncio.sleep to set interrupted signal
state = orchestrator.run()
ASSERT state.run_status == "interrupted"
```

### TS-70-16: WATCH_POLL audit event emitted

**Requirement:** 70-REQ-5.1
**Type:** unit
**Description:** Verify WATCH_POLL event is emitted on each poll.

**Preconditions:**
- Orchestrator with `watch=True`, audit sink capturing events

**Input:**
- Run 2 poll cycles, then SIGINT

**Expected:**
- 2 WATCH_POLL events captured by sink

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, audit_sink=mock_sink)
trigger SIGINT after 2 polls
state = orchestrator.run()
watch_events = [e for e in mock_sink.events if e.type == "watch.poll"]
ASSERT len(watch_events) == 2
```

### TS-70-17: WATCH_POLL payload contents

**Requirement:** 70-REQ-5.2
**Type:** unit
**Description:** Verify poll_number and new_tasks_found in payload.
Mock must account for main loop discovery offset: call 1 is the main loop,
calls 2+ are watch polls.

**Preconditions:**
- Orchestrator with `watch=True`, audit sink
- Mock discovery:
  - Call 1 (main loop): returns False
  - Call 2 (watch poll 1): returns False (no tasks)
  - Call 3 (watch poll 2): returns True (new tasks found)
  - Call 4+ (main loop re-entry): set interrupted, return False

**Input:**
- Call `orchestrator.run()`

**Expected:**
- At least 2 WATCH_POLL events from the watch loop
- Event 0: `poll_number=1, new_tasks_found=False`
- Event 1: `poll_number=2, new_tasks_found=True`

**Assertion pseudocode:**
```
poll_count = 0
mock _try_end_of_run_discovery:
    poll_count += 1
    IF poll_count == 3: RETURN True   # watch poll 2 finds tasks
    IF poll_count >= 4: set interrupted  # terminate after re-entry
    RETURN False
state = orchestrator.run()
events = get_watch_poll_events()
ASSERT len(events) >= 2
ASSERT events[0].payload == {"poll_number": 1, "new_tasks_found": False}
ASSERT events[1].payload == {"poll_number": 2, "new_tasks_found": True}
```

### TS-70-18: WATCH_POLL in AuditEventType enum

**Requirement:** 70-REQ-5.3
**Type:** unit
**Description:** Verify WATCH_POLL exists in AuditEventType with correct value.

**Preconditions:**
- None

**Input:**
- Access `AuditEventType.WATCH_POLL`

**Expected:**
- Value is `"watch.poll"`

**Assertion pseudocode:**
```
ASSERT AuditEventType.WATCH_POLL == "watch.poll"
ASSERT "WATCH_POLL" in AuditEventType.__members__
```

## Property Test Cases

### TS-70-P1: Watch Interval Clamping

**Property:** Property 2 from design.md
**Validates:** 70-REQ-3.2, 70-REQ-3.E1
**Type:** property
**Description:** For any integer watch_interval, the effective value is
always >= 10.

**For any:** `watch_interval` in integers (including negatives and zero)
**Invariant:** `OrchestratorConfig(watch_interval=V).watch_interval >= 10`

**Assertion pseudocode:**
```
FOR ANY V IN st.integers(min_value=-100, max_value=1000):
    config = OrchestratorConfig(watch_interval=V)
    ASSERT config.watch_interval >= 10
    IF V >= 10:
        ASSERT config.watch_interval == V
```

### TS-70-P2: Poll Number Monotonicity

**Property:** Property 4 from design.md
**Validates:** 70-REQ-5.2
**Type:** property
**Description:** Poll numbers in WATCH_POLL events are strictly increasing.

**For any:** sequence of N poll cycles (1 <= N <= 20)
**Invariant:** `poll_numbers == [1, 2, ..., N]`

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(min_value=1, max_value=20):
    events = run_watch_polls(n)
    poll_numbers = [e.payload["poll_number"] for e in events]
    ASSERT poll_numbers == list(range(1, n + 1))
```

### TS-70-P3: Hot-Load Gate

**Property:** Property 3 from design.md
**Validates:** 70-REQ-1.2
**Type:** property
**Description:** When hot_load is False, watch mode never activates.

**For any:** `watch_interval` in valid range, `watch=True`, `hot_load=False`
**Invariant:** Run terminates with COMPLETED, no WATCH_POLL events emitted

**Assertion pseudocode:**
```
FOR ANY interval IN st.integers(min_value=10, max_value=300):
    state = run_orchestrator(watch=True, hot_load=False, watch_interval=interval)
    ASSERT state.run_status == "completed"
    ASSERT no WATCH_POLL events
```

### TS-70-P4: Stall Overrides Watch

**Property:** Property 6 from design.md
**Validates:** 70-REQ-4.1
**Type:** property
**Description:** Stalls always terminate the run, regardless of watch mode.

**For any:** stalled graph, `watch=True`
**Invariant:** Run terminates with STALLED, no WATCH_POLL events

**Assertion pseudocode:**
```
FOR ANY watch IN st.booleans():
    state = run_orchestrator(watch=watch, stalled_graph=True)
    ASSERT state.run_status == "stalled"
    IF watch:
        ASSERT no WATCH_POLL events
```

## Edge Case Tests

### TS-70-E1: No plan file with --watch

**Requirement:** 70-REQ-1.E1
**Type:** unit
**Description:** Missing plan file errors normally even with --watch.

**Preconditions:**
- No plan.json file exists

**Input:**
- Call `orchestrator.run()` with `watch=True`

**Expected:**
- PlanError raised (same as without watch)

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, plan_path="nonexistent")
ASSERT_RAISES PlanError: orchestrator.run()
```

### TS-70-E2: Empty plan enters watch loop

**Requirement:** 70-REQ-1.E2
**Type:** unit
**Description:** An empty plan with watch mode enters the watch loop.
The interrupt must be set via the discovery mock (not directly before
`run()`) — setting `interrupted=True` before `run()` causes the main
loop to shut down at line 507 before reaching the watch gate.

**Preconditions:**
- Valid but empty plan.json (no nodes)
- `watch=True`, `hot_load=True`
- Mock discovery sets `interrupted=True` on call 1 (main loop),
  returns False — this causes the watch loop to see the interrupt on entry

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Watch loop entered (at least 1 WATCH_POLL event emitted)
- Terminates with INTERRUPTED

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, empty_plan=True)
mock _try_end_of_run_discovery:
    set interrupted = True
    RETURN False
state = orchestrator.run()
ASSERT count(WATCH_POLL events) >= 1
ASSERT state.run_status == "interrupted"
```

### TS-70-E3: Barrier exception during watch poll

**Requirement:** 70-REQ-2.E1
**Type:** unit
**Description:** Barrier exceptions are logged but do not stop the watch loop.
The exception must be raised on mock call 2 (first watch poll), not call 1
(main loop) — the main loop does not catch `_try_end_of_run_discovery`
exceptions the same way.

**Preconditions:**
- Orchestrator with `watch=True`
- Mock discovery:
  - Call 1 (main loop): returns False (enters watch gate)
  - Call 2 (watch poll 1): raises RuntimeError
  - Call 3 (watch poll 2): sets interrupted, returns False

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Error logged for watch poll 1
- Watch poll 2 runs normally
- 2 WATCH_POLL events emitted (poll 1 with exception treated as
  `new_tasks_found=False`, poll 2 normal)

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True)
poll_count = 0
mock _try_end_of_run_discovery:
    poll_count += 1
    IF poll_count == 2: RAISE RuntimeError  # watch poll 1
    set interrupted = True  # watch poll 2
    RETURN False
state = orchestrator.run()
ASSERT error logged
ASSERT count(WATCH_POLL events) == 2
```

### TS-70-E4: Watch interval updated via hot-reload

**Requirement:** 70-REQ-2.E2
**Type:** unit
**Description:** Interval changes from config reload are used on next cycle.
Config change must happen on mock call 2 (first watch poll), not call 1
(main loop), to ensure the first watch sleep uses the original interval.

**Preconditions:**
- Orchestrator with `watch=True`, `watch_interval=60`
- Mock discovery: call 2 (first watch poll) updates config to
  `watch_interval=20`, returns False
- Mock sleep: tracks args, sets interrupted after 2 calls

**Input:**
- Call `orchestrator.run()`

**Expected:**
- First sleep: 60 seconds (original)
- Second sleep: 20 seconds (hot-reloaded)

**Assertion pseudocode:**
```
poll_count = 0
mock _try_end_of_run_discovery:
    poll_count += 1
    IF poll_count == 2:  # first watch poll
        update config.watch_interval = 20
    RETURN False
mock asyncio.sleep to track args, set interrupted after 2 calls
ASSERT sleep_calls == [60, 20]
```

### TS-70-E5: Watch interval at exact minimum

**Requirement:** 70-REQ-3.E1
**Type:** unit
**Description:** watch_interval=10 is accepted without clamping.

**Preconditions:**
- None

**Input:**
- Create `OrchestratorConfig(watch_interval=10)`

**Expected:**
- `watch_interval == 10`

**Assertion pseudocode:**
```
config = OrchestratorConfig(watch_interval=10)
ASSERT config.watch_interval == 10
```

### TS-70-E6: Circuit breaker before watch loop entry

**Requirement:** 70-REQ-4.E1
**Type:** unit
**Description:** Cost limit during dispatch prevents watch loop entry.

**Preconditions:**
- Orchestrator with `watch=True`, `max_cost=5.0`
- Task dispatch consumes $5.0

**Input:**
- Call `orchestrator.run()`

**Expected:**
- Run terminates with COST_LIMIT
- No WATCH_POLL events

**Assertion pseudocode:**
```
orchestrator = create_orchestrator(watch=True, max_cost=5.0)
mock task to consume $5.0
state = orchestrator.run()
ASSERT state.run_status == "cost_limit"
ASSERT no WATCH_POLL events
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 70-REQ-1.1 | TS-70-1 | unit |
| 70-REQ-1.2 | TS-70-2 | unit |
| 70-REQ-1.3 | TS-70-3 | integration |
| 70-REQ-1.E1 | TS-70-E1 | unit |
| 70-REQ-1.E2 | TS-70-E2 | unit |
| 70-REQ-2.1 | TS-70-4 | unit |
| 70-REQ-2.2 | TS-70-5 | unit |
| 70-REQ-2.3 | TS-70-6 | unit |
| 70-REQ-2.4 | TS-70-7 | unit |
| 70-REQ-2.5 | TS-70-8 | unit |
| 70-REQ-2.E1 | TS-70-E3 | unit |
| 70-REQ-2.E2 | TS-70-E4 | unit |
| 70-REQ-3.1 | TS-70-9 | unit |
| 70-REQ-3.2 | TS-70-10 | unit |
| 70-REQ-3.3 | TS-70-11 | integration |
| 70-REQ-3.4 | TS-70-12 | unit |
| 70-REQ-3.E1 | TS-70-E5 | unit |
| 70-REQ-4.1 | TS-70-13 | unit |
| 70-REQ-4.2 | TS-70-14 | unit |
| 70-REQ-4.3 | TS-70-15 | unit |
| 70-REQ-4.E1 | TS-70-E6 | unit |
| 70-REQ-5.1 | TS-70-16 | unit |
| 70-REQ-5.2 | TS-70-17 | unit |
| 70-REQ-5.3 | TS-70-18 | unit |
| Property 1 | TS-70-P1 | property |
| Property 2 | TS-70-P2 | property |
| Property 3 | TS-70-P3 | property |
| Property 4 | TS-70-P4 | property |
