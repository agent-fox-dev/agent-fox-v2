# Requirements Document

## Introduction

This spec makes DuckDB a hard requirement for agent-fox operations. Currently,
DuckDB connectivity is optional with silent degradation across 15+ code
locations. This spec removes all optional patterns, making failures explicit
and ensuring all knowledge-dependent features are always available.

## Glossary

| Term | Definition |
|------|------------|
| **KnowledgeDB** | Wrapper class around a DuckDB connection that manages the knowledge store lifecycle (open, migrate, close). Defined in `knowledge/db.py`. |
| **Knowledge Store** | The DuckDB database file that stores memory facts, causal links, review findings, session outcomes, and complexity assessments. |
| **Silent Degradation** | A pattern where DuckDB unavailability is caught by a try/except or None check, logged as a warning, and execution continues without the feature. |
| **Hard Requirement** | A dependency that must be satisfied for the system to operate. Failure to satisfy it results in an immediate abort with a clear error message. |
| **DuckDB Sink** | The `DuckDBSink` class that records session outcomes to DuckDB. Currently best-effort with swallowed exceptions. |
| **Dual-Write** | The pattern where facts are written to both JSONL (append-only log) and DuckDB (queryable index). Both writes must succeed. |

## Requirements

### Requirement 1: Mandatory Initialization

**User Story:** As a system operator, I want agent-fox to fail fast with a
clear error if DuckDB cannot be initialized, so that I don't run sessions
with silently degraded functionality.

#### Acceptance Criteria

1. [38-REQ-1.1] WHEN the knowledge store cannot be opened, THE system SHALL raise an exception with message containing `"Knowledge store initialization failed"` and the underlying error detail.
2. [38-REQ-1.2] THE system SHALL remove the `open_knowledge_store()` function's try/except that returns `None` on failure.
3. [38-REQ-1.3] WHEN the CLI `code` command starts, THE system SHALL initialize the knowledge store before any session dispatch.

#### Edge Cases

1. [38-REQ-1.E1] IF the DuckDB file path is not writable, THEN THE system SHALL abort with an error message that includes the file path.

### Requirement 2: Required Parameters

**User Story:** As a developer, I want all DuckDB-dependent functions to
require a connection parameter, so that missing connections are caught at
call time rather than silently skipped.

#### Acceptance Criteria

1. [38-REQ-2.1] THE system SHALL change all `KnowledgeDB | None` function parameters to `KnowledgeDB` (non-optional).
2. [38-REQ-2.2] THE system SHALL change all `duckdb.DuckDBPyConnection | None` function parameters to `duckdb.DuckDBPyConnection` (non-optional).
3. [38-REQ-2.3] THE system SHALL remove all `if knowledge_db is None: return` guard clauses from functions that previously accepted optional connections.
4. [38-REQ-2.4] THE system SHALL remove all `if self._db_conn is None` guard clauses from `MemoryStore` methods.

### Requirement 3: Error Propagation

**User Story:** As a system operator, I want DuckDB errors to surface
immediately, so that I can diagnose and fix issues rather than discovering
them later through missing data.

#### Acceptance Criteria

1. [38-REQ-3.1] WHEN a DuckDB write operation fails in `DuckDBSink`, THE system SHALL propagate the exception instead of catching and logging it.
2. [38-REQ-3.2] WHEN a DuckDB write operation fails in `MemoryStore`, THE system SHALL propagate the exception instead of catching and logging it.
3. [38-REQ-3.3] WHEN causal link storage fails in `knowledge_harvest.py`, THE system SHALL propagate the exception instead of silently continuing.
4. [38-REQ-3.4] WHEN fact sync to DuckDB fails in `sync_facts_to_duckdb()`, THE system SHALL propagate the exception instead of silently continuing.

#### Edge Cases

1. [38-REQ-3.E1] IF a DuckDB error occurs during session context assembly (`assemble_context`), THEN THE system SHALL propagate the error rather than falling back to file-based rendering.

### Requirement 4: Context Assembly Without Fallback

**User Story:** As a session consumer, I want context assembly to always use
DuckDB-backed rendering, so that review findings and causal context are
always included.

#### Acceptance Criteria

1. [38-REQ-4.1] THE system SHALL change `assemble_context()` to require a `duckdb.DuckDBPyConnection` parameter (non-optional).
2. [38-REQ-4.2] THE system SHALL remove the file-based fallback path for review, verification, and drift context rendering.
3. [38-REQ-4.3] THE system SHALL always use `select_context_with_causal()` for fact selection when assembling context.

### Requirement 5: Test Infrastructure

**User Story:** As a developer, I want a shared DuckDB test fixture, so that
tests requiring a knowledge store can use a clean in-memory database.

#### Acceptance Criteria

1. [38-REQ-5.1] THE system SHALL provide a pytest fixture that creates an in-memory DuckDB database with all migrations applied.
2. [38-REQ-5.2] WHEN a test uses the DuckDB fixture, THE system SHALL provide a fresh database per test (no cross-test contamination).
3. [38-REQ-5.3] THE system SHALL update all existing tests that previously created `MemoryStore` or `NodeSessionRunner` without a DuckDB connection to use the fixture.

### Requirement 6: Routing Pipeline Hardening

**User Story:** As the adaptive routing system, I want a guaranteed DuckDB
connection, so that outcome persistence and statistical model training are
always available.

#### Acceptance Criteria

1. [38-REQ-6.1] THE system SHALL change `AssessmentPipeline.__init__()` to require a `duckdb.DuckDBPyConnection` parameter (non-optional).
2. [38-REQ-6.2] THE system SHALL remove the `_get_outcome_count()` fallback that returns `0` when `self._db is None`.
