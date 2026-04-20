# Implementation Plan: Knowledge Context Improvements

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in four groups: (1) write failing tests from
test_spec.md, (2) implement causal traversal integration and confidence
threshold propagation, (3) wire pre-computed fact ranking cache into the
session lifecycle, (4) extend cross-task-group finding propagation to include
all finding types.

The ordering ensures tests are in place first, then the two simpler changes
(causal integration, confidence threading) are done together, followed by the
cache wiring, and finally the finding propagation which touches the most
rendering logic.

## Dependencies

| Spec | Relationship | Justification |
|------|-------------|---------------|
| 37 (confidence normalization) | Requires completed | Float confidence values in [0.0, 1.0] |
| 38 (DuckDB hardening) | Requires completed | Non-optional DuckDB connections |

## Test Commands

- Spec tests: `uv run pytest tests/unit/knowledge/test_knowledge_context.py tests/unit/session/test_context_assembly.py -v`
- Property tests: `uv run pytest tests/property/knowledge/test_knowledge_context_props.py -v`
- All spec + property tests: `uv run pytest tests/unit/knowledge/test_knowledge_context.py tests/unit/session/test_context_assembly.py tests/property/knowledge/test_knowledge_context_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/knowledge/test_knowledge_context.py`
    - Test class `TestTraverseWithReviews` with TS-42-1, TS-42-2, TS-42-3, TS-42-4, TS-42-E1, TS-42-E2
    - Test class `TestConfidenceFiltering` with TS-42-6, TS-42-7, TS-42-8, TS-42-9
    - Test class `TestFactCache` with TS-42-10, TS-42-11, TS-42-12, TS-42-13, TS-42-E3
    - _Test Spec: TS-42-1 through TS-42-4, TS-42-6 through TS-42-13, TS-42-E1, TS-42-E2, TS-42-E3_

  - [x] 1.2 Create `tests/unit/session/test_context_assembly.py`
    - Test class `TestCausalContextAssembly` with TS-42-5
    - Test class `TestPriorGroupFindings` with TS-42-15 through TS-42-20, TS-42-E4, TS-42-E5
    - Test class `TestCacheIntegration` with TS-42-14
    - _Test Spec: TS-42-5, TS-42-14, TS-42-15 through TS-42-20, TS-42-E4, TS-42-E5_

  - [x] 1.3 Create `tests/property/knowledge/test_knowledge_context_props.py`
    - Property test `test_confidence_monotonicity` (TS-42-P1)
    - Property test `test_deduplication_invariant` (TS-42-P2)
    - Property test `test_group_boundary_invariant` (TS-42-P3)
    - Property test `test_cache_staleness_detection` (TS-42-P4)
    - _Test Spec: TS-42-P1 through TS-42-P4_

  - [x] 1.4 Verify all new tests fail and no regressions in existing tests
    - Run spec tests: all new tests should fail (red phase)
    - Run full suite: existing tests must still pass

- [x] 2. Causal traversal integration + confidence threshold propagation
  - [x] 2.1 Update `select_context_with_causal()` in `agent_fox/session/prompt.py`
    - Replace `traverse_causal_chain` import with `traverse_with_reviews`
    - Update traversal calls to use `traverse_with_reviews()`
    - Handle non-CausalFact objects in the result processing loop
    - Render ReviewFinding/DriftFinding/VerificationResult items with type labels
    - Maintain deduplication via `seen_ids` set
    - _Test Spec: TS-42-1 through TS-42-5, TS-42-E1, TS-42-E2_

  - [x] 2.2 Thread confidence threshold from config through session lifecycle
    - Identify all call sites of `select_relevant_facts()` in the codebase
    - Update each call site to pass `config.knowledge.confidence_threshold`
    - Update `precompute_fact_rankings()` call sites to pass threshold from config
    - _Test Spec: TS-42-6 through TS-42-9_

  - [x] 2.3 Verify task group 2 tests pass
    - Run spec tests for causal and confidence: TS-42-1 through TS-42-9, TS-42-E1, TS-42-E2
    - Run property tests TS-42-P1 and TS-42-P2
    - Run full test suite to confirm no regressions

- [x] 3. Pre-computed fact ranking cache integration
  - [x] 3.1 Wire cache population into orchestrator plan dispatch
    - In `agent_fox/engine/engine.py`, after plan construction:
      - Check `config.knowledge.fact_cache_enabled`
      - If enabled, call `precompute_fact_rankings()` with plan spec names
        and `config.knowledge.confidence_threshold`
      - Store cache dict on orchestrator instance
    - _Test Spec: TS-42-10, TS-42-14, TS-42-E3_

  - [x] 3.2 Wire cache lookup into session context assembly
    - Before calling `select_relevant_facts()`, query current active fact count
    - Call `get_cached_facts()` with spec name and current count
    - If cache hit, use cached facts; if miss, fall back to live computation
    - _Test Spec: TS-42-11, TS-42-12, TS-42-13, TS-42-E3_

  - [x] 3.3 Verify task group 3 tests pass
    - Run spec tests for cache: TS-42-10 through TS-42-14, TS-42-E3
    - Run property test TS-42-P4
    - Run full test suite to confirm no regressions

- [x] 4. Cross-task-group finding propagation
  - [x] 4.1 Define `PriorFinding` dataclass in `agent_fox/session/prompt.py`
    - Frozen dataclass with fields: type, group, severity, description, created_at
    - _Test Spec: TS-42-19_

  - [x] 4.2 Extend `get_prior_group_findings()` to query all three tables
    - Add queries for `drift_findings` and `verification_results`
    - Convert results to `PriorFinding` objects with appropriate type labels
    - Merge results from all three tables
    - Sort by `created_at` ascending
    - Change return type from `list[ReviewFinding]` to `list[PriorFinding]`
    - _Test Spec: TS-42-15, TS-42-16, TS-42-17, TS-42-18, TS-42-20, TS-42-E4_

  - [x] 4.3 Update `render_prior_group_findings()` for new data structure
    - Render each PriorFinding with group, type, and severity/verdict labels
    - Handle verification results (render as `requirement_id: verdict`)
    - Return empty string when no findings (causes section omission)
    - _Test Spec: TS-42-19, TS-42-E5_

  - [x] 4.4 Update `assemble_context()` to use new prior findings
    - Ensure the call to `get_prior_group_findings()` and
      `render_prior_group_findings()` works with the new return types
    - _Test Spec: TS-42-E5_

  - [x] 4.5 Verify task group 4 tests pass
    - Run spec tests for propagation: TS-42-15 through TS-42-20, TS-42-E4, TS-42-E5
    - Run property test TS-42-P3
    - Run full test suite: `uv run pytest -x -q`
    - Run linter: `uv run ruff check agent_fox/ tests/`
