# Implementation Plan: Duration-Based Task Ordering

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in three task groups: (1) write failing tests from
test_spec.md, (2) implement duration hints, presets, ordering, and config,
(3) implement regression model and orchestrator integration.

The code already exists in `agent_fox/routing/duration.py`,
`agent_fox/routing/duration_presets.py`, `agent_fox/engine/graph_sync.py`,
`agent_fox/engine/engine.py`, and `agent_fox/core/config.py` from the
original spec 39 implementation. This spec validates and hardens that
implementation against the focused requirements extracted from spec 39.

## Test Commands

- Spec tests: `uv run pytest tests/unit/routing/test_duration.py tests/unit/routing/test_duration_presets.py tests/unit/engine/test_duration_ordering.py tests/property/routing/test_duration_props.py -v`
- Unit tests: `uv run pytest tests/unit/routing/test_duration.py tests/unit/routing/test_duration_presets.py tests/unit/engine/test_duration_ordering.py -v`
- Property tests: `uv run pytest tests/property/routing/test_duration_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/ && uv run ruff format --check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/routing/test_duration.py`
    - Test class `TestGetDurationHint` with TS-41-5, TS-41-6, TS-41-10, TS-41-14, TS-41-15
    - Test class `TestHistoricalMedian` with TS-41-7, TS-41-8
    - Test class `TestFeatureVector` with TS-41-13
    - Test class `TestTrainDurationModel` with TS-41-11, TS-41-12
    - Shared fixtures: in-memory DuckDB with `complexity_assessments` and
      `execution_outcomes` tables, helper to insert test outcomes
    - _Test Spec: TS-41-5, TS-41-6, TS-41-7, TS-41-8, TS-41-10, TS-41-11,
      TS-41-12, TS-41-13, TS-41-14, TS-41-15_

  - [x] 1.2 Create `tests/unit/routing/test_duration_presets.py`
    - Test class `TestDurationPresets` with TS-41-9
    - _Test Spec: TS-41-9_

  - [x] 1.3 Create `tests/unit/engine/test_duration_ordering.py`
    - Test class `TestOrderByDuration` with TS-41-1, TS-41-2, TS-41-3
    - Test class `TestReadyTasksOrdering` with TS-41-4, TS-41-18
    - Test class `TestPlanningConfig` with TS-41-16, TS-41-17
    - _Test Spec: TS-41-1, TS-41-2, TS-41-3, TS-41-4, TS-41-16, TS-41-17,
      TS-41-18_

  - [x] 1.4 Create edge case tests
    - In `tests/unit/routing/test_duration.py`: add `TestEdgeCases` class
      with TS-41-E1, TS-41-E2, TS-41-E3, TS-41-E4, TS-41-E5, TS-41-E8
    - In `tests/unit/engine/test_duration_ordering.py`: add
      `TestConfigClamping` class with TS-41-E6, TS-41-E7
    - _Test Spec: TS-41-E1, TS-41-E2, TS-41-E3, TS-41-E4, TS-41-E5,
      TS-41-E6, TS-41-E7, TS-41-E8_

  - [x] 1.5 Create `tests/property/routing/test_duration_props.py`
    - Property tests TS-41-P1 through TS-41-P6
    - Use Hypothesis strategies for node ID lists, duration hint dicts,
      feature vector dicts
    - _Test Spec: TS-41-P1, TS-41-P2, TS-41-P3, TS-41-P4, TS-41-P5,
      TS-41-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests PASS (green) -- implementation already exists from spec 39
    - [x] No linter warnings introduced
    - [x] `make lint` passes

- [x] 2. Implement duration hints, presets, and ordering
  - [x] 2.1 Validate and harden `agent_fox/routing/duration_presets.py`
    - Verify `DURATION_PRESETS` covers all 6 archetypes x 3 tiers
    - Verify `DEFAULT_DURATION_MS` is 300,000
    - Add any missing archetype/tier combinations
    - _Requirements: 41-REQ-3.1, 41-REQ-3.2, 41-REQ-3.3, 41-REQ-3.4_

  - [x] 2.2 Validate and harden `agent_fox/routing/duration.py` core functions
    - Verify `DurationHint` dataclass fields (node_id, predicted_ms, source)
    - Verify `get_duration_hint()` source precedence chain
    - Verify `_get_historical_median()` median computation (odd/even)
    - Verify `_feature_vector_to_array()` JSON parsing and field extraction
    - Verify `order_by_duration()` sort logic (descending, tie-breaking)
    - _Requirements: 41-REQ-1.1, 41-REQ-1.2, 41-REQ-1.3, 41-REQ-2.1,
      41-REQ-2.2, 41-REQ-2.3, 41-REQ-3.2, 41-REQ-3.3_

  - [x] 2.3 Validate `agent_fox/engine/graph_sync.py` integration
    - Verify `ready_tasks()` accepts `duration_hints` parameter
    - Verify delegation to `order_by_duration()` when hints provided
    - Verify alphabetical fallback when hints is None or empty
    - _Requirements: 41-REQ-1.1, 41-REQ-1.4, 41-REQ-1.E2_

  - [x] 2.4 Validate `agent_fox/core/config.py` PlanningConfig
    - Verify `duration_ordering`, `min_outcomes_for_historical`,
      `min_outcomes_for_regression` fields with correct defaults
    - Verify clamping validators for numeric fields
    - _Requirements: 41-REQ-5.1, 41-REQ-5.E1_

  - [x] 2.V Verify task group 2
    - [x] Tests from TS-41-1 through TS-41-10, TS-41-16 pass
    - [x] Edge case tests TS-41-E2, TS-41-E3, TS-41-E5, TS-41-E6, TS-41-E7 pass
    - [x] Property tests TS-41-P1, TS-41-P2, TS-41-P3, TS-41-P5, TS-41-P6 pass
    - [x] `make check` passes

- [ ] 3. Implement regression model and orchestrator integration
  - [ ] 3.1 Validate and harden `train_duration_model()` in `agent_fox/routing/duration.py`
    - Verify training with sufficient outcomes returns LinearRegression
    - Verify None returned with insufficient outcomes
    - Verify feature vector extraction from execution_outcomes
    - Verify scikit-learn import guard
    - _Requirements: 41-REQ-4.1, 41-REQ-4.2, 41-REQ-4.3, 41-REQ-4.E2_

  - [ ] 3.2 Validate regression prediction in `get_duration_hint()`
    - Verify regression predictions take precedence over all other sources
    - Verify prediction clamping to minimum 1 ms
    - Verify fallthrough on predict() failure
    - Verify fallthrough on missing feature vector
    - _Requirements: 41-REQ-4.4, 41-REQ-4.5, 41-REQ-4.E1, 41-REQ-4.E3_

  - [ ] 3.3 Validate orchestrator integration in `agent_fox/engine/engine.py`
    - Verify `_compute_duration_hints()` respects `duration_ordering` config
    - Verify hints are computed for all pending nodes
    - Verify pipeline/DB unavailability returns None
    - Verify exception handling returns None with warning
    - _Requirements: 41-REQ-5.2, 41-REQ-5.3, 41-REQ-5.4, 41-REQ-5.E2_

  - [ ] 3.V Verify task group 3
    - [ ] All remaining tests pass: TS-41-11 through TS-41-18
    - [ ] Edge case tests TS-41-E1, TS-41-E4, TS-41-E8 pass
    - [ ] Property test TS-41-P4 passes
    - [ ] All spec tests pass (full suite)
    - [ ] `make check` passes
    - [ ] No regressions in existing test suite
