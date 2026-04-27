# Test Specification: Knowledge System Pruning

## Overview

Tests verify that removed components are gone, retained components still work,
the database migration drops the correct tables, and the simplified
FoxKnowledgeProvider returns only review findings. Tests use the project's
existing pytest framework with DuckDB fixtures.

## Test Cases

### TS-116-1: Gotcha extraction module removed

**Requirement:** 116-REQ-1.1
**Type:** unit
**Description:** Verify that `gotcha_extraction` module cannot be imported.

**Preconditions:** None.

**Input:** Attempt to import `agent_fox.knowledge.gotcha_extraction`.

**Expected:** `ModuleNotFoundError` or `ImportError` is raised.

**Assertion pseudocode:**
```
WITH EXPECT ImportError:
    import agent_fox.knowledge.gotcha_extraction
```

### TS-116-2: Gotcha store module removed

**Requirement:** 116-REQ-1.2
**Type:** unit
**Description:** Verify that `gotcha_store` module cannot be imported.

**Preconditions:** None.

**Input:** Attempt to import `agent_fox.knowledge.gotcha_store`.

**Expected:** `ModuleNotFoundError` or `ImportError` is raised.

**Assertion pseudocode:**
```
WITH EXPECT ImportError:
    import agent_fox.knowledge.gotcha_store
```

### TS-116-3: Ingest is a no-op

**Requirement:** 116-REQ-1.3
**Type:** unit
**Description:** Verify that `FoxKnowledgeProvider.ingest()` returns
immediately without LLM calls or database writes.

**Preconditions:**
- FoxKnowledgeProvider instance with a real KnowledgeDB.

**Input:**
```
provider.ingest("session_1", "spec_01", {
    "session_status": "completed",
    "touched_files": ["src/main.rs"],
    "commit_sha": "abc123"
})
```

**Expected:** Returns `None`. No new rows in any table.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(knowledge_db, config)
tables_before = snapshot_all_table_counts(conn)
provider.ingest("s1", "spec_01", {"session_status": "completed", ...})
tables_after = snapshot_all_table_counts(conn)
ASSERT tables_before == tables_after
```

### TS-116-4: Retrieve returns no gotchas

**Requirement:** 116-REQ-1.4
**Type:** unit
**Description:** Verify retrieve returns no `[GOTCHA]`-prefixed items.

**Preconditions:**
- FoxKnowledgeProvider instance with KnowledgeDB.

**Input:** `provider.retrieve("any_spec", "any task")`

**Expected:** Returned list contains no strings starting with `[GOTCHA]`.

**Assertion pseudocode:**
```
result = provider.retrieve("any_spec", "any task")
ASSERT all(not item.startswith("[GOTCHA]") for item in result)
```

### TS-116-5: Errata store module removed

**Requirement:** 116-REQ-2.1
**Type:** unit
**Description:** Verify that `errata_store` module cannot be imported.

**Preconditions:** None.

**Input:** Attempt to import `agent_fox.knowledge.errata_store`.

**Expected:** `ModuleNotFoundError` or `ImportError` is raised.

**Assertion pseudocode:**
```
WITH EXPECT ImportError:
    import agent_fox.knowledge.errata_store
```

### TS-116-6: Retrieve returns no errata

**Requirement:** 116-REQ-2.2
**Type:** unit
**Description:** Verify retrieve returns no `[ERRATA]`-prefixed items.

**Preconditions:**
- FoxKnowledgeProvider instance with KnowledgeDB.

**Input:** `provider.retrieve("any_spec", "any task")`

**Expected:** Returned list contains no strings starting with `[ERRATA]`.

**Assertion pseudocode:**
```
result = provider.retrieve("any_spec", "any task")
ASSERT all(not item.startswith("[ERRATA]") for item in result)
```

### TS-116-7: Blocking history module removed

**Requirement:** 116-REQ-3.1
**Type:** unit
**Description:** Verify that `blocking_history` module cannot be imported.

**Preconditions:** None.

**Input:** Attempt to import `agent_fox.knowledge.blocking_history`.

**Expected:** `ModuleNotFoundError` or `ImportError` is raised.

**Assertion pseudocode:**
```
WITH EXPECT ImportError:
    import agent_fox.knowledge.blocking_history
