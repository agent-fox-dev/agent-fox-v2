# Implementation Plan: Predictive Planning and Knowledge Usage

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in seven groups: (1) write failing tests, (2) duration
hints with presets and historical median, (3) duration regression model and
ordering integration, (4) causal graph review integration and confidence
filtering, (5) fact cache and cross-group finding propagation, (6) project
model and critical path, (7) file conflict detection and learned blocking
thresholds.

Groups 2-3 cover planning/dispatch improvements. Groups 4-5 cover knowledge
improvements. Groups 6-7 cover model/conflict/threshold features.

## Test Commands

- Spec tests: `uv run pytest tests/unit/routing/test_duration.py tests/unit/knowledge/test_causal_reviews.py tests/unit/memory/test_confidence_filter.py tests/unit/engine/test_fact_cache.py tests/unit/knowledge/test_project_model.py tests/unit/graph/test_critical_path.py tests/unit/graph/test_file_impacts.py tests/unit/knowledge/test_blocking_history.py -v`
- Property tests: `uv run pytest tests/property/planning/test_predictive_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create `tests/unit/routing/test_duration.py`
    - Test class `TestDurationOrdering` with TS-39-1
    - Test class `TestDurationHints` with TS-39-2, TS-39-3, TS-39-4
    - Test class `TestDurationRegression` with TS-39-5, TS-39-6, TS-39-7
    - _Test Spec: TS-39-1 through TS-39-7, TS-39-E1_

  - [ ] 1.2 Create `tests/unit/knowledge/test_causal_reviews.py`
    - Test class `TestCausalTraversalWithReviews` with TS-39-8, TS-39-9, TS-39-10
    - _Test Spec: TS-39-8, TS-39-9, TS-39-10_

  - [ ] 1.3 Create `tests/unit/memory/test_confidence_filter.py`
    - Test class `TestConfidenceFiltering` with TS-39-11, TS-39-12, TS-39-13
    - _Test Spec: TS-39-11, TS-39-12, TS-39-13_

  - [ ] 1.4 Create `tests/unit/engine/test_fact_cache.py` and `tests/unit/knowledge/test_project_model.py`
    - Test class `TestFactCache` with TS-39-14, TS-39-15, TS-39-16
    - Test class `TestFindingPropagation` with TS-39-17, TS-39-18
    - Test class `TestProjectModel` with TS-39-19, TS-39-20, TS-39-21, TS-39-22
    - _Test Spec: TS-39-14 through TS-39-22_

  - [ ] 1.5 Create `tests/unit/graph/test_critical_path.py` and `tests/unit/graph/test_file_impacts.py` and `tests/unit/knowledge/test_blocking_history.py`
    - Test class `TestCriticalPath` with TS-39-23, TS-39-24, TS-39-25
    - Test class `TestFileImpacts` with TS-39-26, TS-39-27, TS-39-28
    - Test class `TestBlockingHistory` with TS-39-29, TS-39-30, TS-39-31
    - _Test Spec: TS-39-23 through TS-39-31, TS-39-E2_

  - [ ] 1.6 Create `tests/property/planning/test_predictive_props.py`
    - Property tests TS-39-P1 through TS-39-P8
    - _Test Spec: TS-39-P1 through TS-39-P8_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings: `uv run ruff check tests/unit/routing/test_duration.py tests/unit/knowledge/test_causal_reviews.py tests/unit/memory/test_confidence_filter.py tests/unit/engine/test_fact_cache.py tests/unit/knowledge/test_project_model.py tests/unit/graph/test_critical_path.py tests/unit/graph/test_file_impacts.py tests/unit/knowledge/test_blocking_history.py tests/property/planning/test_predictive_props.py`

- [ ] 2. Duration hints with presets and historical median
  - [ ] 2.1 Create `agent_fox/routing/duration_presets.py`
    - Define DURATION_PRESETS dict (archetype -> tier -> ms)
    - Define DEFAULT_DURATION_MS constant
    - _Requirements: 39-REQ-1.3_

  - [ ] 2.2 Create `agent_fox/routing/duration.py`
    - Implement DurationHint dataclass
    - Implement `get_duration_hint()` with historical median lookup and preset fallback
    - Historical: query execution_outcomes for median duration by spec+archetype
    - Preset: lookup from DURATION_PRESETS
    - Default: use DEFAULT_DURATION_MS
    - _Requirements: 39-REQ-1.2, 39-REQ-1.4, 39-REQ-1.E1_

  - [ ] 2.3 Add duration ordering to `agent_fox/engine/graph_sync.py`
    - Update `ready_tasks()` to accept optional duration_hints parameter
    - Sort ready set by predicted duration descending, ties alphabetical
    - _Requirements: 39-REQ-1.1, 39-REQ-1.3_

  - [ ] 2.4 Add `[planning]` config section
    - Add duration_ordering, min_outcomes_for_historical, min_outcomes_for_regression
      to config schema
    - _Requirements: 39-REQ-1.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/routing/test_duration.py::TestDurationOrdering tests/unit/routing/test_duration.py::TestDurationHints -v`
    - [ ] Edge case test passes: `uv run pytest tests/unit/routing/test_duration.py -k "insufficient_outcomes" -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/routing/duration.py agent_fox/routing/duration_presets.py agent_fox/engine/graph_sync.py`
    - [ ] Requirements 39-REQ-1.* met

