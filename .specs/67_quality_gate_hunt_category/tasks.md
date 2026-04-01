# Implementation Plan: Quality Gate Hunt Category

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds a `QualityGateCategory` hunt category to night-shift
in three groups: tests first, then config changes, then the category
implementation. The config changes come before the category so that the
timeout field is available when the category code is written.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_quality_gate.py tests/property/nightshift/test_quality_gate_props.py`
- Unit tests: `uv run pytest -q tests/unit/nightshift/test_quality_gate.py`
- Property tests: `uv run pytest -q tests/property/nightshift/test_quality_gate_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/nightshift/test_quality_gate.py`
    - Test class `TestStaticPhase` with tests for TS-67-1, TS-67-2
    - Test class `TestAIAnalysis` with tests for TS-67-3, TS-67-4, TS-67-5
    - Test class `TestSeverityMapping` with tests for TS-67-6, TS-67-7, TS-67-8
    - Test class `TestConfiguration` with tests for TS-67-9, TS-67-10
    - Test class `TestRegistration` with test for TS-67-11
    - _Test Spec: TS-67-1 through TS-67-11_

  - [x] 1.2 Create edge case tests in same file
    - Test class `TestEdgeCases` with tests for TS-67-E1 through TS-67-E7
    - _Test Spec: TS-67-E1 through TS-67-E7_

  - [x] 1.3 Create property test file `tests/property/nightshift/test_quality_gate_props.py`
    - Property tests for TS-67-P1 through TS-67-P6
    - Use Hypothesis for input generation
    - _Test Spec: TS-67-P1 through TS-67-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Config extensions and category registration
  - [x] 2.1 Add `quality_gate: bool = True` to `NightShiftCategoryConfig`
    - File: `agent_fox/nightshift/config.py`
    - _Requirements: 67-REQ-5.1_

  - [x] 2.2 Add `quality_gate_timeout: int = 600` to `NightShiftConfig`
    - Add field with `Field(default=600, description=...)`
    - Add to the existing `clamp_interval_minimum` validator or create
      a dedicated validator that clamps to minimum 60
    - File: `agent_fox/nightshift/config.py`
    - _Requirements: 67-REQ-5.2, 67-REQ-5.3_

  - [x] 2.3 Register `QualityGateCategory` in `HuntCategoryRegistry`
    - Add import and instantiation in `_register_builtins()`
    - File: `agent_fox/nightshift/hunt.py`
    - _Requirements: 67-REQ-6.1_

  - [x] 2.4 Export `QualityGateCategory` from categories package
    - Add to `__init__.py` imports and `__all__`
    - File: `agent_fox/nightshift/categories/__init__.py`
    - _Requirements: 67-REQ-6.2_

  - [x] 2.V Verify task group 2
    - [x] Config tests pass: `uv run pytest -q tests/unit/nightshift/test_quality_gate.py::TestConfiguration`
    - [x] Registration test passes: `uv run pytest -q tests/unit/nightshift/test_quality_gate.py::TestRegistration`
    - [x] Timeout clamping property passes: `uv run pytest -q tests/property/nightshift/test_quality_gate_props.py -k "timeout"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 67-REQ-5.1, 67-REQ-5.2, 67-REQ-5.3, 67-REQ-6.1, 67-REQ-6.2 met

