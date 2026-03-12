# Implementation Plan: Project Model

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in five groups: (1) write failing tests for all four
components, (2) implement project model aggregation, (3) implement critical
path computation, (4) implement file conflict detection, (5) implement
learned blocking thresholds.

The implementation code already exists in `agent_fox/knowledge/project_model.py`,
`agent_fox/graph/critical_path.py`, `agent_fox/graph/file_impacts.py`, and
`agent_fox/knowledge/blocking_history.py` from prior spec 39 work. Task
groups 2-5 verify existing implementations against the new test contracts,
fix any gaps, and wire integrations (CLI status, engine dispatch, convergence
thresholds).

## Dependencies

| Spec | Required Task Group | Relationship |
|------|---------------------|--------------|
| 38 (DuckDB Hardening) | All groups complete | DuckDB connections are mandatory |
| 39 (Package Consolidation) | All groups complete | Knowledge code location established |
| 41 (Duration Ordering) | All groups complete | Duration hints available for critical path |

## Test Commands

- Spec tests: `uv run pytest tests/unit/knowledge/test_project_model.py tests/unit/graph/test_critical_path.py tests/unit/graph/test_file_impacts.py tests/unit/knowledge/test_blocking_history.py -v`
- Property tests: `uv run pytest tests/property/knowledge/test_project_model_props.py tests/property/graph/test_critical_path_props.py tests/property/graph/test_file_impacts_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create `tests/unit/knowledge/test_project_model.py`
    - Test class `TestBuildProjectModel` with TS-43-1, TS-43-2, TS-43-3
    - Test class `TestFormatProjectModel` with TS-43-4
    - Test class `TestProjectModelEdgeCases` with TS-43-E1, TS-43-E2
    - _Test Spec: TS-43-1, TS-43-2, TS-43-3, TS-43-4, TS-43-E1, TS-43-E2_

  - [ ] 1.2 Create `tests/unit/graph/test_critical_path.py`
    - Test class `TestComputeCriticalPath` with TS-43-5, TS-43-6
    - Test class `TestFormatCriticalPath` with TS-43-7
    - Test class `TestCriticalPathEdgeCases` with TS-43-E3, TS-43-E4
    - _Test Spec: TS-43-5, TS-43-6, TS-43-7, TS-43-E3, TS-43-E4_

  - [ ] 1.3 Create `tests/unit/graph/test_file_impacts.py`
    - Test class `TestExtractFileImpacts` with TS-43-8
    - Test class `TestDetectConflicts` with TS-43-9
    - Test class `TestFilterConflicts` with TS-43-10
    - Test class `TestFileImpactEdgeCases` with TS-43-E5, TS-43-E6
    - _Test Spec: TS-43-8, TS-43-9, TS-43-10, TS-43-E5, TS-43-E6_

  - [ ] 1.4 Create `tests/unit/knowledge/test_blocking_history.py`
    - Test class `TestRecordBlockingDecision` with TS-43-11
    - Test class `TestComputeOptimalThreshold` with TS-43-12, TS-43-13
    - Test class `TestStoreAndRetrieveThreshold` with TS-43-14
    - Test class `TestFormatThresholds` with TS-43-15
    - Test class `TestBlockingEdgeCases` with TS-43-E7, TS-43-E8
    - _Test Spec: TS-43-11, TS-43-12, TS-43-13, TS-43-14, TS-43-15, TS-43-E7, TS-43-E8_

  - [ ] 1.5 Create `tests/property/knowledge/test_project_model_props.py`
    - Property test TS-43-P1 (failure rate bounds)
    - _Test Spec: TS-43-P1_

  - [ ] 1.6 Create `tests/property/graph/test_critical_path_props.py`
    - Property test TS-43-P2 (critical path determinism)
    - Property test TS-43-P5 (critical path duration optimality)
    - _Test Spec: TS-43-P2, TS-43-P5_

  - [ ] 1.7 Create `tests/property/graph/test_file_impacts_props.py`
    - Property test TS-43-P3 (conflict symmetry)
    - Property test TS-43-P4 (dispatch safety)
    - _Test Spec: TS-43-P3, TS-43-P4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings: `uv run ruff check tests/unit/knowledge/test_project_model.py tests/unit/graph/test_critical_path.py tests/unit/graph/test_file_impacts.py tests/unit/knowledge/test_blocking_history.py tests/property/knowledge/test_project_model_props.py tests/property/graph/test_critical_path_props.py tests/property/graph/test_file_impacts_props.py`
    - [ ] All previously passing tests still pass (no regressions)

- [ ] 2. Project model aggregation
  - [ ] 2.1 Verify `agent_fox/knowledge/project_model.py` implementation
    - Confirm SpecMetrics dataclass with spec_name, avg_cost, avg_duration_ms, failure_rate, session_count
    - Confirm ProjectModel dataclass with spec_outcomes, module_stability, archetype_effectiveness, knowledge_staleness, active_drift_areas
    - Confirm build_project_model() queries execution_outcomes JOIN complexity_assessments
    - Confirm _compute_module_stability() computes finding density
    - Confirm _compute_archetype_effectiveness() extracts archetype from feature_vector JSON
    - Confirm format_project_model() produces human-readable output
    - Fix any gaps found by spec tests
    - _Requirements: 43-REQ-1.1, 43-REQ-1.2, 43-REQ-1.3, 43-REQ-1.4, 43-REQ-1.E1, 43-REQ-1.E2_

  - [ ] 2.2 Wire project model into CLI status output
    - Update `agent_fox/cli/status.py` to call build_project_model() and format_project_model()
    - Add --model flag or always include in status output
    - _Requirements: 43-REQ-1.4_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_project_model.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_project_model_props.py -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/project_model.py agent_fox/cli/status.py`
    - [ ] Requirements 43-REQ-1.* met

