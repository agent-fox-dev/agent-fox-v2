# Test Specification: DuckDB Knowledge Store

## Overview

Tests for the DuckDB knowledge store infrastructure: database lifecycle,
schema creation and versioning, SessionSink protocol, DuckDB sink, JSONL
sink, and graceful degradation. Tests map to requirements in `requirements.md`
and correctness properties in `design.md`.

All DuckDB tests use in-memory databases (`duckdb.connect(":memory:")`) or
temporary files via `tmp_path`. No network access is required.

## Test Cases

### TS-11-1: Database opens and creates schema

**Requirement:** 11-REQ-1.1, 11-REQ-2.1
**Type:** unit
**Description:** Verify that opening a KnowledgeDB creates the database file
and all schema tables.

**Preconditions:**
- A temporary directory with no existing database file.

**Input:**
- `KnowledgeDB(config)` with `store_path` pointing to `tmp_path / "test.duckdb"`.
- Call `db.open()`.

**Expected:**
- Database file exists at the configured path.
- Tables `schema_version`, `memory_facts`, `memory_embeddings`,
  `session_outcomes`, `fact_causes`, `tool_calls`, `tool_errors` all exist.

**Assertion pseudocode:**
```
db = KnowledgeDB(config_with_tmp_path)
db.open()
tables = db.connection.execute("SHOW TABLES").fetchall()
table_names = {row[0] for row in tables}
ASSERT "schema_version" IN table_names
ASSERT "memory_facts" IN table_names
ASSERT "memory_embeddings" IN table_names
ASSERT "session_outcomes" IN table_names
ASSERT "fact_causes" IN table_names
ASSERT "tool_calls" IN table_names
ASSERT "tool_errors" IN table_names
db.close()
```

---

### TS-11-2: Schema version recorded on creation

**Requirement:** 11-REQ-2.2
**Type:** unit
**Description:** Verify that initial schema creation records version 1 in the
schema_version table.

**Preconditions:**
- Fresh database opened via KnowledgeDB.

**Input:**
- Query `schema_version` table after `open()`.

**Expected:**
- Exactly one row with `version = 1`.
- `applied_at` is a valid timestamp.
- `description` is a non-empty string.

**Assertion pseudocode:**
```
db = KnowledgeDB(config_with_tmp_path)
db.open()
rows = db.connection.execute("SELECT version, applied_at, description FROM schema_version").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0][0] == 1
ASSERT rows[0][1] IS NOT None
ASSERT len(rows[0][2]) > 0
db.close()
```

---

### TS-11-3: Database connection closes cleanly

**Requirement:** 11-REQ-1.3
**Type:** unit
**Description:** Verify that close() releases the connection and subsequent
access raises an error.

**Preconditions:**
- An open KnowledgeDB.

**Input:**
- Call `db.close()`, then access `db.connection`.

**Expected:**
- `KnowledgeStoreError` raised on property access after close.

**Assertion pseudocode:**
```
db = KnowledgeDB(config_with_tmp_path)
db.open()
db.close()
ASSERT_RAISES KnowledgeStoreError FROM db.connection
```

---

### TS-11-4: Context manager opens and closes

**Requirement:** 11-REQ-1.1, 11-REQ-1.3
**Type:** unit
**Description:** Verify that KnowledgeDB works as a context manager.

**Preconditions:**
- Temporary path for database.

**Input:**
- Use `with KnowledgeDB(config) as db:` and verify access inside and after.

**Expected:**
- Connection is accessible inside the `with` block.
- `KnowledgeStoreError` raised after the block exits.

**Assertion pseudocode:**
```
with KnowledgeDB(config) as db:
    ASSERT db.connection IS NOT None
    tables = db.connection.execute("SHOW TABLES").fetchall()
    ASSERT len(tables) > 0
ASSERT_RAISES KnowledgeStoreError FROM db.connection
```

---

### TS-11-5: Migration applies pending migrations

**Requirement:** 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3
**Type:** unit
**Description:** Verify that a registered migration is applied and recorded
in schema_version.

**Preconditions:**
- In-memory DuckDB with schema_version at version 1.
- A test migration registered at version 2.

**Input:**
- Call `apply_pending_migrations(conn)` with a migration that adds a column.

**Expected:**
- The migration's DDL has been applied (new column exists).
- `schema_version` has a row for version 2.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
# Create schema_version and seed version 1
create_schema(conn)

