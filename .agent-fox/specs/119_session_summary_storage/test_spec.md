# Test Specification: Session Summary Storage

## Overview

Tests are organized into four categories: acceptance criterion tests (unit and
integration), edge case tests, property tests, and integration smoke tests.
All tests use an in-memory DuckDB connection with the full schema applied via
`base_schema_ddl()` + migration v24, except where noted.

Test function names reference the module under test. Pseudocode uses
`summary_store`, `fox_provider`, and `session_lifecycle` as module prefixes.

## Test Cases

### TS-119-1: Insert summary stores correct row

**Requirement:** 119-REQ-1.1
**Type:** unit
**Description:** Verify that `insert_summary()` inserts a row with all fields
matching the input `SummaryRecord`.

**Preconditions:**
- Empty `session_summaries` table in a fresh DuckDB connection.

**Input:**
- `SummaryRecord(id="uuid-1", node_id="spec_a:3", run_id="run-1",
  spec_name="spec_a", task_group="3", archetype="coder", attempt=1,
  summary="Implemented SQLite store", created_at="2026-04-28T18:00:00")`

**Expected:**
- One row in `session_summaries` with all fields matching input.

**Assertion pseudocode:**
```
record = SummaryRecord(...)
insert_summary(conn, record)
rows = conn.execute("SELECT * FROM session_summaries").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].node_id == "spec_a:3"
ASSERT rows[0].summary == "Implemented SQLite store"
ASSERT rows[0].archetype == "coder"
ASSERT rows[0].attempt == 1
```

### TS-119-2: Table schema matches specification

**Requirement:** 119-REQ-1.2
**Type:** unit
**Description:** Verify that the `session_summaries` table has exactly the
specified columns with correct types.

**Preconditions:**
- Fresh DuckDB connection with schema applied.

**Input:**
- None (schema introspection).

**Expected:**
- Table exists with columns: id (UUID/VARCHAR), node_id (VARCHAR),
  run_id (VARCHAR), spec_name (VARCHAR), task_group (VARCHAR),
  archetype (VARCHAR), attempt (INTEGER), summary (TEXT),
  created_at (TIMESTAMP).

**Assertion pseudocode:**
```
cols = conn.execute(
    "SELECT column_name, data_type FROM information_schema.columns "
    "WHERE table_name='session_summaries'"
).fetchall()
col_map = {c[0]: c[1] for c in cols}
ASSERT "id" in col_map
ASSERT "node_id" in col_map
ASSERT "summary" in col_map
ASSERT "attempt" in col_map
ASSERT len(col_map) == 9
```

### TS-119-3: Append-only retains all attempts

**Requirement:** 119-REQ-1.3
**Type:** unit
**Description:** Verify that inserting summaries for multiple attempts of the
same task group retains all rows (no supersession).

**Preconditions:**
- Empty `session_summaries` table.

**Input:**
- Two `SummaryRecord`s with same `node_id="spec_a:3"` but `attempt=1` and
  `attempt=2`, different UUIDs and different summary text.

**Expected:**
- Two rows in `session_summaries`, both with `node_id="spec_a:3"`.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(id="uuid-1", node_id="spec_a:3", attempt=1, summary="First try", ...))
insert_summary(conn, SummaryRecord(id="uuid-2", node_id="spec_a:3", attempt=2, summary="Fixed issues", ...))
rows = conn.execute("SELECT * FROM session_summaries WHERE node_id='spec_a:3'").fetchall()
ASSERT len(rows) == 2
summaries = {r.attempt: r.summary for r in rows}
ASSERT summaries[1] == "First try"
ASSERT summaries[2] == "Fixed issues"
```

### TS-119-4: Migration v24 creates table on existing database

**Requirement:** 119-REQ-1.4
**Type:** unit
**Description:** Verify that migration v24 creates the `session_summaries`
table when applied to a database at schema version 23.

**Preconditions:**
- DuckDB connection at schema version 23 (all prior migrations applied).

**Input:**
- Apply migration v24.

**Expected:**
- `session_summaries` table exists and accepts inserts.
- Schema version is now 24.

**Assertion pseudocode:**
```
apply_pending_migrations(conn)  # applies v24
version = get_current_version(conn)
ASSERT version == 24
conn.execute("INSERT INTO session_summaries VALUES (?, ...)", [...])
rows = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()
ASSERT rows[0] == 1
```

### TS-119-5: Same-spec retrieval returns prior groups only

**Requirement:** 119-REQ-2.1
**Type:** unit
**Description:** Verify that `query_same_spec_summaries()` returns only
summaries from task groups less than the current group.

**Preconditions:**
- `session_summaries` contains coder summaries for spec_a groups 1, 2, 3, 4.

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "3", "run-1")`

