# Test Specification: Orchestrator

## Overview

Tests for the orchestrator execution engine: execution loop, retry logic,
cascade blocking, state persistence, resume, cost/session limits, parallel
execution, exactly-once guarantees, and graceful interruption. All tests mock
`SessionRunner` -- no real LLM calls. Tests map to requirements in
`requirements.md` and correctness properties in `design.md`.

## Test Cases

### TS-04-1: Execution loop completes linear chain

**Requirement:** 04-REQ-1.1, 04-REQ-1.2, 04-REQ-1.3
**Type:** unit
**Description:** Verify the orchestrator executes a 3-task linear chain
(A -> B -> C) in order, dispatching each to the session runner.

**Preconditions:**
- Mock plan with 3 nodes: A -> B -> C (sequential dependencies).
- Mock session runner that returns success for all sessions.
- Parallelism = 1 (serial mode).

**Input:**
- `orchestrator.run()` with the mock plan.

**Expected:**
- Sessions dispatched in order: A, then B, then C.
- All nodes end in `completed` status.
- `ExecutionState.total_sessions == 3`.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT dispatch_order == ["A", "B", "C"]
ASSERT state.node_states["A"] == "completed"
ASSERT state.node_states["B"] == "completed"
ASSERT state.node_states["C"] == "completed"
ASSERT state.total_sessions == 3
```

---

### TS-04-2: Ready tasks identified correctly from graph

**Requirement:** 04-REQ-1.1
**Type:** unit
**Description:** Verify `GraphSync.ready_tasks()` returns only tasks whose
dependencies are all completed.

**Preconditions:**
- Graph: A -> B, A -> C (A has no deps; B and C both depend on A).
- A is `pending`, B is `pending`, C is `pending`.

**Input:**
- `graph_sync.ready_tasks()` before any execution.
- Then mark A as completed, call `ready_tasks()` again.

**Expected:**
- First call: only A is ready.
- After A completed: B and C are both ready.

**Assertion pseudocode:**
```
ready = graph_sync.ready_tasks()
ASSERT ready == ["A"]
graph_sync.mark_completed("A")
ready = graph_sync.ready_tasks()
ASSERT set(ready) == {"B", "C"}
```

---

### TS-04-3: Retry on failure with error feedback

**Requirement:** 04-REQ-2.1, 04-REQ-2.2
**Type:** unit
**Description:** Verify a failed task is retried with the previous error
message passed to the session runner.

**Preconditions:**
- Mock plan with 1 node (A), max_retries = 2.
- Mock session runner: fails on attempt 1 with "syntax error in line 42",
  succeeds on attempt 2.

**Input:**
- `orchestrator.run()`

**Expected:**
- Session dispatched twice for node A.
- Second dispatch receives `previous_error="syntax error in line 42"`.
- Node A ends in `completed` status.
- `state.total_sessions == 2`.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT runner.call_count("A") == 2
ASSERT runner.calls[1].previous_error == "syntax error in line 42"
ASSERT state.node_states["A"] == "completed"
```

---

### TS-04-4: Task blocked after exhausting retries

**Requirement:** 04-REQ-2.3
**Type:** unit
**Description:** Verify a task is marked as blocked after all retry attempts
fail.

**Preconditions:**
- Mock plan with 1 node (A), max_retries = 2.
- Mock session runner: fails on all 3 attempts.

**Input:**
- `orchestrator.run()`

**Expected:**
- 3 session dispatches for node A (1 initial + 2 retries).
- Node A ends in `blocked` status.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT runner.call_count("A") == 3
ASSERT state.node_states["A"] == "blocked"
```

---

### TS-04-5: Zero retries blocks immediately

**Requirement:** 04-REQ-2.E1
**Type:** unit
**Description:** Verify that with max_retries=0, a failed task is blocked
after a single attempt.

**Preconditions:**
- Mock plan with 1 node (A), max_retries = 0.
- Mock session runner: fails on attempt 1.

**Input:**
- `orchestrator.run()`

**Expected:**
- 1 session dispatch for node A.
- Node A ends in `blocked` status.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT runner.call_count("A") == 1
ASSERT state.node_states["A"] == "blocked"
```

