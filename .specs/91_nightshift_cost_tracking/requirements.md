# Requirements Document

## Introduction

This specification addresses the gap where night-shift fix sessions and
auxiliary AI calls do not emit cost-bearing audit events, causing the `status`
command to under-report total API spend. The fix wires the standard audit
pipeline into night-shift operations so that all costs are visible in a
single dashboard.

## Glossary

- **SinkDispatcher**: Multiplexer that routes audit events and session outcomes
  to one or more `SessionSink` implementations (e.g. DuckDBSink).
- **run_id**: Unique identifier scoping a set of related audit events. In the
  orchestrator, one run_id covers an entire `run_code()` invocation. In
  night-shift, one run_id covers a single `FixPipeline.process_issue()` call.
- **session.complete / session.fail**: Audit event types emitted after a
  coding session finishes, carrying token counts and USD cost in their payload.
- **Auxiliary AI call**: A direct Anthropic API call (not going through
  `run_session()`) that incurs token costs. Examples: finding consolidation
  critic, batch triage, staleness check, quality gate analysis.
- **Archetype**: A role label assigned to a session or API call (e.g. `coder`,
  `triage`, `fix_coder`, `hunt_critic`). Used to group costs in the status
  report.

## Requirements

### Requirement 1: SinkDispatcher for NightShiftEngine

**User Story:** As an operator, I want night-shift to write audit events to
DuckDB, so that the status command can report night-shift costs.

#### Acceptance Criteria

1. [91-REQ-1.1] WHEN `NightShiftEngine` is constructed, THE system SHALL
   accept an optional `sink_dispatcher` parameter of type `SinkDispatcher`
   and store it for use in downstream operations.

2. [91-REQ-1.2] WHEN the `night-shift` CLI command starts, THE system SHALL
   create a `SinkDispatcher` backed by a `DuckDBSink` (using the standard
   knowledge store path) and pass it to `NightShiftEngine`.

3. [91-REQ-1.3] WHEN no `sink_dispatcher` is provided to `NightShiftEngine`,
   THE system SHALL continue to operate without emitting audit events
   (graceful degradation).

#### Edge Cases

1. [91-REQ-1.E1] IF the DuckDB database cannot be opened at night-shift
   startup, THEN THE system SHALL log a warning and proceed without a
   `SinkDispatcher` (no audit events emitted, but night-shift still runs).

### Requirement 2: Per-Fix run_id Generation

**User Story:** As an operator, I want each fix pipeline invocation to have
its own run_id, so that audit events are scoped per-fix and traceable.

#### Acceptance Criteria

1. [91-REQ-2.1] WHEN `FixPipeline.process_issue()` is called, THE system
   SHALL generate a unique `run_id` using `generate_run_id()` and use it for
   all audit events emitted during that invocation.

2. [91-REQ-2.2] WHEN `FixPipeline` is constructed, THE system SHALL accept
   an optional `sink_dispatcher` parameter and store it for audit emission.

#### Edge Cases

1. [91-REQ-2.E1] IF `sink_dispatcher` is None when `process_issue()` runs,
   THEN THE system SHALL skip all audit event emission without error.

### Requirement 3: Fix Session Audit Events

**User Story:** As an operator, I want each fix session (triage, coder,
reviewer) to emit `session.complete` or `session.fail` events with cost
data, so that the status command includes night-shift fix costs.

#### Acceptance Criteria

1. [91-REQ-3.1] WHEN a fix session completes successfully via `_run_session()`,
   THE system SHALL emit a `session.complete` audit event with payload
   containing `archetype`, `model_id`, `input_tokens`, `output_tokens`,
   `cache_read_input_tokens`, `cache_creation_input_tokens`, `cost`, and
   `duration_ms`, AND return the `SessionOutcome` to the caller.

2. [91-REQ-3.2] WHEN a fix session fails via `_run_session()`, THE system
   SHALL emit a `session.fail` audit event with payload containing
   `archetype`, `model_id`, `error_message`, and `attempt`.

