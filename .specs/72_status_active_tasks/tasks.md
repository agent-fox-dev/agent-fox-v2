# Implementation Plan: Show Active Tasks in Status Command

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into 3 groups: tests first, then data model and
report generation, then text formatting. JSON output requires no additional
work as `asdict()` handles serialization automatically.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_status_active_tasks.py tests/property/test_status_active_tasks.py`
- Unit tests: `uv run pytest -q tests/unit/test_status_active_tasks.py`
- Property tests: `uv run pytest -q tests/property/test_status_active_tasks.py`
- All tests: `uv run pytest -q`
- Linter: `ruff check agent_fox/reporting/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_status_active_tasks.py`
    - Test class for report generation (TS-72-1, TS-72-2, TS-72-3)
    - Test class for text formatting (TS-72-4, TS-72-5, TS-72-6, TS-72-7, TS-72-8)
    - Test class for JSON output (TS-72-9, TS-72-10)
    - Test class for edge cases (TS-72-E1, TS-72-E2, TS-72-E3)
    - _Test Spec: TS-72-1 through TS-72-10, TS-72-E1 through TS-72-E3_
    - _Note: placed in `tests/unit/reporting/` following project convention_

  - [x] 1.2 Create property test file `tests/property/test_status_active_tasks.py`
    - TS-72-P1: In-progress filter invariant
    - TS-72-P2: Text section presence invariant
    - _Test Spec: TS-72-P1, TS-72-P2_
    - _Note: placed in `tests/property/reporting/` following project convention_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet (15 failed)
    - [x] No linter warnings introduced: `ruff check tests/unit/test_status_active_tasks.py tests/property/test_status_active_tasks.py`

- [x] 2. Data model and report generation
  - [x] 2.1 Add `in_progress_tasks` field to `StatusReport` dataclass
    - Import `TaskActivity` from `reporting/standup.py`
    - Add field: `in_progress_tasks: list[TaskActivity] = field(default_factory=list)`
    - File: `agent_fox/reporting/status.py`
    - _Requirements: 72-REQ-1.1_

  - [x] 2.2 Compute in-progress task activities in `generate_status()`
    - Import `_compute_task_activities` from `reporting/standup.py`
    - Call `_compute_task_activities()` with all sessions and node_states
    - Filter to `current_status == "in_progress"` entries only
    - Include both coder and non-coder nodes
    - Populate `in_progress_tasks` in the returned `StatusReport`
    - File: `agent_fox/reporting/status.py`
    - _Requirements: 72-REQ-1.1, 72-REQ-1.2, 72-REQ-1.3, 72-REQ-1.E1, 72-REQ-1.E2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_status_active_tasks.py -k "TestReportGeneration or TestEdgeCases"`
    - [x] JSON tests pass (asdict handles new field): `uv run pytest -q tests/unit/test_status_active_tasks.py -k "TestJsonOutput"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `ruff check agent_fox/reporting/`

- [ ] 3. Text formatting
  - [ ] 3.1 Add "Active Tasks" section to `TableFormatter.format_status()`
    - Insert section after Tokens line and before Cost by Archetype
    - Use `_display_node_id()` for task ID display
    - Use `format_tokens()` for token values
    - Render tasks with sessions: `{display_id}: {status}. {completed}/{total} sessions. tokens {in} in / {out} out. ${cost}`
    - Render tasks without sessions: `{display_id}: {status}`
    - Omit section entirely when `in_progress_tasks` is empty
    - File: `agent_fox/reporting/formatters.py`
    - _Requirements: 72-REQ-2.1, 72-REQ-2.2, 72-REQ-2.3, 72-REQ-2.4, 72-REQ-2.5, 72-REQ-2.E1_

  - [ ] 3.V Verify task group 3
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/test_status_active_tasks.py tests/property/test_status_active_tasks.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `ruff check agent_fox/reporting/`
    - [ ] All requirements 72-REQ-*.* acceptance criteria met

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
| 72-REQ-1.1 | TS-72-1 | 2.1, 2.2 | test_status_active_tasks.py::TestReportGeneration |
| 72-REQ-1.2 | TS-72-2 | 2.2 | test_status_active_tasks.py::TestReportGeneration |
| 72-REQ-1.3 | TS-72-3 | 2.2 | test_status_active_tasks.py::TestReportGeneration |
| 72-REQ-1.E1 | TS-72-E2 | 2.2 | test_status_active_tasks.py::TestEdgeCases |
| 72-REQ-1.E2 | TS-72-E1 | 2.2 | test_status_active_tasks.py::TestEdgeCases |
| 72-REQ-2.1 | TS-72-4 | 3.1 | test_status_active_tasks.py::TestTextFormatting |
| 72-REQ-2.2 | TS-72-5 | 3.1 | test_status_active_tasks.py::TestTextFormatting |
| 72-REQ-2.3 | TS-72-6 | 3.1 | test_status_active_tasks.py::TestTextFormatting |
| 72-REQ-2.4 | TS-72-7 | 3.1 | test_status_active_tasks.py::TestTextFormatting |
| 72-REQ-2.5 | TS-72-8 | 3.1 | test_status_active_tasks.py::TestTextFormatting |
| 72-REQ-2.E1 | TS-72-E3 | 3.1 | test_status_active_tasks.py::TestEdgeCases |
| 72-REQ-3.1 | TS-72-9 | 2.1 | test_status_active_tasks.py::TestJsonOutput |
| 72-REQ-3.2 | TS-72-10 | 2.1 | test_status_active_tasks.py::TestJsonOutput |
| Property 1 | TS-72-P1 | 2.2 | test_status_active_tasks.py (property) |
| Property 2 | TS-72-P2 | 3.1 | test_status_active_tasks.py (property) |

## Notes

- `_compute_task_activities()` from `standup.py` is a module-level function
  (not a method) and can be imported directly.
- The standup module computes activities for ALL tasks; the status module
  filters post-hoc to only `in_progress` entries.
- JSON serialization requires no code change — `asdict()` in
  `JsonFormatter.format_status()` automatically picks up the new field.
- The `active_agents` field (added in spec 67) is unchanged. It provides
  archetype names only; `in_progress_tasks` is a superset with full metrics.
