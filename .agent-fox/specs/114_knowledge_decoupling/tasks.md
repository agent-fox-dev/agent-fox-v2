# Implementation Plan: Knowledge System Decoupling

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec performs a large-scale removal of ~35 low-value knowledge modules and
replaces them with a two-method `KnowledgeProvider` protocol. The plan is
ordered to minimize breakage: protocol and NoOp are created first, then engine
integration points are rewired, then dead modules/tests/config are deleted, and
finally wiring is verified.

Task groups are sized so that groups 2-3 do creation/wiring (safe to test
incrementally), groups 4-6 do deletion (bulk removal that must be atomic within
each group), and group 7 verifies everything end-to-end.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_provider.py tests/unit/knowledge/test_decoupling.py tests/unit/engine/test_engine_import_isolation.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/knowledge/test_knowledge_provider_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create protocol unit tests
    - Create `tests/unit/knowledge/test_provider.py`
    - Tests for `KnowledgeProvider` protocol definition (TS-114-1 through TS-114-4)
    - Tests for `NoOpKnowledgeProvider` (TS-114-5 through TS-114-7)
    - Edge case tests for partial protocol (TS-114-E1) and NoOp robustness (TS-114-E2)
    - _Test Spec: TS-114-1, TS-114-2, TS-114-3, TS-114-4, TS-114-5, TS-114-6, TS-114-7, TS-114-E1, TS-114-E2_

  - [ ] 1.2 Create engine integration tests
    - Create `tests/unit/knowledge/test_decoupling.py`
    - Tests for engine default provider (TS-114-8)
    - Tests for retrieve/ingest call flow (TS-114-9, TS-114-11, TS-114-12)
    - Tests for retrieve/ingest failure resilience (TS-114-E3, TS-114-E4)
    - _Test Spec: TS-114-8, TS-114-9, TS-114-11, TS-114-12, TS-114-E3, TS-114-E4_

  - [ ] 1.3 Create import isolation and deletion tests
    - Create `tests/unit/engine/test_engine_import_isolation.py`
    - Tests for engine import isolation (TS-114-10, TS-114-13, TS-114-15)
    - Tests for nightshift import isolation (TS-114-17 through TS-114-20)
    - Tests for CLI import isolation (TS-114-32 through TS-114-34)
    - Tests for file/directory deletion (TS-114-14, TS-114-21 through TS-114-25)
    - Tests for config changes (TS-114-26 through TS-114-30)
    - Tests for CLI removal (TS-114-31)
    - Tests for dead test cleanup (TS-114-38)
    - Edge case tests (TS-114-E5 through TS-114-E8)
    - _Test Spec: TS-114-10, TS-114-13, TS-114-14, TS-114-15, TS-114-17, TS-114-18, TS-114-19, TS-114-20, TS-114-21, TS-114-22, TS-114-23, TS-114-24, TS-114-25, TS-114-26, TS-114-27, TS-114-28, TS-114-29, TS-114-30, TS-114-31, TS-114-32, TS-114-33, TS-114-34, TS-114-38, TS-114-E5, TS-114-E6, TS-114-E7, TS-114-E8_

  - [ ] 1.4 Create property tests
    - Create `tests/property/knowledge/test_knowledge_provider_props.py`
    - Property tests for protocol conformance (TS-114-P1)
    - Property tests for NoOp behavior (TS-114-P2, TS-114-P3)
    - Property tests for config backward compatibility (TS-114-P7)
    - _Test Spec: TS-114-P1, TS-114-P2, TS-114-P3, TS-114-P7_

  - [ ] 1.5 Create smoke tests
    - Create `tests/integration/knowledge/test_decoupling_smoke.py`
    - Smoke tests for all 5 execution paths (TS-114-SMOKE-1 through TS-114-SMOKE-5)
    - _Test Spec: TS-114-SMOKE-1, TS-114-SMOKE-2, TS-114-SMOKE-3, TS-114-SMOKE-4, TS-114-SMOKE-5_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Define KnowledgeProvider protocol and NoOpKnowledgeProvider
  - [ ] 2.1 Create `agent_fox/knowledge/provider.py`
    - Define `KnowledgeProvider` as `typing.Protocol` with `@runtime_checkable`
    - `ingest(session_id: str, spec_name: str, context: dict) -> None`
    - `retrieve(spec_name: str, task_description: str) -> list[str]`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 2.2 Implement `NoOpKnowledgeProvider` in `provider.py`
    - `ingest()` returns None immediately
    - `retrieve()` returns empty list
    - _Requirements: 2.1, 2.2, 2.3, 2.E1_

  - [ ] 2.3 Export from `agent_fox/knowledge/__init__.py`
    - Add `KnowledgeProvider` and `NoOpKnowledgeProvider` to package exports
    - _Requirements: 1.1, 2.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_provider.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/provider.py`
    - [ ] Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.E1 acceptance criteria met

- [ ] 3. Rewire engine to use KnowledgeProvider protocol
  - [ ] 3.1 Modify `session_lifecycle.py` retrieval path
    - Replace `AdaptiveRetriever`/`RetrievalConfig`/`EmbeddingGenerator` imports with `KnowledgeProvider` import
    - Replace `_build_prompts` retrieval assembly with `self._knowledge_provider.retrieve()` call
    - Wrap `retrieve()` in try/except, log WARNING on failure, use empty context
    - Update `NodeSessionRunner.__init__` to accept `knowledge_provider: KnowledgeProvider` instead of `embedder`
    - Remove `_retrieval_summary`, `_query_prior_touched_files`, and related retrieval logic
    - _Requirements: 3.1, 3.2, 3.3, 3.E1_

  - [ ] 3.2 Replace knowledge harvest with provider ingest
    - Replace `extract_and_store_knowledge` call in `_extract_knowledge_and_findings` with `self._knowledge_provider.ingest()` call
    - Remove import of `knowledge_harvest.extract_and_store_knowledge`
    - Build context dict with `touched_files`, `commit_sha`, `session_status`
    - Wrap `ingest()` in try/except, log WARNING on failure, no retry
    - _Requirements: 4.1, 4.2, 4.E1_

  - [ ] 3.3 Modify `run.py` infrastructure setup
    - Remove `EmbeddingGenerator` creation and `run_background_ingestion` call
    - Remove imports: `EmbeddingGenerator`, `run_background_ingestion`, `ingest`
    - Create `NoOpKnowledgeProvider()` and add to infrastructure dict
    - Update `session_runner_factory` to pass `knowledge_provider` instead of `embedder`
    - _Requirements: 2.4, 3.2_

  - [ ] 3.4 Clean up barrier.py
    - Remove `run_consolidation` import (top-level try/except block)
    - Remove lifecycle cleanup block (`run_cleanup` call)
    - Remove consolidation pipeline block
    - Remove compaction block (`compact` call)
    - Remove sleep compute block (`SleepComputer`/`SleepContext`/`BundleBuilder`/`ContextRewriter`)
    - Remove `render_summary` import and call
    - Keep worktree verification, develop sync, hot-load, barrier callback, config reload
    - _Requirements: 5.1, 5.2_

  - [ ] 3.5 Clean up engine.py
    - Remove end-of-run consolidation block (deferred import of `run_consolidation`)
    - Remove final `render_summary` call
    - Remove `consolidated_specs` tracking set
    - _Requirements: 5.1_

  - [ ] 3.6 Clean up reset.py
    - Remove `from agent_fox.knowledge.compaction import compact` import
    - Remove or update any code that calls `compact()`
    - _Requirements: 5.1_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_decoupling.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/engine/`
    - [ ] Requirements 2.4, 3.1, 3.2, 3.3, 3.E1, 4.1, 4.2, 4.E1, 5.1, 5.2 acceptance criteria met

