# Implementation Plan: Adaptive Model Routing

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation follows a bottom-up approach: data types and storage first,
then the core escalation ladder, then the assessment pipeline, then calibration,
and finally orchestrator integration. Each layer is independently testable.

The new `agent_fox/routing/` package contains all adaptive routing logic.
Modifications to existing modules (`config.py`, `engine.py`,
`session_lifecycle.py`) are isolated to the final integration group.

## Test Commands

- Spec tests: `uv run pytest tests/test_routing/ -q`
- Unit tests: `uv run pytest tests/test_routing/ -q -m "not integration"`
- Property tests: `uv run pytest tests/test_routing/ -q -m property`
- Integration tests: `uv run pytest tests/test_routing/ -q -m integration`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/ && uv run ruff format --check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/test_routing/` package with `__init__.py`
    - Create `tests/test_routing/test_features.py` for feature extraction tests
    - Create `tests/test_routing/test_escalation.py` for escalation ladder tests
    - Create `tests/test_routing/test_storage.py` for DuckDB storage tests
    - Create `tests/test_routing/test_assessor.py` for assessment pipeline tests
    - Create `tests/test_routing/test_calibration.py` for calibration tests
    - Create `tests/test_routing/test_config.py` for routing config tests
    - Create `tests/test_routing/test_integration.py` for orchestrator integration tests
    - Create `tests/test_routing/conftest.py` with shared fixtures (temp spec dirs, DuckDB instances)
    - _Test Spec: TS-30-1 through TS-30-29, TS-30-P1 through TS-30-P9, TS-30-E1 through TS-30-E11_

  - [x] 1.2 Translate acceptance-criterion tests from test_spec.md
    - One test function per TS-30-{N} entry (TS-30-1 through TS-30-29)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-30-1 through TS-30-29_

  - [x] 1.3 Translate edge-case tests from test_spec.md
    - One test function per TS-30-E{N} entry (TS-30-E1 through TS-30-E11)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-30-E1 through TS-30-E11_

  - [x] 1.4 Translate property tests from test_spec.md
    - One property test per TS-30-P{N} entry (TS-30-P1 through TS-30-P9)
    - Use Hypothesis strategies for tier enums, config ranges, feature vectors
    - _Test Spec: TS-30-P1 through TS-30-P9_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/test_routing/`

- [x] 2. Implement data types, configuration, and DuckDB schema
  - [x] 2.1 Create routing package and data types
    - Create `agent_fox/routing/__init__.py`
    - Create `agent_fox/routing/types.py`: `FeatureVector`, `ComplexityAssessment`,
      `ExecutionOutcome` frozen dataclasses
    - _Requirements: 1.1, 1.2, 3.1_

  - [x] 2.2 Add RoutingConfig to config system
    - Add `RoutingConfig` pydantic model to `agent_fox/core/config.py` with
      `retries_before_escalation`, `training_threshold`, `accuracy_threshold`,
      `retrain_interval` fields with clamping validators
    - Add `routing: RoutingConfig` field to `AgentFoxConfig`
    - _Requirements: 5.1, 5.2, 5.E1, 5.E2_

  - [x] 2.3 Add DuckDB migration for new tables
    - Add migration to `agent_fox/knowledge/migrations.py` creating
      `complexity_assessments` and `execution_outcomes` tables
    - Use `CREATE TABLE IF NOT EXISTS` for idempotency
    - _Requirements: 6.1, 6.2, 6.3, 6.E1_

  - [x] 2.4 Implement storage CRUD
    - Create `agent_fox/routing/storage.py`: `persist_assessment()`,
      `persist_outcome()`, `query_outcomes()`, `count_outcomes()` functions
    - All operations are best-effort (catch and log on DB errors)
    - _Requirements: 1.6, 3.1, 3.2, 3.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest tests/test_routing/test_config.py tests/test_routing/test_storage.py -q`
    - [x] Property test TS-30-P9 passes: `uv run pytest tests/test_routing/ -q -k "test_p9"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/routing/ agent_fox/core/config.py`
    - [x] Requirements 5.1, 5.2, 5.E1, 5.E2, 6.1, 6.2, 6.3, 6.E1 acceptance criteria met

- [x] 3. Implement escalation ladder and feature extraction
  - [x] 3.1 Implement escalation ladder
    - Create `agent_fox/routing/escalation.py`: `EscalationLadder` class with
      `current_tier`, `is_exhausted`, `attempt_count`, `escalation_count`
      properties and `record_failure()`, `should_retry()` methods
    - Tier ordering: SIMPLE (0) < STANDARD (1) < ADVANCED (2)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.E1, 2.E2_

  - [x] 3.2 Implement feature extraction
    - Create `agent_fox/routing/features.py`: `extract_features()` function
    - Parse `tasks.md` for subtask count (for the specific task group)
    - Count words across spec files (requirements.md, design.md)
    - Detect property test presence in test_spec.md
    - Count edge cases in requirements.md
    - Count dependencies from prd.md dependency table
    - Return default values on any parse error
    - _Requirements: 1.2, 1.E3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest tests/test_routing/test_escalation.py tests/test_routing/test_features.py -q`
    - [x] Property tests TS-30-P1, P2, P3, P5 pass: `uv run pytest tests/test_routing/ -q -k "test_p1 or test_p2 or test_p3 or test_p5"`
    - [x] Edge case tests TS-30-E3, E4, E5 pass: `uv run pytest tests/test_routing/ -q -k "test_e3 or test_e4 or test_e5"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/routing/`
    - [x] Requirements 2.1-2.4, 2.E1, 2.E2, 1.2, 1.E3 acceptance criteria met

