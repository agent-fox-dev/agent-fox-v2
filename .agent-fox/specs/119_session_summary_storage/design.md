# Design Document: Session Summary Storage

## Overview

This spec adds three capabilities to the agent-fox knowledge system:

1. **Storage**: A new `session_summaries` DuckDB table persists the
   natural-language summary produced by each coding session.
2. **Retrieval**: `FoxKnowledgeProvider.retrieve()` queries stored summaries
   and injects them into downstream session prompts as `[CONTEXT]` and
   `[CROSS-SPEC]` items.
3. **Audit enhancement**: The `session.complete` audit event payload includes
   the summary text.

The design follows the existing patterns established by review findings
(spec 27), the knowledge provider protocol (spec 114), and the pluggable
knowledge provider (spec 115).

## Architecture

```mermaid
flowchart TD
    SDK["Claude Code SDK"] -->|writes| SF["session-summary.json"]
    SL["session_lifecycle.py<br/>_run_and_harvest()"] -->|reads| SF
    SL -->|passes summary via context| KP["FoxKnowledgeProvider.ingest()"]
    SL -->|includes in payload| AE["audit event<br/>SESSION_COMPLETE"]
    KP -->|INSERT| DB["session_summaries table<br/>(DuckDB)"]
    FP["FoxKnowledgeProvider.retrieve()"] -->|SELECT| DB
    FP -->|formats as [CONTEXT] / [CROSS-SPEC]| PROMPT["Session prompt context"]
```

### Module Responsibilities

1. **`agent_fox/knowledge/migrations.py`** — Defines the `session_summaries`
   table schema (migration v24) and updates the base DDL.
2. **`agent_fox/knowledge/summary_store.py`** (new) — CRUD operations for the
   `session_summaries` table: insert, query same-spec, query cross-spec.
3. **`agent_fox/knowledge/fox_provider.py`** — Extended `retrieve()` to query
   and format summaries; extended `ingest()` to store summaries.
4. **`agent_fox/engine/session_lifecycle.py`** — Modified to read the summary
   earlier in the lifecycle, pass it to both the audit event and the knowledge
   ingestion context.

## Execution Paths

### Path 1: Summary storage after session completion

1. `engine/session_lifecycle.py: NodeSessionRunner._run_and_harvest()` —
   after `_harvest_and_integrate()` returns, reads session artifacts
2. `engine/session_lifecycle.py: NodeSessionRunner._read_session_artifacts(workspace)` →
   `dict | None` containing `{"summary": "...", ...}`
3. `engine/session_lifecycle.py: NodeSessionRunner._run_and_harvest()` —
   extracts `summary_text = artifacts.get("summary", "")` if artifacts exist
4. `engine/session_lifecycle.py: NodeSessionRunner._ingest_knowledge()` —
   passes `summary_text` in the context dict under key `"summary"`
5. `knowledge/fox_provider.py: FoxKnowledgeProvider.ingest()` — receives
   context with `"summary"` key
6. `knowledge/summary_store.py: insert_summary()` — INSERT into
   `session_summaries` table
7. Side effect: row persisted in DuckDB

### Path 2: Summary injection into downstream session

1. `engine/session_lifecycle.py: NodeSessionRunner._build_prompts()` — calls
   `retrieve()` on the knowledge provider
2. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve(spec_name, task_description, task_group, session_id)` —
   orchestrates retrieval
3. `knowledge/summary_store.py: query_same_spec_summaries(conn, spec_name, task_group, run_id, max_items)` →
   `list[SummaryRecord]` — queries prior groups, latest attempt, coder only
4. `knowledge/summary_store.py: query_cross_spec_summaries(conn, spec_name, run_id, max_items)` →
   `list[SummaryRecord]` — queries other specs, latest attempt, coder only
5. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve()` — formats
   records as `[CONTEXT] (group G, attempt A) text` and
   `[CROSS-SPEC] (spec, group G) text`
6. Return: `list[str]` of formatted items appended to other knowledge items

### Path 3: Summary in audit event payload

1. `engine/session_lifecycle.py: NodeSessionRunner._run_and_harvest()` —
   after reading artifacts, includes `"summary": summary_text` in the
   `session.complete` audit event payload dict