**Expected:**
- Returns summaries for groups 1 and 2 only. Group 3 and 4 excluded.

**Assertion pseudocode:**
```
# Insert summaries for groups 1-4
for g in [1, 2, 3, 4]:
    insert_summary(conn, SummaryRecord(task_group=str(g), spec_name="spec_a", ...))
results = query_same_spec_summaries(conn, "spec_a", "3", "run-1")
groups = [r.task_group for r in results]
ASSERT groups == ["1", "2"]
```

### TS-119-6: Summaries formatted with CONTEXT prefix

**Requirement:** 119-REQ-2.2
**Type:** unit
**Description:** Verify that `FoxKnowledgeProvider.retrieve()` formats
same-spec summaries with the `[CONTEXT]` prefix pattern.

**Preconditions:**
- `session_summaries` contains a coder summary for spec_a group 2 attempt 1.

**Input:**
- `provider.retrieve("spec_a", "task description", task_group="3", session_id="spec_a:3")`

**Expected:**
- Returned list includes a string matching
  `[CONTEXT] (group 2, attempt 1) <summary text>`.

**Assertion pseudocode:**
```
items = provider.retrieve("spec_a", "task description", task_group="3", session_id="spec_a:3")
context_items = [i for i in items if i.startswith("[CONTEXT]")]
ASSERT len(context_items) >= 1
ASSERT "(group 2, attempt 1)" in context_items[0]
```

### TS-119-7: Latest attempt only in retrieval

**Requirement:** 119-REQ-2.3
**Type:** unit
**Description:** Verify that when multiple attempts exist for a prior group,
only the latest attempt's summary is returned.

**Preconditions:**
- `session_summaries` contains summaries for spec_a group 2 attempt 1 and
  attempt 2.

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "3", "run-1")`

**Expected:**
- Returns one result for group 2 with attempt=2.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(task_group="2", attempt=1, summary="First", ...))
insert_summary(conn, SummaryRecord(task_group="2", attempt=2, summary="Fixed", ...))
results = query_same_spec_summaries(conn, "spec_a", "3", "run-1")
ASSERT len(results) == 1
ASSERT results[0].attempt == 2
ASSERT results[0].summary == "Fixed"
```

### TS-119-8: Sort order is task group ascending

**Requirement:** 119-REQ-2.4
**Type:** unit
**Description:** Verify that same-spec summaries are sorted by task group
number ascending.

**Preconditions:**
- `session_summaries` contains coder summaries for spec_a groups 1, 3, 2
  (inserted out of order).

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "5", "run-1")`

**Expected:**
- Results sorted as groups 1, 2, 3.

**Assertion pseudocode:**
```
for g in [1, 3, 2]:
    insert_summary(conn, SummaryRecord(task_group=str(g), ...))
results = query_same_spec_summaries(conn, "spec_a", "5", "run-1")
groups = [r.task_group for r in results]
ASSERT groups == ["1", "2", "3"]
```

### TS-119-9: Same-spec cap applied

**Requirement:** 119-REQ-2.5
**Type:** unit
**Description:** Verify that same-spec retrieval is capped at max_items.

**Preconditions:**
- `session_summaries` contains coder summaries for spec_a groups 1 through 8.

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "9", "run-1", max_items=5)`

**Expected:**
- Returns exactly 5 results (groups 1-5, the earliest groups by sort order).

**Assertion pseudocode:**
```
for g in range(1, 9):
    insert_summary(conn, SummaryRecord(task_group=str(g), ...))
results = query_same_spec_summaries(conn, "spec_a", "9", "run-1", max_items=5)
ASSERT len(results) == 5
```

### TS-119-10: Only coder summaries retrieved

**Requirement:** 119-REQ-2.6
**Type:** unit
**Description:** Verify that reviewer and verifier summaries are excluded
from retrieval.

**Preconditions:**
- `session_summaries` contains summaries for spec_a group 2 with archetypes
  "coder", "reviewer", and "verifier".

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "3", "run-1")`

**Expected:**
- Returns only the coder summary. Reviewer and verifier excluded.

**Assertion pseudocode:**
```
for arch in ["coder", "reviewer", "verifier"]:
    insert_summary(conn, SummaryRecord(archetype=arch, task_group="2", ...))
