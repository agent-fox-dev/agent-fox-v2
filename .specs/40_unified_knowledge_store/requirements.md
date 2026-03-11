# Requirements Document

## Introduction

This spec unifies the `agent_fox/memory/` and `agent_fox/knowledge/` packages
into a single `knowledge/` package, makes DuckDB the primary persistence layer,
introduces a structured audit log with typed event schemas and immediate
dual-write to DuckDB and per-run JSONL files, preserves the existing execution
state checkpoint mechanism, extends the sink architecture to handle audit
events, and adds a CLI `agent-fox audit` command for querying the audit trail.

## Glossary

- **Fact**: A unit of knowledge extracted from a session transcript, stored with
  category, confidence, spec association, and optional causal links.
- **Audit event**: A typed, timestamped record of a significant action during an
  orchestrator run (session lifecycle, status changes, git operations, knowledge
  pipeline activity, etc.).
- **Flush point**: A defined moment when in-memory facts and findings are
  persisted to DuckDB. Occurs at end of task group, sync barriers, and session
  end. Audit events are NOT subject to flush points -- they are written
  immediately.
- **Dual-write**: The pattern where every audit event is written to both the
  per-run JSONL log file and the DuckDB `audit_events` table. This is
  best-effort, not transactionally atomic -- either side may fail independently.
- **Orchestrator run**: A single invocation of `agent-fox code` that processes
  one or more task groups from a plan.
- **State machine**: The in-memory buffer for facts and findings during an
  orchestrator run, flushed to DuckDB at defined flush points.
- **Execution state checkpoint**: The existing `ExecutionState` / `StateManager`
  mechanism that persists node statuses, session history, and aggregate metrics
  after every session. Separate from the audit log.
- **JSONL export**: A line-delimited JSON file derived from DuckDB data, used
  for git-tracking and portability (`memory.jsonl`).
- **Run ID**: A unique identifier for an orchestrator run, formatted as
  `{YYYYMMDD}_{HHMMSS}_{short_hex}` where `short_hex` is the first 8
  characters of a UUID4 hex. Used to scope audit queries and name log files.
- **Severity**: An enum classifying the operational significance of an audit
  event: `info`, `warning`, `error`, or `critical`.

## Requirements

### Requirement 1: Package Consolidation

**User Story:** As a developer, I want a single package for all persistent
knowledge so that import paths are consistent and the architecture is clear.

#### Acceptance Criteria

[40-REQ-1.1] WHEN the codebase is loaded, THE system SHALL provide all fact
storage, extraction, compaction, filtering, rendering, embedding, search, and
query functionality from the `agent_fox.knowledge` package.

[40-REQ-1.2] WHEN the codebase is loaded, THE system SHALL NOT contain an
`agent_fox.memory` package or any imports from `agent_fox.memory`.

[40-REQ-1.3] THE system SHALL preserve all public APIs previously exported by
`agent_fox.memory` (Fact, Category, parse_confidence, append_facts,
load_all_facts, load_facts_by_spec, write_facts, MemoryStore, MemoryStore.write_fact,
MemoryStore.sync_to_duckdb, extract_facts, compact, select_relevant_facts,
render_summary) as importable names from `agent_fox.knowledge` submodules.

#### Edge Cases

[40-REQ-1.E1] IF a third-party tool or script imports from `agent_fox.memory`,
THEN THE system SHALL fail with a clear ImportError (no silent fallback).

### Requirement 2: In-Memory State Machine (Facts and Findings)

**User Story:** As the orchestrator, I want to batch fact and finding mutations
in memory and flush at defined points so that DuckDB I/O is minimized while
preserving crash resilience for audit events and execution state.

#### Acceptance Criteria

[40-REQ-2.1] WHEN an orchestrator run starts, THE system SHALL load existing
facts from DuckDB into an in-memory state machine scoped to that run.

[40-REQ-2.2] WHILE an orchestrator run is active, THE system SHALL accumulate
new facts and findings in memory without writing them to DuckDB until a flush
point is reached.

[40-REQ-2.3] WHEN a flush point is reached (end of task group, sync barrier, or
session end), THE system SHALL persist all accumulated in-memory facts and
findings to DuckDB in a single transaction.

[40-REQ-2.4] WHEN a flush completes, THE system SHALL export the current fact
set to `memory.jsonl` at the same points where the JSONL file would currently
be written.

[40-REQ-2.5] THE system SHALL NOT buffer audit events in the state machine.
Audit events SHALL be written immediately on emission per Requirement 5.

[40-REQ-2.6] THE system SHALL NOT alter the existing `ExecutionState` /
`StateManager` per-session checkpoint mechanism. Execution state SHALL continue
to be persisted after every session as it is today.

