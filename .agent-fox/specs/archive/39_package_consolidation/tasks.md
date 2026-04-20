# Implementation Plan: Package Consolidation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in four groups: (1) write failing tests, (2) move
modules and update imports, (3) implement DuckDB read path and JSONL
export-only, (4) implement KnowledgeStateMachine and final cleanup.

## Test Commands

- Spec tests: `uv run pytest tests/unit/knowledge/test_package_consolidation.py tests/unit/knowledge/test_consolidation_store.py tests/unit/knowledge/test_state_machine.py -v`
- Property tests: `uv run pytest tests/property/knowledge/test_state_machine_props.py tests/property/knowledge/test_consolidation_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`
- Stale imports: `grep -r "from agent_fox\.memory" agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/knowledge/test_package_consolidation.py`
    - Test class `TestModuleExistence` with TS-39-1
    - Test class `TestPackageDeletion` with TS-39-2
    - Test class `TestReExports` with TS-39-3
    - Test class `TestNoStaleImports` with TS-39-15
    - _Test Spec: TS-39-1, TS-39-2, TS-39-3, TS-39-15_

  - [x] 1.2 Create `tests/unit/knowledge/test_consolidation_store.py`
    - Test class `TestDuckDBLoadAllFacts` with TS-39-4
    - Test class `TestDuckDBLoadBySpec` with TS-39-5
    - Test class `TestDuckDBReadError` with TS-39-6
    - Test class `TestMemoryStoreDuckDBOnly` with TS-39-7
    - Test class `TestJSONLExport` with TS-39-8
    - Test class `TestCompactionViaDuckDB` with TS-39-9
    - Test class `TestJSONLExportFailure` with TS-39-10
    - _Test Spec: TS-39-4, TS-39-5, TS-39-6, TS-39-7, TS-39-8, TS-39-9, TS-39-10_

  - [x] 1.3 Create `tests/unit/knowledge/test_state_machine.py`
    - Test class `TestAddFact` with TS-39-11
    - Test class `TestFlush` with TS-39-12
    - Test class `TestFlushEmpty` with TS-39-13
    - Test class `TestPartialFlushFailure` with TS-39-14
    - _Test Spec: TS-39-11, TS-39-12, TS-39-13, TS-39-14_

  - [x] 1.4 Create `tests/property/knowledge/test_state_machine_props.py`
    - Property test `TestFlushConservation` with TS-39-P1
    - _Test Spec: TS-39-P1_

  - [x] 1.5 Create `tests/property/knowledge/test_consolidation_props.py`
    - Property test `TestDuckDBRoundTrip` with TS-39-P2
    - Property test `TestExportImportRoundTrip` with TS-39-P3
    - Property test `TestCompactionMonotonicity` with TS-39-P4
    - _Test Spec: TS-39-P2, TS-39-P3, TS-39-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings: `uv run ruff check tests/unit/knowledge/test_package_consolidation.py tests/unit/knowledge/test_consolidation_store.py tests/unit/knowledge/test_state_machine.py tests/property/knowledge/test_state_machine_props.py tests/property/knowledge/test_consolidation_props.py`

