# Test Specification: Knowledge System Decoupling

## Test Environment

- Python 3.11+
- pytest with tmp_path fixtures for DuckDB isolation
- No sentence-transformers or embedding model dependencies after removal

## Test Contracts

### TC-1: KnowledgeProvider Protocol

**Verifies:** [114-REQ-1.1], [114-REQ-1.2], [114-REQ-1.3], [114-REQ-1.4],
[114-REQ-1.E1]

**File:** `tests/unit/knowledge/test_provider.py`

#### TC-1.1: Protocol is runtime-checkable

```
GIVEN the KnowledgeProvider protocol
WHEN isinstance() is called with a conforming object
THEN it returns True
```

#### TC-1.2: NoOp satisfies protocol

```
GIVEN a NoOpKnowledgeProvider instance
WHEN isinstance(instance, KnowledgeProvider) is called
THEN it returns True
```

#### TC-1.3: Partial implementation fails protocol check

```
GIVEN a class that implements only ingest() but not retrieve()
WHEN isinstance(instance, KnowledgeProvider) is called
THEN it returns False
```

#### TC-1.4: retrieve() returns list[str]

```
GIVEN a NoOpKnowledgeProvider instance
WHEN retrieve("spec_name", "task_desc") is called
THEN the return value is an empty list of type list
```

#### TC-1.5: ingest() accepts context dict

```
GIVEN a NoOpKnowledgeProvider instance
WHEN ingest("session_1", "spec_1", {"touched_files": [], "commit_sha": "", "session_status": "completed"}) is called
THEN no exception is raised
AND the return value is None
```

### TC-2: NoOpKnowledgeProvider Behavior

**Verifies:** [114-REQ-2.1], [114-REQ-2.2], [114-REQ-2.3], [114-REQ-2.4],
[114-REQ-2.E1]

**File:** `tests/unit/knowledge/test_provider.py`

#### TC-2.1: retrieve() always returns empty list

```
GIVEN a NoOpKnowledgeProvider instance
WHEN retrieve() is called with various spec_name and task_description values
THEN each call returns []
```

#### TC-2.2: ingest() is a no-op

```
GIVEN a NoOpKnowledgeProvider instance
WHEN ingest() is called multiple times
THEN no side effects occur (no files written, no DB changes)
```

### TC-3: Engine Does Not Import Removed Modules

**Verifies:** [114-REQ-3.2], [114-REQ-4.2], [114-REQ-5.1], [114-REQ-7.5]

**File:** `tests/unit/test_import_isolation.py`

#### TC-3.1: Engine module isolation

```
GIVEN the list of removed module names
WHEN scanning all .py files in agent_fox/engine/ for import statements
THEN no import references any removed module name
```

#### TC-3.2: Nightshift module isolation

```
GIVEN the list of removed module names
WHEN scanning all .py files in agent_fox/nightshift/ for import statements
THEN no import references any removed module name
```

#### TC-3.3: Full import succeeds

```
GIVEN the agent_fox package after all deletions
WHEN python -c "import agent_fox" is executed
THEN it exits with code 0 and no ImportError
```

### TC-4: Retrieval Error Isolation

**Verifies:** [114-REQ-3.E1]

**File:** `tests/unit/engine/test_session_lifecycle_provider.py`

#### TC-4.1: Exception in retrieve() does not block session

```
GIVEN a KnowledgeProvider whose retrieve() raises RuntimeError
WHEN the engine prepares a session using this provider
THEN the session starts with empty knowledge context
AND a WARNING-level log message is emitted
```

### TC-5: Ingestion Error Isolation

**Verifies:** [114-REQ-4.E1]

**File:** `tests/unit/engine/test_session_lifecycle_provider.py`

#### TC-5.1: Exception in ingest() does not block session completion

```
GIVEN a KnowledgeProvider whose ingest() raises RuntimeError
WHEN a session completes and the engine calls ingest()
THEN the session outcome is still recorded
AND a WARNING-level log message is emitted
AND no retry is attempted
```

### TC-6: Configuration Backward Compatibility

**Verifies:** [114-REQ-8.1], [114-REQ-8.2], [114-REQ-8.3], [114-REQ-8.4],
[114-REQ-8.5]

**File:** `tests/unit/core/test_config_knowledge.py`

#### TC-6.1: Old config fields are ignored

```
GIVEN a dictionary with old KnowledgeConfig fields (embedding_model, dedup_similarity_threshold, retrieval, sleep, etc.)
WHEN KnowledgeConfig(**dict) is constructed
THEN no ValidationError is raised
AND only store_path is set on the resulting object
```

#### TC-6.2: store_path default is preserved

```
GIVEN no arguments
WHEN KnowledgeConfig() is constructed
THEN store_path equals ".agent-fox/knowledge.duckdb"
```

### TC-7: Deleted Modules Do Not Exist

