# Requirements Document

## Introduction

This specification defines a structured, append-only audit log that captures all
significant agent actions during an orchestration run. Events are dual-written
to DuckDB (for querying) and JSONL (for portability). A CLI command provides
filtered access to the log. Retention is configurable to bound disk usage.

## Glossary

- **AuditEvent**: A structured record of a significant agent action, identified
  by UUID, timestamped, and tagged with a run ID, event type, and severity.
- **Run ID**: A unique identifier for a single orchestrator invocation, formatted
  as `{YYYYMMDD}_{HHMMSS}_{short_hex}`.
- **Event type**: One of 20 string constants (e.g. `session.start`,
  `tool.invocation`, `run.complete`) identifying the category of action.
- **Severity**: One of `info`, `warning`, `error`, `critical`.
- **Payload**: A JSON-serializable dictionary of event-type-specific fields.
- **SinkDispatcher**: Existing fan-out mechanism that dispatches events to
  multiple `SessionSink` implementations.
- **SessionSink**: Protocol defining the interface for event consumers.
- **DuckDBSink**: Existing `SessionSink` implementation backed by DuckDB.
- **AuditJsonlSink**: New `SessionSink` implementation that writes audit events
  as JSON lines to `.agent-fox/audit/audit_{run_id}.jsonl`.
- **Retention**: The maximum number of runs whose audit data is kept. Older
  runs are pruned at orchestrator start.

## Requirements

### Requirement 1: AuditEvent Data Model

**User Story:** As a developer, I want a structured event model so that every
significant agent action is recorded with consistent metadata.

#### Acceptance Criteria

[40-REQ-1.1] THE system SHALL define an `AuditEvent` dataclass with fields:
`id` (UUID), `timestamp` (datetime), `run_id` (str), `event_type` (str),
`node_id` (str, optional), `session_id` (str, optional), `archetype` (str,
optional), `severity` (str), and `payload` (dict).

[40-REQ-1.2] THE system SHALL define an `AuditEventType` enum with exactly 20
variants: `run.start`, `run.complete`, `run.limit_reached`, `session.start`,
`session.complete`, `session.fail`, `session.retry`, `task.status_change`,
`model.escalation`, `model.assessment`, `tool.invocation`, `tool.error`,
`git.merge`, `git.conflict`, `harvest.complete`, `fact.extracted`,
`fact.compacted`, `knowledge.ingested`, `sync.barrier`.

[40-REQ-1.3] THE system SHALL define an `AuditSeverity` enum with exactly 4
values: `info`, `warning`, `error`, `critical`.

[40-REQ-1.4] WHEN an `AuditEvent` is created, THE system SHALL auto-populate
the `id` field with a new UUID4 and the `timestamp` field with the current
UTC time.

#### Edge Cases

[40-REQ-1.E1] IF `node_id`, `session_id`, or `archetype` are not applicable
for a given event type, THEN THE system SHALL store them as empty strings.

### Requirement 2: Run ID Generation

**User Story:** As a developer, I want each orchestrator invocation to have a
unique run ID so that I can correlate all events from the same run.

#### Acceptance Criteria

[40-REQ-2.1] THE system SHALL generate a run ID at the start of each
orchestrator `execute()` call, formatted as `{YYYYMMDD}_{HHMMSS}_{short_hex}`
where short_hex is the first 6 characters of a UUID4 hex string.

[40-REQ-2.2] THE system SHALL use the same run ID for all audit events emitted
during that orchestrator invocation.

#### Edge Cases

[40-REQ-2.E1] IF two orchestrator invocations start within the same second,
THEN their run IDs SHALL differ due to the random hex suffix.

### Requirement 3: DuckDB Migration

**User Story:** As a developer, I want audit events stored in DuckDB so that
I can query them efficiently.

#### Acceptance Criteria

[40-REQ-3.1] THE system SHALL add a migration (v6) creating an `audit_events`
table with columns: `id` (VARCHAR PRIMARY KEY), `timestamp` (TIMESTAMP NOT
NULL), `run_id` (VARCHAR NOT NULL), `event_type` (VARCHAR NOT NULL), `node_id`
(VARCHAR), `session_id` (VARCHAR), `archetype` (VARCHAR), `severity` (VARCHAR
NOT NULL), `payload` (JSON NOT NULL).

[40-REQ-3.2] THE migration SHALL create indexes on `run_id` and `event_type`
for efficient filtering.

[40-REQ-3.3] THE migration SHALL be registered in the `MIGRATIONS` list in
`agent_fox/knowledge/migrations.py`.

### Requirement 4: SessionSink Protocol Extension

**User Story:** As a developer, I want the sink protocol to support audit
events so that all sink implementations can receive them.

#### Acceptance Criteria

