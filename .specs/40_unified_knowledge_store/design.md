# Design Document

## Overview

This design covers the unified knowledge store and structured audit log. It
consolidates `agent_fox/memory/` into `agent_fox/knowledge/`, makes DuckDB
the primary fact store, introduces typed audit events with immediate dual-write,
enriches tool call records with parameter summaries, adds model interaction
metadata to session events, and provides a CLI `agent-fox audit` command.

## Architecture

### Package Layout (Post-Consolidation)

```
agent_fox/knowledge/
├── __init__.py          # Re-exports public API (Fact, Category, etc.)
├── db.py                # KnowledgeDB, schema creation, connection management
├── migrations.py        # Versioned migrations (add v_next for audit_events)
├── sink.py              # SessionSink protocol, SinkDispatcher, event dataclasses
├── duckdb_sink.py       # DuckDB sink (session outcomes, audit events)
├── audit_jsonl_sink.py  # NEW: Per-run JSONL audit sink
├── audit.py             # NEW: AuditEvent model, EventType enum, emit helpers
├── state_machine.py     # NEW: In-memory fact/finding buffer with flush
├── facts.py             # Fact dataclass, append/load/write (from memory/)
├── extraction.py        # LLM-based fact extraction (from memory/)
├── compaction.py        # Fact compaction (from memory/)
├── filtering.py         # Fact filtering/selection (from memory/)
├── rendering.py         # Fact summary rendering (from memory/)
├── store.py             # MemoryStore (from memory/, uses DuckDB primary)
├── embeddings.py        # Vector embeddings
├── search.py            # Vector/semantic search
├── causal.py            # Causal graph
├── ingest.py            # KnowledgeIngestor (ADRs, commits, errata)
├── review_store.py      # Review findings CRUD
├── verification_store.py # Verification results CRUD
└── drift_store.py       # Drift findings CRUD
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Session Execution (session_lifecycle.py)                        │
│                                                                 │
│  _build_prompts() ──→ prompt_template name saved on runner      │
│  _execute_query() ──→ streams AgentMessage objects              │
│    │                                                            │
│    ├─ ToolUseMessage ──→ emit tool.invocation audit event        │
│    │   tool_name + abbreviate_arg(tool_input) → param_summary   │
│    │                                                            │
│    ├─ AssistantMessage ──→ (no audit event, activity UI only)   │
│    │                                                            │
│    └─ ResultMessage ──→ emit session.complete / session.fail    │
│         includes: archetype, model_id, prompt_template,         │
│         tokens, cost, duration_ms, files_touched                │
│                                                                 │
│  session start ──→ emit session.start                           │
│    includes: archetype, model_id, prompt_template, attempt      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ SinkDispatcher                                                  │
│   .emit_audit_event(event)                                      │
│     ├─→ DuckDBSink.emit_audit_event()  → INSERT audit_events    │
│     └─→ AuditJsonlSink.emit_audit_event() → append JSONL       │
│                                                                 │
│   .record_session_outcome()  (unchanged)                        │
│   .record_tool_call()        (deprecated, retained)             │
└─────────────────────────────────────────────────────────────────┘
```

## Data Models

### AuditEvent

```python
@dataclass(frozen=True)
class AuditEvent:
    id: UUID
    timestamp: datetime          # UTC, ISO-8601
    run_id: str                  # "{YYYYMMDD}_{HHMMSS}_{short_hex}"
    event_type: EventType        # Enum of all event types
    node_id: str | None          # Task graph node (None for run-level events)
    session_id: str | None       # Session identifier (None for non-session events)
    archetype: str | None        # "coder", "skeptic", etc.
    severity: Severity           # info | warning | error | critical
    payload: dict[str, Any]      # Typed per event_type
```

### EventType Enum

```python
class EventType(str, Enum):
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
    ARCHETYPE_FINDING = "archetype.finding"
    TOOL_INVOCATION = "tool.invocation"
    TOOL_ERROR = "tool.error"
    GIT_MERGE = "git.merge"
    GIT_CONFLICT = "git.conflict"
    HARVEST_COMPLETE = "harvest.complete"
    FACT_EXTRACTED = "fact.extracted"
    FACT_COMPACTED = "fact.compacted"
    KNOWLEDGE_INGESTED = "knowledge.ingested"
    SYNC_BARRIER = "sync.barrier"
```