- [ ] 3. Duration regression model and dispatch integration
  - [ ] 3.1 Add `train_duration_model()` to `agent_fox/routing/duration.py`
    - Train LinearRegression from execution_outcomes feature vectors
    - Return None if fewer than min_outcomes_for_regression outcomes
    - _Requirements: 39-REQ-2.1_

  - [ ] 3.2 Integrate regression into `get_duration_hint()`
    - Check for trained model first (source="regression")
    - Fall back to historical > preset > default
    - _Requirements: 39-REQ-2.2_

  - [ ] 3.3 Add retraining trigger
    - Retrain model when new outcomes are recorded (same trigger as tier classifier)
    - _Requirements: 39-REQ-2.3_

  - [ ] 3.4 Integrate duration ordering into `engine/engine.py` dispatch
    - Call `get_duration_hint()` for each ready task
    - Pass hints to `ready_tasks()` ordering
    - _Requirements: 39-REQ-1.1_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/routing/test_duration.py::TestDurationRegression -v`
    - [ ] Property tests pass: `uv run pytest tests/property/planning/test_predictive_props.py::test_duration_ordering_correctness tests/property/planning/test_predictive_props.py::test_duration_hint_source_precedence -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/routing/duration.py agent_fox/engine/engine.py`
    - [ ] Requirements 39-REQ-2.* met

- [ ] 4. Causal graph review integration and confidence filtering
  - [ ] 4.1 Add `traverse_with_reviews()` to `agent_fox/knowledge/causal.py`
    - Query review_findings, drift_findings, verification_results alongside fact_causes
    - Match review findings to facts by requirement ID keywords
    - _Requirements: 39-REQ-3.1, 39-REQ-3.2, 39-REQ-3.3_

  - [ ] 4.2 Update `select_relevant_facts()` in `agent_fox/memory/filter.py`
    - Add confidence_threshold parameter (default 0.5)
    - Filter facts by confidence before keyword scoring
    - _Requirements: 39-REQ-4.1, 39-REQ-4.3_

  - [ ] 4.3 Add `[knowledge]` config section
    - Add confidence_threshold and fact_cache_enabled settings
    - _Requirements: 39-REQ-4.2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_causal_reviews.py tests/unit/memory/test_confidence_filter.py -v`
    - [ ] Property test passes: `uv run pytest tests/property/planning/test_predictive_props.py::test_confidence_filter_monotonicity -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/causal.py agent_fox/memory/filter.py`
    - [ ] Requirements 39-REQ-3.*, 39-REQ-4.* met

