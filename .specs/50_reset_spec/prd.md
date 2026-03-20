# PRD: Spec-Scoped Reset Command

## Summary

Add a `--spec <spec_name>` option to the `reset` command that performs a
hard-reset scoped to a single specification. All tasks belonging to the named
spec (coder and archetype nodes) are reset to `pending`, their worktrees and
local branches are cleaned up, and `tasks.md` checkboxes and `plan.json`
statuses are synchronized — without affecting any other spec's state.

## Context

The current `reset` command supports two modes:

- **Soft reset** (`reset` / `reset <task_id>`): resets only `failed`, `blocked`,
  or `in_progress` tasks.
- **Hard reset** (`reset --hard`): resets ALL tasks, rolls back code on
  `develop`, and compacts the knowledge base.

Neither mode supports resetting a single spec while leaving others intact. When
a spec's tasks are blocked or need re-execution (e.g., after API failures
exhausted retries), the user must either reset every task individually or nuke
the entire project with `--hard`. A spec-scoped reset fills this gap.

## Proposed Behavior

```
agent-fox reset --spec <spec_name> [--yes]
```

- Identify all nodes belonging to `<spec_name>` in the plan (coder nodes AND
  archetype nodes: skeptic, auditor, verifier, oracle).
- Reset all identified nodes to `pending` in `state.jsonl`.
- Clean up worktrees and local feature branches for all identified nodes.
- Reset `tasks.md` checkboxes for all task groups in the spec.
- Reset `plan.json` statuses for all identified nodes.
- Require `--yes` or interactive confirmation (destructive operation).
- **No git rollback** on `develop`. Commits from different specs may be
  interleaved on `develop`, making a safe rollback impossible without
  potentially undoing other specs' work.
- **No knowledge compaction**. Knowledge compaction is a global operation and
  not appropriate for a spec-scoped reset.
- **Preserve** session history, token/cost counters, and config (same as
  `--hard`).

## Mutual Exclusivity

`--spec` is mutually exclusive with:

- `--hard` (project-wide hard reset)
- Positional `<task_id>` argument (single-task reset)

If combined, the command exits with a clear error message.

## Error Cases

- Unknown spec name: error with list of valid spec names from the plan.
- No plan file: error telling user to run `agent-fox plan` first.
- No state file: error (same as existing reset behavior).
- Spec has no tasks in the plan: warning, no-op.

## Relevant Files

- `agent_fox/cli/reset.py` — CLI entry point (add `--spec` option)
- `agent_fox/engine/reset.py` — new `reset_spec()` function
- `agent_fox/engine/state.py` — `ExecutionState`, `StateManager`
- `agent_fox/graph/persistence.py` — `load_plan()` for node lookup
- `agent_fox/workspace/git.py` — branch cleanup

## Dependencies

This spec has no cross-spec dependencies. It extends existing reset
infrastructure from specs 07 and 35.

## Clarifications

1. **Code rollback is intentionally skipped.** Commits from different specs are
   interleaved on `develop`. A safe per-spec rollback is not feasible without
   risking other specs' work.
2. **Knowledge compaction is skipped.** It is a global operation; per-spec
   scoping of knowledge facts is not currently supported.
3. **All node types are reset.** Both coder and archetype nodes (skeptic,
   auditor, verifier, oracle) belonging to the spec are reset to `pending`.
4. **Cascade unblocking is not performed.** This is a full spec reset — all
   nodes go to `pending` regardless of dependencies.
