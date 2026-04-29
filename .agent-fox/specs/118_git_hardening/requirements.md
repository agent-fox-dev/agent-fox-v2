# Requirements Document

## Introduction

This specification hardens the git operations stack in agent-fox to detect
workspace issues early, classify errors for correct retry behavior, and provide
actionable diagnostics. The primary focus is preventing wasted compute when the
repository state makes harvest impossible.

## Glossary

- **Harvest**: The process of squash-merging a feature branch into the develop
  branch after a coding session completes. Implemented in
  `agent_fox/workspace/harvest.py`.
- **Workspace health check**: A pre-dispatch validation that verifies the
  repository working tree is in a state that permits harvest.
- **Force-clean**: An opt-in mode that automatically removes conflicting
  untracked files instead of aborting.
- **Non-retryable error**: An error caused by external workspace state (not
  coding quality) that cannot be resolved by re-running the same session.
- **Cascade blocking**: When a node is blocked, all downstream dependent nodes
  in the task graph are transitively blocked.
- **Divergent untracked file**: An untracked file on disk whose content differs
  from the version of the same file on the incoming feature branch.
- **Stale run**: A run entry in the knowledge database with status "running"
  from a prior process that exited without transitioning the run to a terminal
  status.
- **Escalation ladder**: The retry mechanism that attempts a failed node
  multiple times, optionally escalating to a higher model tier, before
  blocking. Implemented in `agent_fox/routing/escalation.py`.
- **Develop sync**: The process of ensuring the local develop branch is
  up-to-date with origin before creating worktrees. Implemented in
  `agent_fox/workspace/develop.py`.

## Requirements

### Requirement 1: Pre-Run Workspace Health Gate

**User Story:** As a user running agent-fox, I want the engine to verify
workspace cleanliness before spending tokens on coding sessions, so that I
don't waste time and money on sessions that can't be harvested.

#### Acceptance Criteria

1. [118-REQ-1.1] WHEN the engine starts a new run, THE system SHALL check the
   repository working tree for untracked files (respecting `.gitignore`
   exclusions) and report any found AND return the list of detected files to
   the caller for further action.
2. [118-REQ-1.2] IF the pre-run health check finds untracked files AND the
   `force_clean` option is not enabled, THEN THE system SHALL abort the run
   with an error message listing the untracked files and remediation commands.
3. [118-REQ-1.3] WHEN the pre-run health check completes with no issues, THE
   system SHALL log a confirmation message at INFO level and proceed with
   session dispatch.

#### Edge Cases

1. [118-REQ-1.E1] IF the repository has no untracked files but has a dirty
   index (staged uncommitted changes), THEN THE system SHALL include the dirty
   index in the health report and treat it as a blocking issue.
2. [118-REQ-1.E2] IF the health check fails due to a git command error, THEN
   THE system SHALL log a WARNING and proceed with the run (fail-open for git
   errors, fail-closed for workspace issues).

### Requirement 2: Force-Clean Workspace Option

**User Story:** As a user, I want to opt into automatic cleanup of conflicting
untracked files, so that I don't have to manually clean the workspace before
re-running.

#### Acceptance Criteria

1. [118-REQ-2.1] WHERE the `force_clean` option is enabled, THE system SHALL
   remove all untracked files detected by the pre-run health check before
   proceeding with session dispatch AND log a WARNING listing every file
   removed.
2. [118-REQ-2.2] THE system SHALL accept the `force_clean` option via both a
   CLI flag (`--force-clean`) on the `code` command and a configuration key
   (`workspace.force_clean`) in the project config file.
3. [118-REQ-2.3] WHERE the `force_clean` option is enabled AND harvest detects
   divergent untracked files, THE system SHALL remove the divergent files and
   proceed with the merge instead of raising an IntegrationError.

#### Edge Cases

1. [118-REQ-2.E1] IF force-clean is enabled AND the health check finds a dirty
   index, THEN THE system SHALL reset the index via `git checkout -- .` and log
   a WARNING listing the reset files.
2. [118-REQ-2.E2] IF a file cannot be removed during force-clean (permission
   error), THEN THE system SHALL log a WARNING for that file, include it in the
   health report as unresolved, and abort the run with a diagnostic message.

### Requirement 3: Non-Retryable Error Classification

**User Story:** As a user, I want the system to immediately block nodes when
the failure is due to workspace state, so that retries don't waste tokens on
the same non-recoverable error.

#### Acceptance Criteria

1. [118-REQ-3.1] WHEN harvest fails due to divergent untracked files in
   `_clean_conflicting_untracked`, THE system SHALL mark the resulting
   IntegrationError as non-retryable by setting `retryable=False` on the
   exception.
2. [118-REQ-3.2] WHEN the result handler processes a failed session whose error
   is marked non-retryable, THE system SHALL block the node immediately without
   consuming escalation ladder retries AND return the non-retryable
   classification in the blocked reason.
3. [118-REQ-3.3] WHEN a node is blocked due to a non-retryable error, THE
   system SHALL include the classification "workspace-state" in the blocked
   reason string.

#### Edge Cases

1. [118-REQ-3.E1] IF a harvest failure is due to a merge conflict (not
   divergent untracked files), THEN THE system SHALL treat it as retryable
   (existing behavior preserved; `retryable` defaults to `True`).

