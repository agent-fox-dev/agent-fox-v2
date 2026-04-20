# Implementation Plan: Review Parse Resilience

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Three implementation phases after test scaffolding:
1. Stricter prompt templates (REQ-1.*)
2. Tolerant parser with fuzzy matching and key normalization (REQ-2.*)
3. Format retry logic, partial convergence, and observability (REQ-3.*, 4.*, 5.*)

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/session/test_review_parse_resilience.py tests/unit/engine/test_review_parse_resilience.py tests/integration/test_review_parse_resilience.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for prompt template assertions
    - `tests/unit/session/test_review_parse_resilience.py`
    - Tests for TS-74-1 through TS-74-6 (prompt content checks)
    - _Test Spec: TS-74-1, TS-74-2, TS-74-3, TS-74-4, TS-74-5, TS-74-6_

  - [x] 1.2 Create unit test file for parser tolerance
    - `tests/unit/engine/test_review_parse_resilience.py`
    - Tests for TS-74-7 through TS-74-13 (fuzzy matching, normalization)
    - Tests for TS-74-15, TS-74-16, TS-74-19 (retry unit tests)
    - Tests for TS-74-20 through TS-74-27 (convergence, observability)
    - Edge case tests: TS-74-E1, TS-74-E2, TS-74-E3
    - _Test Spec: TS-74-7 through TS-74-27, TS-74-E1 through TS-74-E3_

  - [x] 1.3 Create property test file
    - `tests/property/test_review_parse_resilience_props.py`
    - Property tests: TS-74-P1 through TS-74-P6
    - _Test Spec: TS-74-P1, TS-74-P2, TS-74-P3, TS-74-P4, TS-74-P5, TS-74-P6_

  - [x] 1.4 Create integration test file for format retry
    - `tests/integration/test_review_parse_resilience.py`
    - Tests for TS-74-14, TS-74-17, TS-74-18 (end-to-end retry)
    - _Test Spec: TS-74-14, TS-74-17, TS-74-18_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Stricter prompt templates
  - [x] 2.1 Update skeptic.md with strict format instructions
    - Add "Output ONLY the JSON block" instruction
    - Add negative example showing markdown-fenced JSON labeled as WRONG
    - Add CRITICAL REMINDERS section at end repeating format constraints
    - _Requirements: 74-REQ-1.1, 74-REQ-1.5, 74-REQ-1.6_

  - [x] 2.2 Update verifier.md with strict format instructions
    - Same changes as 2.1 adapted for verifier schema
    - _Requirements: 74-REQ-1.2, 74-REQ-1.5, 74-REQ-1.6_

  - [x] 2.3 Update auditor.md with strict format instructions
    - Same changes as 2.1 adapted for auditor schema
    - _Requirements: 74-REQ-1.3, 74-REQ-1.5, 74-REQ-1.6_

  - [x] 2.4 Update oracle.md with strict format instructions
    - Same changes as 2.1 adapted for oracle schema
    - _Requirements: 74-REQ-1.4, 74-REQ-1.5, 74-REQ-1.6_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: TS-74-1 through TS-74-6
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 74-REQ-1.1 through 74-REQ-1.6 acceptance criteria met

- [x] 3. Tolerant parser with fuzzy matching
  - [x] 3.1 Add WRAPPER_KEY_VARIANTS map and _resolve_wrapper_key()
    - In `agent_fox/session/review_parser.py`
    - Maps canonical keys to accepted variant sets
    - Case-insensitive lookup
    - _Requirements: 74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3_

  - [x] 3.2 Update _unwrap_items() to use fuzzy key matching
    - Replace exact `wrapper_key in data` check with `_resolve_wrapper_key()`
    - Preserve existing single-item and bare-array fallbacks
    - Added direct json.loads fast-path for robustness with nested JSON
    - _Requirements: 74-REQ-2.3, 74-REQ-2.E1_

  - [x] 3.3 Add _normalize_keys() and apply in field-level parsers
    - In `agent_fox/engine/review_parser.py`
    - Apply in `parse_review_findings()`, `parse_verification_results()`,
      `parse_drift_findings()`
    - _Requirements: 74-REQ-2.4_

  - [x] 3.4 Verify backward compatibility
    - Ensure existing exact-match JSON still parses identically
    - Run existing review parser tests
    - _Requirements: 74-REQ-2.5_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: TS-74-7 through TS-74-13, TS-74-E1, TS-74-E2
    - [x] Property tests pass: TS-74-P1, TS-74-P2, TS-74-P5, TS-74-P6
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 74-REQ-2.1 through 74-REQ-2.E2 acceptance criteria met