- [x] 2. Move modules and update all imports
  - [x] 2.1 Copy modules from `agent_fox/memory/` to `agent_fox/knowledge/`
    - `types.py` -> `facts.py`
    - `memory.py` -> `store.py`
    - `filter.py` -> `filtering.py`
    - `render.py` -> `rendering.py`
    - `extraction.py` -> `extraction.py` (overwrite existing or merge if needed)
    - `compaction.py` -> `compaction.py`
    - Update all internal imports within moved modules (e.g., `agent_fox.memory.types` -> `agent_fox.knowledge.facts`)
    - _Requirements: 39-REQ-1.1_

  - [x] 2.2 Update `agent_fox/knowledge/__init__.py` with re-exports
    - Add all public symbols listed in 39-REQ-1.4
    - _Requirements: 39-REQ-1.4_

  - [x] 2.3 Update imports in production code
    - `agent_fox/engine/knowledge_harvest.py`
    - `agent_fox/engine/engine.py`
    - `agent_fox/engine/reset.py`
    - `agent_fox/engine/session_lifecycle.py`
    - `agent_fox/engine/fact_cache.py`
    - `agent_fox/fix/analyzer.py`
    - `agent_fox/reporting/status.py`
    - Any other files found by `grep -r "from agent_fox.memory" agent_fox/`
    - _Requirements: 39-REQ-1.3_

  - [x] 2.4 Move and update test files
    - Move `tests/unit/memory/` contents to `tests/unit/knowledge/` (merge with existing)
    - Move `tests/property/memory/` contents to `tests/property/knowledge/` (merge with existing)
    - Update all imports in moved test files
    - Update any test files in other directories that import from `agent_fox.memory`
    - _Requirements: 39-REQ-1.5_

  - [x] 2.5 Update templates and non-Python references
    - Check `agent_fox/_templates/` for `agent_fox.memory` references
    - Check `docs/` for stale references
    - _Requirements: 39-REQ-1.E1_

  - [x] 2.6 Delete `agent_fox/memory/` package
    - Remove the entire `agent_fox/memory/` directory
    - Remove empty `tests/unit/memory/` and `tests/property/memory/` directories
    - _Requirements: 39-REQ-1.2_

  - [x] 2.V Verify task group 2
    - [x] `grep -r "from agent_fox\.memory" agent_fox/ tests/` returns no results
    - [x] `uv run ruff check agent_fox/ tests/` passes
    - [x] `uv run pytest -x -q` passes (all existing tests with updated imports)
    - [x] TS-39-1, TS-39-2, TS-39-3, TS-39-15 tests pass
    - [x] Requirements 39-REQ-1.*, 39-REQ-5.* met

- [x] 3. DuckDB primary read path and JSONL export-only
  - [x] 3.1 Update `load_all_facts()` in `agent_fox/knowledge/store.py`
    - Change signature: `path: Path` -> `conn: duckdb.DuckDBPyConnection`
    - Query `memory_facts` table, exclude `superseded_by IS NOT NULL`
    - Return list of `Fact` objects
    - _Requirements: 39-REQ-2.1, 39-REQ-2.3, 39-REQ-2.5, 39-REQ-2.E1_

  - [x] 3.2 Update `load_facts_by_spec()` in `agent_fox/knowledge/store.py`
    - Change signature: `path: Path` -> `conn: duckdb.DuckDBPyConnection`
    - Query with `WHERE spec_name = ?` and `superseded_by IS NULL`
    - _Requirements: 39-REQ-2.2, 39-REQ-2.4_

  - [x] 3.3 Update `MemoryStore.write_fact()` in `agent_fox/knowledge/store.py`
    - Remove JSONL append from `write_fact()`
    - Keep DuckDB write and embedding write
    - _Requirements: 39-REQ-3.1_

  - [x] 3.4 Add `export_facts_to_jsonl()` function
    - Load all non-superseded facts from DuckDB
    - Write to JSONL file (full overwrite)
    - Log warning on write failure, do not roll back DuckDB
    - Return count of exported facts
    - _Requirements: 39-REQ-3.2, 39-REQ-3.E1_

  - [x] 3.5 Update `compact()` in `agent_fox/knowledge/compaction.py`
    - Change signature to accept `conn` and optional `jsonl_path`
    - Read from DuckDB, deduplicate, resolve supersession
    - Update DuckDB (delete removed facts)
    - Export to JSONL via `export_facts_to_jsonl()`
    - _Requirements: 39-REQ-3.3_

  - [x] 3.6 Update `render_summary()` in `agent_fox/knowledge/rendering.py`
    - Change signature to accept `conn` instead of `memory_path`
    - Load facts via `load_all_facts(conn)`
    - _Requirements: 39-REQ-2.1 (transitive)_

  - [x] 3.7 Update all callers of `load_all_facts()`, `load_facts_by_spec()`, `render_summary()`, and `compact()`
    - Pass DuckDB connection instead of JSONL path
    - Update `agent_fox/engine/knowledge_harvest.py`
    - Update `agent_fox/engine/session_lifecycle.py`
    - Update `agent_fox/engine/engine.py`
    - Update `agent_fox/engine/reset.py`
    - Update `agent_fox/engine/fact_cache.py`
    - Update `agent_fox/reporting/status.py`
    - Update any test files that call these functions
    - _Requirements: 39-REQ-2.1, 39-REQ-2.2 (transitive)_

  - [x] 3.V Verify task group 3
    - [x] TS-39-4, TS-39-5, TS-39-6, TS-39-7, TS-39-8, TS-39-9, TS-39-10 tests pass
    - [x] TS-39-P2, TS-39-P3, TS-39-P4 property tests pass
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] Requirements 39-REQ-2.*, 39-REQ-3.* met