### Requirement 4: Pre-Session Workspace Guard

**User Story:** As a user, I want the system to verify workspace health before
each session dispatch, so that mid-run workspace drift doesn't waste tokens.

#### Acceptance Criteria

1. [118-REQ-4.1] WHEN the engine prepares to dispatch a coding session, THE
   system SHALL perform a lightweight workspace check (untracked file scan)
   before creating the worktree AND return the result to the dispatcher.
2. [118-REQ-4.2] IF the pre-session check detects untracked files that would
   block harvest, THEN THE system SHALL skip the session dispatch and block the
   node with a diagnostic message identifying the conflicting files.
3. [118-REQ-4.3] WHEN the pre-session workspace check passes, THE system SHALL
   proceed with worktree creation and session dispatch.

#### Edge Cases

1. [118-REQ-4.E1] IF the pre-session check fails due to a git command error,
   THEN THE system SHALL log a WARNING and proceed with the dispatch
   (fail-open).

### Requirement 5: Develop Sync Audit Trail

**User Story:** As a user reviewing run logs, I want structured audit events
for develop branch sync operations, so that I can diagnose sync-related
failures.

#### Acceptance Criteria

1. [118-REQ-5.1] WHEN the develop branch sync succeeds, THE system SHALL emit
   a `develop.sync` audit event with severity `info` and a payload containing
   the sync method used (fast-forward, rebase, or merge) and the commit counts
   (local-ahead, remote-ahead) AND return the sync method to the caller.
2. [118-REQ-5.2] WHEN the develop branch sync fails, THE system SHALL emit a
   `develop.sync_failed` audit event with severity `warning` and a payload
   containing the failure reason and the divergence state.
3. [118-REQ-5.3] WHEN the develop branch sync detects divergence (local ahead
   AND remote ahead), THE system SHALL log the commit counts at INFO level
   before attempting reconciliation.

#### Edge Cases

1. [118-REQ-5.E1] IF the remote is unreachable during fetch, THEN THE system
   SHALL emit a `develop.fetch_failed` audit event with severity `warning` and
   proceed with local-only state.

### Requirement 6: Run Lifecycle Completeness

**User Story:** As a user, I want every run to reach a terminal status, so that
the knowledge database doesn't accumulate stale "running" entries.

#### Acceptance Criteria

1. [118-REQ-6.1] WHEN the engine starts, THE system SHALL scan for prior runs
   with status "running" in the knowledge database, transition each to
   "stalled" with a reason noting stale detection, AND return the count of
   stale runs found.
2. [118-REQ-6.2] THE system SHALL register a cleanup handler (via `atexit` or
   signal handling) that transitions the current run to "stalled" on unexpected
   process termination.
3. [118-REQ-6.3] WHEN the engine completes normally (success or failure), THE
   system SHALL verify the current run has reached a terminal status
   (completed, failed, or stalled) before exiting.

#### Edge Cases

1. [118-REQ-6.E1] IF the cleanup handler cannot write to the database (e.g.,
   database locked or corrupted), THEN THE system SHALL log a WARNING and exit
   without blocking.
2. [118-REQ-6.E2] IF multiple stale runs are detected on startup, THE system
   SHALL transition all of them to "stalled".

### Requirement 7: Idempotent Cascade Blocking

**User Story:** As a user reviewing logs, I want cascade blocking to be clean
and not produce spurious warnings, so that real issues aren't obscured by
noise.

#### Acceptance Criteria

1. [118-REQ-7.1] WHEN cascade-blocking a node that is already in "blocked"
   state, THE system SHALL skip the transition silently (no warning log, no
   audit event).
2. [118-REQ-7.2] WHEN cascade-blocking a node that is in "completed" state,
   THE system SHALL skip the transition (completed nodes are terminal).

#### Edge Cases

1. [118-REQ-7.E1] WHEN cascade-blocking a node that is in "in_progress" state,
   THE system SHALL skip the transition and log a DEBUG message noting that the
   node is actively running and will be handled upon completion.

### Requirement 8: Actionable Error Diagnostics

**User Story:** As a user encountering harvest failures, I want error messages
that tell me exactly what's wrong and how to fix it, so that I can resolve
issues without reading source code.

#### Acceptance Criteria

1. [118-REQ-8.1] WHEN a harvest failure occurs due to divergent untracked
   files, THE system SHALL include in the error message: (a) the list of
   conflicting files, (b) the remediation command (`git clean -fd`), and (c)
   the suggestion to use `--force-clean` for automatic cleanup.
2. [118-REQ-8.2] WHEN a pre-run health check fails, THE system SHALL include
   the same diagnostic format as harvest failures: file list, remediation
   commands, and `--force-clean` suggestion.
3. [118-REQ-8.3] WHEN a run stalls or fails due to workspace-state errors, THE
   system SHALL include the root cause classification ("workspace-state") and
   the original error message in the final run summary output.

#### Edge Cases

1. [118-REQ-8.E1] IF the list of conflicting files exceeds 20, THEN THE system
   SHALL show the first 20 files followed by "... and N more" to prevent
   excessive output.
