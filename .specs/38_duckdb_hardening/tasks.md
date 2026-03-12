# Implementation Plan: DuckDB Hardening

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in five groups: (1) write failing tests, (2) harden
initialization and add test fixture, (3) remove optional parameters from
session lifecycle and knowledge harvest, (4) harden memory store, context
assembly, and routing, (5) update existing tests to use DuckDB fixture.

The ordering ensures the foundation (initialization + fixture) is built first,
then parameters are hardened module by module, and finally existing tests are
migrated.

## Test Commands

- Spec tests: `uv run pytest tests/unit/knowledge/test_duckdb_hardening.py tests/unit/engine/test_hardening_lifecycle.py tests/unit/memory/test_hardening_store.py -v`
- Property tests: `uv run pytest tests/property/knowledge/test_duckdb_hardening_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/knowledge/test_duckdb_hardening.py`
    - Test class `TestInitialization` with TS-38-1, TS-38-2, TS-38-E1
    - Test class `TestDuckDBSinkPropagation` with TS-38-8
    - Test class `TestKnowledgeHarvestPropagation` with TS-38-10
    - Test class `TestFixtureIsolation` with TS-38-12
    - _Test Spec: TS-38-1, TS-38-2, TS-38-8, TS-38-10, TS-38-12, TS-38-E1_

  - [x] 1.2 Create `tests/unit/engine/test_hardening_lifecycle.py`
    - Test class `TestRequiredParameters` with TS-38-3, TS-38-4
    - _Test Spec: TS-38-3, TS-38-4_

  - [x] 1.3 Create `tests/unit/memory/test_hardening_store.py`
    - Test class `TestMemoryStoreRequired` with TS-38-5
    - Test class `TestMemoryStorePropagation` with TS-38-9
    - _Test Spec: TS-38-5, TS-38-9_

  - [x] 1.4 Create tests for context and routing hardening
    - Test class `TestContextAssemblyRequired` with TS-38-6, TS-38-11, TS-38-E2
      in `tests/unit/knowledge/test_duckdb_hardening.py`
    - Test class `TestRoutingRequired` with TS-38-7
      in `tests/unit/knowledge/test_duckdb_hardening.py`
    - _Test Spec: TS-38-6, TS-38-7, TS-38-11, TS-38-E2_

  - [x] 1.5 Create `tests/property/knowledge/test_duckdb_hardening_props.py`
    - Property tests TS-38-P1, TS-38-P2
    - _Test Spec: TS-38-P1, TS-38-P2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests PASS (implementation was completed in prior sessions)
    - [x] No linter warnings: `uv run ruff check tests/unit/knowledge/test_duckdb_hardening.py tests/unit/engine/test_hardening_lifecycle.py tests/unit/memory/test_hardening_store.py tests/property/knowledge/test_duckdb_hardening_props.py`