- [x] 4. KnowledgeStateMachine and final verification
  - [x] 4.1 Create `agent_fox/knowledge/state_machine.py`
    - Implement `KnowledgeStateMachine` class
    - `__init__(self, store: MemoryStore)`
    - `pending` property returning copy of buffer
    - `add_fact(fact: Fact)` appending to buffer
    - `flush()` writing all buffered facts via `MemoryStore.write_fact()`, clearing buffer, returning count
    - Partial failure handling: remove written facts from buffer, re-raise
    - _Requirements: 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.3, 39-REQ-4.4, 39-REQ-4.5, 39-REQ-4.6, 39-REQ-4.E1_

  - [x] 4.2 Add `KnowledgeStateMachine` to `agent_fox/knowledge/__init__.py` re-exports
    - _Requirements: 39-REQ-1.4_

  - [x] 4.3 Add session-end JSONL export call
    - In the session lifecycle (or engine shutdown), call `export_facts_to_jsonl()` after the final flush
    - _Requirements: 39-REQ-3.2_

  - [x] 4.4 Final verification
    - [x] All spec tests pass: `uv run pytest tests/unit/knowledge/test_package_consolidation.py tests/unit/knowledge/test_consolidation_store.py tests/unit/knowledge/test_state_machine.py -v`
    - [x] All property tests pass: `uv run pytest tests/property/knowledge/test_state_machine_props.py tests/property/knowledge/test_consolidation_props.py -v`
    - [x] Full test suite passes: `uv run pytest -x -q`
    - [x] `grep -r "from agent_fox\.memory" agent_fox/ tests/` returns no results
    - [x] `agent_fox/memory/` directory does not exist
    - [x] Requirements 39-REQ-4.* met
    - [x] All 39-REQ-* acceptance criteria met

  - [x] 4.V Verify task group 4
    - [x] All spec tests pass
    - [x] Clean working tree (no uncommitted changes)

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 39-REQ-1.1 | TS-39-1 | 2.1 | `test_package_consolidation.py::TestModuleExistence` |
| 39-REQ-1.2 | TS-39-2 | 2.6 | `test_package_consolidation.py::TestPackageDeletion` |
| 39-REQ-1.3 | TS-39-15 | 2.3, 2.4 | `test_package_consolidation.py::TestNoStaleImports` |
| 39-REQ-1.4 | TS-39-3 | 2.2 | `test_package_consolidation.py::TestReExports` |
| 39-REQ-1.5 | TS-39-15 | 2.4 | `test_package_consolidation.py::TestNoStaleImports` |
| 39-REQ-1.E1 | TS-39-15 | 2.5 | `test_package_consolidation.py::TestNoStaleImports` |
| 39-REQ-2.1 | TS-39-4 | 3.1 | `test_consolidation_store.py::TestDuckDBLoadAllFacts` |
| 39-REQ-2.2 | TS-39-5 | 3.2 | `test_consolidation_store.py::TestDuckDBLoadBySpec` |
| 39-REQ-2.3 | TS-39-4 | 3.1 | `test_consolidation_store.py::TestDuckDBLoadAllFacts` |
| 39-REQ-2.4 | TS-39-5 | 3.2 | `test_consolidation_store.py::TestDuckDBLoadBySpec` |
| 39-REQ-2.5 | TS-39-4 | 3.1 | `test_consolidation_store.py::TestDuckDBLoadAllFacts` |
| 39-REQ-2.E1 | TS-39-4 | 3.1 | `test_consolidation_store.py::TestDuckDBLoadAllFacts` |
| 39-REQ-2.E2 | TS-39-6 | 3.1 | `test_consolidation_store.py::TestDuckDBReadError` |
| 39-REQ-3.1 | TS-39-7 | 3.3 | `test_consolidation_store.py::TestMemoryStoreDuckDBOnly` |
| 39-REQ-3.2 | TS-39-8 | 3.4 | `test_consolidation_store.py::TestJSONLExport` |
| 39-REQ-3.3 | TS-39-9 | 3.5 | `test_consolidation_store.py::TestCompactionViaDuckDB` |
| 39-REQ-3.4 | TS-39-7 | 3.3 | `test_consolidation_store.py::TestMemoryStoreDuckDBOnly` |
| 39-REQ-3.E1 | TS-39-10 | 3.4 | `test_consolidation_store.py::TestJSONLExportFailure` |
| 39-REQ-4.1 | TS-39-11 | 4.1 | `test_state_machine.py::TestAddFact` |
| 39-REQ-4.2 | TS-39-11 | 4.1 | `test_state_machine.py::TestAddFact` |
| 39-REQ-4.3 | TS-39-12 | 4.1 | `test_state_machine.py::TestFlush` |
| 39-REQ-4.4 | TS-39-11 | 4.1 | `test_state_machine.py::TestAddFact` |
| 39-REQ-4.5 | TS-39-13 | 4.1 | `test_state_machine.py::TestFlushEmpty` |
| 39-REQ-4.6 | TS-39-11 | 4.1 | `test_state_machine.py::TestAddFact` |
| 39-REQ-4.E1 | TS-39-14 | 4.1 | `test_state_machine.py::TestPartialFlushFailure` |
| 39-REQ-5.1 | TS-39-2 | 2.6 | `test_package_consolidation.py::TestPackageDeletion` |
| 39-REQ-5.2 | 4.V | 2.*, 3.*, 4.* | Full test suite (`uv run pytest -x -q`) |
| 39-REQ-5.3 | 4.V | 2.*, 3.*, 4.* | `uv run ruff check agent_fox/ tests/` |
| Property 1 | TS-39-P1 | 4.1 | `test_state_machine_props.py::TestFlushConservation` |
| Property 2 | TS-39-P2 | 3.1 | `test_consolidation_props.py::TestDuckDBRoundTrip` |
| Property 3 | TS-39-P3 | 3.4 | `test_consolidation_props.py::TestExportImportRoundTrip` |
| Property 4 | TS-39-P4 | 3.5 | `test_consolidation_props.py::TestCompactionMonotonicity` |

## Notes

- Task group 2 has the largest blast radius: every file that imports from
  `agent_fox.memory` must be updated. Use `grep -r` to ensure completeness.
- The `extraction.py` module exists in both packages currently. The knowledge
  package does NOT have its own `extraction.py` -- the existing
  `agent_fox/knowledge/` files are: `blocking_history.py`, `causal.py`,
  `db.py`, `duckdb_sink.py`, `embeddings.py`, `ingest.py`, `jsonl_sink.py`,
  `migrations.py`, `project_model.py`, `query.py`, `review_store.py`,
  `search.py`, `sink.py`. So `extraction.py` can be moved without conflict.
- Some test files in `tests/unit/knowledge/` already exist (e.g.,
  `test_dual_write.py`, `test_duckdb_hardening.py`). Moving memory tests
  into the same directory requires checking for name collisions.
- The `conftest.py` files in `tests/unit/memory/` and `tests/property/memory/`
  may contain fixtures that need to be merged into the knowledge test
  directories' conftest files.