- [x] 4. Format retry, partial convergence, and observability
  - [x] 4.1 Add REVIEW_PARSE_RETRY_SUCCESS audit event type
    - In `agent_fox/knowledge/audit.py`
    - _Requirements: 74-REQ-5.1_

  - [x] 4.2 Implement format retry in persist_review_findings()
    - Add FORMAT_RETRY_PROMPT constant
    - On parse failure: if session alive, send retry message, re-parse
    - Limit to 1 retry, skip if session terminated
    - Emit REVIEW_PARSE_RETRY_SUCCESS on success
    - Enhance REVIEW_PARSE_FAILURE payload with retry_attempted and strategy
    - _Requirements: 74-REQ-3.1, 74-REQ-3.2, 74-REQ-3.3, 74-REQ-3.4,
      74-REQ-3.5, 74-REQ-3.E1, 74-REQ-3.E2, 74-REQ-5.1, 74-REQ-5.2,
      74-REQ-5.3_

  - [x] 4.3 Add partial-result filtering at convergence call sites
    - Filter None/empty results before passing to converge_* functions
    - Log warning for failed instances
    - Emit REVIEW_PARSE_FAILURE only if ALL instances fail
    - _Requirements: 74-REQ-4.1, 74-REQ-4.2, 74-REQ-4.3, 74-REQ-4.4,
      74-REQ-4.5, 74-REQ-4.E1, 74-REQ-4.E2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for this group pass: TS-74-14 through TS-74-27, TS-74-E3
    - [x] Property tests pass: TS-74-P3, TS-74-P4
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 74-REQ-3.* through 74-REQ-5.* acceptance criteria met

- [x] 5. Checkpoint — Review Parse Resilience Complete
  - [x] All spec tests pass
  - [x] All property tests pass
  - [x] Full test suite passes: `make check`
  - [x] Update documentation if needed

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 74-REQ-1.1 | TS-74-1 | 2.1 | tests/unit/session/test_review_parse_resilience.py |
| 74-REQ-1.2 | TS-74-2 | 2.2 | tests/unit/session/test_review_parse_resilience.py |
| 74-REQ-1.3 | TS-74-3 | 2.3 | tests/unit/session/test_review_parse_resilience.py |
| 74-REQ-1.4 | TS-74-4 | 2.4 | tests/unit/session/test_review_parse_resilience.py |
| 74-REQ-1.5 | TS-74-5 | 2.1-2.4 | tests/unit/session/test_review_parse_resilience.py |
| 74-REQ-1.6 | TS-74-6 | 2.1-2.4 | tests/unit/session/test_review_parse_resilience.py |
| 74-REQ-1.E1 | — | 2.1-2.4 | Manual review (replaces existing instructions) |
| 74-REQ-2.1 | TS-74-7, TS-74-P1 | 3.1 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-2.2 | TS-74-8, TS-74-P5 | 3.1 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-2.3 | TS-74-9, TS-74-P5 | 3.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-2.4 | TS-74-10, TS-74-P2 | 3.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-2.5 | TS-74-11, TS-74-P6 | 3.4 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-2.E1 | TS-74-12, TS-74-E1, TS-74-E2 | 3.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-2.E2 | TS-74-13 | 3.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-3.1 | TS-74-14 | 4.2 | tests/integration/test_review_parse_resilience.py |
| 74-REQ-3.2 | TS-74-15 | 4.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-3.3 | TS-74-16, TS-74-P3 | 4.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-3.4 | TS-74-17 | 4.2 | tests/integration/test_review_parse_resilience.py |
| 74-REQ-3.5 | TS-74-14 | 4.2 | tests/integration/test_review_parse_resilience.py |
| 74-REQ-3.E1 | TS-74-18, TS-74-P3 | 4.2 | tests/integration/test_review_parse_resilience.py |
| 74-REQ-3.E2 | TS-74-19 | 4.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.1 | TS-74-20, TS-74-P4 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.2 | TS-74-21, TS-74-P4 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.3 | TS-74-22, TS-74-P4 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.4 | TS-74-23 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.5 | TS-74-24 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.E1 | TS-74-25 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-4.E2 | TS-74-E3 | 4.3 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-5.1 | TS-74-26 | 4.1, 4.2 | tests/unit/engine/test_review_parse_resilience.py |
| 74-REQ-5.2 | TS-74-18 | 4.2 | tests/integration/test_review_parse_resilience.py |
| 74-REQ-5.3 | TS-74-27 | 4.2 | tests/unit/engine/test_review_parse_resilience.py |

## Notes

- Task group 2 (prompts) has no code dependencies — only template files change.
- Task group 3 (parser tolerance) is pure Python with no async or I/O.
- Task group 4 (retry + convergence) involves async session interaction and
  will need mock backends for testing.
- The format retry requires `persist_review_findings()` to accept a session
  handle or backend reference. This is a signature change that needs careful
  wiring from `session_lifecycle.py`.
