# Implementation Plan: Fix Pipeline Triage & Reviewer Archetypes

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan replaces the skeptic and verifier archetypes in the fix pipeline
with triage and fix_reviewer. Implementation proceeds in five groups:
(1) failing tests, (2) data types and parsers, (3) prompt templates and
archetype registration, (4) fix pipeline rewrite with retry/escalation,
(5) wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_fix_pipeline_triage.py tests/unit/session/test_triage_parser.py tests/unit/test_archetype_registry.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/nightshift/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create parser test file
    - Create `tests/unit/session/test_triage_parser.py`
    - Translate TS-82-3 through TS-82-5 (triage parsing)
    - Translate TS-82-8, TS-82-9 (reviewer parsing)
    - Translate TS-82-E1, TS-82-E3, TS-82-E4 (edge cases)
    - _Test Spec: TS-82-3, TS-82-4, TS-82-5, TS-82-8, TS-82-9, TS-82-E1, TS-82-E3, TS-82-E4_

  - [ ] 1.2 Create archetype registry test additions
    - Add tests to existing `tests/unit/test_archetype_registry.py` or create
      if absent
    - Translate TS-82-1 (triage registration) and TS-82-6 (fix_reviewer
      registration)
    - Translate TS-82-2 (triage prompt) and TS-82-7 (reviewer prompt)
    - _Test Spec: TS-82-1, TS-82-2, TS-82-6, TS-82-7_

  - [ ] 1.3 Create pipeline test file
    - Create `tests/unit/nightshift/test_fix_pipeline_triage.py`
    - Translate TS-82-10 through TS-82-20 (pipeline behavior, comments,
      retry, escalation, error handling)
    - _Test Spec: TS-82-10 through TS-82-20_

  - [ ] 1.4 Create property test file
    - Create `tests/property/test_fix_triage_properties.py`
    - Translate TS-82-P1 through TS-82-P4
    - _Test Spec: TS-82-P1, TS-82-P2, TS-82-P3, TS-82-P4_

  - [ ] 1.5 Create integration smoke test file
    - Create `tests/integration/nightshift/test_fix_pipeline_smoke.py`
    - Translate TS-82-SMOKE-1 through TS-82-SMOKE-3
    - _Test Spec: TS-82-SMOKE-1, TS-82-SMOKE-2, TS-82-SMOKE-3_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check`

- [ ] 2. Data types and parse functions
  - [ ] 2.1 Define data types
    - Add `AcceptanceCriterion`, `TriageResult`, `FixReviewVerdict`, and
      `FixReviewResult` dataclasses
    - Place in `agent_fox/nightshift/fix_pipeline.py` or a new
      `agent_fox/nightshift/fix_types.py` if cleaner
    - _Requirements: 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3, 82-REQ-5.1_

  - [ ] 2.2 Implement `parse_triage_output()`
    - Add to `agent_fox/session/review_parser.py`
    - Use existing `_unwrap_items()` with wrapper key
      `"acceptance_criteria"`
    - Validate required fields per criterion, skip incomplete
    - Extract top-level `summary` and `affected_files`
    - Return `TriageResult`
    - _Requirements: 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3, 82-REQ-2.E1_

  - [ ] 2.3 Implement `parse_fix_review_output()`
    - Add to `agent_fox/session/review_parser.py`
    - Use existing `_unwrap_items()` with wrapper key `"verdicts"`
    - Validate verdict values (PASS/FAIL only), skip invalid
    - Enforce overall_verdict=FAIL if any verdict is FAIL
    - Default to FAIL on parse failure
    - Return `FixReviewResult`
    - _Requirements: 82-REQ-5.1_

  - [ ] 2.4 Extend `_resolve_wrapper_key()` variant map
    - Add `"acceptance_criteria": {"acceptance_criteria", "criteria", "test_cases"}`
    - _Requirements: 82-REQ-2.1_

  - [ ] 2.V Verify task group 2
    - [ ] Parser tests pass: `uv run pytest -q tests/unit/session/test_triage_parser.py`
    - [ ] Property tests TS-82-P1 and TS-82-P2 pass: `uv run pytest -q tests/property/test_fix_triage_properties.py -k "P1 or P2"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 82-REQ-2.1, 2.2, 2.3, 2.E1, 5.1 met

