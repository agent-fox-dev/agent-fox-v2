# Implementation Plan: Knowledge Harvest & Causal Graph

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The knowledge harvest pipeline is structurally sound but functionally inert
because the calling code in `session_lifecycle.py` silently skips extraction
when `.session-summary.json` is absent. This plan fixes the trigger, adds a
fallback input path, tightens causal extraction conditions, and adds
observability via audit events.

Implementation order:
1. Write failing tests for all spec entries.
2. Fix the fact extraction trigger and add fallback input.
3. Add causal extraction threshold, context window, and audit events.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_knowledge_harvest.py tests/unit/knowledge/test_causal_harvest.py tests/integration/test_harvest_pipeline.py -v`
- Unit tests: `make test-unit`
- Property tests: `make test-property`
- All tests: `make test`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for harvest trigger
    - Create `tests/unit/engine/test_knowledge_harvest.py`
    - Tests for TS-52-1, TS-52-2, TS-52-3 (extraction trigger, fallback, error isolation)
    - Tests for TS-52-E1, TS-52-E2 (no commits fallback, non-completed skip)
    - _Test Spec: TS-52-1, TS-52-2, TS-52-3, TS-52-E1, TS-52-E2_

  - [x] 1.2 Create unit test file for fact storage and audit events
    - Create `tests/unit/knowledge/test_causal_harvest.py`
    - Tests for TS-52-5, TS-52-7 (idempotent insert, embedding failure isolation)
    - Tests for TS-52-8, TS-52-9, TS-52-E5 (audit events, empty harvest, null sink)
    - Tests for TS-52-10, TS-52-11, TS-52-12 (causal threshold, context window)
    - Tests for TS-52-14, TS-52-E3 (causal audit, invalid category)
    - _Test Spec: TS-52-5, TS-52-7, TS-52-8, TS-52-9, TS-52-10, TS-52-11, TS-52-12, TS-52-14, TS-52-E3, TS-52-E5_

  - [x] 1.3 Create integration test file
    - Create `tests/integration/test_harvest_pipeline.py`
    - Tests for TS-52-4, TS-52-6, TS-52-13, TS-52-E4 (provenance, embeddings, causal idempotency, missing fact link)
    - Use real in-memory DuckDB with schema from `migrations.py`
    - _Test Spec: TS-52-4, TS-52-6, TS-52-13, TS-52-E4_

  - [x] 1.4 Create property test file
    - Create `tests/property/engine/test_harvest_props.py`
    - Property tests for TS-52-P1 through TS-52-P9
    - Use Hypothesis strategies for fact generation, session states
    - _Test Spec: TS-52-P1, TS-52-P2, TS-52-P3, TS-52-P4, TS-52-P5, TS-52-P6, TS-52-P7, TS-52-P8, TS-52-P9_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Fix fact extraction trigger and fallback
  - [x] 2.1 Add `_build_fallback_input()` to `SessionLifecycle`
    - New method in `engine/session_lifecycle.py`
    - Constructs structured text from spec_name, task_group, node_id, commit diff
    - Omits `## Changes` section when no commits exist
    - _Requirements: 52-REQ-1.2, 52-REQ-1.E1_

  - [x] 2.2 Fix extraction trigger in `_post_session_integrate()`
    - Remove the `if transcript:` guard that silently skips extraction
    - Add fallback path: `if not transcript: transcript = self._build_fallback_input(...)`
    - Ensure extraction is always called for completed sessions
    - _Requirements: 52-REQ-1.1, 52-REQ-1.2, 52-REQ-1.E2_

  - [x] 2.3 Add `HARVEST_EMPTY` to `AuditEventType`
    - New enum member: `HARVEST_EMPTY = "harvest.empty"`
    - Update `default_severity_for()` to return WARNING for this type
    - _Requirements: 52-REQ-4.2_

  - [x] 2.4 Add audit events to `extract_and_store_knowledge()`
    - Emit `harvest.complete` with fact_count, categories, causal_link_count
    - Emit `harvest.empty` (warning) when input is non-empty but zero facts
    - Handle sink_dispatcher=None gracefully
    - _Requirements: 52-REQ-4.1, 52-REQ-4.2, 52-REQ-4.E1_

  - [x] 2.5 Add embedding generation after fact insertion
    - Call embedding generator after `sync_facts_to_duckdb()`
    - Wrap in try/except to isolate embedding failures
    - Log warning on failure, continue with causal extraction
    - _Requirements: 52-REQ-3.1, 52-REQ-3.2, 52-REQ-3.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_knowledge_harvest.py -v`
    - [x] TS-52-1, TS-52-2, TS-52-3, TS-52-4, TS-52-5, TS-52-E1, TS-52-E2, TS-52-E3 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 52-REQ-1.x, 52-REQ-2.x, 52-REQ-3.x, 52-REQ-4.x met

- [x] 3. Add causal extraction improvements
  - [x] 3.1 Add `causal_context_limit` to `OrchestratorConfig`
    - New field: `causal_context_limit: int = Field(default=200, ...)`
    - In `core/config.py`
    - _Requirements: 52-REQ-6.1_

  - [x] 3.2 Add minimum fact threshold to `_extract_causal_links()`
    - Query count of non-superseded facts before extraction
    - Skip with debug log when count < 5
    - _Requirements: 52-REQ-5.1, 52-REQ-5.2, 52-REQ-5.E1_

  - [x] 3.3 Add similarity-ranked context window
    - When fact count > `causal_context_limit`, use embedding similarity
    - Rank prior facts by cosine similarity to new facts
    - Include top N prior facts + all new facts
    - Handle facts without embeddings (append after ranked facts)
    - _Requirements: 52-REQ-6.1, 52-REQ-6.2, 52-REQ-6.E1_

  - [x] 3.4 Add `FACT_CAUSAL_LINKS` audit event
    - Emit after causal link extraction with new_link_count, total_link_count
    - Use existing `FACT_EXTRACTED` pattern as template
    - _Requirements: 52-REQ-7.2_

  - [x] 3.5 Pass `causal_context_limit` through the call chain
    - Thread from `OrchestratorConfig` → `SessionLifecycle` → `extract_and_store_knowledge()` → `_extract_causal_links()`
    - _Requirements: 52-REQ-6.1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_causal_harvest.py tests/integration/test_harvest_pipeline.py -v`
    - [x] TS-52-10, TS-52-11, TS-52-12, TS-52-13, TS-52-14, TS-52-E4, TS-52-E5, TS-52-E6 pass
    - [x] Property tests pass: `uv run pytest -q tests/property/engine/test_harvest_props.py -v`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 52-REQ-5.x, 52-REQ-6.x, 52-REQ-7.x met

