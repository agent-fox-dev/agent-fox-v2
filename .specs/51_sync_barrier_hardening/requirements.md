# Requirements Document

## Introduction

This specification hardens the sync barrier — the periodic checkpoint in the
orchestrator where execution pauses to synchronize state, discover new specs,
and regenerate knowledge summaries. The changes ensure that no agents are
running during the barrier, that the develop branch is fully synchronized with
the remote, and that only well-formed, committed specs are hot-loaded into the
plan.

## Glossary

- **Sync barrier**: A periodic checkpoint triggered every N completed tasks
  (configured via `orchestrator.sync_interval`) where the orchestrator pauses
  to run hooks, hot-load specs, and regenerate memory.
- **Hot-load**: The process of discovering new spec folders in `.specs/` and
  incorporating them into the running task graph without restarting.
- **Parallel drain**: Waiting for all in-flight asyncio tasks in the parallel
  dispatch pool to complete before proceeding.
- **Worktree**: An isolated git worktree created under `.agent-fox/worktrees/`
  for each coding session.
- **Harvest**: The process of merging a session's feature branch into develop
  after successful completion.
- **MergeLock**: A file-based lock that serializes develop-branch operations
  across asyncio tasks and OS processes.
- **Spec gate**: A validation check that a candidate spec must pass to be
  accepted for hot-loading.
- **Develop sync**: The process of synchronizing the local `develop` branch
  with `origin/develop` in both directions (pull then push).

## Requirements

### Requirement 1: Parallel Drain Before Barrier

**User Story:** As an orchestrator operator, I want all in-flight tasks to
complete before the sync barrier fires, so that no agents are running during
barrier operations and all session results are reflected in the state.

#### Acceptance Criteria

[51-REQ-1.1] WHEN parallel dispatch is active AND a sync barrier is triggered,
THE orchestrator SHALL wait for all in-flight tasks in the parallel pool to
complete and process their results before entering the barrier sequence.

[51-REQ-1.2] WHEN the parallel drain completes, THE orchestrator SHALL have
processed all session results (state updates, cascade blocking, outcome
recording) for the drained tasks before proceeding to barrier operations.

[51-REQ-1.3] WHILE draining the parallel pool, THE orchestrator SHALL NOT
dispatch new tasks until the barrier sequence completes.

#### Edge Cases

[51-REQ-1.E1] IF the orchestrator is running in serial mode, THEN THE
orchestrator SHALL skip the parallel drain step and proceed directly to barrier
operations (no behavioral change from current serial flow).

[51-REQ-1.E2] IF a SIGINT is received during the parallel drain, THEN THE
orchestrator SHALL cancel the drain and proceed to graceful shutdown as per
existing SIGINT handling.

### Requirement 2: Worktree Verification

**User Story:** As an orchestrator operator, I want the barrier to verify that
no orphaned worktrees remain, so that I am alerted to sessions whose changes
may not have been merged into develop.

#### Acceptance Criteria

[51-REQ-2.1] WHEN the sync barrier enters, THE orchestrator SHALL scan the
`.agent-fox/worktrees/` directory for any remaining subdirectories.

[51-REQ-2.2] IF orphaned worktree directories are found, THEN THE orchestrator
SHALL log a warning listing each orphaned path.

[51-REQ-2.3] THE orchestrator SHALL proceed with the barrier sequence
regardless of whether orphaned worktrees are found (verification is
advisory, not blocking).

#### Edge Cases

[51-REQ-2.E1] IF the `.agent-fox/worktrees/` directory does not exist, THEN
THE orchestrator SHALL treat the verification as passed (no orphans) and
proceed without error.

### Requirement 3: Bidirectional Develop Sync

**User Story:** As an orchestrator operator, I want the barrier to
synchronize local develop with origin/develop in both directions, so that
remote collaborators see the latest work and local develop includes any
remote changes.

#### Acceptance Criteria

[51-REQ-3.1] WHEN the sync barrier enters, THE orchestrator SHALL fetch from
origin and synchronize local develop with origin/develop (pull direction)
using the existing develop sync mechanism.

