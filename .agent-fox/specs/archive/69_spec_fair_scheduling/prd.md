# PRD: Spec-Fair Task Scheduling

## Problem

The task scheduler in `GraphSync.ready_tasks()` sorts ready tasks alphabetically
by node ID. Since node IDs are prefixed with the spec name (e.g.
`67_quality_gate_hunt_category:0`, `68_config_simplification:0`), this creates a
**starvation problem**: specs whose names sort later alphabetically never get
dispatched while earlier-sorted specs still have pending work.

In serial mode (`parallel=1`), `_dispatch_serial()` picks exactly one task per
iteration — the first in the sorted list — then breaks. A newly hot-loaded spec
(e.g. spec 68) can sit indefinitely with its root node ready while an
earlier-numbered spec (e.g. spec 67) works through its entire task chain.

In parallel mode, the bias is less severe (multiple tasks dispatch per round) but
still systematic: earlier-numbered specs consistently fill slots before
later-numbered specs get any.

This was observed in production: spec `68_config_simplification` was discovered
during a sync barrier and added to `plan.json` with its root node
(`68_config_simplification:0`) having no predecessors. Despite being fully
independent of spec 67 (no cross-spec edges), it was never scheduled because
spec 67's tasks always sorted first.

## Goal

Replace the alphabetical sort in `ready_tasks()` with a **spec-fair
round-robin** ordering that guarantees every spec with at least one ready task
gets representation in the output list before any spec gets a second entry.

## Design Decisions

1. **Interleave first, then duration.** Spec-fair round-robin is the primary
   ordering strategy. Within each spec's slot in the interleaved list, duration
   hints determine which of that spec's ready tasks gets priority.

2. **Round-robin applies to both serial and parallel modes.** The fix is in
   `ready_tasks()` itself, which is the single ordering function used by both
   dispatch paths. No dispatch-path-specific changes needed.

3. **Spec number ascending within each round.** When interleaving across specs,
   lower-numbered specs (created earlier) get slight priority within each round.
   This matches the intuition that older specs should finish first, while still
   guaranteeing every spec gets at least one slot per round.

4. **Backward compatible.** When only one spec has ready tasks, behavior is
   identical to today (alphabetical within-spec, or duration-ordered if hints
   are provided).

## Interleaving Algorithm

Given ready tasks from N specs:

1. **Group** ready tasks by spec name.
2. **Sort specs** by spec number ascending (extract numeric prefix from spec
   name).
3. **Within each spec group**, sort tasks by duration descending (if hints
   provided), otherwise alphabetically.
4. **Interleave** across spec groups round-robin: take the first task from
   spec 1, first task from spec 2, ..., first task from spec N, then second
   task from spec 1, second task from spec 2, etc.

Example with 3 specs, each having 2 ready tasks:
- Spec 65: `[65:3, 65:4]`
- Spec 67: `[67:2]`
- Spec 68: `[68:0, 68:1]`

Result: `[65:3, 67:2, 68:0, 65:4, 68:1]`

## Scope

### In Scope
- Modify `GraphSync.ready_tasks()` to use spec-fair round-robin ordering.
- Extract spec name from node IDs (format: `{spec_name}:{group}` or
  `{spec_name}:{group}:{role}`).
- Update existing tests that assert on alphabetical ordering.
- Add new tests for fairness properties.

### Out of Scope
- Changes to `_dispatch_serial()` or `_dispatch_parallel()` — the fix is
  entirely in the ordering function.
- Changes to duration hint computation or file conflict detection.
- Priority overrides or user-configurable scheduling policies.

## Affected Files

- `agent_fox/engine/graph_sync.py` — primary change in `ready_tasks()`
- `tests/unit/engine/test_sync.py` — update ordering assertions
- `tests/unit/engine/test_duration_ordering.py` — update ordering assertions
- `tests/property/engine/test_sync_props.py` — add fairness properties

## Clarifications

- **Node ID format:** Node IDs follow `{spec_name}:{group_number}` or
  `{spec_name}:{group_number}:{role}` (e.g. `67_quality_gate:1:auditor`).
  The spec name is everything before the first colon.
- **Spec number extraction:** The numeric prefix of the spec name (e.g. `67`
  from `67_quality_gate_hunt_category`) determines spec ordering within each
  round. Specs without numeric prefixes (if any) sort after all numbered specs.
- **Duration hints interaction:** Duration hints still influence ordering
  *within* each spec's slot, but do not override the spec-fair interleaving
  across specs. This means a very long task from spec 68 won't jump ahead of
  spec 65's slot in the round, but it will be chosen before shorter spec-68
  tasks within spec 68's slot.