- [ ] 5. Fact cache and cross-group finding propagation
  - [ ] 5.1 Create `agent_fox/engine/fact_cache.py`
    - Implement RankedFactCache dataclass
    - Implement `precompute_fact_rankings()` — compute and cache per-spec ranked facts
    - Implement `get_cached_facts()` — return cached if valid, None if stale
    - Add ranked_fact_cache DuckDB table
    - _Requirements: 39-REQ-5.1, 39-REQ-5.2, 39-REQ-5.3_

  - [ ] 5.2 Integrate fact cache into context assembly
    - Update `assemble_context()` in `agent_fox/session/prompt.py`
    - Use cached rankings when available, fall back to live computation
    - _Requirements: 39-REQ-5.2_

  - [ ] 5.3 Add cross-group finding propagation to `agent_fox/session/prompt.py`
    - Query findings from groups 1..K-1 when assembling context for group K
    - Render propagated findings under "Prior Group Findings" section
    - _Requirements: 39-REQ-6.1, 39-REQ-6.2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest tests/unit/engine/test_fact_cache.py tests/unit/knowledge/test_project_model.py::TestFindingPropagation -v`
    - [ ] Property tests pass: `uv run pytest tests/property/planning/test_predictive_props.py::test_fact_cache_consistency tests/property/planning/test_predictive_props.py::test_cross_group_finding_visibility -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/engine/fact_cache.py agent_fox/session/prompt.py`
    - [ ] Requirements 39-REQ-5.*, 39-REQ-6.* met

- [ ] 6. Project model and critical path
  - [ ] 6.1 Create `agent_fox/knowledge/project_model.py`
    - Implement SpecMetrics and ProjectModel dataclasses
    - Implement `build_project_model()` — aggregate from execution_outcomes
    - Compute avg_cost, avg_duration_ms, failure_rate, session_count per spec
    - Compute module_stability from review finding density
    - Compute archetype_effectiveness as success rate per archetype
    - _Requirements: 39-REQ-7.1, 39-REQ-7.2, 39-REQ-7.3_

  - [ ] 6.2 Create `agent_fox/graph/critical_path.py`
    - Implement CriticalPathResult dataclass
    - Implement `compute_critical_path()` using forward/backward pass
    - Handle tied paths (multiple critical paths with equal duration)
    - _Requirements: 39-REQ-8.1, 39-REQ-8.3_

  - [ ] 6.3 Integrate into status output
    - Add project model to `agent-fox status --model` output
    - Add critical path to `agent-fox status` output
    - _Requirements: 39-REQ-7.4, 39-REQ-8.2_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_project_model.py::TestProjectModel tests/unit/graph/test_critical_path.py -v`
    - [ ] Property test passes: `uv run pytest tests/property/planning/test_predictive_props.py::test_critical_path_validity -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/project_model.py agent_fox/graph/critical_path.py`
    - [ ] Requirements 39-REQ-7.*, 39-REQ-8.* met