# Register a test migration
test_migration = Migration(
    version=2,
    description="add test_col to session_outcomes",
    apply=lambda c: c.execute("ALTER TABLE session_outcomes ADD COLUMN test_col TEXT"),
)
# Temporarily add to MIGRATIONS and apply
apply_pending_migrations(conn)

rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
ASSERT (2,) IN rows
# Verify column exists
cols = conn.execute("DESCRIBE session_outcomes").fetchall()
col_names = {row[0] for row in cols}
ASSERT "test_col" IN col_names
```

---

### TS-11-6: Schema initialization is idempotent

**Requirement:** 11-REQ-2.1, 11-REQ-2.2
**Type:** unit
**Description:** Verify that opening the same database twice does not
duplicate tables or version rows.

**Preconditions:**
- A temporary database file.

**Input:**
- Open, close, then open again.

**Expected:**
- Schema version table still has exactly one row (version 1).
- All tables exist, no duplicates.

**Assertion pseudocode:**
```
config = config_with_tmp_path
db = KnowledgeDB(config)
db.open()
db.close()

db2 = KnowledgeDB(config)
db2.open()
rows = db2.connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()
ASSERT rows[0] == 1
db2.close()
```

---

### TS-11-7: DuckDB sink records session outcome (always-on)

**Requirement:** 11-REQ-5.1, 11-REQ-5.2
**Type:** unit
**Description:** Verify that the DuckDB sink writes a session outcome row
regardless of debug mode.

**Preconditions:**
- In-memory DuckDB with schema created.
- DuckDBSink with `debug=False`.

**Input:**
- Call `record_session_outcome(outcome)` with a SessionOutcome.

**Expected:**
- One row in `session_outcomes` matching the outcome data.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
create_schema(conn)
sink = DuckDBSink(conn, debug=False)

outcome = SessionOutcome(
    spec_name="test_spec",
    task_group="1",
    node_id="test_spec/1",
    touched_paths=["src/main.py"],
    status="completed",
    input_tokens=1000,
    output_tokens=500,
    duration_ms=30000,
)
sink.record_session_outcome(outcome)

rows = conn.execute("SELECT spec_name, status FROM session_outcomes").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0][0] == "test_spec"
ASSERT rows[0][1] == "completed"
```

---

### TS-11-8: DuckDB sink records tool signals only in debug

**Requirement:** 11-REQ-5.3, 11-REQ-5.4
**Type:** unit
**Description:** Verify that tool calls and errors are written only when
debug=True, and are no-ops when debug=False.

**Preconditions:**
- In-memory DuckDB with schema created.

**Input:**
- DuckDBSink with `debug=False`: call `record_tool_call` and
  `record_tool_error`.
- DuckDBSink with `debug=True`: call `record_tool_call` and
  `record_tool_error`.

**Expected:**
- With debug=False: `tool_calls` and `tool_errors` have 0 rows.
- With debug=True: `tool_calls` and `tool_errors` each have 1 row.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
create_schema(conn)

# debug=False: no-op
sink_off = DuckDBSink(conn, debug=False)
sink_off.record_tool_call(ToolCall(tool_name="bash"))
sink_off.record_tool_error(ToolError(tool_name="bash"))
ASSERT conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0
ASSERT conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == 0

# debug=True: writes
sink_on = DuckDBSink(conn, debug=True)
sink_on.record_tool_call(ToolCall(tool_name="bash"))
sink_on.record_tool_error(ToolError(tool_name="bash"))
ASSERT conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 1
ASSERT conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == 1
```

---

### TS-11-9: DuckDB sink handles multiple touched paths

**Requirement:** 11-REQ-5.2
**Type:** unit
**Description:** Verify that a session outcome with multiple touched paths
creates one row per path.

**Preconditions:**
- In-memory DuckDB with schema created.

**Input:**
- SessionOutcome with `touched_paths=["a.py", "b.py", "c.py"]`.

**Expected:**
- 3 rows in `session_outcomes`, all sharing the same id, spec_name, status,
  but with different `touched_path` values.

**Assertion pseudocode:**
```
outcome = SessionOutcome(
    spec_name="multi",
    touched_paths=["a.py", "b.py", "c.py"],
    status="completed",
)
sink.record_session_outcome(outcome)