3. [91-REQ-3.3] THE system SHALL pass `sink_dispatcher` and `run_id` to
   `run_session()` so that tool-level audit events (tool.invocation) are
   also emitted during fix sessions.

#### Edge Cases

1. [91-REQ-3.E1] IF the audit event emission fails (e.g. DuckDB write
   error), THEN THE system SHALL log a debug warning and continue without
   interrupting the fix pipeline.

### Requirement 4: Auxiliary AI Cost Tracking

**User Story:** As an operator, I want auxiliary AI calls (critic,
batch triage, staleness, quality gate) to emit cost-bearing audit events,
so that all night-shift API spend appears in the status report.

#### Acceptance Criteria

1. [91-REQ-4.1] WHEN the finding consolidation critic completes an API call,
   THE system SHALL emit a `session.complete` audit event with archetype
   `hunt_critic`, token counts, and calculated cost.

2. [91-REQ-4.2] WHEN the batch triage completes an API call, THE system
   SHALL emit a `session.complete` audit event with archetype `batch_triage`,
   token counts, and calculated cost.

3. [91-REQ-4.3] WHEN the staleness check completes an API call, THE system
   SHALL emit a `session.complete` audit event with archetype
   `staleness_check`, token counts, and calculated cost.

4. [91-REQ-4.4] WHEN the quality gate category completes an AI analysis call,
   THE system SHALL emit a `session.complete` audit event with archetype
   `quality_gate`, token counts, and calculated cost.

5. [91-REQ-4.5] WHEN an auxiliary AI call fails, THE system SHALL emit a
   `session.fail` audit event with the appropriate archetype and error
   message.

#### Edge Cases

1. [91-REQ-4.E1] IF no `sink_dispatcher` is available when an auxiliary AI
   call completes, THEN THE system SHALL skip audit emission without error.

### Requirement 5: Remove JSONL-Based Night-Shift Audit

**User Story:** As a maintainer, I want night-shift audit events routed
through the standard DuckDB pipeline, so that there is a single audit
mechanism.

#### Acceptance Criteria

1. [91-REQ-5.1] THE system SHALL remove the `nightshift/audit.py` module
   and all imports of its `emit_audit_event` function.

2. [91-REQ-5.2] WHEN night-shift operational events (e.g. `night_shift.fix_start`,
   `night_shift.hunt_scan_complete`) are emitted, THE system SHALL use the
   standard `engine/audit_helpers.emit_audit_event()` function with the
   shared `SinkDispatcher` and the current `run_id`.

3. [91-REQ-5.3] THE system SHALL update `NightShiftEngine` and `DaemonRunner`
   to use the standard audit helper instead of the removed JSONL module,
   AND pass `sink_dispatcher` and `run_id` to every call.

#### Edge Cases

1. [91-REQ-5.E1] IF `sink_dispatcher` is None, THEN THE standard
   `emit_audit_event()` SHALL return immediately without error (existing
   guard behaviour).

### Requirement 6: Status Command Displays Night-Shift Costs

**User Story:** As an operator, I want to see night-shift costs in the status
command output, distinguishable from regular coding session costs.

#### Acceptance Criteria

1. [91-REQ-6.1] WHEN the `status` command queries `session.complete` and
   `session.fail` events, THE system SHALL include events emitted by
   night-shift sessions (no query changes needed — these events already
   use the same event types and schema).

2. [91-REQ-6.2] THE system SHALL include night-shift session costs in
   `StatusReport.estimated_cost` (the grand total).

3. [91-REQ-6.3] THE system SHALL include night-shift session costs in
   `StatusReport.cost_by_archetype`, grouped by their archetype labels
   (`triage`, `fix_coder`, `fix_reviewer`, `hunt_critic`, `batch_triage`,
   `staleness_check`, `quality_gate`).
