# Test Specification: DB-Based Plan State

## Overview

Tests validate plan persistence round-trips, node status management,
session history unification, run tracking, file removal, and concurrent
read access. Each acceptance criterion maps to at least one test case;
each correctness property maps to a property-based test.

## Test Cases

### TS-105-1: Plan nodes round-trip

**Requirement:** 105-REQ-1.1, 105-REQ-1.2
**Type:** unit
**Description:** Verify a TaskGraph persisted to DuckDB loads back
identically.

**Preconditions:**
- In-memory DuckDB with v9 schema applied.
- TaskGraph with 3 nodes, 2 edges, metadata.

**Input:**
- `save_plan(graph, conn)` then `load_plan(conn)`

**Expected:**
- Loaded graph has same nodes (all fields), edges, order, metadata.

**Assertion pseudocode:**
```
save_plan(graph, conn)
loaded = load_plan(conn)
ASSERT loaded.nodes.keys() == graph.nodes.keys()
FOR nid IN graph.nodes:
    ASSERT vars(loaded.nodes[nid]) == vars(graph.nodes[nid])
ASSERT loaded.edges == graph.edges
ASSERT loaded.order == graph.order
```

### TS-105-2: Plan saved in single transaction

**Requirement:** 105-REQ-1.1
**Type:** unit
**Description:** Verify save_plan writes nodes, edges, and meta atomically.

**Preconditions:**
- In-memory DuckDB with v9 schema.

**Input:**
- Save a plan, then check row counts.

**Expected:**
- All three tables populated in one call.

**Assertion pseudocode:**
```
save_plan(graph_with_3_nodes_2_edges, conn)
ASSERT conn.sql("SELECT count(*) FROM plan_nodes").fetchone()[0] == 3
ASSERT conn.sql("SELECT count(*) FROM plan_edges").fetchone()[0] == 2
ASSERT conn.sql("SELECT count(*) FROM plan_meta").fetchone()[0] == 1
```

### TS-105-3: Content hash stored and retrievable

**Requirement:** 105-REQ-1.4
**Type:** unit
**Description:** Verify plan_meta stores content hash correctly.

**Preconditions:**
- In-memory DuckDB with v9 schema.

**Input:**
- Save plan, query plan_meta.content_hash.

**Expected:**
- Hash matches `compute_plan_hash(graph)`.

**Assertion pseudocode:**
```
expected_hash = compute_plan_hash(graph)
save_plan(graph, conn)
stored_hash = conn.sql("SELECT content_hash FROM plan_meta").fetchone()[0]
ASSERT stored_hash == expected_hash
```

### TS-105-4: Node status persisted on transition

**Requirement:** 105-REQ-2.1
**Type:** unit
**Description:** Verify persist_node_status updates the DB row.

**Preconditions:**
- Plan saved with node "spec_a:1" at status "pending".

**Input:**
- `persist_node_status(conn, "spec_a:1", "in_progress")`

**Expected:**
- DB row status is "in_progress", updated_at changed.

**Assertion pseudocode:**
```
persist_node_status(conn, "spec_a:1", "in_progress")
row = conn.sql("SELECT status, updated_at FROM plan_nodes WHERE id = 'spec_a:1'").fetchone()
ASSERT row[0] == "in_progress"
ASSERT row[1] > original_created_at
```

### TS-105-5: V3 status values accepted

**Requirement:** 105-REQ-2.2
**Type:** unit
**Description:** Verify all v3 status values can be stored and loaded.

**Preconditions:**
- Plan saved with one node.

**Input:**
- Set status to each v3 value in sequence.

**Expected:**
- Each value round-trips correctly.

**Assertion pseudocode:**
```
FOR status IN ["pending", "in_progress", "completed", "failed", "blocked",
               "skipped", "cost_blocked", "merge_blocked"]:
    persist_node_status(conn, node_id, status)
    loaded = load_execution_state(conn)
    ASSERT loaded[node_id] == status
```

### TS-105-6: Blocked reason stored

**Requirement:** 105-REQ-2.3
**Type:** unit
**Description:** Verify blocked_reason is persisted with blocked status.

**Preconditions:**
- Plan saved with one node.

**Input:**
- `persist_node_status(conn, node_id, "blocked", blocked_reason="upstream failed")`

**Expected:**
- DB row has blocked_reason = "upstream failed".

