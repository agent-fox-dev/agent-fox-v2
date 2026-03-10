# Implementation Plan: Structured Review Records

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in 7 task groups: (1) write failing tests, (2) schema
migration, (3) review store CRUD, (4) output parser, (5) context rendering,
(6) convergence + GitHub issues, (7) template updates + backward compat +
checkpoint.

## Test Commands

- Spec tests: `uv run pytest tests/unit/knowledge/test_review_store.py tests/unit/session/test_review_parser.py tests/unit/session/test_review_context.py -q`
- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/property/ -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file structure
    - Create `tests/unit/knowledge/test_review_store.py`
    - Create `tests/unit/session/test_review_parser.py`
    - Create `tests/unit/session/test_review_context.py`
    - Create `tests/unit/session/test_convergence_records.py`
    - Create `tests/property/knowledge/test_review_store_props.py`
    - Create `tests/property/session/test_review_parser_props.py`
    - Create `tests/property/session/test_review_context_props.py`
    - _Test Spec: TS-27-1 through TS-27-18_

  - [x] 1.2 Translate schema and store tests
    - TS-27-1: review_findings table created
    - TS-27-2: verification_results table created
    - TS-27-6: insert findings with supersession
    - TS-27-7: insert verdicts with supersession
    - TS-27-8: causal links on supersession
    - _Test Spec: TS-27-1, TS-27-2, TS-27-6, TS-27-7, TS-27-8_

  - [x] 1.3 Translate parser tests
    - TS-27-3: parse skeptic JSON
    - TS-27-4: parse verifier JSON
    - TS-27-5: validate schema rejects invalid
    - _Test Spec: TS-27-3, TS-27-4, TS-27-5_

  - [x] 1.4 Translate context rendering tests
    - TS-27-9: render review context
    - TS-27-10: render verification context
    - TS-27-11: rendered format matches legacy
    - _Test Spec: TS-27-9, TS-27-10, TS-27-11_

  - [x] 1.5 Translate convergence and integration tests
    - TS-27-12: converge skeptic records
    - TS-27-13: converge verifier records
    - TS-27-14: GitHub issue body from DB
    - TS-27-15: skeptic template JSON instructions
    - TS-27-16: verifier template JSON instructions
    - TS-27-17: legacy review file migration
    - TS-27-18: legacy verification file migration
    - _Test Spec: TS-27-12 through TS-27-18_

  - [x] 1.6 Translate edge case and property tests
    - TS-27-E1 through TS-27-E9
    - TS-27-P1 through TS-27-P7
    - _Test Spec: TS-27-E1 through TS-27-E9, TS-27-P1 through TS-27-P7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests pass (implementation from prior commit already exists)
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Schema migration and data types
  - [x] 2.1 Define ReviewFinding and VerificationResult dataclasses
    - Create `agent_fox/knowledge/review_store.py` with dataclass definitions
    - Define `VALID_SEVERITIES` and `VALID_VERDICTS` constants
    - _Requirements: 1.1, 2.1_

  - [x] 2.2 Implement schema migration v2
    - Add migration to `agent_fox/knowledge/migrations.py`
    - Create `review_findings` and `verification_results` tables
    - Increment schema version
    - _Requirements: 1.1, 1.2, 2.1, 2.2_

  - [x] 2.3 Wire migration into KnowledgeDB.open()
    - Ensure `apply_pending_migrations()` picks up the new migration
    - _Requirements: 1.2, 2.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: TS-27-1, TS-27-2, TS-27-E1, TS-27-E2, TS-27-P6
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 1.1, 1.2, 1.E1, 2.1, 2.2, 2.E1 met

- [x] 3. Review store CRUD operations
  - [x] 3.1 Implement insert_findings with supersession
    - Supersede existing active records for same (spec_name, task_group)
    - Insert new records
    - Create causal links from superseded to new records
    - _Requirements: 4.1, 4.3_

  - [x] 3.2 Implement insert_verdicts with supersession
    - Same supersession logic for verification results
    - _Requirements: 4.2, 4.3_

  - [x] 3.3 Implement query functions
    - `query_active_findings()` — WHERE superseded_by IS NULL
    - `query_active_verdicts()` — WHERE superseded_by IS NULL
    - `query_findings_by_session()` — for convergence
    - `query_verdicts_by_session()` — for convergence
    - _Requirements: 5.1, 5.2, 6.1, 6.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: TS-27-6, TS-27-7, TS-27-8, TS-27-E5, TS-27-P1
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 4.1, 4.2, 4.3, 4.E1 met

