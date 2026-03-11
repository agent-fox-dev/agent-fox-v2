# Test Specification: DuckDB Hardening

## Overview

This test specification verifies that DuckDB is a hard requirement: initialization
fails fast, connection parameters are non-optional, DuckDB errors propagate, and
the test fixture provides isolation.

## Test Cases

### TS-38-1: Initialization Raises on Failure

**Requirement:** 38-REQ-1.1, 38-REQ-1.2
**Type:** unit
**Description:** Verify open_knowledge_store raises RuntimeError when DuckDB cannot be opened.

**Preconditions:**
- KnowledgeConfig pointing to an invalid/unwritable path.

**Input:**
- Call `open_knowledge_store(bad_config)`.

**Expected:**
- `RuntimeError` raised with message containing `"Knowledge store initialization failed"`.

**Assertion pseudocode:**
```
WITH pytest.raises(RuntimeError, match="Knowledge store initialization failed"):
    open_knowledge_store(bad_config)
```

### TS-38-2: Initialization Returns KnowledgeDB

**Requirement:** 38-REQ-1.3
**Type:** unit
**Description:** Verify open_knowledge_store returns a valid KnowledgeDB on success.

**Preconditions:**
- Valid KnowledgeConfig with writable path.

**Input:**
- Call `open_knowledge_store(good_config)`.

**Expected:**
- Returns `KnowledgeDB` instance (not None).

**Assertion pseudocode:**
```
result = open_knowledge_store(good_config)
ASSERT isinstance(result, KnowledgeDB)
ASSERT result is not None
```

### TS-38-3: SessionLifecycle Requires KnowledgeDB

**Requirement:** 38-REQ-2.1
**Type:** unit
**Description:** Verify NodeSessionRunner requires knowledge_db parameter.

**Preconditions:**
- NodeSessionRunner class available.

**Input:**
- Inspect constructor signature.

**Expected:**
- `knowledge_db` parameter type is `KnowledgeDB` (not Optional).

**Assertion pseudocode:**
```
hints = get_type_hints(NodeSessionRunner.__init__)
ASSERT hints["knowledge_db"] is KnowledgeDB  # not Optional
```

### TS-38-4: Knowledge Harvest Requires KnowledgeDB

**Requirement:** 38-REQ-2.1, 38-REQ-2.3
**Type:** unit
**Description:** Verify extract_and_store_knowledge requires knowledge_db.

**Preconditions:**
- Function signature inspectable.

**Input:**
- Inspect `extract_and_store_knowledge` signature.

**Expected:**
- `knowledge_db` parameter type is `KnowledgeDB` (not Optional).

**Assertion pseudocode:**
```
hints = get_type_hints(extract_and_store_knowledge)
ASSERT hints["knowledge_db"] is KnowledgeDB
```

### TS-38-5: MemoryStore Requires db_conn

**Requirement:** 38-REQ-2.2, 38-REQ-2.4
**Type:** unit
**Description:** Verify MemoryStore requires db_conn parameter.

**Preconditions:**
- MemoryStore class available.

**Input:**
- Inspect constructor signature.

**Expected:**
- `db_conn` parameter type is `duckdb.DuckDBPyConnection` (not Optional).

**Assertion pseudocode:**
```
hints = get_type_hints(MemoryStore.__init__)
ASSERT hints["db_conn"] is duckdb.DuckDBPyConnection
```

### TS-38-6: assemble_context Requires conn

**Requirement:** 38-REQ-4.1
**Type:** unit
**Description:** Verify assemble_context requires conn parameter.

**Preconditions:**
- Function signature inspectable.

**Input:**
- Inspect `assemble_context` signature.

**Expected:**
- `conn` parameter type is `duckdb.DuckDBPyConnection` (not Optional).

**Assertion pseudocode:**
```
hints = get_type_hints(assemble_context)
ASSERT hints["conn"] is duckdb.DuckDBPyConnection
```