- [x] 2. Harden initialization and add test fixture
  - [x] 2.1 Update `open_knowledge_store()` in `agent_fox/knowledge/db.py`
    - Change return type from `KnowledgeDB | None` to `KnowledgeDB`
    - Replace try/except that returns None with RuntimeError raise
    - Include file path and underlying error in message
    - _Requirements: 38-REQ-1.1, 38-REQ-1.2, 38-REQ-1.E1_

  - [x] 2.2 Add DuckDB test fixture
    - Add `knowledge_conn` fixture to `tests/conftest.py`
    - Creates in-memory DuckDB with all migrations applied
    - Fresh per test (function-scoped)
    - Add `knowledge_db` fixture wrapping `KnowledgeDB`
    - _Requirements: 38-REQ-5.1, 38-REQ-5.2_

  - [x] 2.3 Update CLI initialization in `agent_fox/cli/code.py`
    - Remove `if knowledge_db is not None` guards (4 locations)
    - Let RuntimeError from `open_knowledge_store()` propagate
    - Always register DuckDBSink
    - Always pass knowledge_db to AssessmentPipeline
    - _Requirements: 38-REQ-1.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/knowledge/test_duckdb_hardening.py::TestInitialization tests/unit/knowledge/test_duckdb_hardening.py::TestFixtureIsolation -v`
    - [x] Property tests pass: `uv run pytest tests/property/knowledge/test_duckdb_hardening_props.py -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/db.py agent_fox/cli/code.py`
    - [x] Requirements 38-REQ-1.*, 38-REQ-5.* met

- [x] 3. Harden session lifecycle and knowledge harvest
  - [x] 3.1 Update `NodeSessionRunner` in `agent_fox/engine/session_lifecycle.py`
    - Change `knowledge_db: KnowledgeDB | None = None` to `knowledge_db: KnowledgeDB`
    - Remove `if self._knowledge_db is not None` guard in causal enhancement
    - Remove try/except fallback to keyword-only facts
    - _Requirements: 38-REQ-2.1, 38-REQ-2.3_

  - [x] 3.2 Update `extract_and_store_knowledge()` in `agent_fox/engine/knowledge_harvest.py`
    - Change `knowledge_db: KnowledgeDB | None = None` to `knowledge_db: KnowledgeDB`
    - Remove `if knowledge_db is None: return` guard
    - _Requirements: 38-REQ-2.1, 38-REQ-2.3_

  - [x] 3.3 Update `sync_facts_to_duckdb()` in `agent_fox/engine/knowledge_harvest.py`
    - Change `knowledge_db: KnowledgeDB | None` to `knowledge_db: KnowledgeDB`
    - Remove `if knowledge_db is None: return` guard
    - Remove per-fact try/except that silently continues
    - _Requirements: 38-REQ-2.1, 38-REQ-3.4_

  - [x] 3.4 Update `_extract_causal_links()` in `agent_fox/engine/knowledge_harvest.py`
    - Change `knowledge_db: KnowledgeDB | None` to `knowledge_db: KnowledgeDB`
    - Remove `if knowledge_db is None: return` guard
    - Remove outer try/except that silently logs
    - _Requirements: 38-REQ-2.1, 38-REQ-3.3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/engine/test_hardening_lifecycle.py tests/unit/knowledge/test_duckdb_hardening.py::TestKnowledgeHarvestPropagation -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/session_lifecycle.py agent_fox/engine/knowledge_harvest.py`
    - [x] Requirements 38-REQ-2.1, 38-REQ-2.3, 38-REQ-3.3, 38-REQ-3.4 met

