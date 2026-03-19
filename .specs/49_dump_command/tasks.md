# Implementation Plan: `dump` CLI Command

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The `dump` command is a thin CLI layer over existing knowledge-store
infrastructure. Task group 1 writes failing tests, task group 2 implements
the `knowledge/dump.py` module and the `rendering.render_summary_json()`
function, and task group 3 wires the CLI command and registers it.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_dump.py tests/unit/test_dump_db.py tests/property/test_dump_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/ && uv run ruff format --check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/test_dump.py` — CLI-level tests
    - TS-49-1: command registration
    - TS-49-2: error when no flags
    - TS-49-3: error when both flags
    - TS-49-4: memory Markdown export
    - TS-49-5: memory JSON export
    - TS-49-6: confirmation message
    - TS-49-11: error when DB missing
    - TS-49-E1: empty facts Markdown
    - TS-49-E2: empty facts JSON
    - _Test Spec: TS-49-1 through TS-49-6, TS-49-11, TS-49-E1, TS-49-E2_

  - [x] 1.2 Create `tests/unit/test_dump_db.py` — DB-dump module tests
    - TS-49-7: DB dump Markdown
    - TS-49-8: DB dump JSON
    - TS-49-9: confirmation message
    - TS-49-10: cell truncation
    - TS-49-E3: no tables
    - _Test Spec: TS-49-7 through TS-49-10, TS-49-E3_

  - [x] 1.3 Create `tests/property/test_dump_props.py` — property tests
    - TS-49-P1: fact count preservation
    - TS-49-P2: JSON key completeness
    - TS-49-P3: table coverage
    - _Test Spec: TS-49-P1, TS-49-P2, TS-49-P3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/test_dump.py tests/unit/test_dump_db.py tests/property/test_dump_props.py`

- [x] 2. Implement knowledge dump module and memory JSON export
  - [x] 2.1 Create `agent_fox/knowledge/dump.py`
    - `discover_tables(conn)` — list all table names
    - `dump_table_md(conn, table)` — render one table as Markdown
    - `dump_all_tables_md(conn, output)` — write all tables to Markdown file
    - `dump_all_tables_json(conn, output)` — write all tables to JSON file
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 2.2 Add `render_summary_json()` to `agent_fox/knowledge/rendering.py`
    - Read all facts via `read_all_facts(conn)`
    - Serialize to JSON with `facts` array and `generated` timestamp
    - Handle empty-facts case (empty array)
    - _Requirements: 2.2, 2.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_dump_db.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/dump.py agent_fox/knowledge/rendering.py`
    - [x] Requirements 2.2, 3.1, 3.2, 3.4 acceptance criteria met

- [x] 3. Implement CLI command and register it
  - [x] 3.1 Create `agent_fox/cli/dump.py`
    - Click command with `--memory` and `--db` flags
    - Flag validation (mutual exclusivity, at-least-one)
    - DB existence check using `DEFAULT_DB_PATH`
    - Read-only DuckDB connection
    - Dispatch to memory or DB export based on flag and JSON mode
    - Confirmation messages to stderr
    - _Requirements: 1.1, 1.2, 1.E1, 2.1, 2.3, 3.3, 3.E1, 4.1, 5.1_

  - [x] 3.2 Register command in `agent_fox/cli/app.py`
    - Import `dump_cmd` and add via `main.add_command(dump_cmd, name="dump")`
    - _Requirements: 1.1_

  - [x] 3.3 Update CLI reference documentation in `docs/cli-reference.md`
    - Document the `dump` command, its flags, and output files
    - _Requirements: 1.1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_dump.py tests/unit/test_dump_db.py tests/property/test_dump_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/cli/dump.py agent_fox/cli/app.py`
    - [x] Requirements 1.1, 1.2, 1.E1, 2.1, 2.3, 3.3, 3.E1, 4.1, 5.1 acceptance criteria met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 49-REQ-1.1 | TS-49-1 | 3.1, 3.2 | `test_dump.py::test_command_registered` |
| 49-REQ-1.2 | TS-49-2 | 3.1 | `test_dump.py::test_no_flags_error` |
| 49-REQ-1.E1 | TS-49-3 | 3.1 | `test_dump.py::test_both_flags_error` |
| 49-REQ-2.1 | TS-49-4 | 3.1 | `test_dump.py::test_memory_markdown` |
| 49-REQ-2.2 | TS-49-5 | 2.2, 3.1 | `test_dump.py::test_memory_json` |
| 49-REQ-2.3 | TS-49-6 | 3.1 | `test_dump.py::test_memory_confirmation` |
| 49-REQ-2.E1 | TS-49-E1, TS-49-E2 | 2.2, 3.1 | `test_dump.py::test_memory_empty_*` |
| 49-REQ-3.1 | TS-49-7 | 2.1 | `test_dump_db.py::test_db_dump_markdown` |
| 49-REQ-3.2 | TS-49-8 | 2.1 | `test_dump_db.py::test_db_dump_json` |
| 49-REQ-3.3 | TS-49-9 | 3.1 | `test_dump_db.py::test_db_dump_confirmation` |
| 49-REQ-3.4 | TS-49-10 | 2.1 | `test_dump_db.py::test_cell_truncation` |
| 49-REQ-3.E1 | TS-49-E3 | 3.1 | `test_dump_db.py::test_no_tables_error` |
| 49-REQ-4.1 | TS-49-11 | 3.1 | `test_dump.py::test_missing_db_error` |
| 49-REQ-5.1 | (implicit) | 3.1 | `test_dump_props.py` |
| Property 3 | TS-49-P1 | 2.2 | `test_dump_props.py::test_fact_count_preservation` |
| Property 4 | TS-49-P2 | 2.2 | `test_dump_props.py::test_json_key_completeness` |
| Property 5 | TS-49-P3 | 2.1 | `test_dump_props.py::test_table_coverage` |