2. `engine/audit_helpers.py: emit_audit_event()` — creates `AuditEvent` with
   the enriched payload
3. `knowledge/duckdb_sink.py: DuckDbSink.write()` — serializes payload as JSON
   and inserts into `audit_events` table
4. Side effect: audit event row contains summary in payload JSON

## Components and Interfaces

### Data Types

```python
@dataclass
class SummaryRecord:
    """A stored session summary."""
    id: str           # UUID
    node_id: str      # e.g. "01_audit_hub:3"
    run_id: str       # Run identifier
    spec_name: str    # e.g. "01_audit_hub"
    task_group: str   # e.g. "3"
    archetype: str    # e.g. "coder"
    attempt: int      # 1-indexed
    summary: str      # The natural-language summary text
    created_at: str   # ISO 8601 timestamp
```

### Module Interfaces

#### `summary_store.py`

```python
def insert_summary(
    conn: duckdb.DuckDBPyConnection,
    record: SummaryRecord,
) -> None:
    """Insert a session summary. No supersession — append-only."""

def query_same_spec_summaries(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str,
    run_id: str,
    max_items: int = 5,
) -> list[SummaryRecord]:
    """Return coder summaries from prior task groups in the same spec/run.
    
    Filters: archetype='coder', task_group < current, latest attempt per group.
    Sorts by task_group ASC. Caps at max_items.
    """

def query_cross_spec_summaries(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    run_id: str,
    max_items: int = 3,
) -> list[SummaryRecord]:
    """Return coder summaries from other specs in the same run.
    
    Filters: archetype='coder', spec_name != current, latest attempt per
    (spec, task_group). Sorts by created_at DESC. Caps at max_items.
    """
```

#### `fox_provider.py` extensions

```python
# Inside FoxKnowledgeProvider.retrieve():
def _query_same_spec_summaries(
    self,
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_group: str | None,
) -> list[str]:
    """Query and format same-spec summaries as [CONTEXT] items."""

def _query_cross_spec_summaries(
    self,
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> list[str]:
    """Query and format cross-spec summaries as [CROSS-SPEC] items."""

# Inside FoxKnowledgeProvider.ingest():
# Reads context["summary"] and calls insert_summary()
```

#### `session_lifecycle.py` modifications

The `_run_and_harvest()` method is restructured so that `_read_session_artifacts()`
is called before the audit event emission and knowledge ingestion, making the
summary text available to both. The summary is also stored on the returned
`SessionRecord` for the caller's log message.

```python
# Pseudocode for the modified flow in _run_and_harvest:
outcome = await self._execute_session(...)
status, error_message, touched_files, ... = await self._harvest_and_integrate(...)
summary_text = self._extract_summary_text(workspace)  # reads artifacts
# ... emit audit event with summary in payload ...
# ... call _ingest_knowledge with summary in context ...
return SessionRecord(..., summary=summary_text)
```

## Data Models

### `session_summaries` table

```sql
CREATE TABLE IF NOT EXISTS session_summaries (
    id          UUID PRIMARY KEY,
    node_id     VARCHAR NOT NULL,
    run_id      VARCHAR NOT NULL,
    spec_name   VARCHAR NOT NULL,
    task_group  VARCHAR NOT NULL,
    archetype   VARCHAR NOT NULL,
    attempt     INTEGER NOT NULL DEFAULT 1,
    summary     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
```

No unique constraint on `(node_id, run_id, attempt)` — append-only means
duplicates from idempotent retries are acceptable (the insert is protected by
the UUID primary key).

### Audit event payload (enhanced)

```json
{
    "archetype": "coder",
    "model_id": "claude-opus-4-6",
    "prompt_template": "coder",
    "input_tokens": 24,
    "output_tokens": 6827,
    "cache_read_input_tokens": 2002174,
    "cache_creation_input_tokens": 18525,
    "cost": 1.29,
    "duration_ms": 165000,
    "files_touched": ["internal/store/store.go", ...],
    "summary": "Implemented task group 3: SQLite store..."
}
```

The `summary` field is omitted (not null) when no summary is available.

## Operational Readiness

- **Observability**: Summary storage failures are logged at WARNING level.
  Missing summaries are logged at DEBUG level. No new metrics or alerts
  required.
- **Rollout**: Migration v24 is additive (new table only). No existing tables
  or columns are modified. Safe to apply without downtime.
