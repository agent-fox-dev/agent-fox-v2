# Implementation Plan: Review Archetype Persistence & Review-Only Mode

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The review persistence functions (`insert_findings()`, `insert_verdicts()`,
`insert_drift_findings()`) already exist in `review_store.py`. The gap is
that archetype session output is not being parsed and fed into them. This plan
adds a JSON extraction/parsing layer, wires it into the session lifecycle,
then adds review-only mode as a separate task group.

Implementation order:
1. Write failing tests.
2. Build the JSON extraction and parsing layer.
3. Wire archetype output into persistence + add retry context.
4. Add review-only CLI mode and graph construction.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_review_parser.py tests/unit/engine/test_review_persistence.py tests/integration/test_review_pipeline.py tests/unit/cli/test_review_only.py -v`
- Unit tests: `make test-unit`
- Property tests: `make test-property`
- All tests: `make test`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit tests for JSON extraction and parsing
    - Create `tests/unit/engine/test_review_parser.py`
    - Tests for TS-53-6, TS-53-7, TS-53-E2 (JSON extraction, field validation, multiple arrays)
    - _Test Spec: TS-53-6, TS-53-7, TS-53-E2_

  - [x] 1.2 Create unit tests for archetype routing and persistence
    - Create `tests/unit/engine/test_review_persistence.py`
    - Tests for TS-53-1, TS-53-2, TS-53-3, TS-53-5 (parse + persist per archetype, parse failure)
    - Tests for TS-53-8, TS-53-9 (retry context assembly)
    - _Test Spec: TS-53-1, TS-53-2, TS-53-3, TS-53-5, TS-53-8, TS-53-9_

  - [x] 1.3 Create integration tests for persistence and review-only
    - Create `tests/integration/test_review_pipeline.py`
    - Tests for TS-53-4, TS-53-10, TS-53-13 (supersession, review-only graph, summary)
    - _Test Spec: TS-53-4, TS-53-10, TS-53-13_

  - [x] 1.4 Create unit tests for review-only mode
    - Create `tests/unit/cli/test_review_only.py`
    - Tests for TS-53-11, TS-53-12, TS-53-E1, TS-53-E3 (graph nodes, audit events, no specs, filter)
    - _Test Spec: TS-53-11, TS-53-12, TS-53-E1, TS-53-E3_

  - [x] 1.5 Create property tests
    - Create `tests/property/engine/test_review_persistence_props.py`
    - Tests for TS-53-P1 through TS-53-P7
    - _Test Spec: TS-53-P1, TS-53-P2, TS-53-P3, TS-53-P4, TS-53-P5, TS-53-P6, TS-53-P7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. JSON extraction and parsing layer
  - [x] 2.1 Create `engine/review_parser.py`
    - `extract_json_array(output_text) -> list[dict] | None`
    - Try bracket-matching first, then markdown fences
    - Return first valid JSON array found
    - _Requirements: 53-REQ-4.1, 53-REQ-4.E1_

  - [x] 2.2 Add typed parse functions
    - `parse_review_findings(json_objects, spec_name, task_group, session_id) -> list[ReviewFinding]`
    - `parse_verification_results(json_objects, spec_name, task_group, session_id) -> list[VerificationResult]`
    - `parse_drift_findings(json_objects, spec_name, task_group, session_id) -> list[DriftFinding]`
    - Skip objects missing required fields, log warning
    - _Requirements: 53-REQ-4.2_

  - [x] 2.3 Add `REVIEW_PARSE_FAILURE` to `AuditEventType`
    - New enum member: `REVIEW_PARSE_FAILURE = "review.parse_failure"`
    - Set default severity to WARNING
    - _Requirements: 53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_review_parser.py -v`
    - [x] TS-53-6, TS-53-7, TS-53-E2 pass
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 53-REQ-4.x met

