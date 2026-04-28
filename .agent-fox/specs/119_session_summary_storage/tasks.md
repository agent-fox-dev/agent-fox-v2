# Implementation Plan: Session Summary Storage

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan implements session summary storage and retrieval in five task groups:

1. **Failing tests** — translate all test_spec.md entries into executable pytest tests
2. **Schema and data model** — migration v24, `SummaryRecord`, `summary_store.py`
3. **Knowledge provider extension** — retrieval and ingestion in `fox_provider.py`
4. **Session lifecycle integration** — restructure `_run_and_harvest()` to read
   summary earlier, pass to audit event and knowledge ingestion
5. **Wiring verification** — end-to-end trace, smoke tests, stub audit

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_summary_store.py tests/unit/knowledge/test_fox_provider_summaries.py tests/integration/test_summary_lifecycle.py`
- Unit tests: `uv run pytest -q tests/unit/knowledge/`
- Property tests: `uv run pytest -q tests/unit/knowledge/test_summary_properties.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file for summary_store unit tests
    - Create `tests/unit/knowledge/test_summary_store.py`
    - Implement test fixtures: in-memory DuckDB with full schema applied
    - Write test functions for TS-119-1 through TS-119-4 (insert, schema, append-only, migration)
    - Write test functions for TS-119-5, TS-119-7 through TS-119-10 (same-spec query tests)
    - Write test functions for TS-119-11, TS-119-13 through TS-119-15 (cross-spec query tests)
    - _Test Spec: TS-119-1, TS-119-2, TS-119-3, TS-119-4, TS-119-5, TS-119-7, TS-119-8, TS-119-9, TS-119-10, TS-119-11, TS-119-13, TS-119-14, TS-119-15_

  - [x] 1.2 Create test file for edge case tests
    - Add to `tests/unit/knowledge/test_summary_store.py` or create separate file
    - Write test functions for TS-119-E1 through TS-119-E9
    - _Test Spec: TS-119-E1, TS-119-E2, TS-119-E3, TS-119-E4, TS-119-E5, TS-119-E6, TS-119-E7, TS-119-E8, TS-119-E9_

  - [x] 1.3 Create test file for fox_provider summary tests
    - Create `tests/unit/knowledge/test_fox_provider_summaries.py`
    - Write test functions for TS-119-6 (CONTEXT prefix formatting)
    - Write test functions for TS-119-12 (CROSS-SPEC prefix formatting)
    - _Test Spec: TS-119-6, TS-119-12_

  - [x] 1.4 Create test file for property tests
    - Create `tests/unit/knowledge/test_summary_properties.py`
    - Write property tests for TS-119-P1 through TS-119-P6
    - Use Hypothesis strategies for task group numbers, spec names, archetype strings, attempt counts
    - _Test Spec: TS-119-P1, TS-119-P2, TS-119-P3, TS-119-P4, TS-119-P5, TS-119-P6_

  - [x] 1.5 Create test file for integration tests
    - Create `tests/integration/knowledge/test_summary_lifecycle.py`
    - Write test functions for TS-119-16 through TS-119-20 (audit event, ingest, lifecycle)
    - Write test functions for TS-119-SMOKE-1 through TS-119-SMOKE-3
    - _Test Spec: TS-119-16, TS-119-17, TS-119-18, TS-119-19, TS-119-20, TS-119-SMOKE-1, TS-119-SMOKE-2, TS-119-SMOKE-3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Schema and data model
  - [ ] 2.1 Add migration v24 for session_summaries table
    - Add `Migration(version=24, ...)` to the `MIGRATIONS` list in `agent_fox/knowledge/migrations.py`
    - SQL: `CREATE TABLE IF NOT EXISTS session_summaries (id UUID PRIMARY KEY, node_id VARCHAR NOT NULL, run_id VARCHAR NOT NULL, spec_name VARCHAR NOT NULL, task_group VARCHAR NOT NULL, archetype VARCHAR NOT NULL, attempt INTEGER NOT NULL DEFAULT 1, summary TEXT NOT NULL, created_at TIMESTAMP NOT NULL)`
    - Update `base_schema_ddl()` to include the table for fresh databases
    - _Requirements: 119-REQ-1.2, 119-REQ-1.4_

  - [ ] 2.2 Create SummaryRecord dataclass
    - Create `agent_fox/knowledge/summary_store.py`
    - Define `SummaryRecord` dataclass with fields: id, node_id, run_id, spec_name, task_group, archetype, attempt, summary, created_at
    - _Requirements: 119-REQ-1.1_

  - [ ] 2.3 Implement insert_summary()
    - Add `insert_summary(conn, record)` function to `summary_store.py`
    - Simple INSERT with all fields from SummaryRecord
    - No supersession logic — append-only
    - _Requirements: 119-REQ-1.1, 119-REQ-1.3_

  - [ ] 2.4 Implement query_same_spec_summaries()
    - Add `query_same_spec_summaries(conn, spec_name, task_group, run_id, max_items=5)` to `summary_store.py`
    - SQL: filter by spec_name, run_id, archetype='coder', task_group < current
    - Use window function or subquery to get latest attempt per group
    - Sort by task_group ASC, cap at max_items
    - Handle missing table gracefully (catch CatalogException, return [])
    - _Requirements: 119-REQ-2.1, 119-REQ-2.3, 119-REQ-2.4, 119-REQ-2.5, 119-REQ-2.6, 119-REQ-2.E1, 119-REQ-2.E2, 119-REQ-2.E3_

  - [ ] 2.5 Implement query_cross_spec_summaries()
    - Add `query_cross_spec_summaries(conn, spec_name, run_id, max_items=3)` to `summary_store.py`
    - SQL: filter by run_id, archetype='coder', spec_name != current
    - Latest attempt per (spec_name, task_group), sort by created_at DESC, cap at max_items
    - Handle missing table gracefully
    - _Requirements: 119-REQ-3.1, 119-REQ-3.3, 119-REQ-3.4, 119-REQ-3.5, 119-REQ-3.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_summary_store.py`
    - [ ] Property tests pass: `uv run pytest -q tests/unit/knowledge/test_summary_properties.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/summary_store.py agent_fox/knowledge/migrations.py`
    - [ ] Requirements 119-REQ-1.1 through 1.4, 1.E1-E3, 2.1-2.6, 2.E1-E3, 3.1-3.5, 3.E1 acceptance criteria met

- [ ] 3. Knowledge provider extension
  - [ ] 3.1 Extend FoxKnowledgeProvider.retrieve() with summary queries
    - Add `_query_same_spec_summaries()` private method to `fox_provider.py`
    - Add `_query_cross_spec_summaries()` private method to `fox_provider.py`
    - Call both from `retrieve()`, format results as `[CONTEXT]` and `[CROSS-SPEC]` strings
    - Same-spec: `[CONTEXT] (group {G}, attempt {A}) {text}`
    - Cross-spec: `[CROSS-SPEC] ({spec}, group {G}) {text}`
    - Handle missing run_id: skip cross-spec when run_id is None
    - _Requirements: 119-REQ-2.1, 119-REQ-2.2, 119-REQ-3.1, 119-REQ-3.2, 119-REQ-3.E2_

  - [ ] 3.2 Extend FoxKnowledgeProvider.ingest() with summary storage
    - In `ingest()`, check for `context.get("summary")` when session_status is "completed"
    - Extract node_id components (spec_name, task_group) from the session_id parameter
    - Extract archetype and attempt from context (add to context dict in lifecycle)
    - Call `insert_summary()` with a new SummaryRecord
    - Wrap in try/except to handle DB failures gracefully (log warning)
    - _Requirements: 119-REQ-5.2, 119-REQ-1.E1, 119-REQ-1.E2, 119-REQ-5.E1_

  - [ ] 3.3 Wire run_id into FoxKnowledgeProvider
    - Ensure the provider has access to the current `run_id` for cross-spec queries
    - The run_id is already available via the engine — pass it through constructor or retrieve() parameter
    - _Requirements: 119-REQ-3.E2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_fox_provider_summaries.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/fox_provider.py`
    - [ ] Requirements 119-REQ-2.2, 3.2, 5.2 acceptance criteria met