- [ ] 7. File conflict detection and learned blocking thresholds
  - [ ] 7.1 Create `agent_fox/graph/file_impacts.py`
    - Implement FileImpact dataclass
    - Implement `extract_file_impacts()` — regex extraction from tasks.md and design.md
    - Implement `detect_conflicts()` — pairwise overlap detection
    - Add task_file_impacts DuckDB table
    - _Requirements: 39-REQ-9.1, 39-REQ-9.2, 39-REQ-9.E1_

  - [ ] 7.2 Integrate conflict detection into dispatch
    - When file_conflict_detection is enabled, serialize conflicting task pairs
    - Add `[planning] file_conflict_detection` config flag
    - _Requirements: 39-REQ-9.3_

  - [ ] 7.3 Create `agent_fox/knowledge/blocking_history.py`
    - Implement BlockingDecision dataclass
    - Implement `record_blocking_decision()` — store to blocking_history table
    - Implement `compute_optimal_threshold()` — minimize false positives at target FNR
    - Add blocking_history and learned_thresholds DuckDB tables
    - _Requirements: 39-REQ-10.1, 39-REQ-10.2, 39-REQ-10.3_

  - [ ] 7.4 Integrate learned thresholds into convergence
    - Update `agent_fox/session/convergence.py` to use learned thresholds
    - Add `[blocking]` config section with learn_thresholds, min_decisions, max_fnr
    - Surface learned thresholds in status --model output
    - _Requirements: 39-REQ-10.2, 39-REQ-10.3_

  - [ ] 7.V Verify task group 7
    - [ ] Spec tests pass: `uv run pytest tests/unit/graph/test_file_impacts.py tests/unit/knowledge/test_blocking_history.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/planning/test_predictive_props.py::test_file_conflict_symmetry tests/property/planning/test_predictive_props.py::test_blocking_threshold_convergence -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/graph/file_impacts.py agent_fox/knowledge/blocking_history.py agent_fox/session/convergence.py`
    - [ ] Requirements 39-REQ-9.*, 39-REQ-10.* met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 39-REQ-1.1 | TS-39-1 | 2.3, 3.4 | `test_duration.py::TestDurationOrdering::test_descending_order` |
