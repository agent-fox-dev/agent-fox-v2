# Design Document: Structured Audit Log

## Overview

This spec introduces a structured, append-only audit log that captures all
significant agent actions during an orchestration run. The design extends the
existing `SessionSink` protocol with a single new method (`emit_audit_event`)
and adds two sink implementations: DuckDB persistence and JSONL file output.
Event emission is wired at 20 points across the engine, session lifecycle,
routing, harvest, and knowledge modules. A CLI command provides queryable
access.

## Architecture

```mermaid
flowchart TD
    subgraph "Event Emitters"
        ENG[engine.py] -->|run.*, task.*, sync.*| SD[SinkDispatcher]
        SL[session_lifecycle.py] -->|session.*, harvest.*| SD
        RT[routing/] -->|model.*| SD
        SS[session/session.py] -->|tool.*| SD
        KH[knowledge_harvest.py] -->|fact.*, git.*| SD
        KI[knowledge/ingest.py] -->|knowledge.*| SD
        CP[compaction.py] -->|fact.compacted| SD
    end

    subgraph "Sink Layer"
        SD --> DBS[DuckDBSink]
        SD --> AJS[AuditJsonlSink]
        SD --> EXS[Existing Sinks]
    end

    subgraph "Storage"
        DBS -->|INSERT| DB[(audit_events table)]
        AJS -->|append| JF[audit_{run_id}.jsonl]
    end

    subgraph "Consumers"
        CLI[agent-fox audit] -->|SELECT| DB
        STATUS[status.py] -->|SELECT| DB
        STANDUP[standup.py] -->|SELECT| DB
    end
```

### Module Responsibilities

1. **`agent_fox/knowledge/audit.py`** (new) -- `AuditEvent` dataclass,
   `AuditEventType` enum, `AuditSeverity` enum, `generate_run_id()`,
   `AuditJsonlSink` class.
2. **`agent_fox/knowledge/sink.py`** (modified) -- Add `emit_audit_event()`
   to `SessionSink` protocol and `SinkDispatcher`.
3. **`agent_fox/knowledge/duckdb_sink.py`** (modified) -- Add
   `emit_audit_event()` implementation that INSERTs into `audit_events`.
4. **`agent_fox/knowledge/migrations.py`** (modified) -- Add v6 migration
   for `audit_events` table.
5. **`agent_fox/engine/engine.py`** (modified) -- Emit `run.*`, `task.*`,
   `sync.*`, `session.retry` events; generate and propagate run ID.
6. **`agent_fox/engine/session_lifecycle.py`** (modified) -- Emit
   `session.*`, `harvest.complete` events.
7. **`agent_fox/session/session.py`** (modified) -- Emit `tool.*` events.
8. **`agent_fox/routing/router.py`** (modified) -- Emit `model.*` events.
9. **`agent_fox/engine/knowledge_harvest.py`** (modified) -- Emit `git.*`,
   `fact.extracted` events.
10. **`agent_fox/knowledge/compaction.py`** (modified) -- Emit
    `fact.compacted` events.
11. **`agent_fox/knowledge/ingest.py`** (modified) -- Emit
    `knowledge.ingested` events.
12. **`agent_fox/cli/audit.py`** (new) -- `agent-fox audit` CLI command.
13. **`agent_fox/reporting/status.py`** (modified) -- Read from DuckDB.
14. **`agent_fox/reporting/standup.py`** (modified) -- Read from DuckDB.

## Components and Interfaces

### AuditEvent Data Model

