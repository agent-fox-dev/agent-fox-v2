# Requirements Document: Global --json Flag (Spec 23)

## Introduction

This document specifies the requirements for adding a global `--json` flag
to the agent-fox CLI. The flag switches every command to structured JSON
input/output mode, enabling agent-to-agent and script-driven workflows.

## Glossary

| Term | Definition |
|------|------------|
| **Global flag** | A Click option defined on the top-level command group, inherited by all subcommands. |
| **JSON mode** | The CLI operating mode when `--json` is active — structured I/O, no banner, error envelopes. |
| **JSONL** | JSON Lines — one JSON object per line, used for streaming output. |
| **Error envelope** | A JSON object `{"error": "<message>"}` emitted on failure in JSON mode. |
| **Status envelope** | A JSON object `{"status": "ok"}` emitted on success by side-effect-only commands. |
| **Banner** | The fox ASCII art and version line printed at CLI startup. |

## Requirements

### Requirement 1: Global --json Flag

**User Story:** As an agent or script, I want a single `--json` flag that works on every command, so that I can get structured output without knowing per-command format options.

#### Acceptance Criteria

1. [23-REQ-1.1] THE CLI group SHALL accept a `--json` boolean flag on the top-level `main` command group.
2. [23-REQ-1.2] WHEN `--json` is provided, THE flag value SHALL be accessible to every subcommand via `ctx.obj["json"]`.
3. [23-REQ-1.3] WHEN `--json` is not provided, THE system SHALL default to human-readable output (current behavior).

#### Edge Cases

1. [23-REQ-1.E1] IF `--json` is combined with `--verbose` or `--quiet`, THEN THE system SHALL apply both: JSON output mode with the requested log level.

---

### Requirement 2: Banner Suppression

**User Story:** As an agent consuming JSON output, I want the banner suppressed in JSON mode, so that stdout contains only valid JSON.

#### Acceptance Criteria

1. [23-REQ-2.1] WHEN `--json` is active, THE system SHALL NOT render the fox banner to stdout.
2. [23-REQ-2.2] WHEN `--json` is active, THE system SHALL NOT emit any non-JSON text to stdout (logging goes to stderr only).

#### Edge Cases

1. [23-REQ-2.E1] IF `--json` is active AND `--quiet` is not set, THEN log messages SHALL still go to stderr (not stdout).

---

### Requirement 3: JSON Output for Batch Commands

**User Story:** As an agent, I want every batch command to emit a single JSON object, so that I can parse the result programmatically.

#### Acceptance Criteria

1. [23-REQ-3.1] WHEN `--json` is active, THE `status` command SHALL emit its report as a single JSON object to stdout.
2. [23-REQ-3.2] WHEN `--json` is active, THE `standup` command SHALL emit its report as a single JSON object to stdout.
3. [23-REQ-3.3] WHEN `--json` is active, THE `lint-spec` command SHALL emit findings and summary as a single JSON object to stdout.
4. [23-REQ-3.4] WHEN `--json` is active, THE `plan` command SHALL emit the execution plan as a single JSON object to stdout.
5. [23-REQ-3.5] WHEN `--json` is active, THE `patterns` command SHALL emit pattern results as a single JSON object to stdout.
6. [23-REQ-3.6] WHEN `--json` is active, THE `compact` command SHALL emit compaction statistics as a single JSON object to stdout.
7. [23-REQ-3.7] WHEN `--json` is active, THE `ingest` command SHALL emit ingestion statistics as a single JSON object to stdout.

#### Edge Cases

1. [23-REQ-3.E1] IF a batch command produces no data (e.g., `plan` with no specs), THEN THE system SHALL emit a valid JSON object with empty/default fields, not an empty string.

---

### Requirement 4: JSON Output for Side-Effect Commands

**User Story:** As an agent, I want side-effect commands to confirm success via JSON, so that I can detect completion programmatically.

#### Acceptance Criteria

1. [23-REQ-4.1] WHEN `--json` is active, THE `init` command SHALL emit `{"status": "ok"}` on successful completion.
2. [23-REQ-4.2] WHEN `--json` is active, THE `reset` command SHALL emit a JSON object containing the reset summary on successful completion.

---

### Requirement 5: JSONL Output for Streaming Commands

**User Story:** As an agent, I want streaming commands to emit one JSON object per line, so that I can process events incrementally.

#### Acceptance Criteria

1. [23-REQ-5.1] WHEN `--json` is active, THE `code` command SHALL emit progress events as JSONL (one JSON object per line) to stdout.
2. [23-REQ-5.2] WHEN `--json` is active, THE `ask` command SHALL emit its answer as a JSON object to stdout.
3. [23-REQ-5.3] WHEN `--json` is active, THE `fix` command SHALL emit progress events as JSONL to stdout.

#### Edge Cases

1. [23-REQ-5.E1] IF a streaming command is interrupted (SIGINT), THEN THE system SHALL emit a final JSON object `{"status": "interrupted"}` before exiting.

---

### Requirement 6: JSON Error Envelope

**User Story:** As an agent, I want errors reported as JSON when in JSON mode, so that I can detect and handle failures programmatically.

#### Acceptance Criteria

1. [23-REQ-6.1] WHEN `--json` is active AND a command fails, THE system SHALL emit `{"error": "<message>"}` to stdout.
2. [23-REQ-6.2] WHEN `--json` is active AND a command fails, THE system SHALL preserve the current non-zero exit code.
3. [23-REQ-6.3] WHEN `--json` is active AND a command fails, THE system SHALL NOT emit unstructured error text to stdout.

#### Edge Cases

1. [23-REQ-6.E1] IF an unhandled exception occurs in JSON mode, THEN THE system SHALL emit `{"error": "<exception message>"}` to stdout and exit with code 1.

---

### Requirement 7: JSON Input on Stdin

**User Story:** As an agent, I want to pass command parameters as JSON on stdin, so that I can call commands like a REST API.

#### Acceptance Criteria

1. [23-REQ-7.1] WHEN `--json` is active AND stdin is not a TTY, THE system SHALL attempt to read a JSON object from stdin.
2. [23-REQ-7.2] WHEN JSON input is provided on stdin, THE command SHALL use the parsed fields as parameter defaults (CLI flags take precedence).
3. [23-REQ-7.3] WHEN `--json` is active AND stdin is a TTY (no pipe), THE system SHALL NOT block waiting for input.

#### Edge Cases

1. [23-REQ-7.E1] IF stdin contains invalid JSON, THEN THE system SHALL emit an error envelope `{"error": "invalid JSON input: <details>"}` and exit with code 1.
2. [23-REQ-7.E2] IF stdin contains JSON fields not recognized by the command, THEN THE system SHALL ignore them silently.

---

### Requirement 8: Remove --format and YAML Support

**User Story:** As a maintainer, I want to remove the redundant `--format` option and YAML formatter, so that the codebase has one consistent output switching mechanism.

#### Acceptance Criteria

1. [23-REQ-8.1] THE `status` command SHALL NOT accept a `--format` option.
2. [23-REQ-8.2] THE `standup` command SHALL NOT accept a `--format` option.
3. [23-REQ-8.3] THE `lint-spec` command SHALL NOT accept a `--format` option.
4. [23-REQ-8.4] THE `OutputFormat` enum SHALL NOT contain a `YAML` member.
5. [23-REQ-8.5] THE system SHALL NOT contain YAML formatting code for command output (the `yaml` dependency may remain for other uses).

#### Edge Cases

1. [23-REQ-8.E1] IF a user passes `--format` to a command that previously supported it, THEN THE system SHALL produce a Click usage error (standard Click behavior for unknown options).
