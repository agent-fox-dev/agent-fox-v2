# Implementation Plan: Operational Commands

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements three operational CLI commands: `agent-fox status`,
`agent-fox standup`, and `agent-fox reset`. Task group 1 writes failing tests.
Groups 2-5 implement the production code to make those tests pass: status
reporting, standup reporting, reset engine, and output formatters.

## Test Commands

- Unit tests: `uv run pytest tests/unit/reporting/ tests/unit/engine/test_reset.py -q`
- Property tests: `uv run pytest tests/property/reporting/ -q`
- All spec tests: `uv run pytest tests/unit/reporting/ tests/unit/engine/test_reset.py tests/property/reporting/ -q`
- Linter: `uv run ruff check agent_fox/reporting/ agent_fox/engine/reset.py agent_fox/cli/status.py agent_fox/cli/standup.py agent_fox/cli/reset.py`
- Type check: `uv run mypy agent_fox/reporting/ agent_fox/engine/reset.py agent_fox/cli/status.py agent_fox/cli/standup.py agent_fox/cli/reset.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Write status report tests
    - `tests/unit/reporting/test_status.py`: TS-07-1 (task counts), TS-07-2
      (token usage and cost), TS-07-3 (problem tasks list)
    - Create test fixtures: sample state.jsonl content and plan.json content
      with various task states
    - _Test Spec: TS-07-1, TS-07-2, TS-07-3_

  - [x] 1.2 Write standup report tests
    - `tests/unit/reporting/test_standup.py`: TS-07-4 (agent activity
      windowing), TS-07-5 (human commits), TS-07-6 (file overlap detection),
      TS-07-7 (queue summary), TS-07-8 (cost breakdown by model)
    - Create test fixtures: sample state with timestamps, mock git log output
    - _Test Spec: TS-07-4, TS-07-5, TS-07-6, TS-07-7, TS-07-8_

  - [x] 1.3 Write formatter tests
    - `tests/unit/reporting/test_formatters.py`: TS-07-9 (JSON valid),
      TS-07-10 (YAML valid)
    - _Test Spec: TS-07-9, TS-07-10_

  - [x] 1.4 Write reset engine tests
    - `tests/unit/engine/test_reset.py`: TS-07-11 (full reset), TS-07-12
      (single-task reset with cascade unblock)
    - Create test fixtures: sample plan with dependencies, state with
      failed/blocked tasks, temporary worktree directories
    - _Test Spec: TS-07-11, TS-07-12_

  - [x] 1.5 Write edge case tests
    - `tests/unit/reporting/test_status.py`: TS-07-E1 (no state file),
      TS-07-E2 (no plan file)
    - `tests/unit/reporting/test_standup.py`: TS-07-E3 (no agent activity),
      TS-07-E4 (no git commits)
    - `tests/unit/reporting/test_formatters.py`: TS-07-E5 (unwritable output)
    - `tests/unit/engine/test_reset.py`: TS-07-E6 (nothing to reset),
      TS-07-E7 (no state file), TS-07-E8 (unknown task ID), TS-07-E9 (reset
      completed task)
    - _Test Spec: TS-07-E1 through TS-07-E9_

  - [x] 1.6 Write property tests
    - `tests/property/reporting/test_status_props.py`: TS-07-P1 (count
      consistency), TS-07-P3 (JSON roundtrip)
    - `tests/property/reporting/test_reset_props.py`: TS-07-P2 (reset
      preserves completed), TS-07-P4 (cascade unblock correctness)
    - _Test Spec: TS-07-P1, TS-07-P2, TS-07-P3, TS-07-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/reporting/ tests/unit/engine/test_reset.py tests/property/reporting/`

