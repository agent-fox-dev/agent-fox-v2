# Implementation Plan: Post-Session Quality Gate & Complexity Enrichment

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Two independent capabilities: a configurable post-session quality gate and
four new feature vector fields. These can be implemented in parallel since
they share no code paths. The quality gate integrates into
`session_lifecycle.py`; the feature vector extends `routing/core.py` and
`routing/features.py`.

Implementation order:
1. Write failing tests.
2. Implement the quality gate.
3. Extend the feature vector and heuristic assessor.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_quality_gate.py tests/unit/routing/test_feature_enrichment.py tests/integration/test_quality_gate.py -v`
- Unit tests: `make test-unit`
- Property tests: `make test-property`
- All tests: `make test`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit tests for quality gate
    - Create `tests/unit/engine/test_quality_gate.py`
    - Tests for TS-54-1, TS-54-2, TS-54-3, TS-54-4, TS-54-5 (run, skip, timeout, audit, status)
    - Tests for TS-54-E1 (command not found)
    - _Test Spec: TS-54-1, TS-54-2, TS-54-3, TS-54-4, TS-54-5, TS-54-E1_

  - [x] 1.2 Create unit tests for feature enrichment
    - Create `tests/unit/routing/test_feature_enrichment.py`
    - Tests for TS-54-7, TS-54-8, TS-54-9, TS-54-10, TS-54-12, TS-54-13 (features + heuristic)
    - Tests for TS-54-E2, TS-54-E3, TS-54-E4, TS-54-E5, TS-54-E6 (edge cases)
    - _Test Spec: TS-54-7, TS-54-8, TS-54-9, TS-54-10, TS-54-12, TS-54-13, TS-54-E2, TS-54-E3, TS-54-E4, TS-54-E5, TS-54-E6_

  - [x] 1.3 Create integration tests
    - Create `tests/integration/test_quality_gate.py`
    - Tests for TS-54-6, TS-54-11 (gate doesn't block, historical median)
    - _Test Spec: TS-54-6, TS-54-11_

  - [x] 1.4 Create property tests
    - Create `tests/property/routing/test_feature_enrichment_props.py`
    - Tests for TS-54-P1 through TS-54-P8
    - _Test Spec: TS-54-P1, TS-54-P2, TS-54-P3, TS-54-P4, TS-54-P5, TS-54-P6, TS-54-P7, TS-54-P8_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Quality gate implementation
  - [x] 2.1 Add config fields to `OrchestratorConfig`
    - `quality_gate: str = Field(default="", ...)`
    - `quality_gate_timeout: int = Field(default=300, ...)`
    - In `core/config.py`
    - _Requirements: 54-REQ-1.1, 54-REQ-1.2, 54-REQ-1.3_

  - [x] 2.2 Add `QualityGateResult` dataclass
    - In `engine/session_lifecycle.py` or new module
    - Fields: exit_code, stdout_tail, stderr_tail, duration_ms, passed
    - _Requirements: 54-REQ-2.1_

  - [x] 2.3 Implement `_run_quality_gate()` in `SessionLifecycle`
    - Execute command via `subprocess.run` with timeout
    - Handle `TimeoutExpired` (SIGTERM → SIGKILL, exit_code=-1)
    - Handle `FileNotFoundError` (exit_code=-2)
    - Capture last 50 lines of stdout/stderr
    - _Requirements: 54-REQ-1.1, 54-REQ-1.2, 54-REQ-1.E1, 54-REQ-1.E2_

  - [x] 2.4 Add `QUALITY_GATE_RESULT` to `AuditEventType`
    - New enum member: `QUALITY_GATE_RESULT = "quality_gate.result"`
    - Emit after gate execution with result payload
    - _Requirements: 54-REQ-2.1, 54-REQ-2.E1_

  - [x] 2.5 Wire quality gate into session lifecycle
    - Call `_run_quality_gate()` after successful coder sessions
    - Set status to `completed_with_gate_failure` on failure
    - Ensure failure does not block next session
    - _Requirements: 54-REQ-2.2, 54-REQ-2.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_quality_gate.py tests/integration/test_quality_gate.py -v`
    - [x] TS-54-1 through TS-54-6, TS-54-E1 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 54-REQ-1.x, 54-REQ-2.x met

