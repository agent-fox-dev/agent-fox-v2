# Requirements Document

## Introduction

This specification defines requirements for renaming two CLI commands, ensuring
clean separation between CLI wiring and backing modules across all 9 commands,
and improving progress logging during orchestrated code execution.

## Glossary

- **Backing module**: A Python module containing the business logic for a CLI
  command, callable without the Click framework. Located outside `agent_fox/cli/`.
- **CLI handler**: A Click-decorated function in `agent_fox/cli/` that parses
  arguments and delegates to a backing module.
- **Task event line**: A permanent line printed to the terminal during `code`
  execution when a task completes, fails, or is blocked.
- **Activity line**: A transient spinner line showing the current tool invocation
  during a coding session.
- **Archetype**: A role assigned to an agent instance (coder, skeptic, verifier,
  oracle, auditor, librarian, cartographer, coordinator).
- **Model escalation**: Automatic promotion to a higher-capability model tier
  (SIMPLE → STANDARD → ADVANCED) after repeated failures.
- **Retry-predecessor**: A mechanism where a review archetype (verifier, auditor)
  resets a predecessor task to pending for re-execution.
- **Truncation limit**: The maximum character length for tool argument display
  in the activity line.

## Requirements

### Requirement 1: Command Renames

**User Story:** As a CLI user, I want command names that clearly describe their
purpose, so that the interface is intuitive.

#### Acceptance Criteria

1. [59-REQ-1.1] WHEN the user runs `agent-fox export --memory`, THE system
   SHALL produce identical output to the former `agent-fox dump --memory`
   command.
2. [59-REQ-1.2] WHEN the user runs `agent-fox export --db`, THE system SHALL
   produce identical output to the former `agent-fox dump --db` command.
3. [59-REQ-1.3] WHEN the user runs `agent-fox lint-specs`, THE system SHALL
   produce identical output to the former `agent-fox lint-spec` command.
4. [59-REQ-1.4] WHEN the user runs `agent-fox lint-specs --ai --fix --all`,
   THE system SHALL accept all three flags and behave identically to the
   former `agent-fox lint-spec --ai --fix --all`.

#### Edge Cases

1. [59-REQ-1.E1] WHEN the user runs `agent-fox dump`, THE system SHALL exit
   with a non-zero code and print an error indicating the command does not
   exist.
2. [59-REQ-1.E2] WHEN the user runs `agent-fox lint-spec`, THE system SHALL
   exit with a non-zero code and print an error indicating the command does
   not exist.

### Requirement 2: CLI/Module Separation — Export

**User Story:** As a developer, I want to call export functionality from Python
code, so that I can integrate knowledge export into scripts and tests.

#### Acceptance Criteria

1. [59-REQ-2.1] THE system SHALL provide a function
   `agent_fox.knowledge.export.export_memory(conn, output_path, json_mode)`
   that can be called without the CLI framework.
2. [59-REQ-2.2] THE system SHALL provide a function
   `agent_fox.knowledge.export.export_db(conn, output_path, json_mode)`
   that can be called without the CLI framework.
3. [59-REQ-2.3] WHEN `export_memory` or `export_db` is called from code, THE
   system SHALL return a result summary (fact count or table count) instead of
   printing to stderr.

### Requirement 3: CLI/Module Separation — Lint-Specs

**User Story:** As a developer, I want to call spec linting from Python code,
so that I can integrate validation into CI pipelines and tools.

#### Acceptance Criteria

1. [59-REQ-3.1] THE system SHALL provide a function
   `agent_fox.spec.lint.run_lint_specs(specs_dir, *, ai, fix, lint_all)` that
   can be called without the CLI framework.
2. [59-REQ-3.2] WHEN `run_lint_specs` is called, THE system SHALL return a
   structured result containing findings, summary counts, and an exit code.
3. [59-REQ-3.3] WHEN `run_lint_specs` is called with `fix=True`, THE system
   SHALL apply fixes and return the list of fix results without performing
   git operations.

#### Edge Cases

1. [59-REQ-3.E1] IF the specs directory does not exist, THEN `run_lint_specs`
   SHALL raise `PlanError` instead of calling `sys.exit()`.

### Requirement 4: CLI/Module Separation — Code

**User Story:** As a developer, I want to configure and launch the orchestrator
from code, so that I can embed agent-fox execution in larger workflows.

#### Acceptance Criteria

