# Test Specification: Structured Audit Log

## Overview

Tests validate that audit events are correctly modeled, serialized, emitted at
all wiring points, persisted to both DuckDB and JSONL, retained within
configured bounds, and queryable via the CLI. All test cases map to
requirements and correctness properties from design.md.

## Test Cases

### TS-40-1: AuditEvent Dataclass Fields

**Requirement:** 40-REQ-1.1
**Type:** unit
**Description:** `AuditEvent` has all required fields with correct types and
defaults.

**Preconditions:**
- None.

**Input:**
- Create `AuditEvent(run_id="20260312_143000_abc123", event_type=AuditEventType.RUN_START)`.

**Expected:**
- `id` is a UUID, `timestamp` is a datetime, `severity` defaults to `info`,
  `node_id` defaults to `""`, `payload` defaults to `{}`.

**Assertion pseudocode:**
```
event = AuditEvent(run_id="20260312_143000_abc123", event_type=AuditEventType.RUN_START)
ASSERT isinstance(event.id, UUID)
ASSERT isinstance(event.timestamp, datetime)
ASSERT event.severity == AuditSeverity.INFO
ASSERT event.node_id == ""
ASSERT event.session_id == ""
ASSERT event.archetype == ""
ASSERT event.payload == {}
```

### TS-40-2: AuditEventType Enum Completeness

**Requirement:** 40-REQ-1.2
**Type:** unit
**Description:** `AuditEventType` has exactly 19 variants matching the spec.

**Preconditions:**
- None.

**Input:**
- Enumerate all `AuditEventType` members.

**Expected:**
- 19 members with values matching the event type strings.

**Assertion pseudocode:**
```
expected = {"run.start", "run.complete", "run.limit_reached",
    "session.start", "session.complete", "session.fail", "session.retry",
    "task.status_change", "model.escalation", "model.assessment",
    "tool.invocation", "tool.error", "git.merge", "git.conflict",
    "harvest.complete", "fact.extracted", "fact.compacted",
    "knowledge.ingested", "sync.barrier"}
actual = {e.value for e in AuditEventType}
ASSERT actual == expected
```

### TS-40-3: AuditSeverity Enum Values

**Requirement:** 40-REQ-1.3
**Type:** unit
**Description:** `AuditSeverity` has exactly 4 values.

**Preconditions:**
- None.

**Input:**
- Enumerate all `AuditSeverity` members.

**Expected:**
- `{"info", "warning", "error", "critical"}`.

**Assertion pseudocode:**
```
actual = {s.value for s in AuditSeverity}
ASSERT actual == {"info", "warning", "error", "critical"}
```

### TS-40-4: AuditEvent Auto-Populates ID and Timestamp

**Requirement:** 40-REQ-1.4
**Type:** unit
**Description:** Creating an `AuditEvent` auto-generates `id` and `timestamp`.

**Preconditions:**
- None.

**Input:**
- Create two events without specifying `id` or `timestamp`.

**Expected:**
- Each event has a unique UUID and a recent timestamp.

**Assertion pseudocode:**
```
e1 = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
e2 = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
ASSERT e1.id != e2.id
ASSERT (datetime.now(UTC) - e1.timestamp).total_seconds() < 5
```

### TS-40-5: Run ID Format

**Requirement:** 40-REQ-2.1
**Type:** unit
**Description:** `generate_run_id()` produces correctly formatted IDs.

**Preconditions:**
- None.

**Input:**
- Call `generate_run_id()`.

**Expected:**
- Matches pattern `\d{8}_\d{6}_[0-9a-f]{6}`.

**Assertion pseudocode:**
```
import re
run_id = generate_run_id()
ASSERT re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", run_id) is not None
```

### TS-40-6: Run ID Uniqueness

**Requirement:** 40-REQ-2.E1
**Type:** unit
**Description:** Two consecutive `generate_run_id()` calls produce different IDs.

**Preconditions:**
- None.

**Input:**
- Call `generate_run_id()` twice.

**Expected:**
- Different IDs.

**Assertion pseudocode:**
```
id1 = generate_run_id()
id2 = generate_run_id()
ASSERT id1 != id2
```

