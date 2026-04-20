# Implementation Plan: Knowledge Consolidation Agent

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The consolidation pipeline is built in four phases: first the test suite, then
the core module with deterministic steps (data models, pipeline skeleton, git
verification), then the LLM-powered steps (merging, promotion, pruning), and
finally orchestrator integration (barrier hook, end-of-run hook, cost tracking).
Each phase builds on the previous one.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_consolidation.py tests/unit/engine/test_consolidation_barrier.py tests/integration/knowledge/test_consolidation_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/knowledge/test_consolidation.py tests/unit/engine/test_consolidation_barrier.py`
- Property tests: `uv run pytest -q tests/property/knowledge/test_consolidation_props.py`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/unit/knowledge/test_consolidation.py` for TS-96-1
      through TS-96-20, TS-96-E1 through TS-96-E9
    - Create `tests/unit/engine/test_consolidation_barrier.py` for TS-96-21
      through TS-96-24, TS-96-E10, TS-96-E11
    - Create `tests/property/knowledge/test_knowledge_consolidation_props.py` for
      TS-96-P1 through TS-96-P6 (renamed; see docs/errata/96_test_naming.md)
    - Create `tests/integration/knowledge/test_consolidation_smoke.py` for
      TS-96-SMOKE-1 and TS-96-SMOKE-2
    - Use existing DuckDB fixtures; add fixtures for entity graph tables
      (requires migration v8 from spec 95)
    - _Test Spec: TS-96-1 through TS-96-24, TS-96-E1 through TS-96-E11,
      TS-96-P1 through TS-96-P6, TS-96-SMOKE-1, TS-96-SMOKE-2_

  - [x] 1.2 Translate acceptance-criterion tests from test_spec.md
    - One test function per TS-96-{N} entry (24 tests)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - Import from `agent_fox.knowledge.consolidation`
    - _Test Spec: TS-96-1 through TS-96-24_

  - [x] 1.3 Translate edge-case tests from test_spec.md
    - One test function per TS-96-E{N} entry (11 tests)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-96-E1 through TS-96-E11_

  - [x] 1.4 Translate property tests from test_spec.md
    - One property test per TS-96-P{N} entry (6 tests)
    - Use Hypothesis with `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-96-P1 through TS-96-P6_

  - [x] 1.5 Translate integration smoke tests from test_spec.md
    - One test per TS-96-SMOKE-{N} entry (2 tests)
    - Use real DuckDB connections with migrations through v8
    - Mock subprocess (git) and LLM calls
    - _Test Spec: TS-96-SMOKE-1, TS-96-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Core consolidation module (deterministic steps)
  - [x] 2.1 Create `agent_fox/knowledge/consolidation.py` with data models
    - Define `CONSOLIDATION_STALE_SENTINEL` (uuid5)
    - Define `VerificationResult`, `MergeResult`, `PromotionResult`,
      `PruneResult`, `ConsolidationResult` dataclasses
    - _Requirements: 96-REQ-1.1, 96-REQ-3.4_

  - [x] 2.2 Implement pipeline skeleton (`run_consolidation`)
    - Async entry point that calls each step in order
    - Wrap each step in try/except: log warning, record error name, continue
    - Emit `consolidation.complete` audit event on completion
    - Handle zero-facts early exit
    - _Requirements: 96-REQ-1.1, 96-REQ-1.2, 96-REQ-1.3, 96-REQ-1.E1_

  - [x] 2.3 Implement git verification step (`_verify_against_git`)
    - Query `fact_entities JOIN entity_graph` for active facts with file links
    - Check file existence on disk for each linked file
    - Run `git diff --numstat` for facts with commit_sha
    - Compute change ratio: (insertions + deletions) / current_line_count
    - Supersede facts where all linked files deleted (set superseded_by to sentinel)
    - Halve confidence for significantly changed files (ratio > threshold)
    - Skip facts without entity links; skip change check if no commit_sha
    - Return `VerificationResult` with counts
    - _Requirements: 96-REQ-3.1, 96-REQ-3.2, 96-REQ-3.3, 96-REQ-3.4,
      96-REQ-3.E1, 96-REQ-3.E2_

  - [x] 2.4 Implement entity graph integration helpers
    - `_refresh_entity_graph(conn, repo_root)`: call `analyze_codebase`,
      handle missing tables gracefully
    - `_link_unlinked_facts(conn, repo_root)`: query unlinked facts (LEFT JOIN
      fact_entities WHERE NULL), call `link_facts`
    - Handle missing entity graph tables (96-REQ-1.E2) and invalid repo root
      (96-REQ-2.E1) gracefully
    - _Requirements: 96-REQ-2.1, 96-REQ-2.2, 96-REQ-2.3, 96-REQ-1.E2,
      96-REQ-2.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for deterministic steps pass: `uv run pytest -q tests/unit/knowledge/test_consolidation.py -k "pipeline or step_fail or audit or entity_refresh or unlinked or git_verify or supersede or halve or verification_result or no_facts or missing_tables or invalid_repo or no_links or no_commit_sha"`
    - [x] Property tests P1, P2, P6 pass: `uv run pytest -q tests/property/knowledge/test_consolidation_props.py -k "independence or git_accuracy or confidence"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 96-REQ-1.*, 96-REQ-2.*, 96-REQ-3.* acceptance criteria met