#### Edge Cases

[40-REQ-2.E1] IF DuckDB write fails during a flush, THEN THE system SHALL log
the error, retain the in-memory state, and retry on the next flush point.

[40-REQ-2.E2] IF the orchestrator terminates abnormally (crash, SIGKILL), THEN
THE system SHALL recover on next startup by loading the last successfully
flushed facts from DuckDB and the last execution state checkpoint.

### Requirement 3: DuckDB Primary Fact Persistence

**User Story:** As the system, I want DuckDB to be the single source of truth
for facts so that all queries go through one store.

#### Acceptance Criteria

[40-REQ-3.1] WHEN facts are persisted, THE system SHALL write them to the
`memory_facts` DuckDB table as the primary store.

[40-REQ-3.2] WHEN facts are loaded for session context, filtering, or
rendering, THE system SHALL read them from DuckDB (not from JSONL).

[40-REQ-3.3] WHEN `memory.jsonl` is exported, THE system SHALL derive its
content from the `memory_facts` table so that the JSONL file is a
reproducible projection of the database.

#### Edge Cases

[40-REQ-3.E1] IF the DuckDB file is missing or corrupt on startup, THEN THE
system SHALL create a fresh database, apply all migrations, and log a warning
that historical data is unavailable.

### Requirement 4: Structured Audit Events

**User Story:** As an operator, I want every significant agent action recorded
as a typed event so that I can trace what happened, when, and why.

#### Acceptance Criteria

[40-REQ-4.1] THE system SHALL define a typed `AuditEvent` data model with
fields: `id` (UUID), `timestamp` (ISO-8601), `run_id` (str), `event_type`
(enum), `node_id` (optional str), `session_id` (optional str), `archetype`
(optional str), `severity` (enum: info | warning | error | critical), and
`payload` (typed dict per event_type).

[40-REQ-4.2] THE system SHALL define the `run_id` as a string formatted
`{YYYYMMDD}_{HHMMSS}_{short_hex}` where `short_hex` is the first 8 characters
of a UUID4 hex, generated once at the start of each orchestrator run.

[40-REQ-4.3] WHEN a session starts, completes, fails, or is retried, THE
system SHALL emit the corresponding `session.*` audit event with the fields
specified in the event type table, including `archetype`, `model_id`, and
`prompt_template`.

[40-REQ-4.4] WHEN a task status changes, a model is escalated, an assessment
completes, a sync barrier is reached, or a git operation occurs, THE system
SHALL emit the corresponding audit event.

[40-REQ-4.5] WHEN an orchestrator run starts or completes, THE system SHALL
emit `run.start` and `run.complete` events with aggregate metrics.

[40-REQ-4.6] WHEN an orchestrator run terminates due to a cost limit, session
limit, or stall condition, THE system SHALL emit a `run.limit_reached` event
before the `run.complete` event.

[40-REQ-4.7] WHEN facts are extracted from a session transcript, THE system
SHALL emit a `fact.extracted` event with the count and category breakdown.

[40-REQ-4.8] WHEN fact compaction runs, THE system SHALL emit a
`fact.compacted` event with before/after counts and superseded count.

[40-REQ-4.9] WHEN the harvest phase completes for a session, THE system SHALL
emit a `harvest.complete` event with the commit SHA, facts extracted count, and
findings persisted count.

[40-REQ-4.10] WHEN `KnowledgeIngestor` ingests ADRs, git commits, or errata,
THE system SHALL emit a `knowledge.ingested` event with the source type, path,
and item count.

#### Edge Cases

[40-REQ-4.E1] IF event emission fails (e.g. serialization error), THEN THE
system SHALL log the failure and continue without blocking the orchestrator.

### Requirement 11: Enriched Tool Call Records

**User Story:** As an operator, I want each tool invocation recorded with a
parameter summary so that I can reconstruct what an agent did during a session
without parsing raw transcripts.

#### Acceptance Criteria

[40-REQ-11.1] WHEN an agent invokes a tool during a session, THE system SHALL
emit a `tool.invocation` audit event with fields: `session_id`, `node_id`,
`tool_name`, `param_summary`, and `called_at`.

[40-REQ-11.2] WHEN the tool input contains a file path argument, THE system
SHALL set `param_summary` to a shortened file path (basename, or last two path
components with `…/` prefix when the full path exceeds 120 characters).

[40-REQ-11.3] WHEN the tool input does not contain a file path but contains a
string argument, THE system SHALL set `param_summary` to the first string
argument abbreviated to at most 120 characters.

[40-REQ-11.4] WHEN the tool input contains no string arguments, THE system
SHALL set `param_summary` to `None`.

