# Requirements Document

## Introduction

This document specifies the DuckDB knowledge store infrastructure for
agent-fox v2: database lifecycle management, schema creation and versioning,
the SessionSink protocol, the DuckDB sink implementation, the JSONL sink
implementation, always-on session outcome recording, debug-gated tool signal
recording, and graceful degradation. Every subsequent knowledge-related spec
(Fox Ball, Time Vision) depends on the infrastructure established here.

## Glossary

| Term | Definition |
|------|-----------|
| Knowledge store | The DuckDB database at `.agent-fox/knowledge.duckdb` that persists structured session data |
| Schema version | An integer tracking the current database schema revision |
| Migration | A forward-only Python function that transforms the schema from version N to N+1 |
| SessionSink | A Protocol defining the interface for recording session events |
| DuckDB sink | A SessionSink implementation that writes to the DuckDB knowledge store |
| JSONL sink | A SessionSink implementation that writes raw audit data to timestamped JSONL files |
| Session outcome | A structured record of a coding session's result: spec, task, status, tokens, duration |
| Tool signal | A structured record of a tool call or tool error extracted from the message stream |
| VSS | DuckDB Vector Similarity Search extension, providing HNSW index support |
| WAL | Write-ahead log -- DuckDB's crash-safety mechanism for append-only writes |
| Graceful degradation | Continuing operation without the knowledge store when it is unavailable |

## Requirements

### Requirement 1: Database Lifecycle

**User Story:** As a developer, I want the knowledge store to be created and
managed automatically so that I never need to manually set up or configure a
database.

#### Acceptance Criteria

1. [11-REQ-1.1] WHEN the system opens the knowledge store for the first time,
   THE system SHALL create the DuckDB database file at the path specified by
   `KnowledgeConfig.store_path` (default: `.agent-fox/knowledge.duckdb`).
2. [11-REQ-1.2] WHEN the system opens the knowledge store, THE system SHALL
   install and load the VSS extension (`INSTALL vss; LOAD vss;`) on first use,
   and load it (`LOAD vss;`) on subsequent connections.
3. [11-REQ-1.3] WHEN the database connection is no longer needed, THE system
   SHALL close the connection cleanly, releasing all file locks.

#### Edge Cases

1. [11-REQ-1.E1] IF the parent directory for the database file does not exist,
   THEN THE system SHALL create it before opening the database.
2. [11-REQ-1.E2] IF the database file cannot be created or opened (permission
   denied, disk full), THEN THE system SHALL raise a `KnowledgeStoreError`
   with the underlying cause.

---

### Requirement 2: Schema Creation

**User Story:** As a developer, I want the database schema to be created
automatically on first use so that the knowledge store is immediately ready
for writes.

#### Acceptance Criteria

1. [11-REQ-2.1] WHEN the knowledge store is opened and the `schema_version`
   table does not exist, THE system SHALL create all schema tables:
   `schema_version`, `memory_facts`, `memory_embeddings`,
   `session_outcomes`, `fact_causes`, `tool_calls`, `tool_errors`.
2. [11-REQ-2.2] THE `schema_version` table SHALL record version 1 as the
   initial schema version with a timestamp and description.
3. [11-REQ-2.3] THE `memory_embeddings` table SHALL use a `FLOAT[N]` array
   column where N is derived from `KnowledgeConfig.embedding_dimensions`
   (default: 1024).

---

### Requirement 3: Schema Migration

**User Story:** As a developer of agent-fox, I want a migration system that
evolves the database schema forward without data loss so that schema changes
ship safely across releases.

#### Acceptance Criteria

1. [11-REQ-3.1] WHEN the knowledge store is opened and the current schema
   version is less than the latest version defined in code, THE system SHALL
   apply all pending migrations in order.
2. [11-REQ-3.2] Each migration SHALL be a numbered Python function that
   receives a DuckDB connection and transforms the schema from version N to
   N+1.
3. [11-REQ-3.3] WHEN a migration is applied, THE system SHALL insert a row
   into `schema_version` recording the new version, timestamp, and
   description.

#### Edge Cases

1. [11-REQ-3.E1] IF a migration fails, THEN THE system SHALL raise a
   `KnowledgeStoreError` with the failing migration version and the
   underlying database error.

---

### Requirement 4: SessionSink Protocol

**User Story:** As a developer of agent-fox, I want a composable sink
abstraction so that recording targets (DuckDB, JSONL, future sinks) are
decoupled from the session runner and can be mixed independently.

#### Acceptance Criteria

1. [11-REQ-4.1] THE system SHALL define a `SessionSink` as a
   `typing.Protocol` with the following methods: `record_session_outcome`,
   `record_tool_call`, `record_tool_error`, and `close`.
2. [11-REQ-4.2] THE session runner SHALL call sink methods without knowing
   which sinks are active. The orchestrator's sink attachment logic SHALL be
   the single place where the debug/always decision is made.
3. [11-REQ-4.3] Multiple sinks SHALL be composable: the system SHALL support
   dispatching events to a list of sinks, calling each in turn.

---

### Requirement 5: DuckDB Sink

**User Story:** As a developer, I want session outcomes always recorded to
DuckDB and tool signals recorded when debugging so that structured session
data is always available for analytics.

#### Acceptance Criteria

1. [11-REQ-5.1] THE DuckDB sink SHALL implement the `SessionSink` protocol.
2. [11-REQ-5.2] THE `record_session_outcome` method SHALL always write a row
   to the `session_outcomes` table, regardless of whether debug mode is
   enabled.
3. [11-REQ-5.3] THE `record_tool_call` and `record_tool_error` methods SHALL
   write rows to `tool_calls` and `tool_errors` tables respectively, only
   when the sink is configured with debug mode enabled.
4. [11-REQ-5.4] WHEN debug mode is disabled, `record_tool_call` and
   `record_tool_error` SHALL be no-ops (return immediately without writing).

#### Edge Cases

1. [11-REQ-5.E1] IF a DuckDB write fails (disk full, lock timeout), THEN THE
   sink SHALL log a warning and continue without raising an exception to the
   session runner.

---

### Requirement 6: JSONL Sink

**User Story:** As a developer, I want the existing JSONL audit behavior
preserved so that raw session replay remains available when debugging.

#### Acceptance Criteria

1. [11-REQ-6.1] THE JSONL sink SHALL implement the `SessionSink` protocol.
2. [11-REQ-6.2] THE JSONL sink SHALL write all events (session outcomes, tool
   calls, tool errors) as JSON lines to a timestamped file in
   `.agent-fox/`.
3. [11-REQ-6.3] THE JSONL sink SHALL only be attached when debug mode is
   enabled, preserving the existing v1 behavior.

---

### Requirement 7: Graceful Degradation

**User Story:** As a developer, I want agent-fox to continue working even if
the knowledge store is broken so that a corrupted database never blocks my
coding sessions.

#### Acceptance Criteria

1. [11-REQ-7.1] IF the DuckDB file is corrupted or inaccessible at startup,
   THEN THE system SHALL log a warning and continue operating without the
   knowledge store.
2. [11-REQ-7.2] IF DuckDB becomes inaccessible mid-run (e.g., disk full),
   THEN THE system SHALL log the error and continue execution -- knowledge
   writes are best-effort, not execution-blocking.
3. [11-REQ-7.3] WHEN the knowledge store is unavailable, session outcomes
   SHALL fall back to JSONL-only recording (if debug mode is enabled) or
   be silently skipped (if debug mode is disabled).