### TS-38-7: AssessmentPipeline Requires db

**Requirement:** 38-REQ-6.1, 38-REQ-6.2
**Type:** unit
**Description:** Verify AssessmentPipeline requires db parameter.

**Preconditions:**
- AssessmentPipeline class available.

**Input:**
- Inspect constructor signature.

**Expected:**
- `db` parameter type is `duckdb.DuckDBPyConnection` (not Optional).

**Assertion pseudocode:**
```
hints = get_type_hints(AssessmentPipeline.__init__)
ASSERT hints["db"] is duckdb.DuckDBPyConnection
```

### TS-38-8: DuckDBSink Propagates Write Errors

**Requirement:** 38-REQ-3.1
**Type:** unit
**Description:** Verify DuckDBSink does not swallow DuckDB errors.

**Preconditions:**
- DuckDBSink with a mock connection that raises `duckdb.Error`.

**Input:**
- Call `record_session_outcome()` with a failing connection.

**Expected:**
- Exception propagates (not caught and logged).

**Assertion pseudocode:**
```
sink = DuckDBSink(failing_conn)
WITH pytest.raises(duckdb.Error):
    sink.record_session_outcome(outcome)
```

### TS-38-9: MemoryStore Propagates Write Errors

**Requirement:** 38-REQ-3.2
**Type:** unit
**Description:** Verify MemoryStore propagates DuckDB write errors.

**Preconditions:**
- MemoryStore with a connection that raises on INSERT.

**Input:**
- Call `write_fact()` with a fact that triggers a DuckDB error.

**Expected:**
- Exception propagates after JSONL write succeeds.

**Assertion pseudocode:**
```
store = MemoryStore(jsonl_path, failing_conn)
WITH pytest.raises(duckdb.Error):
    store.write_fact(fact)
# JSONL write should have succeeded
ASSERT fact_in_jsonl(jsonl_path, fact)
```

### TS-38-10: Knowledge Harvest Propagates Errors

**Requirement:** 38-REQ-3.3, 38-REQ-3.4
**Type:** unit
**Description:** Verify knowledge harvest does not silently skip DuckDB errors.

**Preconditions:**
- KnowledgeDB with a connection that raises on write.

**Input:**
- Call `sync_facts_to_duckdb()` with a failing connection.

**Expected:**
- Exception propagates.

**Assertion pseudocode:**
```
WITH pytest.raises(duckdb.Error):
    sync_facts_to_duckdb(failing_db, facts)
```

### TS-38-11: Context Assembly Uses DB Only

**Requirement:** 38-REQ-4.2, 38-REQ-4.3
**Type:** integration
**Description:** Verify assemble_context always uses DB-backed rendering.

**Preconditions:**
- Spec dir with review.md file AND DuckDB with review findings.

**Input:**
- Call `assemble_context()` with DuckDB conn.

**Expected:**
- Context includes DB-backed review content.
- Does NOT fall back to file reading.

**Assertion pseudocode:**
```
# Insert finding into DB
insert_findings(conn, [finding])
context = assemble_context(spec_dir, task_group=1, conn=conn)
ASSERT finding.description in context
```

### TS-38-12: Test Fixture Provides Fresh DB

**Requirement:** 38-REQ-5.1, 38-REQ-5.2
**Type:** unit
**Description:** Verify the DuckDB test fixture provides isolated databases.

**Preconditions:**
- pytest fixture `knowledge_conn` available.

**Input:**
- Two test functions using the same fixture.

**Expected:**
- Data from one test is not visible in the other.

**Assertion pseudocode:**
```
def test_a(knowledge_conn):
    knowledge_conn.execute("INSERT INTO memory_facts ...")
    ASSERT count_rows(knowledge_conn) == 1

def test_b(knowledge_conn):
    ASSERT count_rows(knowledge_conn) == 0  # fresh DB
```

## Edge Case Tests

