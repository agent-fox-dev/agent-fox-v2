# Test Specification: Package Consolidation

## Overview

Tests verify that the package consolidation is complete, DuckDB is the primary
read path, JSONL is export-only, and the KnowledgeStateMachine buffers and
flushes correctly.

## Test Fixtures

### `knowledge_conn`

An in-memory DuckDB connection with all migrations applied. Function-scoped.
Already exists from spec 38 -- reused here.

### `memory_store`

A `MemoryStore` instance backed by `knowledge_conn` and a temporary JSONL path.
Function-scoped.

### `state_machine`

A `KnowledgeStateMachine` instance backed by `memory_store`. Function-scoped.

### `sample_fact`

A `Fact` with known field values for deterministic assertions.

## Unit Tests

### TS-39-1: Module Existence

**Location:** `tests/unit/knowledge/test_package_consolidation.py`
**Requirements:** 39-REQ-1.1

- Assert that `agent_fox.knowledge.facts` is importable and contains `Fact`, `Category`, `ConfidenceLevel`, `parse_confidence`, `CONFIDENCE_MAP`, `DEFAULT_CONFIDENCE`.
- Assert that `agent_fox.knowledge.store` is importable and contains `MemoryStore`, `load_all_facts`, `load_facts_by_spec`, `append_facts`, `write_facts`, `export_facts_to_jsonl`, `DEFAULT_MEMORY_PATH`.
- Assert that `agent_fox.knowledge.filtering` is importable and contains `select_relevant_facts`.
- Assert that `agent_fox.knowledge.rendering` is importable and contains `render_summary`.
- Assert that `agent_fox.knowledge.extraction` is importable and contains `extract_facts`.
- Assert that `agent_fox.knowledge.compaction` is importable and contains `compact`.
- Assert that `agent_fox.knowledge.state_machine` is importable and contains `KnowledgeStateMachine`.

### TS-39-2: Package Deletion

**Location:** `tests/unit/knowledge/test_package_consolidation.py`
**Requirements:** 39-REQ-1.2, 39-REQ-5.1

- Assert that `import agent_fox.memory` raises `ImportError` (or `ModuleNotFoundError`).
- Assert that `from agent_fox.memory.types import Fact` raises `ImportError`.

### TS-39-3: Re-exports from __init__

**Location:** `tests/unit/knowledge/test_package_consolidation.py`
**Requirements:** 39-REQ-1.4

- Import each public symbol from `agent_fox.knowledge` (the top-level `__init__`).
- Assert each symbol is the same object as the one from its source module (e.g., `agent_fox.knowledge.Fact is agent_fox.knowledge.facts.Fact`).

### TS-39-4: DuckDB Read -- load_all_facts

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-2.1, 39-REQ-2.3, 39-REQ-2.5, 39-REQ-2.E1

- Given an empty `memory_facts` table, `load_all_facts(conn)` returns `[]`.
- Given 3 facts in `memory_facts` (none superseded), `load_all_facts(conn)` returns all 3.
- Given 3 facts where 1 has `superseded_by IS NOT NULL`, `load_all_facts(conn)` returns 2.

### TS-39-5: DuckDB Read -- load_facts_by_spec

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-2.2, 39-REQ-2.4

- Given facts for specs "alpha" and "beta", `load_facts_by_spec("alpha", conn)` returns only "alpha" facts.
- Given no facts for spec "gamma", `load_facts_by_spec("gamma", conn)` returns `[]`.

### TS-39-6: DuckDB Read Error Propagation

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-2.E2

- Given a closed DuckDB connection, `load_all_facts(conn)` raises an exception (not silently returns `[]`).

### TS-39-7: MemoryStore Write -- DuckDB Only

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-3.1

- Call `MemoryStore.write_fact(fact)` and verify:
  - The fact exists in DuckDB `memory_facts`.
  - The JSONL file was NOT written to (file does not exist or is unchanged).

### TS-39-8: JSONL Export

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-3.2

- Insert 3 facts into DuckDB via `MemoryStore`.
- Call `export_facts_to_jsonl(conn, path)`.
- Assert the JSONL file contains exactly 3 lines, each a valid JSON object with the correct fact data.
- Assert the return value is 3.

### TS-39-9: Compaction via DuckDB

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-3.3