```

### TS-116-8: Result handler does not import blocking_history

**Requirement:** 116-REQ-3.E1
**Type:** unit
**Description:** Verify that `result_handler.py` does not reference
`blocking_history`.

**Preconditions:** None.

**Input:** Read source of `agent_fox.engine.result_handler`.

**Expected:** No reference to `blocking_history`, `record_blocking_decision`,
or `BlockingDecision`.

**Assertion pseudocode:**
```
source = inspect.getsource(agent_fox.engine.result_handler)
ASSERT "blocking_history" not in source
ASSERT "record_blocking_decision" not in source
```

### TS-116-9: Migration v18 drops unused tables

**Requirement:** 116-REQ-4.1, 116-REQ-4.3
**Type:** integration
**Description:** Verify that migration v18 drops exactly the 10 specified
tables and records itself in schema_version.

**Preconditions:**
- Fresh DuckDB with all migrations v1-v17 applied (all tables exist).

**Input:** Apply migration v18.

**Expected:**
- Tables dropped: gotchas, errata_index, blocking_history, sleep_artifacts,
  memory_facts, memory_embeddings, entity_graph, entity_edges, fact_entities,
  fact_causes.
- schema_version contains row with version=18.

**Assertion pseudocode:**
```
conn = create_db_with_migrations_up_to(17)
dropped_tables = ["gotchas", "errata_index", "blocking_history",
    "sleep_artifacts", "memory_facts", "memory_embeddings",
    "entity_graph", "entity_edges", "fact_entities", "fact_causes"]
FOR table IN dropped_tables:
    ASSERT table_exists(conn, table)

apply_migration_v18(conn)

FOR table IN dropped_tables:
    ASSERT NOT table_exists(conn, table)

version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
ASSERT version == 18
```

### TS-116-10: Migration v18 preserves retained tables

**Requirement:** 116-REQ-4.2
**Type:** integration
**Description:** Verify migration v18 does not alter retained tables.

**Preconditions:**
- DuckDB with migrations v1-v17 applied.
- Insert a test row into review_findings and session_outcomes.

**Input:** Apply migration v18.

**Expected:** Test rows in review_findings and session_outcomes are still
present. All retained tables exist.

**Assertion pseudocode:**
```
conn = create_db_with_migrations_up_to(17)
insert_test_finding(conn)
insert_test_outcome(conn)
apply_migration_v18(conn)

retained = ["review_findings", "verification_results", "drift_findings",
    "session_outcomes", "tool_calls", "tool_errors", "audit_events",
    "plan_nodes", "plan_edges", "plan_meta", "runs", "schema_version"]
FOR table IN retained:
    ASSERT table_exists(conn, table)

ASSERT count_rows(conn, "review_findings") == 1
ASSERT count_rows(conn, "session_outcomes") == 1
```

### TS-116-11: Migration v18 on fresh database

**Requirement:** 116-REQ-4.E1
**Type:** integration
**Description:** Verify migration v18 succeeds even when tables to drop
do not exist.

**Preconditions:**
- Fresh DuckDB with no tables.

**Input:** Apply all migrations v1-v18.

**Expected:** No errors. Schema version is 18.

**Assertion pseudocode:**
```
conn = fresh_duckdb()
apply_all_migrations(conn)
version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
ASSERT version == 18
```

### TS-116-12: Supersession without fact_causes

**Requirement:** 116-REQ-5.1, 116-REQ-5.2
**Type:** unit
**Description:** Verify that superseding review findings works correctly
without writing to fact_causes.

**Preconditions:**
- DuckDB with migration v18 applied (fact_causes table dropped).
- Insert initial review finding for spec "test_spec", task_group 1.

**Input:** Call `insert_findings()` with new findings for the same spec and
task_group.

**Expected:**
- Old finding has `superseded_by` set.
- New finding is active (superseded_by is NULL).
- No error from missing fact_causes table.

**Assertion pseudocode:**
```
conn = create_db_with_v18()
old_findings = [ReviewFinding(spec_name="test", task_group=1, ...)]
insert_findings(conn, old_findings, session_id="s1")
new_findings = [ReviewFinding(spec_name="test", task_group=1, ...)]
count = insert_findings(conn, new_findings, session_id="s2")
ASSERT count == 1
active = query_active_findings(conn, "test")
ASSERT len(active) == 1
ASSERT active[0].session_id == "s2"
```

### TS-116-13: Retrieve returns review findings

**Requirement:** 116-REQ-6.1
**Type:** unit
**Description:** Verify that retrieve returns active critical/major review
findings.

**Preconditions:**
- FoxKnowledgeProvider with KnowledgeDB.
- Insert one critical and one observation finding for "test_spec".

**Input:** `provider.retrieve("test_spec", "any task")`

**Expected:** Returns list with exactly one `[REVIEW]` item (the critical
finding). The observation is excluded.

**Assertion pseudocode:**
```
insert_finding(conn, spec="test_spec", severity="critical", desc="fix X")
insert_finding(conn, spec="test_spec", severity="observation", desc="note Y")
result = provider.retrieve("test_spec", "task")
ASSERT len(result) == 1
ASSERT "[REVIEW]" in result[0]
ASSERT "fix X" in result[0]
```

### TS-116-14: Retrieve empty when no findings

**Requirement:** 116-REQ-6.2
**Type:** unit
**Description:** Verify that retrieve returns empty list when no active
critical/major findings exist.

**Preconditions:**
- FoxKnowledgeProvider with KnowledgeDB.
- No review findings for "empty_spec".

**Input:** `provider.retrieve("empty_spec", "any task")`

**Expected:** Empty list.

**Assertion pseudocode:**
```
result = provider.retrieve("empty_spec", "any task")
ASSERT result == []
```

### TS-116-15: FoxKnowledgeProvider satisfies protocol

**Requirement:** 116-REQ-6.3
**Type:** unit
**Description:** Verify FoxKnowledgeProvider is a runtime-checkable
KnowledgeProvider.

**Preconditions:** None.

**Input:** `isinstance(provider, KnowledgeProvider)`

**Expected:** `True`.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(knowledge_db, config)
ASSERT isinstance(provider, KnowledgeProvider)
```