- [x] 3. Feature vector enrichment
  - [x] 3.1 Extend `FeatureVector` in `routing/core.py`
    - Add `file_count_estimate: int = 0`
    - Add `cross_spec_integration: bool = False`
    - Add `language_count: int = 1`
    - Add `historical_median_duration_ms: int | None = None`
    - _Requirements: 54-REQ-3.1, 54-REQ-4.1, 54-REQ-5.1, 54-REQ-6.1_

  - [x] 3.2 Add extraction helpers in `routing/features.py`
    - `_count_file_paths(spec_dir, task_group) -> int`
    - `_detect_cross_spec(spec_dir, task_group, own_spec) -> bool`
    - `_count_languages(spec_dir, task_group) -> int`
    - `_get_historical_median_duration(conn, spec_name) -> int | None`
    - _Requirements: 54-REQ-3.1, 54-REQ-4.1, 54-REQ-5.1, 54-REQ-6.1_

  - [x] 3.3 Update `extract_features()` signature and body
    - Add `conn` and `spec_name` keyword arguments
    - Call new helpers and populate new FeatureVector fields
    - _Requirements: 54-REQ-3.1, 54-REQ-4.1, 54-REQ-5.1, 54-REQ-6.1_

  - [x] 3.4 Update heuristic assessor thresholds
    - ADVANCED when `cross_spec_integration=True` OR `file_count_estimate >= 8`
    - Confidence 0.7 for these cases
    - No double-upgrade
    - _Requirements: 54-REQ-7.1, 54-REQ-7.E1_

  - [x] 3.5 Ensure feature vector JSON serialization includes all fields
    - Update `persist_assessment()` to serialize all 10 fields
    - Verify round-trip: serialize → deserialize → same values
    - _Requirements: 54-REQ-7.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/routing/test_feature_enrichment.py tests/integration/test_quality_gate.py -v`
    - [x] TS-54-7 through TS-54-13, TS-54-E2 through TS-54-E6 pass
    - [x] Property tests pass: `uv run pytest -q tests/property/routing/test_feature_enrichment_props.py -v`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 54-REQ-3.x through 54-REQ-7.x met

- [ ] 4. Checkpoint — Quality Gate & Complexity Complete
  - [ ] All spec tests pass
  - [ ] All property tests pass
  - [ ] Full test suite green: `make check`
  - [ ] Review coverage matrix — all requirements have passing tests

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 54-REQ-1.1 | TS-54-1 | 2.1, 2.3, 2.5 | `test_quality_gate.py::test_gate_runs` |
| 54-REQ-1.2 | TS-54-3 | 2.1, 2.3 | `test_quality_gate.py::test_gate_timeout` |
| 54-REQ-1.3 | TS-54-2 | 2.1, 2.5 | `test_quality_gate.py::test_gate_skipped` |
| 54-REQ-1.E1 | TS-54-E1 | 2.3 | `test_quality_gate.py::test_command_not_found` |
| 54-REQ-1.E2 | TS-54-4 | 2.3 | `test_quality_gate.py::test_output_truncation` |
| 54-REQ-2.1 | TS-54-4 | 2.4 | `test_quality_gate.py::test_audit_event` |
| 54-REQ-2.2 | TS-54-5 | 2.5 | `test_quality_gate.py::test_status_downgrade` |
| 54-REQ-2.3 | TS-54-6 | 2.5 | `test_quality_gate.py::test_no_block` |
| 54-REQ-2.E1 | TS-54-4 | 2.4 | `test_quality_gate.py::test_null_sink` |
| 54-REQ-3.1 | TS-54-7 | 3.2, 3.3 | `test_feature_enrichment.py::test_file_count` |
| 54-REQ-3.2 | TS-54-E4 | 3.2 | `test_feature_enrichment.py::test_no_file_paths` |
| 54-REQ-4.1 | TS-54-8 | 3.2, 3.3 | `test_feature_enrichment.py::test_cross_spec_detected` |
| 54-REQ-4.2 | TS-54-9 | 3.2 | `test_feature_enrichment.py::test_own_spec_not_cross` |
| 54-REQ-5.1 | TS-54-10 | 3.2, 3.3 | `test_feature_enrichment.py::test_language_count` |
| 54-REQ-5.2 | TS-54-E5 | 3.2 | `test_feature_enrichment.py::test_language_default` |
| 54-REQ-6.1 | TS-54-11 | 3.2, 3.3 | `test_quality_gate.py::test_historical_median` |
| 54-REQ-6.2 | TS-54-E2 | 3.2 | `test_feature_enrichment.py::test_no_prior_outcomes` |
| 54-REQ-6.E1 | TS-54-E3 | 3.2 | `test_feature_enrichment.py::test_single_outcome` |
| 54-REQ-7.1 | TS-54-12 | 3.4 | `test_feature_enrichment.py::test_heuristic_advanced` |
| 54-REQ-7.2 | TS-54-13 | 3.5 | `test_feature_enrichment.py::test_json_serialization` |
| 54-REQ-7.E1 | TS-54-E6 | 3.4 | `test_feature_enrichment.py::test_no_double_upgrade` |

## Notes

- Quality gate uses `subprocess.run` with `shell=True` since the command is
  a user-configured string. The security module's `validate_command()` should
  be consulted to ensure the command passes allowlist checks if applicable.
- Feature extraction helpers read from `tasks.md` using regex patterns. The
  file path regex `[a-zA-Z_/]+\.\w{1,5}` may produce false positives for
  prose like "e.g." — consider adding an exclusion list for common
  abbreviations.
- Historical median query requires a DuckDB connection. When no connection is
  available (e.g. in tests without DB), the field defaults to None.
- The `FeatureVector` dataclass is frozen, so new fields must have defaults
  to maintain backward compatibility with existing construction sites.