results = query_same_spec_summaries(conn, "spec_a", "3", "run-1")
ASSERT len(results) == 1
ASSERT results[0].archetype == "coder"
```

### TS-119-11: Cross-spec retrieval excludes current spec

**Requirement:** 119-REQ-3.1
**Type:** unit
**Description:** Verify that `query_cross_spec_summaries()` returns summaries
from other specs but not the current spec.

**Preconditions:**
- `session_summaries` contains coder summaries for spec_a group 2 and
  spec_b group 3.

**Input:**
- `query_cross_spec_summaries(conn, "spec_a", "run-1")`

**Expected:**
- Returns only the spec_b summary.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="spec_a", task_group="2", ...))
insert_summary(conn, SummaryRecord(spec_name="spec_b", task_group="3", ...))
results = query_cross_spec_summaries(conn, "spec_a", "run-1")
ASSERT len(results) == 1
ASSERT results[0].spec_name == "spec_b"
```

### TS-119-12: Cross-spec formatted with CROSS-SPEC prefix

**Requirement:** 119-REQ-3.2
**Type:** unit
**Description:** Verify that cross-spec summaries are formatted with the
`[CROSS-SPEC]` prefix.

**Preconditions:**
- `session_summaries` contains a coder summary for spec_b group 3.

**Input:**
- `provider.retrieve("spec_a", "task description", task_group="2", session_id="spec_a:2")`

**Expected:**
- Returned list includes a string matching
  `[CROSS-SPEC] (spec_b, group 3) <summary text>`.

**Assertion pseudocode:**
```
items = provider.retrieve("spec_a", "task description", task_group="2", session_id="spec_a:2")
cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
ASSERT len(cross_items) >= 1
ASSERT "(spec_b, group 3)" in cross_items[0]
```

### TS-119-13: Cross-spec cap applied

**Requirement:** 119-REQ-3.3
**Type:** unit
**Description:** Verify that cross-spec retrieval is capped at max_items.

**Preconditions:**
- `session_summaries` contains coder summaries for 5 different specs.

**Input:**
- `query_cross_spec_summaries(conn, "spec_a", "run-1", max_items=3)`

**Expected:**
- Returns exactly 3 results.

**Assertion pseudocode:**
```
for s in ["spec_b", "spec_c", "spec_d", "spec_e", "spec_f"]:
    insert_summary(conn, SummaryRecord(spec_name=s, ...))
results = query_cross_spec_summaries(conn, "spec_a", "run-1", max_items=3)
ASSERT len(results) == 3
```

### TS-119-14: Cross-spec sorted by created_at descending

**Requirement:** 119-REQ-3.4
**Type:** unit
**Description:** Verify that cross-spec summaries are sorted most recent first.

**Preconditions:**
- `session_summaries` contains coder summaries for spec_b (older) and
  spec_c (newer).

**Input:**
- `query_cross_spec_summaries(conn, "spec_a", "run-1")`

**Expected:**
- spec_c summary appears before spec_b summary.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="spec_b", created_at="2026-04-28T10:00:00", ...))
insert_summary(conn, SummaryRecord(spec_name="spec_c", created_at="2026-04-28T11:00:00", ...))
results = query_cross_spec_summaries(conn, "spec_a", "run-1")
ASSERT results[0].spec_name == "spec_c"
ASSERT results[1].spec_name == "spec_b"
```

### TS-119-15: Cross-spec latest attempt only

**Requirement:** 119-REQ-3.5
**Type:** unit
**Description:** Verify that cross-spec retrieval returns only the latest
attempt per (spec, task_group).

**Preconditions:**
- `session_summaries` contains spec_b group 2 attempt 1 and attempt 2.

**Input:**
- `query_cross_spec_summaries(conn, "spec_a", "run-1")`

**Expected:**
- Returns one result for spec_b group 2 with attempt=2.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="spec_b", task_group="2", attempt=1, ...))
insert_summary(conn, SummaryRecord(spec_name="spec_b", task_group="2", attempt=2, ...))
results = query_cross_spec_summaries(conn, "spec_a", "run-1")
ASSERT len(results) == 1
ASSERT results[0].attempt == 2
```

### TS-119-16: Audit event includes summary

**Requirement:** 119-REQ-4.1
**Type:** integration
**Description:** Verify that the `session.complete` audit event payload
contains the summary when available.

