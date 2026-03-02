# Implementation Plan: DuckDB Knowledge Store

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the DuckDB knowledge store infrastructure for agent-fox
v2. Task groups build from failing tests through database infrastructure,
sinks, and integration. All DuckDB tests use in-memory databases or temp
files.

## Dependencies

- Spec 01 (Core Foundation) must be implemented first: provides
  `KnowledgeConfig`, `KnowledgeStoreError`, logging infrastructure.

## Test Commands

- Unit tests: `uv run pytest tests/unit/knowledge/ -q`
- Property tests: `uv run pytest tests/property/knowledge/ -q`
- All knowledge tests: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ -q`
- Linter: `uv run ruff check agent_fox/knowledge/`
- Type check: `uv run mypy agent_fox/knowledge/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory structure
    - Create `tests/unit/knowledge/__init__.py`
    - Create `tests/unit/knowledge/conftest.py` with shared fixtures:
      `knowledge_config` (KnowledgeConfig with tmp_path),
      `in_memory_conn` (duckdb.connect(":memory:")),
      `create_schema` helper function
    - Create `tests/property/knowledge/__init__.py`
    - Add `duckdb>=1.0` to test dependencies if not already present
    - Run `uv sync` to install duckdb

  - [x] 1.2 Write database lifecycle tests
    - `tests/unit/knowledge/test_db.py`: TS-11-1 (opens and creates
      schema), TS-11-2 (version recorded), TS-11-3 (close releases
      connection), TS-11-4 (context manager), TS-11-6 (schema
      idempotent)
    - _Test Spec: TS-11-1, TS-11-2, TS-11-3, TS-11-4, TS-11-6_

  - [x] 1.3 Write migration tests
    - `tests/unit/knowledge/test_migrations.py`: TS-11-5 (applies
      pending migrations)
    - _Test Spec: TS-11-5_

  - [x] 1.4 Write sink protocol and dispatcher tests
    - `tests/unit/knowledge/test_sink.py`: TS-11-11 (dispatcher multi-
      sink), TS-11-12 (protocol structural typing)
    - _Test Spec: TS-11-11, TS-11-12_

  - [x] 1.5 Write DuckDB sink tests
    - `tests/unit/knowledge/test_duckdb_sink.py`: TS-11-7 (always-on
      outcomes), TS-11-8 (debug gating), TS-11-9 (multiple touched
      paths)
    - _Test Spec: TS-11-7, TS-11-8, TS-11-9_

  - [x] 1.6 Write JSONL sink tests
    - `tests/unit/knowledge/test_jsonl_sink.py`: TS-11-10 (writes events
      to file)
    - _Test Spec: TS-11-10_

  - [x] 1.7 Write edge case tests
    - `tests/unit/knowledge/test_db.py`: TS-11-E1 (parent dir created),
      TS-11-E2 (corrupted DB degrades)
    - `tests/unit/knowledge/test_duckdb_sink.py`: TS-11-E3 (write
      failure non-fatal), TS-11-E7 (empty touched paths)
    - `tests/unit/knowledge/test_sink.py`: TS-11-E4 (dispatcher fault
      isolation)
    - `tests/unit/knowledge/test_migrations.py`: TS-11-E5 (migration
      failure)
    - `tests/unit/knowledge/test_jsonl_sink.py`: TS-11-E6 (empty
      touched paths)
    - _Test Spec: TS-11-E1..TS-11-E7_

  - [x] 1.8 Write property tests
    - `tests/property/knowledge/test_db_props.py`: TS-11-P1 (schema
      idempotency)
    - `tests/property/knowledge/test_migrations_props.py`: TS-11-P2
      (version monotonicity)
    - `tests/property/knowledge/test_sink_props.py`: TS-11-P3 (protocol
      compliance), TS-11-P4 (debug gating invariant)
    - _Test Spec: TS-11-P1, TS-11-P2, TS-11-P3, TS-11-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement database infrastructure
  - [x] 2.1 Create knowledge package
    - `agent_fox/knowledge/__init__.py`: package init, public exports
    - Add `duckdb>=1.0` to project dependencies in `pyproject.toml`
    - Run `uv sync`

  - [x] 2.2 Implement schema migration system
    - `agent_fox/knowledge/migrations.py`: Migration dataclass,
      MIGRATIONS registry, `get_current_version()`,
      `apply_pending_migrations()`, `record_version()`
    - _Requirements: 11-REQ-3.1, 11-REQ-3.2, 11-REQ-3.3, 11-REQ-3.E1_

  - [x] 2.3 Implement database connection manager
    - `agent_fox/knowledge/db.py`: KnowledgeDB class with open/close,
      context manager, VSS setup, schema creation, parent dir creation,
      `open_knowledge_store()` graceful wrapper
    - Full SQL schema as documented in design.md
    - _Requirements: 11-REQ-1.1, 11-REQ-1.2, 11-REQ-1.3, 11-REQ-1.E1,
      11-REQ-1.E2, 11-REQ-2.1, 11-REQ-2.2, 11-REQ-2.3, 11-REQ-7.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/knowledge/test_db.py tests/unit/knowledge/test_migrations.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/knowledge/test_db_props.py tests/property/knowledge/test_migrations_props.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/`
    - [x] Requirements 11-REQ-1.*, 11-REQ-2.*, 11-REQ-3.* acceptance criteria met

- [x] 3. Implement sink protocol and sink implementations
  - [x] 3.1 Implement SessionSink protocol and event dataclasses
    - `agent_fox/knowledge/sink.py`: SessionOutcome, ToolCall, ToolError
      dataclasses; SessionSink Protocol; SinkDispatcher with fault
      isolation
    - _Requirements: 11-REQ-4.1, 11-REQ-4.2, 11-REQ-4.3_

  - [x] 3.2 Implement DuckDB sink
    - `agent_fox/knowledge/duckdb_sink.py`: DuckDBSink class with
      always-on session outcomes, debug-gated tool signals, best-effort
      error handling
    - _Requirements: 11-REQ-5.1, 11-REQ-5.2, 11-REQ-5.3, 11-REQ-5.4,
      11-REQ-5.E1_

  - [x] 3.3 Implement JSONL sink
    - `agent_fox/knowledge/jsonl_sink.py`: JsonlSink class with
      timestamped file creation, JSON line writing, clean close
    - _Requirements: 11-REQ-6.1, 11-REQ-6.2, 11-REQ-6.3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/knowledge/test_sink.py tests/unit/knowledge/test_duckdb_sink.py tests/unit/knowledge/test_jsonl_sink.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/knowledge/test_sink_props.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/`
    - [x] Requirements 11-REQ-4.*, 11-REQ-5.*, 11-REQ-6.* acceptance criteria met

