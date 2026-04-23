# Implementation Plan: Knowledge System Pruning

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a subtractive change: delete files, drop tables, simplify code. The
implementation order is: (1) write tests that assert the desired final state,
(2) add migration v18, (3) delete files and simplify code, (4) clean up
imports and config, (5) verify wiring end-to-end.

## Test Commands

- Spec tests: `uv run pytest -q tests/test_knowledge_pruning.py`
- Unit tests: `uv run pytest -q tests/test_knowledge_pruning.py -k "not smoke and not property"`
- Property tests: `uv run pytest -q tests/test_knowledge_pruning.py -k "property"`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file structure
    - Create `tests/test_knowledge_pruning.py`
    - Import pytest, DuckDB fixtures from existing test infrastructure
    - _Test Spec: TS-116-1 through TS-116-20_

  - [ ] 1.2 Translate module-removal tests
    - Tests for TS-116-1, TS-116-2, TS-116-5, TS-116-7 (import should fail)
    - Tests for TS-116-8 (result_handler has no blocking_history reference)
    - Tests for TS-116-19 (no dead imports in production code)
    - Tests for TS-116-20 (reset.py table list updated)
    - These tests MUST FAIL now (modules still exist)
    - _Test Spec: TS-116-1, TS-116-2, TS-116-5, TS-116-7, TS-116-8, TS-116-19, TS-116-20_

  - [ ] 1.3 Translate provider and config tests
    - Tests for TS-116-3 (ingest is no-op)
    - Tests for TS-116-4, TS-116-6 (no gotcha/errata in retrieve)
    - Tests for TS-116-13, TS-116-14, TS-116-15 (review retrieval works)
    - Tests for TS-116-16, TS-116-17, TS-116-18 (config fields)
    - _Test Spec: TS-116-3, TS-116-4, TS-116-6, TS-116-13, TS-116-14, TS-116-15, TS-116-16, TS-116-17, TS-116-18_

  - [ ] 1.4 Translate migration and supersession tests
    - Tests for TS-116-9 (migration drops tables)
    - Tests for TS-116-10 (migration preserves retained tables)
    - Tests for TS-116-11 (migration on fresh DB)
    - Tests for TS-116-12 (supersession without fact_causes)
    - _Test Spec: TS-116-9, TS-116-10, TS-116-11, TS-116-12_

  - [ ] 1.5 Translate edge case and property tests
    - Tests for TS-116-E1 (missing review_findings table)
    - Tests for TS-116-E2 (config ignores removed fields)
    - Tests for TS-116-E3 (gotchas table exists but not queried)
    - Property tests for TS-116-P1, TS-116-P2, TS-116-P3
    - _Test Spec: TS-116-E1, TS-116-E2, TS-116-E3, TS-116-P1, TS-116-P2, TS-116-P3_

  - [ ] 1.6 Translate integration smoke tests
    - Tests for TS-116-SMOKE-1 (full retrieve cycle)
    - Tests for TS-116-SMOKE-2 (ingest then retrieve)
    - Tests for TS-116-SMOKE-3 (full migration with data)
    - _Test Spec: TS-116-SMOKE-1, TS-116-SMOKE-2, TS-116-SMOKE-3_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/test_knowledge_pruning.py`

- [ ] 2. Add migration v18 and remove causal links
  - [ ] 2.1 Add migration v18 to migrations.py
    - Add `_migrate_v18()` function with DROP TABLE IF EXISTS for all 10 tables
    - Register in migration list with description "drop unused knowledge tables"
    - _Requirements: 116-REQ-4.1, 116-REQ-4.2, 116-REQ-4.3, 116-REQ-4.E1_

  - [ ] 2.2 Remove `_insert_causal_links()` from review_store.py
    - Delete the `_insert_causal_links()` function
    - Remove all calls to `_insert_causal_links()` from `insert_findings()`,
      `insert_verdicts()`, and `insert_drift_findings()`
    - Supersession via `superseded_by` column continues to work unchanged
    - _Requirements: 116-REQ-5.1, 116-REQ-5.2_

  - [ ] 2.3 Update `db.py` bootstrap schema
    - Remove `fact_causes` table from the bootstrap `CREATE TABLE IF NOT
      EXISTS` block in `db.py` (if present)
    - _Requirements: 116-REQ-5.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: TS-116-9, TS-116-10, TS-116-11, TS-116-12
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/`