### TS-40-7: DuckDB Migration Creates Table

**Requirement:** 40-REQ-3.1, 40-REQ-3.2
**Type:** unit
**Description:** Migration v6 creates `audit_events` table with indexes.

**Preconditions:**
- In-memory DuckDB with schema_version table and migrations applied up to v5.

**Input:**
- Apply v6 migration.

**Expected:**
- `audit_events` table exists with correct columns.
- Indexes on `run_id` and `event_type` exist.

**Assertion pseudocode:**
```
apply_v6_migration(conn)
result = conn.execute("SELECT * FROM audit_events LIMIT 0")
columns = {desc[0] for desc in result.description}
ASSERT {"id", "timestamp", "run_id", "event_type", "node_id",
    "session_id", "archetype", "severity", "payload"} <= columns
```

### TS-40-8: Migration Registered in MIGRATIONS List

**Requirement:** 40-REQ-3.3
**Type:** unit
**Description:** v6 migration is in the MIGRATIONS registry.

**Preconditions:**
- None.

**Input:**
- Inspect `MIGRATIONS` list.

**Expected:**
- Contains an entry with `version=6`.

**Assertion pseudocode:**
```
from agent_fox.knowledge.migrations import MIGRATIONS
versions = [m.version for m in MIGRATIONS]
ASSERT 6 in versions
```

### TS-40-9: SessionSink Protocol Has emit_audit_event

**Requirement:** 40-REQ-4.1
**Type:** unit
**Description:** `SessionSink` protocol includes `emit_audit_event` method.

**Preconditions:**
- None.

**Input:**
- Inspect `SessionSink` protocol methods.

**Expected:**
- `emit_audit_event` is a method on the protocol.

**Assertion pseudocode:**
```
ASSERT hasattr(SessionSink, "emit_audit_event")
```

### TS-40-10: SinkDispatcher Dispatches emit_audit_event

**Requirement:** 40-REQ-4.2
**Type:** unit
**Description:** `SinkDispatcher.emit_audit_event()` calls all registered sinks.

**Preconditions:**
- Two mock sinks registered in a `SinkDispatcher`.

**Input:**
- Call `dispatcher.emit_audit_event(event)`.

**Expected:**
- Both mocks received the event.

**Assertion pseudocode:**
```
sink1, sink2 = MockSink(), MockSink()
dispatcher = SinkDispatcher([sink1, sink2])
event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
dispatcher.emit_audit_event(event)
ASSERT sink1.emit_audit_event_called_with == event
ASSERT sink2.emit_audit_event_called_with == event
```

### TS-40-11: SinkDispatcher Swallows Sink Failures

**Requirement:** 40-REQ-4.E1
**Type:** unit
**Description:** If a sink raises on `emit_audit_event`, the dispatcher
logs a warning and continues.

**Preconditions:**
- One failing sink and one working sink registered.

**Input:**
- Call `dispatcher.emit_audit_event(event)`.

**Expected:**
- No exception raised, working sink received the event.

**Assertion pseudocode:**
```
failing_sink = MockSinkThatRaises()
working_sink = MockSink()
dispatcher = SinkDispatcher([failing_sink, working_sink])
dispatcher.emit_audit_event(event)  # does not raise
ASSERT working_sink.emit_audit_event_called_with == event
```

### TS-40-12: DuckDBSink Inserts Audit Event

**Requirement:** 40-REQ-5.1, 40-REQ-5.2
**Type:** unit
**Description:** `DuckDBSink.emit_audit_event()` inserts a row into
`audit_events` with JSON-serialized payload.

**Preconditions:**
- In-memory DuckDB with `audit_events` table created.

**Input:**
- `sink.emit_audit_event(event)` with payload `{"plan_hash": "abc123"}`.

**Expected:**
- One row in `audit_events` with matching fields.
- `payload` column contains valid JSON with `plan_hash`.

**Assertion pseudocode:**
```
event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START,
    payload={"plan_hash": "abc123"})
sink.emit_audit_event(event)
row = conn.execute("SELECT * FROM audit_events WHERE id = ?",
    [str(event.id)]).fetchone()
ASSERT row is not None
ASSERT json.loads(row["payload"])["plan_hash"] == "abc123"
```

