# Implementation Plan: Sleep-Time Compute

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in six groups: failing tests, core protocol and
orchestrator, the two initial sleep tasks (context rewriter + bundle builder),
retriever integration, barrier + nightshift wiring, and final verification.

The database migration is created in group 2 (needed by tests in group 1 via
in-memory DuckDB). The config changes are also in group 2 since tests
reference `SleepConfig`.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_sleep_compute.py tests/unit/knowledge/test_context_rewriter.py tests/unit/knowledge/test_bundle_builder.py tests/unit/knowledge/test_sleep_retrieval.py tests/integration/test_sleep_compute_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/knowledge/`
- Property tests: `uv run pytest -q tests/unit/knowledge/test_sleep_compute.py -k property`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file structure
    - Create `tests/unit/knowledge/test_sleep_compute.py` for protocol,
      orchestrator, config, and schema tests (TS-112-1 through TS-112-10,
      TS-112-30 through TS-112-34, TS-112-E8, TS-112-E9, TS-112-E10, TS-112-E11)
    - Create `tests/unit/knowledge/test_context_rewriter.py` for
      ContextRewriter tests (TS-112-11 through TS-112-15, TS-112-E1 through TS-112-E3)
    - Create `tests/unit/knowledge/test_bundle_builder.py` for BundleBuilder
      tests (TS-112-16 through TS-112-20, TS-112-E4, TS-112-E5)
    - Create `tests/unit/knowledge/test_sleep_retrieval.py` for retriever
      integration tests (TS-112-21 through TS-112-29, TS-112-E6, TS-112-E7)
    - Create `tests/integration/test_sleep_compute_smoke.py` for smoke tests
      (TS-112-SMOKE-1 through TS-112-SMOKE-3)
    - _Test Spec: TS-112-1 through TS-112-34, TS-112-E1 through TS-112-E11_

  - [x] 1.2 Translate acceptance-criterion tests from test_spec.md
    - One test function per TS-112-N entry
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-112-1 through TS-112-34_

  - [x] 1.3 Translate edge-case tests from test_spec.md
    - One test function per TS-112-EN entry
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-112-E1 through TS-112-E11_

  - [x] 1.4 Translate property tests from test_spec.md
    - One property test per TS-112-PN entry using Hypothesis
    - _Test Spec: TS-112-P1 through TS-112-P9_

  - [x] 1.5 Write integration smoke tests
    - One test per TS-112-SMOKE-N entry
    - _Test Spec: TS-112-SMOKE-1 through TS-112-SMOKE-3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Core protocol, orchestrator, config, and schema
  - [x] 2.1 Add SleepConfig to config system
    - Add `SleepConfig` pydantic model to `agent_fox/core/config.py`
    - Add `sleep` field to `KnowledgeConfig` with `default_factory=SleepConfig`
    - _Requirements: 112-REQ-7.1, 112-REQ-7.E1_

  - [x] 2.2 Add sleep_artifacts schema migration
    - Add migration v15 to `agent_fox/knowledge/migrations.py` creating the
      `sleep_artifacts` table with all columns
    - Follow existing migration pattern (next schema_version number)
    - _Requirements: 112-REQ-8.1, 112-REQ-8.2, 112-REQ-8.4, 112-REQ-8.E1_

  - [x] 2.3 Implement SleepTask protocol, data types, and SleepComputer
    - Created `agent_fox/knowledge/sleep_compute.py`
    - Defined `SleepTask` Protocol (with cost_estimate per errata), `SleepContext`,
      `SleepTaskResult`, `SleepComputeResult` dataclasses
    - Implemented `SleepComputer` with registration-order execution, budget
      decrementation, error isolation, per-task enable check, audit event
    - Added `SLEEP_COMPUTE_COMPLETE` to `AuditEventType` enum
    - Implemented `upsert_artifact()` and `compute_content_hash()` helpers
    - Created `agent_fox/knowledge/sleep_tasks/` package with ContextRewriter
      and BundleBuilder stubs (full implementation in groups 3 and 4)
    - Added `SleepComputeStream` stub to `agent_fox/nightshift/streams.py`
    - _Requirements: 112-REQ-1.1 through 112-REQ-1.5, 112-REQ-2.1 through
      112-REQ-2.5, 112-REQ-2.E1, 112-REQ-2.E2, 112-REQ-7.2, 112-REQ-7.3,
      112-REQ-7.4, 112-REQ-8.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_sleep_compute.py -k "..."`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [x] Requirements 112-REQ-1.*, 112-REQ-2.*, 112-REQ-7.*, 112-REQ-8.* met