**Assertion pseudocode:**
```
persist_node_status(conn, node_id, "blocked", blocked_reason="upstream failed")
reason = conn.sql("SELECT blocked_reason FROM plan_nodes WHERE id = ?", [node_id]).fetchone()[0]
ASSERT reason == "upstream failed"
```

### TS-105-7: Session record with extended fields

**Requirement:** 105-REQ-3.1, 105-REQ-3.2
**Type:** unit
**Description:** Verify session_outcomes accepts all extended fields.

**Preconditions:**
- In-memory DuckDB with v9 schema.

**Input:**
- INSERT a SessionOutcomeRecord with all fields populated.

**Expected:**
- All fields retrievable via SELECT.

**Assertion pseudocode:**
```
record = SessionOutcomeRecord(
    id="s1", spec_name="spec_a", task_group="1", node_id="spec_a:1",
    touched_path="file.py", status="completed", input_tokens=1000,
    output_tokens=500, duration_ms=30000, created_at="2026-01-01T00:00:00",
    run_id="run_1", attempt=1, cost=0.05, model="claude-sonnet-4-6",
    archetype="coder", commit_sha="abc123", error_message=None,
    is_transport_error=False)
record_session(conn, record)
row = conn.sql("SELECT run_id, attempt, cost, model, archetype, commit_sha FROM session_outcomes WHERE id = 's1'").fetchone()
ASSERT row == ("run_1", 1, 0.05, "claude-sonnet-4-6", "coder", "abc123")
```

### TS-105-8: Run creation and completion

**Requirement:** 105-REQ-4.1, 105-REQ-4.2, 105-REQ-4.4
**Type:** unit
**Description:** Verify run lifecycle from creation to completion.

**Preconditions:**
- In-memory DuckDB with v9 schema.

**Input:**
- Create run, update totals, complete run.

**Expected:**
- Final row has accumulated totals and completion timestamp.

**Assertion pseudocode:**
```
create_run(conn, "run_1", "hash_abc")
update_run_totals(conn, "run_1", input_tokens=1000, output_tokens=500, cost=0.05)
update_run_totals(conn, "run_1", input_tokens=2000, output_tokens=800, cost=0.08)
complete_run(conn, "run_1", "completed")
row = conn.sql("SELECT total_input_tokens, total_cost, status, completed_at FROM runs WHERE id = 'run_1'").fetchone()
ASSERT row[0] == 3000
ASSERT abs(row[1] - 0.13) < 0.001
ASSERT row[2] == "completed"
ASSERT row[3] IS NOT None
```

### TS-105-9: PLAN_PATH and STATE_PATH removed

**Requirement:** 105-REQ-5.1
**Type:** unit
**Description:** Verify path constants no longer exist.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Attempt to import PLAN_PATH and STATE_PATH from core.paths.

**Expected:**
- AttributeError raised.

**Assertion pseudocode:**
```
TRY:
    from agent_fox.core.paths import PLAN_PATH
    FAIL("should not be importable")
EXCEPT (ImportError, AttributeError):
    PASS
TRY:
    from agent_fox.core.paths import STATE_PATH
    FAIL("should not be importable")
EXCEPT (ImportError, AttributeError):
    PASS
```

### TS-105-10: No state files created

**Requirement:** 105-REQ-5.4
**Type:** integration
**Description:** Verify af run does not create plan.json or state.jsonl.

**Preconditions:**
- Fresh project directory with specs.
- Mock session runner (completes immediately).

**Input:**
- Run the orchestrator through a simple plan.

**Expected:**
- No plan.json or state.jsonl files on disk.
- Plan state exists in DuckDB.

**Assertion pseudocode:**
```
run_orchestrator_with_mock_sessions(project_dir)
ASSERT NOT (project_dir / ".agent-fox" / "plan.json").exists()
ASSERT NOT (project_dir / ".agent-fox" / "state.jsonl").exists()
ASSERT conn.sql("SELECT count(*) FROM plan_nodes").fetchone()[0] > 0
```

### TS-105-11: Legacy files ignored

**Requirement:** 105-REQ-5.E1
**Type:** unit
**Description:** Verify existing plan.json/state.jsonl are not read.

**Preconditions:**
- plan.json and state.jsonl exist on disk with content.
- DuckDB has no plan tables populated.

**Input:**
- Call load_plan(conn).

**Expected:**
- Returns None (not data from plan.json).