- [x] 3. QualityGateCategory implementation
  - [x] 3.1 Create `agent_fox/nightshift/categories/quality_gate.py`
    - Define `QualityGateCategory(BaseHuntCategory)` with `_name = "quality_gate"`
    - Define `QUALITY_GATE_PROMPT` template for AI analysis
    - Define `SEVERITY_MAP` dict mapping `CheckCategory` to severity string
    - Define `MAX_OUTPUT_CHARS = 8000` for output truncation
    - _Requirements: 67-REQ-3.4, 67-REQ-4.1, 67-REQ-4.2, 67-REQ-4.3, 67-REQ-4.4_

  - [x] 3.2 Implement `_run_static_tool()` method
    - Call `detect_checks(project_root)` to discover checks
    - Return empty string if no checks detected
    - Execute each check via `subprocess.run()` with configured timeout
    - Collect failures, format as structured string
    - Return empty string if all checks pass
    - _Requirements: 67-REQ-1.1, 67-REQ-1.2, 67-REQ-2.1, 67-REQ-2.2, 67-REQ-2.3, 67-REQ-2.4, 67-REQ-2.E1, 67-REQ-2.E2_

  - [x] 3.3 Implement `_run_ai_analysis()` method
    - Return `[]` if static_output is empty
    - Send failure output to AI with `QUALITY_GATE_PROMPT`
    - Parse response with `extract_json_array()`
    - Convert each AI result to a `Finding` with correct severity and group_key
    - Populate `evidence` with raw output (truncated)
    - _Requirements: 67-REQ-3.1, 67-REQ-3.2, 67-REQ-3.3, 67-REQ-3.4_

  - [x] 3.4 Implement mechanical fallback for AI failure
    - On AI exception or unparseable response, generate one Finding per
      failure mechanically (check name as title, raw output as description)
    - _Requirements: 67-REQ-3.E1_

  - [x] 3.5 Override `detect()` to handle `detect_checks()` exceptions
    - Wrap the base class `detect()` call to catch exceptions from the
      static phase and return `[]` with a warning log
    - _Requirements: 67-REQ-1.E1_

  - [x] 3.V Verify task group 3
    - [x] All unit tests pass: `uv run pytest -q tests/unit/nightshift/test_quality_gate.py`
    - [x] All property tests pass: `uv run pytest -q tests/property/nightshift/test_quality_gate_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] All 67-REQ-* requirements met

- [ ] 4. Checkpoint -- Quality Gate Category Complete
  - Ensure all tests pass, ask the user if questions arise.
  - `make check` is green.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 67-REQ-1.1 | TS-67-1 | 3.2 | test_quality_gate.py::TestStaticPhase |
| 67-REQ-1.2 | TS-67-E2, TS-67-P5 | 3.2 | test_quality_gate.py::TestEdgeCases |
| 67-REQ-1.E1 | TS-67-E1 | 3.5 | test_quality_gate.py::TestEdgeCases |
| 67-REQ-2.1 | TS-67-1 | 3.2 | test_quality_gate.py::TestStaticPhase |
| 67-REQ-2.2 | TS-67-10 | 3.2 | test_quality_gate.py::TestConfiguration |
| 67-REQ-2.3 | TS-67-2, TS-67-P1 | 3.2 | test_quality_gate.py::TestStaticPhase |
| 67-REQ-2.4 | TS-67-1 | 3.2 | test_quality_gate.py::TestStaticPhase |
| 67-REQ-2.E1 | TS-67-E3 | 3.2 | test_quality_gate.py::TestEdgeCases |
| 67-REQ-2.E2 | TS-67-E4, TS-67-P1 | 3.2 | test_quality_gate.py::TestEdgeCases |
| 67-REQ-3.1 | TS-67-3 | 3.3 | test_quality_gate.py::TestAIAnalysis |
| 67-REQ-3.2 | TS-67-3, TS-67-P2 | 3.3 | test_quality_gate.py::TestAIAnalysis |
| 67-REQ-3.3 | TS-67-4 | 3.3 | test_quality_gate.py::TestAIAnalysis |
| 67-REQ-3.4 | TS-67-5 | 3.1 | test_quality_gate.py::TestAIAnalysis |
| 67-REQ-3.E1 | TS-67-E5, TS-67-E6, TS-67-P4 | 3.4 | test_quality_gate.py::TestEdgeCases |
| 67-REQ-4.1 | TS-67-6, TS-67-P3 | 3.1 | test_quality_gate.py::TestSeverityMapping |
| 67-REQ-4.2 | TS-67-7, TS-67-P3 | 3.1 | test_quality_gate.py::TestSeverityMapping |
| 67-REQ-4.3 | TS-67-8, TS-67-P3 | 3.1 | test_quality_gate.py::TestSeverityMapping |
| 67-REQ-4.4 | TS-67-P3 | 3.1 | test_quality_gate_props.py |
| 67-REQ-5.1 | TS-67-9 | 2.1 | test_quality_gate.py::TestConfiguration |
| 67-REQ-5.2 | TS-67-10 | 2.2 | test_quality_gate.py::TestConfiguration |
| 67-REQ-5.3 | TS-67-E7, TS-67-P6 | 2.2 | test_quality_gate.py::TestEdgeCases |
| 67-REQ-6.1 | TS-67-11 | 2.3 | test_quality_gate.py::TestRegistration |
| 67-REQ-6.2 | TS-67-11 | 2.4 | test_quality_gate.py::TestRegistration |
| 67-REQ-6.3 | TS-67-1 | 3.2 | test_quality_gate.py::TestStaticPhase |