- [ ] 4. Integration and graceful degradation
  - [ ] 4.1 Implement graceful degradation
    - Verify `open_knowledge_store()` returns None on corrupted file
    - Verify DuckDB sink swallows write failures
    - Verify SinkDispatcher continues when a sink fails
    - _Requirements: 11-REQ-7.1, 11-REQ-7.2, 11-REQ-7.3_

  - [ ] 4.2 Wire up public API in `__init__.py`
    - Export: KnowledgeDB, open_knowledge_store, SessionSink,
      SinkDispatcher, SessionOutcome, ToolCall, ToolError, DuckDBSink,
      JsonlSink
    - Ensure all imports resolve cleanly

  - [ ] 4.V Verify task group 4
    - [ ] All spec tests pass: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ -q`
    - [ ] All edge case tests pass (TS-11-E1 through TS-11-E7)
    - [ ] All property tests pass (TS-11-P1 through TS-11-P4)
    - [ ] No regressions: `uv run pytest tests/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/`
    - [ ] Type check passes: `uv run mypy agent_fox/knowledge/`
    - [ ] Requirements 11-REQ-7.* acceptance criteria met

- [ ] 5. Checkpoint -- DuckDB Knowledge Store Complete
  - Ensure all tests pass: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/knowledge/ tests/unit/knowledge/ tests/property/knowledge/`
  - Ensure type check clean: `uv run mypy agent_fox/knowledge/`
  - Verify no regressions in existing tests: `uv run pytest tests/ -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 11-REQ-1.1 | TS-11-1, TS-11-4 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-1.2 | TS-11-1 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-1.3 | TS-11-3, TS-11-4 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-1.E1 | TS-11-E1 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-1.E2 | TS-11-3 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-2.1 | TS-11-1, TS-11-6 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-2.2 | TS-11-2, TS-11-6 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-2.3 | TS-11-1 | 2.3 | tests/unit/knowledge/test_db.py |
| 11-REQ-3.1 | TS-11-5 | 2.2 | tests/unit/knowledge/test_migrations.py |
| 11-REQ-3.2 | TS-11-5 | 2.2 | tests/unit/knowledge/test_migrations.py |
| 11-REQ-3.3 | TS-11-5 | 2.2 | tests/unit/knowledge/test_migrations.py |
| 11-REQ-3.E1 | TS-11-E5 | 2.2 | tests/unit/knowledge/test_migrations.py |
| 11-REQ-4.1 | TS-11-12 | 3.1 | tests/unit/knowledge/test_sink.py |
| 11-REQ-4.2 | TS-11-11 | 3.1 | tests/unit/knowledge/test_sink.py |
| 11-REQ-4.3 | TS-11-11, TS-11-E4 | 3.1 | tests/unit/knowledge/test_sink.py |
| 11-REQ-5.1 | TS-11-7, TS-11-12 | 3.2 | tests/unit/knowledge/test_duckdb_sink.py |
| 11-REQ-5.2 | TS-11-7, TS-11-9, TS-11-E7 | 3.2 | tests/unit/knowledge/test_duckdb_sink.py |
| 11-REQ-5.3 | TS-11-8 | 3.2 | tests/unit/knowledge/test_duckdb_sink.py |
| 11-REQ-5.4 | TS-11-8 | 3.2 | tests/unit/knowledge/test_duckdb_sink.py |
| 11-REQ-5.E1 | TS-11-E3 | 3.2 | tests/unit/knowledge/test_duckdb_sink.py |
| 11-REQ-6.1 | TS-11-10, TS-11-12 | 3.3 | tests/unit/knowledge/test_jsonl_sink.py |
| 11-REQ-6.2 | TS-11-10, TS-11-E6 | 3.3 | tests/unit/knowledge/test_jsonl_sink.py |
| 11-REQ-6.3 | -- | 3.3 | (orchestrator-level test) |
| 11-REQ-7.1 | TS-11-E2 | 4.1 | tests/unit/knowledge/test_db.py |
| 11-REQ-7.2 | TS-11-E3 | 4.1 | tests/unit/knowledge/test_duckdb_sink.py |
| 11-REQ-7.3 | TS-11-E2 | 4.1 | tests/unit/knowledge/test_db.py |
| Property 1 | TS-11-P1 | 2.3 | tests/property/knowledge/test_db_props.py |
| Property 2 | TS-11-P2 | 2.2 | tests/property/knowledge/test_migrations_props.py |
| Property 3 | TS-11-P3 | 3.1, 3.2, 3.3 | tests/property/knowledge/test_sink_props.py |
| Property 5 | TS-11-P4 | 3.2 | tests/property/knowledge/test_sink_props.py |

## Notes

- All DuckDB tests use `duckdb.connect(":memory:")` or `tmp_path` -- never
  touch the real `.agent-fox/knowledge.duckdb`.
- The VSS extension may not be available in CI. Tests that require VSS should
  use `pytest.importorskip` or check for extension availability and skip
  gracefully.
- Task group 1 must create the test directory structure and install `duckdb`
  as a dependency so that tests can import.
- The `create_schema` helper in `conftest.py` should execute the same DDL as
  `KnowledgeDB._initialize_schema` to keep test fixtures aligned with the
  real schema.
- JSONL sink tests should verify file content by reading and parsing each
  line as JSON.
