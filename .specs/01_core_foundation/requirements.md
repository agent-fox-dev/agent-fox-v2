# Requirements Document

## Introduction

This document specifies the core foundation of agent-fox v2: the project
skeleton, CLI framework, configuration system, init command, error types,
model registry, logging, and terminal theme. Every subsequent spec depends
on the infrastructure established here.

## Glossary

| Term | Definition |
|------|-----------|
| agent-fox | The autonomous coding-agent orchestrator being built |
| CLI | Command-line interface — the primary user interaction surface |
| Config | Project-level TOML configuration file at `.agent-fox/config.toml` |
| Init | The process of preparing a repository for agent-fox operation |
| Model tier | A classification of AI models by capability and cost (SIMPLE, STANDARD, ADVANCED) |
| Development branch | The long-lived git branch (default: `develop`) where agent-fox integrates completed work |
| Rich | Python library for terminal formatting and styled output |
| TOML | Tom's Obvious Minimal Language — the configuration file format |

## Requirements

### Requirement 1: CLI Entry Point

**User Story:** As a developer, I want a single `agent-fox` command with
discoverable subcommands, so that I can invoke any agent-fox operation from
my terminal.

#### Acceptance Criteria

1. [01-REQ-1.1] THE CLI SHALL provide a top-level `agent-fox` command group
   that accepts `--version` and `--help` flags.
2. [01-REQ-1.2] THE CLI SHALL support subcommand registration so that other
   specs can add commands (init, plan, code, etc.) without modifying the
   entry point.
3. [01-REQ-1.3] THE CLI SHALL display a themed banner with the project name
   and version when invoked without a subcommand.
4. [01-REQ-1.4] THE CLI SHALL be installable as a console script entry point
   via `pyproject.toml` (`agent-fox = "agent_fox.cli.app:main"`).

#### Edge Cases

1. [01-REQ-1.E1] IF the CLI is invoked with an unknown subcommand, THEN THE
   CLI SHALL print an error listing available commands and exit with code 2.

---

### Requirement 2: Configuration System

**User Story:** As a developer, I want agent-fox to read project-level
configuration from a TOML file with sensible defaults, so that I can
customize behavior without editing code.

#### Acceptance Criteria

1. [01-REQ-2.1] WHEN a configuration file exists at `.agent-fox/config.toml`,
   THE system SHALL load it, validate all fields using pydantic models, and
   merge with defaults.
2. [01-REQ-2.2] WHEN a configuration field has an invalid value, THE system
   SHALL report a clear error message identifying the field, the invalid
   value, and the expected type or range.
3. [01-REQ-2.3] WHEN a configuration field is absent, THE system SHALL use the
   documented default value.
4. [01-REQ-2.4] THE configuration model SHALL expose all settings documented in
   PRD Section 6 (parallelism, sync interval, models, timeouts, hooks, platform,
   theme, etc.) with their specified defaults.
5. [01-REQ-2.5] WHERE a command-line option overrides a configuration value,
   THE system SHALL prefer the command-line value.
6. [01-REQ-2.6] WHEN the configuration file contains unrecognized keys, THE
   system SHALL log a warning and ignore them (forward compatibility).

#### Edge Cases

1. [01-REQ-2.E1] IF the configuration file does not exist, THEN THE system
   SHALL use all default values without error.
2. [01-REQ-2.E2] IF the configuration file is not valid TOML, THEN THE system
   SHALL exit with a clear parse error and exit code 1.
3. [01-REQ-2.E3] IF a numeric configuration value is out of the valid range,
   THEN THE system SHALL clamp it to the nearest valid bound and log a warning.

---

### Requirement 3: Project Initialization

**User Story:** As a developer, I want to run `agent-fox init` in my project
directory to prepare it for autonomous coding, so that I can start using
agent-fox immediately.

#### Acceptance Criteria

1. [01-REQ-3.1] WHEN the user runs the init command, THE system SHALL create
   the `.agent-fox/` directory with a default `config.toml`, empty `hooks/`
   and `worktrees/` subdirectories.
2. [01-REQ-3.2] WHEN the user runs the init command, THE system SHALL create
   or verify the existence of a long-lived development branch (default name:
   `develop`).
3. [01-REQ-3.3] WHEN the project is already initialized (`.agent-fox/` exists
   with a `config.toml`), THE system SHALL preserve the existing configuration,
   report that the project is already initialized, and exit successfully.
