# Requirements Document

## Introduction

This specification adds a `--hard` flag to the existing `agent-fox reset`
command. The hard reset performs a comprehensive wipe: resetting all tasks
(including completed ones) to pending, cleaning up all worktrees and local
feature branches, compacting the knowledge base, and rolling back code on
`develop` to its pre-task state. A partial variant (`reset --hard <task_id>`)
supports targeted rollback to a specific task boundary.

A prerequisite data-model change adds git revision tracking to `SessionRecord`
so that the rollback target can be determined.

## Glossary

- **Hard reset**: A reset operation that affects ALL tasks regardless of status,
  including completed tasks, and optionally rolls back code on the develop
  branch.
- **Soft reset**: The existing reset behavior — only resets tasks in `failed`,
  `blocked`, or `in_progress` states.
- **Commit SHA**: The 40-character hexadecimal git commit identifier.
- **Develop HEAD**: The commit that the `develop` branch currently points to.
- **Harvest**: The process of merging a task's feature branch into `develop`
  after a successful coding session (see `agent_fox/workspace/harvest.py`).
- **Rollback target**: The git commit to which `develop` is reset during a hard
  reset. For full hard reset, this is the develop HEAD before the first tracked
  task was committed. For partial hard reset, it is the develop HEAD before the
  specified task was committed.
- **Affected tasks**: During partial hard reset, the set of tasks whose
  `commit_sha` is no longer an ancestor of the new develop HEAD after rollback.
- **Knowledge compaction**: Deduplication and supersession resolution of the
  memory/knowledge JSONL file (see `agent_fox/memory/compaction.py`).
- **State.jsonl**: Append-only JSON Lines file where each line is a complete
  `ExecutionState` snapshot. The last line is the current state.
- **SessionRecord**: A record of a single session attempt, stored in
  `ExecutionState.session_history`.
- **Plan.json**: The serialized task graph stored at `.agent-fox/plan.json`.
  Contains node statuses that are synced with execution state.
- **Tasks.md checkboxes**: Markdown checkboxes (`[ ]`, `[x]`, `[-]`) in each
  spec's `tasks.md` file. The graph builder reads these to set initial node
  statuses when building the plan.

## Requirements

### Requirement 1: Git Revision Tracking

**User Story:** As an operator, I want each completed task to record the git
commit SHA on develop after harvest, so that hard reset can determine where to
roll back code.

#### Acceptance Criteria

1. [35-REQ-1.1] WHEN a task session completes successfully and harvest merges
   code into develop, THE system SHALL capture the current develop HEAD SHA
   (via `git rev-parse develop`) and store it in the `SessionRecord.commit_sha`
   field.
2. [35-REQ-1.2] WHEN a task session fails or produces no code changes, THE
   system SHALL set `SessionRecord.commit_sha` to an empty string.
3. [35-REQ-1.3] THE system SHALL deserialize `SessionRecord` objects that lack
   a `commit_sha` field by defaulting to an empty string.

#### Edge Cases

1. [35-REQ-1.E1] IF `git rev-parse develop` fails after a successful harvest,
   THEN THE system SHALL log a warning and set `commit_sha` to an empty string
   rather than failing the session.

### Requirement 2: Hard Reset Flag

**User Story:** As an operator, I want a `--hard` flag on the reset command so
that I can distinguish between a soft reset (existing behavior) and a full
state wipe.

#### Acceptance Criteria

1. [35-REQ-2.1] THE system SHALL accept a `--hard` boolean flag on the `reset`
   CLI command.
2. [35-REQ-2.2] WHEN `--hard` is not provided, THE system SHALL preserve the
   existing soft-reset behavior unchanged.

### Requirement 3: Full Hard Reset

**User Story:** As an operator, I want `reset --hard` to wipe all task states
and roll back code so that I can re-execute the entire project from scratch.

#### Acceptance Criteria

1. [35-REQ-3.1] WHEN the user runs `reset --hard` without a task ID, THE system
   SHALL reset ALL tasks to `pending` regardless of their current status
   (including `completed`).
2. [35-REQ-3.2] WHEN the user runs `reset --hard`, THE system SHALL clean up
   ALL worktree directories under `.agent-fox/worktrees/`.
3. [35-REQ-3.3] WHEN the user runs `reset --hard`, THE system SHALL delete ALL
   local feature branches matching the `feature/{spec}/{group}` pattern.
4. [35-REQ-3.4] WHEN the user runs `reset --hard`, THE system SHALL call the
   knowledge compaction function to deduplicate and resolve superseded facts.
5. [35-REQ-3.5] WHEN the user runs `reset --hard` AND at least one
   `SessionRecord` in the session history has a non-empty `commit_sha`, THE
   system SHALL roll back the `develop` branch to the commit immediately before
   the earliest tracked `commit_sha` on develop's first-parent history.
6. [35-REQ-3.6] WHEN the user runs `reset --hard`, THE system SHALL preserve
   `session_history`, `total_input_tokens`, `total_output_tokens`,
   `total_cost`, and `total_sessions` in the execution state.
