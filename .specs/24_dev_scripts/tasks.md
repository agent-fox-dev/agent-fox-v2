# Implementation Plan: Developer Utility Scripts

<!-- AGENT INSTRUCTIONS
- This is a single task group — implement in one session
- No automated tests — verify manually
- Follow git-flow: feature branch from develop -> implement -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Single task group: create the `scripts/` directory and the `dump_knowledge.py`
script. No test-first approach since this is a developer utility with manual
verification only.

## Test Commands

- Linter: `uv run ruff check scripts/ && uv run ruff format --check scripts/`
- Manual: `python scripts/dump_knowledge.py`

## Tasks

- [ ] 1. Create dump_knowledge script
  - [ ] 1.1 Create `scripts/` directory and `dump_knowledge.py`
    - Import `KnowledgeDB` and `KnowledgeConfig` from `agent_fox`
    - Define `TABLES_TO_DUMP` list (all tables except `memory_embeddings`)
    - _Requirements: 24-REQ-1.1, 24-REQ-3.1_

  - [ ] 1.2 Implement DB existence check and open
    - Check if the DB file exists at `KnowledgeConfig().store_path`
    - If missing: print error to stderr, `sys.exit(1)`
    - If present: open via `KnowledgeDB` context manager
    - _Requirements: 24-REQ-2.1, 24-REQ-2.E1_

  - [ ] 1.3 Implement `dump_table()` function
    - Query `SELECT * FROM {table}` for each table
    - Format as Markdown section: `## table_name (N rows)`
    - Render rows as a Markdown table with column headers from cursor description
    - If zero rows, render "No rows." instead of table
    - _Requirements: 24-REQ-2.2, 24-REQ-2.3, 24-REQ-2.E2_

  - [ ] 1.4 Implement `main()` entry point
    - Open DB, iterate `TABLES_TO_DUMP`, collect Markdown sections
    - Add top-level heading with generation timestamp
    - Write to `.agent-fox/knowledge_dump.md`
    - Close DB (via context manager)
    - Print confirmation message to stdout
    - _Requirements: 24-REQ-2.4_

  - [ ] 1.V Verify task group 1
    - [ ] Script runs without errors: `python scripts/dump_knowledge.py`
    - [ ] Output file created at `.agent-fox/knowledge_dump.md`
    - [ ] All tables except `memory_embeddings` have sections
    - [ ] Empty tables show "No rows."
    - [ ] Missing DB produces error message and exit code 1
    - [ ] No linter warnings: `uv run ruff check scripts/`

## Traceability

| Requirement | Implemented By Task | Verified By |
|-------------|---------------------|-------------|
| 24-REQ-1.1 | 1.1 | 1.V (directory exists) |
| 24-REQ-2.1 | 1.2 | 1.V (script runs) |
| 24-REQ-2.2 | 1.3 | 1.V (all tables dumped) |
| 24-REQ-2.3 | 1.3 | 1.V (sections formatted) |
| 24-REQ-2.4 | 1.4 | 1.V (context manager closes) |
| 24-REQ-2.E1 | 1.2 | 1.V (missing DB test) |
| 24-REQ-2.E2 | 1.3 | 1.V (empty table test) |
| 24-REQ-3.1 | 1.1 | 1.V (code review) |
| 24-REQ-3.2 | all | 1.V (code review) |