### Severity Enum

```python
class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

### Event Payload Schemas

Each `event_type` defines the shape of its `payload` dict. Key payloads:

**`session.start`:**
```python
{
    "model_id": str,            # Resolved model ID (e.g. "claude-sonnet-4-6")
    "prompt_template": str,     # Template filename (e.g. "coding.md")
    "attempt": int,
}
```

**`session.complete`:**
```python
{
    "model_id": str,
    "prompt_template": str,
    "input_tokens": int,
    "output_tokens": int,
    "cost": float,
    "duration_ms": int,
    "files_touched": list[str],
}
```

**`session.fail`:**
```python
{
    "model_id": str,
    "prompt_template": str,
    "error_message": str,
    "attempt": int,
}
```

**`tool.invocation`:**
```python
{
    "tool_name": str,
    "param_summary": str | None,  # Shortened file path or abbreviated arg
    "called_at": str,             # ISO-8601
}
```

**`tool.error`:**
```python
{
    "tool_name": str,
    "param_summary": str | None,
    "failed_at": str,
}
```

### Run ID Generation

```python
def generate_run_id() -> str:
    now = datetime.now(UTC)
    short_hex = uuid4().hex[:8]
    return f"{now:%Y%m%d}_{now:%H%M%S}_{short_hex}"
```

## DuckDB Schema Changes

### New Migration (v_next)

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id             UUID PRIMARY KEY,
    timestamp      TIMESTAMP NOT NULL,
    run_id         TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    node_id        TEXT,
    session_id     TEXT,
    archetype      TEXT,
    severity       TEXT NOT NULL DEFAULT 'info',
    payload        JSON NOT NULL
);

CREATE INDEX idx_audit_run_id ON audit_events(run_id);
CREATE INDEX idx_audit_event_type ON audit_events(event_type);
CREATE INDEX idx_audit_node_id ON audit_events(node_id);
CREATE INDEX idx_audit_timestamp ON audit_events(timestamp);
```

The legacy `tool_calls` and `tool_errors` tables are retained for backward
compatibility but are no longer written to. New tool invocation data flows
exclusively through audit events.

## Sink Protocol Extension

The `SessionSink` protocol gains one new method:

```python
class SessionSink(Protocol):
    def record_session_outcome(self, outcome: SessionOutcome) -> None: ...
    def record_tool_call(self, call: ToolCall) -> None: ...       # deprecated
    def record_tool_error(self, error: ToolError) -> None: ...    # deprecated
    def emit_audit_event(self, event: AuditEvent) -> None: ...    # NEW
    def close(self) -> None: ...
```

`SinkDispatcher` dispatches `emit_audit_event` to all sinks.

### AuditJsonlSink

New sink implementation that appends audit events as JSON lines to a per-run
file:

```python
class AuditJsonlSink:
    def __init__(self, audit_dir: Path, run_id: str) -> None:
        self._path = audit_dir / f"audit_{run_id}.jsonl"
        self._file: IO | None = None

    def emit_audit_event(self, event: AuditEvent) -> None:
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a")
        line = json.dumps(serialize_event(event))
        self._file.write(line + "\n")
        self._file.flush()

    # record_session_outcome, record_tool_call, record_tool_error: no-op
```

### DuckDBSink Extension

`DuckDBSink.emit_audit_event()` inserts a row into `audit_events`:

```python
def emit_audit_event(self, event: AuditEvent) -> None:
    self._conn.execute(
        """INSERT INTO audit_events
           (id, timestamp, run_id, event_type, node_id, session_id,
            archetype, severity, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [str(event.id), event.timestamp, event.run_id,
         event.event_type.value, event.node_id, event.session_id,
         event.archetype, event.severity.value,
         json.dumps(event.payload)],
    )
```

## In-Memory State Machine

```python
class KnowledgeStateMachine:
    """Buffers facts and findings in memory, flushes to DuckDB at defined points."""

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn
        self._pending_facts: list[Fact] = []
        self._pending_findings: list[Any] = []

    def add_fact(self, fact: Fact) -> None:
        self._pending_facts.append(fact)

    def add_finding(self, finding: Any) -> None:
        self._pending_findings.append(finding)

    def flush(self) -> None:
        """Persist all pending facts and findings to DuckDB."""
        # Write facts to memory_facts table
        # Write findings to review_findings / verification_results
        # Clear pending lists
        ...

    def load_facts(self) -> list[Fact]:
        """Load all facts from DuckDB."""
        ...
```

