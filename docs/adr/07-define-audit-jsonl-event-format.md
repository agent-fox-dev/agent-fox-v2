---
Title: 07. Define audit JSONL event format
Date: 2026-04-26
Status: Accepted
---

## Context

Agent-fox emits structured audit events throughout its lifecycle — from run
start through session execution, tool calls, review persistence, git
operations, night-shift activities, and knowledge management. These events are
the primary observability mechanism: they power cost tracking, debugging,
post-run analysis, and retention enforcement.

Events are serialized as JSON Lines (one JSON object per line) into files at
`.agent-fox/audit/audit_{run_id}.jsonl`. A single file covers one complete run.
The `AuditJsonlSink` appends events under a threading lock to handle concurrent
session writes safely. Retention is enforced at `max_runs` (default 20) by
`enforce_audit_retention`, which deletes both JSONL files and corresponding
DuckDB rows for the oldest runs.

This ADR documents the canonical event format and the complete event type
catalog so that tooling authors, analysts, and future contributors have a
single reference for the audit schema.

## Decision Drivers

- Engineers analyzing run behavior need a single reference for what each event
  type means and what payload keys to expect
- Tooling that parses JSONL files (dashboards, cost reports, anomaly detection)
  needs a stable schema contract
- The event catalog has grown to 50+ types across engine, session, review,
  night-shift, and knowledge subsystems — informal knowledge no longer scales

## Options Considered

### Option A: Document the format in an ADR

Capture the envelope schema and full event catalog in a versioned,
decision-record format alongside the codebase.

**Pros:**
- Lives next to the code, versioned in git
- Follows the project's existing ADR convention
- Immutable once accepted — future changes create new ADRs

**Cons:**
- May drift from code if new event types are added without updating

### Option B: Auto-generate documentation from the enum

Write a script that introspects `AuditEventType` and emits docs.

**Pros:**
- Always in sync with the enum definition

**Cons:**
- Cannot capture payload schemas (those are in emit-site code, not the enum)
- Requires build tooling maintenance

## Decision

We will **document the format in this ADR** because the payload structures are
defined at emit sites across the codebase, not derivable from the enum alone. A
hand-written reference is the only way to capture the full contract including
payload keys, types, and semantics.

## Envelope Schema

Every audit event is a single JSON object on one line. The envelope fields are
fixed; the `payload` object varies by `event_type`.

```jsonc
{
  "id":         "uuid-v4",              // unique event identifier
  "timestamp":  "ISO-8601+tz",          // UTC, e.g. "2026-04-26T19:02:38.351315+00:00"
  "run_id":     "{YYYYMMDD}_{HHMMSS}_{6-hex}",  // unique run identifier
  "event_type": "category.action",      // dot-separated, see catalog below
  "node_id":    "spec:group[:role]",     // task-graph node, empty for run-level events
  "session_id": "",                      // currently unused in most events
  "archetype":  "coder|reviewer|...",    // archetype name, empty when not applicable
  "severity":   "info|warning|error|critical",
  "payload":    { ... }                  // event-type-specific data
}
```

### Field semantics

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID v4 string | Unique per event, generated at creation |
| `timestamp` | ISO 8601 string | UTC wall-clock time of emission |
| `run_id` | string | Groups all events for one orchestrator run; format `{YYYYMMDD}_{HHMMSS}_{short_hex}` |
| `event_type` | string | Dot-separated category and action (see catalog) |
| `node_id` | string | Task-graph node ID in `{spec_name}:{group_number}` or `{spec_name}:{group_number}:{role}` format; empty for run-level events |
| `session_id` | string | Reserved; populated as `{node_id}:{attempt}` in a few events |
| `archetype` | string | Agent archetype (`coder`, `reviewer`, `verifier`, etc.); empty for non-session events |
| `severity` | string | One of `info`, `warning`, `error`, `critical` |
| `payload` | object | Event-specific data; keys and types vary per `event_type` |

### File naming and location

- **Path:** `.agent-fox/audit/audit_{run_id}.jsonl`
- **Encoding:** UTF-8, one JSON object per line, newline-terminated
- **Concurrency:** Thread-safe via `threading.Lock` in `AuditJsonlSink`
- **Retention:** Oldest files pruned when run count exceeds `max_runs` (default 20)

### Default severity mapping

Most events default to `info`. Exceptions:

| Event type | Default severity |
|-----------|-----------------|
| `session.fail` | `error` |
| `run.limit_reached` | `warning` |
| `git.conflict` | `warning` |
| `harvest.empty` | `warning` |
| `review.parse_failure` | `warning` |

---

## Event Catalog

