# Requirements Document

## Introduction

This specification hardens the git worktree lifecycle in agent-fox to eliminate
a race condition where stale worktree registry entries cause branch deletion
failures, leading to session crashes and unnecessary retries.

## Glossary

- **Worktree registry**: Git's internal tracking of active worktrees, stored
  under `.git/worktrees/`. Each entry links a branch to a filesystem path.
- **Stale worktree**: A worktree whose filesystem directory no longer exists
  but whose entry persists in the worktree registry.
- **Worktree prune**: The `git worktree prune` command that removes registry
  entries whose linked directories no longer exist.
- **Orphaned directory**: An empty directory under `.agent-fox/worktrees/`
  left behind after a failed or partial worktree cleanup.
- **Ensure-then-act**: A pattern where preconditions are verified before
  performing an action, rather than attempting the action and handling failure.

## Requirements

### Requirement 1: Post-Prune Verification

**User Story:** As an operator, I want worktree cleanup to verify that the git
registry is clean before attempting branch deletion, so that sessions do not
fail due to stale registry entries.

#### Acceptance Criteria

[80-REQ-1.1] WHEN `destroy_worktree` removes a worktree directory and prunes
the registry, THE system SHALL verify that the branch is no longer referenced
by any worktree entry before calling `delete_branch`, AND return successfully
once the branch is deleted.

[80-REQ-1.2] WHEN `create_worktree` removes a stale worktree directory and
prunes the registry, THE system SHALL verify that the branch is no longer
referenced by any worktree entry before calling `delete_branch`, AND proceed
to create the new worktree once the stale branch is deleted.

[80-REQ-1.3] THE verification function SHALL check whether a branch is
referenced by any worktree by parsing the output of `git worktree list
--porcelain` AND return `True` if the branch appears in any `branch` line,
`False` otherwise.

#### Edge Cases

[80-REQ-1.E1] IF post-prune verification shows the branch is still referenced
after the first prune, THEN THE system SHALL call `git worktree prune` once
more and re-verify. If still referenced after the second prune, THE system
SHALL log a warning and skip branch deletion rather than raising an error.

[80-REQ-1.E2] IF `git worktree list --porcelain` fails, THEN THE system SHALL
log a warning and proceed to attempt branch deletion (optimistic fallback).

### Requirement 2: Recoverable Branch Deletion

**User Story:** As an operator, I want branch deletion failures caused by stale
worktree references to be handled gracefully, so that a single stale entry does
not crash the session.

#### Acceptance Criteria

[80-REQ-2.1] WHEN `delete_branch` fails with an error containing "used by
worktree", THE system SHALL call `git worktree prune`, retry the deletion once,
AND return successfully if the retry succeeds.

[80-REQ-2.2] WHEN the retry after prune also fails, THE system SHALL log a
warning with the branch name and error details AND return without raising
(treat as non-fatal).

#### Edge Cases

[80-REQ-2.E1] IF `delete_branch` fails with both "used by worktree" AND the
worktree directory actually exists (not stale), THEN THE system SHALL raise
`WorkspaceError` (the branch is legitimately in use, not a stale reference).

### Requirement 3: Orphaned Directory Cleanup

**User Story:** As an operator, I want empty worktree directories cleaned up
automatically, so that they do not trigger stale-worktree detection on
subsequent runs.

#### Acceptance Criteria

[80-REQ-3.1] WHEN `destroy_worktree` completes, THE system SHALL remove empty
ancestor directories of the worktree path up to (but not including) the
`.agent-fox/worktrees/` root.

[80-REQ-3.2] WHEN `create_worktree` removes a stale worktree, THE system SHALL
remove empty ancestor directories of the stale path up to (but not including)
the `.agent-fox/worktrees/` root before proceeding with creation.

#### Edge Cases

[80-REQ-3.E1] IF an ancestor directory is not empty (contains other worktrees),
THEN THE system SHALL leave it in place.

[80-REQ-3.E2] IF directory removal fails (permissions, etc.), THEN THE system
SHALL log a warning and continue without raising.