[40-REQ-4.1] THE `SessionSink` protocol SHALL include an `emit_audit_event`
method accepting an `AuditEvent` parameter and returning `None`.

[40-REQ-4.2] THE `SinkDispatcher` SHALL dispatch `emit_audit_event` calls to
all registered sinks, logging and swallowing individual failures.

#### Edge Cases

[40-REQ-4.E1] IF a sink implementation does not implement `emit_audit_event`,
THEN THE `SinkDispatcher` SHALL log a warning and continue dispatching to
other sinks.

### Requirement 5: DuckDBSink Extension

**User Story:** As a developer, I want audit events persisted in DuckDB so
that they can be queried by the CLI and reporting modules.

#### Acceptance Criteria

[40-REQ-5.1] THE `DuckDBSink` SHALL implement `emit_audit_event` by inserting
a row into the `audit_events` table.

[40-REQ-5.2] THE `DuckDBSink` SHALL serialize the `payload` dict as JSON for
the `payload` column.

### Requirement 6: AuditJsonlSink

**User Story:** As a developer, I want audit events written to portable JSONL
files so that I can inspect them without DuckDB.

#### Acceptance Criteria

[40-REQ-6.1] THE system SHALL provide an `AuditJsonlSink` class implementing
`SessionSink` that appends audit events as JSON lines to
`.agent-fox/audit/audit_{run_id}.jsonl`.

[40-REQ-6.2] THE `AuditJsonlSink` SHALL create the `.agent-fox/audit/`
directory if it does not exist.

[40-REQ-6.3] EACH JSON line SHALL contain all `AuditEvent` fields with
`id` serialized as string, `timestamp` as ISO-8601, and `payload` as a
nested JSON object.

[40-REQ-6.4] THE `AuditJsonlSink` SHALL implement all other `SessionSink`
methods as no-ops (session outcomes, tool calls, tool errors are handled by
existing sinks).

#### Edge Cases

[40-REQ-6.E1] IF the JSONL file write fails (e.g. disk full), THEN THE
`AuditJsonlSink` SHALL log a warning and not raise an exception.

### Requirement 7: Session Lifecycle Events

**User Story:** As a developer, I want session start, completion, and failure
recorded as audit events so that I can trace session lifecycles.

#### Acceptance Criteria

[40-REQ-7.1] WHEN a session starts, THE system SHALL emit a `session.start`
event with payload fields: `archetype`, `model_id`, `prompt_template`,
`attempt`.

[40-REQ-7.2] WHEN a session completes successfully, THE system SHALL emit a
`session.complete` event with payload fields: `archetype`, `model_id`,
`prompt_template`, `tokens`, `cost`, `duration_ms`, `files_touched`.

[40-REQ-7.3] WHEN a session fails, THE system SHALL emit a `session.fail`
event with severity `error` and payload fields: `archetype`, `model_id`,
`prompt_template`, `error_message`, `attempt`.

[40-REQ-7.4] WHEN a session is retried, THE system SHALL emit a
`session.retry` event with payload fields: `attempt`, `reason`.

### Requirement 8: Tool Events

**User Story:** As a developer, I want tool invocations and errors recorded so
that I can audit tool usage patterns.

#### Acceptance Criteria

[40-REQ-8.1] WHEN a tool is invoked, THE system SHALL emit a `tool.invocation`
event with payload fields: `tool_name`, `param_summary`, `called_at`.

[40-REQ-8.2] THE `param_summary` field SHALL be generated using the existing
`abbreviate_arg` function to avoid logging sensitive or large parameters.

[40-REQ-8.3] WHEN a tool invocation fails, THE system SHALL emit a `tool.error`
event with payload fields: `tool_name`, `param_summary`, `failed_at`.

### Requirement 9: Orchestrator Events

**User Story:** As a developer, I want orchestrator lifecycle events recorded
so that I can see run boundaries, limits, and task transitions.

#### Acceptance Criteria

[40-REQ-9.1] WHEN the orchestrator starts, THE system SHALL emit a `run.start`
event with payload fields: `plan_hash`, `total_nodes`, `parallel`.

[40-REQ-9.2] WHEN the orchestrator completes, THE system SHALL emit a
`run.complete` event with payload fields: `total_sessions`, `total_cost`,
`duration_ms`, `run_status`.

[40-REQ-9.3] WHEN a resource limit is reached, THE system SHALL emit a
`run.limit_reached` event with severity `warning` and payload fields:
`limit_type`, `limit_value`.

[40-REQ-9.4] WHEN a task changes status, THE system SHALL emit a
`task.status_change` event with payload fields: `from_status`, `to_status`,
`reason`.

[40-REQ-9.5] WHEN parallel tasks reach a sync barrier, THE system SHALL emit
a `sync.barrier` event with payload fields: `completed_nodes`,
`pending_nodes`.