---

### TS-04-6: Cascade blocking propagates to all dependents

**Requirement:** 04-REQ-3.1, 04-REQ-3.2
**Type:** unit
**Description:** Verify that when a task is blocked, all transitively
dependent tasks are cascade-blocked.

**Preconditions:**
- Graph: A -> B -> C -> D. A has no deps.
- A is `completed`. B fails and is blocked.

**Input:**
- `graph_sync.mark_blocked("B", "retries exhausted")`

**Expected:**
- B, C, and D are all `blocked`.
- Each cascade-blocked task records the blocking reason.

**Assertion pseudocode:**
```
blocked = graph_sync.mark_blocked("B", "retries exhausted")
ASSERT set(blocked) == {"C", "D"}
ASSERT graph_sync.node_states["B"] == "blocked"
ASSERT graph_sync.node_states["C"] == "blocked"
ASSERT graph_sync.node_states["D"] == "blocked"
```

---

### TS-04-7: Cascade blocking with diamond dependency

**Requirement:** 04-REQ-3.E1
**Type:** unit
**Description:** Verify cascade blocking in a diamond graph where a task
has multiple upstream paths.

**Preconditions:**
- Graph: A -> B, A -> C, B -> D, C -> D. A is completed.
- B fails and is blocked.

**Input:**
- `graph_sync.mark_blocked("B", "failed")`

**Expected:**
- D is blocked (because B is blocked, even though C is still pending).

**Assertion pseudocode:**
```
graph_sync.mark_blocked("B", "failed")
ASSERT graph_sync.node_states["D"] == "blocked"
```

---

### TS-04-8: State persisted after every session

**Requirement:** 04-REQ-4.1, 04-REQ-4.2
**Type:** unit
**Description:** Verify that state is written to state.jsonl after each
session completes.

**Preconditions:**
- Mock plan with 2 nodes (A -> B), both succeed.
- tmp_path for state.jsonl.

**Input:**
- `orchestrator.run()`

**Expected:**
- state.jsonl exists and contains at least 2 JSON lines.
- Last line contains both A and B as completed.
- Session history has 2 entries.

**Assertion pseudocode:**
```
state = await orchestrator.run()
lines = state_path.read_text().strip().split("\n")
ASSERT len(lines) >= 2
last_state = json.loads(lines[-1])
ASSERT last_state["node_states"]["A"] == "completed"
ASSERT last_state["node_states"]["B"] == "completed"
ASSERT len(last_state["session_history"]) == 2
```

---

### TS-04-9: Resume from persisted state

**Requirement:** 04-REQ-4.3, 04-REQ-7.2
**Type:** unit
**Description:** Verify the orchestrator loads state and skips completed tasks.

**Preconditions:**
- Mock plan with 3 nodes (A -> B -> C).
- state.jsonl pre-populated with A completed.
- Mock session runner succeeds for B and C.

**Input:**
- `orchestrator.run()` with existing state.

**Expected:**
- A is NOT dispatched (already completed).
- B and C are dispatched and completed.
- `state.total_sessions == 2` (only B and C).

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT "A" NOT IN runner.dispatched_nodes
ASSERT state.node_states["A"] == "completed"
ASSERT state.node_states["B"] == "completed"
ASSERT state.node_states["C"] == "completed"
```

---

### TS-04-10: Cost limit stops new launches

**Requirement:** 04-REQ-5.1, 04-REQ-5.2
**Type:** unit
**Description:** Verify the orchestrator stops launching new sessions when
cumulative cost reaches the configured ceiling.

**Preconditions:**
- Mock plan with 3 nodes (A, B, C -- all independent).
- max_cost = 0.50.
- Mock session runner: A costs $0.30, B costs $0.25.

**Input:**
- `orchestrator.run()`

**Expected:**
- A completes ($0.30 total).
- B completes ($0.55 total -- exceeds limit).
- C is NOT dispatched (cost limit reached).
- Run status indicates cost limit.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT state.node_states["A"] == "completed"
ASSERT state.node_states["B"] == "completed"
ASSERT state.node_states["C"] == "pending"
ASSERT state.run_status == "cost_limit"
```