7. [35-REQ-3.7] WHEN the user runs `reset --hard`, THE system SHALL preserve
   `.agent-fox/config.toml` and `.agent-fox/memory.jsonl`.

#### Edge Cases

1. [35-REQ-3.E1] IF no `SessionRecord` in the history has a non-empty
   `commit_sha`, THEN THE system SHALL skip the code rollback step silently
   and only reset task states and clean artifacts.
2. [35-REQ-3.E2] IF the rollback target commit cannot be resolved (e.g., git
   history was rewritten), THEN THE system SHALL log a warning, skip code
   rollback, and proceed with the remaining reset operations.

### Requirement 4: Partial Hard Reset

**User Story:** As an operator, I want `reset --hard <task_id>` to roll back
to just before a specific task so that I can re-execute from that point without
wiping earlier work.

#### Acceptance Criteria

1. [35-REQ-4.1] WHEN the user runs `reset --hard <task_id>` AND the target
   task has a completed `SessionRecord` with a non-empty `commit_sha`, THE
   system SHALL roll back `develop` to the commit immediately before that
   task's `commit_sha` on develop's first-parent history.
2. [35-REQ-4.2] WHEN the user runs `reset --hard <task_id>`, THE system SHALL
   reset the target task to `pending`.
3. [35-REQ-4.3] WHEN the user runs `reset --hard <task_id>` AND code is rolled
   back, THE system SHALL identify all other tasks whose `commit_sha` is no
   longer an ancestor of the new develop HEAD, and reset those tasks to
   `pending` as well.
4. [35-REQ-4.4] WHEN the user runs `reset --hard <task_id>`, THE system SHALL
   clean up worktrees and local feature branches for all affected tasks (the
   target task plus any cascaded tasks).
5. [35-REQ-4.5] WHEN the user runs `reset --hard <task_id>`, THE system SHALL
   compact the knowledge base.

#### Edge Cases

1. [35-REQ-4.E1] IF the target task has no completed `SessionRecord` with a
   non-empty `commit_sha`, THEN THE system SHALL skip code rollback and only
   reset the target task's state to `pending` (plus cleanup).
2. [35-REQ-4.E2] IF the target `task_id` does not exist in the plan, THEN THE
   system SHALL raise an error with the list of valid task IDs.

### Requirement 5: Confirmation

**User Story:** As an operator, I want hard reset to require confirmation so
that I do not accidentally wipe my project state.

#### Acceptance Criteria

1. [35-REQ-5.1] WHEN the user runs `reset --hard` without `--yes`, THE system
   SHALL prompt for interactive confirmation before proceeding.
2. [35-REQ-5.2] WHEN the user provides `--yes`, THE system SHALL skip the
   confirmation prompt and proceed immediately.
3. [35-REQ-5.3] WHILE in JSON mode (`--json`), THE system SHALL skip the
   confirmation prompt (non-interactive context).

#### Edge Cases

1. [35-REQ-5.E1] IF the user declines confirmation, THEN THE system SHALL
   abort the operation and print a cancellation message.

### Requirement 7: Artifact Synchronization

**User Story:** As an operator, I want hard reset to update `tasks.md`
checkboxes and `plan.json` node statuses so that subsequent `plan` and `code`
commands see the correct reset state.

#### Acceptance Criteria

1. [35-REQ-7.1] WHEN a hard reset completes, THE system SHALL reset the
   `tasks.md` checkboxes for all affected tasks from `[x]` or `[-]` to `[ ]`
   in the corresponding spec folders.
2. [35-REQ-7.2] WHEN a hard reset completes, THE system SHALL update all
   affected node statuses in `.agent-fox/plan.json` to `"pending"`.
3. [35-REQ-7.3] WHEN code rollback restores earlier versions of `tasks.md`
   files, THE system SHALL still perform the programmatic checkbox reset
   (idempotent no-op in this case).

#### Edge Cases

1. [35-REQ-7.E1] IF a `tasks.md` file does not exist for a given spec, THEN
   THE system SHALL skip that file and continue with the remaining specs.
2. [35-REQ-7.E2] IF `plan.json` does not exist, THEN THE system SHALL skip the
   plan status update and continue.

### Requirement 6: Output

**User Story:** As an operator, I want the hard reset to report what it did so
that I can verify the operation.

#### Acceptance Criteria

1. [35-REQ-6.1] WHEN a hard reset completes, THE system SHALL display a summary
   including: number of tasks reset, worktrees cleaned, branches deleted,
   compaction result (original vs surviving fact count), and whether code was
   rolled back (with the target commit SHA).
2. [35-REQ-6.2] WHILE in JSON mode, THE system SHALL emit the hard reset
   result as a JSON object containing: `reset_tasks`, `cleaned_worktrees`,
   `cleaned_branches`, `compaction` (with `original_count` and
   `surviving_count`), and `rollback` (with `target_sha` or `null`).
