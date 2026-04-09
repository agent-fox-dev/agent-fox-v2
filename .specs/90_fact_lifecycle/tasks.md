# Implementation Plan: Fact Lifecycle Management

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan implements three fact lifecycle mechanisms in four task groups:
(1) failing tests, (2) core lifecycle functions (dedup + decay), (3) LLM
contradiction detection, (4) pipeline and cleanup integration. The split
keeps LLM-dependent code separate from pure computation, allowing groups
2 and 3 to be developed in parallel after tests exist.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_lifecycle.py tests/unit/knowledge/test_contradiction.py tests/integration/test_harvest_lifecycle.py tests/property/test_lifecycle_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for lifecycle functions
    - Create `tests/unit/knowledge/test_lifecycle.py`
    - Implement test fixtures: in-memory DuckDB with schema, fact seeding
      helpers, embedding seeding helpers
    - Write tests TS-90-1 through TS-90-4 (dedup)
    - Write tests TS-90-9 through TS-90-11 (decay)
    - Write tests TS-90-12 through TS-90-15 (cleanup)
    - _Test Spec: TS-90-1, TS-90-2, TS-90-3, TS-90-4, TS-90-9, TS-90-10,
      TS-90-11, TS-90-12, TS-90-13, TS-90-14, TS-90-15_

  - [x] 1.2 Create unit test file for contradiction detection
    - Create `tests/unit/knowledge/test_contradiction.py`
    - Write tests TS-90-5 through TS-90-8 (contradiction)
    - _Test Spec: TS-90-5, TS-90-6, TS-90-7, TS-90-8_

  - [x] 1.3 Create edge case tests
    - Add edge case tests to both test files
    - Write tests TS-90-E1 through TS-90-E8
    - _Test Spec: TS-90-E1, TS-90-E2, TS-90-E3, TS-90-E4, TS-90-E5,
      TS-90-E6, TS-90-E7, TS-90-E8_

  - [x] 1.4 Create property tests
    - Create `tests/property/test_lifecycle_props.py`
    - Write property tests TS-90-P1, TS-90-P2, TS-90-P3, TS-90-P4,
      TS-90-P5, TS-90-P6, TS-90-P7, TS-90-P8, TS-90-P9
    - Use `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-90-P1, TS-90-P2, TS-90-P3, TS-90-P4, TS-90-P5,
      TS-90-P6, TS-90-P7, TS-90-P8, TS-90-P9_

  - [x] 1.5 Create integration test file
    - Create `tests/integration/test_harvest_lifecycle.py`
    - Write tests TS-90-16, TS-90-17
    - Write smoke tests TS-90-SMOKE-1, TS-90-SMOKE-2, TS-90-SMOKE-3
    - _Test Spec: TS-90-16, TS-90-17, TS-90-SMOKE-1, TS-90-SMOKE-2,
      TS-90-SMOKE-3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement dedup and decay lifecycle functions
  - [x] 2.1 Add config fields to KnowledgeConfig
    - Add `dedup_similarity_threshold`, `decay_half_life_days`,
      `decay_floor`, `cleanup_fact_threshold`, `cleanup_enabled` to
      `core/config.py: KnowledgeConfig`
    - _Requirements: 1.4, 3.3, 3.4, 4.3, 4.4_

  - [x] 2.2 Create `knowledge/lifecycle.py` with data types
    - Define `DedupResult`, `CleanupResult` dataclasses
    - _Requirements: 4.6_

  - [x] 2.3 Implement `dedup_new_facts()`
    - Query `memory_embeddings` for cosine similarity above threshold
    - Call `mark_superseded()` for each duplicate
    - Return `DedupResult` with superseded IDs and surviving facts
    - Handle edge cases: no embedding on new fact, no existing embeddings
    - _Requirements: 1.1, 1.2, 1.3, 1.5_
    - _Test Spec: TS-90-1, TS-90-2, TS-90-3, TS-90-4_

  - [x] 2.4 Implement `run_decay_cleanup()`
    - Load all active facts with `created_at`
    - Compute effective confidence using decay formula
    - Self-supersede facts below floor
    - Do NOT modify `confidence` column
    - Handle edge cases: NULL timestamp, future date
    - _Requirements: 3.1, 3.2, 3.5, 3.6_
    - _Test Spec: TS-90-9, TS-90-10, TS-90-11_

  - [x] 2.5 Implement `run_cleanup()`
    - Check `cleanup_enabled` config
    - Check active fact count against threshold
    - Run decay if above threshold
    - Emit `fact.cleanup` audit event
    - Return `CleanupResult`
    - _Requirements: 4.1, 4.2, 4.5, 4.6_
    - _Test Spec: TS-90-12, TS-90-13, TS-90-14, TS-90-15_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_lifecycle.py -k "dedup or decay or cleanup"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_lifecycle_props.py -k "P1 or P2 or P5 or P6 or P7 or P8"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Requirements 1.1-1.5, 1.E1, 1.E2, 3.1-3.6, 3.E1, 3.E2, 4.1-4.6, 4.E1, 4.E2 met

- [x] 3. Implement LLM contradiction detection
  - [x] 3.1 Add contradiction config fields to KnowledgeConfig
    - Add `contradiction_similarity_threshold`, `contradiction_model`
    - _Requirements: 2.7, 2.8_

  - [x] 3.2 Create `knowledge/contradiction.py`
    - Define `ContradictionVerdict` dataclass
    - Define `CONTRADICTION_PROMPT` template
    - Implement `classify_contradiction_batch()` — batched LLM call,
      response parsing, error handling
    - _Requirements: 2.2, 2.5_

  - [x] 3.3 Implement `detect_contradictions()` in lifecycle.py
    - Define `ContradictionResult` dataclass
    - Query embeddings for candidate pairs above threshold
    - Batch candidates (max 10 per LLM call)
    - Call `classify_contradiction_batch()`
    - Supersede confirmed contradictions
    - Handle edge cases: LLM failure, malformed JSON, no embedding
    - _Requirements: 2.1, 2.3, 2.4, 2.6_
    - _Test Spec: TS-90-5, TS-90-6, TS-90-7, TS-90-8_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_contradiction.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_lifecycle_props.py -k "P3 or P4"`
    - [x] Edge case tests pass: `uv run pytest -q tests/unit/knowledge/ -k "E3 or E4"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Requirements 2.1-2.8, 2.E1, 2.E2, 2.E3 met

- [ ] 4. Integrate into harvest pipeline and end-of-run barrier
  - [ ] 4.1 Wire dedup and contradiction into `extract_and_store_knowledge()`
    - After `sync_facts_to_duckdb()` and `_generate_embeddings()`: call
      `dedup_new_facts()`, then `detect_contradictions()` on survivors
    - Add dedup_count and contradiction_count to harvest.complete payload
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 4.2 Wire `run_cleanup()` into `engine/barrier.py`
    - Call `run_cleanup()` after knowledge harvesting, before compaction
    - Gate on `config.knowledge.cleanup_enabled`
    - _Requirements: 4.1, 4.2_

  - [ ] 4.3 Add `FACT_CLEANUP` to `AuditEventType` enum
    - Add the new event type in `knowledge/audit.py`
    - _Requirements: 4.5_

  - [ ] 4.V Verify task group 4
    - [ ] Integration tests pass: `uv run pytest -q tests/integration/test_harvest_lifecycle.py`
    - [ ] Smoke tests pass: `uv run pytest -q tests/integration/test_harvest_lifecycle.py -k "SMOKE"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/`
    - [ ] Requirements 5.1-5.4, 5.E1 met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - `dedup_new_facts()` → `DedupResult` used by harvest to filter facts
      for contradiction
    - `detect_contradictions()` → `ContradictionResult` used by harvest for
      audit event payload
    - `run_cleanup()` → `CleanupResult` used by barrier for logging
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-90-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-90-SMOKE-1, TS-90-SMOKE-2, TS-90-SMOKE-3_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All existing tests still pass: `uv run pytest -q`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

### Test Task Annotations

- Spec test references: `_Test Spec: TS-90-N_` (links subtask to test_spec.md entries)
- Requirement references: `_Requirements: N.N_` (links subtask to requirements.md)

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 90-REQ-1.1 | TS-90-1 | 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_detects_near_duplicate |
| 90-REQ-1.2 | TS-90-2 | 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_supersedes_older |
| 90-REQ-1.3 | TS-90-3 | 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_supersedes_multiple |
| 90-REQ-1.4 | TS-90-4 | 2.1, 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_threshold_configurable |
| 90-REQ-1.5 | TS-90-1 | 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_logs_supersession |
| 90-REQ-1.E1 | TS-90-E1 | 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_skip_no_embedding |
| 90-REQ-1.E2 | TS-90-E2 | 2.3 | tests/unit/knowledge/test_lifecycle.py::test_dedup_skip_no_existing_embeddings |
| 90-REQ-2.1 | TS-90-5 | 3.3 | tests/unit/knowledge/test_contradiction.py::test_contradiction_identifies_candidates |
| 90-REQ-2.2 | TS-90-6 | 3.2, 3.3 | tests/unit/knowledge/test_contradiction.py::test_contradiction_confirmed_supersedes |
| 90-REQ-2.3 | TS-90-6 | 3.3 | tests/unit/knowledge/test_contradiction.py::test_contradiction_confirmed_supersedes |
| 90-REQ-2.4 | TS-90-7 | 3.3 | tests/unit/knowledge/test_contradiction.py::test_non_contradiction_unchanged |
| 90-REQ-2.5 | TS-90-8 | 3.2, 3.3 | tests/unit/knowledge/test_contradiction.py::test_contradiction_batch_size |
| 90-REQ-2.6 | TS-90-6 | 3.3 | tests/unit/knowledge/test_contradiction.py::test_contradiction_logs_reason |
| 90-REQ-2.7 | TS-90-5 | 3.1 | tests/unit/knowledge/test_contradiction.py::test_contradiction_threshold_config |
| 90-REQ-2.8 | TS-90-6 | 3.1 | tests/unit/knowledge/test_contradiction.py::test_contradiction_model_config |
| 90-REQ-2.E1 | TS-90-E3 | 3.3 | tests/unit/knowledge/test_contradiction.py::test_llm_failure_non_fatal |
| 90-REQ-2.E2 | TS-90-E1 | 3.3 | tests/unit/knowledge/test_contradiction.py::test_skip_no_embedding |
| 90-REQ-2.E3 | TS-90-E4 | 3.2 | tests/unit/knowledge/test_contradiction.py::test_malformed_json_non_contradiction |
| 90-REQ-3.1 | TS-90-9 | 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_formula |
| 90-REQ-3.2 | TS-90-10 | 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_auto_supersedes |
| 90-REQ-3.3 | TS-90-9 | 2.1, 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_half_life_config |
| 90-REQ-3.4 | TS-90-10 | 2.1, 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_floor_config |
| 90-REQ-3.5 | TS-90-10 | 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_logs_count |
| 90-REQ-3.6 | TS-90-11 | 2.4 | tests/unit/knowledge/test_lifecycle.py::test_stored_confidence_unchanged |
| 90-REQ-3.E1 | TS-90-E5 | 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_null_timestamp |
| 90-REQ-3.E2 | TS-90-E6 | 2.4 | tests/unit/knowledge/test_lifecycle.py::test_decay_future_date |
| 90-REQ-4.1 | TS-90-12 | 4.2 | tests/integration/test_harvest_lifecycle.py::test_cleanup_at_end_of_run |
| 90-REQ-4.2 | TS-90-12, TS-90-13 | 2.5 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_threshold_gate |
| 90-REQ-4.3 | TS-90-13 | 2.1, 2.5 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_below_threshold |
| 90-REQ-4.4 | TS-90-E7 | 2.1, 2.5 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_disabled |
| 90-REQ-4.5 | TS-90-14 | 2.5, 4.3 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_audit_event |
| 90-REQ-4.6 | TS-90-15 | 2.5 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_returns_result |
| 90-REQ-4.E1 | TS-90-E7 | 2.5 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_disabled |
| 90-REQ-4.E2 | TS-90-E7 | 2.5 | tests/unit/knowledge/test_lifecycle.py::test_cleanup_db_unavailable |
| 90-REQ-5.1 | TS-90-16 | 4.1 | tests/integration/test_harvest_lifecycle.py::test_harvest_runs_dedup |
| 90-REQ-5.2 | TS-90-16 | 4.1 | tests/integration/test_harvest_lifecycle.py::test_harvest_runs_contradiction |
| 90-REQ-5.3 | TS-90-16 | 4.1 | tests/integration/test_harvest_lifecycle.py::test_harvest_dedup_before_contradiction |
| 90-REQ-5.4 | TS-90-17 | 4.1 | tests/integration/test_harvest_lifecycle.py::test_harvest_event_counts |
| 90-REQ-5.E1 | TS-90-E8 | 4.1 | tests/unit/knowledge/test_lifecycle.py::test_all_deduped_skips_contradiction |
| Property 1 | TS-90-P1 | 2.3 | tests/property/test_lifecycle_props.py::test_dedup_idempotency |
| Property 2 | TS-90-P2 | 2.3 | tests/property/test_lifecycle_props.py::test_dedup_threshold_monotonicity |
| Property 3 | TS-90-P3 | 3.3 | tests/property/test_lifecycle_props.py::test_contradiction_requires_llm |
| Property 4 | TS-90-P4 | 3.3 | tests/property/test_lifecycle_props.py::test_contradiction_graceful_degradation |
| Property 5 | TS-90-P5 | 2.4 | tests/property/test_lifecycle_props.py::test_decay_monotonicity |
| Property 6 | TS-90-P6 | 2.4 | tests/property/test_lifecycle_props.py::test_decay_floor_boundary |
| Property 7 | TS-90-P7 | 2.4 | tests/property/test_lifecycle_props.py::test_confidence_immutability |
| Property 8 | TS-90-P8 | 2.5 | tests/property/test_lifecycle_props.py::test_cleanup_threshold_gate |
| Property 9 | TS-90-P9 | 4.1 | tests/property/test_lifecycle_props.py::test_pipeline_order |

## Notes

- Property tests should use `@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])` when using pytest fixtures.
- In-memory DuckDB (`duckdb.connect(":memory:")`) is used for all tests to avoid filesystem side effects.
- Mock LLM responses use `unittest.mock.AsyncMock` for `cached_messages_create` and `unittest.mock.MagicMock` for `cached_messages_create_sync`.
- The `all-MiniLM-L6-v2` model is NOT loaded in tests; embeddings are pre-computed as fixed vectors.
- Task groups 2 and 3 can be developed in parallel after group 1 is complete.
