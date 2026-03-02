# Implementation Plan: Standup Report Plain-Text Formatting

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec replaces the Rich table output of `agent-fox standup --format table`
with compact plain text matching agent-fox v1. Task group 1 writes failing
tests. Group 2 enriches the data model and generator. Group 3 rewrites the
formatter and updates existing tests for backward compatibility.

## Test Commands

- Spec tests: `uv run pytest tests/unit/reporting/test_standup_formatting.py -q`
- Property tests: `uv run pytest tests/property/reporting/test_standup_fmt_props.py -q`
- All spec 15 tests: `uv run pytest tests/unit/reporting/test_standup_formatting.py tests/property/reporting/test_standup_fmt_props.py -q`
- Existing standup tests: `uv run pytest tests/unit/reporting/test_standup.py tests/unit/reporting/test_formatters.py -q`
- All reporting tests: `uv run pytest tests/unit/reporting/ tests/property/reporting/ -q`
- Linter: `uv run ruff check agent_fox/reporting/standup.py agent_fox/reporting/formatters.py`
- Type check: `uv run mypy agent_fox/reporting/standup.py agent_fox/reporting/formatters.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for formatter output
    - Create `tests/unit/reporting/test_standup_formatting.py`
    - Add helper to build a sample `StandupReport` with all new fields
    - Write tests: TS-15-1 (header), TS-15-2 (per-task lines), TS-15-3
      (human commits), TS-15-4 (queue status), TS-15-5 (file overlaps),
      TS-15-6 (total cost)
    - _Test Spec: TS-15-1, TS-15-2, TS-15-3, TS-15-4, TS-15-5, TS-15-6_

  - [x] 1.2 Write utility function tests
    - In the same test file, add tests for `_format_tokens()` and
      `_display_node_id()`: TS-15-7, TS-15-8
    - _Test Spec: TS-15-7, TS-15-8_

  - [x] 1.3 Write data model / generator tests
    - Add tests: TS-15-9 (per-task activity generation), TS-15-10 (enriched
      queue summary generation)
    - These tests call `generate_standup()` and assert on new model fields
    - _Test Spec: TS-15-9, TS-15-10_

  - [x] 1.4 Write edge case tests
    - TS-15-E1 (no agent activity), TS-15-E2 (no human commits),
      TS-15-E3 (no file overlaps), TS-15-E4 (no ready tasks),
      TS-15-E5 (total cost zero), TS-15-E6 (hours=1)
    - _Test Spec: TS-15-E1 through TS-15-E6_

  - [x] 1.5 Write property tests
    - Create `tests/property/reporting/test_standup_fmt_props.py`
    - TS-15-P1 (token format), TS-15-P2 (node ID roundtrip),
      TS-15-P3 (session sum), TS-15-P4 (queue total), TS-15-P5 (section
      ordering), TS-15-P6 (empty sections)
    - _Test Spec: TS-15-P1 through TS-15-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/reporting/test_standup_formatting.py tests/property/reporting/test_standup_fmt_props.py`

- [ ] 2. Enrich data models and generator
  - [ ] 2.1 Add `TaskActivity` dataclass to `standup.py`
    - Frozen dataclass with fields: `task_id`, `current_status`,
      `completed_sessions`, `total_sessions`, `input_tokens`,
      `output_tokens`, `cost`
    - _Requirements: 15-REQ-2.3_

  - [ ] 2.2 Enrich `QueueSummary` dataclass
    - Add `total: int`, `in_progress: int`, `ready_task_ids: list[str]`
      fields (with defaults for backward compatibility)
    - _Requirements: 15-REQ-4.3_

  - [ ] 2.3 Enrich `StandupReport` dataclass
    - Add `task_activities: list[TaskActivity]` field (default empty list)
    - Add `total_cost: float` field (default 0.0)
    - _Requirements: 15-REQ-2.3, 15-REQ-6.2_

  - [ ] 2.4 Implement `_compute_task_activities()` function
    - Group windowed sessions by `node_id`
    - For each group: count completed vs total sessions, sum tokens and cost
    - Look up `current_status` from execution state `node_states`
    - Return `list[TaskActivity]` sorted by task_id
    - _Requirements: 15-REQ-2.2, 15-REQ-2.3_

  - [ ] 2.5 Update `_build_queue_summary()` to populate new fields
    - Compute `total` as sum of all task counts
    - Track `in_progress` tasks
    - Collect `ready_task_ids` list
    - _Requirements: 15-REQ-4.1, 15-REQ-4.3_

  - [ ] 2.6 Update `generate_standup()` to populate new report fields
    - Call `_compute_task_activities()` with windowed sessions and node states
    - Pass `total_cost` from `ExecutionState.total_cost` (0.0 if no state)
    - Pass enriched `QueueSummary` with new fields
    - _Requirements: 15-REQ-2.3, 15-REQ-4.3, 15-REQ-6.2_

  - [ ] 2.V Verify task group 2
    - [ ] Generator tests pass: `uv run pytest tests/unit/reporting/test_standup_formatting.py::TestPerTaskActivityGeneration tests/unit/reporting/test_standup_formatting.py::TestEnrichedQueueSummary -q`
    - [ ] Existing standup tests still pass: `uv run pytest tests/unit/reporting/test_standup.py -q`
    - [ ] Existing formatter tests still pass: `uv run pytest tests/unit/reporting/test_formatters.py -q`
    - [ ] Property tests for data model pass: `uv run pytest tests/property/reporting/test_standup_fmt_props.py::test_per_task_session_sum tests/property/reporting/test_standup_fmt_props.py::test_queue_total_equals_component_sum -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/reporting/standup.py`
    - [ ] Requirements 15-REQ-2.3, 15-REQ-4.3, 15-REQ-6.2 acceptance criteria met