- [x] 4. Checkpoint — Core Components Complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify escalation ladder, feature extraction, storage, and config are solid.

- [x] 5. Implement assessment pipeline
  - [x] 5.1 Implement heuristic assessor
    - Create `agent_fox/routing/assessor.py`: `heuristic_assess()` function
    - Rules: SIMPLE if subtask_count <= 3 AND word_count < 500 AND no property tests;
      ADVANCED if subtask_count >= 6 OR dependency_count >= 3 OR has_property_tests;
      STANDARD otherwise
    - Fixed confidence = 0.6
    - _Requirements: 1.3_

  - [x] 5.2 Implement LLM assessor
    - Add `llm_assess()` async function to `assessor.py`
    - Build structured prompt with spec content summary and feature vector
    - Parse LLM response for tier prediction and confidence
    - Use SIMPLE tier model for cost efficiency
    - Handle timeout/API errors gracefully (return None on failure)
    - _Requirements: 1.5, 1.E1_

  - [x] 5.3 Implement assessment pipeline orchestration
    - Add `AssessmentPipeline` class to `assessor.py`
    - Method selection: count outcomes → choose heuristic/statistical/hybrid
    - Execute selected assessor(s), merge results
    - Persist assessment via storage module
    - Wrap entire pipeline in try/except for graceful degradation
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.E1, 1.E2_

  - [x] 5.V Verify task group 5
    - [x] Spec tests for this group pass: `uv run pytest tests/test_routing/test_assessor.py -q`
    - [x] Property tests TS-30-P6, P7 pass: `uv run pytest tests/test_routing/ -q -k "test_p6 or test_p7"`
    - [x] Edge case tests TS-30-E1, E2 pass: `uv run pytest tests/test_routing/ -q -k "test_e1 or test_e2"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/routing/`
    - [x] Requirements 1.1-1.6, 1.E1, 1.E2 acceptance criteria met

- [ ] 6. Implement statistical model and calibration
  - [ ] 6.1 Implement statistical assessor
    - Create `agent_fox/routing/calibration.py`: `StatisticalAssessor` class
    - `is_ready()`: check outcome count vs training threshold
    - `train()`: load feature vectors + outcomes from DuckDB, fit logistic
      regression (scikit-learn), compute cross-validated accuracy, return accuracy
    - `predict()`: transform feature vector, predict tier with probability
    - Handle training failures (zero variance, numerical errors) gracefully
    - _Requirements: 4.1, 4.2, 4.3, 4.E1_

  - [ ] 6.2 Implement retraining and accuracy tracking
    - Add retraining trigger: retrain after every N new outcomes
    - Track last training outcome count to detect when retrain is needed
    - On accuracy degradation below threshold: log warning, flag for hybrid
    - _Requirements: 4.4, 4.5, 4.E2_

  - [ ] 6.3 Add scikit-learn dependency
    - Add `scikit-learn` to project dependencies in `pyproject.toml`
    - _Requirements: 4.1_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests for this group pass: `uv run pytest tests/test_routing/test_calibration.py -q`
    - [ ] Edge case tests TS-30-E7, E8 pass: `uv run pytest tests/test_routing/ -q -k "test_e7 or test_e8"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/routing/`
    - [ ] Requirements 4.1-4.5, 4.E1, 4.E2 acceptance criteria met

