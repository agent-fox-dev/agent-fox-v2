# Implementation Plan: Fix-Coder Archetype

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Three implementation groups: (1) write failing tests, (2) create the template
and archetype registration, (3) update the fix pipeline and run wiring
verification. The template is standalone (copy-and-diverge from coding.md).

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_fix_coder.py tests/unit/test_fix_coder_archetype.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file `tests/unit/test_fix_coder_archetype.py`
    - Template loading test (TS-88-1)
    - Template content assertions: no .specs/ (TS-88-2), commit format (TS-88-3),
      git workflow (TS-88-4), quality gates (TS-88-5), no session artifacts (TS-88-6)
    - Registry tests: entry exists (TS-88-7), defaults match coder (TS-88-8),
      not task-assignable (TS-88-9)
    - Edge cases: interpolation (TS-88-E1), fallback (TS-88-E2)
    - _Test Spec: TS-88-1 through TS-88-9, TS-88-E1, TS-88-E2_

  - [ ] 1.2 Create test file `tests/unit/nightshift/test_fix_coder.py`
    - Fix pipeline tests: _build_coder_prompt archetype (TS-88-10), no commit
      format in task prompt (TS-88-11), _run_coder_session archetype (TS-88-12)
    - _Test Spec: TS-88-10 through TS-88-12_

  - [ ] 1.3 Add property tests to `tests/property/test_fix_coder_props.py`
    - Template isolation under interpolation (TS-88-P1)
    - Registry parity (TS-88-P2)
    - SDK parameter parity (TS-88-P3)
    - _Test Spec: TS-88-P1 through TS-88-P3_

  - [ ] 1.4 Add integration smoke test to `tests/integration/test_fix_coder_smoke.py`
    - Full prompt build + session invocation (TS-88-SMOKE-1)
    - _Test Spec: TS-88-SMOKE-1_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`

- [ ] 2. Create fix_coding.md template and register archetype
  - [ ] 2.1 Create `agent_fox/_templates/prompts/fix_coding.md`
    - Copy `coding.md` as starting point, then diverge
    - Replace role description: "Fix Coder" for issue-driven fixes
    - Remove: TASK LOCK section (task groups), IMPLEMENT group-based workflow,
      SESSION SUMMARY, SESSION LEARNINGS, tasks.md references
    - Add: issue-focused IMPLEMENT section (read issue, implement fix directly)
    - Add: `fix(#<N>, nightshift): <description>` commit format in GIT WORKFLOW
    - Keep: ORIENTATION, GIT WORKFLOW (adapted), QUALITY GATES, REMINDERS
    - Verify: no `.specs/` or `tasks.md` references remain
    - _Requirements: 88-REQ-1.1 through 88-REQ-1.6, 88-REQ-1.E1_

  - [ ] 2.2 Add `fix_coder` entry to `ARCHETYPE_REGISTRY` in `archetypes.py`
    - `templates=["fix_coding.md"]`
    - Same defaults as `coder`: STANDARD, 300 turns, adaptive, 64000 budget
    - `task_assignable=False`
    - _Requirements: 88-REQ-2.1 through 88-REQ-2.3_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests TS-88-1 through TS-88-9 pass
    - [ ] Property tests TS-88-P1, TS-88-P2 pass
    - [ ] Edge case tests TS-88-E1, TS-88-E2 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/`

- [ ] 3. Update fix pipeline and wiring verification
  - [ ] 3.1 Update `_build_coder_prompt()` in `fix_pipeline.py`
    - Change `archetype="coder"` to `archetype="fix_coder"`
    - Remove the hardcoded commit format lines appended to task_prompt
    - _Requirements: 88-REQ-3.1, 88-REQ-3.3_

  - [ ] 3.2 Update `_run_coder_session()` in `fix_pipeline.py`
    - Change `"coder"` to `"fix_coder"` in the `_run_session()` call
    - _Requirements: 88-REQ-3.2_

  - [ ] 3.3 Trace execution path end-to-end
    - Verify `_build_coder_prompt` → `build_system_prompt` → `get_archetype("fix_coder")` → `_load_template("fix_coding.md")` chain is live
    - Verify `_run_coder_session` → `_run_session("fix_coder")` → `resolve_model_tier(config, "fix_coder")` chain resolves correctly
    - _Requirements: all_

  - [ ] 3.4 Run integration smoke test
    - TS-88-SMOKE-1 passes using real components
    - _Test Spec: TS-88-SMOKE-1_

  - [ ] 3.5 Stub / dead-code audit
    - Search all files touched by this spec for stubs, `return []`, `pass`,
      `NotImplementedError`, `# TODO`
    - Verify no unjustified stubs remain
    - _Requirements: all_

  - [ ] 3.V Verify task group 3
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/nightshift/test_fix_coder.py tests/unit/test_fix_coder_archetype.py tests/property/test_fix_coder_props.py tests/integration/test_fix_coder_smoke.py`
    - [ ] SDK parity tests TS-88-P3 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/`
    - [ ] No unjustified stubs in touched files
    - [ ] Execution path from design.md is live

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 88-REQ-1.1 | TS-88-1 | 2.1 | `test_fix_coder_archetype.py::test_template_exists` |
| 88-REQ-1.2 | TS-88-2, TS-88-P1 | 2.1 | `test_fix_coder_archetype.py::test_no_specs_references` |
| 88-REQ-1.3 | TS-88-3 | 2.1 | `test_fix_coder_archetype.py::test_commit_format` |
| 88-REQ-1.4 | TS-88-4 | 2.1 | `test_fix_coder_archetype.py::test_git_workflow` |
| 88-REQ-1.5 | TS-88-5 | 2.1 | `test_fix_coder_archetype.py::test_quality_gates` |
| 88-REQ-1.6 | TS-88-6 | 2.1 | `test_fix_coder_archetype.py::test_no_session_artifacts` |
| 88-REQ-1.E1 | TS-88-E1, TS-88-P1 | 2.1 | `test_fix_coder_archetype.py::test_interpolation_no_specs` |
| 88-REQ-2.1 | TS-88-7, TS-88-P2 | 2.2 | `test_fix_coder_archetype.py::test_registry_entry` |
| 88-REQ-2.2 | TS-88-8, TS-88-P2 | 2.2 | `test_fix_coder_archetype.py::test_defaults_match_coder` |
| 88-REQ-2.3 | TS-88-9, TS-88-P2 | 2.2 | `test_fix_coder_archetype.py::test_not_task_assignable` |
| 88-REQ-2.E1 | TS-88-E2 | 2.2 | `test_fix_coder_archetype.py::test_fallback` |
| 88-REQ-3.1 | TS-88-10 | 3.1 | `test_fix_coder.py::test_build_prompt_archetype` |
| 88-REQ-3.2 | TS-88-12 | 3.2 | `test_fix_coder.py::test_run_coder_session_archetype` |
| 88-REQ-3.3 | TS-88-11 | 3.1 | `test_fix_coder.py::test_no_commit_format_in_task` |
| 88-REQ-3.E1 | TS-88-E2 | 2.2 | `test_fix_coder_archetype.py::test_fallback` |
| 88-REQ-4.1 | TS-88-P3 | 2.2 | `test_fix_coder_props.py::test_sdk_parity` |
| 88-REQ-4.2 | TS-88-P3 | 2.2 | `test_fix_coder_props.py::test_sdk_parity` |
| Path 1 | TS-88-SMOKE-1 | 3.4 | `test_fix_coder_smoke.py::test_pipeline_uses_fix_coding` |