**Preconditions:**
- Session completes successfully with a summary artifact.

**Input:**
- Mock session execution that produces a `session-summary.json` with
  `{"summary": "Built the store"}`.

**Expected:**
- The emitted `session.complete` audit event payload contains
  `"summary": "Built the store"`.

**Assertion pseudocode:**
```
# Mock the session execution and artifact file
workspace = create_test_workspace_with_summary("Built the store")
runner = NodeSessionRunner(...)
record = await runner._run_and_harvest(...)
# Capture the emitted audit event
ASSERT mock_sink.events[-1].payload["summary"] == "Built the store"
```

### TS-119-17: Audit event omits summary when missing

**Requirement:** 119-REQ-4.2
**Type:** integration
**Description:** Verify that the `session.complete` audit event payload does
not contain a summary key when no summary is available.

**Preconditions:**
- Session completes successfully without a summary artifact.

**Input:**
- Mock session execution with no `session-summary.json`.

**Expected:**
- The emitted `session.complete` audit event payload does not contain
  `"summary"`.

**Assertion pseudocode:**
```
workspace = create_test_workspace_without_summary()
runner = NodeSessionRunner(...)
record = await runner._run_and_harvest(...)
ASSERT "summary" not in mock_sink.events[-1].payload
```

### TS-119-18: Summary passed to ingest via context

**Requirement:** 119-REQ-5.1
**Type:** integration
**Description:** Verify that `_ingest_knowledge()` passes the summary string
to the knowledge provider's context dict.

**Preconditions:**
- Session completes with a summary artifact.

**Input:**
- Mock knowledge provider that records the context dict.

**Expected:**
- The context dict passed to `ingest()` contains
  `"summary": "summary text"`.

**Assertion pseudocode:**
```
mock_provider = MockKnowledgeProvider()
runner = NodeSessionRunner(..., knowledge_provider=mock_provider)
await runner._run_and_harvest(...)
ASSERT mock_provider.last_context["summary"] == "summary text"
```

### TS-119-19: Ingest stores summary in database

**Requirement:** 119-REQ-5.2
**Type:** integration
**Description:** Verify that `FoxKnowledgeProvider.ingest()` inserts the
summary into `session_summaries` when context contains a summary.

**Preconditions:**
- Empty `session_summaries` table. Provider configured with DuckDB connection.

**Input:**
- `provider.ingest("spec_a:3", "spec_a", {"summary": "Built store", "session_status": "completed", ...})`

**Expected:**
- One row in `session_summaries` with summary "Built store".

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(conn)
provider.ingest("spec_a:3", "spec_a", {
    "summary": "Built store",
    "session_status": "completed",
    "touched_files": [],
    "commit_sha": "abc123",
})
rows = conn.execute("SELECT * FROM session_summaries").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].summary == "Built store"
```

### TS-119-20: Summary available to both audit event and ingest

**Requirement:** 119-REQ-5.3
**Type:** integration
**Description:** Verify that both the audit event and the knowledge ingestion
receive the same summary text from a single read of the session artifacts.

**Preconditions:**
- Session completes with a summary artifact.

**Input:**
- Mock sink and mock knowledge provider.

**Expected:**
- The summary in the audit event payload matches the summary in the
  ingest context.

**Assertion pseudocode:**
```
mock_sink = MockSink()
mock_provider = MockKnowledgeProvider()
runner = NodeSessionRunner(..., sink=mock_sink, knowledge_provider=mock_provider)
await runner._run_and_harvest(...)
audit_summary = mock_sink.events[-1].payload.get("summary")
ingest_summary = mock_provider.last_context.get("summary")
ASSERT audit_summary == ingest_summary
ASSERT audit_summary is not None
```

## Edge Case Tests

### TS-119-E1: Missing summary artifact

**Requirement:** 119-REQ-1.E1
**Type:** unit
**Description:** Verify that no row is stored when the session summary
artifact is missing.

**Preconditions:**
- No `session-summary.json` in the worktree.

**Input:**
- Session completes successfully; `_read_session_artifacts()` returns None.

**Expected:**
- `session_summaries` table remains empty. Debug log emitted.

**Assertion pseudocode:**
```
result = NodeSessionRunner._read_session_artifacts(empty_workspace)
ASSERT result is None
# After full lifecycle, no summary row stored
rows = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()
ASSERT rows[0] == 0
```

### TS-119-E2: Failed session skips summary

**Requirement:** 119-REQ-1.E2
**Type:** unit
**Description:** Verify that summaries are not stored for failed sessions.

**Preconditions:**
- Session summary artifact exists but session status is "failed".

**Input:**
- `provider.ingest("spec_a:3", "spec_a", {"summary": "Some text", "session_status": "failed", ...})`

**Expected:**
- No row inserted into `session_summaries`.

**Assertion pseudocode:**
```
provider.ingest("spec_a:3", "spec_a", {
    "summary": "Some text",
    "session_status": "failed",
    "touched_files": [],
    "commit_sha": "",
})
rows = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()
ASSERT rows[0] == 0
```

### TS-119-E3: Missing table handled gracefully

**Requirement:** 119-REQ-1.E3, 119-REQ-2.E3
**Type:** unit
**Description:** Verify that queries against a missing `session_summaries`
table return empty results without error.

**Preconditions:**
- DuckDB connection with no `session_summaries` table (schema < v24).

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "3", "run-1")`
- `query_cross_spec_summaries(conn, "spec_a", "run-1")`

