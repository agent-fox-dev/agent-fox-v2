# Implementation Plan: Cross-Spec Vector Retrieval

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds cross-spec vector retrieval to the session context
assembly pipeline. Task group 1 writes failing tests, group 2 adds the
config field and extraction function, group 3 wires the retrieval into the
session lifecycle and factory, and group 4 performs wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_cross_spec_retrieval.py tests/property/engine/test_cross_spec_retrieval_props.py tests/integration/engine/test_cross_spec_retrieval_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/engine/test_cross_spec_retrieval.py`
- Property tests: `uv run pytest -q tests/property/engine/test_cross_spec_retrieval_props.py`
- Integration tests: `uv run pytest -q tests/integration/engine/test_cross_spec_retrieval_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file
    - Create `tests/unit/engine/test_cross_spec_retrieval.py`
    - Add `__init__.py` if missing in `tests/unit/engine/`
    - Write test functions for TS-94-1 through TS-94-10
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-94-1 through TS-94-10_

  - [x] 1.2 Create edge case tests
    - Add tests for TS-94-E1 through TS-94-E7 in the unit test file
    - Tests MUST fail
    - _Test Spec: TS-94-E1 through TS-94-E7_

  - [x] 1.3 Create property tests
    - Create `tests/property/engine/test_cross_spec_retrieval_props.py`
    - Add `__init__.py` if missing in `tests/property/engine/`
    - Write property tests for TS-94-P1 through TS-94-P5
    - Use Hypothesis with `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-94-P1 through TS-94-P5_

  - [x] 1.4 Create integration smoke tests
    - Create `tests/integration/engine/test_cross_spec_retrieval_smoke.py`
    - Add `__init__.py` if missing in `tests/integration/engine/`
    - Write smoke tests for TS-94-SMOKE-1 and TS-94-SMOKE-2
    - _Test Spec: TS-94-SMOKE-1, TS-94-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Config field and subtask description extraction
  - [x] 2.1 Add `cross_spec_top_k` to `KnowledgeConfig`
    - Add `cross_spec_top_k: int = Field(default=15, description="...")` to
      `agent_fox/core/config.py` in the `KnowledgeConfig` class
    - _Requirements: 94-REQ-4.1, 94-REQ-4.2_

  - [x] 2.2 Implement `extract_subtask_descriptions` function
    - Add the function to `agent_fox/engine/session_lifecycle.py`
    - Parse `tasks.md` via existing `parse_tasks()`, locate matching group,
      iterate body lines to extract first non-metadata bullet per subtask
    - Import `_SUBTASK_PATTERN` from `agent_fox/spec/parser`
    - _Requirements: 94-REQ-1.1, 94-REQ-1.2_

  - [x] 2.3 Handle extraction edge cases
    - Return empty list when `tasks.md` is missing (94-REQ-1.E1)
    - Return empty list when task group not found (94-REQ-1.E2)
    - Return empty list when all bullets are metadata (94-REQ-1.E2)
    - _Requirements: 94-REQ-1.E1, 94-REQ-1.E2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_cross_spec_retrieval.py -k "extract or config or TS_94_1 or TS_94_2 or TS_94_7 or TS_94_E1 or TS_94_E2 or TS_94_E3"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 94-REQ-1.1, 94-REQ-1.2, 94-REQ-1.E1, 94-REQ-1.E2, 94-REQ-4.1, 94-REQ-4.2 acceptance criteria met

- [x] 3. Cross-spec retrieval method and factory wiring
  - [x] 3.1 Add `embedder` parameter to `NodeSessionRunner.__init__`
    - Add optional `embedder: EmbeddingGenerator | None = None` parameter
    - Store as `self._embedder`
    - _Requirements: 94-REQ-6.1, 94-REQ-6.2_

  - [x] 3.2 Implement `_retrieve_cross_spec_facts` method
    - Add the method to `NodeSessionRunner`
    - Check guards: `self._embedder is None` or `cross_spec_top_k == 0` → return input
    - Call `extract_subtask_descriptions`, embed, search, convert, merge, deduplicate
    - Wrap entire body in try/except for graceful degradation
    - _Requirements: 94-REQ-2.1, 94-REQ-2.2, 94-REQ-3.1, 94-REQ-3.2, 94-REQ-5.1_

  - [x] 3.3 Wire into `_build_prompts`
    - Call `_retrieve_cross_spec_facts(spec_dir, relevant)` after
      `_load_relevant_facts()` and before `_enhance_with_causal()`
    - Use the merged result for causal enhancement; also enables cross-spec
      retrieval when no spec-specific facts exist (addresses Skeptic finding)
    - _Requirements: 94-REQ-3.2_

  - [x] 3.4 Update session runner factory in `run.py`
    - Create `EmbeddingGenerator(config.knowledge)` in the factory setup
    - Wrap in try/except, set to `None` on failure
    - Pass `embedder=embedder` to `NodeSessionRunner`
    - Moved `open_knowledge_store`, `DuckDBSink`, `run_background_ingestion`
      to module-level imports so tests can patch them at `agent_fox.engine.run.X`
    - _Requirements: 94-REQ-6.1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_cross_spec_retrieval.py tests/integration/engine/test_cross_spec_retrieval_smoke.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 94-REQ-2.*, 94-REQ-3.*, 94-REQ-5.1, 94-REQ-6.* acceptance criteria met

- [x] 4. Wiring verification

  - [x] 4.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_
    - **Path 1 verified** (`session_lifecycle.py`):
      - `_build_prompts` (line 269) → `_retrieve_cross_spec_facts` ✓
      - `_retrieve_cross_spec_facts` (line 386) → `extract_subtask_descriptions` ✓
      - `_retrieve_cross_spec_facts` (line 396) → `self._embedder.embed_text` ✓
      - `_retrieve_cross_spec_facts` (line 408) → `VectorSearch(conn, config).search` ✓
      - `_retrieve_cross_spec_facts` (line 415) → `merge_cross_spec_facts` ✓
      - `_build_prompts` (line 272) → `_enhance_with_causal(merged)` ✓
    - **Path 2 verified** (graceful degradation): early returns at lines 373,
      380, 392, 404, 412 all return `relevant_facts` unchanged ✓
    - **Factory verified** (`run.py` lines 144-182): `EmbeddingGenerator`
      created once, passed as `embedder=embedder` to every `NodeSessionRunner` ✓

  - [x] 4.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_
    - `extract_subtask_descriptions()` → stored in `descriptions` (line 386),
      used to build query string (line 394) ✓
    - `embed_text()` → stored in `embedding` (line 396), passed to
      `VectorSearch.search()` (line 408) ✓
    - `VectorSearch.search()` → stored in `results` (line 408), passed to
      `merge_cross_spec_facts()` (line 415) ✓
    - `merge_cross_spec_facts()` → stored in `merged` (line 415), returned
      from `_retrieve_cross_spec_facts()` ✓
    - `_retrieve_cross_spec_facts()` → stored in `merged` (line 269),
      passed to `_enhance_with_causal()` (line 272) ✓

  - [x] 4.3 Run the integration smoke tests
    - All `TS-94-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-94-SMOKE-1, TS-94-SMOKE-2_
    - **Result: 24/24 tests pass** (17 unit + 5 property + 2 integration)
    - Smoke tests use real DuckDB and real `VectorSearch`; embedder is a
      mock that returns a deterministic fixed vector (acceptable per spec)

  - [x] 4.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale
    - **Audit results — all hits are justified:**
      - `session_lifecycle.py:99` — `return []` in `extract_subtask_descriptions`
        when `tasks.md` does not exist (94-REQ-1.E1 ✓)
      - `session_lifecycle.py:105` — `return []` after `read_text` failure;
        debug-logged, safe fallback (94-REQ-1.E1 ✓)
      - `session_lifecycle.py:112` — `return []` after `parse_tasks` failure;
        debug-logged, safe fallback (94-REQ-1.E2 ✓)
      - `session_lifecycle.py:115` — `return []` when task group not found
        (94-REQ-1.E2 ✓)
      - `session_lifecycle.py:1087` — `return []` in fact-loading helper when
        no facts exist; Optional-style empty-collection return, unrelated to spec 94
      - `session_lifecycle.py:452,461` — `return None` in
        `_read_session_artifacts` whose declared return type is `dict | None`;
        not a stub, fully typed Optional return, unrelated to spec 94
      - No `pass`, `# TODO`, `# stub`, or `NotImplementedError` found in any
        spec-94-touched file

  - [x] 4.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 94-REQ-1.1 | TS-94-1 | 2.2 | `test_cross_spec_retrieval.py::test_extract_subtask_descriptions` |