---

### TS-04-11: Session limit stops new launches

**Requirement:** 04-REQ-5.3
**Type:** unit
**Description:** Verify the orchestrator stops after the configured number
of sessions.

**Preconditions:**
- Mock plan with 5 independent nodes.
- max_sessions = 3.
- Mock session runner: all succeed.

**Input:**
- `orchestrator.run()`

**Expected:**
- Exactly 3 sessions dispatched.
- 2 nodes remain pending.
- Run status indicates session limit.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT state.total_sessions == 3
completed = [n for n, s in state.node_states.items() if s == "completed"]
ASSERT len(completed) == 3
ASSERT state.run_status == "session_limit"
```

---

### TS-04-12: Parallel execution dispatches concurrent tasks

**Requirement:** 04-REQ-6.1
**Type:** unit
**Description:** Verify the parallel runner dispatches multiple independent
tasks concurrently.

**Preconditions:**
- Mock plan with 4 independent nodes (A, B, C, D -- no dependencies).
- Parallelism = 4.
- Mock session runner: all succeed with a simulated delay.

**Input:**
- `orchestrator.run()`

**Expected:**
- All 4 tasks dispatched.
- At least 2 tasks have overlapping execution times (concurrent).
- All nodes end in `completed` status.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT all(s == "completed" for s in state.node_states.values())
# Verify concurrency by checking wall-clock time < sum of individual durations
```

---

### TS-04-13: Parallel execution respects dependencies

**Requirement:** 04-REQ-6.1
**Type:** unit
**Description:** Verify that in parallel mode, tasks with unmet dependencies
are not dispatched prematurely.

**Preconditions:**
- Graph: A and B independent, C depends on A, D depends on B.
- Parallelism = 4.

**Input:**
- `orchestrator.run()`

**Expected:**
- A and B dispatched first (concurrently).
- C dispatched only after A completes.
- D dispatched only after B completes.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT runner.dispatch_time["A"] < runner.dispatch_time["C"]
ASSERT runner.dispatch_time["B"] < runner.dispatch_time["D"]
```

---

### TS-04-14: Parallel state writes are serialized

**Requirement:** 04-REQ-6.3
**Type:** unit
**Description:** Verify that concurrent state writes do not interleave.

**Preconditions:**
- Mock plan with 4 independent nodes.
- Parallelism = 4.
- Mock session runner with simulated concurrent completion.

**Input:**
- `orchestrator.run()`

**Expected:**
- state.jsonl is valid: every line is parseable JSON.
- Lines are ordered by timestamp (no interleaving).

**Assertion pseudocode:**
```
state = await orchestrator.run()
lines = state_path.read_text().strip().split("\n")
FOR EACH line IN lines:
    ASSERT json.loads(line) IS valid