**Expected:**
- Both return empty lists. No exception raised.

**Assertion pseudocode:**
```
conn_old = duckdb.connect(":memory:")
# Apply only base schema WITHOUT v24
results1 = query_same_spec_summaries(conn_old, "spec_a", "3", "run-1")
results2 = query_cross_spec_summaries(conn_old, "spec_a", "run-1")
ASSERT results1 == []
ASSERT results2 == []
```

### TS-119-E4: Task group 1 returns empty same-spec list

**Requirement:** 119-REQ-2.E1
**Type:** unit
**Description:** Verify that requesting summaries for task group 1 returns
nothing (no prior groups exist).

**Preconditions:**
- `session_summaries` contains summaries for groups 1, 2, 3.

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "1", "run-1")`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
for g in [1, 2, 3]:
    insert_summary(conn, SummaryRecord(task_group=str(g), ...))
results = query_same_spec_summaries(conn, "spec_a", "1", "run-1")
ASSERT results == []
```

### TS-119-E5: No coder summaries for prior groups

**Requirement:** 119-REQ-2.E2
**Type:** unit
**Description:** Verify that an empty list is returned when all prior group
sessions failed or were non-coder archetypes.

**Preconditions:**
- `session_summaries` contains only reviewer summaries for prior groups.

**Input:**
- `query_same_spec_summaries(conn, "spec_a", "3", "run-1")`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(task_group="1", archetype="reviewer", ...))
insert_summary(conn, SummaryRecord(task_group="2", archetype="verifier", ...))
results = query_same_spec_summaries(conn, "spec_a", "3", "run-1")
ASSERT results == []
```

### TS-119-E6: No cross-spec summaries in run

**Requirement:** 119-REQ-3.E1
**Type:** unit
**Description:** Verify that cross-spec returns empty when no other specs
have completed in the run.

**Preconditions:**
- `session_summaries` contains only summaries for "spec_a".

**Input:**
- `query_cross_spec_summaries(conn, "spec_a", "run-1")`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="spec_a", ...))
results = query_cross_spec_summaries(conn, "spec_a", "run-1")
ASSERT results == []
```

### TS-119-E7: No run_id skips cross-spec

**Requirement:** 119-REQ-3.E2
**Type:** unit
**Description:** Verify that cross-spec retrieval is skipped when no run_id
is available.

**Preconditions:**
- `session_summaries` contains summaries for multiple specs.

**Input:**
- `provider.retrieve("spec_a", "desc", task_group="2")` with no run_id
  configured on the provider.