**Assertion pseudocode:**
```
write_file(plan_path, '{"nodes": {"a:1": {...}}}')
result = load_plan(conn)
ASSERT result IS None  # DB is empty, file is ignored
```

### TS-105-12: Concurrent read during write

**Requirement:** 105-REQ-6.3
**Type:** integration
**Description:** Verify read-only connection sees consistent state during
writes.

**Preconditions:**
- DuckDB file on disk (not in-memory) with v9 schema and a saved plan.

**Input:**
- Write connection updates node status.
- Read-only connection queries plan_nodes concurrently.

**Expected:**
- Read connection sees either pre-update or post-update state, not partial.

**Assertion pseudocode:**
```
write_conn = duckdb.connect(db_path)
read_conn = duckdb.connect(db_path, read_only=True)
save_plan(graph, write_conn)
# Read from separate connection
nodes = read_conn.sql("SELECT id, status FROM plan_nodes").fetchall()
ASSERT len(nodes) == expected_count
ASSERT all(row[1] IN valid_statuses FOR row IN nodes)
```

## Property Test Cases

### TS-105-P1: Plan round-trip equivalence

**Property:** Property 1 from design.md
**Validates:** 105-REQ-1.1, 105-REQ-1.2
**Type:** property
**Description:** Arbitrary TaskGraphs survive save/load round-trips.

**For any:** TaskGraph with 0-20 nodes, 0-30 edges (valid DAG), random
archetype/status/model values, random metadata.

**Invariant:** `load_plan(save_plan(graph)) == graph` (structural equality).

**Assertion pseudocode:**
```
FOR ANY graph IN valid_task_graphs():
    save_plan(graph, conn)
    loaded = load_plan(conn)
    ASSERT loaded.nodes == graph.nodes
    ASSERT loaded.edges == graph.edges
    ASSERT loaded.order == graph.order
```

### TS-105-P2: Status transition atomicity

**Property:** Property 2 from design.md
**Validates:** 105-REQ-2.1, 105-REQ-2.4
**Type:** property
**Description:** Every status transition is immediately visible on reload.

**For any:** Node ID, sequence of 1-10 status transitions from the v3 set.

**Invariant:** After each transition, `load_execution_state` reflects the
latest status.

**Assertion pseudocode:**
```
FOR ANY node_id, transitions IN random_status_sequences():
    FOR status IN transitions:
        persist_node_status(conn, node_id, status)
        loaded = load_execution_state(conn)
        ASSERT loaded[node_id] == status
```

### TS-105-P3: Content hash stability

**Property:** Property 3 from design.md
**Validates:** 105-REQ-1.4
**Type:** property
**Description:** Content hash is stable across save/load.

**For any:** Valid TaskGraph.

**Invariant:** `compute_plan_hash(graph) == compute_plan_hash(load_plan(conn))`
after save.

**Assertion pseudocode:**
```
FOR ANY graph IN valid_task_graphs():
    hash_before = compute_plan_hash(graph)
    save_plan(graph, conn)
    loaded = load_plan(conn)
    hash_after = compute_plan_hash(loaded)
    ASSERT hash_before == hash_after
```

### TS-105-P4: Session record completeness

**Property:** Property 4 from design.md
**Validates:** 105-REQ-3.1, 105-REQ-3.2
**Type:** property
**Description:** All session record fields survive DB round-trip.

**For any:** SessionOutcomeRecord with random field values.

**Invariant:** SELECT returns all field values matching the original record.

**Assertion pseudocode:**
```
FOR ANY record IN random_session_records():
    record_session(conn, record)
    row = SELECT * FROM session_outcomes WHERE id = record.id
    ASSERT row.run_id == record.run_id
    ASSERT row.attempt == record.attempt
    ASSERT row.cost == record.cost
    ASSERT row.model == record.model
    # ... all fields
```

### TS-105-P5: Run aggregate accuracy

**Property:** Property 5 from design.md
**Validates:** 105-REQ-4.3
**Type:** property
**Description:** Run totals are the exact sum of all deltas.

**For any:** Sequence of 1-50 (input_tokens, output_tokens, cost) deltas.

**Invariant:** Final run row totals equal the sum of all deltas.

