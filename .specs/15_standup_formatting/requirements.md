# Requirements Document: Standup Report Plain-Text Formatting

## Introduction

This document specifies the replacement of the Rich table output in
`agent-fox standup --format table` with a compact, indented plain-text format
matching agent-fox v1. The change affects only the table formatter for standup
reports; JSON, YAML, and the status command are out of scope.

## Glossary

| Term | Definition |
|------|-----------|
| Plain-text format | Indented text output with section headers and one-line-per-item entries, no table borders or column headers |
| Display node ID | A node ID rendered with slash separators (`spec_name/group_number`) instead of the internal colon format (`spec_name:group_number`) |
| Human-readable tokens | Token counts formatted with a `k` suffix for thousands and one decimal place (e.g., `12.9k`); values below 1000 shown as integers |
| Per-task breakdown | A summary line for each task that had session activity in the reporting window, showing status, session counts, tokens, and cost |
| All-time total cost | The cumulative cost across all sessions ever recorded in `ExecutionState.total_cost`, not limited to the reporting window |

## Requirements

### Requirement 1: Plain-Text Standup Header

**User Story:** As a developer, I want the standup report to start with a clean
one-line title and generated timestamp so that I can immediately see the
reporting window.

#### Acceptance Criteria

1. [15-REQ-1.1] WHEN `--format table` is used (default), THE standup output
   SHALL begin with a line `Standup Report — last {hours}h` where `{hours}` is
   the `--hours` value and `—` is an em dash (U+2014).

2. [15-REQ-1.2] THE standup output SHALL include a second line
   `Generated: {timestamp}` where `{timestamp}` is the window end time in
   ISO 8601 format.

3. [15-REQ-1.3] THE header SHALL be followed by a blank line before the first
   section.

#### Edge Cases

1. [15-REQ-1.E1] IF `--hours` is 1, THEN the header SHALL read
   `Standup Report — last 1h` (no pluralization).

---

### Requirement 2: Per-Task Agent Activity Section

**User Story:** As a developer, I want to see each task's status, session count,
token usage, and cost on a single indented line so that I can quickly scan agent
progress per task.

#### Acceptance Criteria

1. [15-REQ-2.1] THE standup output SHALL include an `Agent Activity` section
   header followed by one indented line per task that had any session activity
   within the reporting window.

2. [15-REQ-2.2] EACH per-task line SHALL follow the format:
   `  {display_id}: {status}. {completed}/{total} sessions. tokens {in} in / {out} out. ${cost}`
   where `{display_id}` uses slash separators, `{completed}` is the number of
   sessions with status `completed`, `{total}` is the total number of sessions,
   tokens use human-readable formatting, and cost is formatted as `$X.XX`.

3. [15-REQ-2.3] THE `StandupReport` data model SHALL include a per-task
   breakdown list with fields: task_id, current_status, completed_sessions,
   total_sessions, input_tokens, output_tokens, and cost.

#### Edge Cases

1. [15-REQ-2.E1] IF no agent activity occurred within the window, THEN THE
   system SHALL print `  (no agent activity)` under the section header.

---

### Requirement 3: Human Commits Section

**User Story:** As a developer, I want to see each human commit as a compact
one-liner with SHA, author, and subject so that I can scan what colleagues did.

#### Acceptance Criteria

1. [15-REQ-3.1] THE standup output SHALL include a `Human Commits` section
   header followed by one indented line per human commit in the format:
   `  {sha_7} {author}: {subject}` where `{sha_7}` is the first 7 characters
   of the commit SHA.

#### Edge Cases

1. [15-REQ-3.E1] IF no human commits occurred within the window, THEN THE
   system SHALL print `  (no human commits)` under the section header.

---

### Requirement 4: Queue Status Section

**User Story:** As a developer, I want to see all queue counts on a single line
and a list of ready task IDs so that I know what's next without reading a table.

#### Acceptance Criteria

1. [15-REQ-4.1] THE standup output SHALL include a `Queue Status` section
   header followed by a summary line in the format:
   `  {total} total: {done} done | {in_progress} in progress | {pending} pending | {ready} ready | {blocked} blocked | {failed} failed`
   where `{total}` is the sum of all task counts, `{done}` maps to the
   `completed` count, and all other values are integer counts.

2. [15-REQ-4.2] WHEN there are ready tasks, THE system SHALL print a second
   line `  Ready: {id1}, {id2}, ...` listing all ready task IDs in display
   (slash) format.

3. [15-REQ-4.3] THE `QueueSummary` data model SHALL include `total: int`,
   `in_progress: int`, and `ready_task_ids: list[str]` fields.

#### Edge Cases

1. [15-REQ-4.E1] IF no tasks are ready, THEN THE `Ready:` line SHALL be
   omitted entirely.

---

### Requirement 5: File Overlaps Section

**User Story:** As a developer, I want file overlap warnings in a compact
inline format so that I can quickly spot potential merge conflicts.

#### Acceptance Criteria

1. [15-REQ-5.1] WHEN file overlaps exist, THE standup output SHALL include a
   `Heads Up — File Overlaps` section header (with em dash) followed by one
   indented line per overlapping file in the format:
   `  {path} — commits: {sha1}, {sha2} | agents: {task1}, {task2}`
   where commit SHAs are truncated to 7 characters and task IDs use display
   (slash) format.

#### Edge Cases

1. [15-REQ-5.E1] IF no file overlaps exist, THEN THE entire section (header
   and body) SHALL be omitted from the output.

---

### Requirement 6: Total Cost Line

**User Story:** As a developer, I want to see the all-time project cost at the
bottom of the standup so that I have overall spend context.

#### Acceptance Criteria

1. [15-REQ-6.1] THE standup output SHALL end with a line
   `Total Cost: ${all_time_total}` where `{all_time_total}` is formatted as
   `X.XX` and represents the all-time total cost from `ExecutionState.total_cost`.

2. [15-REQ-6.2] THE `StandupReport` data model SHALL include a
   `total_cost: float` field populated from `ExecutionState.total_cost`.

#### Edge Cases

1. [15-REQ-6.E1] IF no execution state exists (no sessions ever run), THEN
   the total cost SHALL be `$0.00`.

---

### Requirement 7: Human-Readable Token Formatting

**User Story:** As a developer, I want token counts displayed with `k` suffixes
so that large numbers are easy to read at a glance.

#### Acceptance Criteria

1. [15-REQ-7.1] THE system SHALL format token counts using human-readable
   notation: values >= 1000 SHALL be displayed as `{value/1000:.1f}k`
   (e.g., `12900` becomes `12.9k`); values < 1000 SHALL be displayed as
   plain integers (e.g., `345` remains `345`).

---

### Requirement 8: Display Node ID Formatting

**User Story:** As a developer, I want task IDs displayed with slashes instead
of colons so that they match the v1 convention and are easier to read.

#### Acceptance Criteria

1. [15-REQ-8.1] THE system SHALL provide a utility function to convert internal
   node IDs (colon-separated, e.g., `01_core_foundation:1`) to display format
   (slash-separated, e.g., `01_core_foundation/1`).

2. [15-REQ-8.2] ALL task IDs in the plain-text standup output (agent activity,
   queue status ready list, file overlaps) SHALL use the display (slash) format.