**Expected:**
- No cross-spec items in the returned list.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(conn, run_id=None)
items = provider.retrieve("spec_a", "desc", task_group="2")
cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
ASSERT cross_items == []
```

### TS-119-E8: Audit summary truncated at 2000 chars

**Requirement:** 119-REQ-4.E1
**Type:** unit
**Description:** Verify that audit event payload truncates long summaries.

**Preconditions:**
- Session produces a summary longer than 2000 characters.

**Input:**
- Summary text of 3000 characters.

**Expected:**
- Audit event payload `"summary"` is exactly 2003 characters (2000 + "...").
- Database stores the full 3000-character summary.

**Assertion pseudocode:**
```
long_summary = "x" * 3000
# After session lifecycle:
audit_summary = mock_sink.events[-1].payload["summary"]
ASSERT len(audit_summary) == 2003
ASSERT audit_summary.endswith("...")
# Database has full text
rows = conn.execute("SELECT summary FROM session_summaries").fetchone()
ASSERT len(rows[0]) == 3000
```

### TS-119-E9: DB failure during insert does not crash

**Requirement:** 119-REQ-5.E1
**Type:** unit
**Description:** Verify that a database failure during summary insertion is
caught and logged without crashing.

**Preconditions:**
- DuckDB connection that raises on INSERT (e.g., closed connection).

**Input:**
- `provider.ingest("spec_a:3", "spec_a", {"summary": "text", "session_status": "completed", ...})`

**Expected:**
- No exception propagated. Warning logged.

**Assertion pseudocode:**
```
broken_conn = create_broken_connection()
provider = FoxKnowledgeProvider(broken_conn)
# Should not raise
provider.ingest("spec_a:3", "spec_a", {
    "summary": "text",
    "session_status": "completed",
    "touched_files": [],
    "commit_sha": "",
})
ASSERT warning_logged("insert.*failed")
```

## Property Test Cases

### TS-119-P1: Prior-group filtering correctness

**Property:** Property 2 from design.md
**Validates:** 119-REQ-2.1, 119-REQ-2.3, 119-REQ-2.6
**Type:** property
**Description:** For any task group N and spec S, same-spec queries return
only coder summaries from groups < N with the latest attempt per group.

**For any:** `task_group` in 1..10, `spec_name` from a set of 3,
`num_summaries` in 1..20, `num_attempts` in 1..3, archetypes from
`["coder", "reviewer", "verifier"]`.

**Invariant:** Every returned row has `spec_name == S` AND
`int(task_group) < N` AND `archetype == "coder"`. No two rows share the
same `task_group`. Each row has the maximum `attempt` for its group.

**Assertion pseudocode:**
```
FOR ANY (N, S, summaries) IN strategy:
    insert_all(conn, summaries)
    results = query_same_spec_summaries(conn, S, str(N), run_id)
    FOR EACH r IN results:
        ASSERT r.spec_name == S
        ASSERT int(r.task_group) < N
        ASSERT r.archetype == "coder"
    groups = [r.task_group for r in results]
    ASSERT len(groups) == len(set(groups))  # no duplicates
    FOR EACH g IN set(groups):
        max_attempt = max(s.attempt for s in summaries if s.task_group == g and s.archetype == "coder")
        ASSERT [r for r in results if r.task_group == g][0].attempt == max_attempt
```

### TS-119-P2: Cross-spec exclusion

**Property:** Property 3 from design.md
**Validates:** 119-REQ-3.1, 119-REQ-3.5
**Type:** property
**Description:** Cross-spec queries never return rows from the requesting spec.

**For any:** `spec_name` from a set of 5, `num_summaries` in 1..15 distributed
across specs.

**Invariant:** No returned row has `spec_name` equal to the query spec. Every
returned row has `archetype == "coder"`. No two rows share the same
`(spec_name, task_group)`. Each has the maximum attempt.

**Assertion pseudocode:**
```
FOR ANY (S, summaries) IN strategy:
    insert_all(conn, summaries)
    results = query_cross_spec_summaries(conn, S, run_id)
    FOR EACH r IN results:
        ASSERT r.spec_name != S
        ASSERT r.archetype == "coder"
    pairs = [(r.spec_name, r.task_group) for r in results]
    ASSERT len(pairs) == len(set(pairs))
```

### TS-119-P3: Append-only invariant

**Property:** Property 4 from design.md
**Validates:** 119-REQ-1.3
**Type:** property
**Description:** Row count equals insert count; no rows are modified or
deleted.

**For any:** `num_inserts` in 1..20, with varying node_ids and attempts.

**Invariant:** After N inserts, `SELECT COUNT(*) FROM session_summaries`
returns N. All inserted summaries are retrievable with original text.

**Assertion pseudocode:**
```
FOR ANY inserts IN strategy:
    for record in inserts:
        insert_summary(conn, record)
    count = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
    ASSERT count == len(inserts)
    for record in inserts:
        row = conn.execute("SELECT summary FROM session_summaries WHERE id=?", [record.id]).fetchone()
        ASSERT row[0] == record.summary