- [x] 3. LLM-powered consolidation steps
  - [x] 3.1 Implement cross-spec fact merging (`_merge_related_facts`)
    - Find clusters of similar facts across different specs using embedding
      cosine similarity above configurable threshold
    - Build LLM prompt with cluster facts, call LLM for merge/link decision
    - Merge action: create consolidated fact (max confidence from cluster),
      supersede originals
    - Link action: add causal edges between cluster facts
    - Handle embedding failures (exclude fact) and LLM failures (skip cluster)
    - _Requirements: 96-REQ-4.1, 96-REQ-4.2, 96-REQ-4.3, 96-REQ-4.4,
      96-REQ-4.E1, 96-REQ-4.E2_

  - [x] 3.2 Implement pattern promotion (`_promote_patterns`)
    - Find groups of similar active facts spanning 3+ distinct spec_name values
    - Check for existing pattern links (skip if already linked to pattern fact)
    - Build LLM prompt, call for pattern confirmation and description
    - Create new fact (category=PATTERN, confidence=0.9, LLM-generated content)
    - Add causal edges from original facts to pattern fact
    - _Requirements: 96-REQ-5.1, 96-REQ-5.2, 96-REQ-5.3, 96-REQ-5.E1_

  - [x] 3.3 Implement causal chain pruning (`_prune_redundant_chains`)
    - Query `fact_causes` for chains A->B->C where direct A->C exists
    - Build LLM prompt with facts A, B, C for intermediate evaluation
    - Remove edges A->B and B->C if B not meaningful (preserve A->C)
    - Handle LLM failures (preserve all edges)
    - _Requirements: 96-REQ-6.1, 96-REQ-6.2, 96-REQ-6.3, 96-REQ-6.E1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for LLM steps pass: `uv run pytest -q tests/unit/knowledge/test_consolidation.py -k "cluster or merge_class or merge_action or link_action or pattern or chain or prune or embed_fail or llm_fail or duplicate_pattern or chain_eval"`
    - [x] Property tests P3, P4, P5 pass: `uv run pytest -q tests/property/knowledge/test_consolidation_props.py -k "idempotency or threshold or preservation"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 96-REQ-4.*, 96-REQ-5.*, 96-REQ-6.* acceptance criteria met

- [x] 4. Orchestrator integration
  - [x] 4.1 Hook consolidation into sync barrier (`engine/barrier.py`)
    - Add consolidation step after lifecycle cleanup (line ~229), before
      memory summary regeneration
    - Accept `completed_specs_fn`, `consolidation_fn`, and `consolidated_specs`
      set as parameters to `run_sync_barrier_sequence`
    - Call consolidation when `completed_specs_fn()` returns new specs not in
      `consolidated_specs`
    - Add consolidated spec names to the tracking set
    - _Requirements: 96-REQ-7.1, 96-REQ-7.3_

  - [x] 4.2 Hook consolidation into end-of-run (`engine/engine.py`)
    - In the finally block, after `cleanup_completed_spec_audits`, determine
      specs not yet consolidated (`completed - _consolidated_specs`)
    - Call `run_consolidation` for remaining specs
    - Log result at INFO level
    - _Requirements: 96-REQ-7.2_

  - [x] 4.3 Wire consolidated_specs tracking through the engine
    - Add `_consolidated_specs: set[str]` to the engine instance
    - Pass it through to `run_sync_barrier_sequence`
    - Pass `completed_spec_names` function to barrier
    - Wire `run_consolidation` import and parameters (conn, repo_root, model,
      embedding_generator, sink_dispatcher, run_id)
    - _Requirements: 96-REQ-7.1, 96-REQ-7.2, 96-REQ-7.3_

  - [x] 4.4 Add consolidation cost tracking
    - Track LLM costs within `run_consolidation` (sum of individual step costs)
    - Emit `consolidation.cost` audit event with cost breakdown
    - Implement budget check: abort step if remaining budget exceeded
    - Report consolidation cost in `ConsolidationResult.total_llm_cost`
    - _Requirements: 96-REQ-7.4, 96-REQ-7.E1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for orchestrator integration pass: `uv run pytest -q tests/unit/engine/test_consolidation_barrier.py`
    - [x] Smoke tests pass: `uv run pytest -q tests/integration/knowledge/test_consolidation_smoke.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 96-REQ-7.* acceptance criteria met

