# Requirements Document

## Introduction

Live progress display for the `agent-fox code` command. Shows an animated
spinner with abbreviated model/API activity on a single terminal line that
is overwritten in place, plus permanent milestone lines for task completion
and failure.

## Glossary

| Term | Definition |
|------|-----------|
| **Spinner line** | The single, continuously-overwritten terminal line showing animated spinner + activity text. |
| **Permanent line** | A line printed above the spinner that scrolls up and is never overwritten. |
| **Activity event** | A notification from the session runner indicating tool use or model state (thinking, tool name, etc.). |
| **Task event** | A notification from the orchestrator indicating a task state change (completed, failed, blocked). |
| **Progress display** | The overall UI component managing the spinner line and permanent lines. |
| **Node ID** | The task graph identifier in format `{spec_name}:{group_number}` (e.g. `03_session:2`). |

## Requirements

### Requirement 1: Progress Display Lifecycle

**User Story:** As a user running `agent-fox code`, I want to see that the
fox is actively working, so I can distinguish working from stuck.

#### Acceptance Criteria

1. [18-REQ-1.1] WHEN the orchestrator begins execution, THE progress display
   SHALL start and show a spinner on the last terminal line.
2. [18-REQ-1.2] WHILE the orchestrator is executing tasks, THE spinner
   animation SHALL cycle continuously.
3. [18-REQ-1.3] WHEN the orchestrator finishes execution (any termination
   reason), THE progress display SHALL stop and clear the spinner line.

#### Edge Cases

1. [18-REQ-1.E1] IF `--quiet` is set, THEN THE progress display SHALL be
   entirely suppressed (no spinner, no permanent lines).
2. [18-REQ-1.E2] IF stdout is not a TTY, THEN THE progress display SHALL
   disable spinner animation and carriage-return overwriting, but still
   print permanent task-completion lines.

### Requirement 2: Activity Events from Session Runner

**User Story:** As a user, I want to see what tool the model is currently
using, so I know the fox is making progress.

#### Acceptance Criteria

1. [18-REQ-2.1] WHEN the session runner receives an SDK message indicating
   tool use, THE system SHALL emit an activity event containing the node ID,
   tool name, and first argument.
2. [18-REQ-2.2] WHEN no tool-use messages have been received for a session
   (model is thinking), THE system SHALL emit an activity event with the
   node ID and the text `thinking...`.
3. [18-REQ-2.3] THE activity event callback SHALL be an optional parameter
   on the session runner, defaulting to None (no-op).

#### Edge Cases

1. [18-REQ-2.E1] IF the SDK message stream raises an exception, THEN
   activity event emission SHALL stop gracefully without affecting session
   execution.
2. [18-REQ-2.E2] IF the tool-use argument is a file path, THEN the
   activity event SHALL abbreviate it to the basename only.
3. [18-REQ-2.E3] IF the tool-use argument exceeds 30 characters after
   abbreviation, THEN it SHALL be truncated with an ellipsis.

### Requirement 3: Spinner Line Rendering

**User Story:** As a user, I want the status to stay on one line without
cluttering my terminal.

#### Acceptance Criteria

1. [18-REQ-3.1] THE spinner line SHALL be rendered as:
   `{spinner_char} [{node_id}] {tool_name} {abbreviated_arg}`.
2. [18-REQ-3.2] THE spinner line SHALL be written using carriage return
   (`\r`) without a trailing newline, overwriting the previous content.
3. [18-REQ-3.3] THE spinner line SHALL be truncated to the current terminal
   width to prevent line wrapping.
4. [18-REQ-3.4] WHEN a new activity event arrives, THE spinner line SHALL
   update immediately with the new content.

#### Edge Cases

1. [18-REQ-3.E1] IF the terminal width cannot be determined, THEN THE
   spinner line SHALL assume a default width of 80 columns.

### Requirement 4: Permanent Lines for Task Events

**User Story:** As a user, I want to see when tasks finish so I can track
overall progress without reading log files.

#### Acceptance Criteria

1. [18-REQ-4.1] WHEN a task completes successfully, THE progress display
   SHALL print a permanent line above the spinner:
   `{check_mark} {node_id} done ({duration})`.
2. [18-REQ-4.2] WHEN a task fails or is blocked, THE progress display
   SHALL print a permanent line above the spinner:
   `{cross_mark} {node_id} {status}`.
3. [18-REQ-4.3] Permanent lines SHALL use themed styling (success role for
   completion, error role for failure/blocked).
4. [18-REQ-4.4] After printing a permanent line, THE spinner SHALL
   continue on the next line below it.

#### Edge Cases

1. [18-REQ-4.E1] IF stdout is not a TTY, THEN permanent lines SHALL be
   printed as plain text without ANSI styling.

### Requirement 5: Integration with Code Command

**User Story:** As a user, I want progress to appear automatically when I
run `agent-fox code` without any extra flags.

#### Acceptance Criteria

1. [18-REQ-5.1] THE `agent-fox code` command SHALL create and manage the
   progress display around the orchestrator execution.
2. [18-REQ-5.2] THE progress display SHALL appear between the banner and
   the final summary.
3. [18-REQ-5.3] THE code command SHALL pass the activity event callback
   through the session runner factory to each session.
4. [18-REQ-5.4] THE code command SHALL pass a task event callback to the
   orchestrator for completion/failure notifications.

#### Edge Cases

1. [18-REQ-5.E1] IF the orchestrator raises an exception, THEN THE
   progress display SHALL be stopped cleanly before the error is printed.

### Requirement 6: Thread and Concurrency Safety

**User Story:** As a user running parallel sessions, I want the display to
remain coherent without garbled output.

#### Acceptance Criteria

1. [18-REQ-6.1] WHEN multiple sessions emit activity events concurrently,
   THE spinner line SHALL show the most recently received event (last
   writer wins).
2. [18-REQ-6.2] Writes to the spinner line SHALL be serialized so that
   concurrent updates do not produce garbled terminal output.

#### Edge Cases

1. [18-REQ-6.E1] IF an activity event arrives while a permanent line is
   being printed, THEN THE permanent line SHALL complete before the
   spinner updates.
