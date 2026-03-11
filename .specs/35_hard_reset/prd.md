# PRD: Hard Reset Command

## Summary

Add a `--hard` flag to the existing `reset` command that performs a
comprehensive state wipe — resetting ALL tasks regardless of current status,
cleaning up all worktrees and local feature branches, compacting the knowledge
base, and rolling back code on the `develop` branch to its pre-task state.

A partial variant (`reset --hard <task_id>`) rolls back to just before a
specific task, resetting only that task and everything committed after it.

## Context

The current `reset` command (`agent_fox/cli/reset.py`,
`agent_fox/engine/reset.py`) only resets tasks in `failed`, `blocked`, or
`in_progress` states. A `--hard` variant is needed for full or partial project
re-execution scenarios where you want to start from scratch (or from a specific
task) without re-running `init`.

## Proposed Behavior

### Full Hard Reset

```
agent-fox reset --hard [--yes]
```

- Reset ALL tasks to `pending` regardless of current status (including
  `completed`).
- Clean up ALL worktrees and local feature branches (including those from
  completed tasks). Remote branches are not touched.
- Compact the memory/knowledge base (dedup + supersession resolution).
- Roll back code on `develop` to the commit that existed before the first
  tracked task was committed. If no revision data is tracked (legacy projects),
  skip code rollback silently and only reset task states.
- Require `--yes` or interactive confirmation (destructive operation).
- Preserve `.agent-fox/config.toml` and `memory.jsonl` (memory is compacted,
  not deleted).
- Do NOT reset token/cost counters — costs are compounding.
- Do NOT clear session history — preserve the audit trail.

### Partial Hard Reset

```
agent-fox reset --hard <task_id> [--yes]
```

- Roll back code on `develop` to the commit before the specified task was
  committed.
- Reset the specified task and all tasks whose code was committed at or after
  that point to `pending`.
- Clean up worktrees and local feature branches for all affected tasks.
- Compact the memory/knowledge base.
- If no revision data is tracked for the target task, skip code rollback and
  only reset that single task's state (same behavior as regular
  `reset <task_id>` but also resets completed tasks).
- Require `--yes` or interactive confirmation.
- Same preservation rules as full hard reset.

### Git Revision Tracking

`SessionRecord` in `state.jsonl` does not currently track git revisions. To
support code rollback:

- Add a `commit_sha` field to `SessionRecord` that stores the `develop` HEAD
  SHA after the task's code is harvested/merged into develop.
- The SHA is captured in `_run_and_harvest()` right after a successful
  `harvest()` call, using `git rev-parse develop`.
- For sessions that fail or produce no code changes, `commit_sha` remains
  empty.
- No backward compatibility is needed — `reset --hard` simply skips code
  rollback for projects or tasks without tracked revisions.

## Relevant Files

- `agent_fox/cli/reset.py` — CLI entry point
- `agent_fox/engine/reset.py` — `reset_all()`, `reset_task()` logic
- `agent_fox/engine/state.py` — `ExecutionState`, `SessionRecord`
- `agent_fox/engine/session_lifecycle.py` — harvest phase (commit_sha capture)
- `agent_fox/memory/compaction.py` — `compact()` function
- `agent_fox/workspace/workspace.py` — worktree/branch management, `run_git()`