rows = conn.execute("SELECT touched_path FROM session_outcomes ORDER BY touched_path").fetchall()
ASSERT len(rows) == 3
ASSERT [r[0] for r in rows] == ["a.py", "b.py", "c.py"]
```

---

### TS-11-10: JSONL sink writes events to file

**Requirement:** 11-REQ-6.1, 11-REQ-6.2
**Type:** unit
**Description:** Verify that the JSONL sink writes all event types as JSON
lines.

**Preconditions:**
- Temporary directory via `tmp_path`.

**Input:**
- Create a JsonlSink, record a session outcome, a tool call, and a tool error.

**Expected:**
- A JSONL file exists in the directory.
- File contains 3 lines, each valid JSON with an `event_type` field.

**Assertion pseudocode:**
```
sink = JsonlSink(directory=tmp_path, session_id="test-session")
sink.record_session_outcome(SessionOutcome(spec_name="s1", status="completed"))
sink.record_tool_call(ToolCall(tool_name="bash"))
sink.record_tool_error(ToolError(tool_name="read"))
sink.close()

jsonl_files = list(tmp_path.glob("*.jsonl"))
ASSERT len(jsonl_files) == 1

lines = jsonl_files[0].read_text().strip().split("\n")
ASSERT len(lines) == 3
FOR line IN lines:
    data = json.loads(line)
    ASSERT "event_type" IN data
```

---

### TS-11-11: SinkDispatcher dispatches to multiple sinks

**Requirement:** 11-REQ-4.3
**Type:** unit
**Description:** Verify that the dispatcher calls all sinks for each event.

**Preconditions:**
- Two mock sinks implementing SessionSink.

**Input:**
- Add both sinks to a SinkDispatcher.
- Call `record_session_outcome`.

**Expected:**
- Both mock sinks have their `record_session_outcome` called exactly once.

**Assertion pseudocode:**
```
mock1 = MockSink()
mock2 = MockSink()
dispatcher = SinkDispatcher([mock1, mock2])
dispatcher.record_session_outcome(SessionOutcome(status="completed"))
ASSERT mock1.outcomes_received == 1
ASSERT mock2.outcomes_received == 1
```

---

### TS-11-12: SessionSink protocol structural typing

**Requirement:** 11-REQ-4.1, 11-REQ-5.1, 11-REQ-6.1
**Type:** unit
**Description:** Verify that DuckDBSink and JsonlSink satisfy the SessionSink
protocol via isinstance checks.

**Preconditions:** None.

**Input:**
- `isinstance(DuckDBSink(...), SessionSink)` and
  `isinstance(JsonlSink(...), SessionSink)`.

**Expected:**
- Both return True.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
ASSERT isinstance(DuckDBSink(conn), SessionSink)
ASSERT isinstance(JsonlSink(tmp_path), SessionSink)
```

## Property Test Cases

### TS-11-P1: Schema initialization idempotency

**Property:** Property 1 from design.md
**Validates:** 11-REQ-2.1, 11-REQ-2.2
**Type:** property
**Description:** Opening and initializing the same database N times produces
identical schema state.

**For any:** N in [1, 5]
**Invariant:** After N open/close cycles, `schema_version` has exactly 1 row
with version 1, and all 7 tables exist.

**Assertion pseudocode:**
```
FOR ANY n IN range(1, 6):
    config = config_with_tmp_path
    FOR i IN range(n):
        db = KnowledgeDB(config)
        db.open()
        db.close()
    db = KnowledgeDB(config)
    db.open()
    ASSERT db.connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
    tables = {r[0] for r in db.connection.execute("SHOW TABLES").fetchall()}
    ASSERT len(tables) == 7
    db.close()
```

---

### TS-11-P2: Migration version monotonicity

**Property:** Property 2 from design.md
**Validates:** 11-REQ-3.1, 11-REQ-3.3
**Type:** property
**Description:** Schema version is strictly increasing after migrations.

**For any:** sequence of 1-3 migrations
**Invariant:** The versions in `schema_version` are strictly increasing.

**Assertion pseudocode:**
```
FOR ANY migration_count IN [1, 2, 3]:
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    apply_test_migrations(conn, count=migration_count)
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_version ORDER BY version"
    ).fetchall()]
    FOR i IN range(1, len(versions)):
        ASSERT versions[i] > versions[i-1]
```

---

### TS-11-P3: Sink protocol compliance

**Property:** Property 3 from design.md
**Validates:** 11-REQ-4.1, 11-REQ-5.1, 11-REQ-6.1
**Type:** property
**Description:** Both sink implementations satisfy the SessionSink protocol.

