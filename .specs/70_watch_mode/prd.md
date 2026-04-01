# PRD: Watch Mode for the Code Command

## Summary

Add a `--watch` flag to `agent-fox code` that keeps the orchestrator running
after all current specs/tasks are completed, periodically polling for new specs
instead of terminating. This turns `agent-fox code` into a long-lived process
that picks up new work as it appears — without requiring a manual restart.

## Current Behavior

When the orchestrator finishes all tasks and no new work is found via
end-of-run discovery (spec 60), the run terminates with `RunStatus.COMPLETED`.
The user must manually re-invoke `agent-fox code` to process any specs that
appeared after termination.

End-of-run discovery (spec 60) already performs a single barrier check before
exiting. If that check finds no new specs, the run ends. There is no mechanism
to wait and retry.

## Expected Behavior

When `--watch` is passed to `agent-fox code`:

1. After all current tasks complete, instead of terminating, the orchestrator
   enters a **watch loop**.
2. The watch loop sleeps for `watch_interval` seconds (default: 60), then runs
   the full sync barrier sequence (reusing `run_sync_barrier_sequence()`),
   which includes develop sync, hot-load discovery, hooks, and knowledge
   ingestion.
3. After each barrier, `ready_tasks()` is re-checked.
4. If new tasks appeared, execution resumes normally (dispatch loop).
5. If no new tasks appeared, the watch loop repeats from step 2.
6. Each watch poll cycle emits a `WATCH_POLL` audit event so idle time is
   visible in audit logs.

The watch loop continues indefinitely until interrupted by SIGINT or stopped by
an existing circuit breaker (cost limit, session limit).

### Stall Behavior

Stalls (`RunStatus.STALLED`) still cause immediate termination, even in watch
mode. A stall means existing tasks are blocked with no progress possible — new
specs will not unblock them. Watch mode is for discovering **new** work, not
for resolving dependency deadlocks.

### Interaction with Existing Safeguards

- `--max-cost` and `--max-sessions` are honored during watch mode. When a limit
  is reached, the run terminates regardless of `--watch`.
- `--watch` does not require `--max-cost`. The user is responsible for setting
  cost limits if desired.
- SIGINT triggers graceful shutdown as today (first SIGINT = graceful, second =
  immediate).

### Exit Codes

Exit codes are unchanged from non-watch behavior. The run status that causes
termination determines the exit code:
- SIGINT -> 130
- Cost/session limit -> 3
- Stall -> 2
- Completed (only reachable if watch is later disabled via config hot-reload) -> 0

## Scope

- **CLI layer**: Add `--watch` boolean flag to the `code` command and
  `watch_interval` integer option.
- **Config layer**: Add `watch` (bool, default False) and `watch_interval`
  (int, default 60, minimum 10) to `OrchestratorConfig`.
- **Engine layer**: Modify the main loop's COMPLETED branch to enter a
  sleep-poll-barrier cycle when watch mode is enabled.
- **Audit layer**: Add `WATCH_POLL` to `AuditEventType` enum.
- **Config hot-reload**: `watch` and `watch_interval` are mutable fields that
  can be changed at runtime via config reload. Setting `watch` to `false` at
  runtime causes the next poll cycle to exit with COMPLETED.

## Clarifications

1. **Watch interval minimum**: Clamped to a minimum of 10 seconds to avoid
   excessive polling. Values below 10 are silently clamped.
2. **Stall in watch mode**: Terminates immediately (same as non-watch). New
   specs do not unblock stalled tasks.
3. **No watch timeout**: There is no maximum wall-clock time for watch mode.
   Use `--max-cost` or `--max-sessions` if a ceiling is needed.
4. **Cost limit responsibility**: `--watch` does not mandate `--max-cost`.
   The user is responsible for cost management.
5. **Audit trail**: Each watch poll cycle emits a `WATCH_POLL` audit event
   with payload containing the poll number and whether new tasks were found.
6. **Hot-load dependency**: Watch mode requires `hot_load=True` (the default).
   If `hot_load` is disabled, `--watch` logs a warning and behaves as if
   `--watch` was not set (no polling, immediate termination).
7. **CLI flag only**: `--watch` is a CLI flag, not a config-file field. The
   config file controls `watch_interval` only. This prevents accidental
   persistent watch mode.
8. **Config hot-reload of watch_interval**: The interval is re-read from
   config at each poll cycle, so changes take effect on the next iteration.

## Dependencies

No cross-spec dependencies. This spec builds on:
- Spec 60 (`end_of_run_discovery`): The existing `_try_end_of_run_discovery()`
  method and `run_sync_barrier_sequence()` are reused as-is.
- Spec 66 (`config_hot_reload`): `watch_interval` is a mutable config field
  updated during reload.

All referenced code is already implemented and stable.
