# Requirements Document

## Introduction

This document specifies requirements for adding an "Active Tasks" section to
the `agent-fox status` command output. The section lists all currently
in-progress tasks with per-task session metrics, matching the format of the
`standup` command's "Agent Activity" section.

## Glossary

- **Active task**: A task node (coder or non-coder) whose current status is
  `in_progress` in the execution state.
- **TaskActivity**: A data structure containing per-task session metrics
  (task ID, status, session counts, token usage, cost). Defined in
  `reporting/standup.py`.
- **Status report**: The data model (`StatusReport`) produced by
  `generate_status()` and consumed by the text and JSON formatters.

## Requirements

### Requirement 1: In-Progress Tasks in Status Report

**User Story:** As an operator, I want the status command to show which tasks
are currently running with their session details so that I can monitor
progress without running the standup command.

#### Acceptance Criteria

1. [72-REQ-1.1] THE `StatusReport` dataclass SHALL include an
   `in_progress_tasks` field containing a list of `TaskActivity` objects
   for all tasks with `in_progress` status.
2. [72-REQ-1.2] THE `in_progress_tasks` field SHALL include both coder
   tasks and non-coder archetype nodes (verifier, auditor, skeptic) that
   have `in_progress` status.
3. [72-REQ-1.3] WHEN `generate_status()` is called, THE system SHALL
   compute `TaskActivity` records for in-progress tasks using session
   history data (session counts, token totals, cost).

#### Edge Cases

1. [72-REQ-1.E1] IF no tasks have `in_progress` status, THEN THE
   `in_progress_tasks` field SHALL be an empty list.
2. [72-REQ-1.E2] IF no execution state exists (no state.jsonl), THEN THE
   `in_progress_tasks` field SHALL be an empty list.

### Requirement 2: Text Output Formatting

**User Story:** As an operator, I want in-progress tasks displayed in the
same format as the standup command so that the output is consistent and
familiar.

#### Acceptance Criteria

1. [72-REQ-2.1] WHEN `in_progress_tasks` is non-empty, THE text formatter
   SHALL render an "Active Tasks" section.
2. [72-REQ-2.2] THE "Active Tasks" section SHALL appear after the Tokens
   line and before the "Cost by Archetype" section.
3. [72-REQ-2.3] WHEN a task has sessions, THE formatter SHALL render each
   task as: `{display_id}: {status}. {completed}/{total} sessions.
   tokens {in} in / {out} out. ${cost}`.
4. [72-REQ-2.4] WHEN a task has zero sessions, THE formatter SHALL render
   it as: `{display_id}: {status}`.
5. [72-REQ-2.5] WHEN `in_progress_tasks` is empty, THE text formatter
   SHALL omit the "Active Tasks" section entirely.

#### Edge Cases

1. [72-REQ-2.E1] IF `in_progress_tasks` contains tasks with zero tokens
   but non-zero session count, THEN THE formatter SHALL display `0 in /
   0 out` for the token values.

### Requirement 3: JSON Output

**User Story:** As a tool author, I want in-progress task data available in
the JSON output so that I can programmatically monitor active work.

#### Acceptance Criteria

1. [72-REQ-3.1] WHEN the status command is invoked in JSON mode, THE
   output SHALL include an `in_progress_tasks` array containing
   serialized `TaskActivity` objects.
2. [72-REQ-3.2] EACH `TaskActivity` object in the JSON output SHALL
   contain the fields: `task_id`, `current_status`, `completed_sessions`,
   `total_sessions`, `input_tokens`, `output_tokens`, `cost`.