### Run lifecycle

#### `run.start`

Emitted once at orchestrator startup after the task graph is built.

| Payload key | Type | Description |
|-------------|------|-------------|
| `plan_hash` | string | SHA-256 hash of the serialized task graph |
| `total_nodes` | int | Number of nodes in the plan |
| `parallel` | bool | Whether parallel execution is enabled |

#### `run.complete`

Emitted once when the orchestrator finishes (success or early termination).

| Payload key | Type | Description |
|-------------|------|-------------|
| `total_sessions` | int | Total sessions executed across all nodes |
| `total_cost` | float | Cumulative cost in USD |
| `duration_ms` | int | Wall-clock run duration |
| `run_status` | string | Terminal status: `COMPLETED`, `STALLED`, `COST_LIMIT`, `SESSION_LIMIT`, `BLOCK_LIMIT`, `INTERRUPTED` |

#### `run.limit_reached`

A circuit breaker tripped — cost, session count, or block budget exceeded.

| Payload key | Type | Description |
|-------------|------|-------------|
| `limit_type` | string | `"cost"`, `"sessions"`, or `"block_budget"` |
| `limit_value` | float | The threshold that was hit |
| `blocked_count` | int | (block_budget only) Number of blocked tasks |
| `total_nodes` | int | (block_budget only) Total graph nodes |
| `blocked_fraction` | float | (block_budget only) Fraction blocked (0.0–1.0) |
| `max_blocked_fraction` | float | (block_budget only) Configured ceiling |

#### `config.reloaded`

Hot-reload of configuration detected mid-run.

| Payload key | Type | Description |
|-------------|------|-------------|
| `changed_fields` | dict | Map of `"section.field"` to `{"old": value, "new": value}` |

#### `watch.poll`

Periodic poll in watch mode checking for new work.

| Payload key | Type | Description |
|-------------|------|-------------|
| `poll_number` | int | Incremental counter within the run |
| `new_tasks_found` | bool | Whether new tasks were discovered |

#### `preflight.skip`

A node was skipped because preflight checks determined work is already done.

| Payload key | Type | Description |
|-------------|------|-------------|
| `from_status` | string | Previous status (e.g., `"pending"`) |
| `reason` | string | Skip rationale (e.g., `"checkboxes done, no active findings, tests pass"`) |

---

### Session lifecycle

#### `session.start`

A new agent session is about to begin.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | Agent archetype |
| `model_id` | string | Resolved model identifier |
| `prompt_template` | string | Template name (matches archetype) |
| `attempt` | int | Attempt number for this node |

#### `session.complete`

A session finished successfully.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | Agent archetype |
| `model_id` | string | Model used |
| `prompt_template` | string | Template name |
| `input_tokens` | int | Input tokens consumed |
| `output_tokens` | int | Output tokens generated |
| `cache_read_input_tokens` | int | Tokens served from cache |
| `cache_creation_input_tokens` | int | Tokens written to cache |
| `cost` | float | Session cost in USD |
| `duration_ms` | int | Session wall-clock duration |
| `files_touched` | list[string] | Files modified during session |

#### `session.fail`

A session terminated with an error. Severity: `error`.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | Agent archetype |
| `model_id` | string | Model used |
| `prompt_template` | string | Template name |
| `error_message` | string | Error description |
| `attempt` | int | Which attempt failed |
| `input_tokens` | int | Tokens consumed before failure |
| `output_tokens` | int | Output tokens generated |
| `cache_read_input_tokens` | int | Cache reads |
| `cache_creation_input_tokens` | int | Cache writes |
| `cost` | float | Cost before failure |
| `duration_ms` | int | Duration before failure |

#### `session.retry`

A failed session is being retried (escalation ladder).

| Payload key | Type | Description |
|-------------|------|-------------|
| `attempt` | int | The new attempt number |
| `reason` | string | Why the retry was triggered |

#### `session.timeout_retry`

A session timed out and is being retried with extended parameters.

| Payload key | Type | Description |
|-------------|------|-------------|
| `timeout_retry_count` | int | How many timeout retries so far |
| `max_timeout_retries` | int | Configured maximum |
| `original_max_turns` | int or null | Original turn limit |
| `extended_max_turns` | int or null | Extended turn limit |
| `original_timeout` | int | Original timeout in seconds |
| `extended_timeout` | int | Extended timeout (clamped to ceiling) |

---

### Task graph

#### `task.status_change`

A node's status changed in the task graph.

