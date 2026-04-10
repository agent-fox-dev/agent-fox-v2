# Implementation Plan: Simplify Model Routing

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a **removal** spec. Most task groups delete code and verify the
deletions. The order is: write tests first, then delete source modules, then
simplify integration points, then clean up tests and config, then archive
superseded specs, and finally verify wiring end-to-end.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/routing/test_simplify_routing.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file `tests/unit/routing/test_simplify_routing.py`
    - Tests for TS-89-1 through TS-89-13, TS-89-E1
    - Tests for TS-89-P1 through TS-89-P5
    - All tests MUST fail initially (assert against not-yet-simplified behavior)
    - _Test Spec: TS-89-1 through TS-89-13, TS-89-E1, TS-89-P1 through TS-89-P5_

  - [x] 1.2 Create smoke test `tests/integration/test_routing_simplified_smoke.py`
    - TS-89-SMOKE-1: orchestrator dispatch creates ladder without pipeline
    - _Test Spec: TS-89-SMOKE-1_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Delete prediction pipeline source modules
  - [x] 2.1 Delete `agent_fox/routing/assessor.py`
    - _Requirements: 89-REQ-2.1_

  - [x] 2.2 Delete `agent_fox/routing/features.py`
    - _Requirements: 89-REQ-2.1_

  - [x] 2.3 Delete `agent_fox/routing/calibration.py`
    - _Requirements: 89-REQ-2.1_

  - [x] 2.4 Delete `agent_fox/routing/duration.py`
    - _Requirements: 89-REQ-2.1_

  - [x] 2.5 Gut `agent_fox/routing/core.py`
    - Remove functions: `_feature_vector_to_json`, `persist_assessment`, `persist_outcome`, `count_outcomes`, `query_outcomes`
    - Remove DuckDB imports
    - Keep dataclasses: `FeatureVector`, `ComplexityAssessment`, `ExecutionOutcome`
    - _Requirements: 89-REQ-2.2, 89-REQ-2.4_

  - [x] 2.V Verify task group 2
    - [x] Spec tests TS-89-4, TS-89-5, TS-89-6 pass
    - [x] No linter warnings: `uv run ruff check agent_fox/routing/`

- [x] 3. Simplify engine integration points
  - [x] 3.1 Simplify `agent_fox/engine/assessment.py`
    - Remove pipeline parameter from `AssessmentManager.__init__`
    - Remove pipeline call and try/except in `assess_node()`
    - Always create ladder from archetype default tier
    - Remove `self.pipeline` and `self.assessments` attributes
    - _Requirements: 89-REQ-1.1, 89-REQ-1.2, 89-REQ-1.3, 89-REQ-1.E1_

  - [x] 3.2 Clean up `agent_fox/engine/result_handler.py`
    - Remove `routing_pipeline` parameter from `__init__`
    - Remove `self._routing_pipeline` attribute
    - Remove `record_node_outcome()` method
    - Remove all code that calls `self._routing_pipeline.record_outcome()`
    - _Requirements: 89-REQ-3.1, 89-REQ-3.2_

  - [x] 3.3 Clean up `agent_fox/engine/run.py`
    - Remove `AssessmentPipeline` import and construction
    - Remove `assessment_pipeline` from infra dict
    - Update orchestrator construction to not pass assessment_pipeline
    - _Requirements: 89-REQ-2.3_

  - [x] 3.4 Remove duration references
    - Remove `get_duration_hint` import/usage from `agent_fox/engine/engine.py`
    - Remove `get_duration_hint` import/usage from `agent_fox/cli/status.py`
    - _Requirements: 89-REQ-6.1_

  - [x] 3.5 Update callers of AssessmentManager and SessionResultHandler
    - Update `Orchestrator.__init__` to not pass `pipeline` to AssessmentManager
    - Update SessionResultHandler construction to not pass `routing_pipeline`
    - Grep for any remaining references to removed modules and fix
    - _Requirements: 89-REQ-2.3, 89-REQ-3.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests TS-89-1 through TS-89-3, TS-89-7 through TS-89-9, TS-89-12, TS-89-E1 pass
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Requirements 89-REQ-1.*, 89-REQ-2.3, 89-REQ-3.*, 89-REQ-6.1 met

- [x] 4. Clean up config and tests
  - [x] 4.1 Remove prediction-only fields from `RoutingConfig`
    - Remove `training_threshold`, `accuracy_threshold`, `retrain_interval`
    - Keep `retries_before_escalation`, `max_timeout_retries`, `timeout_multiplier`, `timeout_ceiling_factor`
    - _Requirements: 89-REQ-4.1, 89-REQ-4.2_

  - [x] 4.2 Delete prediction pipeline test files
    - Delete `tests/test_routing/test_assessor.py`
    - Delete `tests/test_routing/test_features.py`
    - Delete `tests/test_routing/test_calibration.py`
    - Delete `tests/test_routing/test_storage.py`
    - Delete `tests/test_routing/test_integration.py`
    - _Requirements: 89-REQ-5.1_

  - [x] 4.3 Clean up `tests/test_routing/conftest.py` and `tests/test_routing/helpers.py`
    - Remove fixtures and helpers that reference deleted modules
    - If nothing remains, delete the files entirely
    - _Requirements: 89-REQ-5.1_

  - [x] 4.4 Verify retained tests pass
    - Run `uv run pytest -q tests/test_routing/test_escalation.py tests/test_routing/test_config.py`
    - _Requirements: 89-REQ-5.2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests TS-89-10, TS-89-11 pass
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Requirements 89-REQ-4.*, 89-REQ-5.* met