```python
from enum import StrEnum

class AuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AuditEventType(StrEnum):
    RUN_START = "run.start"
    RUN_COMPLETE = "run.complete"
    RUN_LIMIT_REACHED = "run.limit_reached"
    SESSION_START = "session.start"
    SESSION_COMPLETE = "session.complete"
    SESSION_FAIL = "session.fail"
    SESSION_RETRY = "session.retry"
    TASK_STATUS_CHANGE = "task.status_change"
    MODEL_ESCALATION = "model.escalation"
    MODEL_ASSESSMENT = "model.assessment"
    TOOL_INVOCATION = "tool.invocation"
    TOOL_ERROR = "tool.error"
    GIT_MERGE = "git.merge"
    GIT_CONFLICT = "git.conflict"
    HARVEST_COMPLETE = "harvest.complete"
    FACT_EXTRACTED = "fact.extracted"
    FACT_COMPACTED = "fact.compacted"
    KNOWLEDGE_INGESTED = "knowledge.ingested"
    SYNC_BARRIER = "sync.barrier"

@dataclass(frozen=True)
class AuditEvent:
    """Structured record of a significant agent action."""

    run_id: str
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    node_id: str = ""
    session_id: str = ""
    archetype: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
```

**Note:** The enum has 19 values listed above. The 20th value depends on
whether `session.retry` is counted. The design includes `session.retry` in
the list, making it 19 named values covering all required event types. The
actual count is 19 distinct types as listed.

### Run ID Generation

```python
def generate_run_id() -> str:
    """Generate a unique run ID: {YYYYMMDD}_{HHMMSS}_{short_hex}.

    The short_hex is the first 6 characters of a UUID4 hex string,
    ensuring uniqueness even when two runs start in the same second.
    """
    now = datetime.now(UTC)
    short_hex = uuid4().hex[:6]
    return f"{now:%Y%m%d}_{now:%H%M%S}_{short_hex}"
```

### SessionSink Protocol Extension

```python
@runtime_checkable
class SessionSink(Protocol):
    """Protocol for recording session events."""

    def record_session_outcome(self, outcome: SessionOutcome) -> None: ...
    def record_tool_call(self, call: ToolCall) -> None: ...
    def record_tool_error(self, error: ToolError) -> None: ...
    def emit_audit_event(self, event: AuditEvent) -> None: ...  # NEW
    def close(self) -> None: ...
```

The `SinkDispatcher` gains a corresponding `emit_audit_event` method:

```python
class SinkDispatcher:
    def emit_audit_event(self, event: AuditEvent) -> None:
        """Dispatch to all sinks. Logs and swallows individual failures."""
        self._dispatch("emit_audit_event", event)
```

### DuckDBSink Extension

```python
class DuckDBSink:
    def emit_audit_event(self, event: AuditEvent) -> None:
        """Insert audit event into audit_events table."""
        self._conn.execute(
            """
            INSERT INTO audit_events
                (id, timestamp, run_id, event_type, node_id, session_id,
                 archetype, severity, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(event.id),
                event.timestamp,
                event.run_id,
                event.event_type.value,
                event.node_id,
                event.session_id,
                event.archetype,
                event.severity.value,
                json.dumps(event.payload),
            ],
        )
```

### AuditJsonlSink

```python
class AuditJsonlSink:
    """SessionSink that writes audit events to a JSONL file.

    One file per run: .agent-fox/audit/audit_{run_id}.jsonl
    Other SessionSink methods are no-ops.
    """

    def __init__(self, audit_dir: Path, run_id: str) -> None:
        self._audit_dir = audit_dir
        self._run_id = run_id
        self._file_path = audit_dir / f"audit_{run_id}.jsonl"
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    def emit_audit_event(self, event: AuditEvent) -> None:
        """Append a JSON line to the audit file."""
        line = json.dumps({
            "id": str(event.id),
            "timestamp": event.timestamp.isoformat(),
            "run_id": event.run_id,
            "event_type": event.event_type.value,
            "node_id": event.node_id,
            "session_id": event.session_id,
            "archetype": event.archetype,
            "severity": event.severity.value,
            "payload": event.payload,
        })
        try:
            with open(self._file_path, "a") as f:
                f.write(line + "\n")
        except OSError:
            logger.warning("Failed to write audit event to %s", self._file_path)

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        pass  # handled by other sinks

    def record_tool_call(self, call: ToolCall) -> None:
        pass

    def record_tool_error(self, error: ToolError) -> None:
        pass

    def close(self) -> None:
        pass  # file handle opened/closed per write
```