- [ ] 4. Output parser
  - [ ] 4.1 Implement parse_review_output
    - Extract JSON blocks from agent response text
    - Validate against finding schema (severity, description required)
    - Normalize unknown severities to "observation"
    - Return list of ReviewFinding dataclasses
    - _Requirements: 3.1, 3.3_

  - [ ] 4.2 Implement parse_verification_output
    - Extract JSON blocks from agent response text
    - Validate against verdict schema (requirement_id, verdict required)
    - Return list of VerificationResult dataclasses
    - _Requirements: 3.2, 3.3_

  - [ ] 4.3 Implement JSON extraction helper
    - Find JSON blocks in mixed prose/JSON agent output
    - Handle fenced code blocks (```json ... ```) and bare JSON
    - _Requirements: 3.1, 3.2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: TS-27-3, TS-27-4, TS-27-5, TS-27-E3, TS-27-E4, TS-27-P2, TS-27-P5
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 3.1, 3.2, 3.3, 3.E1, 3.E2 met

- [ ] 5. Context rendering from DB
  - [ ] 5.1 Implement render_review_context
    - Query active findings, group by severity
    - Render markdown matching legacy Skeptic format
    - Return None if no findings exist
    - _Requirements: 5.1, 5.3_

  - [ ] 5.2 Implement render_verification_context
    - Query active verdicts, render as markdown table
    - Compute overall verdict (FAIL if any FAIL)
    - Return None if no verdicts exist
    - _Requirements: 5.2, 5.3_

  - [ ] 5.3 Update assemble_context to use DB rendering
    - Add optional `conn` parameter to `assemble_context()`
    - Query DB for review/verification sections
    - Fall back to file-based reading if conn is None or query fails
    - Remove review.md and verification.md from `_SPEC_FILES` when DB is used
    - _Requirements: 5.1, 5.2, 5.E1, 5.E2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: TS-27-9, TS-27-10, TS-27-11, TS-27-E6, TS-27-E7, TS-27-P3
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 5.1, 5.2, 5.3, 5.E1, 5.E2 met

- [ ] 6. Convergence and GitHub issues
  - [ ] 6.1 Implement converge_skeptic_records
    - Same union-dedup-majority-gate algorithm on ReviewFinding records
    - Write merged results back to DB with convergence session_id
    - _Requirements: 6.1, 6.3_

  - [ ] 6.2 Implement converge_verifier_records
    - Majority vote on VerificationResult records
    - Write merged results back to DB
    - _Requirements: 6.2, 6.3_

  - [ ] 6.3 Update github_issues.py to source from DB
    - Add function to format issue body from ReviewFinding records
    - Update file_or_update_issue call sites
    - _Requirements: 7.1, 7.2_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests pass: TS-27-12, TS-27-13, TS-27-14, TS-27-E8, TS-27-P4
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 6.1, 6.2, 6.3, 6.E1, 7.1, 7.2, 7.E1 met