- [ ] 2. Implement status report generator
  - [ ] 2.1 Create report data models
    - `agent_fox/reporting/__init__.py`
    - `agent_fox/reporting/status.py`: `TaskSummary` and `StatusReport`
      frozen dataclasses
    - _Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3_

  - [ ] 2.2 Implement state and plan loading helpers
    - Helper functions to load `state.jsonl` and `plan.json`, reconstruct
      node statuses, compute cumulative tokens and cost
    - Handle missing state file (return empty state with all tasks pending)
    - Handle missing plan file (raise AgentFoxError)
    - _Requirements: 07-REQ-1.E1, 07-REQ-1.E2_

  - [ ] 2.3 Implement generate_status()
    - Read state and plan, compute counts by status, aggregate tokens/cost,
      build problem tasks list with reasons from block_reasons and
      session error messages
    - Compute per-spec breakdown
    - _Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/reporting/test_status.py -q`
    - [ ] Edge case tests pass: TS-07-E1, TS-07-E2
    - [ ] No linter warnings: `uv run ruff check agent_fox/reporting/status.py`
    - [ ] Requirements 07-REQ-1.* acceptance criteria met

- [ ] 3. Implement standup report generator
  - [ ] 3.1 Create standup data models
    - `agent_fox/reporting/standup.py`: `AgentActivity`, `HumanCommit`,
      `FileOverlap`, `CostBreakdown`, `QueueSummary`, `StandupReport`
      frozen dataclasses
    - _Requirements: 07-REQ-2.1 through 07-REQ-2.5_

  - [ ] 3.2 Implement human commit detection
    - `_get_human_commits()`: run `git log` with `--invert-grep
      --author=<agent>` and `--format="%H|%an|%aI|%s" --name-only`,
      parse output into `HumanCommit` records
    - Handle git command failure gracefully (log warning, return empty list)
    - _Requirements: 07-REQ-2.2, 07-REQ-2.E2_

  - [ ] 3.3 Implement file overlap detection
    - `_detect_overlaps()`: intersect agent touched_paths from session
      records with human commit changed files
    - _Requirements: 07-REQ-2.3_

  - [ ] 3.4 Implement generate_standup()
    - Filter session records by timestamp window
    - Compute agent activity metrics
    - Get human commits via git log
    - Detect file overlaps
    - Build cost breakdown by model tier
    - Build queue summary from current task statuses
    - _Requirements: 07-REQ-2.1 through 07-REQ-2.5_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/reporting/test_standup.py -q`
    - [ ] Edge case tests pass: TS-07-E3, TS-07-E4
    - [ ] No linter warnings: `uv run ruff check agent_fox/reporting/standup.py`
    - [ ] Requirements 07-REQ-2.* acceptance criteria met