- Insert 5 facts into DuckDB: 2 duplicates by content, 1 superseded.
- Call `compact(conn, jsonl_path)`.
- Assert return value is `(5, 3)` -- 5 original, 3 surviving.
- Assert DuckDB contains exactly 3 facts.
- Assert JSONL file contains exactly 3 lines.

### TS-39-10: JSONL Export Failure

**Location:** `tests/unit/knowledge/test_consolidation_store.py`
**Requirements:** 39-REQ-3.E1

- Insert a fact into DuckDB.
- Call `export_facts_to_jsonl(conn, path)` where `path` is a read-only location.
- Assert a warning is logged.
- Assert the fact still exists in DuckDB.

### TS-39-11: KnowledgeStateMachine -- add_fact

**Location:** `tests/unit/knowledge/test_state_machine.py`
**Requirements:** 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.4

- Create a `KnowledgeStateMachine`.
- Call `add_fact(fact)`.
- Assert `pending` contains the fact.
- Assert the fact is NOT in DuckDB.

### TS-39-12: KnowledgeStateMachine -- flush

**Location:** `tests/unit/knowledge/test_state_machine.py`
**Requirements:** 39-REQ-4.3, 39-REQ-4.5

- Add 3 facts via `add_fact()`.
- Call `flush()`.
- Assert return value is 3.
- Assert `pending` is empty.
- Assert all 3 facts exist in DuckDB.

### TS-39-13: KnowledgeStateMachine -- flush empty

**Location:** `tests/unit/knowledge/test_state_machine.py`
**Requirements:** 39-REQ-4.5

- Create a `KnowledgeStateMachine` with empty buffer.
- Call `flush()`.
- Assert return value is 0.
- Assert no DuckDB writes occurred.

### TS-39-14: KnowledgeStateMachine -- partial flush failure

**Location:** `tests/unit/knowledge/test_state_machine.py`
**Requirements:** 39-REQ-4.E1

- Add 3 facts. Mock `MemoryStore.write_fact()` to succeed for the first 2 and raise on the 3rd.
- Call `flush()` -- assert it raises.
- Assert `pending` contains only the 3rd fact.
- Assert the first 2 facts are in DuckDB.

### TS-39-15: No Stale Imports

**Location:** `tests/unit/knowledge/test_package_consolidation.py`
**Requirements:** 39-REQ-1.3, 39-REQ-5.3

- Use `subprocess` to run `grep -r "from agent_fox.memory" agent_fox/ tests/` (or equivalent).
- Assert the output is empty (no remaining old imports).

## Property Tests

### TS-39-P1: Flush Conservation

**Location:** `tests/property/knowledge/test_state_machine_props.py`
**Requirements:** 39-REQ-4.3

- Generate a list of N facts (1..50) using Hypothesis.
- Add all to a `KnowledgeStateMachine`.
- Call `flush()`.
- Assert `flush()` returns N.
- Assert `pending` is empty.
- Assert DuckDB `memory_facts` count increased by N.

### TS-39-P2: DuckDB Round-Trip Fidelity

**Location:** `tests/property/knowledge/test_consolidation_props.py`
**Requirements:** 39-REQ-2.1

- Generate a `Fact` with arbitrary valid fields using Hypothesis.
- Write it to DuckDB via `MemoryStore.write_fact()`.
- Load it back via `load_all_facts(conn)`.
- Assert the loaded fact's content, category, spec_name, confidence, and keywords match the original.

### TS-39-P3: Export-Import Round-Trip

**Location:** `tests/property/knowledge/test_consolidation_props.py`
**Requirements:** 39-REQ-3.2

- Generate N facts, write to DuckDB.
- Call `export_facts_to_jsonl(conn, path)`.
- Parse the JSONL file manually.
- Assert the exported facts match the DuckDB contents (same IDs, same content).

### TS-39-P4: Compaction Monotonicity

**Location:** `tests/property/knowledge/test_consolidation_props.py`
**Requirements:** 39-REQ-3.3

- Generate N facts with some duplicate content and some supersession chains.
- Insert into DuckDB.
- Call `compact(conn, path)`.
- Assert surviving_count <= original_count.
- Assert all surviving facts have unique content hashes.
- Assert no surviving fact's ID appears in any other fact's `supersedes` field.

## Integration Tests

No new integration tests for this spec. The structural refactor is fully
testable via unit and property tests. Existing integration tests will be
updated with new import paths as part of the consolidation.