### TS-40-13: AuditJsonlSink Creates Directory

**Requirement:** 40-REQ-6.2
**Type:** unit
**Description:** `AuditJsonlSink.__init__` creates the audit directory if
it does not exist.

**Preconditions:**
- Temporary directory without `.agent-fox/audit/` subdirectory.

**Input:**
- Create `AuditJsonlSink(audit_dir, "r1")`.

**Expected:**
- `audit_dir` exists.

**Assertion pseudocode:**
```
audit_dir = tmp_path / ".agent-fox" / "audit"
ASSERT NOT audit_dir.exists()
sink = AuditJsonlSink(audit_dir, "r1")
ASSERT audit_dir.exists()
```

### TS-40-14: AuditJsonlSink Writes JSON Lines

**Requirement:** 40-REQ-6.1, 40-REQ-6.3
**Type:** unit
**Description:** `AuditJsonlSink.emit_audit_event()` appends a valid JSON
line to the file.

**Preconditions:**
- `AuditJsonlSink` initialized with a temp directory.

**Input:**
- Emit two events.

**Expected:**
- File has 2 lines, each parseable as JSON with correct fields.

**Assertion pseudocode:**
```
sink = AuditJsonlSink(tmp_audit_dir, "r1")
sink.emit_audit_event(event1)
sink.emit_audit_event(event2)
lines = (tmp_audit_dir / "audit_r1.jsonl").read_text().strip().split("\n")
ASSERT len(lines) == 2
parsed = json.loads(lines[0])
ASSERT "id" in parsed
ASSERT "timestamp" in parsed
ASSERT "event_type" in parsed
ASSERT "payload" in parsed
```

### TS-40-15: AuditJsonlSink No-Ops for Other Methods

**Requirement:** 40-REQ-6.4
**Type:** unit
**Description:** `AuditJsonlSink` implements other SessionSink methods as
no-ops.

**Preconditions:**
- `AuditJsonlSink` initialized.

**Input:**
- Call `record_session_outcome()`, `record_tool_call()`, `record_tool_error()`,
  `close()`.

**Expected:**
- No exceptions raised, no files written for these methods.

**Assertion pseudocode:**
```
sink = AuditJsonlSink(tmp_audit_dir, "r1")
sink.record_session_outcome(SessionOutcome())  # no-op
sink.record_tool_call(ToolCall())              # no-op
sink.record_tool_error(ToolError())            # no-op
sink.close()                                    # no-op
# No exceptions raised
```

### TS-40-16: AuditJsonlSink Handles Write Failure

**Requirement:** 40-REQ-6.E1
**Type:** unit
**Description:** JSONL write failure logs a warning but does not raise.

**Preconditions:**
- `AuditJsonlSink` with a read-only or invalid path.

**Input:**
- Call `emit_audit_event()`.

**Expected:**
- No exception raised, warning logged.

**Assertion pseudocode:**
```
sink = AuditJsonlSink(Path("/nonexistent/path"), "r1")
sink.emit_audit_event(event)  # does not raise
ASSERT warning_logged("Failed to write audit event")
```

### TS-40-17: Session Start Event Emitted

**Requirement:** 40-REQ-7.1
**Type:** integration
**Description:** A `session.start` event is emitted when a session begins.

**Preconditions:**
- Mocked session lifecycle with sink dispatcher.

**Input:**
- Start a session with archetype="coder", model_id="claude-sonnet-4-6".

**Expected:**
- A `session.start` event with correct payload fields.

**Assertion pseudocode:**
```
events = run_session_and_capture_events(archetype="coder", model_id="claude-sonnet-4-6")
start_events = [e for e in events if e.event_type == AuditEventType.SESSION_START]
ASSERT len(start_events) >= 1
ASSERT start_events[0].payload["archetype"] == "coder"
ASSERT start_events[0].payload["model_id"] == "claude-sonnet-4-6"
ASSERT "prompt_template" in start_events[0].payload
ASSERT "attempt" in start_events[0].payload
```

### TS-40-18: Session Complete Event Emitted