- [ ] 3. Prompt templates and archetype registration
  - [ ] 3.1 Create `triage.md` prompt template
    - Place in `agent_fox/_templates/prompts/triage.md`
    - Follow same structure as existing archetype templates (frontmatter,
      role description, orientation, scope lock, output format, constraints,
      critical reminders)
    - Direct agent to: explore codebase, analyze issue, produce acceptance
      criteria in test_spec.md format
    - Specify JSON output schema with `acceptance_criteria` wrapper key
    - Include `{spec_name}` interpolation placeholder
    - _Requirements: 82-REQ-1.2, 82-REQ-2.4_

  - [ ] 3.2 Create `fix_reviewer.md` prompt template
    - Place in `agent_fox/_templates/prompts/fix_reviewer.md`
    - Follow same structure as existing archetype templates
    - Direct agent to: verify coder's changes against acceptance criteria,
      run test suite, produce per-criterion PASS/FAIL verdicts
    - Specify JSON output schema with `verdicts` wrapper key
    - Include `{spec_name}` interpolation placeholder
    - Handle no-criteria fallback (82-REQ-5.E1): instruct to verify from
      issue description
    - _Requirements: 82-REQ-4.2, 82-REQ-5.2, 82-REQ-5.3, 82-REQ-5.E1_

  - [ ] 3.3 Register archetypes in registry
    - Add `"triage"` entry to `ARCHETYPE_REGISTRY` in `archetypes.py`:
      template=`triage.md`, tier=ADVANCED, read-only allowlist, max_turns=80
    - Add `"fix_reviewer"` entry: template=`fix_reviewer.md`, tier=ADVANCED,
      full allowlist (uv, make, pytest, etc.), max_turns=120
    - _Requirements: 82-REQ-1.1, 82-REQ-4.1_

  - [ ] 3.V Verify task group 3
    - [ ] Registry tests pass: `uv run pytest -q tests/unit/test_archetype_registry.py`
    - [ ] Prompt template tests TS-82-2, TS-82-7 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 82-REQ-1.1, 1.2, 4.1, 4.2 met

