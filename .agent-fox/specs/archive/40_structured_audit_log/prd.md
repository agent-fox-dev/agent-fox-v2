# PRD: Structured Audit Log

> Source: [GitHub Issue #143](https://github.com/agent-fox-dev/agent-fox-v2/issues/143)

## Problem

Agent-fox orchestrates multi-session AI coding runs spanning dozens of sessions,
tool invocations, routing decisions, and knowledge operations. Today, the only
record of what happened lives in `state.jsonl` (checkpoint-oriented, not
event-oriented) and scattered log lines. There is no structured, queryable log
that captures the full timeline of significant agent actions within a run.

This makes it difficult to:

- Answer "what happened during run X?" without parsing ad-hoc logs.
- Audit routing escalations, session retries, and failure cascades.
- Build post-run reports beyond what `agent-fox status` provides.
- Debug production issues where the sequence of events matters.
- Compare cost and behavior across runs.

## Goals

1. **Structured event stream** -- every significant agent action emits a typed
   audit event with a consistent schema (id, timestamp, run_id, event_type,
   severity, payload).
2. **Dual-write persistence** -- events are written to both DuckDB (for
   querying) and JSONL files (for portability and debugging).
3. **Run-scoped identity** -- each orchestrator invocation gets a unique run ID
   (`{YYYYMMDD}_{HHMMSS}_{short_hex}`) that correlates all events.
4. **Queryable CLI** -- `agent-fox audit` provides filtering by run, event type,
   node, time range, and supports both human-readable and JSON output.
5. **Automatic retention** -- old audit logs are pruned to keep disk usage
   bounded (configurable, default 20 runs).
6. **Non-invasive integration** -- audit event emission uses the existing
   `SinkDispatcher` / `SessionSink` protocol, extended with a single new method.

## Scope

### In Scope

- `AuditEvent` data model with 20 event types covering session lifecycle,
  orchestrator control flow, routing decisions, tool invocations, harvest
  operations, and knowledge ingestion.
- DuckDB migration adding an `audit_events` table with indexes.
- `emit_audit_event()` method added to the `SessionSink` protocol.
- `DuckDBSink` extended to INSERT audit events.
- `AuditJsonlSink` -- new sink that appends JSON lines to
  `.agent-fox/audit/audit_{run_id}.jsonl`.
- Event emission wiring at all 20 emission points across engine, session
  lifecycle, routing, harvest, and knowledge modules.
- Run ID generation at orchestrator start.
- Log retention enforced at orchestrator start (configurable max runs).
- `agent-fox audit` CLI command with filtering options.
- Reporting migration: `status.py` and `standup.py` read from DuckDB audit
  events instead of parsing JSONL state files.

### Out of Scope

- Package consolidation (spec 39).
- Confidence normalization (spec 37).
- DuckDB hardening (spec 38).
- Duration ordering or predictive features.
- Real-time streaming of audit events (events are written synchronously).
- Remote/cloud audit log shipping or telemetry.
- Modification of the existing `ExecutionState` / `StateManager` checkpoint
  mechanism.

## Clarifications

1. **Run ID format** -- `{YYYYMMDD}_{HHMMSS}_{short_hex}` where short_hex is
   the first 6 characters of a UUID4 hex. Generated once per orchestrator
   `execute()` call.
2. **Event types are a closed enum** -- 20 variants at launch. Adding new types
   requires a spec update.
3. **Severity levels** -- `info`, `warning`, `error`, `critical`. Most events
   are `info`; `session.fail` is `error`; `run.limit_reached` is `warning`.
4. **Payload is typed** -- each event type has a defined set of payload fields.
   The payload is stored as JSON in DuckDB and in JSONL files.
5. **Sink failure isolation** -- audit event emission failures are logged and
   swallowed, consistent with existing `SinkDispatcher` behavior.
6. **Retention** -- default 20 runs. Retention is enforced at orchestrator
   start by deleting the oldest JSONL files and the corresponding DuckDB rows.
7. **Reporting migration** -- `status.py` and `standup.py` will read session
   metrics from DuckDB audit events rather than replaying `state.jsonl`. The
   `state.jsonl` checkpoint mechanism is unchanged.
8. **Spec 39 dependency** -- this spec assumes all knowledge code lives in
   `agent_fox/knowledge/`. Import paths reference that package.