**Assertion pseudocode:**
```
FOR ANY deltas IN lists_of_token_cost_triples():
    create_run(conn, run_id, hash)
    expected_input = expected_output = 0
    expected_cost = 0.0
    FOR (inp, out, cost) IN deltas:
        update_run_totals(conn, run_id, inp, out, cost)
        expected_input += inp
        expected_output += out
        expected_cost += cost
    row = load_run(conn, run_id)
    ASSERT row.total_input_tokens == expected_input
    ASSERT row.total_output_tokens == expected_output
    ASSERT abs(row.total_cost - expected_cost) < 1e-6
```

## Edge Case Tests

### TS-105-E1: No plan in DB

**Requirement:** 105-REQ-1.E1
**Type:** unit
**Description:** load_plan returns None when no plan exists.

**Preconditions:**
- Fresh DuckDB with v9 schema, no data.

**Input:**
- `load_plan(conn)`

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
result = load_plan(conn)
ASSERT result IS None
```

### TS-105-E2: Empty plan (zero nodes)

**Requirement:** 105-REQ-1.E2
**Type:** unit
**Description:** Empty plan round-trips correctly.

**Preconditions:**
- TaskGraph with empty nodes, edges, order.

**Input:**
- save_plan then load_plan.

**Expected:**
- Loaded graph has empty nodes dict, empty edges list, empty order list.

**Assertion pseudocode:**
```
empty_graph = TaskGraph(nodes={}, edges=[], order=[])
save_plan(empty_graph, conn)
loaded = load_plan(conn)
ASSERT loaded.nodes == {}
ASSERT loaded.edges == []
ASSERT loaded.order == []
```

### TS-105-E3: Crash recovery resets in_progress

**Requirement:** 105-REQ-2.E1
**Type:** unit
**Description:** In-progress nodes reset to pending on resume.

**Preconditions:**
- Plan in DB with node "spec_a:1" at status "in_progress".

**Input:**
- Load execution state, apply reset logic.

**Expected:**
- Node status becomes "pending".

**Assertion pseudocode:**
```
persist_node_status(conn, "spec_a:1", "in_progress")
reset_in_progress_nodes(conn)
loaded = load_execution_state(conn)
ASSERT loaded["spec_a:1"] == "pending"
```

### TS-105-E4: Null error_message stored as NULL

**Requirement:** 105-REQ-3.E1
**Type:** unit
**Description:** Successful sessions store NULL error_message, not empty string.

**Preconditions:**
- In-memory DuckDB with v9 schema.

**Input:**
- Record session with error_message=None.

**Expected:**
- DB column is NULL.

**Assertion pseudocode:**
```
record = SessionOutcomeRecord(..., error_message=None)
record_session(conn, record)
val = conn.sql("SELECT error_message FROM session_outcomes WHERE id = ?", [record.id]).fetchone()[0]
ASSERT val IS None  # SQL NULL, not ""
```

### TS-105-E5: Incomplete run detected on resume

**Requirement:** 105-REQ-4.E1
**Type:** unit
**Description:** Crashed run is detected and updated, not duplicated.

**Preconditions:**
- Runs table has a row with status="running", completed_at=NULL.

**Input:**
- Resume orchestrator, which calls create_or_resume_run.

**Expected:**
- No new run row created. Existing row updated.

**Assertion pseudocode:**
```
create_run(conn, "run_1", "hash_a")
# Simulate crash: run_1 still "running"
run = load_incomplete_run(conn)
ASSERT run IS NOT None
ASSERT run.id == "run_1"
ASSERT conn.sql("SELECT count(*) FROM runs").fetchone()[0] == 1
```

### TS-105-E6: DB missing for af status

**Requirement:** 105-REQ-6.E1
**Type:** unit
**Description:** af status handles missing DB gracefully.

**Preconditions:**
- No DuckDB file on disk.

**Input:**
- Invoke status_cmd.

**Expected:**
- Outputs "No plan found" (no crash).

**Assertion pseudocode:**
```
result = generate_status(db_path=nonexistent_path)
ASSERT "No plan found" IN result OR result IS empty_dashboard
```

## Integration Smoke Tests

### TS-105-SMOKE-1: Full orchestration cycle with DB state

**Execution Path:** Paths 1, 2, 3 from design.md
**Description:** Verify plan creation, session execution, and status
persistence through DuckDB — no file-based state involved.

**Setup:**
- Temp directory with one spec (2 task groups).
- Mock session runner that completes immediately.
- Real persistence.save_plan, real state functions, real DuckDB.

**Trigger:** Run orchestrator on the spec.

**Expected side effects:**
- plan_nodes has 2 rows, both with status "completed".
- session_outcomes has 2 rows with run_id, attempt, model populated.
- runs has 1 row with status "completed", totals > 0.
- No plan.json or state.jsonl on disk.

**Must NOT satisfy with:**
- Mocking save_plan or load_plan.
- Mocking record_session or persist_node_status.
- Writing plan.json or state.jsonl.

**Assertion pseudocode:**
```
orchestrator = build_orchestrator(project_dir, mock_runner)
await orchestrator.run()
ASSERT conn.sql("SELECT count(*) FROM plan_nodes WHERE status = 'completed'").fetchone()[0] == 2
ASSERT conn.sql("SELECT count(*) FROM session_outcomes").fetchone()[0] == 2
ASSERT conn.sql("SELECT status FROM runs").fetchone()[0] == "completed"
ASSERT NOT (project_dir / ".agent-fox" / "plan.json").exists()
ASSERT NOT (project_dir / ".agent-fox" / "state.jsonl").exists()
```

### TS-105-SMOKE-2: Concurrent status read during execution

**Execution Path:** Path 4 from design.md
**Description:** Verify af status reads from DB while orchestrator writes.

**Setup:**
- DuckDB file on disk with v9 schema and a saved plan.
- Write connection held by simulated orchestrator.

**Trigger:** Open read-only connection and query plan_nodes.

**Expected side effects:**
- Read connection returns valid rows without error.
- Write connection continues to function.

**Must NOT satisfy with:**
- Using the same connection for read and write.
- Using in-memory DB (must test file-based concurrent access).

**Assertion pseudocode:**
```
db_path = tmp_path / "knowledge.duckdb"
write_conn = duckdb.connect(str(db_path))
apply_migrations(write_conn)
save_plan(graph, write_conn)
persist_node_status(write_conn, "spec_a:1", "in_progress")