timestamps = [json.loads(l)["updated_at"] for l in lines]
ASSERT timestamps == sorted(timestamps)
```

---

### TS-04-15: Graceful shutdown saves state on SIGINT

**Requirement:** 04-REQ-8.1, 04-REQ-8.3
**Type:** unit
**Description:** Verify that SIGINT triggers state save and resume message.

**Preconditions:**
- Mock plan with 5 nodes.
- Mock session runner with delay.
- Simulate SIGINT after 2 completions.

**Input:**
- `orchestrator.run()` with simulated SIGINT.

**Expected:**
- state.jsonl exists with the 2 completed tasks recorded.
- Output contains resume instructions mentioning `agent-fox code`.

**Assertion pseudocode:**
```
# Simulate SIGINT after 2nd session completes
state = await orchestrator.run()  # catches SIGINT internally
ASSERT state_path.exists()
last_state = load_last_state(state_path)
completed = [n for n, s in last_state["node_states"].items() if s == "completed"]
ASSERT len(completed) == 2
ASSERT "agent-fox code" IN captured_output
```

---

### TS-04-16: Inter-session delay is applied

**Requirement:** 04-REQ-9.1
**Type:** unit
**Description:** Verify the orchestrator waits the configured delay between
sessions.

**Preconditions:**
- Mock plan with 2 nodes (A -> B).
- inter_session_delay = 1 second.
- Mock session runner: instant completion.

**Input:**
- `orchestrator.run()` with timing.

**Expected:**
- Wall-clock time between session A end and session B start >= 1 second.

**Assertion pseudocode:**
```
start = time.monotonic()
state = await orchestrator.run()
# Verify delay was applied between sessions
ASSERT runner.dispatch_time["B"] - runner.complete_time["A"] >= 1.0
```

---

### TS-04-17: Stalled execution exits with warning

**Requirement:** 04-REQ-1.4, 04-REQ-10.E1
**Type:** unit
**Description:** Verify the orchestrator detects a stalled state and exits
with details.

**Preconditions:**
- Graph: A -> B. A fails and is blocked (max_retries = 0).
- B is cascade-blocked.

**Input:**
- `orchestrator.run()`

**Expected:**
- Run status is `stalled`.
- Output warns about blocked tasks.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT state.run_status == "stalled"
ASSERT state.node_states["A"] == "blocked"
ASSERT state.node_states["B"] == "blocked"
```

---

### TS-04-18: Exactly-once on resume with in-progress task

**Requirement:** 04-REQ-7.E1
**Type:** unit
**Description:** Verify that an `in_progress` task from a prior interrupted
run is treated as failed on resume.

**Preconditions:**
- state.jsonl with A as `completed`, B as `in_progress`.
- max_retries = 2.
- Mock session runner succeeds for B.

**Input:**
- `orchestrator.run()` with existing state.

**Expected:**
- B is reset to pending (treated as failed attempt), then dispatched.
- B receives error context indicating prior interruption.
- B ends in `completed`.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT state.node_states["B"] == "completed"
ASSERT "interrupted" IN runner.calls["B"][0].previous_error.lower()
```

## Property Test Cases

### TS-04-P1: Cascade completeness

**Property:** Property 2 from design.md
**Validates:** 04-REQ-3.1, 04-REQ-10.2
**Type:** property
**Description:** For any DAG and any blocked node, all transitively
dependent nodes are also blocked.

**For any:** DAG with N nodes (2-20) and random edges, random blocked node
**Invariant:** After `mark_blocked(node)`, every node reachable from `node`
via forward dependency edges has status `blocked`.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(2, 20),
        blocked_node IN graph.nodes:
    sync = GraphSync(graph)
    sync.mark_completed_for_ancestors(blocked_node)
    sync.mark_blocked(blocked_node, "test")
    FOR EACH reachable IN bfs_forward(graph, blocked_node):
        ASSERT sync.node_states[reachable] == "blocked"
```

---

### TS-04-P2: Ready task correctness

**Property:** Property 5 from design.md
**Validates:** 04-REQ-1.1, 04-REQ-10.1
**Type:** property
**Description:** For any graph state, every task reported as ready has all
dependencies completed.

**For any:** DAG with N nodes, random subset marked as completed
**Invariant:** For every node in `ready_tasks()`, all its dependencies
are in `completed` status.

**Assertion pseudocode:**
```
FOR ANY graph IN random_dags(2, 20),
        completed_set IN subsets(graph.nodes):
    sync = GraphSync(graph)
    FOR EACH node IN completed_set:
        sync.mark_completed(node)
    FOR EACH ready IN sync.ready_tasks():
        FOR EACH dep IN graph.dependencies(ready):
            ASSERT sync.node_states[dep] == "completed"
```

