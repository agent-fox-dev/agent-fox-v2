# PRD: End-of-Run Spec Discovery

## Summary

When `agent-fox code` finishes all current tasks and the run would terminate
with COMPLETED status, the orchestrator should check for new specs that have
become ready since the run started. If new specs are found, they are hot-loaded
into the task graph and execution continues. If no new specs are found, the run
terminates as before.

This enables continuous autonomous operation: a separate process (or a human)
can push new specs to the develop branch while agent-fox is running, and the
orchestrator will pick them up without requiring a manual restart.

## Current Behavior

The orchestrator's main loop (`Orchestrator.run()` in `engine/engine.py`)
terminates when `_graph_sync.ready_tasks()` returns an empty list and no tasks
are pending or in-progress. The run status is set to `RunStatus.COMPLETED` and
execution stops.

Hot-loading of new specs currently only happens during sync barriers, which are
triggered every N completed tasks (controlled by `sync_interval`). If all tasks
complete between barriers, the orchestrator exits without checking for new work.

## Expected Behavior

When the orchestrator determines that all tasks are done (COMPLETED state):

1. Run the full sync barrier sequence (reusing `run_sync_barrier_sequence()`),
   which includes develop sync, worktree verification, hooks, and gated spec
   discovery.
2. After the barrier, re-check `ready_tasks()`.
3. If new tasks appeared (from hot-loaded specs), continue the main loop.
4. If no new tasks appeared, terminate with COMPLETED status as before.

This cycle repeats without limit — if new specs keep appearing, execution
continues indefinitely. This is intentional behavior.

## Scope

- Only the COMPLETED terminal state triggers end-of-run discovery. Other
  terminal states (STALLED, COST_LIMIT, SESSION_LIMIT, BLOCK_LIMIT,
  INTERRUPTED) terminate immediately as before.
- End-of-run discovery is gated on the existing `hot_load_enabled`
  configuration flag. No new configuration flag is needed.
- The sync barrier sequence is reused as-is — same checks (git-tracked,
  completeness, lint gates), same audit events, same hooks.

## Clarifications

1. **Full barrier vs. discovery-only**: The full `run_sync_barrier_sequence()`
   is run, not just the hot-load discovery step. This ensures develop is synced
   (pulling specs pushed by other processes) before checking for new work.
2. **Configuration**: Gated on existing `hot_load_enabled` flag. If hot-loading
   is disabled, end-of-run discovery is also disabled.
3. **No loop guard**: There is no cap on how many end-of-run discovery cycles
   can happen. Continuous operation is intentional.
4. **Terminal states**: Only COMPLETED triggers the check. STALLED runs have
   blocked tasks that new specs won't unblock.
5. **Audit trail**: Reuse the existing `SYNC_BARRIER` audit event type.

## Dependencies

No active cross-spec dependencies. This spec reuses
`run_sync_barrier_sequence()` and gated discovery from the fully-implemented
spec 51 (archived). The code is already in `engine/barrier.py` and
`engine/hot_load.py`.