**For any:** sink class in [DuckDBSink, JsonlSink]
**Invariant:** `isinstance(instance, SessionSink)` is True.

**Assertion pseudocode:**
```
FOR ANY SinkClass IN [DuckDBSink, JsonlSink]:
    instance = create_instance(SinkClass)
    ASSERT isinstance(instance, SessionSink)
```

---

### TS-11-P4: Debug gating invariant

**Property:** Property 5 from design.md
**Validates:** 11-REQ-5.3, 11-REQ-5.4
**Type:** property
**Description:** Tool signal tables are empty after writes with debug=False.

**For any:** N tool calls and M tool errors (1 <= N, M <= 10)
**Invariant:** `tool_calls` count = 0 and `tool_errors` count = 0 when
debug=False.

**Assertion pseudocode:**
```
FOR ANY n IN range(1, 11), m IN range(1, 11):
    conn = duckdb.connect(":memory:")
    create_schema(conn)
    sink = DuckDBSink(conn, debug=False)
    FOR _ IN range(n):
        sink.record_tool_call(ToolCall(tool_name="test"))
    FOR _ IN range(m):
        sink.record_tool_error(ToolError(tool_name="test"))
    ASSERT conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0
    ASSERT conn.execute("SELECT COUNT(*) FROM tool_errors").fetchone()[0] == 0
```

## Edge Case Tests

### TS-11-E1: Parent directory created automatically

**Requirement:** 11-REQ-1.E1
**Type:** unit
**Description:** Verify that KnowledgeDB creates missing parent directories.

**Preconditions:**
- `tmp_path / "deep" / "nested" / "dir"` does not exist.

**Input:**
- Open KnowledgeDB with store_path pointing into the nested directory.

**Expected:**
- Database file is created successfully.
- Parent directories exist.

**Assertion pseudocode:**
```
nested = tmp_path / "deep" / "nested" / "dir" / "knowledge.duckdb"
config = KnowledgeConfig(store_path=str(nested))
db = KnowledgeDB(config)
db.open()
ASSERT nested.exists()
db.close()
```

---

### TS-11-E2: Corrupted database degrades gracefully

**Requirement:** 11-REQ-7.1
**Type:** unit
**Description:** Verify that a corrupted database file causes
open_knowledge_store to return None instead of raising.

**Preconditions:**
- A file at the database path containing random bytes (not a valid DuckDB).

**Input:**
- Call `open_knowledge_store(config)`.

**Expected:**
- Returns None.
- No exception raised to the caller.

**Assertion pseudocode:**
```
db_path = tmp_path / "knowledge.duckdb"
db_path.write_bytes(b"this is not a duckdb file")
config = KnowledgeConfig(store_path=str(db_path))
result = open_knowledge_store(config)
ASSERT result IS None
```

---

### TS-11-E3: DuckDB sink write failure is non-fatal

**Requirement:** 11-REQ-5.E1
**Type:** unit
**Description:** Verify that a write failure in the DuckDB sink is logged
but does not raise.

**Preconditions:**
- DuckDB connection that has been closed (simulating failure).

**Input:**
- Call `record_session_outcome` on a sink with a closed connection.

**Expected:**
- No exception raised.
- Warning logged.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
create_schema(conn)
sink = DuckDBSink(conn, debug=False)
conn.close()  # force failure

# Should not raise
sink.record_session_outcome(SessionOutcome(status="completed"))
# Verify warning was logged (check caplog or mock logger)
```

---

### TS-11-E4: SinkDispatcher isolates sink failures

**Requirement:** 11-REQ-4.3
**Type:** unit
**Description:** Verify that a failing sink does not prevent other sinks
from receiving events.

**Preconditions:**
- A sink that always raises RuntimeError.
- A normal mock sink.

**Input:**
- Dispatch a session outcome through both.

**Expected:**
- The failing sink's error is logged.
- The mock sink still receives the outcome.

**Assertion pseudocode:**
```
failing_sink = FailingSink()  # raises RuntimeError on every method
mock_sink = MockSink()
dispatcher = SinkDispatcher([failing_sink, mock_sink])
dispatcher.record_session_outcome(SessionOutcome(status="completed"))
ASSERT mock_sink.outcomes_received == 1
```

---

### TS-11-E5: Migration failure raises KnowledgeStoreError

**Requirement:** 11-REQ-3.E1
**Type:** unit
**Description:** Verify that a failing migration raises KnowledgeStoreError
with version information.

**Preconditions:**
- In-memory DuckDB with schema at version 1.
- A migration at version 2 that executes invalid SQL.

**Input:**
- Call `apply_pending_migrations(conn)`.

**Expected:**
- `KnowledgeStoreError` raised.
- Error message contains the version number (2).

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
create_schema(conn)
bad_migration = Migration(
    version=2,
    description="bad migration",
    apply=lambda c: c.execute("INVALID SQL"),
)
# Register and apply
ASSERT_RAISES KnowledgeStoreError FROM apply_pending_migrations(conn)
ASSERT "2" IN str(error) OR "version" IN str(error).lower()
```

