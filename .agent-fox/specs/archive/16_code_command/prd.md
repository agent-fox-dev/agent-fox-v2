# PRD: `agent-fox code` CLI Command

## Problem

The orchestrator engine (spec 04) is fully implemented but has no CLI entry
point. Users cannot run `agent-fox code` despite it being documented as the
primary workflow command throughout the README, PRD, and supporting
specifications. This spec bridges that gap by creating the Click CLI wrapper
that wires the orchestrator engine to user-facing options.

## Scope

A single CLI command (`agent-fox code`) that:

1. Reads configuration from `.agent-fox/config.toml` (already loaded by the
   Click group in `app.py`).
2. Validates that a plan exists (`.agent-fox/plan.json`).
3. Constructs the `Orchestrator` with the appropriate config, paths, and
   session runner factory.
4. Runs `await orchestrator.run()` via `asyncio.run()`.
5. Prints a compact summary on completion (tasks done, tokens, cost, status).
6. Exits with an appropriate exit code.

## CLI Interface

```
agent-fox code [OPTIONS]

Options:
  --parallel N     Override parallelism (1-8, default: from config)
  --no-hooks       Skip all hook scripts for this run
  --max-cost N     Override cost ceiling in USD
  --max-sessions N Override session count limit
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | All tasks completed successfully |
| 1    | Execution error (missing plan, config error) |
| 2    | Execution stalled (tasks blocked, no progress possible) |
| 3    | Cost or session limit reached (partial completion) |
| 130  | Interrupted by SIGINT (state saved, resumable) |

## Completion Summary

On completion, print a compact summary in the same style as `agent-fox status`:

```
Tasks: 12/14 done | 0 in progress | 0 pending | 2 failed
Tokens: 1.5M in / 2.8M out | $62.13
Status: completed
```

## Out of Scope

- The orchestrator engine itself (spec 04 — already implemented).
- The session runner (spec 03 — already implemented).
- Hook execution logic (spec 06 — already implemented; this spec only wires
  the `--no-hooks` flag).
- Workspace management (spec 03).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 3 | 1 | CLI registration pattern, config loading |
| 04_orchestrator | 6 | 1 | Orchestrator engine, all modules |
| 03_session_and_workspace | 4 | 1 | Session runner factory |