- [ ] 4. Checkpoint - Engine rewiring complete
  - Ensure all tests pass after engine rewiring.
  - At this point the engine uses `KnowledgeProvider` protocol exclusively.
  - Old knowledge modules are still on disk but no longer imported by engine.

- [ ] 5. Delete knowledge modules, directories, and knowledge_harvest.py
  - [ ] 5.1 Delete knowledge pipeline modules
    - Delete from `agent_fox/knowledge/`: `extraction.py`, `embeddings.py`, `search.py`, `retrieval.py`, `causal.py`, `lifecycle.py`, `contradiction.py`, `consolidation.py`, `compaction.py`, `entity_linker.py`, `entity_query.py`, `entity_store.py`, `entities.py`, `static_analysis.py`, `git_mining.py`, `doc_mining.py`, `sleep_compute.py`, `code_analysis.py`, `onboard.py`, `project_model.py`, `query_oracle.py`, `query_patterns.py`, `query_temporal.py`, `rendering.py`, `store.py`, `ingest.py`, `facts.py`
    - _Requirements: 7.1_

  - [ ] 5.2 Delete `agent_fox/knowledge/lang/` directory entirely
    - _Requirements: 7.2_

  - [ ] 5.3 Delete `agent_fox/knowledge/sleep_tasks/` directory entirely
    - _Requirements: 7.3_

  - [ ] 5.4 Delete `agent_fox/engine/knowledge_harvest.py`
    - _Requirements: 7.4, 4.3_

  - [ ] 5.5 Clean up `agent_fox/knowledge/__init__.py`
    - Remove exports for deleted modules
    - Keep exports for retained modules and new `KnowledgeProvider`/`NoOpKnowledgeProvider`
    - _Requirements: 7.5_

  - [ ] 5.6 Fix remaining import references
    - Scan entire `agent_fox/` package for imports from deleted modules
    - Fix nightshift files: `ignore_ingest.py`, `dedup.py`, `ignore_filter.py`, `streams.py`
    - Fix CLI files: `nightshift.py`, `status.py`
    - Fix any other files discovered by scan
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.5, 9.2, 9.3_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_engine_import_isolation.py -k "deletion or import_isolation or nightshift or cli"`
    - [ ] `python -c "import agent_fox"` succeeds with zero errors
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/`
    - [ ] Requirements 4.3, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 9.2, 9.3 acceptance criteria met