**Verifies:** [114-REQ-7.1], [114-REQ-7.2], [114-REQ-7.3], [114-REQ-7.4]

**File:** `tests/unit/test_import_isolation.py`

#### TC-7.1: Knowledge modules deleted

```
GIVEN the list of module files to be deleted
WHEN checking the filesystem
THEN none of the listed files exist
```

#### TC-7.2: lang/ directory deleted

```
GIVEN the path agent_fox/knowledge/lang/
WHEN checking the filesystem
THEN the directory does not exist
```

#### TC-7.3: sleep_tasks/ directory deleted

```
GIVEN the path agent_fox/knowledge/sleep_tasks/
WHEN checking the filesystem
THEN the directory does not exist
```

#### TC-7.4: knowledge_harvest.py deleted

```
GIVEN the path agent_fox/engine/knowledge_harvest.py
WHEN checking the filesystem
THEN the file does not exist
```

### TC-8: Review Store Unchanged

**Verifies:** CP-7

**File:** `tests/unit/knowledge/test_review_store.py` (existing)

#### TC-8.1: Existing review store tests pass

```
GIVEN the existing test suite for review_store.py
WHEN all tests are run
THEN all tests pass without modification
```

### TC-9: Barrier Cleanup

**Verifies:** [114-REQ-5.1], [114-REQ-5.2], [114-REQ-5.E1]

**File:** `tests/unit/engine/test_barrier_cleanup.py`

#### TC-9.1: Barrier does not call removed functions

```
GIVEN the barrier.py source code after changes
WHEN scanning for imports of consolidation, compaction, sleep_compute modules
THEN no such imports are found
```

#### TC-9.2: Barrier still runs rendering

```
GIVEN a sync barrier execution
WHEN the barrier sequence runs
THEN session outcome rendering still executes
AND no calls to removed functions are made
```

### TC-10: CLI Cleanup

**Verifies:** [114-REQ-9.1], [114-REQ-9.2], [114-REQ-9.3], [114-REQ-9.4]

**File:** `tests/unit/test_import_isolation.py`

#### TC-10.1: CLI modules do not import removed modules

```
GIVEN the list of removed module names
WHEN scanning all .py files in agent_fox/cli/ for import statements
THEN no import references any removed module name
```

## Traceability Matrix

| Requirement | Test Contract |
|-------------|---------------|
| [114-REQ-1.1] | TC-1.1, TC-1.2 |
| [114-REQ-1.2] | TC-1.1 |
| [114-REQ-1.3] | TC-1.4 |
| [114-REQ-1.4] | TC-1.5 |
| [114-REQ-1.E1] | TC-1.3 |
| [114-REQ-2.1] | TC-1.2, TC-2.1 |
| [114-REQ-2.2] | TC-2.2 |
| [114-REQ-2.3] | TC-2.1 |
| [114-REQ-2.4] | TC-2.1 |
| [114-REQ-2.E1] | TC-2.1 |
| [114-REQ-3.1] | TC-4.1 |
| [114-REQ-3.2] | TC-3.1 |
| [114-REQ-3.E1] | TC-4.1 |
| [114-REQ-4.1] | TC-5.1 |
| [114-REQ-4.2] | TC-3.1 |
| [114-REQ-4.3] | TC-7.4 |
| [114-REQ-4.E1] | TC-5.1 |
| [114-REQ-5.1] | TC-9.1 |
| [114-REQ-5.2] | TC-9.2 |
| [114-REQ-5.E1] | TC-9.1 |
| [114-REQ-6.1] | TC-3.2 |
| [114-REQ-6.2] | TC-3.2 |
| [114-REQ-6.3] | TC-3.2 |
| [114-REQ-6.4] | TC-3.2 |
| [114-REQ-6.E1] | TC-3.2 |
| [114-REQ-7.1] | TC-7.1 |
| [114-REQ-7.2] | TC-7.2 |
| [114-REQ-7.3] | TC-7.3 |
| [114-REQ-7.4] | TC-7.4 |
| [114-REQ-7.5] | TC-3.3 |
| [114-REQ-7.E1] | TC-3.1 |
| [114-REQ-8.1] | TC-6.1 |
| [114-REQ-8.2] | TC-6.1 |
| [114-REQ-8.3] | TC-6.1 |
| [114-REQ-8.4] | TC-6.2 |
| [114-REQ-8.5] | TC-6.1 |
| [114-REQ-9.1] | TC-10.1 |
| [114-REQ-9.2] | TC-10.1 |
| [114-REQ-9.3] | TC-10.1 |
| [114-REQ-9.4] | TC-10.1 |
| [114-REQ-9.E1] | TC-10.1 |
| [114-REQ-10.1] | TC-3.3, TC-8.1 |
| [114-REQ-10.2] | TC-1.2 |
| [114-REQ-10.3] | TC-3.1 |
| [114-REQ-10.4] | TC-7.1 |