```

### TS-119-P4: Sort order stability

**Property:** Property 7 from design.md
**Validates:** 119-REQ-2.4, 119-REQ-3.4
**Type:** property
**Description:** Same-spec results are always sorted by task group ascending;
cross-spec results are sorted by created_at descending.

**For any:** Random insertion order of 1..10 summaries.

**Invariant:** Same-spec results have strictly increasing task group numbers.
Cross-spec results have non-increasing created_at timestamps.

**Assertion pseudocode:**
```
FOR ANY summaries IN strategy:
    insert_all(conn, summaries)
    same = query_same_spec_summaries(conn, spec, high_group, run_id)
    FOR i IN range(1, len(same)):
        ASSERT int(same[i].task_group) > int(same[i-1].task_group)
    cross = query_cross_spec_summaries(conn, spec, run_id)
    FOR i IN range(1, len(cross)):
        ASSERT cross[i].created_at <= cross[i-1].created_at
```

### TS-119-P5: Graceful degradation

**Property:** Property 5 from design.md
**Validates:** 119-REQ-1.E3, 119-REQ-2.E3
**Type:** property
**Description:** Queries against a connection without the session_summaries
table always return empty lists.

**For any:** `spec_name` from a set of 3, `task_group` in 1..10,
`run_id` from a set of 2.

**Invariant:** Both query functions return `[]` without raising.

**Assertion pseudocode:**
```
conn_no_table = duckdb.connect(":memory:")  # no schema at all
FOR ANY (spec, group, run) IN strategy:
    ASSERT query_same_spec_summaries(conn_no_table, spec, group, run) == []
    ASSERT query_cross_spec_summaries(conn_no_table, spec, run) == []
```

### TS-119-P6: Audit payload consistency

**Property:** Property 6 from design.md
**Validates:** 119-REQ-4.1, 119-REQ-4.2
**Type:** property
**Description:** Audit event summary matches database summary when present,
and is absent when no summary exists.

**For any:** Session with summary text of length 0..5000, or None.

**Invariant:** If summary is not None and not empty: audit payload has
"summary" key AND database row exists with same text (modulo truncation
in audit). If summary is None: audit payload has no "summary" key AND
no database row exists.

**Assertion pseudocode:**
```
FOR ANY summary_text IN strategy:
    # Run session with this summary
    if summary_text is not None:
        ASSERT "summary" in audit_payload
        ASSERT db_row.summary == summary_text
        if len(summary_text) > 2000:
            ASSERT audit_payload["summary"] == summary_text[:2000] + "..."
        else:
            ASSERT audit_payload["summary"] == summary_text
    else:
        ASSERT "summary" not in audit_payload
        ASSERT db_count == 0
```

## Integration Smoke Tests

### TS-119-SMOKE-1: End-to-end summary storage and retrieval

**Execution Path:** Path 1 and Path 2 from design.md
**Description:** Verify that a summary written by one session is retrievable
by a subsequent session's knowledge provider call.

**Setup:** In-memory DuckDB with full schema. Mock session runner that writes
a session-summary.json artifact. Real `FoxKnowledgeProvider` instance.

**Trigger:** Execute a session for spec_a group 2, then call retrieve() for
spec_a group 3.

**Expected side effects:**
- `session_summaries` table has one row for spec_a group 2.
- `retrieve()` returns a list containing a `[CONTEXT] (group 2, attempt 1)`
  item with the summary text.

**Must NOT satisfy with:** Mocking `insert_summary()` or
`query_same_spec_summaries()`. The test must exercise the real store functions.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
apply_full_schema(conn)
provider = FoxKnowledgeProvider(conn, run_id="run-1")

# Simulate session completion for spec_a:2
provider.ingest("spec_a:2", "spec_a", {
    "summary": "Built the SQLite store with WAL mode",
    "session_status": "completed",
    "touched_files": ["store.py"],
    "commit_sha": "abc123",
    "archetype": "coder",
    "task_group": "2",
    "attempt": 1,
})

# Retrieve for next group
items = provider.retrieve("spec_a", "implement handlers", task_group="3")
context_items = [i for i in items if i.startswith("[CONTEXT]")]
ASSERT len(context_items) == 1
ASSERT "Built the SQLite store" in context_items[0]
```

### TS-119-SMOKE-2: Cross-spec summary injection

**Execution Path:** Path 2 from design.md (cross-spec branch)
**Description:** Verify that a summary from spec_b is served as a cross-spec
item when retrieving for spec_a.

**Setup:** In-memory DuckDB with full schema. Real `FoxKnowledgeProvider`.

**Trigger:** Ingest a summary for spec_b, then retrieve for spec_a.