---

### TS-04-P3: Retry bound

**Property:** Property 6 from design.md
**Validates:** 04-REQ-2.1, 04-REQ-2.3
**Type:** property
**Description:** For any max_retries value and any sequence of failures,
the total attempt count never exceeds max_retries + 1.

**For any:** max_retries in [0, 5], task that always fails
**Invariant:** Session dispatch count for the task == max_retries + 1.

**Assertion pseudocode:**
```
FOR ANY max_retries IN integers(0, 5):
    config = OrchestratorConfig(max_retries=max_retries)
    circuit = CircuitBreaker(config)
    FOR attempt IN range(1, max_retries + 10):
        decision = circuit.check_launch("A", attempt, state)
        IF attempt <= max_retries + 1:
            ASSERT decision.allowed
        ELSE:
            ASSERT NOT decision.allowed
```

---

### TS-04-P4: Cost limit enforcement

**Property:** Property 3 from design.md
**Validates:** 04-REQ-5.1, 04-REQ-5.2
**Type:** property
**Description:** No sessions are launched after cumulative cost reaches the
configured ceiling.

**For any:** max_cost > 0, sequence of session costs that eventually exceed it
**Invariant:** Once `state.total_cost >= max_cost`, `circuit.should_stop()`
returns `allowed=False`.

**Assertion pseudocode:**
```
FOR ANY max_cost IN positive_floats(),
        costs IN lists(positive_floats()):
    config = OrchestratorConfig(max_cost=max_cost)
    circuit = CircuitBreaker(config)
    cumulative = 0.0
    FOR cost IN costs:
        cumulative += cost
        state = ExecutionState(total_cost=cumulative)
        decision = circuit.should_stop(state)
        IF cumulative >= max_cost:
            ASSERT NOT decision.allowed
```

---

### TS-04-P5: State save/load roundtrip

**Property:** Property 1 from design.md (resume idempotency)
**Validates:** 04-REQ-4.1, 04-REQ-4.3
**Type:** property
**Description:** Saving and loading an ExecutionState produces an
equivalent object.

**For any:** valid ExecutionState
**Invariant:** `load(save(state)) == state` (field-by-field equality).

**Assertion pseudocode:**
```
FOR ANY state IN valid_execution_states():
    manager = StateManager(tmp_path / "state.jsonl")
    manager.save(state)
    loaded = manager.load()
    ASSERT loaded.plan_hash == state.plan_hash
    ASSERT loaded.node_states == state.node_states
    ASSERT loaded.total_cost == state.total_cost
    ASSERT loaded.total_sessions == state.total_sessions
    ASSERT len(loaded.session_history) == len(state.session_history)
```

## Edge Case Tests

### TS-04-E1: Missing plan file

**Requirement:** 04-REQ-1.E1
**Type:** unit
**Description:** Verify orchestrator raises PlanError when plan.json is
missing.

**Preconditions:**
- No `.agent-fox/plan.json` file exists.

**Input:**
- `orchestrator.run()`

**Expected:**
- `PlanError` raised.
- Error message suggests running `agent-fox plan`.

**Assertion pseudocode:**
```
ASSERT_RAISES PlanError FROM orchestrator.run()
ASSERT "agent-fox plan" IN str(error)
```

---

### TS-04-E2: Empty plan

**Requirement:** 04-REQ-1.E2
**Type:** unit
**Description:** Verify orchestrator exits cleanly with an empty plan.

**Preconditions:**
- plan.json exists but contains zero task nodes.

**Input:**
- `orchestrator.run()`