| Payload key | Type | Description |
|-------------|------|-------------|
| `from_status` | string | Previous status |
| `to_status` | string | New status |
| `reason` | string | Why the transition occurred |
| `coder_node_id` | string | (retry-on-block only) The coder that will retry |
| `regressions` | list[dict] | (coverage regression only) Each: `{file, baseline, current, delta}` |

#### `model.escalation`

A node's model tier was escalated after repeated failures.

| Payload key | Type | Description |
|-------------|------|-------------|
| `from_tier` | string | Previous tier (e.g., `"STANDARD"`) |
| `to_tier` | string | New tier (e.g., `"ADVANCED"`) |
| `reason` | string | Escalation trigger |

#### `sync.barrier`

A sync barrier fired between task-graph phases.

| Payload key | Type | Description |
|-------------|------|-------------|
| `completed_nodes` | list[string] | Node IDs that finished |
| `pending_nodes` | list[string] | Nodes still pending or in-progress |
| `orphaned_worktrees` | list[string] | Orphaned worktree paths cleaned up |
| `develop_sync_status` | string | `"success"` or `"failed"` |

---

### Tool invocation

#### `tool.invocation`

An agent called a tool during its session.

| Payload key | Type | Description |
|-------------|------|-------------|
| `tool_name` | string | Tool name (e.g., `"Bash"`, `"Read"`, `"Write"`, `"Glob"`) |
| `param_summary` | string | Abbreviated parameter string |
| `called_at` | string | ISO 8601 timestamp of the call |

#### `tool.error`

Defined in the enum but not currently emitted via audit events. Tool errors
are recorded through the DuckDB sink's `record_tool_error` method instead.

---

### Git operations

#### `git.merge`

A feature branch was successfully merged into develop.

| Payload key | Type | Description |
|-------------|------|-------------|
| `branch` | string | Feature branch name |
| `commit_sha` | string | Resulting merge commit SHA |
| `files_touched` | list[string] | Files included in the merge |

#### `git.conflict`

A merge conflict occurred. Severity: `warning`.

| Payload key | Type | Description |
|-------------|------|-------------|
| `branch` | string | Branch that conflicted |
| `strategy` | string | Merge strategy attempted (e.g., `"default"`) |
| `error` | string | Conflict error message |

---

### Review persistence

#### `review.findings_persisted`

Pre-review or skeptic findings were written to DuckDB.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | `"skeptic"` or `"reviewer"` |
| `mode` | string or null | `"pre-review"` when using reviewer archetype |
| `count` | int | Number of findings persisted |
| `severity_summary` | dict | Map of severity level to count |
| `spec_name` | string | Spec reviewed |
| `task_group` | string | Task group |

#### `review.verdicts_persisted`

Verifier verdicts were written to DuckDB.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | `"verifier"` |
| `count` | int | Total verdicts |
| `pass_count` | int | PASS verdicts |
| `fail_count` | int | FAIL verdicts |
| `spec_name` | string | Spec verified |
| `task_group` | string | Task group |

#### `review.drift_persisted`

Oracle or drift-review findings were written to DuckDB.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | `"oracle"` or `"reviewer"` |
| `mode` | string or null | `"drift-review"` when using reviewer archetype |
| `count` | int | Number of drift findings |
| `severity_summary` | dict | Severity distribution |
| `spec_name` | string | Spec analyzed |
| `task_group` | string | Task group |

#### `review.parse_failure`

Structured JSON could not be extracted from a reviewer's output.
Severity: `warning`.

| Payload key | Type | Description |
|-------------|------|-------------|
| `raw_output` | string | First 2000 chars of unparseable output |
| `retry_attempted` | bool | Whether a format-retry prompt was sent |
| `strategy` | string | Extraction strategies tried (e.g., `"bracket_scan,retry"`) |
| `all_instances_failed` | bool | (multi-instance only) All instances failed to parse |

#### `review.parse_retry_success`

A format-retry prompt succeeded where initial extraction failed.

| Payload key | Type | Description |
|-------------|------|-------------|
| `archetype` | string | The archetype that recovered |

#### `review.verdict_normalized`

A non-standard verdict value was coerced (e.g., `"PARTIAL"` to `"FAIL"`).
Severity: `warning`.

| Payload key | Type | Description |
|-------------|------|-------------|
| `original_verdict` | string | Raw verdict from model output |
| `normalized_verdict` | string | Coerced standard value |
| `requirement_id` | string | Affected requirement |

#### `review.security_finding_blocked`

A session was blocked due to security-critical review findings.

| Payload key | Type | Description |
|-------------|------|-------------|
| `spec_name` | string | Spec containing security findings |
| `task_group` | string | Task group |
| `security_critical_count` | int | Number of security-critical findings |
| `finding_ids` | list[string] | UUIDs of the blocking findings |