4. [01-REQ-3.4] WHEN the project is initialized, THE system SHALL ensure that
   `.agent-fox/*` entries are in `.gitignore`, with exceptions for
   `config.toml`, `memory.jsonl`, and `state.jsonl` which SHALL be tracked.
5. [01-REQ-3.5] WHEN the init command is run outside a git repository, THE
   system SHALL exit with a clear error message and exit code 1.

#### Edge Cases

1. [01-REQ-3.E1] IF `.agent-fox/` exists but `config.toml` is missing, THEN
   THE system SHALL create a default `config.toml` without overwriting other
   contents.
2. [01-REQ-3.E2] IF the development branch already exists, THEN THE system
   SHALL not create a duplicate and SHALL report that the branch is ready.

---

### Requirement 4: Error Hierarchy

**User Story:** As a developer of agent-fox, I want a structured exception
hierarchy so that every error type has a specific class, enabling precise
catch/handle logic throughout the codebase.

#### Acceptance Criteria

1. [01-REQ-4.1] THE system SHALL define a base `AgentFoxError` exception class
   from which all agent-fox exceptions derive.
2. [01-REQ-4.2] THE system SHALL define specific exception classes for at
   least these categories: `ConfigError`, `InitError`, `PlanError`,
   `SessionError`, `WorkspaceError`, `IntegrationError`, `HookError`,
   `TimeoutError`, `CostLimitError`, `SecurityError`.
3. [01-REQ-4.3] Each exception class SHALL carry a human-readable message and
   optional structured context (e.g., the config field that failed, the task
   that timed out).

#### Edge Cases

1. [01-REQ-4.E1] IF an unexpected exception (not an AgentFoxError subclass)
   reaches the CLI top level, THEN THE CLI SHALL catch it, log the full
   traceback at DEBUG level, print a user-friendly error message, and exit
   with code 1.

---

### Requirement 5: AI Model Registry

**User Story:** As a developer, I want agent-fox to know which AI models are
available and their pricing, so that cost estimation and model selection work
correctly.

#### Acceptance Criteria

1. [01-REQ-5.1] THE system SHALL define three model tiers: SIMPLE (Haiku-class,
   low cost), STANDARD (Sonnet-class, balanced), and ADVANCED (Opus-class,
   highest capability).
2. [01-REQ-5.2] Each model entry SHALL include: model ID string, tier
   classification, input token price (per million), and output token price
   (per million).
3. [01-REQ-5.3] THE system SHALL provide a lookup function that resolves a
   tier name or model ID to a model entry.
4. [01-REQ-5.4] THE system SHALL provide a cost calculation function that
   computes estimated cost from token counts and a model entry.

#### Edge Cases

1. [01-REQ-5.E1] IF a model ID is not found in the registry, THEN THE system
   SHALL raise a `ConfigError` with the unrecognized model ID and a list of
   valid options.

---

### Requirement 6: Logging

**User Story:** As a developer, I want agent-fox to produce structured,
leveled log output so that I can diagnose issues and audit behavior.

#### Acceptance Criteria

1. [01-REQ-6.1] THE system SHALL configure Python's logging module with a
   consistent format: `[LEVEL] component: message`.
2. [01-REQ-6.2] THE system SHALL default to WARNING level, with a `--verbose`
   flag on the CLI that switches to DEBUG.
3. [01-REQ-6.3] THE system SHALL use named loggers per module (e.g.,
   `agent_fox.engine.orchestrator`) so that log filtering by component is
   possible.

#### Edge Cases

1. [01-REQ-6.E1] IF the `--verbose` flag is combined with `--quiet`, THEN THE
   system SHALL prefer `--verbose` (most information wins).

---

### Requirement 7: Terminal Theme

**User Story:** As a developer, I want agent-fox's terminal output to be
colorful and branded, with configurable colors, so that the output is
pleasant and scannable.

#### Acceptance Criteria

1. [01-REQ-7.1] THE system SHALL define a theme with named color roles:
   header, success, error, warning, info, tool, muted.
2. [01-REQ-7.2] THE system SHALL load theme overrides from the `[theme]`
   section of the configuration file.
3. [01-REQ-7.3] WHERE playful mode is enabled (default), THE system SHALL use
   fox-themed personality in status messages (e.g., "The fox is thinking...",
   "Tail wagging — task complete!").
4. [01-REQ-7.4] WHERE playful mode is disabled, THE system SHALL use neutral,
   professional status messages.

#### Edge Cases

1. [01-REQ-7.E1] IF a theme color value is not a valid Rich style string,
   THEN THE system SHALL fall back to the default color for that role and
   log a warning.