- [ ] 6. Configuration cleanup, CLI cleanup, and test cleanup
  - [ ] 6.1 Simplify KnowledgeConfig
    - Remove all fields listed in REQ 8.1 from `KnowledgeConfig`
    - Delete `RetrievalConfig` class
    - Delete `SleepConfig` class
    - Retain `store_path` field and `extra="ignore"` behavior
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 6.2 Remove `cli/onboard.py` command
    - Delete `agent_fox/cli/onboard.py` or remove the command registration
    - Update CLI group to not register the onboard command
    - _Requirements: 9.1_

  - [ ] 6.3 Update `cli/plan.py`
    - Verify `open_knowledge_store` import works without depending on removed modules
    - _Requirements: 9.4_

  - [ ] 6.4 Delete test files for removed functionality
    - Delete unit tests that exclusively test removed modules (extraction, embeddings, retrieval, consolidation, compaction, sleep compute, entity graph, contradiction, lifecycle, onboard, rendering, causal, etc.)
    - Delete integration tests for removed functionality (consolidation_smoke, entity_graph_smoke, multilang_smoke, onboard_smoke, etc.)
    - Delete property tests for removed functionality
    - Delete `tests/unit/engine/test_knowledge_harvest.py`
    - Update any shared test fixtures that reference deleted modules
    - _Requirements: 10.4, 7.E1_

  - [ ] 6.5 Create remaining spec tests
    - Add tests for protocol existence (TS-114-36), import isolation (TS-114-37)
    - Verify `make check` passes (TS-114-35)
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_engine_import_isolation.py -k "config or cli or dead_test"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] `make check` passes
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.4, 10.1, 10.2, 10.3, 10.4 acceptance criteria met

- [ ] 7. Supersede specs 112 and 113
  - [ ] 7.1 Add deprecation banners to spec 112
    - Add `⚠️ **SUPERSEDED** by spec 114_knowledge_decoupling` to top of each file in `112_sleep_time_compute/`
    - _Requirements: PRD Supersedes section_

  - [ ] 7.2 Add deprecation banners to spec 113
    - Add `⚠️ **SUPERSEDED** by spec 114_knowledge_decoupling` to top of each file in `113_knowledge_effectiveness/`
    - _Requirements: PRD Supersedes section_

  - [ ] 7.3 Move superseded specs to archive
    - `git mv .agent-fox/specs/112_sleep_time_compute .agent-fox/specs/archive/112_sleep_time_compute`
    - `git mv .agent-fox/specs/113_knowledge_effectiveness .agent-fox/specs/archive/113_knowledge_effectiveness`
    - _Requirements: PRD Supersedes section_

  - [ ] 7.V Verify task group 7
    - [ ] Deprecation banners present in all archived spec files
    - [ ] Specs 112 and 113 are in `.agent-fox/specs/archive/`
    - [ ] No lint or test regressions: `make check`