**Requirement:** 40-REQ-7.2
**Type:** integration
**Description:** A `session.complete` event is emitted on successful session.

**Preconditions:**
- Mocked session lifecycle producing a successful result.

**Input:**
- Complete a session successfully.

**Expected:**
- A `session.complete` event with token, cost, and duration fields.

**Assertion pseudocode:**
```
events = run_successful_session_and_capture_events()
complete_events = [e for e in events if e.event_type == AuditEventType.SESSION_COMPLETE]
ASSERT len(complete_events) == 1
payload = complete_events[0].payload
ASSERT "tokens" in payload
ASSERT "cost" in payload
ASSERT "duration_ms" in payload
ASSERT "files_touched" in payload
```

### TS-40-19: Session Fail Event Has Error Severity

**Requirement:** 40-REQ-7.3
**Type:** integration
**Description:** A `session.fail` event has severity `error`.

**Preconditions:**
- Mocked session lifecycle producing a failure.

**Input:**
- Fail a session.

**Expected:**
- A `session.fail` event with severity `error`.

**Assertion pseudocode:**
```
events = run_failing_session_and_capture_events()
fail_events = [e for e in events if e.event_type == AuditEventType.SESSION_FAIL]
ASSERT len(fail_events) == 1
ASSERT fail_events[0].severity == AuditSeverity.ERROR
ASSERT "error_message" in fail_events[0].payload
```

### TS-40-20: Tool Invocation Event With Abbreviated Params

**Requirement:** 40-REQ-8.1, 40-REQ-8.2
**Type:** unit
**Description:** Tool invocation events use `abbreviate_arg` for param_summary.

**Preconditions:**
- Session with tool callback wired.

**Input:**
- Invoke a tool with a long parameter.

**Expected:**
- `tool.invocation` event with abbreviated `param_summary`.

**Assertion pseudocode:**
```
events = invoke_tool_and_capture_events("Read", {"file_path": "/very/long/path"})
tool_events = [e for e in events if e.event_type == AuditEventType.TOOL_INVOCATION]
ASSERT len(tool_events) == 1
ASSERT "param_summary" in tool_events[0].payload
ASSERT len(tool_events[0].payload["param_summary"]) <= 200  # abbreviated
```

### TS-40-21: Run Start Event

**Requirement:** 40-REQ-9.1
**Type:** integration
**Description:** `run.start` event is emitted at orchestrator start.

**Preconditions:**
- Mocked orchestrator with plan.

**Input:**
- Call `orchestrator.execute()`.

**Expected:**
- A `run.start` event with `plan_hash`, `total_nodes`, `parallel`.

**Assertion pseudocode:**
```
events = run_orchestrator_and_capture_events()
start = [e for e in events if e.event_type == AuditEventType.RUN_START]
ASSERT len(start) == 1
ASSERT "plan_hash" in start[0].payload
ASSERT "total_nodes" in start[0].payload
ASSERT "parallel" in start[0].payload
```

### TS-40-22: Run Complete Event

**Requirement:** 40-REQ-9.2
**Type:** integration
**Description:** `run.complete` event is emitted at orchestrator end.

**Preconditions:**
- Mocked orchestrator that completes.

**Input:**
- Complete an orchestrator run.

**Expected:**
- A `run.complete` event with summary fields.

**Assertion pseudocode:**
```
events = run_orchestrator_and_capture_events()
complete = [e for e in events if e.event_type == AuditEventType.RUN_COMPLETE]
ASSERT len(complete) == 1
ASSERT "total_sessions" in complete[0].payload
ASSERT "total_cost" in complete[0].payload
ASSERT "duration_ms" in complete[0].payload
```

### TS-40-23: Run Limit Reached Event

**Requirement:** 40-REQ-9.3
**Type:** unit
**Description:** `run.limit_reached` event has severity `warning`.

**Preconditions:**
- Orchestrator hits a cost or time limit.

**Input:**
- Trigger a limit.

**Expected:**
- A `run.limit_reached` event with severity `warning`.

**Assertion pseudocode:**
```
events = trigger_limit_and_capture_events()
limit_events = [e for e in events if e.event_type == AuditEventType.RUN_LIMIT_REACHED]
ASSERT len(limit_events) == 1
ASSERT limit_events[0].severity == AuditSeverity.WARNING
ASSERT "limit_type" in limit_events[0].payload
```

