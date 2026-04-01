# Implementation Plan: Cross-Category Finding Consolidation Critic

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation replaces the existing `consolidate_findings()` in
`finding.py` with a new AI-powered critic stage in `critic.py`. Task group 1
writes failing tests. Group 2 implements the mechanical grouping and data
models (the non-AI path). Group 3 implements the AI critic path with prompt,
parsing, and logging. Group 4 integrates the new module into the engine and
updates existing tests.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_critic.py tests/property/nightshift/test_critic_props.py tests/integration/nightshift/test_critic.py`
- Unit tests: `uv run pytest -q tests/unit/nightshift/test_critic.py`
- Property tests: `uv run pytest -q tests/property/nightshift/test_critic_props.py`
- Integration tests: `uv run pytest -q tests/integration/nightshift/test_critic.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/nightshift/test_critic.py`
    - Test `_mechanical_grouping()` — TS-73-8, TS-73-E6
    - Test `_parse_critic_response()` — TS-73-2, TS-73-E8
    - Test `_log_decisions()` — TS-73-5, TS-73-7, TS-73-10
    - Test async signature introspection — TS-73-11
    - _Test Spec: TS-73-2, TS-73-5, TS-73-7, TS-73-8, TS-73-10, TS-73-11, TS-73-E6, TS-73-E8_

  - [x] 1.2 Create integration test file `tests/integration/nightshift/test_critic.py`
    - Test cross-category merge — TS-73-1
    - Test synthesised title/body — TS-73-3
    - Test evidence validation drops — TS-73-4
    - Test severity calibration — TS-73-6
    - Test all-merged — TS-73-E1
    - Test no-merge — TS-73-E2
    - Test all-dropped — TS-73-E3
    - Test speculative evidence — TS-73-E4
    - Test severity preserved — TS-73-E5
    - Test malformed JSON fallback — TS-73-E7
    - Test AI backend failure fallback — TS-73-E9
    - Test output compatibility — TS-73-9
    - _Test Spec: TS-73-1, TS-73-3, TS-73-4, TS-73-6, TS-73-9, TS-73-E1 through TS-73-E5, TS-73-E7, TS-73-E9_

  - [x] 1.3 Create property test file `tests/property/nightshift/test_critic_props.py`
    - Finding conservation — TS-73-P1
    - Mechanical grouping bijection — TS-73-P2
    - Affected files union — TS-73-P3
    - Output format compatibility — TS-73-P4
    - Graceful degradation — TS-73-P5
    - Empty input invariant — TS-73-P6
    - Decision completeness — TS-73-P7
    - _Test Spec: TS-73-P1 through TS-73-P7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Implement data models and mechanical grouping
  - [x] 2.1 Create `agent_fox/nightshift/critic.py` with module docstring
    - Define `MINIMUM_FINDING_THRESHOLD = 3`
    - Define `CriticDecision` dataclass
    - Define `CriticSummary` dataclass
    - _Requirements: 73-REQ-4.1_

  - [x] 2.2 Implement `_mechanical_grouping()`
    - Each finding becomes its own FindingGroup
    - Title from finding.title, body from build_issue_body pattern
    - affected_files sorted and deduplicated
    - _Requirements: 73-REQ-4.2, 73-REQ-5.1_

  - [x] 2.3 Implement `_log_decisions()` and `_log_summary()`
    - Log merges, drops, severity changes at INFO
    - Log full reasoning at DEBUG
    - Swallow logging exceptions
    - _Requirements: 73-REQ-6.1, 73-REQ-6.2, 73-REQ-6.3, 73-REQ-6.4, 73-REQ-6.E1_

  - [x] 2.4 Implement skeleton `consolidate_findings()` async function
    - Handle empty input (return [])
    - Handle below-threshold (call _mechanical_grouping)
    - Stub the critic path to fall through to _mechanical_grouping
    - _Requirements: 73-REQ-4.E1, 73-REQ-7.2, 73-REQ-7.3_

  - [x] 2.V Verify task group 2
    - [x] Unit tests for mechanical grouping pass: `uv run pytest -q tests/unit/nightshift/test_critic.py`
    - [x] Property tests P2, P3, P4, P6 pass
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 73-REQ-4.*, 73-REQ-6.* met

- [x] 3. Implement AI critic path
  - [x] 3.1 Define critic prompt template
    - System prompt instructing deduplication, validation, severity calibration
    - User message format: indexed JSON array of findings
    - Expected output format: { groups: [...], dropped: [...] }
    - _Requirements: 73-REQ-1.1, 73-REQ-2.1_

  - [x] 3.2 Implement `_run_critic()`
    - Send findings to Claude via existing backend abstraction
    - Return raw response text
    - Raise on backend failure
    - _Requirements: 73-REQ-7.3_

  - [x] 3.3 Implement `_parse_critic_response()`
    - Parse JSON using raw_decode with markdown-fence fallback
    - Build FindingGroups from groups array with original Finding objects
    - Compute affected_files as sorted deduplicated union
    - Build CriticDecision list from groups and dropped arrays
    - Validate finding indices, warn and skip invalid ones
    - Raise ValueError on malformed JSON
    - _Requirements: 73-REQ-1.2, 73-REQ-1.3, 73-REQ-5.2, 73-REQ-5.3, 73-REQ-5.E2_

  - [x] 3.4 Wire critic into `consolidate_findings()`
    - Call _run_critic when count >= threshold
    - Parse response with _parse_critic_response
    - Log decisions
    - Fall back to _mechanical_grouping on any exception
    - _Requirements: 73-REQ-2.2, 73-REQ-3.1, 73-REQ-5.E1, 73-REQ-7.E1_

  - [x] 3.V Verify task group 3
    - [x] All integration tests pass: `uv run pytest -q tests/integration/nightshift/test_critic.py`
    - [x] All property tests pass: `uv run pytest -q tests/property/nightshift/test_critic_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 73-REQ-1.*, 73-REQ-2.*, 73-REQ-3.*, 73-REQ-5.* met