### TS-116-16: Config without gotcha_ttl_days

**Requirement:** 116-REQ-7.1
**Type:** unit
**Description:** Verify KnowledgeProviderConfig has no `gotcha_ttl_days`.

**Preconditions:** None.

**Input:** Inspect `KnowledgeProviderConfig` fields.

**Expected:** No `gotcha_ttl_days` attribute.

**Assertion pseudocode:**
```
ASSERT not hasattr(KnowledgeProviderConfig(), "gotcha_ttl_days")
```

### TS-116-17: Config without model_tier

**Requirement:** 116-REQ-7.2
**Type:** unit
**Description:** Verify KnowledgeProviderConfig has no `model_tier`.

**Preconditions:** None.

**Input:** Inspect `KnowledgeProviderConfig` fields.

**Expected:** No `model_tier` attribute.

**Assertion pseudocode:**
```
ASSERT not hasattr(KnowledgeProviderConfig(), "model_tier")
```

### TS-116-18: Config retains max_items

**Requirement:** 116-REQ-7.3
**Type:** unit
**Description:** Verify KnowledgeProviderConfig has max_items with default 10.

**Preconditions:** None.

**Input:** Create default `KnowledgeProviderConfig()`.

**Expected:** `max_items == 10`.

**Assertion pseudocode:**
```
config = KnowledgeProviderConfig()
ASSERT config.max_items == 10
```

### TS-116-19: No dead imports in production code

**Requirement:** 116-REQ-8.1
**Type:** unit
**Description:** Verify no production code imports removed modules.

**Preconditions:** None.

**Input:** Grep production source for imports of removed modules.

**Expected:** No matches.

**Assertion pseudocode:**
```
removed = ["gotcha_extraction", "gotcha_store", "errata_store", "blocking_history"]
FOR module IN removed:
    matches = grep_production_code(f"import.*{module}")
    ASSERT len(matches) == 0
```

### TS-116-20: Reset table list updated

**Requirement:** 116-REQ-8.2
**Type:** unit
**Description:** Verify that `engine/reset.py` does not list dropped tables.

**Preconditions:** None.

**Input:** Read source of `agent_fox.engine.reset`.

**Expected:** No references to dropped table names in the reset table list.

**Assertion pseudocode:**
```
source = inspect.getsource(agent_fox.engine.reset)
dropped = ["blocking_history", "gotchas", "errata_index", "sleep_artifacts",
    "memory_facts", "memory_embeddings", "entity_graph", "entity_edges",
    "fact_entities", "fact_causes"]
FOR table IN dropped:
    ASSERT f'"{table}"' not in source
```

## Edge Case Tests

### TS-116-E1: Retrieve with missing review_findings table

**Requirement:** 116-REQ-6.E1
**Type:** unit
**Description:** Verify retrieve returns empty list gracefully when
review_findings table doesn't exist.

**Preconditions:**
- FoxKnowledgeProvider with KnowledgeDB where review_findings was dropped.

**Input:** `provider.retrieve("any_spec", "any task")`

**Expected:** Empty list, no exception.

**Assertion pseudocode:**
```
conn.execute("DROP TABLE IF EXISTS review_findings")
result = provider.retrieve("any_spec", "task")
ASSERT result == []
```

### TS-116-E2: Config ignores removed fields