- [ ] 3. Delete files and simplify FoxKnowledgeProvider
  - [ ] 3.1 Delete removed modules
    - Delete `agent_fox/knowledge/gotcha_extraction.py`
    - Delete `agent_fox/knowledge/gotcha_store.py`
    - Delete `agent_fox/knowledge/errata_store.py`
    - Delete `agent_fox/knowledge/blocking_history.py`
    - _Requirements: 116-REQ-1.1, 116-REQ-1.2, 116-REQ-2.1, 116-REQ-3.1_

  - [ ] 3.2 Simplify FoxKnowledgeProvider.ingest()
    - Replace body with `return None` (no-op)
    - Remove imports of gotcha_extraction and gotcha_store
    - _Requirements: 116-REQ-1.3_

  - [ ] 3.3 Simplify FoxKnowledgeProvider.retrieve()
    - Remove `_query_errata()` and `_query_gotchas()` methods
    - Remove `_compose_results()` method
    - `retrieve()` calls only `_query_reviews()` and returns the result
      directly (capped at `max_items`)
    - _Requirements: 116-REQ-1.4, 116-REQ-2.2, 116-REQ-6.1, 116-REQ-6.2_

  - [ ] 3.4 Simplify KnowledgeProviderConfig
    - Remove `gotcha_ttl_days` and `model_tier` fields
    - Keep `max_items` with default 10
    - Ensure `model_config` has `extra = "ignore"` for backward compat
    - _Requirements: 116-REQ-7.1, 116-REQ-7.2, 116-REQ-7.3, 116-REQ-7.E1_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: TS-116-1 through TS-116-6, TS-116-13 through TS-116-18, TS-116-E1, TS-116-E2, TS-116-E3
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/`

- [ ] 4. Clean up imports and external references
  - [ ] 4.1 Remove blocking_history from result_handler.py
    - Remove the `from agent_fox.knowledge.blocking_history import` block
    - Remove the `record_blocking_decision()` call and surrounding try/except
    - _Requirements: 116-REQ-3.2, 116-REQ-3.E1_

  - [ ] 4.2 Update reset.py table list
    - Remove dropped table names from the reset table list
    - _Requirements: 116-REQ-8.2_

  - [ ] 4.3 Verify no stale imports remain
    - Search all production code for imports of removed modules
    - Fix any remaining references
    - _Requirements: 116-REQ-8.1, 116-REQ-8.3_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: TS-116-7, TS-116-8, TS-116-19, TS-116-20
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`

- [ ] 5. Delete existing tests for removed modules
  - [ ] 5.1 Remove test files for deleted modules
    - Delete or update tests that import gotcha_extraction, gotcha_store,
      errata_store, or blocking_history
    - Remove test fixtures that create gotchas or errata data
    - _Requirements: 116-REQ-8.1_

  - [ ] 5.V Verify task group 5
    - [ ] All tests pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [ ] Property tests pass: TS-116-P1, TS-116-P2, TS-116-P3
    - [ ] Smoke tests pass: TS-116-SMOKE-1, TS-116-SMOKE-2, TS-116-SMOKE-3

- [ ] 6. Wiring verification

  - [ ] 6.1 Trace every execution path from design.md end-to-end
    - Path 1 (pre-session retrieval): verify `run.py` creates
      `FoxKnowledgeProvider`, `session_lifecycle.py` calls `retrieve()`,
      `fox_provider.py` calls `review_store.query_active_findings()`
    - Path 2 (post-session ingestion): verify `session_lifecycle.py` calls
      `ingest()`, `fox_provider.py` returns immediately
    - Path 3 (review persistence): verify `session_lifecycle.py` calls
      `review_store.insert_findings()` without `_insert_causal_links()`
    - _Requirements: all_

  - [ ] 6.2 Verify return values propagate correctly
    - `retrieve()` returns `list[str]` consumed by `_build_prompts()`
    - `insert_findings()` returns `int` consumed by `_persist_review_findings()`
    - _Requirements: all_

  - [ ] 6.3 Run the integration smoke tests
    - All `TS-116-SMOKE-*` tests pass using real components
    - _Test Spec: TS-116-SMOKE-1 through TS-116-SMOKE-3_

  - [ ] 6.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be justified or replaced
    - Exception: `ingest()` returning `None` is intentional (protocol no-op)

  - [ ] 6.5 Cross-spec entry point verification
    - Verify `FoxKnowledgeProvider` is instantiated in `engine/run.py`
    - Verify `session_lifecycle.py` calls both `retrieve()` and `ingest()`
    - Verify `result_handler.py` no longer imports `blocking_history`
    - _Requirements: all_

  - [ ] 6.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 116-REQ-1.1 | TS-116-1 | 3.1 | test_gotcha_extraction_removed |