**Expected side effects:**
- `retrieve()` returns a list containing a `[CROSS-SPEC] (spec_b, group 2)`
  item.

**Must NOT satisfy with:** Mocking the cross-spec query. The test must hit the
real `session_summaries` table.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(conn, run_id="run-1")
provider.ingest("spec_b:2", "spec_b", {
    "summary": "Changed AuthConfig to remove BearerToken",
    "session_status": "completed",
    "touched_files": [],
    "commit_sha": "def456",
    "archetype": "coder",
    "task_group": "2",
    "attempt": 1,
})
items = provider.retrieve("spec_a", "implement auth", task_group="3")
cross_items = [i for i in items if i.startswith("[CROSS-SPEC]")]
ASSERT len(cross_items) == 1
ASSERT "Changed AuthConfig" in cross_items[0]
```

### TS-119-SMOKE-3: Audit event includes summary end-to-end

**Execution Path:** Path 3 from design.md
**Description:** Verify that the full lifecycle from artifact reading through
audit event emission includes the summary in the payload.

**Setup:** Mock workspace with session-summary.json. Mock sink to capture
events. Real `NodeSessionRunner` (or minimal test harness).

**Trigger:** Complete a session lifecycle that produces a summary artifact.

**Expected side effects:**
- The captured `SESSION_COMPLETE` audit event has `payload["summary"]`
  matching the artifact content.

**Must NOT satisfy with:** Mocking `_read_session_artifacts()` — the test
must read from a real (temp) file to verify the full path.

**Assertion pseudocode:**
```
workspace = create_temp_workspace()
write_session_summary(workspace, {"summary": "Implemented handlers"})
# Run the post-session lifecycle path
runner = create_test_runner(sink=mock_sink)
summary_text = runner._extract_summary_text(workspace)
# Verify audit event emission includes summary
emit_audit_event(mock_sink, ..., payload={..., "summary": summary_text})
ASSERT mock_sink.last_event.payload["summary"] == "Implemented handlers"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 119-REQ-1.1 | TS-119-1 | unit |
| 119-REQ-1.2 | TS-119-2 | unit |
| 119-REQ-1.3 | TS-119-3 | unit |
| 119-REQ-1.4 | TS-119-4 | unit |
| 119-REQ-1.E1 | TS-119-E1 | unit |
| 119-REQ-1.E2 | TS-119-E2 | unit |
| 119-REQ-1.E3 | TS-119-E3 | unit |
| 119-REQ-2.1 | TS-119-5 | unit |
| 119-REQ-2.2 | TS-119-6 | unit |
| 119-REQ-2.3 | TS-119-7 | unit |
| 119-REQ-2.4 | TS-119-8 | unit |
| 119-REQ-2.5 | TS-119-9 | unit |
| 119-REQ-2.6 | TS-119-10 | unit |
| 119-REQ-2.E1 | TS-119-E4 | unit |
| 119-REQ-2.E2 | TS-119-E5 | unit |
| 119-REQ-2.E3 | TS-119-E3 | unit |
| 119-REQ-3.1 | TS-119-11 | unit |
| 119-REQ-3.2 | TS-119-12 | unit |
| 119-REQ-3.3 | TS-119-13 | unit |
| 119-REQ-3.4 | TS-119-14 | unit |
| 119-REQ-3.5 | TS-119-15 | unit |
| 119-REQ-3.E1 | TS-119-E6 | unit |
| 119-REQ-3.E2 | TS-119-E7 | unit |
| 119-REQ-4.1 | TS-119-16 | integration |
| 119-REQ-4.2 | TS-119-17 | integration |
| 119-REQ-4.E1 | TS-119-E8 | unit |
| 119-REQ-5.1 | TS-119-18 | integration |
| 119-REQ-5.2 | TS-119-19 | integration |
| 119-REQ-5.3 | TS-119-20 | integration |
| 119-REQ-5.E1 | TS-119-E9 | unit |
| Property 1 | TS-119-P1 (partial) | property |
| Property 2 | TS-119-P1 | property |
| Property 3 | TS-119-P2 | property |
| Property 4 | TS-119-P3 | property |
| Property 5 | TS-119-P5 | property |
| Property 6 | TS-119-P6 | property |
| Property 7 | TS-119-P4 | property |
| Path 1 + 2 | TS-119-SMOKE-1 | integration |
| Path 2 (cross) | TS-119-SMOKE-2 | integration |
| Path 3 | TS-119-SMOKE-3 | integration |