### DuckDB Migration (v6)

```python
def _migrate_v6(conn: duckdb.DuckDBPyConnection) -> None:
    """Add audit_events table.

    Requirements: 40-REQ-3.1, 40-REQ-3.2
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id          VARCHAR PRIMARY KEY,
            timestamp   TIMESTAMP NOT NULL,
            run_id      VARCHAR NOT NULL,
            event_type  VARCHAR NOT NULL,
            node_id     VARCHAR,
            session_id  VARCHAR,
            archetype   VARCHAR,
            severity    VARCHAR NOT NULL,
            payload     JSON NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_run_id
            ON audit_events (run_id);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type
            ON audit_events (event_type);
    """)
```

### Event Emission Points

| # | Event Type | Emitter Module | Emission Point | Key Payload Fields |
|---|-----------|----------------|----------------|-------------------|
| 1 | `run.start` | `engine.py` | `execute()` start | `plan_hash`, `total_nodes`, `parallel` |
| 2 | `run.complete` | `engine.py` | `execute()` end | `total_sessions`, `total_cost`, `duration_ms`, `run_status` |
| 3 | `run.limit_reached` | `engine.py` | limit check | `limit_type`, `limit_value` |
| 4 | `session.start` | `session_lifecycle.py` | before SDK call | `archetype`, `model_id`, `prompt_template`, `attempt` |
| 5 | `session.complete` | `session_lifecycle.py` | after SDK success | `archetype`, `model_id`, `prompt_template`, `tokens`, `cost`, `duration_ms`, `files_touched` |
| 6 | `session.fail` | `session_lifecycle.py` | after SDK failure | `archetype`, `model_id`, `prompt_template`, `error_message`, `attempt` |
| 7 | `session.retry` | `engine.py` | retry decision | `attempt`, `reason` |
| 8 | `task.status_change` | `engine.py` | node state update | `from_status`, `to_status`, `reason` |
| 9 | `model.escalation` | `routing/router.py` | escalation | `from_tier`, `to_tier`, `reason` |
| 10 | `model.assessment` | `routing/router.py` | assessment | `predicted_tier`, `confidence`, `method` |
| 11 | `tool.invocation` | `session/session.py` | tool callback | `tool_name`, `param_summary`, `called_at` |
| 12 | `tool.error` | `session/session.py` | tool error | `tool_name`, `param_summary`, `failed_at` |
| 13 | `git.merge` | `knowledge_harvest.py` | merge complete | `branch`, `commit_sha`, `files_touched` |
| 14 | `git.conflict` | `knowledge_harvest.py` | merge conflict | `branch`, `strategy`, `error` |
| 15 | `harvest.complete` | `session_lifecycle.py` | post-harvest | `commit_sha`, `facts_extracted`, `findings_persisted` |
| 16 | `fact.extracted` | `knowledge_harvest.py` | extraction done | `fact_count`, `categories` |
| 17 | `fact.compacted` | `compaction.py` | compaction done | `facts_before`, `facts_after`, `superseded_count` |
| 18 | `knowledge.ingested` | `knowledge/ingest.py` | ingestion done | `source_type`, `source_path`, `item_count` |
| 19 | `sync.barrier` | `engine.py` | barrier reached | `completed_nodes`, `pending_nodes` |

### Log Retention

```python
def enforce_audit_retention(
    audit_dir: Path,
    conn: duckdb.DuckDBPyConnection,
    max_runs: int = 20,
) -> None:
    """Delete audit data for runs beyond the retention limit.

    Steps:
    1. Query distinct run_ids from audit_events ordered by MIN(timestamp).
    2. If count > max_runs, identify the oldest (count - max_runs) run IDs.
    3. Delete corresponding rows from audit_events.
    4. Delete corresponding JSONL files from audit_dir.
    """
```