- [ ] 4. Session lifecycle integration
  - [ ] 4.1 Restructure _run_and_harvest() to read summary before audit event
    - Move `_read_session_artifacts()` call from `_run_session_lifecycle()` into `_run_and_harvest()`, after `_harvest_and_integrate()` but before `emit_audit_event()`
    - Extract summary text: `summary_text = artifacts.get("summary", "") if artifacts else None`
    - Store on returned SessionRecord if a summary field is added, or return as separate value
    - _Requirements: 119-REQ-5.3_

  - [ ] 4.2 Add summary to session.complete audit event payload
    - When `summary_text` is not None and not empty, add `"summary": summary_text` to the payload dict
    - When summary exceeds 2000 chars, truncate to 2000 + "..." for the audit payload only
    - When no summary, omit the key from the payload
    - _Requirements: 119-REQ-4.1, 119-REQ-4.2, 119-REQ-4.E1_

  - [ ] 4.3 Pass summary to _ingest_knowledge() context
    - Add `summary_text` to the context dict in `_ingest_knowledge()` under key `"summary"`
    - Also add `"archetype"`, `"task_group"`, and `"attempt"` to context if not already present
    - _Requirements: 119-REQ-5.1_

  - [ ] 4.4 Clean up _run_session_lifecycle() after restructure
    - Remove the now-redundant `_read_session_artifacts()` call from `_run_session_lifecycle()`
    - Keep the log message using the summary from the returned record or local variable
    - Keep `_cleanup_session_artifacts()` call
    - _Requirements: 119-REQ-5.3_

  - [ ] 4.V Verify task group 4
    - [ ] Integration tests pass: `uv run pytest -q tests/integration/test_summary_lifecycle.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/engine/session_lifecycle.py`
    - [ ] Requirements 119-REQ-4.1, 4.2, 4.E1, 5.1, 5.3 acceptance criteria met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1 (summary storage): `_run_and_harvest()` → `_read_session_artifacts()` → `_ingest_knowledge()` → `FoxKnowledgeProvider.ingest()` → `insert_summary()` → DuckDB INSERT
    - Path 2 (summary injection): `_build_prompts()` → `retrieve()` → `_query_same_spec_summaries()` / `_query_cross_spec_summaries()` → `query_same_spec_summaries()` / `query_cross_spec_summaries()` → formatted strings
    - Path 3 (audit event): `_run_and_harvest()` → `_read_session_artifacts()` → `emit_audit_event()` with summary in payload
    - For each path, verify the entry point actually calls the next function in the chain
    - Confirm no function is a stub
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - `_read_session_artifacts()` returns `dict | None` → consumed by `_run_and_harvest()`
    - `query_same_spec_summaries()` returns `list[SummaryRecord]` → consumed by `_query_same_spec_summaries()` → formatted as strings
    - `query_cross_spec_summaries()` returns `list[SummaryRecord]` → consumed by `_query_cross_spec_summaries()` → formatted as strings
    - Confirm no caller discards a return value
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All TS-119-SMOKE-* tests pass using real components
    - `uv run pytest -q tests/integration/test_summary_lifecycle.py -k smoke`
    - _Test Spec: TS-119-SMOKE-1, TS-119-SMOKE-2, TS-119-SMOKE-3_

  - [ ] 5.4 Stub / dead-code audit
    - Search `agent_fox/knowledge/summary_store.py` for: `return []`, `return None`, `pass`, `# TODO`, `# stub`, `NotImplementedError`
    - Search `agent_fox/knowledge/fox_provider.py` for new code with stubs
    - Each hit must be justified or replaced
    - _Requirements: all_

  - [ ] 5.5 Cross-spec entry point verification
    - `insert_summary()` is called from `FoxKnowledgeProvider.ingest()` (not just tests)
    - `query_same_spec_summaries()` is called from `FoxKnowledgeProvider.retrieve()` (not just tests)
    - `query_cross_spec_summaries()` is called from `FoxKnowledgeProvider.retrieve()` (not just tests)
    - Confirm all three are called from production code
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 119-REQ-1.1 | TS-119-1 | 2.2, 2.3 | test_insert_summary_stores_correct_row |
| 119-REQ-1.2 | TS-119-2 | 2.1 | test_table_schema_matches_spec |
| 119-REQ-1.3 | TS-119-3 | 2.3 | test_append_only_retains_all_attempts |
| 119-REQ-1.4 | TS-119-4 | 2.1 | test_migration_v24_creates_table |
| 119-REQ-1.E1 | TS-119-E1 | 3.2, 4.1 | test_missing_summary_artifact |
| 119-REQ-1.E2 | TS-119-E2 | 3.2 | test_failed_session_skips_summary |
| 119-REQ-1.E3 | TS-119-E3 | 2.4, 2.5 | test_missing_table_handled_gracefully |
| 119-REQ-2.1 | TS-119-5 | 2.4 | test_same_spec_returns_prior_groups_only |
| 119-REQ-2.2 | TS-119-6 | 3.1 | test_summaries_formatted_with_context_prefix |
| 119-REQ-2.3 | TS-119-7 | 2.4 | test_latest_attempt_only_in_retrieval |
| 119-REQ-2.4 | TS-119-8 | 2.4 | test_sort_order_task_group_ascending |
| 119-REQ-2.5 | TS-119-9 | 2.4 | test_same_spec_cap_applied |
| 119-REQ-2.6 | TS-119-10 | 2.4 | test_only_coder_summaries_retrieved |
| 119-REQ-2.E1 | TS-119-E4 | 2.4 | test_task_group_1_returns_empty |
| 119-REQ-2.E2 | TS-119-E5 | 2.4 | test_no_coder_summaries_for_prior_groups |
| 119-REQ-2.E3 | TS-119-E3 | 2.4 | test_missing_table_handled_gracefully |
| 119-REQ-3.1 | TS-119-11 | 2.5, 3.1 | test_cross_spec_excludes_current |
| 119-REQ-3.2 | TS-119-12 | 3.1 | test_cross_spec_formatted_with_prefix |
| 119-REQ-3.3 | TS-119-13 | 2.5 | test_cross_spec_cap_applied |
| 119-REQ-3.4 | TS-119-14 | 2.5 | test_cross_spec_sorted_created_at_desc |
| 119-REQ-3.5 | TS-119-15 | 2.5 | test_cross_spec_latest_attempt_only |
| 119-REQ-3.E1 | TS-119-E6 | 2.5 | test_no_cross_spec_summaries_in_run |
| 119-REQ-3.E2 | TS-119-E7 | 3.1, 3.3 | test_no_run_id_skips_cross_spec |
| 119-REQ-4.1 | TS-119-16 | 4.2 | test_audit_event_includes_summary |
| 119-REQ-4.2 | TS-119-17 | 4.2 | test_audit_event_omits_summary_when_missing |
| 119-REQ-4.E1 | TS-119-E8 | 4.2 | test_audit_summary_truncated |
| 119-REQ-5.1 | TS-119-18 | 4.3 | test_summary_passed_to_ingest_context |
| 119-REQ-5.2 | TS-119-19 | 3.2 | test_ingest_stores_summary |
| 119-REQ-5.3 | TS-119-20 | 4.1, 4.4 | test_summary_available_to_both_paths |
| 119-REQ-5.E1 | TS-119-E9 | 3.2 | test_db_failure_does_not_crash |
| Property 2 | TS-119-P1 | 2.4 | test_prior_group_filtering_property |
| Property 3 | TS-119-P2 | 2.5 | test_cross_spec_exclusion_property |
| Property 4 | TS-119-P3 | 2.3 | test_append_only_property |
| Property 5 | TS-119-P5 | 2.4, 2.5 | test_graceful_degradation_property |
| Property 6 | TS-119-P6 | 4.2, 3.2 | test_audit_payload_consistency_property |
| Property 7 | TS-119-P4 | 2.4, 2.5 | test_sort_order_property |
| Path 1+2 | TS-119-SMOKE-1 | 2+3 | test_smoke_summary_storage_and_retrieval |
| Path 2 (cross) | TS-119-SMOKE-2 | 2+3 | test_smoke_cross_spec_injection |
| Path 3 | TS-119-SMOKE-3 | 4 | test_smoke_audit_event_includes_summary |

## Notes

- The `summary_store.py` module follows the same patterns as `review_store.py`:
  dataclass for records, standalone functions for CRUD, DuckDB connection
  passed as first argument.
- The `FoxKnowledgeProvider` constructor already receives a DuckDB connection.
  The `run_id` may need to be added as a constructor parameter or passed
  through `retrieve()`.
- Task group 4 requires restructuring `_run_and_harvest()` in
  `session_lifecycle.py`. This is the most delicate change — test thoroughly
  against existing session lifecycle tests.
- Property tests should use `@settings(max_examples=100)` to balance coverage
  and speed.