---

### TS-11-E6: JSONL sink handles empty touched_paths

**Requirement:** 11-REQ-6.2
**Type:** unit
**Description:** Verify that the JSONL sink handles a session outcome with
no touched paths.

**Preconditions:**
- Temporary directory.

**Input:**
- Record a SessionOutcome with `touched_paths=[]`.

**Expected:**
- One JSON line written with `touched_paths` as an empty list.

**Assertion pseudocode:**
```
sink = JsonlSink(directory=tmp_path, session_id="test")
sink.record_session_outcome(SessionOutcome(status="failed", touched_paths=[]))
sink.close()

lines = list(tmp_path.glob("*.jsonl"))[0].read_text().strip().split("\n")
ASSERT len(lines) == 1
data = json.loads(lines[0])
ASSERT data["touched_paths"] == []
```

---

### TS-11-E7: DuckDB sink handles empty touched_paths

**Requirement:** 11-REQ-5.2
**Type:** unit
**Description:** Verify that a session outcome with no touched paths creates
one row with NULL touched_path.

**Preconditions:**
- In-memory DuckDB with schema created.

**Input:**
- Record a SessionOutcome with `touched_paths=[]`.

**Expected:**
- One row in `session_outcomes` with `touched_path IS NULL`.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
create_schema(conn)
sink = DuckDBSink(conn, debug=False)
sink.record_session_outcome(SessionOutcome(status="failed", touched_paths=[]))

rows = conn.execute("SELECT touched_path FROM session_outcomes").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0][0] IS None
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 11-REQ-1.1 | TS-11-1, TS-11-4 | unit |
| 11-REQ-1.2 | TS-11-1 | unit |
| 11-REQ-1.3 | TS-11-3, TS-11-4 | unit |
| 11-REQ-1.E1 | TS-11-E1 | unit |
| 11-REQ-1.E2 | TS-11-3 | unit |
| 11-REQ-2.1 | TS-11-1, TS-11-6 | unit |
| 11-REQ-2.2 | TS-11-2, TS-11-6 | unit |
| 11-REQ-2.3 | TS-11-1 | unit |
| 11-REQ-3.1 | TS-11-5 | unit |
| 11-REQ-3.2 | TS-11-5 | unit |
| 11-REQ-3.3 | TS-11-5 | unit |
| 11-REQ-3.E1 | TS-11-E5 | unit |
| 11-REQ-4.1 | TS-11-12 | unit |
| 11-REQ-4.2 | TS-11-11 | unit |
| 11-REQ-4.3 | TS-11-11, TS-11-E4 | unit |
| 11-REQ-5.1 | TS-11-7, TS-11-12 | unit |
| 11-REQ-5.2 | TS-11-7, TS-11-9, TS-11-E7 | unit |
| 11-REQ-5.3 | TS-11-8 | unit |
| 11-REQ-5.4 | TS-11-8 | unit |
| 11-REQ-5.E1 | TS-11-E3 | unit |
| 11-REQ-6.1 | TS-11-10, TS-11-12 | unit |
| 11-REQ-6.2 | TS-11-10, TS-11-E6 | unit |
| 11-REQ-6.3 | (enforced by orchestrator attachment logic, not tested here) | -- |
| 11-REQ-7.1 | TS-11-E2 | unit |
| 11-REQ-7.2 | TS-11-E3 | unit |
| 11-REQ-7.3 | TS-11-E2 | unit |
| Property 1 | TS-11-P1 | property |
| Property 2 | TS-11-P2 | property |
| Property 3 | TS-11-P3 | property |
| Property 5 | TS-11-P4 | property |