### CLI Command

```python
@click.command("audit")
@click.option("--list-runs", is_flag=True, help="List available run IDs.")
@click.option("--run", "run_id", help="Filter by run ID.")
@click.option("--event-type", help="Filter by event type.")
@click.option("--node-id", help="Filter by node ID.")
@click.option("--since", help="Filter events after datetime (ISO-8601 or 24h/7d).")
@click.pass_context
def audit_cmd(ctx, list_runs, run_id, event_type, node_id, since):
    """Query the structured audit log."""
```

### Reporting Migration

`status.py` and `standup.py` currently read from `state.jsonl` via
`StateManager`. After this spec, they will query the `audit_events` DuckDB
table for session metrics:

```python
def build_status_report_from_audit(
    conn: duckdb.DuckDBPyConnection,
    run_id: str | None = None,
) -> StatusReport:
    """Build a StatusReport from audit_events instead of state.jsonl.

    Queries session.complete and session.fail events to compute:
    - Total sessions, pass/fail counts
    - Total tokens and cost
    - Per-archetype breakdown
    - Per-spec breakdown
    """
```

Fallback: if DuckDB is unavailable, the modules fall back to the existing
`state.jsonl` parsing.

## Data Models

### audit_events Table Schema

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | VARCHAR | PRIMARY KEY | UUID as string |
| `timestamp` | TIMESTAMP | NOT NULL | UTC |
| `run_id` | VARCHAR | NOT NULL, INDEXED | Run identifier |
| `event_type` | VARCHAR | NOT NULL, INDEXED | Event type string |
| `node_id` | VARCHAR | | Task node identifier |
| `session_id` | VARCHAR | | Session identifier |
| `archetype` | VARCHAR | | Agent archetype |
| `severity` | VARCHAR | NOT NULL | info/warning/error/critical |
| `payload` | JSON | NOT NULL | Event-type-specific data |

### Event Type Payload Schemas

| Event Type | Payload Fields |
|-----------|----------------|
| `run.start` | `plan_hash: str`, `total_nodes: int`, `parallel: bool` |
| `run.complete` | `total_sessions: int`, `total_cost: float`, `duration_ms: int`, `run_status: str` |
| `run.limit_reached` | `limit_type: str`, `limit_value: int\|float` |
| `session.start` | `archetype: str`, `model_id: str`, `prompt_template: str`, `attempt: int` |
| `session.complete` | `archetype: str`, `model_id: str`, `prompt_template: str`, `tokens: int`, `cost: float`, `duration_ms: int`, `files_touched: list[str]` |
| `session.fail` | `archetype: str`, `model_id: str`, `prompt_template: str`, `error_message: str`, `attempt: int` |
| `session.retry` | `attempt: int`, `reason: str` |
| `task.status_change` | `from_status: str`, `to_status: str`, `reason: str` |
| `model.escalation` | `from_tier: str`, `to_tier: str`, `reason: str` |
| `model.assessment` | `predicted_tier: str`, `confidence: float`, `method: str` |
| `tool.invocation` | `tool_name: str`, `param_summary: str`, `called_at: str` |
| `tool.error` | `tool_name: str`, `param_summary: str`, `failed_at: str` |
| `git.merge` | `branch: str`, `commit_sha: str`, `files_touched: list[str]` |
| `git.conflict` | `branch: str`, `strategy: str`, `error: str` |
| `harvest.complete` | `commit_sha: str`, `facts_extracted: int`, `findings_persisted: int` |
| `fact.extracted` | `fact_count: int`, `categories: list[str]` |
| `fact.compacted` | `facts_before: int`, `facts_after: int`, `superseded_count: int` |
| `knowledge.ingested` | `source_type: str`, `source_path: str`, `item_count: int` |
| `sync.barrier` | `completed_nodes: list[str]`, `pending_nodes: list[str]` |

