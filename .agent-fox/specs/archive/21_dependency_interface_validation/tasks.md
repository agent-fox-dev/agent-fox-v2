# Implementation Plan: Dependency Interface Validation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md -- all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec adds a `stale-dependency` AI lint rule that validates cross-spec
dependency Relationship references against upstream `design.md` files, plus
an auto-fixer that applies AI-suggested corrections. Four task groups:
tests, identifier extraction + AI validation, auto-fixer, and integration.

## Test Commands

- Unit tests: `uv run pytest tests/unit/spec/test_stale_dependency.py -q`
- All spec tests: `uv run pytest tests/unit/spec/test_stale_dependency.py -q`
- Linter: `uv run ruff check agent_fox/spec/ai_validator.py agent_fox/spec/fixer.py tests/unit/spec/test_stale_dependency.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
    - `tests/unit/spec/conftest.py` (extend): add fixtures for prd.md files
      with alt-format dependency tables containing various Relationship text
    - Fixture variants: backtick identifiers, no backticks, parenthesized
      methods, dotted paths, standard library refs, multiple rows to same
      upstream spec, fixable stale refs
    - _Test Spec: TS-21-1 through TS-21-5, TS-21-15 through TS-21-18_

  - [x] 1.2 Write identifier extraction tests
    - `tests/unit/spec/test_stale_dependency.py`: TS-21-1 (backtick
      extraction), TS-21-2 (parenthesis stripping), TS-21-3 (dotted paths),
      TS-21-4 (no backticks skip), TS-21-5 (stdlib extracted)
    - _Test Spec: TS-21-1 through TS-21-5_
    - _Requirements: 21-REQ-1.*_

  - [x] 1.3 Write AI validation tests
    - `tests/unit/spec/test_stale_dependency.py`: TS-21-6 (found identifier),
      TS-21-7 (unfound identifier with suggestion), TS-21-8 (missing
      design.md), TS-21-9 (AI unavailable), TS-21-10 (malformed response)
    - Mock the Anthropic client for all AI tests
    - _Test Spec: TS-21-6 through TS-21-10_
    - _Requirements: 21-REQ-2.*_

  - [x] 1.4 Write batching and integration tests
    - `tests/unit/spec/test_stale_dependency.py`: TS-21-11 (batch same
      upstream), TS-21-12 (no backticks zero calls), TS-21-13 (finding
      severity/format), TS-21-14 (separate upstream specs)
    - _Test Spec: TS-21-11 through TS-21-14_
    - _Requirements: 21-REQ-3.*, 21-REQ-4.*_

  - [x] 1.5 Write auto-fix tests
    - `tests/unit/spec/test_stale_dependency.py`: TS-21-15 (replace stale
      identifier), TS-21-16 (skip no suggestion), TS-21-17 (skip already
      present), TS-21-18 (preserve surrounding text)
    - _Test Spec: TS-21-15 through TS-21-18_
    - _Requirements: 21-REQ-5.*_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced

- [x] 2. Implement identifier extraction and AI validation
  - [x] 2.1 Add DependencyRef dataclass
    - `agent_fox/spec/ai_validator.py`: add `DependencyRef` frozen dataclass
    - _Requirements: 21-REQ-1.1_

  - [x] 2.2 Implement extract_relationship_identifiers()
    - `agent_fox/spec/ai_validator.py`: parse alt-format dependency tables,
      extract backtick tokens, normalize (strip trailing parens, preserve
      dots)
    - Reuse `_DEP_TABLE_HEADER_ALT` and `_TABLE_SEP` patterns from parser.py
    - _Requirements: 21-REQ-1.1, 21-REQ-1.2, 21-REQ-1.3, 21-REQ-1.E1,
      21-REQ-1.E2_

  - [x] 2.3 Implement validate_dependency_interfaces()
    - `agent_fox/spec/ai_validator.py`: build AI prompt with design.md content
      and identifier list, send to model, parse JSON response, produce
      Warning findings for unresolved identifiers
    - Follow same async client pattern as `analyze_acceptance_criteria()`
    - Ensure finding message format includes identifier and suggestion in
      parseable format for the fixer
    - _Requirements: 21-REQ-2.1, 21-REQ-2.3, 21-REQ-2.4, 21-REQ-2.5,
      21-REQ-2.E3_

  - [x] 2.4 Implement run_stale_dependency_validation()
    - `agent_fox/spec/ai_validator.py`: orchestrate extraction, batching by
      upstream spec, design.md reading, and AI validation
    - Read each upstream design.md at most once
    - Skip upstream specs without design.md
    - Graceful degradation on AI unavailability
    - _Requirements: 21-REQ-2.2, 21-REQ-2.E1, 21-REQ-2.E2, 21-REQ-3.1,
      21-REQ-3.2, 21-REQ-3.E1_

  - [x] 2.V Verify task group 2
    - [x] Extraction tests pass (TS-21-1 through TS-21-5)
    - [x] AI validation tests pass (TS-21-6 through TS-21-10)
    - [x] Batching tests pass (TS-21-11, TS-21-12, TS-21-14)
    - [x] No linter warnings

- [x] 3. Implement auto-fixer
  - [x] 3.1 Add IdentifierFix dataclass
    - `agent_fox/spec/fixer.py`: add `IdentifierFix` frozen dataclass
    - _Requirements: 21-REQ-5.1_

  - [x] 3.2 Implement fix_stale_dependency()
    - `agent_fox/spec/fixer.py`: read prd.md, find backtick-delimited
      original identifier, replace with suggestion, write back
    - Skip when suggestion is empty, when original not found, when
      suggestion already present
    - _Requirements: 21-REQ-5.1, 21-REQ-5.2, 21-REQ-5.E1, 21-REQ-5.E3_

  - [x] 3.3 Register stale-dependency in FIXABLE_RULES
    - `agent_fox/spec/fixer.py`: add `"stale-dependency"` to FIXABLE_RULES
    - Update `apply_fixes()` to handle stale-dependency: parse identifier
      and suggestion from finding message, construct IdentifierFix, call
      fix_stale_dependency()
    - _Requirements: 21-REQ-5.3, 21-REQ-5.4_

  - [x] 3.V Verify task group 3
    - [x] Fix tests pass (TS-21-15 through TS-21-18)
    - [x] No linter warnings
    - [x] Existing fixer tests still pass (no regressions)

- [x] 4. Integrate with lint-spec pipeline
  - [x] 4.1 Wire into run_ai_validation()
    - `agent_fox/spec/ai_validator.py`: update `run_ai_validation()` to accept
      `specs_dir` parameter and call `run_stale_dependency_validation()`
    - _Requirements: 21-REQ-4.1_

  - [x] 4.2 Update lint-spec CLI
    - `agent_fox/cli/lint_spec.py`: pass `specs_dir` to `run_ai_validation()`
    - Ensure `--fix --ai` triggers stale-dependency fixes via apply_fixes()
    - _Requirements: 21-REQ-4.1, 21-REQ-4.2, 21-REQ-5.E2_

  - [x] 4.3 Verify integration
    - Run `agent-fox lint-spec --ai` and confirm stale-dependency findings
      appear alongside existing findings
    - Run `agent-fox lint-spec --fix --ai` and confirm stale identifiers are
      corrected in prd.md
    - Verify Warning severity does not cause non-zero exit code
    - _Requirements: 21-REQ-4.2, 21-REQ-4.3_

  - [x] 4.V Verify task group 4
    - [x] Integration test passes (TS-21-13)
    - [x] All existing lint-spec tests still pass (no regressions)
    - [x] All existing AI validation tests still pass
    - [x] All existing fixer tests still pass
    - [x] No linter warnings

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 21-REQ-1.1 | TS-21-1 | 2.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-1.2 | TS-21-2 | 2.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-1.3 | TS-21-3 | 2.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-1.E1 | TS-21-4 | 2.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-1.E2 | TS-21-5 | 2.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.1 | TS-21-6 | 2.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.2 | TS-21-8, TS-21-11 | 2.4 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.3 | TS-21-6 | 2.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.4 | TS-21-7 | 2.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.5 | TS-21-7 | 2.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.E1 | TS-21-8 | 2.4 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.E2 | TS-21-9 | 2.4 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-2.E3 | TS-21-10 | 2.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-3.1 | TS-21-11, TS-21-14 | 2.4 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-3.2 | TS-21-11 | 2.4 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-3.E1 | TS-21-12 | 2.4 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-4.1 | TS-21-13 | 4.1 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-4.2 | TS-21-13 | 4.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-4.3 | TS-21-13 | 4.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-5.1 | TS-21-15 | 3.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-5.2 | TS-21-15, TS-21-18 | 3.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-5.3 | -- | 3.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-5.4 | TS-21-15 | 3.3 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-5.E1 | TS-21-16 | 3.2 | tests/unit/spec/test_stale_dependency.py |
| 21-REQ-5.E2 | -- | 4.2 | integration |
| 21-REQ-5.E3 | TS-21-17 | 3.2 | tests/unit/spec/test_stale_dependency.py |

## Notes

- The `stale-dependency` rule follows the same async pattern as
  `analyze_acceptance_criteria()` in `ai_validator.py`. Reuse the client
  creation, response parsing, and error handling patterns.
- The `DependencyRef` dataclass is intentionally separate from `CrossSpecDep`
  because it carries the identifier and relationship text, which `CrossSpecDep`
  does not store.
- Import `_DEP_TABLE_HEADER_ALT` and `_TABLE_SEP` from `parser.py` rather
  than duplicating the regex patterns.
- The standard dependency table format (`| This Spec | Depends On |`) does not
  have a Relationship column, so it is not checked by this rule. If a spec
  has a coarse dependency table, the coarse-dependency fixer (spec 20) should
  be run first to convert it to alt format, which adds a Relationship column.
- The fixer parses the original identifier and suggestion from the finding
  message text using regex, since `Finding` is a frozen dataclass and we
  avoid modifying its interface. The message format is designed to be
  machine-parseable: `"identifier \`{id}\` not found ... Suggestion: {sug}"`.
- Task group 1 writes all 18 test cases. Task group 2 implements extraction
  and validation. Task group 3 implements the auto-fixer. Task group 4 wires
  integration.
- This spec depends on spec 20's `fixer.py` module being implemented first
  (specifically `FIXABLE_RULES`, `FixResult`, and `apply_fixes()`).