[51-REQ-3.2] AFTER the pull sync completes, THE orchestrator SHALL push local
develop to origin.

[51-REQ-3.3] THE orchestrator SHALL acquire the MergeLock before performing
any develop sync operations and release it after both pull and push complete.

#### Edge Cases

[51-REQ-3.E1] IF the pull sync fails (fetch failure, merge conflict), THEN
THE orchestrator SHALL log a warning and skip the push step, proceeding with
the barrier using local develop as-is.

[51-REQ-3.E2] IF the push to origin fails, THEN THE orchestrator SHALL log a
warning and proceed with the barrier — push failure is non-blocking.

[51-REQ-3.E3] IF no remote named `origin` exists, THEN THE orchestrator SHALL
skip the entire develop sync step and proceed with local develop as-is.

### Requirement 4: Git-Tracked Spec Discovery

**User Story:** As an orchestrator operator, I want only specs committed to
the develop branch to be hot-loaded, so that transient or work-in-progress
spec folders on disk are not incorporated into the plan.

#### Acceptance Criteria

[51-REQ-4.1] WHEN discovering new specs for hot-loading, THE orchestrator
SHALL verify that each candidate spec folder is tracked by git on the local
`develop` branch by checking `git ls-tree`.

[51-REQ-4.2] IF a candidate spec folder is not tracked on the develop branch,
THEN THE orchestrator SHALL skip it with a debug-level log message.

#### Edge Cases

[51-REQ-4.E1] IF `git ls-tree` fails (e.g., develop branch does not exist),
THEN THE orchestrator SHALL fall back to the current filesystem-based
discovery and log a warning.

### Requirement 5: Spec Completeness Gate

**User Story:** As an orchestrator operator, I want only complete specs (all
five required documents) to be hot-loaded, so that the plan does not contain
nodes that will fail due to missing spec files.

#### Acceptance Criteria

[51-REQ-5.1] WHEN evaluating a candidate spec for hot-loading, THE
orchestrator SHALL verify that all five required files exist: `prd.md`,
`requirements.md`, `design.md`, `test_spec.md`, `tasks.md`.

[51-REQ-5.2] IF any of the five required files is missing, THEN THE
orchestrator SHALL skip the spec with an info-level log message naming the
missing file(s).

#### Edge Cases

[51-REQ-5.E1] IF a spec has all five files but one or more are empty (zero
bytes), THEN THE orchestrator SHALL treat the spec as incomplete and skip it.

### Requirement 6: Spec Lint Gate

**User Story:** As an orchestrator operator, I want specs with structural
errors to be rejected at the hot-load gate, so that only well-formed specs
are incorporated into the plan.

#### Acceptance Criteria

[51-REQ-6.1] WHEN a candidate spec passes the completeness gate, THE
orchestrator SHALL run the spec validator (`validate_specs`) against it.

[51-REQ-6.2] IF the validator produces any finding with severity `error`,
THEN THE orchestrator SHALL skip the spec with a warning-level log message
listing the error findings.

[51-REQ-6.3] IF the validator produces only findings with severity `warning`
or `hint` (no errors), THEN THE orchestrator SHALL accept the spec for
hot-loading.

#### Edge Cases

[51-REQ-6.E1] IF the validator raises an unexpected exception, THEN THE
orchestrator SHALL skip the spec with a warning-level log message and
proceed — validator crashes are non-blocking for the barrier.

### Requirement 7: Skip and Re-evaluate

**User Story:** As an orchestrator operator, I want specs that fail any gate
to be silently skipped and re-evaluated at the next barrier, so that specs
that are fixed between barriers are automatically picked up.

#### Acceptance Criteria

[51-REQ-7.1] WHEN a candidate spec fails any gate (tracking, completeness,
lint), THE orchestrator SHALL exclude it from the current hot-load cycle.

[51-REQ-7.2] THE orchestrator SHALL NOT maintain any persistent record of
specs that were skipped — each barrier evaluates candidates with a clean
slate.

[51-REQ-7.3] WHEN a previously skipped spec passes all gates at a
subsequent barrier, THE orchestrator SHALL incorporate it into the plan
normally.