- [x] 4. Pipeline integration and cleanup
  - [x] 4.1 Remove old `consolidate_findings()` from `finding.py`
    - Delete the function
    - Keep Finding, FindingGroup, build_issue_body unchanged
    - _Requirements: 73-REQ-7.1_

  - [x] 4.2 Update engine.py to use new critic
    - Import from `critic` instead of `finding`
    - Await the now-async consolidate_findings call
    - _Requirements: 73-REQ-7.1, 73-REQ-7.2_

  - [x] 4.3 Update existing tests that import old consolidate_findings
    - Fix imports to point to critic module
    - Update any tests that relied on sync behavior
    - _Requirements: 73-REQ-7.1_

  - [x] 4.V Verify task group 4
    - [x] All spec tests pass: `uv run pytest -q tests/unit/nightshift/test_critic.py tests/property/nightshift/test_critic_props.py tests/integration/nightshift/test_critic.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check && uv run ruff format --check`
    - [x] Full pipeline: `make check`
    - [x] Requirements 73-REQ-7.* met

- [ ] 5. Checkpoint — Critic Complete
  - Verify `make check` passes with zero regressions.
  - Review that all traceability entries are satisfied.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 73-REQ-1.1 | TS-73-1 | 3.1, 3.4 | test_critic.py::test_cross_category_merge |
