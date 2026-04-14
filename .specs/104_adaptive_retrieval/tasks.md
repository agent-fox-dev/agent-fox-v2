# Implementation Plan: Adaptive Retrieval with Multi-Signal Fusion

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation builds the unified retriever bottom-up: first tests, then
the core RRF engine and signal functions, then context assembly, then session
lifecycle wiring with legacy removal, and finally wiring verification. The
plan has 5 task groups sized for single coding sessions.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_adaptive_retrieval.py tests/unit/knowledge/test_legacy_removal.py tests/property/knowledge/test_retrieval_props.py tests/integration/test_adaptive_retrieval_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for AdaptiveRetriever
    - Create `tests/unit/knowledge/test_adaptive_retrieval.py`
    - Translate TS-104-1 through TS-104-16 into pytest test functions
    - Tests import from `agent_fox.knowledge.retrieval` (does not exist yet)
    - Use in-memory DuckDB fixtures with schema from migrations
    - _Test Spec: TS-104-1 through TS-104-16_

  - [x] 1.2 Create unit test file for legacy removal verification
    - Create `tests/unit/knowledge/test_legacy_removal.py`
    - Translate TS-104-17, TS-104-18, TS-104-E8 into pytest tests
    - These tests will fail initially (old functions still exist); they'll
      be inverted or adjusted in group 4
    - _Test Spec: TS-104-17, TS-104-18, TS-104-E8_

  - [x] 1.3 Create property tests
    - Create `tests/property/knowledge/test_retrieval_props.py`
    - Translate TS-104-P1 through TS-104-P7
    - Use Hypothesis strategies for signal lists, profiles, fact DAGs
    - _Test Spec: TS-104-P1 through TS-104-P7_

  - [x] 1.4 Create integration smoke tests
    - Create `tests/integration/test_adaptive_retrieval_smoke.py`
    - Translate TS-104-SMOKE-1 and TS-104-SMOKE-2
    - SMOKE-1 uses in-memory DuckDB with full schema, mock embedder,
      real retriever
    - _Test Spec: TS-104-SMOKE-1, TS-104-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Implement core retriever: signals, RRF fusion, intent profiles
  - [x] 2.1 Create `agent_fox/knowledge/retrieval.py` — data types
    - Define `ScoredFact`, `IntentProfile`, `RetrievalResult`,
      `RetrievalConfig` dataclasses
    - Add `RetrievalConfig` as a nested field on `KnowledgeConfig` in
      `agent_fox/core/config.py` with defaults
    - _Requirements: 5.3, 5.E1_

  - [x] 2.2 Implement `derive_intent_profile`
    - Map (archetype, node_status) → IntentProfile using the weight table
      from design.md
    - Default balanced profile for unknown archetypes
    - _Requirements: 3.1, 3.2, 3.3, 3.E1_

  - [x] 2.3 Implement `weighted_rrf_fusion`
    - Accept dict of signal name → list[ScoredFact], IntentProfile, k
    - Deduplicate by fact_id, aggregate scores using weighted RRF formula
    - Return sorted by descending score
    - _Requirements: 2.1, 2.2, 2.3, 2.E1_

  - [x] 2.4 Implement four signal functions
    - `_keyword_signal`: reuse keyword matching logic from `filtering.py`
      (confidence filter + keyword overlap + recency), return ScoredFact list
    - `_vector_signal`: call `VectorSearch.search`, convert SearchResult →
      ScoredFact
    - `_entity_signal`: call `find_related_facts` with touched files,
      convert to ScoredFact
    - `_causal_signal`: query same-spec facts, traverse `fact_causes` via
      `traverse_causal_chain`, convert to ScoredFact ordered by depth
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.E1, 1.E3_

  - [x] 2.V Verify task group 2
    - [x] Signal function tests pass: `uv run pytest -q tests/unit/knowledge/test_adaptive_retrieval.py -k "keyword or vector or entity or causal or rrf or intent"`
    - [x] Property tests pass: `uv run pytest -q tests/property/knowledge/test_retrieval_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 1.*, 2.*, 3.* acceptance criteria met

- [x] 3. Implement context assembly and AdaptiveRetriever
  - [x] 3.1 Implement `assemble_ranked_context`
    - Query causal edges between anchor facts from `fact_causes`
    - Topological sort (causes before effects, ties broken by score)
    - Assign salience tiers (high 20% / medium 40% / low 40%)
    - Render with provenance headers and apply token budget
    - _Requirements: 4.1, 4.2, 4.3, 4.E1_

  - [x] 3.2 Implement `AdaptiveRetriever` class
    - Constructor takes DuckDB connection, RetrievalConfig, optional embedder
    - `retrieve()` method: derive intent → run 4 signals → fuse via RRF →
      assemble context → return RetrievalResult
    - Wrap each signal in try/except for graceful degradation
    - _Requirements: 1.1, 1.E1, 1.E2, 1.E3_

  - [x] 3.V Verify task group 3
    - [x] Context assembly tests pass: `uv run pytest -q tests/unit/knowledge/test_adaptive_retrieval.py -k "context or provenance or budget or causal_order"`
    - [ ] Integration smoke test 1 passes: `uv run pytest -q tests/integration/test_adaptive_retrieval_smoke.py::test_full_retrieval_pipeline`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 4.* acceptance criteria met

- [ ] 4. Wire into session lifecycle, remove legacy retrieval
  - [ ] 4.1 Modify `NodeSessionRunner._build_prompts`
    - Replace `_load_relevant_facts` / `enhance_with_causal` /
      `_retrieve_cross_spec_facts` calls with single
      `AdaptiveRetriever.retrieve()` call
    - Pass `RetrievalResult.context` to `assemble_context` in place of
      `memory_facts`
    - Derive `node_status` from attempt number (attempt > 1 → "retry")
    - Extract touched files from task metadata
    - _Requirements: 5.1, 5.2_

  - [ ] 4.2 Remove legacy functions
    - Delete `select_relevant_facts` and `_compute_relevance_score` from
      `agent_fox/knowledge/filtering.py`
    - Delete `enhance_with_causal` and `load_relevant_facts` from
      `agent_fox/engine/session_lifecycle.py`
    - Delete `_retrieve_cross_spec_facts` from `NodeSessionRunner`
    - Delete `precompute_fact_rankings`, `RankedFactCache`, `get_cached_facts`
      from `agent_fox/engine/fact_cache.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 4.3 Remove fact cache precomputation from infrastructure
    - In `engine/run.py: _setup_infrastructure`, remove the
      `precompute_fact_rankings` call and `fact_cache` variable
    - Remove `fact_cache` parameter from `Orchestrator.__init__` and
      `NodeSessionRunner.__init__` if no longer needed
    - _Requirements: 6.4_

  - [ ] 4.4 Update all remaining imports
    - Search for imports of removed functions across the codebase
    - Update or remove imports in test files and production code
    - Remove old test files that tested removed functions exclusively
    - _Requirements: 6.E1_

  - [ ] 4.5 Flip legacy removal tests
    - In `tests/unit/knowledge/test_legacy_removal.py`, update assertions
      to verify functions are NOT importable
    - _Test Spec: TS-104-17, TS-104-18, TS-104-E8_

  - [ ] 4.6 Remove memory.jsonl infrastructure
    - Delete `export_facts_to_jsonl`, `load_facts_from_jsonl`,
      `append_facts`, `_write_jsonl` from `agent_fox/knowledge/store.py`
    - Remove JSONL fallback from `read_all_facts` in `store.py` — DuckDB
      is the only source; return empty list if unavailable
    - Remove `MEMORY_PATH` from `agent_fox/core/paths.py` and
      `DEFAULT_MEMORY_PATH` from `store.py`
    - Remove JSONL export calls from `knowledge/compaction.py` (line 85),
      `engine/run.py` (`_barrier_sync`, `_cleanup_infrastructure`),
      `engine/barrier.py` (line 277)
    - Remove `memory_path` parameter threading from `engine/reset.py`
      and `cli/reset.py`
    - Remove `memory.jsonl` seed file creation from
      `workspace/init_project.py` (line 292)
    - Remove `!.agent-fox/memory.jsonl` exception from `.gitignore`
    - Update `AGENTS.md` and `_templates/agents_md.md` to remove
      `memory.jsonl` from git-tracked state files list
    - See `docs/errata/104_memory_jsonl_removal.md` for full module list
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 4.7 Update memory.jsonl tests
    - Update `tests/unit/knowledge/test_store.py` — remove JSONL
      round-trip tests for deleted functions
    - Update `tests/unit/knowledge/test_read_all_facts.py` — remove JSONL
      fallback tests, add test for empty return when DuckDB unavailable
    - Update `tests/unit/knowledge/test_compaction.py` — remove JSONL
      export assertions
    - Update `tests/integration/test_init.py` — remove `memory.jsonl`
      seed file checks and `.gitignore` exception checks
    - Update `tests/unit/engine/test_hard_reset.py` — remove
      `memory_path` parameter from test calls
    - Update `tests/unit/knowledge/test_consolidation_store.py` — remove
      `export_facts_to_jsonl` tests
    - Update `tests/property/knowledge/test_consolidation_props.py` and
      `test_dual_write_props.py` — remove JSONL roundtrip properties
    - Add removal-verification tests to `test_legacy_removal.py`
    - _Test Spec: TS-104-19, TS-104-20, TS-104-21_

  - [ ] 4.V Verify task group 4
    - [ ] Legacy removal tests pass: `uv run pytest -q tests/unit/knowledge/test_legacy_removal.py`
    - [ ] Integration smoke test 2 passes: `uv run pytest -q tests/integration/test_adaptive_retrieval_smoke.py::test_legacy_chain_removed`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] `grep -r "select_relevant_facts\|RankedFactCache\|precompute_fact_rankings" agent_fox/` returns zero matches
    - [ ] `grep -r "export_facts_to_jsonl\|load_facts_from_jsonl\|MEMORY_PATH" agent_fox/` returns zero matches
    - [ ] `memory.jsonl` is not referenced in `.gitignore`
    - [ ] Requirements 5.*, 6.*, 7.* acceptance criteria met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1: `_build_prompts` → `AdaptiveRetriever.retrieve` → 4 signals →
      `weighted_rrf_fusion` → `assemble_ranked_context` → `assemble_context`.
      Read calling code at each step, confirm no function is a stub.
    - Path 2: Verify `select_relevant_facts`, `enhance_with_causal`,
      `_retrieve_cross_spec_facts`, `RankedFactCache`,
      `precompute_fact_rankings` are all deleted.
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - `AdaptiveRetriever.retrieve()` returns `RetrievalResult`
    - `RetrievalResult.context` is passed to `assemble_context`
    - `weighted_rrf_fusion` returns scored facts consumed by
      `assemble_ranked_context`
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-104-SMOKE-*` tests pass using real components
    - _Test Spec: TS-104-SMOKE-1, TS-104-SMOKE-2_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be justified or replaced
    - _Requirements: all_

  - [ ] 5.5 Cross-spec entry point verification
    - `AdaptiveRetriever` is instantiated in `_build_prompts` (this spec) and
      calls `find_related_facts` from spec 95, `VectorSearch.search` from
      spec 94, and `traverse_causal_chain` from existing causal module
    - Verify all upstream functions exist in production code
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
| 104-REQ-1.1 | TS-104-SMOKE-1 | 3.2 | `tests/integration/test_adaptive_retrieval_smoke.py::test_full_retrieval_pipeline` |
| 104-REQ-1.2 | TS-104-1 | 2.4 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_keyword_signal` |
| 104-REQ-1.3 | TS-104-2 | 2.4 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_vector_signal` |
| 104-REQ-1.4 | TS-104-3 | 2.4 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_entity_signal` |
| 104-REQ-1.5 | TS-104-4 | 2.4 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_causal_signal` |
| 104-REQ-1.E1 | TS-104-5 | 2.4, 3.2 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_empty_signal_excluded` |
| 104-REQ-1.E2 | TS-104-6 | 3.2 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_all_signals_empty` |
| 104-REQ-1.E3 | TS-104-7 | 3.2 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_vector_signal_failure` |
| 104-REQ-2.1 | TS-104-8 | 2.3 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_rrf_formula` |
| 104-REQ-2.2 | TS-104-8 | 2.3 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_rrf_formula` |
| 104-REQ-2.3 | TS-104-9 | 2.3 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_rrf_deduplication` |
| 104-REQ-2.E1 | TS-104-E4 | 2.3 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_single_signal_scoring` |
| 104-REQ-3.1 | TS-104-10 | 2.2 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_intent_coder_retry` |
| 104-REQ-3.2 | TS-104-8 | 2.2, 2.3 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_rrf_formula` |
| 104-REQ-3.3 | TS-104-10 | 2.2 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_intent_coder_retry` |
| 104-REQ-3.E1 | TS-104-11 | 2.2 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_unknown_archetype_fallback` |
| 104-REQ-4.1 | TS-104-12 | 3.1 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_causal_ordering` |
| 104-REQ-4.2 | TS-104-13 | 3.1 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_provenance_metadata` |
| 104-REQ-4.3 | TS-104-14 | 3.1 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_token_budget` |
| 104-REQ-4.E1 | TS-104-15 | 3.1 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_under_budget_full_render` |
| 104-REQ-5.1 | TS-104-SMOKE-1 | 4.1 | `tests/integration/test_adaptive_retrieval_smoke.py::test_full_retrieval_pipeline` |
| 104-REQ-5.2 | TS-104-SMOKE-1 | 4.1 | `tests/integration/test_adaptive_retrieval_smoke.py::test_full_retrieval_pipeline` |
| 104-REQ-5.3 | TS-104-16 | 2.1 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_config_defaults` |
| 104-REQ-5.E1 | TS-104-16 | 2.1 | `tests/unit/knowledge/test_adaptive_retrieval.py::test_config_defaults` |
| 104-REQ-6.1 | TS-104-17 | 4.2 | `tests/unit/knowledge/test_legacy_removal.py::test_select_relevant_facts_removed` |
| 104-REQ-6.2 | TS-104-SMOKE-2 | 4.2 | `tests/integration/test_adaptive_retrieval_smoke.py::test_legacy_chain_removed` |
| 104-REQ-6.3 | TS-104-SMOKE-2 | 4.2 | `tests/integration/test_adaptive_retrieval_smoke.py::test_legacy_chain_removed` |
| 104-REQ-6.4 | TS-104-18 | 4.2, 4.3 | `tests/unit/knowledge/test_legacy_removal.py::test_ranked_fact_cache_removed` |
| 104-REQ-6.E1 | TS-104-E8 | 4.4 | `tests/unit/knowledge/test_legacy_removal.py::test_no_legacy_imports` |
| 104-REQ-7.1 | TS-104-19, TS-104-21 | 4.6 | `tests/unit/knowledge/test_legacy_removal.py::test_jsonl_functions_removed` |
| 104-REQ-7.2 | TS-104-20 | 4.6 | `tests/unit/knowledge/test_legacy_removal.py::test_read_all_facts_no_jsonl_fallback` |
| 104-REQ-7.3 | TS-104-E8 | 4.6 | `tests/unit/knowledge/test_legacy_removal.py::test_no_legacy_imports` |
| 104-REQ-7.4 | TS-104-21 | 4.6 | `tests/unit/knowledge/test_legacy_removal.py::test_memory_path_removed` |
| 104-REQ-7.E1 | TS-104-20 | 4.6 | `tests/unit/knowledge/test_legacy_removal.py::test_read_all_facts_no_jsonl_fallback` |
| Property 1 | TS-104-P1 | 2.3 | `tests/property/knowledge/test_retrieval_props.py::test_rrf_monotonicity` |
| Property 2 | TS-104-P2 | 2.3 | `tests/property/knowledge/test_retrieval_props.py::test_rrf_dedup_invariant` |
| Property 3 | TS-104-P3 | 2.3 | `tests/property/knowledge/test_retrieval_props.py::test_weight_application` |
| Property 4 | TS-104-P4 | 2.3, 3.2 | `tests/property/knowledge/test_retrieval_props.py::test_graceful_degradation` |
| Property 5 | TS-104-P5 | 3.1 | `tests/property/knowledge/test_retrieval_props.py::test_causal_ordering` |
| Property 6 | TS-104-P6 | 3.1 | `tests/property/knowledge/test_retrieval_props.py::test_token_budget_compliance` |
| Property 7 | TS-104-P7 | 2.2 | `tests/property/knowledge/test_retrieval_props.py::test_default_fallback_profile` |

## Notes

- The four signal functions run sequentially in v1. If latency proves an
  issue, they can be parallelized with `asyncio.gather` in a future iteration
  since they are independent (no shared mutable state, all read-only DuckDB
  queries). The `AdaptiveRetriever.retrieve` method should be made `async`
  from the start to enable this without API changes.
- The `_keyword_signal` function reuses the scoring logic from the current
  `_compute_relevance_score` (keyword match count + recency bonus) but wraps
  it in ScoredFact instead of returning raw Facts. The logic itself is
  preserved, not reimplemented.
- The `assemble_ranked_context` function produces a self-contained markdown
  string that replaces the `memory_facts` parameter in `assemble_context`.
  The rest of `assemble_context` (spec docs, review findings, steering
  directives) is unchanged.
- Existing tests that exercise the old `select_relevant_facts` or
  `enhance_with_causal` paths will need updating or removal in group 4. Key
  files: `tests/unit/knowledge/test_filtering.py`,
  `tests/unit/engine/test_fact_cache.py`. These should be audited and either
  adapted to test the new retriever or removed if they only test deleted code.
- **Memory JSONL removal** (added post-spec): Task group 4 also removes
  `.agent-fox/memory.jsonl` entirely. DuckDB is the sole fact store. The
  JSONL file was a pre-DuckDB artifact used as a backup/fallback. With the
  adaptive retriever querying DuckDB directly, the JSONL layer is redundant.
  `docs/memory.md` continues to be generated for external tool consumption.
  See `docs/errata/104_memory_jsonl_removal.md` for full impact analysis.