read_conn = duckdb.connect(str(db_path), read_only=True)
rows = read_conn.sql("SELECT id, status FROM plan_nodes").fetchall()
ASSERT len(rows) > 0
read_conn.close()
write_conn.close()
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 105-REQ-1.1 | TS-105-1, TS-105-2 | unit |
| 105-REQ-1.2 | TS-105-1 | unit |
| 105-REQ-1.3 | TS-105-1 | unit |
| 105-REQ-1.4 | TS-105-3 | unit |
| 105-REQ-1.E1 | TS-105-E1 | unit |
| 105-REQ-1.E2 | TS-105-E2 | unit |
| 105-REQ-2.1 | TS-105-4 | unit |
| 105-REQ-2.2 | TS-105-5 | unit |
| 105-REQ-2.3 | TS-105-6 | unit |
| 105-REQ-2.4 | TS-105-4 | unit |
| 105-REQ-2.E1 | TS-105-E3 | unit |
| 105-REQ-3.1 | TS-105-7 | unit |
| 105-REQ-3.2 | TS-105-7 | unit |
| 105-REQ-3.3 | TS-105-9 | unit |
| 105-REQ-3.E1 | TS-105-E4 | unit |
| 105-REQ-4.1 | TS-105-8 | unit |
| 105-REQ-4.2 | TS-105-8 | unit |
| 105-REQ-4.3 | TS-105-8 | unit |
| 105-REQ-4.4 | TS-105-8 | unit |
| 105-REQ-4.E1 | TS-105-E5 | unit |
| 105-REQ-5.1 | TS-105-9 | unit |
| 105-REQ-5.2 | TS-105-1 | unit |
| 105-REQ-5.3 | TS-105-9 | unit |
| 105-REQ-5.4 | TS-105-10 | integration |
| 105-REQ-5.E1 | TS-105-11 | unit |
| 105-REQ-6.1 | TS-105-12 | integration |
| 105-REQ-6.2 | TS-105-SMOKE-1 | integration |
| 105-REQ-6.3 | TS-105-12, TS-105-SMOKE-2 | integration |
| 105-REQ-6.E1 | TS-105-E6 | unit |
| Property 1 | TS-105-P1 | property |
| Property 2 | TS-105-P2 | property |
| Property 3 | TS-105-P3 | property |
| Property 4 | TS-105-P4 | property |
| Property 5 | TS-105-P5 | property |
