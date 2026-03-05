# Implementation Plan: AI-Powered Criteria Auto-Fix

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in four groups: (1) write failing tests, (2) implement
the AI rewrite function, (3) implement the criteria fixer and CLI integration,
(4) checkpoint. The rewrite function and fixer are separate modules following
the existing validator/fixer separation.

## Test Commands

- Spec tests: `uv run pytest tests/unit/spec/test_ai_criteria_fix.py -q`
- Property tests: `uv run pytest tests/property/spec/test_ai_criteria_fix_props.py -q`
- Integration tests: `uv run pytest tests/integration/test_ai_criteria_fix.py -q`
- All spec tests: `uv run pytest tests/unit/spec/ tests/property/spec/ tests/integration/test_lint_spec.py tests/integration/test_lint_fix.py -q`
- Linter: `uv run ruff check agent_fox/spec/ tests/unit/spec/ tests/property/spec/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for rewrite function
    - Create `tests/unit/spec/test_ai_criteria_fix.py`
    - Mock Anthropic client, test `rewrite_criteria()` return values
    - _Test Spec: TS-22-1, TS-22-6, TS-22-7, TS-22-8, TS-22-9, TS-22-10, TS-22-12_

  - [x] 1.2 Create unit tests for criteria fixer
    - Test `fix_ai_criteria()` with bracket and bold ID formats
    - Test FixResult rule names
    - _Test Spec: TS-22-2, TS-22-3, TS-22-4, TS-22-11_

  - [x] 1.3 Create edge case tests
    - API failure, missing criterion ID, fenced JSON, omitted response
    - _Test Spec: TS-22-E1, TS-22-E2, TS-22-E3, TS-22-E4_

  - [x] 1.4 Create property tests
    - Requirement ID round-trip, file integrity, EARS prompt keywords
    - Create `tests/property/spec/test_ai_criteria_fix_props.py`
    - _Test Spec: TS-22-P1, TS-22-P2, TS-22-P3_

  - [x] 1.5 Create integration test
    - Test full CLI flow with mocked AI responses
    - Create `tests/integration/test_ai_criteria_fix.py`
    - _Test Spec: TS-22-5, TS-22-E5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement AI rewrite function
  - [x] 2.1 Define the rewrite prompt template
    - Add `_REWRITE_PROMPT` constant to `agent_fox/spec/ai_validator.py`
    - Include EARS keywords, full requirements text placeholder, flagged criteria list
    - Specify JSON response format: `{"rewrites": [{"criterion_id": "...", "original": "...", "replacement": "..."}]}`
    - _Requirements: 22-REQ-2.1, 22-REQ-2.2, 22-REQ-2.3, 22-REQ-2.4, 22-REQ-2.5_

  - [x] 2.2 Implement `rewrite_criteria()` async function
    - Accept spec_name, requirements_text, findings, model
    - Extract criterion IDs and issue descriptions from findings
    - Short-circuit on empty findings list (22-REQ-3.2)
    - Send prompt to STANDARD model, parse JSON response with `_extract_json`
    - Return `dict[str, str]` mapping criterion_id -> replacement_text
    - _Requirements: 22-REQ-1.1, 22-REQ-3.1, 22-REQ-3.3_

  - [x] 2.3 Handle rewrite errors
    - Catch API exceptions, return empty dict (22-REQ-1.E1)
    - Handle malformed JSON via `_extract_json` (22-REQ-2.E1)
    - Skip omitted criterion IDs in response (22-REQ-2.E2)
    - _Requirements: 22-REQ-1.E1, 22-REQ-2.E1, 22-REQ-2.E2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for rewrite function pass: `uv run pytest tests/unit/spec/test_ai_criteria_fix.py -k "rewrite" -q`
    - [x] All existing tests still pass: `uv run pytest tests/unit/spec/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/spec/ai_validator.py`
    - [x] Requirements 22-REQ-1.1, 22-REQ-2.*, 22-REQ-3.* acceptance criteria met

- [x] 3. Implement criteria fixer and CLI integration
  - [x] 3.1 Implement `fix_ai_criteria()` in fixer module
    - Add to `agent_fox/spec/fixer.py`
    - Locate criterion by ID (support both `[ID]` and `**ID:**` formats)
    - Replace criterion text from ID to end-of-criterion boundary
    - Preserve the ID prefix in output
    - Return list of FixResult with rule from original finding
    - _Requirements: 22-REQ-1.2, 22-REQ-1.3, 22-REQ-1.E2_

  - [x] 3.2 Extract finding metadata for rewrite
    - Parse criterion_id and issue_type from Finding.message format `[criterion_id] explanation`
    - Map rule name to FixResult rule (vague-criterion, implementation-leak)
    - _Requirements: 22-REQ-4.3_

  - [x] 3.3 Wire AI rewrite into lint-spec CLI
    - In `lint_spec()`, after AI analysis and before mechanical fixes:
      if `ai and fix`, group AI criteria findings by spec, call `rewrite_criteria()` per spec, call `fix_ai_criteria()`, extend fix results
    - Ensure `--fix` without `--ai` does not trigger rewrite (22-REQ-1.4)
    - _Requirements: 22-REQ-1.4, 22-REQ-4.1, 22-REQ-4.2_

  - [x] 3.4 Handle batch splitting for large specs
    - Split findings into batches of 20 per rewrite call (22-REQ-3.E1)
    - _Requirements: 22-REQ-3.E1_

  - [x] 3.V Verify task group 3
    - [x] All spec tests pass: `uv run pytest tests/unit/spec/test_ai_criteria_fix.py tests/property/spec/test_ai_criteria_fix_props.py tests/integration/test_ai_criteria_fix.py -q`
    - [x] All existing tests still pass: `uv run pytest tests/unit/spec/ tests/integration/test_lint_spec.py tests/integration/test_lint_fix.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/spec/ agent_fox/cli/lint_spec.py`
    - [x] Requirements 22-REQ-1.*, 22-REQ-4.* acceptance criteria met

- [x] 4. Checkpoint — AI Criteria Fix Complete
  - Ensure all tests pass: `uv run pytest tests/unit/spec/ tests/property/spec/ tests/integration/ -q`
  - All lints clean: `uv run ruff check agent_fox/spec/ agent_fox/cli/ tests/`
  - Type check clean: `uv run mypy agent_fox/spec/ai_validator.py agent_fox/spec/fixer.py agent_fox/cli/lint_spec.py`
  - Update documentation in `docs/cli-reference.md` for `--ai --fix` behavior

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 22-REQ-1.1 | TS-22-1 | 2.2 | `test_ai_criteria_fix.py::test_rewrite_produces_replacement` |
| 22-REQ-1.2 | TS-22-2 | 3.1 | `test_ai_criteria_fix.py::test_rewrite_applied_to_file` |
| 22-REQ-1.3 | TS-22-3, TS-22-4 | 3.1 | `test_ai_criteria_fix.py::test_bracket_id_preserved`, `test_bold_id_preserved` |
| 22-REQ-1.4 | TS-22-5 | 3.3 | `test_ai_criteria_fix.py::test_no_rewrite_without_ai_flag` |
| 22-REQ-1.E1 | TS-22-E1 | 2.3 | `test_ai_criteria_fix.py::test_api_failure_leaves_file_unchanged` |
| 22-REQ-1.E2 | TS-22-E2 | 3.1 | `test_ai_criteria_fix.py::test_missing_criterion_skipped` |
| 22-REQ-2.1 | TS-22-6 | 2.1 | `test_ai_criteria_fix.py::test_ears_keywords_in_prompt` |
| 22-REQ-2.4 | TS-22-7 | 2.1 | `test_ai_criteria_fix.py::test_prompt_includes_full_requirements` |
| 22-REQ-2.5 | TS-22-8 | 2.2 | `test_ai_criteria_fix.py::test_response_json_parsed` |
| 22-REQ-2.E1 | TS-22-E3 | 2.3 | `test_ai_criteria_fix.py::test_fenced_json_parsed` |
| 22-REQ-2.E2 | TS-22-E4 | 2.3 | `test_ai_criteria_fix.py::test_omitted_criterion_skipped` |
| 22-REQ-3.1 | TS-22-9 | 2.2 | `test_ai_criteria_fix.py::test_batching_one_call_per_spec` |
| 22-REQ-3.2 | TS-22-10 | 2.2 | `test_ai_criteria_fix.py::test_no_call_without_findings` |
| 22-REQ-3.3 | TS-22-12 | 2.2 | `test_ai_criteria_fix.py::test_standard_model_used` |
| 22-REQ-3.E1 | — | 3.4 | `test_ai_criteria_fix.py::test_batch_splitting` |
| 22-REQ-4.1 | TS-22-11 | 3.2 | `test_ai_criteria_fix.py::test_fix_result_rule_names` |
| 22-REQ-4.E1 | TS-22-E5 | 3.3 | `test_ai_criteria_fix.py::test_no_re_rewrite` |
| Property 1 | TS-22-P1 | 3.1 | `test_ai_criteria_fix_props.py::test_id_roundtrip` |
| Property 2 | TS-22-P2 | 3.1 | `test_ai_criteria_fix_props.py::test_file_integrity` |
| Property 5 | TS-22-P3 | 2.1 | `test_ai_criteria_fix_props.py::test_ears_in_prompt` |

## Notes

- All AI calls are mocked in tests — no live API calls.
- The rewrite function lives in `ai_validator.py` alongside the existing analysis functions; the fixer lives in `fixer.py` alongside existing fixers. This maintains the validator-detects/fixer-corrects separation.
- The 20-criterion batch limit (22-REQ-3.E1) is a safety valve, not expected in normal use. Most specs have 5-15 criteria total.