- [ ] 3. Context re-representation task
  - [ ] 3.1 Create sleep_tasks package
    - Create `agent_fox/knowledge/sleep_tasks/__init__.py`
    - _Requirements: (structural)_

  - [ ] 3.2 Implement ContextRewriter
    - Create `agent_fox/knowledge/sleep_tasks/context_rewriter.py`
    - Implement directory-based clustering via `fact_entities` table joins
    - Implement content hash computation (SHA-256 of sorted fact IDs +
      confidences)
    - Implement LLM call with STANDARD model tier, structured narrative prompt
    - Implement 2000-char truncation at last complete sentence
    - Store artifacts with metadata (directory, fact_count, fact_ids)
    - Implement `stale_scopes()` by comparing stored vs. current content hashes
    - _Requirements: 112-REQ-3.1 through 112-REQ-3.6, 112-REQ-3.E1,
      112-REQ-3.E2, 112-REQ-3.E3_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_context_rewriter.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 112-REQ-3.* met

- [ ] 4. Retrieval bundle task
  - [ ] 4.1 Implement BundleBuilder
    - Create `agent_fox/knowledge/sleep_tasks/bundle_builder.py`
    - Query distinct spec names with active facts
    - Compute per-spec content hash
    - Call `_keyword_signal` and `_causal_signal` for stale specs
    - Serialize ScoredFact lists to JSON
    - Store artifacts with metadata (spec_name, fact_count, signal sizes)
    - Implement `stale_scopes()` by comparing stored vs. current hashes
    - _Requirements: 112-REQ-4.1 through 112-REQ-4.6, 112-REQ-4.E1,
      112-REQ-4.E2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_bundle_builder.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 112-REQ-4.* met

- [ ] 5. Checkpoint - Sleep tasks complete
  - Ensure all task-level tests pass.
  - Run `uv run pytest -q tests/unit/knowledge/test_sleep_compute.py tests/unit/knowledge/test_context_rewriter.py tests/unit/knowledge/test_bundle_builder.py`

- [ ] 6. Retriever and integration wiring
  - [ ] 6.1 Extend AdaptiveRetriever for sleep artifacts
    - Add `_load_context_preamble(conn, touched_files, token_budget)` function
      to `retrieval.py` — queries context blocks by matching touched file
      directories, enforces 30% budget cap
    - Add `_load_cached_bundle(conn, spec_name)` function — loads and
      deserializes bundle, returns `CachedBundle | None`
    - Modify `AdaptiveRetriever.retrieve()` to: (1) try loading cached bundle
      for keyword + causal signals, (2) load context preamble for touched
      files, (3) prepend preamble to assembled context
    - Add `sleep_hit` and `sleep_artifact_count` fields to `RetrievalResult`
    - Handle missing `sleep_artifacts` table gracefully
    - _Requirements: 112-REQ-5.1 through 112-REQ-5.5, 112-REQ-5.E1,
      112-REQ-5.E2_

  - [ ] 6.2 Wire sleep compute into barrier sequence
    - Add sleep compute step to `run_sync_barrier_sequence` in
      `agent_fox/engine/barrier.py`, after compaction and before
      `render_summary`
    - Check `sleep.enabled` config flag
    - Pass budget from `sleep.max_cost`
    - Instantiate ContextRewriter and BundleBuilder based on per-task
      enable flags
    - _Requirements: 112-REQ-6.1, 112-REQ-6.E1_

  - [ ] 6.3 Implement SleepComputeStream for nightshift
    - Add `SleepComputeStream` class to `agent_fox/nightshift/streams.py`
    - Implement `WorkStream` protocol: name, interval, enabled, run_once,
      shutdown
    - Open/close DB connection per cycle
    - Respect SharedBudget
    - Add `"sleep": "sleep-compute"` to `_CONFIG_TO_STREAM` mapping
    - _Requirements: 112-REQ-6.2, 112-REQ-6.3, 112-REQ-6.4, 112-REQ-6.E2_

  - [ ] 6.4 Update config documentation
    - Add `[knowledge.sleep]` section to `docs/config-reference.md`
    - _Requirements: 112-REQ-7.1_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_sleep_retrieval.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 112-REQ-5.*, 112-REQ-6.*, 112-REQ-7.* met