- [ ] 3. Critical path computation
  - [ ] 3.1 Verify `agent_fox/graph/critical_path.py` implementation
    - Confirm CriticalPathResult dataclass with path, total_duration_ms, tied_paths
    - Confirm compute_critical_path() uses topological sort + forward pass
    - Confirm tied path detection via backtracking
    - Confirm format_critical_path() produces human-readable output
    - Confirm empty graph returns empty path with duration 0
    - Confirm missing duration hints treated as 0ms
    - Fix any gaps found by spec tests
    - _Requirements: 43-REQ-2.1, 43-REQ-2.2, 43-REQ-2.3, 43-REQ-2.E1, 43-REQ-2.E2, 43-REQ-2.E3_

  - [ ] 3.2 Wire critical path into CLI status output
    - Update `agent_fox/cli/status.py` to compute and display critical path
    - Use duration hints from task graph metadata
    - _Requirements: 43-REQ-2.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/graph/test_critical_path.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/graph/test_critical_path_props.py -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/graph/critical_path.py agent_fox/cli/status.py`
    - [ ] Requirements 43-REQ-2.* met

- [ ] 4. File conflict detection
  - [ ] 4.1 Verify `agent_fox/graph/file_impacts.py` implementation
    - Confirm FileImpact dataclass with node_id, predicted_files
    - Confirm extract_file_impacts() reads tasks.md and design.md
    - Confirm _extract_task_group_section() parses task group boundaries
    - Confirm _extract_file_paths() uses backtick regex
    - Confirm detect_conflicts() reports pairs with lower node_id first
    - Confirm filter_conflicts_from_dispatch() keeps first in conflict, defers rest
    - Fix any gaps found by spec tests
    - _Requirements: 43-REQ-3.1, 43-REQ-3.2, 43-REQ-3.3, 43-REQ-3.E1, 43-REQ-3.E2_

  - [ ] 4.2 Verify config flag in `agent_fox/core/config.py`
    - Confirm PlanningConfig.file_conflict_detection exists and defaults to False
    - _Requirements: 43-REQ-3.4_

  - [ ] 4.3 Wire file conflict detection into engine dispatch
    - Update `agent_fox/engine/engine.py` to call filter_conflicts_from_dispatch()
      when config.planning.file_conflict_detection is True
    - _Requirements: 43-REQ-3.3_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/graph/test_file_impacts.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/graph/test_file_impacts_props.py -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/graph/file_impacts.py agent_fox/core/config.py agent_fox/engine/engine.py`
    - [ ] Requirements 43-REQ-3.* met