| 116-REQ-1.2 | TS-116-2 | 3.1 | test_gotcha_store_removed |
| 116-REQ-1.3 | TS-116-3 | 3.2 | test_ingest_is_noop |
| 116-REQ-1.4 | TS-116-4 | 3.3 | test_retrieve_no_gotchas |
| 116-REQ-1.E1 | TS-116-E3 | 3.3 | test_gotchas_table_exists_not_queried |
| 116-REQ-2.1 | TS-116-5 | 3.1 | test_errata_store_removed |
| 116-REQ-2.2 | TS-116-6 | 3.3 | test_retrieve_no_errata |
| 116-REQ-3.1 | TS-116-7 | 3.1 | test_blocking_history_removed |
| 116-REQ-3.2 | TS-116-8 | 4.1 | test_result_handler_no_blocking |
| 116-REQ-3.E1 | TS-116-8 | 4.1 | test_result_handler_no_blocking |
| 116-REQ-4.1 | TS-116-9 | 2.1 | test_migration_v18_drops_tables |
| 116-REQ-4.2 | TS-116-10 | 2.1 | test_migration_v18_preserves_retained |
| 116-REQ-4.3 | TS-116-9 | 2.1 | test_migration_v18_drops_tables |
| 116-REQ-4.E1 | TS-116-11 | 2.1 | test_migration_v18_fresh_db |
| 116-REQ-5.1 | TS-116-12 | 2.2 | test_supersession_without_fact_causes |
| 116-REQ-5.2 | TS-116-12 | 2.2 | test_supersession_without_fact_causes |
| 116-REQ-6.1 | TS-116-13 | 3.3 | test_retrieve_returns_reviews |
| 116-REQ-6.2 | TS-116-14 | 3.3 | test_retrieve_empty_no_findings |
| 116-REQ-6.3 | TS-116-15 | 3.3 | test_provider_satisfies_protocol |
| 116-REQ-6.E1 | TS-116-E1 | 3.3 | test_retrieve_missing_table |
| 116-REQ-7.1 | TS-116-16 | 3.4 | test_config_no_gotcha_ttl |
| 116-REQ-7.2 | TS-116-17 | 3.4 | test_config_no_model_tier |
| 116-REQ-7.3 | TS-116-18 | 3.4 | test_config_retains_max_items |
| 116-REQ-7.E1 | TS-116-E2 | 3.4 | test_config_ignores_removed_fields |
| 116-REQ-8.1 | TS-116-19 | 4.3 | test_no_dead_imports |
| 116-REQ-8.2 | TS-116-20 | 4.2 | test_reset_table_list |
| 116-REQ-8.3 | TS-116-15 | 4.3 | test_provider_satisfies_protocol |
| Property 1 | TS-116-P1 | 3.3 | test_property_review_carryforward |
| Property 2 | TS-116-P2 | 3.3 | test_property_no_gotcha_errata_leak |
| Property 5 | TS-116-P3 | 2.2 | test_property_supersession |
| Path 1 | TS-116-SMOKE-1 | 6.3 | test_smoke_full_retrieve |
| Path 2 | TS-116-SMOKE-2 | 6.3 | test_smoke_ingest_then_retrieve |
| Migration | TS-116-SMOKE-3 | 6.3 | test_smoke_migration_with_data |

## Notes

- This spec is purely subtractive — no new features are added.
- Existing tests for removed modules (gotcha_extraction, gotcha_store,
  errata_store, blocking_history) need to be deleted in task group 5.
- The `KnowledgeProvider` protocol is intentionally kept stable — `ingest()`
  remains in the protocol even though the current implementation is a no-op.
- The `retrieval_summary` column on `session_outcomes` is NOT dropped (column
  drops in DuckDB require table rebuild; the column is harmless).