- [ ] 7. Wiring verification

  - [ ] 7.1 Trace every execution path from design.md end-to-end
    - Path 1: barrier → SleepComputer → tasks → sleep_artifacts
    - Path 2: nightshift daemon → SleepComputeStream → SleepComputer → tasks
    - Path 3: AdaptiveRetriever → _load_context_preamble → sleep_artifacts
    - Path 4: AdaptiveRetriever → _load_cached_bundle → sleep_artifacts
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub
    - Every path must be live in production code
    - _Requirements: all_

  - [ ] 7.2 Verify return values propagate correctly
    - SleepTaskResult → SleepComputeResult (task_results dict, total_llm_cost)
    - CachedBundle → AdaptiveRetriever (keyword_facts, causal_facts)
    - Context preamble string → RetrievalResult.context
    - sleep_hit/sleep_artifact_count → RetrievalResult
    - Grep for callers of each function; confirm none discards the return
    - _Requirements: all_

  - [ ] 7.3 Run the integration smoke tests
    - All `TS-112-SMOKE-*` tests pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/test_sleep_compute_smoke.py`
    - _Test Spec: TS-112-SMOKE-1 through TS-112-SMOKE-3_

  - [ ] 7.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be justified or replaced
    - Document any intentional stubs here with rationale

  - [ ] 7.5 Cross-spec entry point verification
    - Verify `SleepComputeStream` is included in the daemon's stream list
      (constructed in nightshift factory or daemon setup code)
    - Verify barrier sleep compute call is reachable from
      `run_sync_barrier_sequence`
    - _Requirements: all_

  - [ ] 7.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 112-REQ-1.1 | TS-112-1 | 2.3 | `test_sleep_compute.py::test_sleep_task_name` |
| 112-REQ-1.2 | TS-112-2 | 2.3 | `test_sleep_compute.py::test_sleep_task_run` |
| 112-REQ-1.3 | TS-112-3 | 2.3 | `test_sleep_compute.py::test_stale_scopes` |
| 112-REQ-1.4 | TS-112-4 | 2.3 | `test_sleep_compute.py::test_sleep_context_fields` |
| 112-REQ-1.5 | TS-112-5 | 2.3 | `test_sleep_compute.py::test_sleep_task_result_fields` |
| 112-REQ-2.1 | TS-112-6 | 2.3 | `test_sleep_compute.py::test_executes_tasks_in_order` |
| 112-REQ-2.2 | TS-112-7 | 2.3 | `test_sleep_compute.py::test_sleep_compute_result` |
| 112-REQ-2.3 | TS-112-8 | 2.3 | `test_sleep_compute.py::test_task_exception_isolation` |
| 112-REQ-2.4 | TS-112-9 | 2.3 | `test_sleep_compute.py::test_budget_exhaustion` |
| 112-REQ-2.5 | TS-112-10 | 2.3 | `test_sleep_compute.py::test_audit_event` |
| 112-REQ-2.E1 | TS-112-E8 | 2.3 | `test_sleep_compute.py::test_no_registered_tasks` |
| 112-REQ-2.E2 | TS-112-E9 | 2.3 | `test_sleep_compute.py::test_all_tasks_budget_exhausted` |
| 112-REQ-3.1 | TS-112-11 | 3.2 | `test_context_rewriter.py::test_clusters_by_directory` |
| 112-REQ-3.2 | TS-112-12 | 3.2 | `test_context_rewriter.py::test_content_hash_staleness` |
| 112-REQ-3.3 | TS-112-13 | 3.2 | `test_context_rewriter.py::test_llm_call_and_storage` |
| 112-REQ-3.4 | TS-112-14 | 3.2 | `test_context_rewriter.py::test_context_block_size_cap` |
| 112-REQ-3.5 | TS-112-12 | 3.2 | `test_context_rewriter.py::test_content_hash_staleness` |
| 112-REQ-3.6 | TS-112-15 | 3.2 | `test_context_rewriter.py::test_metadata_json` |
| 112-REQ-3.E1 | TS-112-E1 | 3.2 | `test_context_rewriter.py::test_fact_in_multiple_dirs` |
| 112-REQ-3.E2 | TS-112-E2 | 3.2 | `test_context_rewriter.py::test_no_qualifying_clusters` |
| 112-REQ-3.E3 | TS-112-E3 | 3.2 | `test_context_rewriter.py::test_llm_failure_skips_cluster` |
| 112-REQ-4.1 | TS-112-16 | 4.1 | `test_bundle_builder.py::test_identifies_active_specs` |
| 112-REQ-4.2 | TS-112-17 | 4.1 | `test_bundle_builder.py::test_content_hash_staleness` |
| 112-REQ-4.3 | TS-112-18 | 4.1 | `test_bundle_builder.py::test_stores_keyword_and_causal` |
| 112-REQ-4.4 | TS-112-17 | 4.1 | `test_bundle_builder.py::test_content_hash_staleness` |
| 112-REQ-4.5 | TS-112-19 | 4.1 | `test_bundle_builder.py::test_bundle_metadata` |
| 112-REQ-4.6 | TS-112-20 | 4.1 | `test_bundle_builder.py::test_zero_llm_cost` |
| 112-REQ-4.E1 | TS-112-E4 | 4.1 | `test_bundle_builder.py::test_spec_zero_active_facts` |
| 112-REQ-4.E2 | TS-112-E5 | 4.1 | `test_bundle_builder.py::test_signal_computation_failure` |
| 112-REQ-5.1 | TS-112-21 | 6.1 | `test_sleep_retrieval.py::test_prepends_context_preamble` |
| 112-REQ-5.2 | TS-112-22 | 6.1 | `test_sleep_retrieval.py::test_preamble_budget_cap` |
| 112-REQ-5.3 | TS-112-23 | 6.1 | `test_sleep_retrieval.py::test_uses_cached_bundle` |
| 112-REQ-5.4 | TS-112-24 | 6.1 | `test_sleep_retrieval.py::test_fallback_without_bundle` |
| 112-REQ-5.5 | TS-112-25 | 6.1 | `test_sleep_retrieval.py::test_sleep_fields` |
| 112-REQ-5.E1 | TS-112-E6 | 6.1 | `test_sleep_retrieval.py::test_missing_table` |
| 112-REQ-5.E2 | TS-112-E7 | 6.1 | `test_sleep_retrieval.py::test_all_blocks_stale` |
| 112-REQ-6.1 | TS-112-26 | 6.2 | `test_sleep_retrieval.py::test_barrier_runs_sleep_compute` |
| 112-REQ-6.2 | TS-112-27 | 6.3 | `test_sleep_retrieval.py::test_sleep_compute_stream` |
| 112-REQ-6.3 | TS-112-28 | 6.3 | `test_sleep_retrieval.py::test_stream_run_once_lifecycle` |
| 112-REQ-6.4 | TS-112-29 | 6.3 | `test_sleep_retrieval.py::test_stream_shared_budget` |
| 112-REQ-6.E1 | TS-112-26 | 6.2 | `test_sleep_retrieval.py::test_barrier_runs_sleep_compute` |
| 112-REQ-6.E2 | TS-112-27 | 6.3 | `test_sleep_retrieval.py::test_sleep_compute_stream` |
| 112-REQ-7.1 | TS-112-30 | 2.1 | `test_sleep_compute.py::test_config_defaults` |
| 112-REQ-7.2 | TS-112-31 | 2.1, 6.2 | `test_sleep_compute.py::test_sleep_disabled` |
| 112-REQ-7.3 | TS-112-9 | 2.3 | `test_sleep_compute.py::test_budget_exhaustion` |
| 112-REQ-7.4 | TS-112-32 | 2.3 | `test_sleep_compute.py::test_per_task_disable` |
| 112-REQ-7.E1 | TS-112-E10 | 2.1 | `test_sleep_compute.py::test_config_absent` |
| 112-REQ-8.1 | TS-112-33 | 2.2 | `test_sleep_compute.py::test_schema_columns` |
| 112-REQ-8.2 | TS-112-34 | 2.2 | `test_sleep_compute.py::test_artifact_supersession` |
| 112-REQ-8.3 | TS-112-34 | 2.3 | `test_sleep_compute.py::test_artifact_supersession` |
| 112-REQ-8.4 | TS-112-E11 | 2.2 | `test_sleep_compute.py::test_idempotent_migration` |
| 112-REQ-8.E1 | TS-112-E11 | 2.2 | `test_sleep_compute.py::test_idempotent_migration` |
| Property 1 | TS-112-P1 | 2.3 | `test_sleep_compute.py::test_property_staleness_determinism` |
| Property 2 | TS-112-P2 | 2.3 | `test_sleep_compute.py::test_property_artifact_uniqueness` |
| Property 3 | TS-112-P3 | 2.3 | `test_sleep_compute.py::test_property_budget_monotonicity` |
| Property 4 | TS-112-P4 | 6.1 | `test_sleep_retrieval.py::test_property_graceful_degradation` |
| Property 5 | TS-112-P5 | 6.1 | `test_sleep_retrieval.py::test_property_token_budget` |
| Property 6 | TS-112-P6 | 6.1 | `test_sleep_retrieval.py::test_property_preamble_cap` |
| Property 7 | TS-112-P7 | 2.3 | `test_sleep_compute.py::test_property_error_isolation` |
| Property 8 | TS-112-P8 | 3.2 | `test_context_rewriter.py::test_property_block_size_bound` |
| Property 9 | TS-112-P9 | 4.1 | `test_bundle_builder.py::test_property_bundle_fidelity` |
| Path 1 | TS-112-SMOKE-1 | 6.2 | `test_sleep_compute_smoke.py::test_barrier_end_to_end` |
| Path 2 | TS-112-SMOKE-2 | 6.3 | `test_sleep_compute_smoke.py::test_nightshift_stream` |
| Path 3+4 | TS-112-SMOKE-3 | 6.1 | `test_sleep_compute_smoke.py::test_retriever_consumes_artifacts` |

## Notes

- The `sleep_tasks` package uses a flat structure (no nested subpackages).
  Adding a new task means: create one file, implement `SleepTask`, register
  in the factory/config.
- Property tests use Hypothesis with `@settings(max_examples=50)` to keep
  CI fast.
- Integration smoke tests use in-memory DuckDB with mock LLM to avoid
  external API calls.
- The `_keyword_signal` and `_causal_signal` functions are module-level in
  `retrieval.py` — the bundle builder imports them directly. If they are
  refactored in the future, the import path will need updating.