- [ ] 4. Implement reset engine
  - [ ] 4.1 Create reset data model
    - `agent_fox/engine/reset.py`: `ResetResult` frozen dataclass
    - _Requirements: 07-REQ-4.1, 07-REQ-5.1_

  - [ ] 4.2 Implement worktree and branch cleanup
    - `_clean_worktree()`: remove worktree directory if it exists
    - `_clean_branch()`: delete feature branch via `git branch -D` if it
      exists; derive branch name from task ID
      (`feature/{spec_name}-{group_number}`)
    - Handle git failures gracefully (log warning, continue)
    - _Requirements: 07-REQ-4.2_

  - [ ] 4.3 Implement reset_all()
    - Find all tasks with status failed, blocked, or in_progress
    - Reset each to pending, clean up worktrees and branches
    - Write updated state back to state.jsonl
    - Handle no-op case (nothing to reset)
    - _Requirements: 07-REQ-4.1, 07-REQ-4.2, 07-REQ-4.E1_

  - [ ] 4.4 Implement cascade unblocking
    - `_find_sole_blocker_dependents()`: for each downstream blocked task,
      check if all predecessors except the reset target are completed;
      if so, include in unblock list
    - _Requirements: 07-REQ-5.2_

  - [ ] 4.5 Implement reset_task()
    - Validate task ID exists in plan
    - Reject completed tasks
    - Reset the single task, clean up its worktree and branch
    - Re-evaluate downstream blocked tasks using cascade unblock logic
    - Write updated state
    - _Requirements: 07-REQ-5.1, 07-REQ-5.2, 07-REQ-5.E1, 07-REQ-5.E2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/engine/test_reset.py -q`
    - [ ] Edge case tests pass: TS-07-E6, TS-07-E7, TS-07-E8, TS-07-E9
    - [ ] Property tests pass: `uv run pytest tests/property/reporting/test_reset_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/engine/reset.py`
    - [ ] Requirements 07-REQ-4.*, 07-REQ-5.* acceptance criteria met

- [ ] 5. Implement formatters and CLI commands
  - [ ] 5.1 Implement output formatters
    - `agent_fox/reporting/formatters.py`: `OutputFormat` enum,
      `ReportFormatter` protocol, `TableFormatter` (Rich tables),
      `JsonFormatter` (json.dumps), `YamlFormatter` (yaml.dump)
    - `get_formatter()` factory function
    - `write_output()` function with file writing support
    - _Requirements: 07-REQ-3.1, 07-REQ-3.2, 07-REQ-3.3, 07-REQ-3.4_

  - [ ] 5.2 Implement status CLI command
    - `agent_fox/cli/status.py`: `status` Click command registered on
      `main` group
    - `--format` option (table/json/yaml)
    - Load config, call `generate_status()`, format with appropriate
      formatter, print to stdout
    - _Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3, 07-REQ-3.1_

  - [ ] 5.3 Implement standup CLI command
    - `agent_fox/cli/standup.py`: `standup` Click command registered on
      `main` group
    - `--hours`, `--format`, `--output` options
    - Load config, call `generate_standup()`, format, output to stdout or file
    - _Requirements: 07-REQ-2.1, 07-REQ-3.1, 07-REQ-3.4_

  - [ ] 5.4 Implement reset CLI command
    - `agent_fox/cli/reset.py`: `reset` Click command registered on
      `main` group
    - Optional `TASK_ID` argument, `--yes` flag
    - Full reset: show tasks to reset, prompt for confirmation (unless --yes),
      call `reset_all()`
    - Single task reset: call `reset_task()` directly (no prompt)
    - Display result summary
    - _Requirements: 07-REQ-4.3, 07-REQ-4.4, 07-REQ-5.3_

  - [ ] 5.V Verify task group 5
    - [ ] All spec tests pass: `uv run pytest tests/unit/reporting/ tests/unit/engine/test_reset.py -q`
    - [ ] All property tests pass: `uv run pytest tests/property/reporting/ -q`
    - [ ] All edge case tests pass
    - [ ] No linter warnings: `uv run ruff check agent_fox/reporting/ agent_fox/engine/reset.py agent_fox/cli/status.py agent_fox/cli/standup.py agent_fox/cli/reset.py`
    - [ ] Type check passes: `uv run mypy agent_fox/reporting/ agent_fox/engine/reset.py agent_fox/cli/status.py agent_fox/cli/standup.py agent_fox/cli/reset.py`
    - [ ] Requirements 07-REQ-3.* acceptance criteria met
    - [ ] CLI commands are invocable: `uv run agent-fox status --help`, `uv run agent-fox standup --help`, `uv run agent-fox reset --help`

- [ ] 6. Checkpoint -- Operational Commands Complete
  - Ensure all tests pass: `uv run pytest tests/unit/reporting/ tests/unit/engine/test_reset.py tests/property/reporting/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/reporting/ agent_fox/engine/ agent_fox/cli/status.py agent_fox/cli/standup.py agent_fox/cli/reset.py`
  - Ensure type check clean: `uv run mypy agent_fox/reporting/ agent_fox/engine/reset.py`
  - Verify all three commands work end-to-end with sample data
  - No regressions in existing tests: `uv run pytest tests/ -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 07-REQ-1.1 | TS-07-1 | 2.3 | tests/unit/reporting/test_status.py |