## Operational Readiness

### Observability

- Log at DEBUG when an audit event is emitted.
- Log at WARNING when a sink fails to process an audit event.
- Log at INFO when retention cleanup deletes runs.
- Log at WARNING when JSONL file write fails.
- Log at INFO the total event count at run completion.

### Migration / Compatibility

- The `SessionSink` protocol gains one new method. Existing implementations
  that do not define `emit_audit_event` will receive a warning from the
  `SinkDispatcher` but will not break.
- The DuckDB migration (v6) is additive -- it creates a new table and does
  not modify existing tables.
- The `state.jsonl` checkpoint mechanism is unchanged. Reporting modules
  fall back to `state.jsonl` parsing when DuckDB is unavailable.

## Correctness Properties

### Property 1: Event Completeness

*For any* orchestrator run that executes N sessions, the audit log SHALL
contain at least N `session.start` events and exactly one `run.start` event
and one `run.complete` event.

**Validates: Requirements 40-REQ-7.1, 40-REQ-9.1, 40-REQ-9.2**

### Property 2: Run ID Consistency

*For any* audit event emitted during a single orchestrator invocation, the
`run_id` field SHALL be identical across all events.

**Validates: Requirements 40-REQ-2.1, 40-REQ-2.2**

### Property 3: Dual-Write Consistency

*For any* audit event emitted, the event SHALL appear in both the DuckDB
`audit_events` table and the JSONL file (assuming both sinks are registered
and operational).

**Validates: Requirements 40-REQ-5.1, 40-REQ-6.1**

### Property 4: Event Serialization Round-Trip

*For any* `AuditEvent`, serializing to JSON and deserializing back SHALL
produce an equivalent event (same id, timestamp, run_id, event_type,
severity, and payload).

**Validates: Requirements 40-REQ-1.1, 40-REQ-6.3**

### Property 5: Retention Bound

*For any* retention limit R and run count N where N > R, after
`enforce_audit_retention()` executes, at most R runs SHALL have events in
both DuckDB and JSONL files.

**Validates: Requirements 40-REQ-12.1, 40-REQ-12.2**

### Property 6: Severity Classification

*For any* `session.fail` event, the severity SHALL be `error`. *For any*
`run.limit_reached` or `git.conflict` event, the severity SHALL be `warning`.
All other event types SHALL default to `info`.

**Validates: Requirements 40-REQ-7.3, 40-REQ-9.3, 40-REQ-11.2**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| DuckDBSink INSERT fails | Log warning, swallow exception | 40-REQ-4.E1 |
| JSONL file write fails | Log warning, swallow exception | 40-REQ-6.E1 |
| Sink lacks `emit_audit_event` | Log warning, skip sink | 40-REQ-4.E1 |
| DuckDB unavailable for CLI | Display "no audit data" message | 40-REQ-13.E2 |
| No events match CLI filter | Display empty result, exit 0 | 40-REQ-13.E1 |
| Retention JSONL deletion fails | Log warning, continue | 40-REQ-12.E2 |
| DuckDB unavailable for reporting | Fall back to state.jsonl | 40-REQ-14.3 |

## Technology Stack

- **Python 3.12+** -- project baseline
- **DuckDB** -- structured audit event storage
- **Click** -- CLI command framework
- **StrEnum** -- event type and severity enums (stdlib)
- **pytest / Hypothesis** -- testing

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and pushed to remote
7. Feature branch is merged back to `develop`
8. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- **Unit tests** validate the data model, enums, run ID generation,
  serialization, sink implementations, retention logic, and CLI output
  in isolation.
- **Property tests** (Hypothesis) verify event completeness, run ID
  consistency, serialization round-trips, retention bounds, and severity
  classification across generated inputs.
- **Integration tests** verify end-to-end: events emitted at emission
  points flow through sinks to DuckDB and JSONL, and are queryable via
  the CLI command.