| 39-REQ-1.2 | TS-39-2 | 2.2 | `test_duration.py::TestDurationHints::test_historical_median` |
| 39-REQ-1.3 | TS-39-3 | 2.1, 2.3 | `test_duration.py::TestDurationHints::test_preset_fallback` |
| 39-REQ-1.4 | TS-39-4 | 2.2 | `test_duration.py::TestDurationHints::test_returns_duration_hint` |
| 39-REQ-1.E1 | TS-39-E1 | 2.2, 2.4 | `test_duration.py::TestDurationHints::test_insufficient_outcomes` |
| 39-REQ-2.1 | TS-39-5 | 3.1 | `test_duration.py::TestDurationRegression::test_model_training` |
| 39-REQ-2.2 | TS-39-6 | 3.2 | `test_duration.py::TestDurationRegression::test_regression_priority` |
| 39-REQ-2.3 | TS-39-7 | 3.3 | `test_duration.py::TestDurationRegression::test_retraining` |
| 39-REQ-3.1 | TS-39-8 | 4.1 | `test_causal_reviews.py::TestCausalTraversalWithReviews::test_includes_review_findings` |
| 39-REQ-3.2 | TS-39-9 | 4.1 | `test_causal_reviews.py::TestCausalTraversalWithReviews::test_function_exists` |
| 39-REQ-3.3 | TS-39-10 | 4.1 | `test_causal_reviews.py::TestCausalTraversalWithReviews::test_requirement_id_linking` |
| 39-REQ-4.1 | TS-39-11 | 4.2 | `test_confidence_filter.py::TestConfidenceFiltering::test_threshold_filtering` |
| 39-REQ-4.2 | TS-39-12 | 4.3 | `test_confidence_filter.py::TestConfidenceFiltering::test_configurable_threshold` |
| 39-REQ-4.3 | TS-39-13 | 4.2 | `test_confidence_filter.py::TestConfidenceFiltering::test_filter_before_scoring` |
| 39-REQ-5.1 | TS-39-14 | 5.1 | `test_fact_cache.py::TestFactCache::test_precompute_rankings` |
| 39-REQ-5.2 | TS-39-15 | 5.1, 5.2 | `test_fact_cache.py::TestFactCache::test_stale_cache_returns_none` |
| 39-REQ-5.3 | TS-39-16 | 5.1 | `test_fact_cache.py::TestFactCache::test_cache_invalidation` |
| 39-REQ-6.1 | TS-39-17 | 5.3 | `test_project_model.py::TestFindingPropagation::test_cross_group_findings` |
| 39-REQ-6.2 | TS-39-18 | 5.3 | `test_project_model.py::TestFindingPropagation::test_prior_group_label` |
| 39-REQ-7.1 | TS-39-19 | 6.1 | `test_project_model.py::TestProjectModel::test_spec_metrics` |
| 39-REQ-7.2 | TS-39-20 | 6.1 | `test_project_model.py::TestProjectModel::test_module_stability` |
| 39-REQ-7.3 | TS-39-21 | 6.1 | `test_project_model.py::TestProjectModel::test_archetype_effectiveness` |
| 39-REQ-7.4 | TS-39-22 | 6.3 | `test_project_model.py::TestProjectModel::test_status_output` |
| 39-REQ-8.1 | TS-39-23 | 6.2 | `test_critical_path.py::TestCriticalPath::test_compute_critical_path` |
| 39-REQ-8.2 | TS-39-24 | 6.3 | `test_critical_path.py::TestCriticalPath::test_status_output` |
| 39-REQ-8.3 | TS-39-25 | 6.2 | `test_critical_path.py::TestCriticalPath::test_tied_paths` |
| 39-REQ-9.1 | TS-39-26 | 7.1 | `test_file_impacts.py::TestFileImpacts::test_extract_impacts` |
| 39-REQ-9.2 | TS-39-27 | 7.1 | `test_file_impacts.py::TestFileImpacts::test_detect_conflicts` |
| 39-REQ-9.3 | TS-39-28 | 7.2 | `test_file_impacts.py::TestFileImpacts::test_serialize_conflicting` |
| 39-REQ-9.E1 | TS-39-E2 | 7.1 | `test_file_impacts.py::TestFileImpacts::test_no_impacts_non_conflicting` |
| 39-REQ-10.1 | TS-39-29 | 7.3 | `test_blocking_history.py::TestBlockingHistory::test_record_decision` |
| 39-REQ-10.2 | TS-39-30 | 7.3 | `test_blocking_history.py::TestBlockingHistory::test_compute_threshold` |
| 39-REQ-10.3 | TS-39-31 | 7.3, 7.4 | `test_blocking_history.py::TestBlockingHistory::test_stored_thresholds` |
| Property 1 | TS-39-P1 | 2.3 | `test_predictive_props.py::test_duration_ordering_correctness` |
| Property 2 | TS-39-P2 | 2.2, 3.2 | `test_predictive_props.py::test_duration_hint_source_precedence` |
| Property 3 | TS-39-P3 | 4.2 | `test_predictive_props.py::test_confidence_filter_monotonicity` |
| Property 4 | TS-39-P4 | 5.1 | `test_predictive_props.py::test_fact_cache_consistency` |
| Property 5 | TS-39-P5 | 5.3 | `test_predictive_props.py::test_cross_group_finding_visibility` |
| Property 6 | TS-39-P6 | 7.1 | `test_predictive_props.py::test_file_conflict_symmetry` |
| Property 7 | TS-39-P7 | 6.2 | `test_predictive_props.py::test_critical_path_validity` |
| Property 8 | TS-39-P8 | 7.3 | `test_predictive_props.py::test_blocking_threshold_convergence` |

## Notes

- This spec depends on spec 37 (confidence normalization) for float confidence
  values used in threshold filtering (group 4). Spec 37 group 4 must complete
  before this spec's group 4.
- This spec depends on spec 38 (DuckDB hardening) for non-optional connections.
  Spec 38 group 4 must complete before this spec's group 2+.
- Duration presets should be conservative estimates — better to overestimate
  than underestimate, since overestimation just means the task starts earlier.
- The regression model uses scikit-learn LinearRegression, already a dependency
  via the adaptive routing module.
- File conflict detection (group 7) is behind a config flag, disabled by default.
- Learned blocking thresholds (group 7) are behind a config flag, disabled by default.
