# Requirements Document: Code Command

## Introduction

This document specifies the `agent-fox code` CLI command — the user-facing
entry point that invokes the orchestrator engine to execute the task plan.
The orchestrator engine (spec 04), session runner (spec 03), and hook system
(spec 06) are already implemented; this spec covers only the CLI wrapper that
wires them together.

## Glossary

| Term | Definition |
|------|-----------|
| Code command | The `agent-fox code` CLI subcommand that starts or resumes orchestrated execution |
| Orchestrator | The deterministic execution engine (spec 04) that walks the task graph |
| Session runner factory | A callable that creates a session runner for a given task node |
| Completion summary | A compact text block printed after execution showing tasks, tokens, cost, and run status |
| Exit code | The integer returned to the shell indicating execution outcome |

## Requirements

### Requirement 1: Command Registration and Invocation

**User Story:** As a developer, I want to run `agent-fox code` to start
executing the plan built by `agent-fox plan`.

#### Acceptance Criteria

1. [16-REQ-1.1] THE system SHALL register a Click command named `code` on the
   main CLI group, accessible as `agent-fox code`.

2. [16-REQ-1.2] WHEN invoked, THE command SHALL load the project configuration
   from the Click context (already populated by the main group).

3. [16-REQ-1.3] WHEN invoked, THE command SHALL construct an `Orchestrator`
   instance with the project's `OrchestratorConfig`, plan path
   (`.agent-fox/plan.json`), state path (`.agent-fox/state.jsonl`), and a
   session runner factory.

4. [16-REQ-1.4] THE command SHALL execute `orchestrator.run()` via
   `asyncio.run()` and capture the returned `ExecutionState`.

#### Edge Cases

1. [16-REQ-1.E1] IF the plan file does not exist, THEN THE command SHALL print
   an error message instructing the user to run `agent-fox plan` first and exit
   with code 1.

2. [16-REQ-1.E2] IF the orchestrator raises an unexpected exception, THEN THE
   command SHALL log the traceback at debug level, print a user-friendly error
   message, and exit with code 1.

---

### Requirement 2: CLI Option Overrides

**User Story:** As a developer, I want to override orchestrator settings from
the command line so I can adjust parallelism, cost limits, and hook behavior
without editing the config file.

#### Acceptance Criteria

1. [16-REQ-2.1] THE command SHALL accept a `--parallel N` option that overrides
   the `orchestrator.parallel` config value for this run. The value SHALL be
   clamped to the range 1–8.

2. [16-REQ-2.2] THE command SHALL accept a `--no-hooks` flag that disables all
   hook scripts for this run.

3. [16-REQ-2.3] THE command SHALL accept a `--max-cost N` option that overrides
   the `orchestrator.max_cost` config value for this run.

4. [16-REQ-2.4] THE command SHALL accept a `--max-sessions N` option that
   overrides the `orchestrator.max_sessions` config value for this run.

5. [16-REQ-2.5] WHEN CLI options are provided, THE command SHALL apply them to
   the `OrchestratorConfig` before constructing the `Orchestrator`, without
   modifying the persisted config file.

#### Edge Cases

1. [16-REQ-2.E1] IF `--parallel` is given a value outside 1–8, THEN THE
   command SHALL clamp to the nearest bound and log a warning (handled by
   `OrchestratorConfig` validator).

---

### Requirement 3: Completion Summary

**User Story:** As a developer, I want to see a concise summary after
execution so I know what was accomplished without running `agent-fox status`
separately.

#### Acceptance Criteria

1. [16-REQ-3.1] AFTER execution completes (any outcome), THE command SHALL
   print a compact summary with each metric on its own line:
   - **Tasks:** `done/total done` followed by comma-separated conditional
     parts (`N in progress`, `N pending`, `N failed`). Zero-count categories
     SHALL be omitted for readability.
   - **Tokens:** human-readable input and output counts
     (`Tokens: 12.3k in / 4.5k out`).
   - **Cost:** estimated cost in USD (`Cost:   $1.23`).
   - **Status:** run status string (`Status: completed`).

2. [16-REQ-3.2] THE summary format SHALL use compact plain text (no Rich
   tables), with each metric labelled on its own line.

#### Edge Cases

1. [16-REQ-3.E1] IF the execution state is empty (zero tasks), THEN THE
   summary SHALL print "No tasks to execute." and exit with code 0.

---

### Requirement 4: Exit Codes

**User Story:** As a developer, I want meaningful exit codes so I can use
`agent-fox code` in scripts and CI pipelines.

#### Acceptance Criteria

1. [16-REQ-4.1] WHEN all tasks complete successfully (run status `completed`),
   THE command SHALL exit with code 0.

2. [16-REQ-4.2] WHEN an execution error occurs (missing plan, config error,
   unexpected exception), THE command SHALL exit with code 1.

3. [16-REQ-4.3] WHEN execution stalls (run status `stalled`), THE command SHALL
   exit with code 2.

4. [16-REQ-4.4] WHEN a cost or session limit is reached (run status
   `cost_limit` or `session_limit`), THE command SHALL exit with code 3.

5. [16-REQ-4.5] WHEN execution is interrupted by SIGINT (run status
   `interrupted`), THE command SHALL exit with code 130.

#### Edge Cases

1. [16-REQ-4.E1] IF the run status is an unrecognized value, THEN THE command
   SHALL exit with code 1.

---

### Requirement 5: Session Runner Factory

**User Story:** As a developer, I want the code command to wire the correct
session runner so that coding sessions are dispatched with proper configuration.

#### Acceptance Criteria

1. [16-REQ-5.1] THE command SHALL construct a session runner factory that
   creates session runners configured with the project's `AgentFoxConfig`,
   workspace info, and task-specific prompts.

2. [16-REQ-5.2] THE session runner factory SHALL be injected into the
   `Orchestrator` constructor, enabling the orchestrator to dispatch coding
   sessions without knowledge of session implementation details.

#### Edge Cases

1. [16-REQ-5.E1] IF the session runner factory fails to create a runner for a
   given task, THEN THE failure SHALL be reported as a session failure and
   handled by the orchestrator's retry logic.