- [ ] 3. Rewrite formatter and update existing tests
  - [ ] 3.1 Add utility functions to `formatters.py`
    - `_format_tokens(count: int) -> str`
    - `_display_node_id(node_id: str) -> str`
    - _Requirements: 15-REQ-7.1, 15-REQ-8.1_

  - [ ] 3.2 Rewrite `TableFormatter.format_standup()`
    - Replace Rich table rendering with plain-text string building
    - Implement all sections: header, agent activity, human commits,
      queue status, file overlaps (conditional), total cost
    - Use `_format_tokens()` and `_display_node_id()` throughout
    - _Requirements: 15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.3, 15-REQ-2.1,
      15-REQ-2.2, 15-REQ-3.1, 15-REQ-4.1, 15-REQ-4.2, 15-REQ-5.1,
      15-REQ-6.1, 15-REQ-8.2_

  - [ ] 3.3 Update existing test fixtures for new model fields
    - Update `_make_standup_report()` in `test_formatters.py` to include
      `task_activities`, `total_cost`, and enriched `QueueSummary`
    - Update any other fixtures in `test_standup.py` or `conftest.py` that
      construct `StandupReport` or `QueueSummary` directly
    - _Test Spec: (regression — existing TS-07-* tests must pass)_

  - [ ] 3.V Verify task group 3
    - [ ] All spec 15 tests pass: `uv run pytest tests/unit/reporting/test_standup_formatting.py tests/property/reporting/test_standup_fmt_props.py -q`
    - [ ] All existing reporting tests pass: `uv run pytest tests/unit/reporting/ tests/property/reporting/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/reporting/formatters.py agent_fox/reporting/standup.py`
    - [ ] Type check passes: `uv run mypy agent_fox/reporting/formatters.py agent_fox/reporting/standup.py`
    - [ ] Requirements 15-REQ-1.* through 15-REQ-8.* acceptance criteria met

- [ ] 4. Checkpoint — Standup Formatting Complete
  - All tests pass: `uv run pytest tests/unit/reporting/ tests/property/reporting/ -q`
  - All lints clean: `uv run ruff check agent_fox/reporting/`
  - Type check clean: `uv run mypy agent_fox/reporting/`
  - No regressions: `uv run pytest tests/ -q`
  - Verify CLI output manually: `uv run agent-fox standup --help`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 15-REQ-1.1 | TS-15-1 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-1.2 | TS-15-1 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-1.3 | TS-15-1 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-1.E1 | TS-15-E6 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-2.1 | TS-15-2 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-2.2 | TS-15-2 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-2.3 | TS-15-9 | 2.1, 2.4 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-2.E1 | TS-15-E1 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-3.1 | TS-15-3 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-3.E1 | TS-15-E2 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-4.1 | TS-15-4 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-4.2 | TS-15-4 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-4.3 | TS-15-10 | 2.2, 2.5 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-4.E1 | TS-15-E4 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-5.1 | TS-15-5 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-5.E1 | TS-15-E3 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-6.1 | TS-15-6 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-6.2 | TS-15-6 | 2.3, 2.6 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-6.E1 | TS-15-E5 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-7.1 | TS-15-7 | 3.1 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-8.1 | TS-15-8 | 3.1 | tests/unit/reporting/test_standup_formatting.py |
| 15-REQ-8.2 | TS-15-2, TS-15-4, TS-15-5 | 3.2 | tests/unit/reporting/test_standup_formatting.py |
| Property 1 | TS-15-P1 | 3.1 | tests/property/reporting/test_standup_fmt_props.py |
| Property 2 | TS-15-P2 | 3.1 | tests/property/reporting/test_standup_fmt_props.py |
| Property 3 | TS-15-P3 | 2.4 | tests/property/reporting/test_standup_fmt_props.py |
| Property 4 | TS-15-P4 | 2.5 | tests/property/reporting/test_standup_fmt_props.py |
| Property 5 | TS-15-P5 | 3.2 | tests/property/reporting/test_standup_fmt_props.py |
| Property 6 | TS-15-P6 | 3.2 | tests/property/reporting/test_standup_fmt_props.py |

## Notes

- This spec depends on spec 07 (operational commands) which defined the
  original `StandupReport`, `AgentActivity`, `QueueSummary`, and
  `TableFormatter`. All model changes are additive (new fields with defaults)
  to maintain backward compatibility with existing spec 07 tests.
- The `QueueSummary` enrichment adds fields with defaults to avoid breaking
  existing tests that construct `QueueSummary` without the new fields.
  If frozen dataclass defaults are insufficient, update existing test fixtures
  in task 3.3.
- `_format_tokens()` and `_display_node_id()` are module-private functions
  in `formatters.py`. They are tested directly via import.
- The `cost_breakdown` field remains on `StandupReport` for JSON/YAML output
  but is not rendered in the plain-text format.
- Use `conftest.py` helpers (`make_session_record`, `write_plan_file`, etc.)
  from the existing test infrastructure for generator tests.
