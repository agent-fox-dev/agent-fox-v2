# Requirements Document: Orchestrator

## Introduction

This document specifies the orchestrator engine for agent-fox v2: the
deterministic execution loop that reads the task graph, dispatches sessions in
dependency order (serial or parallel), handles retry logic with error feedback,
cascade-blocks failed tasks, persists execution state, enforces cost and session
limits, and handles graceful interruption. It depends on core foundation (spec
01), the planning engine (spec 02), and the session runner (spec 03).

## Glossary

| Term | Definition |
|------|-----------|
| Orchestrator | The deterministic execution engine that walks the task graph and dispatches sessions |
| Execution state | The persistent record of which tasks are complete, failed, blocked, or pending, plus cumulative cost and token usage |
| Session record | A single entry recording one attempt at executing a task: outcome, cost, duration, error message |
| Cascade block | The process of marking all downstream dependents of a failed task as blocked |
| Circuit breaker | The component that checks cost ceilings, session limits, and retry counters before launching a session |
| Ready task | A task whose status is `pending` and whose dependencies are all `completed` |
| In-flight task | A task that is currently being executed by a session runner |
| Resume | Re-starting execution after interruption, loading persisted state to skip completed tasks |
| Inter-session delay | A configurable pause between consecutive session launches to avoid API rate limiting |
| Plan hash | A hash of the plan file used to detect if the plan has changed since the state was persisted |

## Requirements

### Requirement 1: Execution Loop

**User Story:** As a developer, I want the orchestrator to automatically
execute tasks in the correct dependency order so that each task's prerequisites
are completed before it begins.

#### Acceptance Criteria

1. [04-REQ-1.1] WHEN the orchestrator starts, THE system SHALL load the task
   graph from `.agent-fox/plan.json` and identify all ready tasks (status
   `pending` with all dependencies `completed`).

2. [04-REQ-1.2] THE orchestrator SHALL execute ready tasks by dispatching them
   to the session runner, one at a time in serial mode (default) or up to the
   configured parallelism in parallel mode.

3. [04-REQ-1.3] AFTER each session completes (success or failure), THE
   orchestrator SHALL update the task graph, persist state, re-evaluate
   which tasks are now ready, and continue until no more tasks can proceed.

4. [04-REQ-1.4] WHEN no tasks can proceed but incomplete tasks remain (all
   are blocked or failed with no ready tasks), THE orchestrator SHALL warn
   the user with details about which tasks are stuck and why, then exit.

#### Edge Cases

1. [04-REQ-1.E1] IF the plan file does not exist or is corrupted, THEN THE
   orchestrator SHALL raise a `PlanError` instructing the user to run
   `agent-fox plan` first.

2. [04-REQ-1.E2] IF the plan is empty (zero task nodes), THEN THE orchestrator
   SHALL print a message indicating there is nothing to execute and exit
   successfully.

---

### Requirement 2: Retry Logic

**User Story:** As a developer, I want failed sessions to be retried with
the previous error message so the agent can learn from its mistakes.

#### Acceptance Criteria

1. [04-REQ-2.1] WHEN a coding session fails, THE orchestrator SHALL retry the
   task up to the configured maximum retry count (default: 2) before marking
   the task as blocked.

2. [04-REQ-2.2] WHEN retrying a failed task, THE orchestrator SHALL pass the
   previous attempt's error message to the session runner so the agent
   receives it as context.

3. [04-REQ-2.3] WHEN all retry attempts are exhausted, THE orchestrator SHALL
   set the task's status to `blocked` and record the final error message.

#### Edge Cases

1. [04-REQ-2.E1] IF max_retries is set to 0, THEN THE orchestrator SHALL
   mark the task as blocked on the first failure with no retry attempts.

---

### Requirement 3: Cascade Blocking

**User Story:** As a developer, I want all tasks that depend on a failed task
to be automatically blocked so the orchestrator does not waste sessions on
work that cannot succeed.

#### Acceptance Criteria

1. [04-REQ-3.1] WHEN a task is marked as blocked, THE orchestrator SHALL
   cascade-block all tasks that are transitively dependent on it (all
   downstream nodes reachable via dependency edges).

2. [04-REQ-3.2] THE orchestrator SHALL record the blocking reason on each
   cascade-blocked task, identifying the upstream task that caused the block.

#### Edge Cases

1. [04-REQ-3.E1] IF a cascade-blocked task has multiple upstream paths and
   only one is blocked, THE task SHALL still be blocked (all prerequisites
   must be met).

---

### Requirement 4: State Persistence

**User Story:** As a developer, I want execution progress saved after every
session so that I can resume after interruption without losing completed work.

#### Acceptance Criteria

1. [04-REQ-4.1] THE orchestrator SHALL persist an `ExecutionState` record to
   `.agent-fox/state.jsonl` after every session completion (success or failure).

2. [04-REQ-4.2] THE state record SHALL include: plan hash, per-node statuses,
   session history (all attempts with outcome, cost, duration, error), and
   cumulative token/cost totals.

3. [04-REQ-4.3] WHEN the orchestrator starts and a state file exists, THE
   system SHALL load the state, verify the plan hash matches, identify
   completed and failed tasks, and continue from the first ready task.

#### Edge Cases

