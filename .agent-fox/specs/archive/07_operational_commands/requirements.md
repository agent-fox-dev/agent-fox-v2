# Requirements Document: Operational Commands

## Introduction

This document specifies three operational CLI commands for agent-fox v2:
`status` (progress dashboard), `standup` (daily activity report), and `reset`
(clear failed tasks for retry). These commands give developers visibility into
autonomous execution progress and the ability to recover from failures without
manual state editing. They depend on the core foundation (spec 01) for CLI
framework and configuration, and the orchestrator (spec 04) for execution
state and session records.

## Glossary

| Term | Definition |
|------|-----------|
| Status report | A snapshot of task progress: counts by status, token usage, cost, and blocked/failed task details |
| Standup report | A time-windowed activity report covering agent work, human commits, file overlaps, and queued tasks |
| File overlap | A file modified by both the agent and a human within the same reporting period |
| Reset | Clearing a task's failed/blocked status back to pending, cleaning up its worktree and branch |
| Cascade unblock | Re-evaluating downstream tasks after a reset to determine if they can proceed |
| Output format | The serialization format for report data: table (Rich), JSON, or YAML |
| Time window | The reporting period for standup, measured in hours from the current time |
| Agent commit | A git commit authored by agent-fox (identified by author identity) |
| Human commit | A git commit authored by someone other than agent-fox |

## Requirements

### Requirement 1: Status Report Generation

**User Story:** As a developer, I want to see a progress dashboard showing task
counts, cost, and any problems so that I know where my autonomous run stands
without reading logs.

#### Acceptance Criteria

1. [07-REQ-1.1] WHEN the user runs the status command, THE system SHALL read
   the execution state from `.agent-fox/state.jsonl` and the task graph from
   `.agent-fox/plan.json` and display task counts grouped by status (pending,
   in_progress, completed, failed, blocked, skipped).

2. [07-REQ-1.2] WHEN the user runs the status command, THE system SHALL
   display cumulative token usage (input and output tokens) and estimated
   cost in USD across all recorded sessions.

3. [07-REQ-1.3] WHEN blocked or failed tasks exist, THE system SHALL display
   a list of those tasks with their identifiers, titles, and the reason for
   failure or blocking.

#### Edge Cases

1. [07-REQ-1.E1] IF no state file exists (no execution has occurred), THEN THE
   system SHALL display the plan summary from `plan.json` with all tasks
   showing as pending and zero cost/tokens.

2. [07-REQ-1.E2] IF neither state file nor plan file exists, THEN THE system
   SHALL print an error instructing the user to run `agent-fox plan` first and
   exit with code 1.

---

### Requirement 2: Standup Report Generation

**User Story:** As a developer, I want a daily briefing showing what the agent
did, what I did, and where our changes overlap so that I can start my day with
full context.

#### Acceptance Criteria

1. [07-REQ-2.1] WHEN the user runs the standup command, THE system SHALL
   produce a report covering a configurable time window (default: 24 hours)
   that includes: tasks completed by the agent, sessions run, tokens consumed,
   and cost incurred during the window.

2. [07-REQ-2.2] THE standup report SHALL include human commits made during the
   reporting window, identified by filtering `git log` to exclude commits
   authored by agent-fox.

3. [07-REQ-2.3] THE standup report SHALL identify file overlaps: files modified
   by both the agent (from session records) and a human (from git log) during
   the reporting window.

4. [07-REQ-2.4] THE standup report SHALL include a queue summary showing tasks
   that are ready, pending, and blocked.

5. [07-REQ-2.5] THE standup report SHALL include a cost breakdown by model
   tier used during the reporting window.

#### Edge Cases

1. [07-REQ-2.E1] IF no agent activity occurred within the time window, THEN
   THE system SHALL report zero agent activity and still show human commits
   and queue status.

2. [07-REQ-2.E2] IF the git repository has no commits in the time window, THEN
   THE system SHALL report zero human commits without error.

---

### Requirement 3: Output Formats

**User Story:** As a developer, I want to export status and standup reports in
JSON or YAML so that I can integrate them with dashboards and scripts.

#### Acceptance Criteria

1. [07-REQ-3.1] THE status and standup commands SHALL support a `--format`
   option accepting `table` (default), `json`, or `yaml`.

2. [07-REQ-3.2] WHEN `--format json` is specified, THE system SHALL output the
   report data as valid, parseable JSON to stdout.

3. [07-REQ-3.3] WHEN `--format yaml` is specified, THE system SHALL output the
   report data as valid, parseable YAML to stdout.

4. [07-REQ-3.4] THE standup command SHALL support an `--output` option that
   writes the report to the specified file path instead of stdout.

#### Edge Cases

1. [07-REQ-3.E1] IF the `--output` file path is not writable, THEN THE system
   SHALL print an error and exit with code 1.

---

### Requirement 4: Full Reset

**User Story:** As a developer, I want to reset all failed and blocked tasks
back to a ready state so that I can retry them after fixing the underlying
problem.

#### Acceptance Criteria

1. [07-REQ-4.1] WHEN the user runs the reset command without specifying a task,
   THE system SHALL identify all tasks with status `failed`, `blocked`, or
   `in_progress` and reset their status to `pending`.

2. [07-REQ-4.2] FOR each reset task, THE system SHALL remove its worktree
   directory (under `.agent-fox/worktrees/`) if it exists, and delete its
   feature branch if it exists.

3. [07-REQ-4.3] BEFORE performing a full reset, THE system SHALL display the
   list of tasks that will be reset and prompt for confirmation.

4. [07-REQ-4.4] THE user SHALL be able to skip the confirmation prompt by
   passing the `--yes` flag.

#### Edge Cases

1. [07-REQ-4.E1] IF no incomplete tasks exist (all are completed, pending, or
   skipped), THEN THE system SHALL print a message indicating there is nothing
   to reset and exit successfully.

2. [07-REQ-4.E2] IF the state file does not exist, THEN THE system SHALL print
   an error instructing the user to run `agent-fox code` first and exit with
   code 1.

---

### Requirement 5: Single-Task Reset

**User Story:** As a developer, I want to reset a specific failed task and have
its downstream dependents re-evaluated so that I can surgically retry one piece
of work.

#### Acceptance Criteria

1. [07-REQ-5.1] WHEN the user runs the reset command with a task identifier,
   THE system SHALL reset only that task's status to `pending` and clean up
   its worktree and branch.

2. [07-REQ-5.2] AFTER resetting a single task, THE system SHALL re-evaluate
   all downstream tasks that were blocked. IF the reset task was the sole
   blocker for a downstream task, THEN that downstream task SHALL also be
   reset to `pending`.

3. [07-REQ-5.3] THE single-task reset SHALL NOT require confirmation (no
   prompt).

#### Edge Cases

1. [07-REQ-5.E1] IF the specified task identifier does not exist in the plan,
   THEN THE system SHALL print an error listing valid task identifiers and exit
   with code 1.

2. [07-REQ-5.E2] IF the specified task is already `completed`, THEN THE system
   SHALL print a warning that completed tasks cannot be reset and exit
   successfully without changes.
