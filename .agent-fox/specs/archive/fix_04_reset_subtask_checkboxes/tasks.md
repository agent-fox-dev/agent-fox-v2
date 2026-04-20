# Implementation Plan: Hard Reset Sub-task Checkbox Reset

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This fix modifies one function (`reset_tasks_md_checkboxes` in
`agent_fox/engine/reset.py`) to use section-based checkbox resetting instead
of top-level-only regex. Task group 1 writes/updates tests, task group 2
implements the fix and creates the erratum.

## Test Commands

- Spec tests: `uv run pytest tests/unit/engine/test_hard_reset.py -q -k "subtask or nested or section"`
- Unit tests: `uv run pytest tests/unit/engine/test_hard_reset.py -q`
- Property tests: `uv run pytest tests/property/engine/test_reset_checkbox_props.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/engine/reset.py tests/unit/engine/test_hard_reset.py tests/property/engine/test_reset_checkbox_props.py`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Update existing test in `test_hard_reset.py`
    - Replace `test_subtask_checkboxes_not_affected` with
      `test_subtask_checkboxes_are_reset` — assert sub-tasks ARE reset
    - Add `test_deeply_nested_checkboxes_reset` — TS-fix04-2
    - Add `test_queued_state_preserved` — TS-fix04-3
    - Add `test_other_groups_unaffected` — TS-fix04-4
    - _Test Spec: TS-fix04-1 through TS-fix04-4_

  - [ ] 1.2 Add section boundary and edge case tests
    - Add `test_section_boundary_middle_group` — TS-fix04-5
    - Add `test_multiple_groups_reset` — TS-fix04-6
    - Add `test_in_progress_checkboxes_reset` — TS-fix04-7
    - _Test Spec: TS-fix04-5 through TS-fix04-7_

  - [ ] 1.3 Add edge case tests
    - Add `test_group_with_no_subtasks` — TS-fix04-E1
    - Add `test_optional_task_marker_preserved` — TS-fix04-E2
    - Add `test_last_group_section_to_eof` — TS-fix04-E3
    - Add `test_non_checkbox_content_preserved` — TS-fix04-E4
    - _Test Spec: TS-fix04-E1 through TS-fix04-E4_

  - [ ] 1.4 Create property test file
    - Create `tests/property/engine/test_reset_checkbox_props.py`
    - `test_all_nested_checkboxes_reset` — TS-fix04-P1
    - `test_other_groups_unaffected_prop` — TS-fix04-P2
    - `test_queued_unchecked_preserved_prop` — TS-fix04-P3
    - `test_idempotent_reset` — TS-fix04-P4
    - Use Hypothesis: generate tasks.md content with configurable groups,
      sub-tasks, nesting depth, and checkbox states
    - _Test Spec: TS-fix04-P1 through TS-fix04-P4_

  - [ ] 1.V Verify task group 1
    - [ ] All new tests exist and are syntactically valid
    - [ ] New tests FAIL (red) — implementation still uses old regex
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/engine/test_hard_reset.py tests/property/engine/test_reset_checkbox_props.py`

- [ ] 2. Implement fix and erratum
  - [ ] 2.1 Modify `reset_tasks_md_checkboxes` in `agent_fox/engine/reset.py`
    - Replace the single top-level regex with section-based processing
    - Find top-level line for each group_num
    - Find section end (next top-level line or EOF)
    - Reset all `[x]` and `[-]` checkboxes within the section
    - Preserve `[~]`, `[ ]`, and non-checkbox content
    - _Requirements: fix04-REQ-1.1, fix04-REQ-1.2, fix04-REQ-1.3,
      fix04-REQ-1.4, fix04-REQ-2.1, fix04-REQ-2.2_

  - [ ] 2.2 Create erratum for spec 35
    - Create `docs/errata/35_hard_reset_subtask_checkboxes.md`
    - Document that 35-REQ-7.1 originally only reset top-level checkboxes
    - Describe the expanded behavior: all checkboxes in the group section
    - _Requirements: fix04-REQ-3.1_

  - [ ] 2.V Verify task group 2
    - [ ] All unit tests pass: `uv run pytest tests/unit/engine/test_hard_reset.py -q`
    - [ ] All property tests pass: `uv run pytest tests/property/engine/test_reset_checkbox_props.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/engine/reset.py tests/unit/engine/test_hard_reset.py tests/property/engine/test_reset_checkbox_props.py`
    - [ ] Requirements fix04-REQ-1.*, fix04-REQ-2.*, fix04-REQ-3.* met

- [ ] 3. Checkpoint — Fix Complete
  - Ensure all tests pass: `uv run pytest -q`
  - Ensure linting passes: `uv run ruff check agent_fox/engine/reset.py`
  - Verify erratum file exists at `docs/errata/35_hard_reset_subtask_checkboxes.md`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

Tasks are **required by default**. Mark optional tasks with `*` after checkbox: `- [ ]* Optional task`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| fix04-REQ-1.1 | TS-fix04-1, TS-fix04-7 | 2.1 | `test_hard_reset.py::test_subtask_checkboxes_are_reset`, `test_hard_reset.py::test_in_progress_checkboxes_reset` |
| fix04-REQ-1.2 | TS-fix04-2 | 2.1 | `test_hard_reset.py::test_deeply_nested_checkboxes_reset` |
| fix04-REQ-1.3 | TS-fix04-3 | 2.1 | `test_hard_reset.py::test_queued_state_preserved` |
| fix04-REQ-1.4 | TS-fix04-4 | 2.1 | `test_hard_reset.py::test_other_groups_unaffected` |
| fix04-REQ-1.E1 | TS-fix04-E1 | 2.1 | `test_hard_reset.py::test_group_with_no_subtasks` |
| fix04-REQ-1.E2 | TS-fix04-E2 | 2.1 | `test_hard_reset.py::test_optional_task_marker_preserved` |
| fix04-REQ-2.1 | TS-fix04-5 | 2.1 | `test_hard_reset.py::test_section_boundary_middle_group` |
| fix04-REQ-2.2 | TS-fix04-6 | 2.1 | `test_hard_reset.py::test_multiple_groups_reset` |
| fix04-REQ-2.E1 | TS-fix04-E3 | 2.1 | `test_hard_reset.py::test_last_group_section_to_eof` |
| fix04-REQ-2.E2 | TS-fix04-E4 | 2.1 | `test_hard_reset.py::test_non_checkbox_content_preserved` |
| fix04-REQ-3.1 | — | 2.2 | `test_hard_reset.py::test_erratum_file_exists` |
| Property 1 | TS-fix04-P1 | 2.1 | `test_reset_checkbox_props.py::test_all_nested_checkboxes_reset` |
| Property 2 | TS-fix04-P2 | 2.1 | `test_reset_checkbox_props.py::test_other_groups_unaffected_prop` |
| Property 3 | TS-fix04-P3 | 2.1 | `test_reset_checkbox_props.py::test_queued_unchecked_preserved_prop` |
| Property 4 | TS-fix04-P4 | 2.1 | `test_reset_checkbox_props.py::test_idempotent_reset` |

## Notes

- The fix touches only `agent_fox/engine/reset.py` (one function).
- The existing `test_subtask_checkboxes_not_affected` test asserts the OLD
  (buggy) behavior and must be replaced, not just supplemented.
- Property tests should generate tasks.md content with 2-5 groups, 1-4
  sub-tasks per group, and 0-3 nesting levels.
- Use `@settings(max_examples=50)` for property tests to keep CI fast.
