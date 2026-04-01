# Requirements Document

## Introduction

This document specifies the requirements for adding a `--watch` mode to the
`agent-fox code` command. Watch mode keeps the orchestrator running after all
current tasks complete, periodically polling for new specs via the existing
sync barrier mechanism. This turns a single `code` invocation into a
long-lived process that picks up new work as it appears.

## Glossary

- **Watch mode**: A run mode where the orchestrator does not terminate after
  completing all tasks but instead enters a sleep-poll loop waiting for new
  specs.
- **Watch loop**: The sleep-poll-barrier cycle that runs when watch mode is
  active and no tasks are ready.
- **Watch interval**: The number of seconds the orchestrator sleeps between
  poll cycles in the watch loop.
- **Watch poll**: A single iteration of the watch loop: sleep, run barrier,
  check for new tasks.
- **Sync barrier sequence**: The existing multi-step synchronization routine
  (`run_sync_barrier_sequence()`) that includes develop sync, worktree
  verification, hot-load discovery, hooks, and knowledge ingestion.
- **Hot-load**: The process of discovering and incorporating new specs into the
  running task graph at runtime.
- **Circuit breaker**: The existing mechanism that stops execution when cost or
  session limits are reached.

## Requirements

### Requirement 1: Watch Mode Activation

**User Story:** As a user, I want to pass `--watch` to `agent-fox code` so
that it keeps running and picks up new specs without requiring a manual
restart.

#### Acceptance Criteria

1. [70-REQ-1.1] WHEN the user passes `--watch` to `agent-fox code`, THE
   system SHALL enter watch mode after all current tasks complete instead of
   terminating with COMPLETED status.
2. [70-REQ-1.2] WHEN watch mode is active AND `hot_load` is disabled in
   configuration, THE system SHALL log a warning and terminate with COMPLETED
   status as if `--watch` was not set.
3. [70-REQ-1.3] THE `--watch` flag SHALL be a boolean CLI flag (no value
   required) that defaults to `false`.

#### Edge Cases

1. [70-REQ-1.E1] IF no plan file exists when `--watch` is set, THEN THE
   system SHALL exit with the same error as without `--watch` (no special
   behavior).
2. [70-REQ-1.E2] IF the initial plan has zero tasks AND `--watch` is set,
   THEN THE system SHALL enter the watch loop (not terminate immediately),
   allowing specs to appear later.

### Requirement 2: Watch Loop Behavior

**User Story:** As a user, I want the orchestrator to periodically check for
new specs while idle so that new work is picked up promptly.

#### Acceptance Criteria

1. [70-REQ-2.1] WHILE in the watch loop, THE system SHALL sleep for
   `watch_interval` seconds between poll cycles.
2. [70-REQ-2.2] WHEN a watch poll cycle runs, THE system SHALL execute the
   full sync barrier sequence (`run_sync_barrier_sequence()`).
3. [70-REQ-2.3] WHEN the sync barrier discovers new ready tasks, THE system
   SHALL resume the normal dispatch loop.
4. [70-REQ-2.4] WHEN the sync barrier discovers no new tasks, THE system
   SHALL re-enter the watch loop (sleep and poll again).
5. [70-REQ-2.5] WHILE in the watch loop, THE system SHALL check for
   interruption (SIGINT) before each sleep cycle.

#### Edge Cases

1. [70-REQ-2.E1] IF the sync barrier sequence raises an exception during a
   watch poll, THEN THE system SHALL log the error and continue the watch
   loop (non-fatal).
2. [70-REQ-2.E2] IF `watch_interval` is changed via config hot-reload during
   the watch loop, THEN THE system SHALL use the updated interval on the
   next sleep cycle.

### Requirement 3: Watch Interval Configuration

**User Story:** As a user, I want to configure how frequently the orchestrator
polls for new specs so I can balance responsiveness against resource usage.

#### Acceptance Criteria

1. [70-REQ-3.1] THE `OrchestratorConfig` SHALL include a `watch_interval`
   field with a default value of 60 seconds.
2. [70-REQ-3.2] WHEN `watch_interval` is set to a value below 10, THE system
   SHALL clamp it to 10 seconds.
3. [70-REQ-3.3] THE `--watch-interval` CLI option SHALL override the
   `watch_interval` config value when provided.
4. [70-REQ-3.4] THE `watch_interval` field SHALL be mutable during config
   hot-reload.

#### Edge Cases

1. [70-REQ-3.E1] IF `watch_interval` is set to exactly 10, THEN THE system
   SHALL accept it without clamping.

### Requirement 4: Stall and Termination Behavior

**User Story:** As a user, I want watch mode to respect existing termination
conditions so the orchestrator does not run in a broken state.

#### Acceptance Criteria

1. [70-REQ-4.1] WHEN the run stalls AND watch mode is active, THE system
   SHALL terminate with `RunStatus.STALLED` (same as without watch mode).
2. [70-REQ-4.2] WHEN a circuit breaker trips (cost or session limit) during
   the watch loop, THE system SHALL terminate with the appropriate
   `RunStatus`.
3. [70-REQ-4.3] WHEN SIGINT is received during the watch loop sleep, THE
   system SHALL terminate gracefully with `RunStatus.INTERRUPTED`.

#### Edge Cases

1. [70-REQ-4.E1] IF a circuit breaker trips during the dispatch loop (not
   during the watch loop), THEN THE system SHALL terminate immediately
   without entering the watch loop.

### Requirement 5: Audit Trail

**User Story:** As an operator, I want watch poll cycles to be visible in the
audit log so I can distinguish idle polling time from active work.

#### Acceptance Criteria

1. [70-REQ-5.1] WHEN a watch poll cycle begins, THE system SHALL emit a
   `WATCH_POLL` audit event.
2. [70-REQ-5.2] THE `WATCH_POLL` audit event payload SHALL include
   `poll_number` (1-indexed count of polls in this run) and
   `new_tasks_found` (boolean).
3. [70-REQ-5.3] THE `WATCH_POLL` event SHALL be added to the
   `AuditEventType` enum as `WATCH_POLL = "watch.poll"`.