### Requirement 10: Routing Events

**User Story:** As a developer, I want model routing decisions recorded so
that I can audit escalation patterns and assessment accuracy.

#### Acceptance Criteria

[40-REQ-10.1] WHEN a model escalation occurs, THE system SHALL emit a
`model.escalation` event with payload fields: `from_tier`, `to_tier`,
`reason`.

[40-REQ-10.2] WHEN a model assessment is made, THE system SHALL emit a
`model.assessment` event with payload fields: `predicted_tier`, `confidence`,
`method`.

### Requirement 11: Harvest and Knowledge Events

**User Story:** As a developer, I want git, harvest, and knowledge operations
recorded so that I can trace the flow of code and facts.

#### Acceptance Criteria

[40-REQ-11.1] WHEN code is merged from a worktree, THE system SHALL emit a
`git.merge` event with payload fields: `branch`, `commit_sha`,
`files_touched`.

[40-REQ-11.2] WHEN a git conflict occurs during merge, THE system SHALL emit
a `git.conflict` event with severity `warning` and payload fields: `branch`,
`strategy`, `error`.

[40-REQ-11.3] WHEN a harvest operation completes, THE system SHALL emit a
`harvest.complete` event with payload fields: `commit_sha`,
`facts_extracted`, `findings_persisted`.

[40-REQ-11.4] WHEN facts are extracted during knowledge harvest, THE system
SHALL emit a `fact.extracted` event with payload fields: `fact_count`,
`categories`.

[40-REQ-11.5] WHEN facts are compacted, THE system SHALL emit a
`fact.compacted` event with payload fields: `facts_before`, `facts_after`,
`superseded_count`.

[40-REQ-11.6] WHEN knowledge is ingested via KnowledgeIngestor, THE system
SHALL emit a `knowledge.ingested` event with payload fields: `source_type`,
`source_path`, `item_count`.

### Requirement 12: Log Retention

**User Story:** As a developer, I want old audit logs automatically pruned so
that disk usage stays bounded.

#### Acceptance Criteria

[40-REQ-12.1] THE system SHALL support a configurable `audit_retention_runs`
setting (default: 20) specifying the maximum number of runs to retain.

[40-REQ-12.2] WHEN the orchestrator starts, THE system SHALL delete JSONL
audit files and corresponding DuckDB rows for runs older than the retention
limit, ordered by timestamp.

#### Edge Cases

[40-REQ-12.E1] IF there are fewer runs than the retention limit, THEN THE
system SHALL not delete any data.

[40-REQ-12.E2] IF JSONL file deletion fails, THEN THE system SHALL log a
warning and continue with DuckDB cleanup.

### Requirement 13: CLI Command

**User Story:** As a developer, I want a CLI command to query audit events so
that I can inspect run history without manual file parsing.

#### Acceptance Criteria

[40-REQ-13.1] THE system SHALL provide an `agent-fox audit` CLI command.

[40-REQ-13.2] THE `audit` command SHALL support a `--list-runs` flag that
lists all available run IDs with their timestamps and event counts.

[40-REQ-13.3] THE `audit` command SHALL support a `--run` option to filter
events by run ID.

[40-REQ-13.4] THE `audit` command SHALL support an `--event-type` option to
filter events by event type.

[40-REQ-13.5] THE `audit` command SHALL support a `--node-id` option to filter
events by node ID.

[40-REQ-13.6] THE `audit` command SHALL support a `--since` option accepting
an ISO-8601 datetime or relative duration (e.g. `24h`, `7d`) to filter events
by timestamp.

[40-REQ-13.7] THE `audit` command SHALL support the global `--json` flag for
structured JSON output.

#### Edge Cases

[40-REQ-13.E1] IF no events match the filter criteria, THEN THE command SHALL
display an empty result set and exit with code 0.

[40-REQ-13.E2] IF the DuckDB database does not exist or the `audit_events`
table is missing, THEN THE command SHALL display a message indicating no audit
data is available and exit with code 0.

### Requirement 14: Reporting Migration

**User Story:** As a developer, I want status and standup reports to read from
DuckDB audit events so that reporting is consistent with the audit log.

#### Acceptance Criteria

[40-REQ-14.1] THE `status.py` reporting module SHALL read session metrics
(token counts, costs, durations) from the DuckDB `audit_events` table
instead of parsing `state.jsonl` session history.

[40-REQ-14.2] THE `standup.py` reporting module SHALL read recent session
activity from the DuckDB `audit_events` table instead of parsing JSONL files.

[40-REQ-14.3] WHEN the DuckDB database is unavailable, THE reporting modules
SHALL fall back to the existing `state.jsonl` parsing behavior.