- **Rollback**: Drop the `session_summaries` table. The knowledge provider
  gracefully handles a missing table (returns empty list).
- **Compatibility**: Older databases without the table work correctly — the
  provider catches the missing-table error and returns empty results.

## Correctness Properties

### Property 1: Summary Persistence Completeness

*For any* session that completes successfully with a non-empty summary
artifact, the `session_summaries` table SHALL contain exactly one row with
that summary text, matching node_id, run_id, and attempt number.

**Validates: Requirements 119-REQ-1.1, 119-REQ-5.2**

### Property 2: Prior-Group Filtering Correctness

*For any* task group N > 1 and any spec S, `query_same_spec_summaries(S, N, run_id)`
SHALL return only rows where `spec_name = S` AND `task_group < N` AND
`archetype = 'coder'` AND `run_id` matches, with at most one row per
task group (the highest attempt).

**Validates: Requirements 119-REQ-2.1, 119-REQ-2.3, 119-REQ-2.6**

### Property 3: Cross-Spec Exclusion

*For any* spec S and run R, `query_cross_spec_summaries(S, R)` SHALL return
zero rows where `spec_name = S`. Every returned row SHALL have
`spec_name != S` AND `archetype = 'coder'`.

**Validates: Requirements 119-REQ-3.1, 119-REQ-3.5**

### Property 4: Append-Only Invariant

*For any* sequence of `insert_summary()` calls with the same `node_id` and
different `attempt` values, the total row count for that `node_id` SHALL
equal the number of insert calls. No rows SHALL be deleted or have their
`summary` text modified.

**Validates: Requirements 119-REQ-1.3**

### Property 5: Graceful Degradation on Missing Table

*For any* database connection where the `session_summaries` table does not
exist, `query_same_spec_summaries()` and `query_cross_spec_summaries()` SHALL
return empty lists without raising exceptions.

**Validates: Requirements 119-REQ-1.E3, 119-REQ-2.E3**

### Property 6: Audit Payload Consistency

*For any* `session.complete` audit event, if a summary is available, the
payload SHALL contain a `"summary"` key with the same text stored in the
database. If no summary is available, the payload SHALL not contain a
`"summary"` key.

**Validates: Requirements 119-REQ-4.1, 119-REQ-4.2**

### Property 7: Sort Order Stability

*For any* retrieval call, same-spec summaries SHALL be sorted by task group
ascending, and cross-spec summaries SHALL be sorted by `created_at`
descending. The ordering SHALL be deterministic for identical data.

**Validates: Requirements 119-REQ-2.4, 119-REQ-3.4**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| Session summary artifact missing | Store no row, log debug | 119-REQ-1.E1 |
| Session failed (status != completed) | Skip summary storage | 119-REQ-1.E2 |
| `session_summaries` table missing | Return empty list, log debug | 119-REQ-1.E3, 119-REQ-2.E3 |
| Task group is 1 (no prior groups) | Return empty same-spec list | 119-REQ-2.E1 |
| No coder summaries exist for prior groups | Return empty list | 119-REQ-2.E2 |
| No other specs in current run | Return empty cross-spec list | 119-REQ-3.E1 |
| No run_id available | Skip cross-spec retrieval | 119-REQ-3.E2 |
| Summary exceeds 2000 chars (audit) | Truncate with `...` marker | 119-REQ-4.E1 |
| DB connection failure during insert | Log warning, continue | 119-REQ-5.E1 |

## Technology Stack

- **Database**: DuckDB (existing knowledge store)
- **Language**: Python 3.12+
- **Testing**: pytest, Hypothesis (property-based tests)
- **Schema management**: Custom migration system in `migrations.py`

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and merged into `develop`
7. Feature branch is merged back to `develop`
8. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- **Unit tests** validate `summary_store.py` functions in isolation with an
  in-memory DuckDB connection.
- **Property-based tests** (Hypothesis) verify filtering invariants: prior-group
  correctness, cross-spec exclusion, append-only behavior, sort order stability.
- **Integration tests** verify the end-to-end flow from `_read_session_artifacts`
  through `ingest()` to `retrieve()`, using real DuckDB connections.
- **Migration tests** verify that v24 applies cleanly to both fresh databases
  and databases at v23.