### TS-40-24: Retention Deletes Old Runs

**Requirement:** 40-REQ-12.1, 40-REQ-12.2
**Type:** unit
**Description:** `enforce_audit_retention()` removes data for old runs.

**Preconditions:**
- 25 runs with events in DuckDB and JSONL files.

**Input:**
- Call `enforce_audit_retention(max_runs=20)`.

**Expected:**
- 5 oldest runs deleted from DuckDB and JSONL files removed.

**Assertion pseudocode:**
```
create_25_runs_with_events(conn, audit_dir)
enforce_audit_retention(audit_dir, conn, max_runs=20)
remaining = conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
ASSERT len(remaining) == 20
jsonl_files = list(audit_dir.glob("audit_*.jsonl"))
ASSERT len(jsonl_files) == 20
```

### TS-40-25: Retention Skips When Under Limit

**Requirement:** 40-REQ-12.E1
**Type:** unit
**Description:** No data deleted when run count is at or below the limit.

**Preconditions:**
- 10 runs (below default limit of 20).

**Input:**
- Call `enforce_audit_retention(max_runs=20)`.

**Expected:**
- All 10 runs retained.

**Assertion pseudocode:**
```
create_10_runs_with_events(conn, audit_dir)
enforce_audit_retention(audit_dir, conn, max_runs=20)
remaining = conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
ASSERT len(remaining) == 10
```

### TS-40-26: CLI List Runs

**Requirement:** 40-REQ-13.1, 40-REQ-13.2
**Type:** integration
**Description:** `agent-fox audit --list-runs` shows available runs.

**Preconditions:**
- DuckDB with 3 runs of events.

**Input:**
- Invoke `audit --list-runs`.

**Expected:**
- Output shows 3 run IDs with timestamps and event counts.

**Assertion pseudocode:**
```
result = invoke_cli(["audit", "--list-runs"])
ASSERT result.exit_code == 0
ASSERT "20260312" in result.output  # run ID date prefix
lines = result.output.strip().split("\n")
ASSERT len(lines) >= 3  # header + 3 runs (or 3 data lines)
```

### TS-40-27: CLI Filter by Run

**Requirement:** 40-REQ-13.3
**Type:** integration
**Description:** `agent-fox audit --run <id>` filters to that run.

**Preconditions:**
- DuckDB with 2 runs.

**Input:**
- Invoke `audit --run <run_id_1>`.

**Expected:**
- Only events from run_id_1 shown.

**Assertion pseudocode:**
```
result = invoke_cli(["audit", "--run", run_id_1])
ASSERT result.exit_code == 0
ASSERT run_id_1 in result.output
ASSERT run_id_2 NOT in result.output
```

### TS-40-28: CLI Filter by Event Type

**Requirement:** 40-REQ-13.4
**Type:** integration
**Description:** `agent-fox audit --event-type session.complete` filters events.

**Preconditions:**
- DuckDB with mixed event types.

**Input:**
- Invoke `audit --event-type session.complete`.

**Expected:**
- Only `session.complete` events shown.

**Assertion pseudocode:**
```
result = invoke_cli(["audit", "--event-type", "session.complete"])
ASSERT result.exit_code == 0
# All displayed events are session.complete
```

### TS-40-29: CLI Filter by Since

**Requirement:** 40-REQ-13.6
**Type:** integration
**Description:** `agent-fox audit --since 24h` filters by time.

**Preconditions:**
- Events from 48h ago and 1h ago.

**Input:**
- Invoke `audit --since 24h`.

**Expected:**
- Only events from last 24 hours shown.

**Assertion pseudocode:**
```
result = invoke_cli(["audit", "--since", "24h"])
ASSERT result.exit_code == 0
# Old events not present
```

### TS-40-30: CLI JSON Output

**Requirement:** 40-REQ-13.7
**Type:** integration
**Description:** `agent-fox --json audit` produces valid JSON output.

**Preconditions:**
- DuckDB with events.

**Input:**
- Invoke `--json audit`.