- [x] 4. Checkpoint — Knowledge Harvest Complete
  - [x] All spec tests pass
  - [x] All property tests pass
  - [x] Full test suite green: `make check`
  - [x] Review coverage matrix — all requirements have passing tests

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 52-REQ-1.1 | TS-52-1 | 2.2 | `test_knowledge_harvest.py::test_extraction_from_summary` |
| 52-REQ-1.2 | TS-52-2 | 2.1, 2.2 | `test_knowledge_harvest.py::test_fallback_input` |
| 52-REQ-1.3 | TS-52-3 | 2.2 | `test_knowledge_harvest.py::test_extraction_error_isolation` |
| 52-REQ-1.E1 | TS-52-E1 | 2.1 | `test_knowledge_harvest.py::test_fallback_no_commits` |
| 52-REQ-1.E2 | TS-52-E2 | 2.2 | `test_knowledge_harvest.py::test_non_completed_skips` |
| 52-REQ-2.1 | TS-52-4 | 2.2 | `test_harvest_pipeline.py::test_fact_provenance` |
| 52-REQ-2.2 | TS-52-5 | 2.2 | `test_causal_harvest.py::test_fact_idempotent` |
| 52-REQ-2.E1 | TS-52-E3 | 2.2 | `test_causal_harvest.py::test_invalid_category_skipped` |
| 52-REQ-3.1 | TS-52-6 | 2.5 | `test_harvest_pipeline.py::test_embedding_generated` |
| 52-REQ-3.2 | TS-52-7 | 2.5 | `test_causal_harvest.py::test_embedding_failure_isolation` |
| 52-REQ-3.E1 | TS-52-E6 | 2.5 | `test_causal_harvest.py::test_embedding_model_unavailable` |
| 52-REQ-4.1 | TS-52-8 | 2.4 | `test_causal_harvest.py::test_harvest_complete_event` |
| 52-REQ-4.2 | TS-52-9 | 2.3, 2.4 | `test_causal_harvest.py::test_harvest_empty_event` |
| 52-REQ-4.E1 | TS-52-E5 | 2.4 | `test_causal_harvest.py::test_null_sink_no_error` |
| 52-REQ-5.1 | TS-52-10 | 3.2 | `test_causal_harvest.py::test_causal_trigger_threshold` |
| 52-REQ-5.2 | TS-52-11 | 3.2 | `test_causal_harvest.py::test_causal_skip_low_count` |
| 52-REQ-5.E1 | TS-52-E6 | 3.2 | `test_causal_harvest.py::test_causal_without_embeddings` |
| 52-REQ-6.1 | TS-52-12 | 3.3 | `test_causal_harvest.py::test_causal_context_bounded` |
| 52-REQ-6.2 | TS-52-12 | 3.3 | `test_causal_harvest.py::test_causal_all_facts_included` |
| 52-REQ-6.E1 | TS-52-E6 | 3.3 | `test_causal_harvest.py::test_unembedded_facts_appended` |
| 52-REQ-7.1 | TS-52-13 | 3.2 | `test_harvest_pipeline.py::test_causal_link_idempotent` |
| 52-REQ-7.2 | TS-52-14 | 3.4 | `test_causal_harvest.py::test_causal_link_audit_event` |
| 52-REQ-7.E1 | TS-52-E4 | 3.2 | `test_harvest_pipeline.py::test_missing_fact_link_skipped` |

## Notes

- All LLM calls should be mocked in unit tests. Integration tests may use
  a mock LLM or stub responses.
- DuckDB fixtures should use in-memory databases with schema from
  `knowledge/migrations.py` to ensure table structure is correct.
- Property tests should use `hypothesis.strategies` for fact generation,
  reusing patterns from `tests/property/knowledge/` if they exist.
- The `_build_fallback_input()` method needs access to `git diff` — mock
  the subprocess call in unit tests.