- [ ] 7. Integrate with orchestrator and session lifecycle
  - [ ] 7.1 Modify NodeSessionRunner to accept assessed tier
    - Replace `_resolve_model_tier()` static resolution with assessed tier parameter
    - Accept `assessed_tier: ModelTier | None` in constructor; if None, fall back
      to archetype default (backward compat during integration)
    - Add `resolve_tier_ceiling()` helper: config override → archetype default
    - _Requirements: 7.2, 5.3_

  - [ ] 7.2 Modify orchestrator engine loop
    - Replace simple retry logic with escalation ladder
    - Before dispatch: run assessment pipeline, create escalation ladder
    - On failure: call `ladder.record_failure()`, check `should_retry()`
    - On escalation: create new session runner with `ladder.current_tier`
    - Accumulate costs from all attempts for circuit breaker
    - Record execution outcome after task completion/failure
    - _Requirements: 7.1, 7.3, 7.4, 2.5, 3.1, 3.3_

  - [ ] 7.3 Add graceful degradation wrapper
    - Wrap assessment pipeline call in try/except in orchestrator
    - On any exception: fall back to archetype default tier, log error
    - _Requirements: 7.E1_

  - [ ] 7.4 Handle max_retries deprecation
    - If `orchestrator.max_retries` is set and `routing.retries_before_escalation`
      is at default: use `max_retries` as fallback with deprecation warning
    - If both are set: `routing.retries_before_escalation` takes precedence
    - _Requirements: 5.1_

  - [ ] 7.V Verify task group 7
    - [ ] Spec tests for this group pass: `uv run pytest tests/test_routing/test_integration.py -q`
    - [ ] Property tests TS-30-P4, P8 pass: `uv run pytest tests/test_routing/ -q -k "test_p4 or test_p8"`
    - [ ] Edge case tests TS-30-E6, E9, E10, E11 pass: `uv run pytest tests/test_routing/ -q -k "test_e6 or test_e9 or test_e10 or test_e11"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 7.1-7.4, 7.E1, 2.5, 3.1, 3.3, 5.3 acceptance criteria met

- [ ] 8. Checkpoint — Full Integration Complete
  - All spec tests pass: `uv run pytest tests/test_routing/ -q`
  - All property tests pass: `uv run pytest tests/test_routing/ -q -m property`
  - Full test suite passes: `uv run pytest -q`
  - Full lint passes: `uv run ruff check agent_fox/ tests/ && uv run ruff format --check agent_fox/ tests/`
  - Update documentation: README.md (adaptive routing section), docs/adr/ (new ADR)

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
| 30-REQ-1.1 | TS-30-2 | 5.3 | `test_assessor.py::test_assessment_production` |
| 30-REQ-1.2 | TS-30-1 | 3.2 | `test_features.py::test_feature_extraction` |
| 30-REQ-1.3 | TS-30-3 | 5.3 | `test_assessor.py::test_heuristic_on_zero_history` |
| 30-REQ-1.4 | TS-30-4 | 5.3 | `test_assessor.py::test_statistical_preferred` |
| 30-REQ-1.5 | TS-30-5 | 5.3 | `test_assessor.py::test_hybrid_assessment` |
| 30-REQ-1.6 | TS-30-6 | 5.3 | `test_assessor.py::test_assessment_persisted` |
| 30-REQ-1.E1 | TS-30-E1 | 5.2 | `test_assessor.py::test_llm_failure_fallback` |
| 30-REQ-1.E2 | TS-30-E2 | 5.3 | `test_assessor.py::test_no_db_assessment` |
| 30-REQ-1.E3 | TS-30-E3 | 3.2 | `test_features.py::test_bad_spec_dir` |
| 30-REQ-2.1 | TS-30-7 | 3.1 | `test_escalation.py::test_same_tier_retry` |
| 30-REQ-2.2 | TS-30-8 | 3.1 | `test_escalation.py::test_escalation_to_next` |
| 30-REQ-2.3 | TS-30-9 | 3.1 | `test_escalation.py::test_exhaustion` |
| 30-REQ-2.4 | TS-30-10 | 3.1 | `test_escalation.py::test_ceiling_enforcement` |
| 30-REQ-2.5 | TS-30-11 | 7.2 | `test_integration.py::test_cost_in_circuit_breaker` |
| 30-REQ-2.E1 | TS-30-E4 | 3.1 | `test_escalation.py::test_no_escalation_from_advanced` |
| 30-REQ-2.E2 | TS-30-E5 | 3.1 | `test_escalation.py::test_no_escalation_ceiling_simple` |
| 30-REQ-3.1 | TS-30-12 | 2.4 | `test_storage.py::test_outcome_recorded` |
| 30-REQ-3.2 | TS-30-13 | 2.4 | `test_storage.py::test_outcome_linked` |
| 30-REQ-3.3 | TS-30-14 | 7.2 | `test_escalation.py::test_actual_tier_reflects_escalation` |
| 30-REQ-3.E1 | TS-30-E6 | 2.4 | `test_storage.py::test_db_failure_on_outcome` |
| 30-REQ-4.1 | TS-30-15 | 6.1 | `test_calibration.py::test_training_trigger` |
| 30-REQ-4.2 | TS-30-16 | 6.1 | `test_calibration.py::test_cross_validation` |
| 30-REQ-4.3 | TS-30-17 | 6.1 | `test_calibration.py::test_statistical_primary` |
| 30-REQ-4.4 | TS-30-18 | 6.2 | `test_calibration.py::test_hybrid_divergence` |
| 30-REQ-4.5 | TS-30-19 | 6.2 | `test_calibration.py::test_retraining_trigger` |
| 30-REQ-4.E1 | TS-30-E7 | 6.1 | `test_calibration.py::test_training_failure` |
| 30-REQ-4.E2 | TS-30-E8 | 6.2 | `test_calibration.py::test_accuracy_degradation` |
| 30-REQ-5.1 | TS-30-20 | 2.2 | `test_config.py::test_routing_defaults` |
| 30-REQ-5.2 | TS-30-21 | 2.2 | `test_config.py::test_routing_clamping` |
| 30-REQ-5.3 | TS-30-22 | 7.1 | `test_config.py::test_archetype_ceiling` |
| 30-REQ-5.E1 | TS-30-20 | 2.2 | `test_config.py::test_routing_defaults` |
| 30-REQ-5.E2 | TS-30-E9 | 2.2 | `test_config.py::test_invalid_routing_type` |
| 30-REQ-6.1 | TS-30-23 | 2.3 | `test_storage.py::test_assessment_table_schema` |
| 30-REQ-6.2 | TS-30-24 | 2.3 | `test_storage.py::test_outcome_table_schema` |
| 30-REQ-6.3 | TS-30-25 | 2.3 | `test_storage.py::test_migration` |
| 30-REQ-6.E1 | TS-30-E10 | 2.3 | `test_storage.py::test_migration_idempotency` |
| 30-REQ-7.1 | TS-30-26 | 7.2 | `test_integration.py::test_assessment_before_session` |
| 30-REQ-7.2 | TS-30-27 | 7.1 | `test_integration.py::test_static_resolution_replaced` |
| 30-REQ-7.3 | TS-30-28 | 7.2 | `test_integration.py::test_escalation_ladder_in_orchestrator` |
| 30-REQ-7.4 | TS-30-29 | 7.2 | `test_integration.py::test_outcome_recorded_after_completion` |
| 30-REQ-7.E1 | TS-30-E11 | 7.3 | `test_integration.py::test_assessment_failure_fallback` |
| Property 1 | TS-30-P1 | 3.1 | `test_escalation.py::test_p1_order_preservation` |
| Property 2 | TS-30-P2 | 3.1 | `test_escalation.py::test_p2_ceiling_enforcement` |
| Property 3 | TS-30-P3 | 3.1 | `test_escalation.py::test_p3_retry_budget` |
| Property 4 | TS-30-P4 | 7.2 | `test_integration.py::test_p4_persistence_completeness` |
| Property 5 | TS-30-P5 | 3.2 | `test_features.py::test_p5_determinism` |
| Property 6 | TS-30-P6 | 5.3 | `test_assessor.py::test_p6_method_selection` |
| Property 7 | TS-30-P7 | 5.3 | `test_assessor.py::test_p7_graceful_degradation` |
| Property 8 | TS-30-P8 | 7.2 | `test_integration.py::test_p8_cost_accounting` |
| Property 9 | TS-30-P9 | 2.2 | `test_config.py::test_p9_config_clamping` |

## Notes

- **scikit-learn**: Added as a runtime dependency. It is lightweight (~30MB)
  and has no GPU requirement. The logistic regression model trains in
  milliseconds on the expected data volumes (<1000 rows).
- **Testing strategy**: Property tests use Hypothesis with custom strategies
  for ModelTier (sampled_from), FeatureVector (builds), and config values
  (integers/floats in relevant ranges). Integration tests use in-memory
  DuckDB instances.
- **Backward compatibility**: The `max_retries` config field is deprecated
  but still read as a fallback. Existing config.toml files continue to work.