1. [04-REQ-4.E1] IF the state file exists but the plan hash does not match
   (plan has been re-generated), THEN THE orchestrator SHALL log a warning
   and start fresh automatically (discarding the stale state by creating a
   new execution state rather than explicitly deleting the old file).

2. [04-REQ-4.E2] IF the state file is corrupted or unparseable, THEN THE
   orchestrator SHALL log a warning, discard it, and start from the beginning.

---

### Requirement 5: Cost and Session Limits

**User Story:** As a developer, I want to set cost and session count ceilings
so the orchestrator does not spend more than I intend.

#### Acceptance Criteria

1. [04-REQ-5.1] WHERE a cost limit is configured (`max_cost`), THE
   orchestrator SHALL stop launching new sessions when cumulative cost
   across all sessions reaches or exceeds the limit.

2. [04-REQ-5.2] WHEN the cost limit is reached, THE orchestrator SHALL allow
   in-flight sessions to complete, then report progress and exit.

3. [04-REQ-5.3] WHERE a session limit is configured (`max_sessions`), THE
   orchestrator SHALL stop launching new sessions after the specified number
   of sessions have been dispatched.

#### Edge Cases

1. [04-REQ-5.E1] IF a single session's cost exceeds the remaining budget,
   THE orchestrator SHALL NOT preemptively cancel that session -- only
   prevent future launches.

---

### Requirement 6: Parallel Execution

**User Story:** As a developer, I want to run up to 8 independent tasks
concurrently to reduce wall-clock time on large specifications.

#### Acceptance Criteria

1. [04-REQ-6.1] WHERE parallel execution is configured (parallelism > 1),
   THE orchestrator SHALL execute up to the configured number of independent
   ready tasks concurrently using asyncio.

2. [04-REQ-6.2] THE maximum parallelism SHALL be capped at 8. If the user
   configures more, THE system SHALL clamp to 8 and log a warning.

3. [04-REQ-6.3] DURING parallel execution, THE orchestrator SHALL process
   session results sequentially in the single-threaded asyncio event loop
   after `asyncio.wait()` returns, which provides sequential state-write
   guarantees without an explicit lock on the production streaming-pool
   path. Test and batch APIs MAY use an explicit `asyncio.Lock` for
   defense-in-depth.

#### Edge Cases

1. [04-REQ-6.E1] IF fewer ready tasks exist than the configured parallelism,
   THE orchestrator SHALL execute only the available ready tasks without
   waiting for more to become available.

---

### Requirement 7: Exactly-Once Execution

**User Story:** As a developer, I want each task executed exactly once so that
no work is duplicated and no sessions are wasted.

#### Acceptance Criteria

1. [04-REQ-7.1] THE orchestrator SHALL guarantee that a task transitions from
   `pending` to `in_progress` at most once per execution run (or per retry
   attempt, if retries are configured).

2. [04-REQ-7.2] WHEN resuming from persisted state, THE orchestrator SHALL
   NOT re-execute tasks whose status is `completed`.

#### Edge Cases

1. [04-REQ-7.E1] IF the orchestrator is interrupted while a task is
   `in_progress`, THEN on resume THE task SHALL be treated as failed and
   subject to retry logic (the incomplete session's work is discarded).

---

### Requirement 8: Graceful Interruption

**User Story:** As a developer, I want to press Ctrl+C and have the
orchestrator save my progress and print instructions for resuming.

#### Acceptance Criteria

1. [04-REQ-8.1] WHEN the orchestrator receives SIGINT (Ctrl+C), THE system
   SHALL save the current execution state to `.agent-fox/state.jsonl`.

2. [04-REQ-8.2] WHEN interrupted during parallel execution, THE system SHALL
   cancel all in-flight session tasks and wait for cancellation to complete.

3. [04-REQ-8.3] AFTER saving state and cleanup, THE system SHALL print a
   message indicating how many tasks were completed, how many remain, and
   the command to resume (`agent-fox code`).

#### Edge Cases

1. [04-REQ-8.E1] IF a second SIGINT is received during cleanup, THE system
   SHALL exit immediately without further cleanup.

---

### Requirement 9: Inter-Session Delay

**User Story:** As a developer, I want a configurable pause between sessions
to avoid hitting API rate limits.

#### Acceptance Criteria

1. [04-REQ-9.1] THE orchestrator SHALL wait the configured inter-session delay
   (default: 3 seconds) after each session completes before launching the
   next session.

2. [04-REQ-9.2] THE inter-session delay SHALL be skipped when there are no
   more ready tasks to launch.

#### Edge Cases

1. [04-REQ-9.E1] IF the delay is set to 0, THE orchestrator SHALL not pause
   between sessions.

---

### Requirement 10: Graph State Propagation

**User Story:** As a developer, I want the orchestrator to correctly track
which tasks are ready, completed, failed, or blocked at all times.

#### Acceptance Criteria

1. [04-REQ-10.1] WHEN a session succeeds, THE orchestrator SHALL mark the
   task as `completed` and re-evaluate all pending tasks to identify newly
   ready ones.

2. [04-REQ-10.2] WHEN a task is marked as `blocked`, THE orchestrator SHALL
   propagate cascade blocks to all transitively dependent tasks and mark
   them as `blocked`.

#### Edge Cases

1. [04-REQ-10.E1] IF all remaining tasks are blocked and no tasks are
   in-flight, THE orchestrator SHALL report the stalled state and exit
   with a non-zero exit code.