**Expected:**
- Output is valid JSON.

**Assertion pseudocode:**
```
result = invoke_cli(["--json", "audit"])
ASSERT result.exit_code == 0
data = json.loads(result.output)
ASSERT isinstance(data, (list, dict))
```

### TS-40-31: CLI No Events Returns Empty

**Requirement:** 40-REQ-13.E1
**Type:** unit
**Description:** Empty filter result exits with code 0.

**Preconditions:**
- DuckDB with no events.

**Input:**
- Invoke `audit`.

**Expected:**
- Exit code 0, empty result displayed.

**Assertion pseudocode:**
```
result = invoke_cli(["audit"])
ASSERT result.exit_code == 0
```

### TS-40-32: CLI Missing Database

**Requirement:** 40-REQ-13.E2
**Type:** unit
**Description:** Missing DuckDB shows informative message.

**Preconditions:**
- No DuckDB file.

**Input:**
- Invoke `audit`.

**Expected:**
- Message about no audit data, exit code 0.

**Assertion pseudocode:**
```
result = invoke_cli(["audit"], with_db=False)
ASSERT result.exit_code == 0
ASSERT "no audit data" in result.output.lower()
```

### TS-40-33: Reporting Reads From DuckDB

**Requirement:** 40-REQ-14.1
**Type:** integration
**Description:** `status.py` reads session metrics from `audit_events`.

**Preconditions:**
- DuckDB with `session.complete` events.

**Input:**
- Call `build_status_report_from_audit(conn)`.

**Expected:**
- Report contains correct session counts, token totals, and costs.

**Assertion pseudocode:**
```
insert_session_complete_events(conn, count=5, total_tokens=10000)
report = build_status_report_from_audit(conn)
ASSERT report.total_sessions == 5
ASSERT report.total_input_tokens > 0
```

### TS-40-34: Reporting Falls Back to state.jsonl

**Requirement:** 40-REQ-14.3
**Type:** unit
**Description:** When DuckDB is unavailable, reporting falls back to
state.jsonl parsing.

**Preconditions:**
- No DuckDB connection, but state.jsonl exists.

**Input:**
- Call status report builder.

**Expected:**
- Report built from state.jsonl data.

**Assertion pseudocode:**
```
report = build_status_report(conn=None, state_path=state_jsonl_path)
ASSERT report is not None
ASSERT report.total_sessions > 0
```

## Edge Case Tests

### TS-40-E1: Empty Optional Fields

**Requirement:** 40-REQ-1.E1
**Type:** unit
**Description:** Optional fields default to empty strings.

**Preconditions:**
- None.

**Input:**
- Create `AuditEvent` without `node_id`, `session_id`, `archetype`.

**Expected:**
- All three are empty strings.

**Assertion pseudocode:**
```
event = AuditEvent(run_id="r1", event_type=AuditEventType.RUN_START)
ASSERT event.node_id == ""
ASSERT event.session_id == ""
ASSERT event.archetype == ""
```

### TS-40-E2: Retention JSONL Deletion Failure

**Requirement:** 40-REQ-12.E2
**Type:** unit
**Description:** JSONL deletion failure logs warning and continues.

**Preconditions:**
- Read-only JSONL file.

**Input:**
- Call `enforce_audit_retention()` with run to delete.

**Expected:**
- DuckDB rows deleted, warning logged for JSONL failure.

**Assertion pseudocode:**
```
make_jsonl_readonly(oldest_run_file)
enforce_audit_retention(audit_dir, conn, max_runs=1)
ASSERT warning_logged("Failed to delete")
# DuckDB cleanup still happened
remaining = conn.execute("SELECT DISTINCT run_id FROM audit_events").fetchall()
ASSERT len(remaining) == 1
```

## Property Test Cases

### TS-40-P1: Run ID Format Invariant

**Property:** Property 2 from design.md (partial)
**Validates:** 40-REQ-2.1, 40-REQ-2.E1
**Type:** property
**Description:** All generated run IDs match the expected format and are unique.

**For any:** 100 consecutive calls to `generate_run_id()`
**Invariant:** All match `\d{8}_\d{6}_[0-9a-f]{6}` and all are distinct.