- [ ] 5. Learned blocking thresholds
  - [ ] 5.1 Verify `agent_fox/knowledge/blocking_history.py` implementation
    - Confirm BlockingDecision dataclass with spec_name, archetype, critical_count, threshold, blocked, outcome
    - Confirm ensure_blocking_tables() creates blocking_history and learned_thresholds tables
    - Confirm record_blocking_decision() inserts with UUID
    - Confirm compute_optimal_threshold() returns None on insufficient data, int on sufficient
    - Confirm store_learned_threshold() upserts into learned_thresholds
    - Confirm get_learned_threshold() retrieves stored threshold
    - Confirm format_learned_thresholds() produces human-readable output
    - Fix any gaps found by spec tests
    - _Requirements: 43-REQ-4.1, 43-REQ-4.2, 43-REQ-4.3, 43-REQ-4.5, 43-REQ-4.6, 43-REQ-4.7, 43-REQ-4.E1, 43-REQ-4.E2_

  - [ ] 5.2 Verify config flag in `agent_fox/core/config.py`
    - Confirm BlockingConfig.learn_thresholds exists and defaults to False
    - Confirm BlockingConfig.min_decisions_for_learning defaults to 20
    - Confirm BlockingConfig.max_false_negative_rate defaults to 0.1
    - _Requirements: 43-REQ-4.4_

  - [ ] 5.3 Wire learned thresholds into convergence
    - Update `agent_fox/session/convergence.py` to call get_learned_threshold()
      when config.blocking.learn_thresholds is True
    - Fall back to static threshold when learned threshold unavailable
    - _Requirements: 43-REQ-4.4_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_blocking_history.py -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/blocking_history.py agent_fox/core/config.py agent_fox/session/convergence.py`
    - [ ] Requirements 43-REQ-4.* met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 43-REQ-1.1 | TS-43-1 | 2.1 | `test_project_model.py::TestBuildProjectModel::test_spec_outcomes` |
| 43-REQ-1.2 | TS-43-2 | 2.1 | `test_project_model.py::TestBuildProjectModel::test_module_stability` |
| 43-REQ-1.3 | TS-43-3 | 2.1 | `test_project_model.py::TestBuildProjectModel::test_archetype_effectiveness` |
| 43-REQ-1.4 | TS-43-4 | 2.1, 2.2 | `test_project_model.py::TestFormatProjectModel::test_format_output` |
| 43-REQ-1.E1 | TS-43-E1 | 2.1 | `test_project_model.py::TestProjectModelEdgeCases::test_empty_database` |
| 43-REQ-1.E2 | TS-43-E2 | 2.1 | `test_project_model.py::TestProjectModelEdgeCases::test_findings_without_outcomes` |
| 43-REQ-2.1 | TS-43-5 | 3.1 | `test_critical_path.py::TestComputeCriticalPath::test_linear_chain` |
| 43-REQ-2.2 | TS-43-7 | 3.1, 3.2 | `test_critical_path.py::TestFormatCriticalPath::test_format_output` |
| 43-REQ-2.3 | TS-43-6 | 3.1 | `test_critical_path.py::TestComputeCriticalPath::test_tied_paths` |
| 43-REQ-2.E1 | TS-43-E3 | 3.1 | `test_critical_path.py::TestCriticalPathEdgeCases::test_empty_graph` |
| 43-REQ-2.E2 | TS-43-E4 | 3.1 | `test_critical_path.py::TestCriticalPathEdgeCases::test_missing_duration` |
| 43-REQ-3.1 | TS-43-8 | 4.1 | `test_file_impacts.py::TestExtractFileImpacts::test_extract_from_tasks` |
| 43-REQ-3.2 | TS-43-9 | 4.1 | `test_file_impacts.py::TestDetectConflicts::test_overlapping_files` |
| 43-REQ-3.3 | TS-43-10 | 4.1, 4.3 | `test_file_impacts.py::TestFilterConflicts::test_filter_dispatch` |
| 43-REQ-3.4 | -- | 4.2 | config inspection |
| 43-REQ-3.E1 | TS-43-E5 | 4.1 | `test_file_impacts.py::TestFileImpactEdgeCases::test_no_impacts` |
| 43-REQ-3.E2 | TS-43-E6 | 4.1 | `test_file_impacts.py::TestFileImpactEdgeCases::test_missing_files` |
| 43-REQ-4.1 | TS-43-11 | 5.1 | `test_blocking_history.py::TestRecordBlockingDecision::test_record` |
| 43-REQ-4.2 | TS-43-12 | 5.1 | `test_blocking_history.py::TestComputeOptimalThreshold::test_sufficient_data` |
| 43-REQ-4.3 | TS-43-13 | 5.1 | `test_blocking_history.py::TestComputeOptimalThreshold::test_insufficient_data` |
| 43-REQ-4.4 | -- | 5.2 | config inspection |
| 43-REQ-4.5 | TS-43-14 | 5.1 | `test_blocking_history.py::TestStoreAndRetrieveThreshold::test_store_and_get` |
| 43-REQ-4.6 | TS-43-14 | 5.1 | `test_blocking_history.py::TestStoreAndRetrieveThreshold::test_store_and_get` |
| 43-REQ-4.7 | TS-43-15 | 5.1 | `test_blocking_history.py::TestFormatThresholds::test_format_output` |
| 43-REQ-4.E1 | TS-43-E7 | 5.1 | `test_blocking_history.py::TestBlockingEdgeCases::test_missing_table` |
| 43-REQ-4.E2 | TS-43-E8 | 5.1 | `test_blocking_history.py::TestBlockingEdgeCases::test_uniform_outcomes` |
| Property 1 | TS-43-P1 | 2.1 | `test_project_model_props.py` |
| Property 2 | TS-43-P5 | 3.1 | `test_critical_path_props.py` |
| Property 3 | TS-43-P2 | 3.1 | `test_critical_path_props.py` |
| Property 4 | TS-43-P3 | 4.1 | `test_file_impacts_props.py` |
| Property 5 | TS-43-P4 | 4.1 | `test_file_impacts_props.py` |

## Notes

- Implementation code for all four components already exists from spec 39.
  Task groups 2-5 primarily verify existing code against the new test
  contracts and wire integrations.
- The project model queries rely on DuckDB tables created by specs 27
  (review_findings), 30 (execution_outcomes, complexity_assessments), and
  32 (drift_findings). If these tables do not exist, the corresponding
  sub-components return empty results gracefully.
- File conflict detection is behind `planning.file_conflict_detection` config
  flag (default: off). When off, the engine dispatches all ready tasks
  without conflict checking.
- Learned thresholds are behind `blocking.learn_thresholds` config flag
  (default: off). When off, the convergence module uses static thresholds.
