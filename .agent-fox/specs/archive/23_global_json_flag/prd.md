# PRD: Global --json Flag on Every Command

## Overview

Add a global `--json` flag to the `agent-fox` CLI group so that every
subcommand can produce structured JSON output. When active, commands read
input from stdin as JSON and emit results as JSON (or JSONL for streaming
commands). This enables agents and scripts to call agent-fox like a REST API
with structured request/response payloads.

## Problem Statement

Today the CLI is human-first. Most commands produce unstructured text output.
Two commands (`status`, `standup`) have a `--format` flag that supports
`table`, `json`, and `yaml`, and `lint-spec` has a similar `--format` option.
There is no consistency across commands, and no way for an agent to consume
structured output from commands like `plan`, `patterns`, `compact`, or
`ingest`.

The YAML and table options on `--format` add maintenance surface but provide
little value — agents need JSON, humans get the default text output. A single
boolean `--json` flag is simpler and sufficient.

## Goals

1. Add `--json` as a global flag on the `main` Click group, accessible to
   every subcommand via `ctx.obj["json"]`.
2. When `--json` is active:
   - Suppress the fox banner (it would corrupt JSON output).
   - Commands accept optional JSON input on stdin.
   - Commands emit structured JSON (or JSONL for streaming) to stdout.
   - Errors produce a JSON error envelope on stdout (exit codes unchanged).
3. Remove existing `--format` options from `status`, `standup`, and
   `lint-spec`. Replace them with `--json` toggle behavior.
4. Remove YAML formatting support (`OutputFormat.YAML`, `format_yaml`,
   YAML formatter classes) — it is unused outside `--format`.
5. Each command defines its own JSON schema; schemas are undocumented
   initially and may evolve.

## Non-Goals

- Formal JSON schema validation or OpenAPI spec generation.
- Versioned JSON output contracts (future enhancement).
- WebSocket or HTTP server mode.

## Commands and Their JSON Behavior

| Command | Input (stdin) | Output (stdout) | Format |
|---------|--------------|-----------------|--------|
| `status` | (none) | Status report | JSON object |
| `standup` | (none) | Standup report | JSON object |
| `lint-spec` | (none) | Findings + summary | JSON object |
| `plan` | (none) | Execution plan | JSON object |
| `patterns` | (none) | Pattern results | JSON object |
| `compact` | (none) | Compaction stats | JSON object |
| `ingest` | (none) | Ingestion stats | JSON object |
| `init` | (none) | `{"status": "ok"}` | JSON object |
| `reset` | (none) | Reset summary | JSON object |
| `ask` | `{"question": "..."}` | Answer + sources | JSON object |
| `code` | `{"task": "..."}` | Progress events | JSONL stream |
| `fix` | `{"issue": "..."}` | Progress events | JSONL stream |

## Clarifications

1. **JSON input:** When `--json` is active, commands MAY read a JSON object
   from stdin for their parameters (e.g., `echo '{"spec": "foo"}' |
   agent-fox plan --json`). CLI flags still take precedence over stdin
   fields.
2. **Streaming commands:** Interactive/streaming commands (`code`, `fix`)
   emit one JSON object per line (JSONL) so clients can consume events
   incrementally.
3. **Banner suppression:** When `--json` is active, the fox banner is
   suppressed entirely (equivalent to `--quiet` for the banner).
4. **Error envelope:** On failure, commands emit
   `{"error": "<message>"}` to stdout AND preserve the current non-zero
   exit code.
5. **Init/reset envelope:** Commands with side-effect-only behavior emit
   `{"status": "ok"}` on success.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 4 | 2 | Uses CLI group structure, Click options, banner rendering from group 4 |
| 07_operational_commands | 3 | 2 | Uses `status`, `standup` formatters and `OutputFormat` from group 3 |
| 09_spec_validation | 4 | 2 | Uses `lint-spec` CLI command structure and `format_json` from group 4 |