- [x] 5. Wiring verification

  - [x] 5.1 Trace every execution path from design.md end-to-end
    - For each of the 2 paths, verify the entry point actually calls the next
      function in the chain (read the calling code, do not assume)
    - Path 1: barrier.py -> run_consolidation -> each step -> DuckDB mutations
    - Path 2: engine.py finally block -> run_consolidation -> each step
    - Confirm no function in the chain is a stub
    - _Requirements: all_
    - **Verified:** barrier.py lines 237-261 call run_consolidation after
      lifecycle cleanup. engine.py lines 607-632 in finally block call
      run_consolidation for remaining specs. All 6 pipeline steps have real
      DuckDB mutations (no stubs). analyze_codebase and link_facts called from
      _refresh_entity_graph and _link_unlinked_facts respectively.

  - [x] 5.2 Verify return values propagate correctly
    - Key return value chains:
      - `analyze_codebase()` -> `_refresh_entity_graph()` -> `ConsolidationResult.entity_refresh`
      - `link_facts()` -> `_link_unlinked_facts()` -> `ConsolidationResult.facts_linked`
      - `_verify_against_git()` -> `ConsolidationResult.verification`
      - `_merge_related_facts()` -> `ConsolidationResult.merging`
      - `_promote_patterns()` -> `ConsolidationResult.promotion`
      - `_prune_redundant_chains()` -> `ConsolidationResult.pruning`
    - Grep for callers; confirm none discards the return
    - _Requirements: all_
    - **Verified:** All 6 return values assigned in run_consolidation (lines
      904-999) and included in ConsolidationResult. link_result.links_created
      assigned to facts_linked (line 919). No callers discard returns.

  - [x] 5.3 Run the integration smoke tests
    - All `TS-96-SMOKE-*` tests pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/knowledge/test_consolidation_smoke.py`
    - _Test Spec: TS-96-SMOKE-1, TS-96-SMOKE-2_
    - **Verified:** 2 passed in 6.31s

  - [x] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale
    - **Verified:** Two `return []` hits found, both justified:
      - barrier.py:47 — returns empty orphan list when worktrees dir missing
        (correct guard per 51-REQ-2.E1)
      - engine.py:1145 — returns empty predecessors list when _graph_sync is
        None (correct guard for uninitialized state)
      No `# TODO`, `# stub`, `NotImplementedError`, or `pass` stubs in any
      consolidation-touched file.

  - [x] 5.5 Cross-spec entry point verification
    - Verify that `run_consolidation` is called from production code in both:
      (a) `engine/barrier.py` (sync barrier path)
      (b) `engine/engine.py` (end-of-run path)
    - Verify that spec 95 functions (`analyze_codebase`, `link_facts`) are
      called from `consolidation.py` (not just from tests)
    - Confirm no circular imports are introduced
    - _Requirements: all_
    - **Verified:** run_consolidation imported and called in barrier.py (line
      30 import, line 247 call). engine.py imports and calls it in finally
      block (lines 609, 617). consolidation.py imports analyze_codebase
      (line 28) and link_facts (line 27) at module level and calls them in
      _refresh_entity_graph and _link_unlinked_facts. No circular imports
      (Python import of all three modules succeeds without error).

  - [x] 5.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All cross-spec entry points are called from production code
    - [x] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 96-REQ-1.1 | TS-96-1 | 2.2 | test_consolidation::test_pipeline_ordering |