---

### Errata

#### `errata.generated`

Auto-generated errata from reviewer-blocking findings.

| Payload key | Type | Description |
|-------------|------|-------------|
| `spec_name` | string | Spec that triggered errata |
| `task_group` | string | Task group |
| `count` | int | Number of errata records created |

---

### Night-shift

#### `night_shift.start`

The night-shift daemon started.

| Payload key | Type | Description |
|-------------|------|-------------|
| `phase` | string | `"start"` |

#### `night_shift.stop`

The night-shift daemon stopped.

| Payload key | Type | Description |
|-------------|------|-------------|
| `phase` | string | `"stop"` |
| `total_cost` | float | Total cost accumulated |
| `uptime_seconds` | float | Daemon uptime |

#### `night_shift.hunt_scan_complete`

A hunt scan finished analyzing the codebase for issues.

| Payload key | Type | Description |
|-------------|------|-------------|
| `findings_count` | int | Number of findings discovered |

#### `night_shift.issue_created`

A new GitHub issue was filed from hunt findings.

| Payload key | Type | Description |
|-------------|------|-------------|
| `issue_number` | int | GitHub issue number |

#### `night_shift.issue_superseded`

An older issue was closed because a newer issue covers it.

| Payload key | Type | Description |
|-------------|------|-------------|
| `closed_issue` | int | Issue number closed |
| `superseded_by` | int | Replacement issue number |

#### `night_shift.issue_obsolete`

An issue was closed because the underlying problem was already fixed.

| Payload key | Type | Description |
|-------------|------|-------------|
| `closed_issue` | int | Issue number closed |
| `fixed_by` | int | Issue that resolved it |
| `rationale` | string | Explanation from staleness check |

#### `night_shift.fix_start`

The fix pipeline began working on an issue.

| Payload key | Type | Description |
|-------------|------|-------------|
| `issue_number` | int | Issue being fixed |
| `title` | string | Issue title |

#### `night_shift.fix_complete`

An issue fix completed successfully.

| Payload key | Type | Description |
|-------------|------|-------------|
| `issue_number` | int | Fixed issue number |

#### `night_shift.fix_failed`

An issue fix attempt failed.

| Payload key | Type | Description |
|-------------|------|-------------|
| `issue_number` | int | Issue that could not be fixed |

---

### ADR ingestion

#### `adr.validation_failed`

An ADR file failed structural validation during ingestion. Severity: `warning`.

| Payload key | Type | Description |
|-------------|------|-------------|
| `file_path` | string | ADR file path (e.g., `"docs/adr/01-decision.md"`) |
| `diagnostics` | list[string] | Validation error messages |

#### `adr.ingested`

An ADR was successfully ingested into the knowledge store.

| Payload key | Type | Description |
|-------------|------|-------------|
| `file_path` | string | ADR file path |
| `title` | string | ADR title |
| `considered_options_count` | int | Number of options documented |

---

### Defined but not currently emitted

The following event types exist in the `AuditEventType` enum but have no active
emit sites in production code. They are reserved for planned features or were
part of subsystems since removed:

- `harvest.complete`, `harvest.empty` — knowledge harvest lifecycle
- `fact.extracted`, `fact.compacted`, `fact.causal_links`, `fact.cleanup` — fact lifecycle
- `knowledge.ingested`, `knowledge.retrieval` — knowledge store operations
- `consolidation.complete`, `consolidation.cost` — knowledge consolidation
- `SLEEP_COMPUTE_COMPLETE` — sleep/compute cycle tracking
- `quality_gate.result` — quality gate evaluation
- `model.assessment` — model tier assessment
- `tool.error` — tool error recording (errors go through DuckDB sink instead)

---

## Consequences

### Positive

- Single reference for all event types, payload schemas, and envelope fields
- Tooling authors can parse JSONL files with confidence in field types
- New event types can be documented by appending to the catalog

### Negative / Trade-offs

- This document will drift as new event types are added; contributors must
  update it alongside code changes
- Payload schemas are descriptive, not enforced — the source of truth remains
  the emit-site code in each subsystem

### Neutral / Follow-up actions

- Unused event types should be pruned in a future cleanup pass
- Consider adding JSON Schema validation for payloads at emit time to catch
  contract violations during development

## References

- `agent_fox/knowledge/audit.py` — enum, dataclass, serialization, JSONL sink
- `agent_fox/engine/audit_helpers.py` — shared `emit_audit_event` helper
- Spec 40 requirements (`40-REQ-1.*` through `40-REQ-12.*`) — audit system design