### TS-38-E1: Unwritable Path Error Message

**Requirement:** 38-REQ-1.E1
**Type:** unit
**Description:** Verify error message includes the file path when path is unwritable.

**Preconditions:**
- KnowledgeConfig with path to unwritable location.

**Input:**
- Call `open_knowledge_store(config)`.

**Expected:**
- RuntimeError with message containing the file path.

**Assertion pseudocode:**
```
WITH pytest.raises(RuntimeError, match=str(bad_path)):
    open_knowledge_store(config_with_bad_path)
```

### TS-38-E2: Context Assembly DB Error Propagates

**Requirement:** 38-REQ-3.E1
**Type:** unit
**Description:** Verify assemble_context propagates DB errors instead of falling back.

**Preconditions:**
- Connection that raises on query.

**Input:**
- Call `assemble_context()` with failing connection.

**Expected:**
- Exception propagates (no file-based fallback).

**Assertion pseudocode:**
```
WITH pytest.raises(duckdb.Error):
    assemble_context(spec_dir, task_group=1, conn=failing_conn)
```

## Property Test Cases

### TS-38-P1: Initialization Never Returns None

**Property:** Property 1 from design.md
**Validates:** 38-REQ-1.1, 38-REQ-1.2
**Type:** property
**Description:** open_knowledge_store never returns None.

**For any:** KnowledgeConfig (valid or invalid path)
**Invariant:** Result is KnowledgeDB or RuntimeError is raised.

**Assertion pseudocode:**
```
FOR ANY config IN knowledge_config_strategy():
    TRY:
        result = open_knowledge_store(config)
        ASSERT isinstance(result, KnowledgeDB)
    EXCEPT RuntimeError:
        pass  # expected for invalid configs
    # Never returns None
```

### TS-38-P2: Test Fixture Isolation

**Property:** Property 4 from design.md
**Validates:** 38-REQ-5.1, 38-REQ-5.2
**Type:** property
**Description:** Each fixture invocation provides a clean database.

**For any:** sequence of N insert operations followed by a new fixture
**Invariant:** New fixture has zero rows in all tables.

**Assertion pseudocode:**
```
FOR ANY n IN integers(min_value=1, max_value=20):
    conn1 = create_fixture()
    insert_n_rows(conn1, n)
    conn1.close()
    conn2 = create_fixture()
    ASSERT count_all_rows(conn2) == 0
    conn2.close()
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 38-REQ-1.1 | TS-38-1 | unit |
| 38-REQ-1.2 | TS-38-1 | unit |
| 38-REQ-1.3 | TS-38-2 | unit |
| 38-REQ-1.E1 | TS-38-E1 | unit |
| 38-REQ-2.1 | TS-38-3, TS-38-4 | unit |
| 38-REQ-2.2 | TS-38-5, TS-38-6, TS-38-7 | unit |
| 38-REQ-2.3 | TS-38-4 | unit |
| 38-REQ-2.4 | TS-38-5 | unit |
| 38-REQ-3.1 | TS-38-8 | unit |
| 38-REQ-3.2 | TS-38-9 | unit |
| 38-REQ-3.3 | TS-38-10 | unit |
| 38-REQ-3.4 | TS-38-10 | unit |
| 38-REQ-3.E1 | TS-38-E2 | unit |
| 38-REQ-4.1 | TS-38-6 | unit |
| 38-REQ-4.2 | TS-38-11 | integration |
| 38-REQ-4.3 | TS-38-11 | integration |
| 38-REQ-5.1 | TS-38-12 | unit |
| 38-REQ-5.2 | TS-38-12 | unit |
| 38-REQ-5.3 | TS-38-12 | unit |
| 38-REQ-6.1 | TS-38-7 | unit |
| 38-REQ-6.2 | TS-38-7 | unit |
| Property 1 | TS-38-P1 | property |
| Property 4 | TS-38-P2 | property |