Flush is called at: end of task group, sync barriers, session end.
Audit events bypass this buffer entirely.

## Tool Invocation Enrichment

### param_summary Derivation

During `_execute_query()` in `session.py`, when a `ToolUseMessage` is received:

```python
def _derive_param_summary(tool_input: dict[str, Any]) -> str | None:
    """Derive a short parameter summary from tool input.

    Reuses abbreviate_arg() for consistent abbreviation.
    """
    for value in tool_input.values():
        if isinstance(value, str) and value:
            return abbreviate_arg(value, max_len=120)
    return None
```

This reuses the existing `abbreviate_arg()` helper from `agent_fox.ui.events`
which already handles:
- File path shortening (basename or last two components with `…/` prefix)
- String truncation with ellipsis

### Emission Point

Tool invocation events are emitted in the message processing loop of
`_execute_query()`, replacing the current `record_tool_call()` path:

```python
if isinstance(message, ToolUseMessage):
    param_summary = _derive_param_summary(message.tool_input)
    sink.emit_audit_event(AuditEvent(
        event_type=EventType.TOOL_INVOCATION,
        node_id=node_id,
        session_id=session_id,
        payload={
            "tool_name": message.tool_name,
            "param_summary": param_summary,
            "called_at": datetime.now(UTC).isoformat(),
        },
        severity=Severity.INFO,
        run_id=run_id,
    ))
```

## Model Interaction Metadata

### prompt_template Resolution

The `NodeSessionRunner` already knows the archetype and resolves templates via
`ArchetypeEntry.templates`. The primary template filename is captured during
`_build_prompts()`:

```python
def _build_prompts(self, ...) -> tuple[str, str]:
    ...
    entry = get_archetype(self._archetype)
    self._prompt_template = entry.templates[0] if entry.templates else "unknown"
    ...
```

The `_prompt_template` field is then included in session event payloads.

### Data Available at Each Event

| Field | Source | Available at |
|-------|--------|-------------|
| `archetype` | `NodeSessionRunner._archetype` | session.start, complete, fail |
| `model_id` | `NodeSessionRunner._resolved_model_id` | session.start, complete, fail |
| `prompt_template` | `ArchetypeEntry.templates[0]` | session.start, complete, fail |

## Log Retention

At the start of each orchestrator run, before creating a new log file:

```python
def enforce_retention(audit_dir: Path, max_runs: int) -> None:
    files = sorted(audit_dir.glob("audit_*.jsonl"))
    if len(files) > max_runs:
        for f in files[:len(files) - max_runs]:
            f.unlink()
```

Default: 20 runs. Configurable via `[knowledge] audit_log_retention` in
`config.toml`.

## CLI: `agent-fox audit`

### Implementation

New Click command in `agent_fox/cli/audit.py`:

```python
@click.command("audit")
@click.option("--json", "json_mode", is_flag=True)
@click.option("--list-runs", is_flag=True)
@click.option("--event-type", type=str, default=None)
@click.option("--node-id", type=str, default=None)
@click.option("--since", type=str, default=None)
@click.option("--run", "run_id", type=str, default=None)
```

Queries `audit_events` table with filter composition (AND semantics).
Default output: human-readable chronological narrative of the most recent run.

## Reporting Migration

`status.py` and `standup.py` switch from parsing `state.jsonl` / `memory.jsonl`
to querying DuckDB tables (`audit_events`, `memory_facts`, `session_outcomes`).
Output format remains identical.

## Correctness Properties

1. **Immediate persistence**: Audit events are never buffered. A crash after
   emission means the event is recoverable from either JSONL or DuckDB.
2. **Fact consistency**: Facts are only visible after flush. In-memory state
   is the authoritative view during a run.
3. **Idempotent migration**: The new migration uses `CREATE TABLE IF NOT EXISTS`
   and version-checks before applying.
4. **Backward compatibility**: Legacy `tool_calls`/`tool_errors` tables remain
   readable. Old data is not deleted.
5. **No prompt leakage**: Full prompt text is never stored. Only the template
   filename is recorded.