| 07-REQ-1.2 | TS-07-2 | 2.3 | tests/unit/reporting/test_status.py |
| 07-REQ-1.3 | TS-07-3 | 2.3 | tests/unit/reporting/test_status.py |
| 07-REQ-1.E1 | TS-07-E1 | 2.2 | tests/unit/reporting/test_status.py |
| 07-REQ-1.E2 | TS-07-E2 | 2.2 | tests/unit/reporting/test_status.py |
| 07-REQ-2.1 | TS-07-4 | 3.4 | tests/unit/reporting/test_standup.py |
| 07-REQ-2.2 | TS-07-5 | 3.2 | tests/unit/reporting/test_standup.py |
| 07-REQ-2.3 | TS-07-6 | 3.3 | tests/unit/reporting/test_standup.py |
| 07-REQ-2.4 | TS-07-7 | 3.4 | tests/unit/reporting/test_standup.py |
| 07-REQ-2.5 | TS-07-8 | 3.4 | tests/unit/reporting/test_standup.py |
| 07-REQ-2.E1 | TS-07-E3 | 3.4 | tests/unit/reporting/test_standup.py |
| 07-REQ-2.E2 | TS-07-E4 | 3.2 | tests/unit/reporting/test_standup.py |
| 07-REQ-3.1 | TS-07-9, TS-07-10 | 5.1 | tests/unit/reporting/test_formatters.py |
| 07-REQ-3.2 | TS-07-9 | 5.1 | tests/unit/reporting/test_formatters.py |
| 07-REQ-3.3 | TS-07-10 | 5.1 | tests/unit/reporting/test_formatters.py |
| 07-REQ-3.4 | -- | 5.3 | (CLI integration) |
| 07-REQ-3.E1 | TS-07-E5 | 5.1 | tests/unit/reporting/test_formatters.py |
| 07-REQ-4.1 | TS-07-11 | 4.3 | tests/unit/engine/test_reset.py |
| 07-REQ-4.2 | TS-07-11 | 4.2, 4.3 | tests/unit/engine/test_reset.py |
| 07-REQ-4.3 | -- | 5.4 | (CLI integration) |
| 07-REQ-4.4 | -- | 5.4 | (CLI integration) |
| 07-REQ-4.E1 | TS-07-E6 | 4.3 | tests/unit/engine/test_reset.py |
| 07-REQ-4.E2 | TS-07-E7 | 4.3 | tests/unit/engine/test_reset.py |
| 07-REQ-5.1 | TS-07-12 | 4.5 | tests/unit/engine/test_reset.py |
| 07-REQ-5.2 | TS-07-12 | 4.4, 4.5 | tests/unit/engine/test_reset.py |
| 07-REQ-5.3 | -- | 5.4 | (CLI integration) |
| 07-REQ-5.E1 | TS-07-E8 | 4.5 | tests/unit/engine/test_reset.py |
| 07-REQ-5.E2 | TS-07-E9 | 4.5 | tests/unit/engine/test_reset.py |
| Property 1 | TS-07-P1 | 2.3 | tests/property/reporting/test_status_props.py |
| Property 4 | TS-07-P2 | 4.3 | tests/property/reporting/test_reset_props.py |
| Property 5 | TS-07-P4 | 4.4 | tests/property/reporting/test_reset_props.py |
| Property 6 | TS-07-P3 | 5.1 | tests/property/reporting/test_status_props.py |

## Notes

- This spec depends on spec 01 (CLI framework, config, theme) and spec 04
  (ExecutionState, SessionRecord, state.jsonl format). The data models
  referenced from those specs are used as-is -- do not redefine them.
- The `state.jsonl` and `plan.json` file formats are defined by specs 04 and
  02 respectively. This spec reads them but does not modify their schema.
- For standup git log integration, mock `subprocess.run` in unit tests. Use
  a real git repository in integration tests.
- PyYAML is a new dependency -- add it to `pyproject.toml` if not already
  present.
- The `_clean_branch()` function derives branch names from task IDs using the
  pattern `feature/{spec_name}-{group_number}`. This must match the branch
  naming convention used by the session runner (spec 03).
- Use `click.confirm()` for the full reset confirmation prompt. The `--yes`
  flag bypasses it.
- Use `tmp_path` fixtures for worktree directory tests.
- Use `monkeypatch` to mock `subprocess.run` for git operations in unit tests.