| 73-REQ-1.2 | TS-73-2 | 3.3 | test_critic.py::test_affected_files_union |
| 73-REQ-1.3 | TS-73-3 | 3.3 | test_critic.py::test_synthesised_title_body |
| 73-REQ-1.E1 | TS-73-E1 | 3.4 | test_critic.py::test_all_same_root_cause |
| 73-REQ-1.E2 | TS-73-E2 | 3.4 | test_critic.py::test_no_shared_root_cause |
| 73-REQ-2.1 | TS-73-4 | 3.1, 3.3 | test_critic.py::test_evidence_validation_drops |
| 73-REQ-2.2 | TS-73-4 | 3.4 | test_critic.py::test_evidence_validation_drops |
| 73-REQ-2.3 | TS-73-5 | 2.3 | test_critic.py::test_drop_logged |
| 73-REQ-2.E1 | TS-73-E3 | 3.4 | test_critic.py::test_all_findings_dropped |
| 73-REQ-2.E2 | TS-73-E4 | 3.4 | test_critic.py::test_speculative_evidence_dropped |
| 73-REQ-3.1 | TS-73-6 | 3.3, 3.4 | test_critic.py::test_severity_calibration |
| 73-REQ-3.2 | TS-73-7 | 2.3 | test_critic.py::test_severity_change_logged |
| 73-REQ-3.E1 | TS-73-E5 | 3.4 | test_critic.py::test_severity_preserved |
| 73-REQ-4.1 | TS-73-8 | 2.4 | test_critic.py::test_below_threshold_mechanical |
| 73-REQ-4.2 | TS-73-8 | 2.2 | test_critic.py::test_below_threshold_mechanical |
| 73-REQ-4.E1 | TS-73-E6 | 2.4 | test_critic.py::test_zero_findings |
| 73-REQ-5.1 | TS-73-9 | 2.2, 3.3 | test_critic.py::test_output_compatibility |
| 73-REQ-5.2 | TS-73-9 | 3.3 | test_critic.py::test_output_compatibility |
| 73-REQ-5.3 | TS-73-9 | 3.3 | test_critic.py::test_output_compatibility |
| 73-REQ-5.E1 | TS-73-E7 | 3.4 | test_critic.py::test_malformed_json_fallback |
| 73-REQ-5.E2 | TS-73-E8 | 3.3 | test_critic.py::test_invalid_indices |
| 73-REQ-6.1 | TS-73-5 | 2.3 | test_critic.py::test_drop_logged |
| 73-REQ-6.2 | TS-73-5 | 2.3 | test_critic.py::test_drop_logged |
| 73-REQ-6.3 | TS-73-10 | 2.3 | test_critic.py::test_summary_log |
| 73-REQ-6.4 | TS-73-10 | 2.3 | test_critic.py::test_summary_log |
| 73-REQ-6.E1 | TS-73-E7 | 2.3 | test_critic.py::test_malformed_json_fallback |
| 73-REQ-7.1 | TS-73-11 | 4.1, 4.2 | test_critic.py::test_async_signature |
| 73-REQ-7.2 | TS-73-11 | 2.4 | test_critic.py::test_async_signature |
| 73-REQ-7.3 | TS-73-11 | 2.4 | test_critic.py::test_async_signature |
| 73-REQ-7.E1 | TS-73-E9 | 3.4 | test_critic.py::test_ai_backend_failure |
| Property 1 | TS-73-P1 | 3.4 | test_critic_props.py::test_finding_conservation |
| Property 2 | TS-73-P2 | 2.2 | test_critic_props.py::test_mechanical_bijection |
| Property 3 | TS-73-P3 | 2.2, 3.3 | test_critic_props.py::test_affected_files_union |
| Property 4 | TS-73-P4 | 2.2 | test_critic_props.py::test_output_format |
| Property 5 | TS-73-P5 | 3.4 | test_critic_props.py::test_graceful_degradation |
| Property 6 | TS-73-P6 | 2.4 | test_critic_props.py::test_empty_input |
| Property 7 | TS-73-P7 | 3.3 | test_critic_props.py::test_decision_completeness |

## Notes

- Use `json.JSONDecoder.raw_decode()` for JSON extraction from AI responses
  (lesson from memory.md — bracket-depth scanning fails on JSON strings
  containing brackets).
- The critic prompt must instruct the AI to return finding indices (0-based)
  referencing the input array, so `_parse_critic_response()` can map back to
  original Finding objects.
- Existing tests in `tests/unit/nightshift/test_finding.py` that test the old
  `consolidate_findings()` will need import updates in task group 4.
- Property tests should use `@pytest.mark.asyncio` for async tests and
  `suppress(HealthCheck.function_scoped_fixture)` for Hypothesis+fixtures.
