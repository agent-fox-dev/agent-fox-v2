# Requirements Document

## Introduction

The agent-fox project has two overlapping packages (`memory/` and `knowledge/`)
for knowledge management. This spec consolidates them into a single
`agent_fox/knowledge/` package, makes DuckDB the primary read path for facts,
demotes JSONL to export-only, and introduces an in-memory state machine for
buffered writes during orchestrator runs.

## Glossary

| Term | Definition |
|------|------------|
| **Fact** | A structured knowledge item (`Fact` dataclass) with content, category, confidence, keywords, and provenance. |
| **JSONL** | The `.agent-fox/memory.jsonl` append-only file used for fact persistence. |
| **DuckDB** | The `memory_facts` table in the DuckDB knowledge store. |
| **KnowledgeStateMachine** | An in-memory buffer that accumulates facts and findings during an orchestrator run and flushes them to DuckDB at sync points. |
| **Sync point** | A defined moment when buffered state is flushed to DuckDB: task group end, sync barrier, or session end. |
| **Export** | Writing accumulated facts to JSONL at session end or compaction -- JSONL is no longer read as a primary source. |

## Requirements

### Requirement 1: Package Consolidation

**User Story:** As a developer, I want all knowledge-related code in a single
package, so that I can find and modify it without navigating two overlapping
packages.

#### Acceptance Criteria

1. [39-REQ-1.1] THE system SHALL contain all former `agent_fox.memory` modules within `agent_fox.knowledge`, using the following mapping: `types.py` -> `facts.py`, `memory.py` -> `store.py`, `filter.py` -> `filtering.py`, `render.py` -> `rendering.py`, `extraction.py` -> `extraction.py`, `compaction.py` -> `compaction.py`.

2. [39-REQ-1.2] THE system SHALL NOT contain an `agent_fox/memory/` package directory after consolidation.

3. [39-REQ-1.3] WHEN any module in the codebase imports a symbol formerly in `agent_fox.memory`, THE import path SHALL use `agent_fox.knowledge` instead.

4. [39-REQ-1.4] THE `agent_fox.knowledge.__init__` module SHALL re-export all public symbols from the consolidated modules: `Fact`, `Category`, `ConfidenceLevel`, `parse_confidence`, `CONFIDENCE_MAP`, `DEFAULT_CONFIDENCE`, `MemoryStore`, `append_facts`, `load_all_facts`, `load_facts_by_spec`, `write_facts`, `select_relevant_facts`, `render_summary`, `extract_facts`, `compact`.

5. [39-REQ-1.5] WHEN test files previously located under `tests/unit/memory/` or `tests/property/memory/` are moved, THEY SHALL reside under `tests/unit/knowledge/` and `tests/property/knowledge/` respectively, and all their imports SHALL be updated.

#### Edge Cases

1. [39-REQ-1.E1] IF any third-party or template code references `agent_fox.memory`, THEN those references SHALL be updated to `agent_fox.knowledge`.

### Requirement 2: DuckDB Primary Read Path

**User Story:** As the orchestrator, I want to load facts from DuckDB instead
of JSONL, so that queries benefit from SQL indexing and the system has a single
source of truth.

#### Acceptance Criteria

1. [39-REQ-2.1] WHEN `load_all_facts()` is called, THE system SHALL read facts from the `memory_facts` DuckDB table, not from the JSONL file.

2. [39-REQ-2.2] WHEN `load_facts_by_spec(spec_name)` is called, THE system SHALL query `memory_facts` with a `WHERE spec_name = ?` clause.

3. [39-REQ-2.3] THE `load_all_facts()` function SHALL accept a `conn: duckdb.DuckDBPyConnection` parameter instead of a `path: Path` parameter.

4. [39-REQ-2.4] THE `load_facts_by_spec()` function SHALL accept a `conn: duckdb.DuckDBPyConnection` parameter instead of a `path: Path` parameter.

5. [39-REQ-2.5] WHEN loading facts from DuckDB, THE system SHALL exclude rows where `superseded_by IS NOT NULL`.

#### Edge Cases

1. [39-REQ-2.E1] IF the `memory_facts` table is empty, THEN `load_all_facts()` SHALL return an empty list.

2. [39-REQ-2.E2] IF a DuckDB read fails, THEN the error SHALL propagate (no silent fallback to JSONL).

### Requirement 3: JSONL Export-Only

**User Story:** As a system operator, I want JSONL written only at session end
and compaction, so that the system avoids redundant I/O and JSONL serves as a
portable export format rather than a primary store.

#### Acceptance Criteria

1. [39-REQ-3.1] WHEN `MemoryStore.write_fact()` is called, THE system SHALL write to DuckDB only -- not to JSONL.

2. [39-REQ-3.2] WHEN a session ends, THE system SHALL export all non-superseded facts from DuckDB to the JSONL file (full overwrite).

3. [39-REQ-3.3] WHEN compaction runs, THE system SHALL read from DuckDB, perform deduplication and supersession resolution, update DuckDB, and then export the result to JSONL.

4. [39-REQ-3.4] THE `append_facts()` function SHALL be retained as an internal helper for JSONL export, but SHALL NOT be called during normal fact ingestion.

#### Edge Cases

1. [39-REQ-3.E1] IF the JSONL export fails (e.g., disk full), THE system SHALL log a warning but SHALL NOT roll back the DuckDB write.

### Requirement 4: In-Memory State Machine

**User Story:** As the orchestrator, I want facts and findings buffered in
memory during a run and flushed at defined sync points, so that the system
avoids per-fact DuckDB writes and can batch operations for efficiency.

#### Acceptance Criteria

1. [39-REQ-4.1] THE system SHALL provide a `KnowledgeStateMachine` class that buffers `Fact` objects in memory before flushing to DuckDB.

2. [39-REQ-4.2] THE `KnowledgeStateMachine` SHALL expose an `add_fact(fact: Fact)` method that appends to the in-memory buffer without writing to DuckDB.

3. [39-REQ-4.3] THE `KnowledgeStateMachine` SHALL expose a `flush()` method that writes all buffered facts to DuckDB via `MemoryStore` and clears the buffer.

4. [39-REQ-4.4] THE `KnowledgeStateMachine` SHALL expose a `pending` property that returns the list of buffered facts not yet flushed.

5. [39-REQ-4.5] WHEN `flush()` is called with an empty buffer, THE system SHALL be a no-op (no DuckDB writes).

6. [39-REQ-4.6] THE `KnowledgeStateMachine` SHALL accept a `MemoryStore` instance at construction time for DuckDB access.

#### Edge Cases

1. [39-REQ-4.E1] IF `flush()` fails partway through (e.g., DuckDB error on the Nth fact), THEN facts already written SHALL remain in DuckDB, and the error SHALL propagate. The buffer SHALL contain only the unwritten facts.

### Requirement 5: Backward Compatibility

**User Story:** As a developer with muscle memory for the old import paths,
I want a clear error when I use `agent_fox.memory`, so that I know to update
my imports.

#### Acceptance Criteria

1. [39-REQ-5.1] IF code attempts to import from `agent_fox.memory`, THEN an `ImportError` SHALL be raised because the package no longer exists.

2. [39-REQ-5.2] ALL existing tests SHALL pass after the consolidation with updated import paths.

3. [39-REQ-5.3] THE system SHALL produce no new ruff lint warnings after the consolidation.