**Assertion pseudocode:**
```
import re
ids = [generate_run_id() for _ in range(100)]
ASSERT len(set(ids)) == 100
FOR EACH id IN ids:
    ASSERT re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", id)
```

### TS-40-P2: Event Serialization Round-Trip

**Property:** Property 4 from design.md
**Validates:** 40-REQ-1.1, 40-REQ-6.3
**Type:** property
**Description:** Serializing an `AuditEvent` to JSON and back preserves fields.

**For any:** random `AuditEvent` with random payload dicts
**Invariant:** `deserialize(serialize(event))` has equal `id`, `run_id`,
`event_type`, `severity`, and `payload`.

**Assertion pseudocode:**
```
FOR ANY event IN random_audit_events():
    serialized = event_to_json(event)
    deserialized = event_from_json(serialized)
    ASSERT str(deserialized.id) == str(event.id)
    ASSERT deserialized.run_id == event.run_id
    ASSERT deserialized.event_type == event.event_type
    ASSERT deserialized.severity == event.severity
    ASSERT deserialized.payload == event.payload
```

### TS-40-P3: Severity Classification Correctness

**Property:** Property 6 from design.md
**Validates:** 40-REQ-7.3, 40-REQ-9.3, 40-REQ-11.2
**Type:** property
**Description:** Event types have correct default severities.

**For any:** all event types
**Invariant:** `session.fail` -> `error`, `run.limit_reached` -> `warning`,
`git.conflict` -> `warning`, all others -> `info`.

**Assertion pseudocode:**
```
error_types = {AuditEventType.SESSION_FAIL}
warning_types = {AuditEventType.RUN_LIMIT_REACHED, AuditEventType.GIT_CONFLICT}
FOR EACH event_type IN AuditEventType:
    severity = default_severity_for(event_type)
    IF event_type IN error_types:
        ASSERT severity == AuditSeverity.ERROR
    ELIF event_type IN warning_types:
        ASSERT severity == AuditSeverity.WARNING
    ELSE:
        ASSERT severity == AuditSeverity.INFO
```

### TS-40-P4: Dual-Write Consistency

**Property:** Property 3 from design.md
**Validates:** 40-REQ-5.1, 40-REQ-6.1
**Type:** property
**Description:** Events written to DuckDB and JSONL are identical.

**For any:** N random audit events (1-50)
**Invariant:** DuckDB row count == JSONL line count == N, and all event IDs
match between stores.

**Assertion pseudocode:**
```
FOR ANY events IN lists(random_audit_events(), min_size=1, max_size=50):
    dispatcher = SinkDispatcher([duckdb_sink, jsonl_sink])
    FOR EACH event IN events:
        dispatcher.emit_audit_event(event)
    db_ids = set(query_all_event_ids_from_db(conn))
    jsonl_ids = set(parse_all_event_ids_from_jsonl(file_path))
    ASSERT db_ids == jsonl_ids
    ASSERT len(db_ids) == len(events)
```

### TS-40-P5: Retention Bound

**Property:** Property 5 from design.md
**Validates:** 40-REQ-12.1, 40-REQ-12.2
**Type:** property
**Description:** After retention enforcement, at most max_runs are retained.

**For any:** N runs (1-50), max_runs (1-30)
**Invariant:** `remaining_runs <= min(N, max_runs)`.

**Assertion pseudocode:**
```
FOR ANY n_runs, max_runs IN valid_retention_combos():
    create_n_runs(conn, audit_dir, n_runs)
    enforce_audit_retention(audit_dir, conn, max_runs)
    remaining = count_distinct_runs(conn)
    ASSERT remaining <= max_runs
    ASSERT remaining == min(n_runs, max_runs)
```

### TS-40-P6: Event Completeness Per Run

**Property:** Property 1 from design.md
**Validates:** 40-REQ-9.1, 40-REQ-9.2
**Type:** property
**Description:** Every run has exactly one `run.start` and one `run.complete`.

**For any:** completed orchestrator run
**Invariant:** Exactly 1 `run.start` and 1 `run.complete` per run_id.

