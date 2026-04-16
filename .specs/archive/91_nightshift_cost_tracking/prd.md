# PRD: Night-Shift Cost Tracking in Status Command

**Source:** [GitHub Issue #331](https://github.com/agent-fox-dev/agent-fox/issues/331)

## Problem

Costs incurred by night-shift fix sessions are not included in the `status`
command output. The two systems use completely separate cost-tracking paths,
so `status` under-reports total API spend.

`FixPipeline._run_session()` calls `run_session()` without passing a
`sink_dispatcher` or `run_id`. The guard in `emit_audit_event()` short-circuits
when either is missing, so no `session.complete` audit events (which carry the
cost payload) are emitted. The `status` command only reads costs from these
audit events in DuckDB.

Night-shift does calculate and accumulate costs, but only in its own in-memory
`NightShiftState.total_cost`, which the status command never queries.

Additionally, auxiliary AI calls during hunt scans (quality gate analysis,
finding consolidation) and fix ordering (batch triage, staleness checks) incur
costs that are not tracked in the audit system at all.

## Goals

1. **Wire `sink_dispatcher` and `run_id` into night-shift's `run_session()`
   calls** so standard `session.complete` / `session.fail` audit events are
   emitted to DuckDB.
2. **Track auxiliary AI costs** (quality gate, finding consolidation, batch
   triage, staleness checks) via audit events so they appear in the status
   report.
3. **Show night-shift costs independently** from regular coding session costs
   in the status command, using the existing archetype-based breakdown
   (`triage`, `fix_coder`, `fix_reviewer` for fix sessions; new archetype
   labels for auxiliary calls).
4. **Remove the JSONL-based `nightshift/audit.py`** module and migrate all
   night-shift audit events to the standard DuckDB-backed audit pipeline.

## Non-Goals

- Changing the StatusReport data model or adding new top-level fields.
- Modifying the status command rendering logic (archetype names already
  provide the distinction).
- Writing night-shift session data to `state.jsonl` (DuckDB is sufficient).

## Clarifications

- **SinkDispatcher ownership:** `NightShiftEngine` creates its own
  `SinkDispatcher` with a DuckDB-backed sink, mirroring how the orchestrator
  sets one up in `engine/run.py`.
- **Run ID granularity:** Each `FixPipeline.process_issue()` invocation
  generates a fresh `run_id`, matching the orchestrator's per-run pattern.
- **Status rendering:** The existing `cost_by_archetype` breakdown in the
  status report naturally separates night-shift archetypes (`triage`,
  `fix_coder`, `fix_reviewer`) from regular archetypes (`coder`, `skeptic`,
  `verifier`). No structural changes needed.
- **Grand total:** Night-shift costs are included in `StatusReport.estimated_cost`.
- **state.jsonl:** Not updated; DuckDB audit events are the single source
  of truth for night-shift cost data.
- **Hunt scan costs:** Auxiliary AI calls (quality gate analysis, finding
  consolidation critic) are tracked via audit events with descriptive
  archetype labels.
- **JSONL audit removal:** The `nightshift/audit.py` module is removed.
  All night-shift operational events (`night_shift.fix_start`,
  `night_shift.hunt_scan_complete`, etc.) are emitted through the standard
  `engine/audit_helpers.emit_audit_event()` function using the shared
  `SinkDispatcher`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 61_night_shift | N/A (archived, fully implemented) | 1 | FixPipeline, NightShiftEngine, NightShiftState defined in spec 61 |
| 40_structured_audit_log | N/A (archived, fully implemented) | 1 | AuditEventType, emit_audit_event, DuckDBSink, SinkDispatcher defined in spec 40 |