- [ ] 8. Wiring verification

  - [ ] 8.1 Trace every execution path from design.md end-to-end
    - For each path (1-5), verify the entry point actually calls the next function in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`, `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not satisfy this check
    - _Requirements: all_

  - [ ] 8.2 Verify return values propagate correctly
    - For `KnowledgeProvider.retrieve()`: confirm `_build_prompts` receives the return value and passes it to `assemble_context`
    - For `KnowledgeProvider.ingest()`: confirm caller does not discard the return (it's None, but the call must happen)
    - Grep for callers of each function; confirm none discards the return
    - _Requirements: all_

  - [ ] 8.3 Run the integration smoke tests
    - All `TS-114-SMOKE-*` tests pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/knowledge/test_decoupling_smoke.py`
    - _Test Spec: TS-114-SMOKE-1 through TS-114-SMOKE-5_

  - [ ] 8.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None` on non-Optional returns, `pass` in non-abstract methods, `# TODO`, `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it is intentional, or (b) replaced with a real implementation
    - `NoOpKnowledgeProvider.retrieve()` returning `[]` is intentional — document in audit
    - `NoOpKnowledgeProvider.ingest()` returning `None` is intentional — document in audit

  - [ ] 8.5 Cross-spec entry point verification
    - Verify that spec 115 (pluggable knowledge) can implement `KnowledgeProvider` by inspecting the protocol definition
    - Verify that `engine/run.py` instantiates `NoOpKnowledgeProvider` and passes it through the factory — this is the entry point for spec 115 to swap in a real implementation
    - Confirm no upstream callers depend on deleted modules
    - _Requirements: all_

  - [ ] 8.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `make check`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 114-REQ-1.1 | TS-114-1 | 2.1 | tests/unit/knowledge/test_provider.py::test_protocol_definition |
| 114-REQ-1.2 | TS-114-2 | 2.1 | tests/unit/knowledge/test_provider.py::test_runtime_checkable |
| 114-REQ-1.3 | TS-114-3 | 2.1 | tests/unit/knowledge/test_provider.py::test_retrieve_return_type |
| 114-REQ-1.4 | TS-114-4 | 2.1 | tests/unit/knowledge/test_provider.py::test_ingest_signature |
| 114-REQ-1.E1 | TS-114-E1 | 2.1 | tests/unit/knowledge/test_provider.py::test_partial_protocol |
| 114-REQ-2.1 | TS-114-5 | 2.2 | tests/unit/knowledge/test_provider.py::test_noop_satisfies_protocol |
| 114-REQ-2.2 | TS-114-6 | 2.2 | tests/unit/knowledge/test_provider.py::test_noop_ingest |
| 114-REQ-2.3 | TS-114-7 | 2.2 | tests/unit/knowledge/test_provider.py::test_noop_retrieve |
| 114-REQ-2.4 | TS-114-8 | 3.3 | tests/unit/knowledge/test_decoupling.py::test_default_provider |
| 114-REQ-2.E1 | TS-114-E2 | 2.2 | tests/unit/knowledge/test_provider.py::test_noop_any_args |
| 114-REQ-3.1 | TS-114-9 | 3.1 | tests/unit/knowledge/test_decoupling.py::test_retrieve_called |
| 114-REQ-3.2 | TS-114-10 | 3.1, 3.3 | tests/unit/engine/test_engine_import_isolation.py::test_no_retrieval_imports |
| 114-REQ-3.3 | TS-114-11 | 3.1 | tests/unit/knowledge/test_decoupling.py::test_empty_retrieve |
| 114-REQ-3.E1 | TS-114-E3 | 3.1 | tests/unit/knowledge/test_decoupling.py::test_retrieve_exception |
| 114-REQ-4.1 | TS-114-12 | 3.2 | tests/unit/knowledge/test_decoupling.py::test_ingest_called |
| 114-REQ-4.2 | TS-114-13 | 3.2 | tests/unit/engine/test_engine_import_isolation.py::test_no_extraction_imports |
| 114-REQ-4.3 | TS-114-14 | 5.4 | tests/unit/engine/test_engine_import_isolation.py::test_harvest_deleted |
| 114-REQ-4.E1 | TS-114-E4 | 3.2 | tests/unit/knowledge/test_decoupling.py::test_ingest_exception |
| 114-REQ-5.1 | TS-114-15 | 3.4 | tests/unit/engine/test_engine_import_isolation.py::test_barrier_no_removed |
| 114-REQ-5.2 | TS-114-16 | 3.4 | tests/unit/knowledge/test_decoupling.py::test_barrier_retained_steps |
| 114-REQ-5.E1 | TS-114-E5 | 3.4 | tests/unit/engine/test_engine_import_isolation.py::test_barrier_old_tables |
| 114-REQ-6.1 | TS-114-17 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_nightshift_no_embeddings |
| 114-REQ-6.2 | TS-114-18 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_nightshift_no_sleep |
| 114-REQ-6.3 | TS-114-19 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_nightshift_no_sleep_stream |
| 114-REQ-6.4 | TS-114-20 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_nightshift_ingest_dedup |
| 114-REQ-6.E1 | TS-114-E6 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_nightshift_old_artifacts |
| 114-REQ-7.1 | TS-114-21 | 5.1 | tests/unit/engine/test_engine_import_isolation.py::test_knowledge_files_deleted |
| 114-REQ-7.2 | TS-114-22 | 5.2 | tests/unit/engine/test_engine_import_isolation.py::test_lang_dir_deleted |
| 114-REQ-7.3 | TS-114-23 | 5.3 | tests/unit/engine/test_engine_import_isolation.py::test_sleep_tasks_dir_deleted |
| 114-REQ-7.4 | TS-114-24 | 5.4 | tests/unit/engine/test_engine_import_isolation.py::test_harvest_deleted |
| 114-REQ-7.5 | TS-114-25 | 5.5, 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_import_health |
| 114-REQ-7.E1 | TS-114-E7 | 6.4 | tests/unit/engine/test_engine_import_isolation.py::test_no_test_imports_deleted |
| 114-REQ-8.1 | TS-114-26 | 6.1 | tests/unit/engine/test_engine_import_isolation.py::test_config_fields_removed |
| 114-REQ-8.2 | TS-114-27 | 6.1 | tests/unit/engine/test_engine_import_isolation.py::test_retrieval_config_deleted |
| 114-REQ-8.3 | TS-114-28 | 6.1 | tests/unit/engine/test_engine_import_isolation.py::test_sleep_config_deleted |
| 114-REQ-8.4 | TS-114-29 | 6.1 | tests/unit/engine/test_engine_import_isolation.py::test_store_path_retained |
| 114-REQ-8.5 | TS-114-30 | 6.1 | tests/unit/engine/test_engine_import_isolation.py::test_old_config_ignored |
| 114-REQ-9.1 | TS-114-31 | 6.2 | tests/unit/engine/test_engine_import_isolation.py::test_onboard_removed |
| 114-REQ-9.2 | TS-114-32 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_cli_nightshift_no_embeddings |
| 114-REQ-9.3 | TS-114-33 | 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_cli_status_no_removed |
| 114-REQ-9.4 | TS-114-34 | 6.3 | tests/unit/engine/test_engine_import_isolation.py::test_cli_plan_functional |
| 114-REQ-9.E1 | TS-114-E8 | 6.2 | tests/unit/engine/test_engine_import_isolation.py::test_removed_cli_feedback |
| 114-REQ-10.1 | TS-114-35 | 6.5 | make check |
| 114-REQ-10.2 | TS-114-36 | 6.5 | tests/unit/knowledge/test_provider.py (existence) |
| 114-REQ-10.3 | TS-114-37 | 6.5 | tests/unit/engine/test_engine_import_isolation.py (existence) |
| 114-REQ-10.4 | TS-114-38 | 6.4 | tests/unit/engine/test_engine_import_isolation.py::test_dead_tests_deleted |
| Property 1 | TS-114-P1 | 2.1 | tests/property/knowledge/test_knowledge_provider_props.py::test_protocol_conformance |
| Property 2 | TS-114-P2 | 2.2 | tests/property/knowledge/test_knowledge_provider_props.py::test_noop_retrieve_idempotent |
| Property 3 | TS-114-P3 | 2.2 | tests/property/knowledge/test_knowledge_provider_props.py::test_noop_ingest_safe |
| Property 4 | TS-114-P4 | 3.1, 3.4, 5.6 | tests/unit/engine/test_engine_import_isolation.py |
| Property 5 | TS-114-P5 | 5.1, 5.2, 5.3, 5.4 | tests/unit/engine/test_engine_import_isolation.py |
| Property 6 | TS-114-P6 | 5.5, 5.6 | tests/unit/engine/test_engine_import_isolation.py::test_import_health |
| Property 7 | TS-114-P7 | 6.1 | tests/property/knowledge/test_knowledge_provider_props.py::test_config_backward_compat |
| Property 8 | TS-114-P8 | 3.1 | tests/property/knowledge/test_knowledge_provider_props.py::test_retrieve_failure |
| Property 9 | TS-114-P9 | 3.2 | tests/property/knowledge/test_knowledge_provider_props.py::test_ingest_failure |

## Notes

- Task group 5 (deletion) is the riskiest — it removes 27+ files, 2 directories, and 1 engine file in a single group. The import scan in subtask 5.6 must catch all dangling references.
- Nightshift files (`ignore_ingest.py`, `dedup.py`, `ignore_filter.py`) currently depend on `Fact` dataclass and `EmbeddingGenerator`. After deletion, these files need to either be updated to not use embeddings or simplified to remove embedding-dependent functionality.
- The `SleepComputeStream` class in `streams.py` must be deleted or the stream registration removed.
- `cli/status.py`'s `project_model` integration must be replaced with a stub or the status output simplified.
- `reset.py`'s `compact()` call must be removed — the compaction module is being deleted.
- Test deletion in group 6 will remove ~75+ unit test files, ~7 integration test files, and ~1 property test file. This is expected and desirable.