[40-REQ-11.5] WHEN an agent tool invocation fails, THE system SHALL emit a
`tool.error` audit event with the same fields as `tool.invocation`.

[40-REQ-11.6] THE `tool.invocation` and `tool.error` events SHALL be emitted
unconditionally (not gated behind a debug flag). The legacy `tool_calls` and
`tool_errors` DuckDB tables SHALL be retained but deprecated.

[40-REQ-11.7] THE system SHALL reuse the existing `abbreviate_arg()` helper
from `agent_fox.ui.events` for deriving the `param_summary`.

#### Edge Cases

[40-REQ-11.E1] IF `param_summary` derivation raises an exception, THEN THE
system SHALL set `param_summary` to `None` and emit the event without the
summary.

### Requirement 12: Model Interaction Records

**User Story:** As an operator, I want to know which archetype called which
model and with which prompt template so that I can analyze model usage patterns,
costs per archetype, and debug prompt-related issues.

#### Acceptance Criteria

[40-REQ-12.1] WHEN a `session.start` event is emitted, THE system SHALL include
`archetype` (e.g. `coder`, `skeptic`, `verifier`, `oracle`), `model_id` (the
resolved model identifier, not the tier name), and `prompt_template` (the
filename of the prompt template, e.g. `coding.md`, `skeptic.md`).

[40-REQ-12.2] WHEN a `session.complete` event is emitted, THE system SHALL
include the same `archetype`, `model_id`, and `prompt_template` fields
alongside the existing token, cost, and duration fields.

[40-REQ-12.3] WHEN a `session.fail` event is emitted, THE system SHALL include
the same `archetype`, `model_id`, and `prompt_template` fields alongside the
error message.

[40-REQ-12.4] THE `prompt_template` field SHALL contain only the template
filename (e.g. `coding.md`), NOT the full resolved system prompt text.

[40-REQ-12.5] THE system SHALL NOT persist the full system prompt or task prompt
text in the audit log. Token counts on `session.complete` events are sufficient
for size tracking.

#### Edge Cases

[40-REQ-12.E1] IF the archetype does not map to a known prompt template, THEN
THE system SHALL set `prompt_template` to `"unknown"`.

### Requirement 5: Audit Event Persistence

**User Story:** As an operator, I want audit events persisted immediately to
both JSONL and DuckDB so that I have a crash-resilient, portable log file and
a queryable database.

#### Acceptance Criteria

[40-REQ-5.1] WHEN an audit event is emitted, THE system SHALL immediately
append it as a single JSON line to the run's JSONL log file AND insert it into
the DuckDB `audit_events` table. Events SHALL NOT be buffered or deferred.

[40-REQ-5.2] THE system SHALL create one JSONL log file per orchestrator run,
named `audit_{run_id}.jsonl` under `.agent-fox/audit/`.

[40-REQ-5.3] THE system SHALL create the `audit_events` DuckDB table via a
versioned migration with columns matching the `AuditEvent` data model.

[40-REQ-5.4] THE system SHALL extend the existing `SinkDispatcher` /
`SessionSink` protocol to support audit event emission, so that `DuckDBSink`
and a new `AuditJsonlSink` both receive audit events through the established
dispatch mechanism.

#### Edge Cases

[40-REQ-5.E1] IF the JSONL file write fails, THEN THE system SHALL log the
error and continue (DuckDB write is sufficient).

[40-REQ-5.E2] IF the DuckDB write fails, THEN THE system SHALL log the error
and continue (JSONL write is sufficient).

[40-REQ-5.E3] IF both JSONL and DuckDB writes fail, THEN THE system SHALL log
the error at `error` severity and continue. The event is lost.

### Requirement 6: Log Retention

**User Story:** As a developer, I want old audit log files cleaned up
automatically so that disk usage stays bounded.

#### Acceptance Criteria

[40-REQ-6.1] WHEN an orchestrator run starts, THE system SHALL enforce log
retention by deleting the oldest per-run JSONL files that exceed the retention
limit, before creating the new run's log file.

[40-REQ-6.2] THE system SHALL default to retaining the last 20 runs' JSONL
files.

[40-REQ-6.3] THE system SHALL allow the retention limit to be configured via
`config.toml` under `[knowledge] audit_log_retention`.

[40-REQ-6.4] THE system SHALL NOT apply retention to DuckDB audit data. All
audit events remain queryable in DuckDB indefinitely.

#### Edge Cases

[40-REQ-6.E1] IF the audit log directory does not exist or contains no files,
THEN retention enforcement SHALL be a no-op.

### Requirement 7: CLI Audit Command