- [x] 5. Archive superseded specs
  - [x] 5.1 Add deprecation banners to `30_adaptive_model_routing` spec files
    - Add `> **SUPERSEDED** by spec 89_simplify_routing.` banner to top of each file
    - _Requirements: 89-REQ-7.1_

  - [x] 5.2 Add deprecation banners to `57_archetype_model_tiers` spec files
    - Add `> **SUPERSEDED** by spec 89_simplify_routing.` banner to top of each file
    - _Requirements: 89-REQ-7.1_

  - [x] 5.V Verify task group 5
    - [x] Deprecation banners present in all files of both specs
    - [x] `make check` passes: `make check`

- [x] 6. Wiring verification
  - [x] 6.1 Trace every execution path from design.md end-to-end
    - For Path 1 (orchestrator dispatch): verify assess_node() creates ladder,
      result_handler uses ladder for retry, no removed module is imported
    - For Path 2 (fix pipeline): verify fix_pipeline creates its own ladder
      (unchanged, but confirm no broken imports)
    - _Requirements: all_

  - [x] 6.2 Verify return values propagate correctly
    - assess_node() stores ladder in self.ladders; confirm engine reads it
    - Confirm no caller of removed functions remains
    - _Requirements: all_

  - [x] 6.3 Run the integration smoke tests
    - `uv run pytest -q tests/integration/test_routing_simplified_smoke.py`
    - _Test Spec: TS-89-SMOKE-1_

  - [x] 6.4 Stub / dead-code audit
    - Grep for: `AssessmentPipeline`, `routing.assessor`, `routing.features`,
      `routing.calibration`, `routing.duration`, `persist_assessment`,
      `persist_outcome`, `record_node_outcome`, `routing_pipeline`
    - Each hit must be resolved or justified
    - _Requirements: all_

  - [x] 6.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live
    - [x] Full suite passes: `make check`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 89-REQ-1.1 | TS-89-1 | 3.1 | test_simplify_routing::test_ladder_from_archetype_default |
| 89-REQ-1.2 | TS-89-2 | 3.1 | test_simplify_routing::test_ladder_ceiling_advanced |
| 89-REQ-1.3 | TS-89-3 | 3.1 | test_simplify_routing::test_ladder_created_without_pipeline |
| 89-REQ-1.E1 | TS-89-E1 | 3.1 | test_simplify_routing::test_unknown_archetype_defaults_to_coder |
| 89-REQ-2.1 | TS-89-4 | 2.1-2.4 | test_simplify_routing::test_pipeline_modules_deleted |
| 89-REQ-2.2 | TS-89-5 | 2.5 | test_simplify_routing::test_duckdb_functions_removed |
| 89-REQ-2.3 | TS-89-7 | 3.3 | test_simplify_routing::test_no_assessment_pipeline_in_run |
| 89-REQ-2.4 | TS-89-6 | 2.5 | test_simplify_routing::test_dataclasses_retained |
| 89-REQ-3.1 | TS-89-8 | 3.2 | test_simplify_routing::test_no_record_node_outcome |
| 89-REQ-3.2 | TS-89-9 | 3.2 | test_simplify_routing::test_no_routing_pipeline_param |
| 89-REQ-4.1 | TS-89-10 | 4.1 | test_simplify_routing::test_prediction_config_fields_removed |
| 89-REQ-4.2 | TS-89-10 | 4.1 | test_simplify_routing::test_retries_config_retained |
| 89-REQ-5.1 | TS-89-11 | 4.2-4.3 | test_simplify_routing::test_pipeline_test_files_deleted |
| 89-REQ-5.2 | TS-89-11 | 4.4 | test_escalation.py, test_config.py (retained) |
| 89-REQ-5.3 | TS-89-SMOKE-1 | 6.V | make check |
| 89-REQ-6.1 | TS-89-12 | 3.4 | test_simplify_routing::test_no_duration_imports |
| 89-REQ-7.1 | TS-89-13 | 5.1-5.2 | test_simplify_routing::test_superseded_specs_have_banners |
| Property 1 | TS-89-P1 | 3.1 | test_simplify_routing::test_prop_archetype_tier_becomes_ladder |
| Property 2 | TS-89-P2 | 2.1-2.4 | test_simplify_routing::test_prop_pipeline_modules_not_importable |
| Property 3 | TS-89-P3 | 2.5, 3.2 | test_simplify_routing::test_prop_no_duckdb_routing_writes |
| Property 4 | TS-89-P4 | (existing) | test_simplify_routing::test_prop_escalation_preserved |
| Property 5 | TS-89-P5 | 3.1 | test_simplify_routing::test_prop_unknown_archetype_fallback |
| Path 1 | TS-89-SMOKE-1 | 6.3 | test_routing_simplified_smoke.py |