- [ ] 4. Fix pipeline rewrite
  - [ ] 4.1 Add comment formatting methods
    - Implement `_format_triage_comment(triage_result)` → markdown string
    - Implement `_format_review_comment(review_result)` → markdown string
    - _Requirements: 82-REQ-3.1, 82-REQ-6.1_

  - [ ] 4.2 Add prompt building methods
    - Implement `_build_coder_prompt(spec, triage, review_feedback=None)`
    - Implement `_build_reviewer_prompt(spec, triage)`
    - Coder prompt injects criteria as structured context (82-REQ-7.2)
    - Coder prompt injects reviewer evidence on retry (82-REQ-8.1)
    - Reviewer prompt includes criteria for verification (82-REQ-7.3)
    - Handle empty triage result (82-REQ-5.E1, 82-REQ-7.E1)
    - _Requirements: 82-REQ-7.2, 82-REQ-7.3, 82-REQ-8.1, 82-REQ-5.E1_

  - [ ] 4.3 Add coder session runner with model override
    - Implement `_run_coder_session(spec, system_prompt, task_prompt, model_id=None)`
    - Pass `model_id` override to `run_session()` for escalation
    - _Requirements: 82-REQ-8.3_

  - [ ] 4.4 Implement triage runner
    - Implement `_run_triage(spec)` → `TriageResult`
    - Run triage session, parse output, post comment
    - Catch exceptions and return empty TriageResult on failure (82-REQ-7.E1)
    - Catch comment posting errors (82-REQ-3.E1)
    - _Requirements: 82-REQ-3.1, 82-REQ-3.E1, 82-REQ-7.E1_

  - [ ] 4.5 Implement coder-reviewer loop
    - Implement `_coder_review_loop(spec, triage, metrics)` → `bool`
    - Instantiate `EscalationLadder` from config (82-REQ-8.2)
    - Loop: build coder prompt → run coder → build reviewer prompt →
      run reviewer → parse verdict → post comment
    - On FAIL: `ladder.record_failure()`, inject feedback, retry
    - On exhaustion: post failure comment, return False (82-REQ-8.4)
    - On PASS: return True
    - Catch comment posting errors (82-REQ-6.E1)
    - _Requirements: 82-REQ-7.1, 82-REQ-8.1, 82-REQ-8.2, 82-REQ-8.3,
      82-REQ-8.4, 82-REQ-8.E1_

  - [ ] 4.6 Rewrite `process_issue()`
    - Replace `("skeptic", "coder", "verifier")` loop with:
      1. `_run_triage(spec)` → `TriageResult`
      2. `_coder_review_loop(spec, triage, metrics)` → success bool
    - Keep existing branch creation, harvest, and close logic
    - _Requirements: 82-REQ-7.1_

  - [ ] 4.V Verify task group 4
    - [ ] Pipeline tests pass: `uv run pytest -q tests/unit/nightshift/test_fix_pipeline_triage.py`
    - [ ] Property tests TS-82-P3, TS-82-P4 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 82-REQ-3.1, 3.E1, 6.1, 6.E1, 7.1, 7.2, 7.3, 7.E1,
      8.1, 8.2, 8.3, 8.4, 8.E1 met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1: process_issue → _run_triage → _run_session("triage") →
      parse_triage_output → _format_triage_comment → add_issue_comment
    - Path 2: _build_coder_prompt → _run_coder_session → run_session
    - Path 3: _build_reviewer_prompt → _run_session("fix_reviewer") →
      parse_fix_review_output → _format_review_comment → add_issue_comment
    - Path 4: _coder_review_loop → EscalationLadder.record_failure →
      _build_coder_prompt(review_feedback=...) → retry
    - Confirm no function in any chain is a stub
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - `parse_triage_output` → `TriageResult` → consumed by
      `_build_coder_prompt` and `_build_reviewer_prompt`
    - `parse_fix_review_output` → `FixReviewResult` → consumed by
      `_coder_review_loop` for verdict check and feedback injection
    - `EscalationLadder.current_tier` → `ModelTier` → passed to
      `_run_coder_session` as model_id
    - Grep for callers, confirm none discards the return
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All TS-82-SMOKE-* tests pass using real pipeline code (not stubbed)
    - _Test Spec: TS-82-SMOKE-1, TS-82-SMOKE-2, TS-82-SMOKE-3_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit: justified or replaced
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check`

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
| 82-REQ-1.1 | TS-82-1 | 3.3 | test_archetype_registry.py |
| 82-REQ-1.2 | TS-82-2 | 3.1, 3.3 | test_archetype_registry.py |
| 82-REQ-2.1 | TS-82-3, TS-82-E3 | 2.2, 2.4 | test_triage_parser.py |
| 82-REQ-2.2 | TS-82-3, TS-82-4 | 2.1, 2.2 | test_triage_parser.py |
| 82-REQ-2.3 | TS-82-3 | 2.2 | test_triage_parser.py |
| 82-REQ-2.4 | TS-82-2 | 3.1 | test_archetype_registry.py |
| 82-REQ-2.E1 | TS-82-5, TS-82-E1 | 2.2 | test_triage_parser.py |
| 82-REQ-3.1 | TS-82-13 | 4.1, 4.4 | test_fix_pipeline_triage.py |
| 82-REQ-3.E1 | TS-82-19 | 4.4 | test_fix_pipeline_triage.py |
| 82-REQ-4.1 | TS-82-6 | 3.3 | test_archetype_registry.py |
| 82-REQ-4.2 | TS-82-7 | 3.2, 3.3 | test_archetype_registry.py |
| 82-REQ-5.1 | TS-82-8, TS-82-9, TS-82-E4 | 2.3 | test_triage_parser.py |
| 82-REQ-5.2 | TS-82-SMOKE-1 | 3.2 | test_fix_pipeline_smoke.py |
| 82-REQ-5.3 | TS-82-12 | 4.2 | test_fix_pipeline_triage.py |
| 82-REQ-5.E1 | TS-82-E2 | 3.2, 4.2 | test_fix_pipeline_triage.py |
| 82-REQ-6.1 | TS-82-14 | 4.1, 4.5 | test_fix_pipeline_triage.py |
| 82-REQ-6.E1 | TS-82-19 | 4.5 | test_fix_pipeline_triage.py |
| 82-REQ-7.1 | TS-82-10 | 4.6 | test_fix_pipeline_triage.py |
| 82-REQ-7.2 | TS-82-11 | 4.2 | test_fix_pipeline_triage.py |
| 82-REQ-7.3 | TS-82-12 | 4.2 | test_fix_pipeline_triage.py |
| 82-REQ-7.E1 | TS-82-18 | 4.4 | test_fix_pipeline_triage.py |
| 82-REQ-8.1 | TS-82-15 | 4.2, 4.5 | test_fix_pipeline_triage.py |
| 82-REQ-8.2 | TS-82-16 | 4.5 | test_fix_pipeline_triage.py |
| 82-REQ-8.3 | TS-82-16 | 4.5 | test_fix_pipeline_triage.py |
| 82-REQ-8.4 | TS-82-17 | 4.5 | test_fix_pipeline_triage.py |
| 82-REQ-8.E1 | TS-82-20 | 4.5 | test_fix_pipeline_triage.py |
| Property 1 | TS-82-P1 | 2.2 | test_fix_triage_properties.py |
| Property 2 | TS-82-P2 | 2.3 | test_fix_triage_properties.py |
| Property 3 | TS-82-P3 | 4.5 | test_fix_triage_properties.py |
| Property 4 | TS-82-P4 | 4.2 | test_fix_triage_properties.py |
| Property 5 | TS-82-P5 | 4.5, 4.6 | test_fix_triage_properties.py |
| Property 6 | TS-82-P6 | 4.4, 4.5 | test_fix_triage_properties.py |

## Notes

- The spec-based pipeline (skeptic/verifier) is unchanged by this spec.
- Existing fix pipeline tests in `tests/unit/nightshift/` may need updating
  if they assert the old archetype sequence. Update them to expect the new
  sequence, or mark them as superseded by the new test files.
- The `InMemorySpec` dataclass is not modified — triage results flow as a
  separate `TriageResult` object through pipeline methods.
