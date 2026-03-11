# PRD: Unified Knowledge Store & Structured Audit Log

> Combined from GitHub issues #142 and #143.

## Summary

This spec consolidates the `agent_fox/memory/` and `agent_fox/knowledge/`
packages into a single `knowledge/` package, makes DuckDB the primary
persistence layer for facts, introduces a structured audit log with typed event
schemas and dual-write to DuckDB, separates the audit log from the execution
state checkpoint, extends the existing sink architecture to handle audit events,
introduces an in-memory state machine for facts and findings (but not audit
events), adds a CLI `agent-fox audit` command, and establishes a log retention
policy.

## Current State

Two overlapping packages handle persistent knowledge:

- **`memory/`** (7 files) -- JSONL-based fact store with `Fact` dataclass,
  extraction via LLM, compaction, filtering, rendering. Primary store:
  `.agent-fox/memory.jsonl` (git-tracked).
- **`knowledge/`** (14 files) -- DuckDB-centric structured storage: migrations,
  review findings, verification results, embeddings, vector search, causal
  graphs, sinks, ingest. Primary store: `.agent-fox/knowledge.duckdb`
  (gitignored).

The boundary is blurry: `memory/` dual-writes to DuckDB, `knowledge/` reads
from JSONL. `state.jsonl` captures session history but lacks structured event
types and isn't queryable. The existing `SessionSink` / `SinkDispatcher`
infrastructure handles session outcome dual-write but has no audit event
support. `KnowledgeIngestor` ingests ADRs and git commits but is disconnected
from the audit trail.

### Observability Gaps

The existing `tool_calls` and `tool_errors` DuckDB tables record only the tool
name and timestamp -- no parameter data, no return summary. This makes it
impossible to reconstruct what an agent actually did during a session without
re-reading raw transcripts.

Model interactions are similarly opaque: `session_outcomes` records aggregate
token counts, but not which archetype invoked which model with which prompt
template. The system prompt and task prompt are generated at runtime and
discarded after use. There is no record of the prompt template name (e.g.
`coding.md`, `skeptic.md`) or the resolved model ID per session in a queryable
audit trail.

## Proposed Architecture

1. **Single `knowledge/` package** -- all code from `memory/` moves into
   `knowledge/`, `memory/` package is deleted.
2. **DuckDB as primary persistence** -- `memory_facts` table is the source of
   truth for facts.
3. **JSONL as export format** -- `memory.jsonl` is derived from DuckDB, written
   at the same points where it would currently be written (session end,
   compaction).
4. **In-memory state machine (facts and findings only)** -- facts and findings
   accumulate in memory during an orchestrator run; flushed to DuckDB at: end
   of task group, sync barriers, and session end. Audit events are **not**
   buffered -- they are written immediately on emission (see below).
5. **Execution state checkpoint preserved** -- `StateManager` and its
   per-session persistence to DuckDB continue to function as they do today.
   The execution state checkpoint is separate from the audit log.
6. **Structured audit log** -- a new append-only event stream with typed
   schemas. Each event is dual-written to a per-run JSONL file and the DuckDB
   `audit_events` table **immediately on emission** (not buffered). This
   ensures crash-resilient traceability.
7. **Extend existing sink architecture** -- the `SinkDispatcher` /
   `SessionSink` protocol is extended to support audit event emission,
   avoiding a parallel dual-write system. Both `DuckDBSink` and a new
   `AuditJsonlSink` implement audit event writing.
8. **Per-run log files with retention** -- each orchestrator run gets its own
   `audit_{run_id}.jsonl` file. A retention policy limits disk growth.
9. **CLI query command** -- `agent-fox audit` for querying the audit trail from
   DuckDB.
10. **Knowledge ingestion events** -- `KnowledgeIngestor` operations (ADR
    ingestion, git commit ingestion) emit audit events, making all knowledge
    pipeline activity visible in the audit trail.

## Run ID

A **run ID** uniquely identifies a single orchestrator invocation. Format:
`{YYYYMMDD}_{HHMMSS}_{short_hex}` where `short_hex` is the first 8 characters
of a UUID4 hex. Example: `20260311_173000_a1b2c3d4`.

The run ID is:
- Generated at the start of `Orchestrator.run()`.
- Stored in the DuckDB `audit_events` table as a queryable column.
- Used as the suffix for the per-run JSONL file name.
- Discoverable via `agent-fox audit --list-runs`.

## Event Types

| Event Type | Emitted By | Key Fields |
|---|---|---|
| `run.start` | engine | run_id, plan_hash, total_nodes, parallel |
| `run.complete` | engine | run_id, total_sessions, total_cost, duration_ms, run_status |
| `run.limit_reached` | engine | run_id, limit_type (cost\|session\|stall), limit_value |
| `session.start` | session_lifecycle | node_id, session_id, archetype, model_id, prompt_template, attempt |
| `session.complete` | session_lifecycle | node_id, session_id, archetype, model_id, prompt_template, tokens, cost, duration_ms, files_touched |
| `session.fail` | session_lifecycle | node_id, session_id, archetype, model_id, prompt_template, error_message, attempt |
| `session.retry` | engine | node_id, session_id, attempt, reason |
| `task.status_change` | engine | node_id, from_status, to_status, reason |
| `model.escalation` | routing | node_id, from_tier, to_tier, reason |
| `model.assessment` | routing | node_id, predicted_tier, confidence, method |
| `archetype.finding` | session_lifecycle | node_id, session_id, archetype, finding_count, severity_summary |
| `git.merge` | harvest | node_id, branch, commit_sha, files_touched |
| `git.conflict` | harvest | node_id, branch, strategy, error |
| `harvest.complete` | session_lifecycle | node_id, commit_sha, facts_extracted, findings_persisted |
| `fact.extracted` | knowledge_harvest | node_id, session_id, fact_count, categories |
| `fact.compacted` | compaction | facts_before, facts_after, superseded_count |
| `knowledge.ingested` | ingest | source_type (adr\|commit\|errata), source_path, item_count |
| `tool.invocation` | session | session_id, node_id, tool_name, param_summary, called_at |
| `tool.error` | session | session_id, node_id, tool_name, param_summary, failed_at |
| `sync.barrier` | engine | completed_nodes, pending_nodes |