**Expected:**
- No sessions dispatched.
- Returns state with `run_status == "completed"`.

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT state.total_sessions == 0
ASSERT state.run_status == "completed"
```

---

### TS-04-E3: Corrupted state file on resume

**Requirement:** 04-REQ-4.E2
**Type:** unit
**Description:** Verify orchestrator discards corrupted state and starts
fresh.

**Preconditions:**
- state.jsonl exists but contains invalid JSON.
- Mock plan with 2 nodes, both succeed.

**Input:**
- `orchestrator.run()`

**Expected:**
- Warning logged about corrupted state.
- Both tasks dispatched and completed (fresh start).

**Assertion pseudocode:**
```
state_path.write_text("{{not valid json}}\n")
state = await orchestrator.run()
ASSERT state.total_sessions == 2
ASSERT all(s == "completed" for s in state.node_states.values())
```

---

### TS-04-E4: Plan hash mismatch on resume

**Requirement:** 04-REQ-4.E1
**Type:** unit
**Description:** Verify orchestrator detects plan hash mismatch and warns.

**Preconditions:**
- state.jsonl with plan_hash = "old_hash".
- plan.json with different content (new hash).

**Input:**
- `orchestrator.run()`

**Expected:**
- Warning about plan change is logged.
- Orchestrator starts fresh (discards old state).

**Assertion pseudocode:**
```
state = await orchestrator.run()
ASSERT "plan has changed" IN captured_warnings
```

---

### TS-04-E5: Parallelism clamped to 8

**Requirement:** 04-REQ-6.2
**Type:** unit
**Description:** Verify parallelism values above 8 are clamped.

**Preconditions:**
- Config with parallel = 16.

**Input:**
- Create ParallelRunner with the clamped config.

**Expected:**
- Effective parallelism is 8.
- Warning logged.

**Assertion pseudocode:**
```
# Config clamping happens in OrchestratorConfig (spec 01)
# Verify ParallelRunner uses the clamped value
runner = ParallelRunner(factory, max_parallelism=8, delay=0)
ASSERT runner._max_parallelism == 8
```

---

### TS-04-E6: Fewer ready tasks than parallelism

**Requirement:** 04-REQ-6.E1
**Type:** unit
**Description:** Verify parallel runner does not block waiting for more
tasks when fewer are available than the parallelism limit.

**Preconditions:**
- Parallelism = 4.
- Only 2 independent tasks available.

**Input:**
- `parallel_runner.execute_batch([(A, 1, None), (B, 1, None)], callback)`

**Expected:**
- Both tasks dispatched and completed.
- No blocking or timeout.

**Assertion pseudocode:**
```
records = await runner.execute_batch([("A", 1, None), ("B", 1, None)], cb)
ASSERT len(records) == 2
```

---

### TS-04-E7: Inter-session delay of zero

**Requirement:** 04-REQ-9.E1
**Type:** unit
**Description:** Verify no delay when inter_session_delay is 0.

**Preconditions:**
- inter_session_delay = 0.
- Mock plan with 2 nodes.

**Input:**
- `orchestrator.run()` with timing.

**Expected:**
- Sessions dispatched back-to-back with negligible gap.

**Assertion pseudocode:**
```
state = await orchestrator.run()
gap = runner.dispatch_time["B"] - runner.complete_time["A"]
ASSERT gap < 0.1  # less than 100ms
```

---

### TS-04-E8: Circuit breaker denies launch at cost limit

**Requirement:** 04-REQ-5.1
**Type:** unit
**Description:** Verify the circuit breaker returns denied when cost limit
is reached.

**Preconditions:**
- Config with max_cost = 1.00.
- State with total_cost = 1.05.

**Input:**
- `circuit.should_stop(state)`

**Expected:**
- `allowed == False`, reason mentions cost limit.

**Assertion pseudocode:**
```
decision = circuit.should_stop(state)
ASSERT NOT decision.allowed
ASSERT "cost" IN decision.reason.lower()
```

---

### TS-04-E9: Circuit breaker denies launch at session limit

**Requirement:** 04-REQ-5.3
**Type:** unit
**Description:** Verify the circuit breaker returns denied when session
limit is reached.

**Preconditions:**
- Config with max_sessions = 10.
- State with total_sessions = 10.

**Input:**
- `circuit.should_stop(state)`

**Expected:**
- `allowed == False`, reason mentions session limit.

**Assertion pseudocode:**
```
decision = circuit.should_stop(state)
ASSERT NOT decision.allowed
ASSERT "session" IN decision.reason.lower()
```

---

### TS-04-E10: Stall detection

**Requirement:** 04-REQ-10.E1
**Type:** unit
**Description:** Verify `GraphSync.is_stalled()` returns True when no
progress is possible.

**Preconditions:**
- Graph: A -> B. A is `blocked`, B is `blocked`.
- No tasks in_progress.

**Input:**
- `graph_sync.is_stalled()`

**Expected:**
- Returns True.

**Assertion pseudocode:**
```
sync = GraphSync({"A": "blocked", "B": "blocked"}, edges)
ASSERT sync.is_stalled() == True
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 04-REQ-1.1 | TS-04-1, TS-04-2 | unit |
| 04-REQ-1.2 | TS-04-1 | unit |
| 04-REQ-1.3 | TS-04-1 | unit |
| 04-REQ-1.4 | TS-04-17 | unit |
| 04-REQ-1.E1 | TS-04-E1 | unit |
| 04-REQ-1.E2 | TS-04-E2 | unit |
| 04-REQ-2.1 | TS-04-3, TS-04-4 | unit |
| 04-REQ-2.2 | TS-04-3 | unit |
| 04-REQ-2.3 | TS-04-4 | unit |
| 04-REQ-2.E1 | TS-04-5 | unit |
| 04-REQ-3.1 | TS-04-6 | unit |
| 04-REQ-3.2 | TS-04-6 | unit |
| 04-REQ-3.E1 | TS-04-7 | unit |
| 04-REQ-4.1 | TS-04-8 | unit |
| 04-REQ-4.2 | TS-04-8 | unit |
| 04-REQ-4.3 | TS-04-9 | unit |
| 04-REQ-4.E1 | TS-04-E4 | unit |
| 04-REQ-4.E2 | TS-04-E3 | unit |
| 04-REQ-5.1 | TS-04-10, TS-04-E8 | unit |
| 04-REQ-5.2 | TS-04-10 | unit |
| 04-REQ-5.3 | TS-04-11, TS-04-E9 | unit |
| 04-REQ-5.E1 | TS-04-10 | unit |
| 04-REQ-6.1 | TS-04-12, TS-04-13 | unit |
| 04-REQ-6.2 | TS-04-E5 | unit |
| 04-REQ-6.3 | TS-04-14 | unit |
| 04-REQ-6.E1 | TS-04-E6 | unit |
| 04-REQ-7.1 | TS-04-1, TS-04-9 | unit |
| 04-REQ-7.2 | TS-04-9 | unit |
| 04-REQ-7.E1 | TS-04-18 | unit |
| 04-REQ-8.1 | TS-04-15 | unit |
| 04-REQ-8.2 | TS-04-15 | unit |
| 04-REQ-8.3 | TS-04-15 | unit |
| 04-REQ-8.E1 | (manual test -- double SIGINT) | manual |
| 04-REQ-9.1 | TS-04-16 | unit |
| 04-REQ-9.2 | (implicit in TS-04-17 -- no delay when stalled) | unit |
| 04-REQ-9.E1 | TS-04-E7 | unit |
| 04-REQ-10.1 | TS-04-2 | unit |
| 04-REQ-10.2 | TS-04-6 | unit |
| 04-REQ-10.E1 | TS-04-17, TS-04-E10 | unit |
| Property 1 | TS-04-P5 | property |
| Property 2 | TS-04-P1 | property |
| Property 3 | TS-04-P4 | property |
| Property 4 | (covered by TS-04-9 + TS-04-1) | unit |
| Property 5 | TS-04-P2 | property |
| Property 6 | TS-04-P3 | property |
| Property 7 | TS-04-14 | unit |