1. [59-REQ-4.1] THE system SHALL provide a function
   `agent_fox.engine.run.run_code(config, *, parallel, no_hooks, max_cost,
   max_sessions, debug, review_only, specs_dir)` that can be called without
   the CLI framework.
2. [59-REQ-4.2] WHEN `run_code` is called, THE system SHALL return an
   `ExecutionState` with the final status, session records, and cost totals.
3. [59-REQ-4.3] WHEN `run_code` is called with `parallel=N`, THE system SHALL
   pass the parallelism override to the orchestrator.

#### Edge Cases

1. [59-REQ-4.E1] IF `run_code` raises `KeyboardInterrupt`, THEN THE system
   SHALL return an `ExecutionState` with status `"interrupted"`.

### Requirement 5: CLI/Module Separation — Remaining Commands

**User Story:** As a developer, I want all CLI commands to have backing
functions callable from code.

#### Acceptance Criteria

1. [59-REQ-5.1] THE system SHALL provide backing functions for `fix`, `plan`,
   `reset`, `init`, `status`, and `standup` commands that can be called
   without the CLI framework.
2. [59-REQ-5.2] WHEN a backing function is called, THE system SHALL accept
   the same options as the corresponding CLI command, as explicit typed
   parameters.
3. [59-REQ-5.3] WHEN a backing function is called, THE system SHALL return a
   structured result instead of printing to stdout/calling `sys.exit()`.

### Requirement 6: Tool Argument Truncation

**User Story:** As a user watching code execution, I want to see enough of each
tool argument to understand what's happening, without excessive clipping.

#### Acceptance Criteria

1. [59-REQ-6.1] WHEN displaying a tool argument in the activity line, THE
   system SHALL truncate at 60 characters (previously 30).
2. [59-REQ-6.2] WHEN the tool argument is a file path longer than 60
   characters, THE system SHALL show trailing path components prefixed
   with `…/`.

### Requirement 7: Archetype Visibility in Task Events

**User Story:** As a user, I want to see which archetype is running each task,
so that I understand the orchestration flow.

#### Acceptance Criteria

1. [59-REQ-7.1] WHEN a task completes, THE system SHALL display the archetype
   in the task event line in the format `✓ {node_id} [{archetype}] done
   ({duration})`.
2. [59-REQ-7.2] WHEN a task fails, THE system SHALL display the archetype in
   the task event line in the format `✗ {node_id} [{archetype}] failed`.
3. [59-REQ-7.3] WHEN a task is blocked, THE system SHALL display the archetype
   in the task event line in the format `✗ {node_id} [{archetype}] blocked`.

#### Edge Cases

1. [59-REQ-7.E1] IF the archetype is not provided in the task event, THEN
   THE system SHALL omit the bracket label (backward compatibility with
   existing callers).

### Requirement 8: Retry and Escalation Visibility

**User Story:** As a user, I want to see when a reviewer disagrees, when a
task retries, and when the model is escalated, so that I can understand why
execution is taking longer.

#### Acceptance Criteria

1. [59-REQ-8.1] WHEN a review archetype disagrees and triggers a
   retry-predecessor reset, THE system SHALL print a permanent line:
   `✗ {reviewer_node} [{archetype}] disagrees → retry {predecessor_node}`.
2. [59-REQ-8.2] WHEN a task begins a retry attempt, THE system SHALL print
   a permanent line: `⟳ {node_id} [{archetype}] retry #{attempt}`.
3. [59-REQ-8.3] WHEN the system escalates a task's model tier, THE system
   SHALL append escalation info to the retry line:
   `⟳ {node_id} [{archetype}] retry #{attempt} (escalated: {from} → {to})`.

#### Edge Cases

1. [59-REQ-8.E1] IF a retry occurs without model escalation, THEN THE system
   SHALL print the retry line without the escalation suffix.

### Requirement 9: CLI Handler Thinness

**User Story:** As a maintainer, I want CLI handlers to contain only argument
parsing and output formatting, so that business logic is testable without
the CLI.

#### Acceptance Criteria

1. [59-REQ-9.1] THE system SHALL ensure that every CLI handler in
   `agent_fox/cli/` delegates to a backing function and contains no
   business logic beyond argument parsing, output formatting, and
   exit code mapping.
2. [59-REQ-9.2] WHEN a CLI handler calls a backing function, THE system
   SHALL pass all user-provided options as explicit parameters (not via
   Click context or global state).