## Event Severity

Every audit event carries a `severity` field with one of four values:

| Severity | Usage |
|---|---|
| `info` | Normal operations (session start/complete, run start/complete, fact extraction) |
| `warning` | Degraded but recoverable (JSONL write failure, flush retry, model escalation) |
| `error` | Failures requiring attention (session failure, git conflict, DuckDB write failure) |
| `critical` | Blocking failures (run limit reached with stall, migration failure) |

## Enriched Tool Call Records

The existing `tool_calls` table is replaced by `tool.invocation` audit events
with richer data. Each tool invocation emitted during a session captures:

- **`tool_name`**: the tool used (e.g. `Read`, `Edit`, `Bash`).
- **`param_summary`**: a short, human-readable summary of the tool input.
  For file-oriented tools this is the shortened file path (basename or last two
  components with `…/` prefix when truncated). For other tools, the first
  string argument abbreviated to ≤120 characters. `None` when no meaningful
  summary can be derived.
- **`session_id`**, **`node_id`**, **`called_at`**: same context fields as
  today.

Tool errors (`tool.error`) carry the same fields. Both event types are emitted
as audit events (not debug-only), replacing the legacy `tool_calls` /
`tool_errors` tables which are retained but deprecated.

The `param_summary` reuses the existing `abbreviate_arg()` helper from
`agent_fox.ui.events` for consistent abbreviation.

## Model Interaction Records

Every session emits `session.start`, `session.complete`, and `session.fail`
events that now include model interaction metadata:

- **`archetype`**: the agent archetype that ran the session (e.g. `coder`,
  `skeptic`, `verifier`, `oracle`).
- **`model_id`**: the resolved model identifier (e.g. `claude-sonnet-4-6`),
  not the tier name.
- **`prompt_template`**: the filename of the prompt template used to build
  the system prompt (e.g. `coding.md`, `skeptic.md`, `oracle.md`). Derived
  from the archetype at prompt build time.

These fields enable queries like "which model did the skeptic use for spec X?"
and "how many tokens did oracle sessions consume across all runs?"

The full system prompt and task prompt text are NOT stored (they are large and
contain session-specific context). The `prompt_template` name is sufficient to
identify the instructions used. Session-level token counts (input/output)
remain on `session.complete` events.

## CLI: `agent-fox audit`

- Default: human-readable chronological output of the most recent run
  (narrative style, no tables).
- `--json`: pure JSON array of events.
- `--list-runs`: display available run IDs with timestamps and summary stats.
- Filters: `--event-type TYPE`, `--node-id ID`, `--since TIMESTAMP`,
  `--run RUN_ID`.
- Filters compose with AND semantics.

## Log Retention

- Default retention: last 20 runs' JSONL files.
- Configurable via `config.toml`:
  ```toml
  [knowledge]
  audit_log_retention = 20  # number of runs to keep
  ```
- Retention is enforced at the start of each orchestrator run: before creating
  a new log file, delete the oldest JSONL files exceeding the retention limit.
- DuckDB audit data is not subject to retention (queryable indefinitely).
  A future spec may add DuckDB data retention if needed.

## Clarifications

1. Package name: `knowledge/` (move code from `memory/` there, delete
   `memory/` package).
2. JSONL export: `memory.jsonl` is written at the same points where it would
   currently be written.
3. **Audit log and execution state checkpoint are separate concerns.**
   `StateManager` continues to persist `ExecutionState` after every session
   (as today). The audit log is a new, parallel event stream. They are not
   the same file or data structure.
4. Dual-write for audit events: best-effort to both JSONL and DuckDB. Not
   atomic -- either side may fail independently. The word "dual-write" means
   "write to both destinations" not "transactional atomicity."
5. In-memory state machine scope: facts and findings only. Audit events bypass
   the state machine and are written immediately. Execution state checkpoint
   is unchanged from today.
6. Event schemas are typed (not schemaless JSON). The `payload` field is a
   typed dict whose shape is determined by the `event_type` enum variant.
7. The existing `SinkDispatcher` / `SessionSink` protocol is extended (not
   replaced) to support audit event emission.
8. `KnowledgeIngestor` emits audit events when ingesting ADRs, git commits, or
   errata, making knowledge pipeline activity visible in the audit trail.
9. Reporting modules (`status.py`, `standup.py`) continue reading from the same
   data but via DuckDB queries instead of parsing JSONL.
10. The `run_id` is generated as `{YYYYMMDD}_{HHMMSS}_{short_hex}` and is
    discoverable via `agent-fox audit --list-runs`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 11_duckdb_knowledge_store | 3 | 1 | DuckDB schema and migration infrastructure used from group 3 |
| 27_structured_review_records | 2 | 2 | Review store CRUD and parsers imported; group 2 defines the tables |
| 34_token_tracking | 1 | 3 | Token accumulator and pricing config used for cost fields in audit events |

## Risk

High -- touches many modules across the codebase. All imports from
`agent_fox.memory.*` must be rewritten. The sink protocol extension requires
updating all existing sink implementations. Should be done on a dedicated
branch with thorough testing.