| 96-REQ-1.2 | TS-96-2 | 2.2 | test_consolidation::test_step_failure_isolation |
| 96-REQ-1.3 | TS-96-3 | 2.2 | test_consolidation::test_audit_event |
| 96-REQ-1.E1 | TS-96-E1 | 2.2 | test_consolidation::test_zero_facts |
| 96-REQ-1.E2 | TS-96-E2 | 2.4 | test_consolidation::test_missing_entity_tables |
| 96-REQ-2.1 | TS-96-4 | 2.4 | test_consolidation::test_entity_refresh |
| 96-REQ-2.2 | TS-96-5 | 2.4 | test_consolidation::test_unlinked_facts |
| 96-REQ-2.3 | TS-96-6 | 2.4 | test_consolidation::test_entity_counts_in_result |
| 96-REQ-2.E1 | TS-96-E3 | 2.4 | test_consolidation::test_invalid_repo_root |
| 96-REQ-3.1 | TS-96-7 | 2.3 | test_consolidation::test_git_verify_queries_links |
| 96-REQ-3.2 | TS-96-8 | 2.3 | test_consolidation::test_supersede_deleted_files |
| 96-REQ-3.3 | TS-96-9 | 2.3 | test_consolidation::test_halve_confidence |
| 96-REQ-3.4 | TS-96-10 | 2.3 | test_consolidation::test_verification_counts |
| 96-REQ-3.E1 | TS-96-E4 | 2.3 | test_consolidation::test_skip_no_entity_links |
| 96-REQ-3.E2 | TS-96-E5 | 2.3 | test_consolidation::test_no_commit_sha |
| 96-REQ-4.1 | TS-96-11 | 3.1 | test_consolidation::test_cluster_detection |
| 96-REQ-4.2 | TS-96-12 | 3.1 | test_consolidation::test_llm_merge_classification |
| 96-REQ-4.3 | TS-96-13 | 3.1 | test_consolidation::test_merge_creates_fact |
| 96-REQ-4.4 | TS-96-14 | 3.1 | test_consolidation::test_link_adds_edges |
| 96-REQ-4.E1 | TS-96-E6 | 3.1 | test_consolidation::test_embedding_failure |
| 96-REQ-4.E2 | TS-96-E7 | 3.1 | test_consolidation::test_llm_merge_failure |
| 96-REQ-5.1 | TS-96-15 | 3.2 | test_consolidation::test_pattern_candidates |
| 96-REQ-5.2 | TS-96-16 | 3.2 | test_consolidation::test_llm_pattern_confirm |
| 96-REQ-5.3 | TS-96-17 | 3.2 | test_consolidation::test_pattern_fact_creation |
| 96-REQ-5.E1 | TS-96-E8 | 3.2 | test_consolidation::test_duplicate_pattern_skip |
| 96-REQ-6.1 | TS-96-18 | 3.3 | test_consolidation::test_redundant_chain_detect |
| 96-REQ-6.2 | TS-96-19 | 3.3 | test_consolidation::test_llm_chain_eval |
| 96-REQ-6.3 | TS-96-20 | 3.3 | test_consolidation::test_edge_removal |
| 96-REQ-6.E1 | TS-96-E9 | 3.3 | test_consolidation::test_chain_llm_failure |
| 96-REQ-7.1 | TS-96-21 | 4.1 | test_consolidation_barrier::test_barrier_triggers |
| 96-REQ-7.2 | TS-96-22 | 4.2 | test_consolidation_barrier::test_end_of_run |
| 96-REQ-7.3 | TS-96-23 | 4.1 | test_consolidation_barrier::test_exclusive_access |
| 96-REQ-7.4 | TS-96-24 | 4.4 | test_consolidation_barrier::test_cost_reporting |
| 96-REQ-7.E1 | TS-96-E10 | 4.4 | test_consolidation_barrier::test_budget_exceeded |
| 96-REQ-7.E2 | TS-96-E11 | 4.1 | test_consolidation_barrier::test_no_completed_specs |
| Property 1 | TS-96-P1 | 2.2 | test_consolidation_props::test_step_independence |
| Property 2 | TS-96-P2 | 2.3 | test_consolidation_props::test_git_verification_accuracy |
| Property 3 | TS-96-P3 | 3.1 | test_consolidation_props::test_merge_idempotency |
| Property 4 | TS-96-P4 | 3.2 | test_consolidation_props::test_pattern_threshold |
| Property 5 | TS-96-P5 | 3.3 | test_consolidation_props::test_chain_preservation |
| Property 6 | TS-96-P6 | 2.3 | test_consolidation_props::test_confidence_bounds |
| Path 1 | TS-96-SMOKE-1 | 4.1 | test_consolidation_smoke::test_barrier_pipeline |
| Path 2 | TS-96-SMOKE-2 | 4.2 | test_consolidation_smoke::test_end_of_run_pipeline |

## Notes

- **LLM mocking:** All unit tests mock LLM calls. Use structured JSON responses
  matching the prompt templates defined in consolidation.py.
- **Hypothesis health checks:** Use
  `suppress_health_check=[HealthCheck.function_scoped_fixture]` for property
  tests using pytest fixtures.
- **Subprocess mocking:** All `git diff` calls in tests should mock
  `subprocess.run` to avoid requiring a real git history.
- **Entity graph dependency:** Tests require migration v8 (from spec 95) for
  entity graph tables. Use the same DuckDB fixture pattern as spec 95 tests.
- **Barrier test fixtures:** Tests for `run_sync_barrier_sequence` need to
  mock many parameters (hot_load_fn, sync_plan_fn, etc.). Reuse existing
  barrier test fixtures where available.
- **Confidence revisit:** The 50% change-ratio threshold and confidence-halving
  approach (96-REQ-3.3) are design decisions marked for revisit after
  real-world usage data is available (see prd.md Design Decision 6).
- **Cost tracking:** Consolidation LLM calls share the run's budget. The
  budget check occurs before each LLM call. If exceeded, the current step
  aborts and returns a partial result.
