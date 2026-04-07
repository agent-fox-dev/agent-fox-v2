# PRD: Worktree Cleanup Hardening

## Problem

A race condition in the worktree lifecycle causes session failures when stale
worktree state is not fully cleaned up before branch deletion.

### Observed Failure

When a session starts and finds a stale worktree from a previous run:

1. `create_worktree()` detects the stale directory and calls
   `git worktree remove --force` (which may fail silently with `check=False`).
2. `shutil.rmtree()` removes the filesystem directory as a fallback.
3. `git worktree prune` is called to clean the git registry, also with
   `check=False`.
4. `delete_branch()` is called but **fails** with:
   `error: cannot delete branch 'feature/...' used by worktree at '...'`

The git worktree registry (`.git/worktrees/<name>`) retains a reference to
the now-deleted directory. `git worktree prune` should clean this, but either
it didn't fully execute or the registry state was inconsistent.

Additionally, `delete_branch()` doesn't recognize "used by worktree" as a
recoverable error — it only handles "not found" as a benign failure. This
causes a `WorkspaceError` that bubbles up as a session failure and triggers
retries, wasting time and API budget.

A secondary issue: failed worktree cleanups leave behind orphaned empty
directories (e.g., `.agent-fox/worktrees/62_remove_coordinator/`) that trigger
the same stale-worktree detection on subsequent runs.

### Root Causes

1. **No post-prune verification**: After `git worktree prune`, nothing verifies
   the worktree is actually deregistered before attempting branch deletion.
2. **`delete_branch` doesn't handle "used by worktree"**: The error handler
   only checks for "not found" / "error: branch" patterns, missing the "used
   by worktree" case.
3. **No orphaned directory cleanup**: Empty parent directories under
   `.agent-fox/worktrees/` accumulate after failed cleanups.

## Solution

1. **Ensure-then-act pattern**: After removing a worktree directory and pruning,
   verify the branch is no longer referenced by any worktree before attempting
   deletion. If it still is, force-prune again and retry once.
2. **Handle "used by worktree" in `delete_branch`**: Recognize this as a
   recoverable error — prune stale worktree entries and retry the deletion.
3. **Orphan cleanup**: After removing a worktree, clean up empty ancestor
   directories under `.agent-fox/worktrees/`.

## Clarifications

- **Retry strategy**: Ensure-then-act with a single retry-after-prune fallback.
  No infinite retry loops.
- **Orphan scope**: Clean empty parent directories up to (but not including)
  the `.agent-fox/worktrees/` root.
- **Concurrency**: Per-worktree isolation is sufficient. Different worktrees
  use different branches, so no additional locking is needed beyond the
  existing merge lock.
- **Prune check mode**: Keep `check=False` for `git worktree prune` but add
  post-prune verification that the specific branch is no longer referenced.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 03_session_and_workspace | 2 | 2 | Modifies `create_worktree` and `destroy_worktree` first implemented in group 2 |
