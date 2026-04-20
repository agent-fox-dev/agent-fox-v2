# Requirements Document

## Introduction

This specification extends the `agent-fox code` command to check for new specs
when the orchestrator would otherwise terminate with COMPLETED status. If new
specs are discovered through the existing gated hot-load pipeline, they are
added to the task graph and execution continues. This enables continuous
autonomous operation without manual restarts.

## Glossary

- **End-of-run discovery**: The process of checking for new specs when all
  current tasks are complete, before terminating the run.
- **Sync barrier**: A synchronization point during execution where the
  orchestrator syncs with the develop branch, runs hooks, and discovers new
  specs via gated hot-load.
- **Gated discovery**: The three-gate pipeline (git-tracked, completeness,
  lint validation) that filters candidate specs before hot-loading.
- **Hot-load**: Adding new specs to the running task graph without restarting
  the orchestrator.
- **COMPLETED status**: The run status indicating all tasks in the graph have
  finished and no ready tasks remain.

## Requirements

### Requirement 1: End-of-Run Discovery Trigger

**User Story:** As an operator, I want the orchestrator to check for new specs
when all current work is done, so that I don't have to manually restart
`agent-fox code` when new specs are pushed.

#### Acceptance Criteria

1. [60-REQ-1.1] WHEN the orchestrator determines that no ready tasks remain
   AND no tasks are pending or in-progress (COMPLETED state), THE system SHALL
   run the sync barrier sequence before terminating.
2. [60-REQ-1.2] WHEN the sync barrier sequence discovers and hot-loads new
   specs, THE system SHALL re-evaluate ready tasks and continue the main
   execution loop.
3. [60-REQ-1.3] WHEN the sync barrier sequence discovers no new specs, THE
   system SHALL terminate with `RunStatus.COMPLETED` as before.
4. [60-REQ-1.4] WHEN end-of-run discovery loads new specs and execution
   continues, THE system SHALL repeat end-of-run discovery each time all tasks
   complete again, without limit.

#### Edge Cases

1. [60-REQ-1.E1] IF `hot_load_enabled` is false in the orchestrator config,
   THEN THE system SHALL skip end-of-run discovery and terminate immediately
   with COMPLETED status.
2. [60-REQ-1.E2] IF the sync barrier sequence fails (e.g., git sync error),
   THEN THE system SHALL log the error and terminate with COMPLETED status
   rather than retrying or crashing.

### Requirement 2: Terminal State Exclusivity

**User Story:** As an operator, I want end-of-run discovery to only apply when
all work is truly done, not when the run is stuck or limited.

#### Acceptance Criteria

1. [60-REQ-2.1] WHEN the run terminates with STALLED status, THE system SHALL
   NOT perform end-of-run discovery.
2. [60-REQ-2.2] WHEN the run terminates with COST_LIMIT or SESSION_LIMIT
   status, THE system SHALL NOT perform end-of-run discovery.
3. [60-REQ-2.3] WHEN the run terminates with BLOCK_LIMIT status, THE system
   SHALL NOT perform end-of-run discovery.
4. [60-REQ-2.4] WHEN the run terminates with INTERRUPTED status (SIGINT), THE
   system SHALL NOT perform end-of-run discovery.

### Requirement 3: Barrier Sequence Reuse

**User Story:** As a developer, I want end-of-run discovery to use the same
barrier logic as mid-run barriers, so that spec readiness checks are consistent.

#### Acceptance Criteria

1. [60-REQ-3.1] WHEN end-of-run discovery runs, THE system SHALL execute the
   full `run_sync_barrier_sequence()` including develop sync, worktree
   verification, hooks, gated hot-load, knowledge ingestion, and memory
   regeneration.
2. [60-REQ-3.2] WHEN end-of-run discovery runs, THE system SHALL apply the
   same three-gate pipeline (git-tracked, completeness, lint) as mid-run
   hot-load discovery.
3. [60-REQ-3.3] WHEN end-of-run discovery runs, THE system SHALL emit audit
   events using the existing `SYNC_BARRIER` event type.