**Requirement:** 116-REQ-7.E1
**Type:** unit
**Description:** Verify KnowledgeProviderConfig silently ignores
`gotcha_ttl_days` and `model_tier` in input.

**Preconditions:** None.

**Input:** Construct config with extra fields.

**Expected:** No error; extra fields are ignored.

**Assertion pseudocode:**
```
config = KnowledgeProviderConfig(max_items=5, gotcha_ttl_days=90, model_tier="SIMPLE")
ASSERT config.max_items == 5
ASSERT not hasattr(config, "gotcha_ttl_days")
```

### TS-116-E3: Gotchas table exists but not queried

**Requirement:** 116-REQ-1.E1
**Type:** integration
**Description:** Verify that if a gotchas table exists (from prior migration),
it is not queried by retrieve.

**Preconditions:**
- DuckDB with v17 schema (gotchas table exists with data).
- Apply v18 is NOT yet applied (table still exists).

**Input:** `provider.retrieve("any_spec", "any task")`

**Expected:** No `[GOTCHA]`-prefixed items in result, even though table has
data.

**Assertion pseudocode:**
```
conn = create_db_with_migrations_up_to(17)
conn.execute("INSERT INTO gotchas VALUES (...)")
provider = FoxKnowledgeProvider(db, config)
result = provider.retrieve("any_spec", "task")
ASSERT all(not item.startswith("[GOTCHA]") for item in result)
```

## Property Test Cases

### TS-116-P1: Review carry-forward preserved

**Property:** Property 1 from design.md
**Validates:** 116-REQ-6.1, 116-REQ-6.2
**Type:** property
**Description:** For any set of review findings, retrieve returns exactly
the critical/major ones.

**For any:** Set of 0-20 ReviewFinding objects with random severities
(critical, major, minor, observation).

**Invariant:** `retrieve()` returns exactly those findings with severity
in {critical, major}, each prefixed with `[REVIEW]`.

**Assertion pseudocode:**
```
FOR ANY findings IN list_of(review_finding(severity=one_of("critical","major","minor","observation"))):
    insert_findings(conn, findings, session_id="s1")
    result = provider.retrieve(spec_name, "task")
    expected_count = count(f for f in findings if f.severity in ("critical", "major"))
    ASSERT len(result) == expected_count
    ASSERT all(item.startswith("[REVIEW]") for item in result)
```

### TS-116-P2: No gotcha or errata leakage

**Property:** Property 2 from design.md
**Validates:** 116-REQ-1.4, 116-REQ-2.2
**Type:** property
**Description:** For any spec_name and task_description, retrieve never
returns gotcha or errata items.

**For any:** Random spec_name (string), random task_description (string).

**Invariant:** Every item in the returned list starts with `[REVIEW]` or
the list is empty.

**Assertion pseudocode:**
```
FOR ANY spec_name IN text(), task_desc IN text():
    result = provider.retrieve(spec_name, task_desc)
    ASSERT all(item.startswith("[REVIEW]") for item in result)
```

### TS-116-P3: Supersession correctness without causal links

**Property:** Property 5 from design.md
**Validates:** 116-REQ-5.1, 116-REQ-5.2
**Type:** property
**Description:** For any sequence of finding insertions for the same
(spec_name, task_group), only the latest batch is active.

**For any:** 2-5 batches of 1-3 ReviewFinding objects for the same
(spec_name, task_group).

**Invariant:** After all batches, `query_active_findings()` returns exactly
the findings from the last batch.

**Assertion pseudocode:**
```
FOR ANY batches IN lists(lists(review_finding(), min_size=1, max_size=3), min_size=2, max_size=5):
    FOR i, batch IN enumerate(batches):
        insert_findings(conn, batch, session_id=f"s{i}")
    active = query_active_findings(conn, spec_name)
    ASSERT len(active) == len(batches[-1])
    ASSERT all(f.session_id == f"s{len(batches)-1}" for f in active)
```

## Integration Smoke Tests

### TS-116-SMOKE-1: Full retrieve cycle with review findings

**Execution Path:** Path 1 from design.md
**Description:** Verify end-to-end retrieval: insert review findings, call
retrieve through FoxKnowledgeProvider, verify they appear in the result.

**Setup:** Real DuckDB with v18 migration applied. No mocks for
FoxKnowledgeProvider or review_store.

**Trigger:** Insert critical finding, then call `provider.retrieve()`.

**Expected side effects:**
- Return list contains exactly one `[REVIEW] [critical]` prefixed string.
- No `[GOTCHA]` or `[ERRATA]` items.