- [ ] 4. Harden memory store, context assembly, routing, and sink
  - [ ] 4.1 Update `MemoryStore` in `agent_fox/memory/memory.py`
    - Change `db_conn: duckdb.DuckDBPyConnection | None = None` to required
    - Remove `if self._db_conn is None` guards in `write_fact()` and `mark_superseded()`
    - Remove try/except around DuckDB writes — let errors propagate
    - _Requirements: 38-REQ-2.2, 38-REQ-2.4, 38-REQ-3.2_

  - [ ] 4.2 Update `assemble_context()` in `agent_fox/session/prompt.py`
    - Change `conn: duckdb.DuckDBPyConnection | None = None` to required
    - Remove file-based fallback for review/verification/drift rendering
    - Remove outer try/except around DB rendering
    - _Requirements: 38-REQ-4.1, 38-REQ-4.2, 38-REQ-4.3, 38-REQ-3.E1_

  - [ ] 4.3 Update `AssessmentPipeline` in `agent_fox/routing/assessor.py`
    - Change `db: duckdb.DuckDBPyConnection | None` to required
    - Remove `_get_outcome_count()` fallback returning 0 when db is None
    - _Requirements: 38-REQ-6.1, 38-REQ-6.2_

  - [ ] 4.4 Update `DuckDBSink` in `agent_fox/knowledge/duckdb_sink.py`
    - Remove try/except in `record_session_outcome()`, `record_tool_call()`,
      `record_tool_error()` — let DuckDB errors propagate
    - _Requirements: 38-REQ-3.1_

  - [ ] 4.5 Update `fix/analyzer.py`
    - Remove try/except around `query_oracle_context()` and `load_review_context()`
    - Let DuckDB errors propagate
    - _Requirements: 38-REQ-3.1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/memory/test_hardening_store.py tests/unit/knowledge/test_duckdb_hardening.py::TestDuckDBSinkPropagation tests/unit/knowledge/test_duckdb_hardening.py::TestContextAssemblyRequired tests/unit/knowledge/test_duckdb_hardening.py::TestRoutingRequired -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/memory.py agent_fox/session/prompt.py agent_fox/routing/assessor.py agent_fox/knowledge/duckdb_sink.py agent_fox/fix/analyzer.py`
    - [ ] Requirements 38-REQ-2.2, 38-REQ-2.4, 38-REQ-3.*, 38-REQ-4.*, 38-REQ-6.* met

- [ ] 5. Migrate existing tests to use DuckDB fixture
  - [ ] 5.1 Audit existing tests for None connection patterns
    - Grep for `db_conn=None`, `knowledge_db=None`, `conn=None` in tests/
    - List all test files that need updating
    - _Requirements: 38-REQ-5.3_

  - [ ] 5.2 Update existing tests to use `knowledge_conn` fixture
    - Replace `None` connections with fixture
    - Ensure all tests pass with real DuckDB connections
    - _Requirements: 38-REQ-5.3_

  - [ ] 5.3 Update documentation
    - Document DuckDB as hard requirement in README.md
    - Update any developer setup guides
    - _Requirements: documentation_

  - [ ] 5.V Verify task group 5
    - [ ] All tests pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [ ] No remaining `knowledge_db=None` or `db_conn=None` patterns in production code
    - [ ] All 38-REQ-* acceptance criteria met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 38-REQ-1.1 | TS-38-1 | 2.1 | `test_duckdb_hardening.py::TestInitialization::test_raises_on_failure` |
| 38-REQ-1.2 | TS-38-1 | 2.1 | `test_duckdb_hardening.py::TestInitialization::test_no_none_return` |
| 38-REQ-1.3 | TS-38-2 | 2.3 | `test_duckdb_hardening.py::TestInitialization::test_returns_knowledgedb` |
| 38-REQ-1.E1 | TS-38-E1 | 2.1 | `test_duckdb_hardening.py::TestInitialization::test_error_includes_path` |
| 38-REQ-2.1 | TS-38-3, TS-38-4 | 3.1, 3.2, 3.3, 3.4 | `test_hardening_lifecycle.py::TestRequiredParameters` |
| 38-REQ-2.2 | TS-38-5, TS-38-6, TS-38-7 | 4.1, 4.2, 4.3 | `test_hardening_store.py`, `test_duckdb_hardening.py` |
| 38-REQ-2.3 | TS-38-4 | 3.1, 3.2, 3.3, 3.4 | `test_hardening_lifecycle.py` |
| 38-REQ-2.4 | TS-38-5 | 4.1 | `test_hardening_store.py::TestMemoryStoreRequired` |
| 38-REQ-3.1 | TS-38-8 | 4.4 | `test_duckdb_hardening.py::TestDuckDBSinkPropagation` |
| 38-REQ-3.2 | TS-38-9 | 4.1 | `test_hardening_store.py::TestMemoryStorePropagation` |
| 38-REQ-3.3 | TS-38-10 | 3.4 | `test_duckdb_hardening.py::TestKnowledgeHarvestPropagation` |
| 38-REQ-3.4 | TS-38-10 | 3.3 | `test_duckdb_hardening.py::TestKnowledgeHarvestPropagation` |
| 38-REQ-3.E1 | TS-38-E2 | 4.2 | `test_duckdb_hardening.py::TestContextAssemblyRequired` |
| 38-REQ-4.1 | TS-38-6 | 4.2 | `test_duckdb_hardening.py::TestContextAssemblyRequired` |
| 38-REQ-4.2 | TS-38-11 | 4.2 | `test_duckdb_hardening.py::TestContextAssemblyRequired` |
| 38-REQ-4.3 | TS-38-11 | 4.2 | `test_duckdb_hardening.py::TestContextAssemblyRequired` |
| 38-REQ-5.1 | TS-38-12 | 2.2 | `test_duckdb_hardening.py::TestFixtureIsolation` |
| 38-REQ-5.2 | TS-38-12 | 2.2 | `test_duckdb_hardening.py::TestFixtureIsolation` |
| 38-REQ-5.3 | TS-38-12 | 5.2 | `test_duckdb_hardening.py::TestFixtureIsolation` |
| 38-REQ-6.1 | TS-38-7 | 4.3 | `test_duckdb_hardening.py::TestRoutingRequired` |
| 38-REQ-6.2 | TS-38-7 | 4.3 | `test_duckdb_hardening.py::TestRoutingRequired` |
| Property 1 | TS-38-P1 | 2.1 | `test_duckdb_hardening_props.py::TestInitNeverNone` |
| Property 4 | TS-38-P2 | 2.2 | `test_duckdb_hardening_props.py::TestFixtureIsolation` |

## Notes

- This spec has a large blast radius — many existing tests will need the
  DuckDB fixture added. Task group 5 handles this systematically.
- The `MemoryStore` dual-write pattern (JSONL + DuckDB) remains: JSONL is
  the append-only log, DuckDB is the queryable index. Both must succeed.
  If DuckDB fails, the error propagates and the session fails.
- Some callers of `assemble_context()` in tests use `conn=None`. These must
  be updated to pass a real connection via the fixture.
- The `_ingest_if_available()` function in `cli/code.py` should be renamed
  to remove the "if available" qualifier once DuckDB is mandatory.
