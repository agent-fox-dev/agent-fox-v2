# PRD: Robust Git Merging for Finished Task Groups

## Problem

When the engine runs multiple task groups in parallel, their harvest steps
(merging feature branches into `develop`) can execute concurrently. Git
operations are not atomic — two simultaneous `git checkout develop && git merge`
sequences race and corrupt the working tree. The same race exists between
separate `agent-fox run` processes targeting the same repository.

Additionally, the current fallback chain ends with `-X theirs` (blindly
preferring the feature branch), which can silently discard valid changes from
develop. When deterministic merge strategies fail, there is no intelligent
resolution — the system either discards work or marks the task as failed.

## Goals

1. **Merge lock**: Serialize all merge-into-develop operations so that only one
   harvest (or develop-remote sync) runs at a time, both within a single
   engine process and across concurrent `agent-fox` processes.

2. **Agent fallback**: When all deterministic merge strategies fail, spawn a
   dedicated "merge agent" that receives the conflict context and attempts an
   intelligent resolution. If the agent also fails, abort cleanly.

## Features

### 1. Merge Lock

- Introduce a file-based lock (`<repo>/.agent-fox/merge.lock`) that serializes
  access to merge operations on `develop`.
- The lock must work across asyncio tasks within one process AND across
  separate OS processes.
- Callers that cannot acquire the lock queue up and wait, with a configurable
  timeout (default: 5 minutes).
- Stale locks (from crashed processes) are detected via a timeout mechanism and
  automatically broken.
- The lock covers both harvest merge points: (a) merging a feature branch into
  develop, and (b) syncing local develop with origin/develop.

### 2. Agent Fallback for Merge Conflicts

- When all deterministic merge strategies (fast-forward, rebase + ff, merge
  commit) fail, instead of falling back to `-X theirs`, spawn a dedicated
  merge agent.
- The merge agent uses the `ADVANCED` model tier (currently `claude-opus-4-6`).
- The agent receives the git diff and/or conflict markers as context and is
  instructed to resolve merge conflicts only — no other changes.
- The agent operates in the worktree where the conflict occurred.
- If the agent succeeds, the merge is completed. If it fails, the harvest
  aborts and the task is marked as failed with a clear error message.
- The `-X theirs` fallback is removed and replaced entirely by the agent
  fallback.

## Clarifications

1. **Lock scope**: The lock must prevent concurrent merges both within a single
   `agent-fox` process (asyncio tasks) and across multiple `agent-fox`
   processes. This requires a file-based lock, not just an asyncio.Lock.
2. **Lock coverage**: The lock covers both the harvest step (git merge into
   develop) and the post-harvest integration (push to remote, PR creation).
3. **Stale lock timeout**: 5 minutes. If a lock file is older than 5 minutes,
   it is considered stale and can be broken.
4. **Queue behavior**: Callers wait with a timeout (default 5 minutes). If the
   lock cannot be acquired within the timeout, the operation fails.
5. **Merge agent**: A dedicated coding agent session instructed solely to
   resolve merge conflicts. Uses the ADVANCED model tier.
6. **Agent scope**: The merge agent resolves git merge conflicts only — no test
   fixes, no refactoring, no other changes.
7. **Agent failure**: If the merge agent fails, the harvest aborts and the task
   is marked failed.
8. **Conflict context**: The agent receives the git diff/conflict markers if
   available, but must also orient itself in the repository.
9. **Merge points covered**: Both (a) `harvest()` — feature branch into develop,
   and (b) `_sync_develop_with_remote()` — local develop with origin/develop.
10. **Replaces `-X theirs`**: The agent fallback replaces the current
    `-X theirs` strategy entirely.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 03_session_and_workspace | 5 | 2 | Uses harvest() and workspace git operations from group 5 where session lifecycle and harvest were implemented |
| 36_harvest_reconciliation | 2 | 2 | Modifies _sync_develop_with_remote() hardened in group 2; replaces -X ours fallback with agent fallback |