**Must NOT satisfy with:** Mocking FoxKnowledgeProvider, mocking
review_store, or stubbing the DuckDB connection.

**Assertion pseudocode:**
```
db = KnowledgeDB(":memory:")
db.open()
apply_all_migrations(db.connection)
provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
insert_findings(db.connection, [critical_finding(spec="s1")])
result = provider.retrieve("s1", "task")
ASSERT len(result) == 1
ASSERT result[0].startswith("[REVIEW] [critical]")
```

### TS-116-SMOKE-2: Ingest-then-retrieve produces no gotchas

**Execution Path:** Path 2 + Path 1 from design.md
**Description:** Verify that ingesting a completed session followed by
retrieve produces no gotcha items.

**Setup:** Real DuckDB with v18 migration. No mocks for
FoxKnowledgeProvider.

**Trigger:** Call `ingest()` with completed session context, then
`retrieve()`.

**Expected side effects:**
- `ingest()` returns without error.
- `retrieve()` returns empty list (no findings, no gotchas).

**Must NOT satisfy with:** Mocking FoxKnowledgeProvider.ingest().

**Assertion pseudocode:**
```
db = KnowledgeDB(":memory:")
db.open()
apply_all_migrations(db.connection)
provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
provider.ingest("s1", "spec_01", {"session_status": "completed", "touched_files": ["main.rs"], "commit_sha": "abc"})
result = provider.retrieve("spec_01", "task")
ASSERT result == []
```

### TS-116-SMOKE-3: Full migration on existing database

**Execution Path:** Migration path from design.md
**Description:** Verify that applying all migrations v1-v18 on a database
with data produces the correct final state.

**Setup:** Real DuckDB. Insert test data into tables that will be dropped.
No mocks.

**Trigger:** Apply all migrations v1-v18.

**Expected side effects:**
- All 10 specified tables are dropped.
- Retained tables (review_findings, session_outcomes, etc.) are intact.
- schema_version has version 18.

**Must NOT satisfy with:** Starting from an empty database without first
inserting test data into the to-be-dropped tables.

**Assertion pseudocode:**
```
db = KnowledgeDB(":memory:")
apply_migrations_up_to(db.connection, 17)
db.connection.execute("INSERT INTO gotchas VALUES (...)")
db.connection.execute("INSERT INTO memory_facts VALUES (...)")
insert_findings(db.connection, [test_finding()])
apply_migration_v18(db.connection)
ASSERT NOT table_exists(db.connection, "gotchas")
ASSERT NOT table_exists(db.connection, "memory_facts")
ASSERT table_exists(db.connection, "review_findings")
ASSERT count_rows(db.connection, "review_findings") == 1
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 116-REQ-1.1 | TS-116-1 | unit |
| 116-REQ-1.2 | TS-116-2 | unit |
| 116-REQ-1.3 | TS-116-3 | unit |
| 116-REQ-1.4 | TS-116-4 | unit |
| 116-REQ-1.E1 | TS-116-E3 | integration |
| 116-REQ-2.1 | TS-116-5 | unit |
| 116-REQ-2.2 | TS-116-6 | unit |
| 116-REQ-3.1 | TS-116-7 | unit |
| 116-REQ-3.E1 | TS-116-8 | unit |
| 116-REQ-4.1 | TS-116-9 | integration |
| 116-REQ-4.2 | TS-116-10 | integration |
| 116-REQ-4.3 | TS-116-9 | integration |
| 116-REQ-4.E1 | TS-116-11 | integration |
| 116-REQ-5.1 | TS-116-12 | unit |
| 116-REQ-5.2 | TS-116-12 | unit |
| 116-REQ-6.1 | TS-116-13 | unit |
| 116-REQ-6.2 | TS-116-14 | unit |
| 116-REQ-6.3 | TS-116-15 | unit |
| 116-REQ-6.E1 | TS-116-E1 | unit |
| 116-REQ-7.1 | TS-116-16 | unit |
| 116-REQ-7.2 | TS-116-17 | unit |
| 116-REQ-7.3 | TS-116-18 | unit |
| 116-REQ-7.E1 | TS-116-E2 | unit |
| 116-REQ-8.1 | TS-116-19 | unit |
| 116-REQ-8.2 | TS-116-20 | unit |
| 116-REQ-8.3 | TS-116-15 | unit |
| Property 1 | TS-116-P1 | property |
| Property 2 | TS-116-P2 | property |
| Property 5 | TS-116-P3 | property |
| Path 1 | TS-116-SMOKE-1 | integration |
| Path 2 | TS-116-SMOKE-2 | integration |
| Migration | TS-116-SMOKE-3 | integration |