| 94-REQ-1.2 | TS-94-2 | 2.2 | `test_cross_spec_retrieval.py::test_skip_metadata_bullets` |
| 94-REQ-1.E1 | TS-94-E1 | 2.3 | `test_cross_spec_retrieval.py::test_missing_tasks_md` |
| 94-REQ-1.E2 | TS-94-E2, TS-94-E3 | 2.3 | `test_cross_spec_retrieval.py::test_group_not_found`, `test_metadata_only_bullets` |
| 94-REQ-2.1 | TS-94-3 | 3.2 | `test_cross_spec_retrieval.py::test_concatenate_and_embed` |
| 94-REQ-2.2 | TS-94-4 | 3.2 | `test_cross_spec_retrieval.py::test_vector_search_uses_configured_top_k` |
| 94-REQ-2.E1 | TS-94-E4 | 3.2 | `test_cross_spec_retrieval.py::test_embed_returns_none` |
| 94-REQ-2.E2 | TS-94-E6 | 3.2 | `test_cross_spec_retrieval.py::test_search_returns_empty` |
| 94-REQ-3.1 | TS-94-5 | 3.2 | `test_cross_spec_retrieval.py::test_merge_deduplicates` |
| 94-REQ-3.2 | TS-94-6 | 3.3 | `test_cross_spec_retrieval.py::test_merge_before_causal` |
| 94-REQ-3.E1 | TS-94-E5 | 3.2 | `test_cross_spec_retrieval.py::test_all_results_duplicates` |
| 94-REQ-4.1 | TS-94-7 | 2.1 | `test_cross_spec_retrieval.py::test_config_default` |
| 94-REQ-4.2 | TS-94-8 | 3.2 | `test_cross_spec_retrieval.py::test_top_k_zero_disables` |
| 94-REQ-5.1 | TS-94-E7 | 3.2 | `test_cross_spec_retrieval.py::test_exception_graceful_degradation` |
| 94-REQ-6.1 | TS-94-9 | 3.4 | `test_cross_spec_retrieval.py::test_factory_passes_embedder` |
| 94-REQ-6.2 | TS-94-10 | 3.1 | `test_cross_spec_retrieval.py::test_no_embedder_skips` |
| Property 1 | TS-94-P1 | 3.2 | `test_cross_spec_retrieval_props.py::test_deduplication_invariant` |
| Property 2 | TS-94-P2 | 3.2 | `test_cross_spec_retrieval_props.py::test_budget_independence` |
| Property 3 | TS-94-P3 | 3.2 | `test_cross_spec_retrieval_props.py::test_graceful_degradation_identity` |
| Property 4 | TS-94-P4 | 2.2 | `test_cross_spec_retrieval_props.py::test_metadata_exclusion` |
| Property 5 | TS-94-P5 | 3.2 | `test_cross_spec_retrieval_props.py::test_superseded_exclusion` |
| Path 1 | TS-94-SMOKE-1 | 3.3 | `test_cross_spec_retrieval_smoke.py::test_full_pipeline` |
| Path 2 | TS-94-SMOKE-2 | 3.2 | `test_cross_spec_retrieval_smoke.py::test_empty_knowledge_store` |

## Notes

- The `EmbeddingGenerator` model (all-MiniLM-L6-v2) loads in ~1-2 seconds on
  Apple Silicon. Sharing via factory ensures this cost is paid once per run.
- Existing `_SUBTASK_PATTERN` from `spec/parser.py` is reused for subtask
  line detection in `extract_subtask_descriptions`.
- The `SearchResult` → `Fact` conversion uses empty `keywords` and default
  `confidence`/`created_at` since `enhance_with_causal` only accesses
  `id`, `content`, and `spec_name`.