- [x] 3. Wire persistence into session lifecycle
  - [x] 3.1 Refactor `_persist_review_findings()` in session_lifecycle.py
    - Use `extract_json_array()` to parse output
    - Route to correct insert function based on `self._archetype`
    - Emit `review.parse_failure` on extraction failure
    - _Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1_

  - [x] 3.2 Ensure `_persist_review_findings()` is called for all archetypes
    - Verify the call site in `_post_session_integrate()` runs for
      skeptic, verifier, and oracle archetype types
    - _Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1_

  - [x] 3.3 Add `_build_retry_context()` method
    - Query `query_active_findings()` for critical/major findings
    - Format as structured block for coder prompt
    - Return empty string when no findings
    - _Requirements: 53-REQ-5.1, 53-REQ-5.2, 53-REQ-5.E1_

  - [x] 3.4 Inject retry context into coder prompt
    - In session setup for retry attempts (attempt > 1), call
      `_build_retry_context()` and prepend to prompt
    - _Requirements: 53-REQ-5.1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_review_persistence.py tests/integration/test_review_pipeline.py -v`
    - [x] TS-53-1, TS-53-2, TS-53-3, TS-53-5, TS-53-8, TS-53-9 pass (TS-53-4 blocked by TG4 import)
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 53-REQ-1.x, 53-REQ-2.x, 53-REQ-3.x, 53-REQ-5.x met

- [x] 4. Review-only CLI mode
  - [x] 4.1 Add `--review-only` flag to `cli/code.py`
    - Click option on the `code` command
    - Pass through ctx.obj to the engine
    - _Requirements: 53-REQ-6.1_

  - [x] 4.2 Add `build_review_only_graph()` to `graph/injection.py`
    - Scan specs for source files and requirements.md
    - Create Skeptic + Oracle nodes for specs with source files
    - Create Verifier nodes for specs with requirements.md
    - Handle empty specs (print message, exit 0)
    - _Requirements: 53-REQ-6.2, 53-REQ-6.E1_

  - [x] 4.3 Add review-only audit events
    - Emit `run.start` and `run.complete` with `mode: "review_only"` payload
    - _Requirements: 53-REQ-6.3_

  - [x] 4.4 Add review-only summary output
    - Print findings by severity, verdicts by status, drift by severity
    - _Requirements: 53-REQ-6.5_

  - [x] 4.5 Support `--spec` filter in review-only mode
    - Apply spec filter to restrict reviewed specs
    - _Requirements: 53-REQ-6.E2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/cli/test_review_only.py -v`
    - [x] TS-53-10, TS-53-11, TS-53-12, TS-53-13, TS-53-E1, TS-53-E3 pass
    - [x] Property tests pass: `uv run pytest -q tests/property/engine/test_review_persistence_props.py -v`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 53-REQ-6.x met

- [x] 5. Checkpoint — Review Persistence Complete
  - [x] All spec tests pass
  - [x] All property tests pass
  - [x] Full test suite green: `make check`
  - [x] Review coverage matrix — all requirements have passing tests

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 53-REQ-1.1 | TS-53-1 | 3.1, 3.2 | `test_review_persistence.py::test_skeptic_parsed` |
| 53-REQ-1.2 | TS-53-4 | 3.1 | `test_review_pipeline.py::test_supersession` |
| 53-REQ-1.E1 | TS-53-5 | 2.3, 3.1 | `test_review_persistence.py::test_parse_failure_audit` |
| 53-REQ-2.1 | TS-53-2 | 3.1, 3.2 | `test_review_persistence.py::test_verifier_parsed` |
| 53-REQ-2.2 | TS-53-4 | 3.1 | `test_review_pipeline.py::test_supersession` |
| 53-REQ-2.E1 | TS-53-5 | 2.3, 3.1 | `test_review_persistence.py::test_parse_failure_audit` |
| 53-REQ-3.1 | TS-53-3 | 3.1, 3.2 | `test_review_persistence.py::test_oracle_parsed` |
| 53-REQ-3.2 | TS-53-4 | 3.1 | `test_review_pipeline.py::test_supersession` |
| 53-REQ-3.E1 | TS-53-5 | 2.3, 3.1 | `test_review_persistence.py::test_parse_failure_audit` |
| 53-REQ-4.1 | TS-53-6 | 2.1 | `test_review_parser.py::test_json_from_fences` |
| 53-REQ-4.2 | TS-53-7 | 2.2 | `test_review_parser.py::test_invalid_fields_skipped` |
| 53-REQ-4.E1 | TS-53-E2 | 2.1 | `test_review_parser.py::test_multiple_arrays_first` |
| 53-REQ-5.1 | TS-53-8 | 3.3, 3.4 | `test_review_persistence.py::test_retry_context_includes` |
| 53-REQ-5.2 | TS-53-8 | 3.3 | `test_review_persistence.py::test_retry_context_format` |
| 53-REQ-5.E1 | TS-53-9 | 3.3 | `test_review_persistence.py::test_retry_context_empty` |
| 53-REQ-6.1 | TS-53-10 | 4.1 | `test_review_pipeline.py::test_review_only_no_coder` |
| 53-REQ-6.2 | TS-53-11 | 4.2 | `test_review_only.py::test_review_graph_nodes` |
| 53-REQ-6.3 | TS-53-12 | 4.3 | `test_review_only.py::test_review_audit_events` |
| 53-REQ-6.4 | TS-53-P6 | 4.2 | `test_review_persistence_props.py::test_read_only` |
| 53-REQ-6.5 | TS-53-13 | 4.4 | `test_review_pipeline.py::test_review_summary` |
| 53-REQ-6.E1 | TS-53-E1 | 4.2 | `test_review_only.py::test_no_eligible_specs` |
| 53-REQ-6.E2 | TS-53-E3 | 4.5 | `test_review_only.py::test_spec_filter` |

## Notes

- All DuckDB interactions should use in-memory databases in tests.
- The JSON extraction must handle LLM output that wraps JSON in markdown
  code fences — this is the most common format.
- Review-only mode reuses existing archetype allowlists for command
  restriction — no new enforcement mechanism needed.
- The `_persist_review_findings()` method already exists in the codebase
  but may not be fully functional. Inspect before modifying.