- [ ] 7. Templates, backward compat, and checkpoint
  - [ ] 7.1 Update skeptic.md template
    - Add JSON output instructions with schema example
    - Retain read-only constraints and severity guidance
    - _Requirements: 8.1, 8.2_

  - [ ] 7.2 Update verifier.md template
    - Add JSON output instructions with schema example
    - Retain verification process guidance
    - _Requirements: 9.1, 9.2_

  - [ ] 7.3 Implement legacy markdown migration
    - Parse existing review.md into ReviewFinding records
    - Parse existing verification.md into VerificationResult records
    - Trigger on context assembly when DB records don't exist
    - _Requirements: 10.1, 10.2_

  - [ ] 7.4 Documentation and cleanup
    - Update docs/memory.md with new knowledge pipeline changes
    - Create ADR for the architectural decision
    - Ensure all tests pass

  - [ ] 7.V Verify task group 7
    - [ ] Spec tests pass: TS-27-15, TS-27-16, TS-27-17, TS-27-18, TS-27-E9, TS-27-P7
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 8.1, 8.2, 8.E1, 9.1, 9.2, 9.E1, 10.1, 10.2, 10.E1 met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 27-REQ-1.1 | TS-27-1 | 2.1, 2.2 | test_review_store.py::test_review_findings_table_created |
| 27-REQ-1.2 | TS-27-P6 | 2.2, 2.3 | test_review_store_props.py::test_migration_idempotency |
| 27-REQ-1.E1 | TS-27-E1 | 2.2 | test_review_store.py::test_migration_failure_raises |
| 27-REQ-2.1 | TS-27-2 | 2.1, 2.2 | test_review_store.py::test_verification_results_table_created |
| 27-REQ-2.2 | TS-27-P6 | 2.2, 2.3 | test_review_store_props.py::test_migration_idempotency |
| 27-REQ-2.E1 | TS-27-E2 | 2.2 | test_review_store.py::test_migration_already_applied_skips |
| 27-REQ-3.1 | TS-27-3, TS-27-P2 | 4.1 | test_review_parser.py::test_parse_skeptic_json |
| 27-REQ-3.2 | TS-27-4, TS-27-P2 | 4.2 | test_review_parser.py::test_parse_verifier_json |
| 27-REQ-3.3 | TS-27-5, TS-27-P5 | 4.1, 4.2 | test_review_parser.py::test_validate_schema_rejects |
| 27-REQ-3.E1 | TS-27-E3 | 4.1 | test_review_parser.py::test_no_valid_json_returns_empty |
| 27-REQ-3.E2 | TS-27-E4 | 4.1 | test_review_parser.py::test_unknown_severity_normalized |
| 27-REQ-4.1 | TS-27-6, TS-27-P1 | 3.1 | test_review_store.py::test_insert_findings_supersession |
| 27-REQ-4.2 | TS-27-7, TS-27-P1 | 3.2 | test_review_store.py::test_insert_verdicts_supersession |
| 27-REQ-4.3 | TS-27-8 | 3.1, 3.2 | test_review_store.py::test_causal_links_on_supersession |
| 27-REQ-4.E1 | TS-27-E5 | 3.1 | test_review_store.py::test_no_records_to_supersede |
| 27-REQ-5.1 | TS-27-9, TS-27-P3 | 5.1 | test_review_context.py::test_render_review_context |
| 27-REQ-5.2 | TS-27-10 | 5.2 | test_review_context.py::test_render_verification_context |
| 27-REQ-5.3 | TS-27-11, TS-27-P3 | 5.1, 5.2 | test_review_context.py::test_rendered_format_matches_legacy |
| 27-REQ-5.E1 | TS-27-E6, TS-27-P7 | 5.3 | test_review_context.py::test_db_unavailable_fallback |
| 27-REQ-5.E2 | TS-27-E7 | 5.1 | test_review_context.py::test_no_findings_omits_section |
| 27-REQ-6.1 | TS-27-12, TS-27-P4 | 6.1 | test_convergence_records.py::test_converge_skeptic_records |
| 27-REQ-6.2 | TS-27-13, TS-27-P4 | 6.2 | test_convergence_records.py::test_converge_verifier_records |
| 27-REQ-6.3 | TS-27-12 | 6.1, 6.2 | test_convergence_records.py::test_convergence_writes_back |
| 27-REQ-6.E1 | TS-27-E8 | 6.1 | test_convergence_records.py::test_single_instance_skips |
| 27-REQ-7.1 | TS-27-14 | 6.3 | test_review_context.py::test_github_issue_body_from_db |
| 27-REQ-7.2 | TS-27-14 | 6.3 | test_review_context.py::test_github_issue_close_empty |
| 27-REQ-7.E1 | TS-27-E6 | 6.3 | test_review_context.py::test_github_issue_db_unavailable |
| 27-REQ-8.1 | TS-27-15 | 7.1 | test_review_parser.py::test_skeptic_template_json |
| 27-REQ-8.2 | TS-27-15 | 7.1 | test_review_parser.py::test_skeptic_template_constraints |
| 27-REQ-8.E1 | TS-27-15 | 7.1 | test_review_parser.py::test_json_preferred_over_file |
| 27-REQ-9.1 | TS-27-16 | 7.2 | test_review_parser.py::test_verifier_template_json |
| 27-REQ-9.2 | TS-27-16 | 7.2 | test_review_parser.py::test_verifier_template_constraints |
| 27-REQ-9.E1 | TS-27-16 | 7.2 | test_review_parser.py::test_json_preferred_over_file |
| 27-REQ-10.1 | TS-27-17, TS-27-P7 | 7.3 | test_review_context.py::test_legacy_review_migration |
| 27-REQ-10.2 | TS-27-18 | 7.3 | test_review_context.py::test_legacy_verification_migration |
| 27-REQ-10.E1 | TS-27-E9 | 7.3 | test_review_context.py::test_legacy_parse_failure_skips |

## Notes

- Task group 1 creates all test files with failing tests. Groups 2-7
  implement code to make them pass progressively.
- The `schema_conn` fixture from `tests/unit/knowledge/conftest.py` provides
  an in-memory DuckDB with schema v1. Tests for migration v2 should start
  from this baseline.
- The existing `Finding` dataclass in `convergence.py` is preserved — the new
  `ReviewFinding` is a superset. Convergence equivalence tests (TS-27-P4)
  verify that both paths produce the same result.
- Template updates (group 7) are done last to avoid disrupting any running
  Skeptic/Verifier agents during development.