**User Story:** As a developer, I want to query the audit trail from the command
line so that I can diagnose issues without parsing raw files.

#### Acceptance Criteria

[40-REQ-7.1] WHEN `agent-fox audit` is invoked without flags, THE system SHALL
display all events from the most recent run in human-readable chronological
format (narrative style, no tables).

[40-REQ-7.2] WHEN `agent-fox audit --json` is invoked, THE system SHALL output
a pure JSON array of matching events.

[40-REQ-7.3] WHEN `agent-fox audit --list-runs` is invoked, THE system SHALL
display a list of available run IDs with their timestamps, event counts, and
summary statistics (total sessions, total cost, final run status).

[40-REQ-7.4] WHEN `agent-fox audit --event-type TYPE` is invoked, THE system
SHALL filter events to only those matching the specified type.

[40-REQ-7.5] WHEN `agent-fox audit --node-id ID` is invoked, THE system SHALL
filter events to only those associated with the specified node.

[40-REQ-7.6] WHEN `agent-fox audit --since TIMESTAMP` is invoked, THE system
SHALL filter events to only those after the specified timestamp.

[40-REQ-7.7] WHEN `agent-fox audit --run RUN_ID` is invoked, THE system SHALL
filter events to those from the specified run instead of the most recent.

[40-REQ-7.8] WHEN multiple filter flags are provided, THE system SHALL compose
them with AND semantics.

#### Edge Cases

[40-REQ-7.E1] IF no audit events match the filters, THEN THE system SHALL
display a message indicating no events found and exit with code 0.

[40-REQ-7.E2] IF the DuckDB store is unavailable, THEN THE system SHALL display
an error message and exit with code 1.

[40-REQ-7.E3] IF `--run` specifies a run ID that does not exist, THEN THE
system SHALL display an error message indicating the run was not found and
exit with code 1.

### Requirement 8: Reporting Migration

**User Story:** As the system, I want reporting modules to read from DuckDB so
that they benefit from structured queries and don't duplicate JSONL parsing.

#### Acceptance Criteria

[40-REQ-8.1] WHEN `agent-fox status` is invoked, THE system SHALL compute all
report metrics from DuckDB tables (`audit_events`, `memory_facts`,
`session_outcomes`) instead of parsing `state.jsonl` and `memory.jsonl`.

[40-REQ-8.2] WHEN `agent-fox standup` is invoked, THE system SHALL compute
session activity, cost breakdowns, and queue summaries from DuckDB instead of
parsing `state.jsonl`.

[40-REQ-8.3] THE system SHALL produce identical report output (within floating
point tolerance) whether data was loaded from DuckDB or from the legacy JSONL
files.

#### Edge Cases

[40-REQ-8.E1] IF the DuckDB store has no data for the requested time window,
THEN THE system SHALL display an empty report rather than falling back to JSONL
parsing.

### Requirement 9: Schema Migration

**User Story:** As the system, I want the new DuckDB schema applied
automatically so that existing databases are upgraded seamlessly.

#### Acceptance Criteria

[40-REQ-9.1] WHEN the knowledge store is opened, THE system SHALL apply a
versioned migration that creates the `audit_events` table if it does not exist.

[40-REQ-9.2] WHEN an existing database from a prior version is opened, THE
system SHALL migrate it to the new schema without data loss.

#### Edge Cases

[40-REQ-9.E1] IF a migration fails, THEN THE system SHALL log the error, leave
the database in its pre-migration state, and raise a `KnowledgeStoreError`.

### Requirement 10: Knowledge Ingestion Audit Trail

**User Story:** As an operator, I want knowledge pipeline activity (ADR, commit,
errata ingestion) visible in the audit trail so that I can trace what knowledge
was imported and when.

#### Acceptance Criteria

[40-REQ-10.1] WHEN `KnowledgeIngestor` ingests ADRs, THE system SHALL emit a
`knowledge.ingested` audit event with `source_type=adr`, the source path, and
the count of items ingested.

[40-REQ-10.2] WHEN `KnowledgeIngestor` ingests git commits, THE system SHALL
emit a `knowledge.ingested` audit event with `source_type=commit` and the count
of commits ingested.

[40-REQ-10.3] WHEN errata documents are ingested, THE system SHALL emit a
`knowledge.ingested` audit event with `source_type=errata`, the source path,
and the count of items ingested.

[40-REQ-10.4] THE `KnowledgeIngestor` SHALL reside within the unified
`agent_fox.knowledge` package.

#### Edge Cases

[40-REQ-10.E1] IF ingestion fails partway through a batch, THEN THE system
SHALL emit the `knowledge.ingested` event with the count of successfully
ingested items and log the failure.