**Assertion pseudocode:**
```
FOR ANY run IN completed_runs():
    events = query_events_for_run(conn, run.run_id)
    starts = [e for e in events if e.event_type == "run.start"]
    completes = [e for e in events if e.event_type == "run.complete"]
    ASSERT len(starts) == 1
    ASSERT len(completes) == 1
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 40-REQ-1.1 | TS-40-1 | unit |
| 40-REQ-1.2 | TS-40-2 | unit |
| 40-REQ-1.3 | TS-40-3 | unit |
| 40-REQ-1.4 | TS-40-4 | unit |
| 40-REQ-1.E1 | TS-40-E1 | unit |
| 40-REQ-2.1 | TS-40-5 | unit |
| 40-REQ-2.2 | TS-40-21 | integration |
| 40-REQ-2.E1 | TS-40-6 | unit |
| 40-REQ-3.1 | TS-40-7 | unit |
| 40-REQ-3.2 | TS-40-7 | unit |
| 40-REQ-3.3 | TS-40-8 | unit |
| 40-REQ-4.1 | TS-40-9 | unit |
| 40-REQ-4.2 | TS-40-10 | unit |
| 40-REQ-4.E1 | TS-40-11 | unit |
| 40-REQ-5.1 | TS-40-12 | unit |
| 40-REQ-5.2 | TS-40-12 | unit |
| 40-REQ-6.1 | TS-40-14 | unit |
| 40-REQ-6.2 | TS-40-13 | unit |
| 40-REQ-6.3 | TS-40-14 | unit |
| 40-REQ-6.4 | TS-40-15 | unit |
| 40-REQ-6.E1 | TS-40-16 | unit |
| 40-REQ-7.1 | TS-40-17 | integration |
| 40-REQ-7.2 | TS-40-18 | integration |
| 40-REQ-7.3 | TS-40-19 | integration |
| 40-REQ-7.4 | TS-40-17 | integration |
| 40-REQ-8.1 | TS-40-20 | unit |
| 40-REQ-8.2 | TS-40-20 | unit |
| 40-REQ-8.3 | TS-40-20 | unit |
| 40-REQ-9.1 | TS-40-21 | integration |
| 40-REQ-9.2 | TS-40-22 | integration |
| 40-REQ-9.3 | TS-40-23 | unit |
| 40-REQ-9.4 | TS-40-21 | integration |
| 40-REQ-9.5 | TS-40-21 | integration |
| 40-REQ-10.1 | TS-40-21 | integration |
| 40-REQ-10.2 | TS-40-21 | integration |
| 40-REQ-11.1 | TS-40-21 | integration |
| 40-REQ-11.2 | TS-40-21 | integration |
| 40-REQ-11.3 | TS-40-21 | integration |
| 40-REQ-11.4 | TS-40-21 | integration |
| 40-REQ-11.5 | TS-40-21 | integration |
| 40-REQ-11.6 | TS-40-21 | integration |
| 40-REQ-12.1 | TS-40-24 | unit |
| 40-REQ-12.2 | TS-40-24 | unit |
| 40-REQ-12.E1 | TS-40-25 | unit |
| 40-REQ-12.E2 | TS-40-E2 | unit |
| 40-REQ-13.1 | TS-40-26 | integration |
| 40-REQ-13.2 | TS-40-26 | integration |
| 40-REQ-13.3 | TS-40-27 | integration |
| 40-REQ-13.4 | TS-40-28 | integration |
| 40-REQ-13.5 | TS-40-27 | integration |
| 40-REQ-13.6 | TS-40-29 | integration |
| 40-REQ-13.7 | TS-40-30 | integration |
| 40-REQ-13.E1 | TS-40-31 | unit |
| 40-REQ-13.E2 | TS-40-32 | unit |
| 40-REQ-14.1 | TS-40-33 | integration |
| 40-REQ-14.2 | TS-40-33 | integration |
| 40-REQ-14.3 | TS-40-34 | unit |
| Property 1 | TS-40-P6 | property |
| Property 2 | TS-40-P1 | property |
| Property 3 | TS-40-P4 | property |
| Property 4 | TS-40-P2 | property |
| Property 5 | TS-40-P5 | property |
| Property 6 | TS-40-P3 | property |
