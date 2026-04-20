# Requirements Document

## Introduction

The `agent-fox fix` command currently runs silently — no output is visible
between invocation and the final report. This spec adds real-time progress
visualization consistent with the `code` command: a startup banner, a live
spinner showing tool-level session activity, phase/pass milestone lines, and
check execution indicators. All progress output is suppressed in quiet and
JSON modes.

## Glossary

- **Banner**: The fox ASCII art header displayed at command startup, including
  version and model information.
- **ProgressDisplay**: The existing `agent_fox.ui.progress.ProgressDisplay`
  class that manages a Rich Live spinner and permanent milestone lines.
- **ActivityEvent**: A dataclass representing a tool-use event from a coding
  session (tool name, argument, turn count, tokens).
- **activity_callback**: A callable `(ActivityEvent) -> None` passed to
  `run_session()` to receive real-time tool-use updates.
- **Milestone line**: A permanent line printed above the spinner that persists
  in the terminal output (e.g., task completion, phase transitions).
- **Phase**: Either "repair" (Phase 1 fix loop) or "improve" (Phase 2 improve
  loop).
- **Pass**: A single iteration of the fix loop or improve loop.
- **Quality check**: A configured command (ruff, pytest, etc.) executed to
  detect failures.
- **Quiet mode**: The `--quiet` CLI flag that suppresses non-essential output.
- **JSON mode**: The `--json` CLI flag that emits machine-readable JSONL output.

## Requirements

### Requirement 1: Startup Banner

**User Story:** As a user, I want to see the fox banner when `fix` starts, so
that I know the tool is running and which version/model is active.

#### Acceptance Criteria

1. [76-REQ-1.1] WHEN the `fix` command starts AND quiet mode is not active AND
   JSON mode is not active, THE system SHALL render the same startup banner as
   the `code` command, including version and model information.
2. [76-REQ-1.2] WHILE quiet mode is active, THE system SHALL NOT render the
   startup banner.
3. [76-REQ-1.3] WHILE JSON mode is active, THE system SHALL NOT render the
   startup banner.

### Requirement 2: Progress Display Lifecycle

**User Story:** As a user, I want a live spinner during fix execution, so that
I can see the tool is actively working.

#### Acceptance Criteria

1. [76-REQ-2.1] WHEN the `fix` command starts execution (after check detection),
   THE system SHALL create and start a `ProgressDisplay` instance.
2. [76-REQ-2.2] WHEN the `fix` command completes (normally or via error), THE
   system SHALL stop the `ProgressDisplay` in a finally block.
3. [76-REQ-2.3] WHILE quiet mode or JSON mode is active, THE system SHALL
   create the `ProgressDisplay` with `quiet=True` so all display output is
   suppressed.

#### Edge Cases

1. [76-REQ-2.E1] IF the `fix` command is interrupted by KeyboardInterrupt, THEN
   THE system SHALL stop the `ProgressDisplay` before exiting.

### Requirement 3: Session Activity Display

**User Story:** As a user, I want to see what each coding session is doing in
real time (reading files, running commands, editing), so that I can follow the
fix progress at the tool level.

#### Acceptance Criteria

1. [76-REQ-3.1] WHEN a fix coding session is created, THE system SHALL pass the
   `ProgressDisplay.activity_callback` as the `activity_callback` parameter to
   `run_session()`.
2. [76-REQ-3.2] WHEN an improve loop coding session (analyzer, coder, or
   verifier) is created, THE system SHALL pass the
   `ProgressDisplay.activity_callback` as the `activity_callback` parameter to
   `run_session()`.
3. [76-REQ-3.3] WHEN a session emits an `ActivityEvent`, THE system SHALL
   display it in the live spinner using the same format as the `code` command
   (turn count, token count, node ID, tool verb, argument).

### Requirement 4: Phase and Pass Milestone Lines

**User Story:** As a user, I want to see which phase and pass are currently
running, so that I can gauge overall progress.

#### Acceptance Criteria

1. [76-REQ-4.1] WHEN a fix loop pass begins, THE system SHALL print a permanent
   milestone line indicating the phase and pass number (e.g.,
   `[repair] Pass 1/3: running checks`).
2. [76-REQ-4.2] WHEN a fix loop pass completes with no failures found, THE
   system SHALL print a permanent milestone line indicating all checks passed.
3. [76-REQ-4.3] WHEN a fix loop pass finds failures, THE system SHALL print a
   permanent milestone line indicating the number of clusters found.
4. [76-REQ-4.4] WHEN a fix session starts for a cluster, THE system SHALL print
   a permanent milestone line identifying the cluster being fixed.
5. [76-REQ-4.5] WHEN an improve loop pass begins, THE system SHALL print a
   permanent milestone line indicating the phase and pass number (e.g.,
   `[improve] Pass 1/3: analyzing`).
6. [76-REQ-4.6] WHEN an improve loop session completes (analyzer, coder, or
   verifier), THE system SHALL print a permanent milestone line indicating the
   session role and outcome.

#### Edge Cases

1. [76-REQ-4.E1] IF the fix loop terminates due to cost limit, THEN THE system
   SHALL print a permanent milestone line indicating the cost limit was reached.
2. [76-REQ-4.E2] IF a fix session raises an exception, THEN THE system SHALL
   print a permanent milestone line indicating the session failure.

### Requirement 5: Check Execution Visibility

**User Story:** As a user, I want to see which quality check is currently
running, so that I know what the system is waiting on.

#### Acceptance Criteria

1. [76-REQ-5.1] WHEN a quality check begins execution, THE system SHALL update
   the spinner line to show the check name (e.g., `Running check: ruff…`).
2. [76-REQ-5.2] WHEN a quality check completes, THE system SHALL print a
   permanent milestone line indicating the check result (pass or fail with
   exit code).

### Requirement 6: Callback Plumbing

**User Story:** As a developer, I want the fix loop and improve loop to accept
progress callbacks, so that the CLI layer can wire display infrastructure
without the loops depending on UI code.

#### Acceptance Criteria

1. [76-REQ-6.1] WHEN `run_fix_loop` is called, THE system SHALL accept an
   optional `progress_callback` parameter for emitting phase/pass milestone
   events.
2. [76-REQ-6.2] WHEN `run_improve_loop` is called, THE system SHALL accept an
   optional `progress_callback` parameter for emitting phase/pass milestone
   events.
3. [76-REQ-6.3] WHEN `run_checks` is called, THE system SHALL accept an
   optional `check_callback` parameter that is called before and after each
   check execution.

#### Edge Cases

1. [76-REQ-6.E1] IF `progress_callback` is None, THEN THE system SHALL execute
   normally without emitting any progress events (backward compatible).
2. [76-REQ-6.E2] IF `check_callback` is None, THEN THE system SHALL execute
   normally without emitting any check events (backward compatible).
