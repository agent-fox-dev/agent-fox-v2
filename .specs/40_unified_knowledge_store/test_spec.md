# Test Specification

## Conventions

- Test IDs follow the format `TS-40-XX` where `XX` is sequential.
- Each test maps to one or more requirements via `[40-REQ-X.Y]`.
- Tests are language-agnostic contracts; implementations use pytest.

---

## Unit Tests

### Package Consolidation

**TS-40-01** — All public APIs importable from `agent_fox.knowledge`
Verify that `Fact`, `Category`, `parse_confidence`, `append_facts`,
`load_all_facts`, `load_facts_by_spec`, `write_facts`, `MemoryStore`,
`extract_facts`, `compact`, `select_relevant_facts`, `render_summary` are
importable from `agent_fox.knowledge` submodules.
Req: [40-REQ-1.1], [40-REQ-1.3]

**TS-40-02** — `agent_fox.memory` import raises ImportError
Verify that `import agent_fox.memory` raises `ImportError`.
Req: [40-REQ-1.2], [40-REQ-1.E1]

### Audit Event Model

**TS-40-03** — AuditEvent construction with all fields
Verify that an `AuditEvent` can be constructed with all required fields and
serialized to dict/JSON. Verify `event_type` is an `EventType` enum member and
`severity` is a `Severity` enum member.
Req: [40-REQ-4.1]

**TS-40-04** — Run ID format
Verify that `generate_run_id()` produces a string matching
`YYYYMMDD_HHMMSS_[0-9a-f]{8}`.
Req: [40-REQ-4.2]

**TS-40-05** — EventType enum completeness
Verify that `EventType` contains all 20 event types from the PRD table.
Req: [40-REQ-4.1]

**TS-40-06** — Severity enum values
Verify `Severity` has exactly four members: `info`, `warning`, `error`,
`critical`.
Req: [40-REQ-4.1]

### Enriched Tool Call Records

**TS-40-07** — param_summary from file path input
Given a `ToolUseMessage` with `tool_input={"file_path": "/a/b/c/d/e.py"}`,
verify `_derive_param_summary()` returns a shortened path (e.g. `…/d/e.py` or
`e.py`).
Req: [40-REQ-11.2]

**TS-40-08** — param_summary from long string input
Given a `ToolUseMessage` with a string argument exceeding 120 characters, verify
`_derive_param_summary()` returns a string of at most 120 characters.
Req: [40-REQ-11.3]

**TS-40-09** — param_summary None for non-string inputs
Given a `ToolUseMessage` with `tool_input={"count": 5, "flag": True}`, verify
`_derive_param_summary()` returns `None`.
Req: [40-REQ-11.4]

**TS-40-10** — param_summary exception handling
Given a `ToolUseMessage` whose `tool_input` causes `abbreviate_arg()` to raise,
verify `_derive_param_summary()` returns `None` without propagating the
exception.
Req: [40-REQ-11.E1]

**TS-40-11** — tool.invocation event structure
Verify that a `tool.invocation` event has `event_type=EventType.TOOL_INVOCATION`
and payload contains `tool_name`, `param_summary`, and `called_at`.
Req: [40-REQ-11.1]

**TS-40-12** — tool.error event structure
Verify that a `tool.error` event has `event_type=EventType.TOOL_ERROR` and
payload contains `tool_name`, `param_summary`, and `failed_at`.
Req: [40-REQ-11.5]

### Model Interaction Records

**TS-40-13** — session.start payload includes model interaction fields
Verify that a `session.start` event payload contains `archetype`, `model_id`,
and `prompt_template` fields.
Req: [40-REQ-12.1]

**TS-40-14** — session.complete payload includes model interaction fields
Verify that a `session.complete` event payload contains `archetype`, `model_id`,
`prompt_template`, `input_tokens`, `output_tokens`, `cost`, `duration_ms`, and
`files_touched`.
Req: [40-REQ-12.2]

**TS-40-15** — session.fail payload includes model interaction fields
Verify that a `session.fail` event payload contains `archetype`, `model_id`,
`prompt_template`, and `error_message`.
Req: [40-REQ-12.3]

**TS-40-16** — prompt_template is filename only
Given archetype `"coder"`, verify `prompt_template` is `"coding.md"` (not a
full path or rendered content).
Req: [40-REQ-12.4]

**TS-40-17** — unknown archetype yields prompt_template "unknown"
Given an archetype name not in `ARCHETYPE_REGISTRY`, verify `prompt_template`
is set to `"unknown"`.
Req: [40-REQ-12.E1]

**TS-40-18** — full prompt text is not stored
Verify that no field in `session.start`, `session.complete`, or `session.fail`
payloads contains the full system prompt or task prompt text.
Req: [40-REQ-12.5]

### In-Memory State Machine

**TS-40-19** — Facts accumulate without DuckDB write
Add facts to `KnowledgeStateMachine`. Verify they are retrievable in memory but
not yet in DuckDB until `flush()` is called.
Req: [40-REQ-2.2]

**TS-40-20** — Flush persists all pending facts
Add 5 facts, call `flush()`. Verify all 5 are now in the `memory_facts` table.
Req: [40-REQ-2.3]

**TS-40-21** — JSONL export after flush
After `flush()`, verify `memory.jsonl` is written with content matching the
DuckDB state.
Req: [40-REQ-2.4]

**TS-40-22** — Audit events bypass state machine
Verify that calling `emit_audit_event()` writes directly to DuckDB/JSONL
without buffering in the state machine.
Req: [40-REQ-2.5]

**TS-40-23** — DuckDB flush failure retains in-memory state
Mock DuckDB write to fail. Verify facts remain in memory after failed flush.
Call `flush()` again with DuckDB restored; verify facts are persisted.
Req: [40-REQ-2.E1]

### DuckDB Primary Persistence

**TS-40-24** — Facts loaded from DuckDB
Insert facts directly into DuckDB. Verify `load_all_facts()` reads from DuckDB.
Req: [40-REQ-3.2]

**TS-40-25** — JSONL derived from DuckDB
Insert facts into DuckDB, export JSONL. Verify JSONL content matches DuckDB
records.
Req: [40-REQ-3.3]

### Audit Event Persistence

**TS-40-26** — Dual-write to DuckDB and JSONL
Emit an audit event. Verify the event appears in both the DuckDB
`audit_events` table and the per-run JSONL file.
Req: [40-REQ-5.1]

**TS-40-27** — Per-run JSONL file naming
Start a run with `run_id="20260312_100000_abcd1234"`. Verify the JSONL file is
named `audit_20260312_100000_abcd1234.jsonl`.
Req: [40-REQ-5.2]

**TS-40-28** — audit_events table created by migration
Apply the new migration to a fresh DuckDB. Verify the `audit_events` table
exists with columns: `id`, `timestamp`, `run_id`, `event_type`, `node_id`,
`session_id`, `archetype`, `severity`, `payload`.
Req: [40-REQ-5.3], [40-REQ-9.1]

**TS-40-29** — SinkDispatcher dispatches emit_audit_event
Create a `SinkDispatcher` with two mock sinks. Emit an audit event. Verify
both sinks received the event.
Req: [40-REQ-5.4]

**TS-40-30** — JSONL write failure does not block
Mock JSONL file write to fail. Verify the audit event still reaches DuckDB and
no exception propagates.
Req: [40-REQ-5.E1]

**TS-40-31** — DuckDB write failure does not block
Mock DuckDB insert to fail. Verify the audit event still reaches JSONL and no
exception propagates.
Req: [40-REQ-5.E2]

**TS-40-32** — Both writes fail, event lost gracefully
Mock both DuckDB and JSONL to fail. Verify no exception propagates and an error
is logged.
Req: [40-REQ-5.E3]

### Log Retention

**TS-40-33** — Retention enforced at run start
Create 25 JSONL files in the audit directory. Start a new run with retention=20.
Verify the 5 oldest files are deleted and the new file is created.
Req: [40-REQ-6.1], [40-REQ-6.2]

**TS-40-34** — Configurable retention limit
Set `audit_log_retention=5` in config. Create 10 files. Verify only 5 remain
after enforcement.
Req: [40-REQ-6.3]

**TS-40-35** — Empty audit directory is no-op
Call retention enforcement on a non-existent directory. Verify no error.
Req: [40-REQ-6.E1]

### Schema Migration

**TS-40-36** — Migration upgrades existing database
Open a DuckDB with schema version N (pre-audit). Apply migrations. Verify
`audit_events` table exists and schema version is incremented.
Req: [40-REQ-9.1], [40-REQ-9.2]

**TS-40-37** — Migration failure leaves database intact
Mock the migration DDL to fail. Verify the database remains at its original
schema version and `KnowledgeStoreError` is raised.
Req: [40-REQ-9.E1]

### Knowledge Ingestion Audit Trail

**TS-40-38** — ADR ingestion emits audit event
Trigger ADR ingestion. Verify a `knowledge.ingested` event is emitted with
`source_type=adr`.
Req: [40-REQ-10.1]

**TS-40-39** — Git commit ingestion emits audit event
Trigger commit ingestion. Verify a `knowledge.ingested` event with
`source_type=commit`.
Req: [40-REQ-10.2]

**TS-40-40** — Errata ingestion emits audit event
Trigger errata ingestion. Verify a `knowledge.ingested` event with
`source_type=errata`.
Req: [40-REQ-10.3]

**TS-40-41** — Partial ingestion failure reports count
Mock ingestion to fail after 3 of 5 items. Verify the event reports
`item_count=3`.
Req: [40-REQ-10.E1]

---

## Integration Tests

### CLI: `agent-fox audit`

**TS-40-42** — Default output shows most recent run
Seed DuckDB with events from two runs. Invoke `agent-fox audit`. Verify output
contains only events from the most recent run.
Req: [40-REQ-7.1]

**TS-40-43** — `--json` outputs JSON array
Invoke `agent-fox audit --json`. Verify output is valid JSON and is an array of
event objects.
Req: [40-REQ-7.2]

**TS-40-44** — `--list-runs` shows run summaries
Seed 3 runs. Invoke `--list-runs`. Verify output lists 3 run IDs with
timestamps and event counts.
Req: [40-REQ-7.3]

**TS-40-45** — `--event-type` filter
Seed events of types `session.start` and `session.complete`. Filter with
`--event-type session.start`. Verify only `session.start` events in output.
Req: [40-REQ-7.4]

**TS-40-46** — `--node-id` filter
Seed events for nodes `spec:1` and `spec:2`. Filter `--node-id spec:1`. Verify
only `spec:1` events.
Req: [40-REQ-7.5]

**TS-40-47** — `--since` filter
Seed events at T-1h and T-5m. Filter `--since T-30m`. Verify only the recent
event.
Req: [40-REQ-7.6]

**TS-40-48** — `--run` filter
Seed two runs. Filter `--run <older_run_id>`. Verify only events from that run.
Req: [40-REQ-7.7]

**TS-40-49** — Compound filters (AND semantics)
Seed diverse events. Filter `--event-type session.complete --node-id spec:1`.
Verify only matching events.
Req: [40-REQ-7.8]

**TS-40-50** — No matching events
Filter with `--event-type nonexistent`. Verify "no events found" message and
exit code 0.
Req: [40-REQ-7.E1]

**TS-40-51** — DuckDB unavailable
Delete the DuckDB file. Invoke `agent-fox audit`. Verify error message and
exit code 1.
Req: [40-REQ-7.E2]

**TS-40-52** — Unknown run ID
Filter `--run bad_id`. Verify "run not found" error and exit code 1.
Req: [40-REQ-7.E3]

### Reporting Migration

**TS-40-53** — `status` reads from DuckDB
Seed DuckDB with session outcomes and audit events. Invoke `agent-fox status`.
Verify output reflects DuckDB data.
Req: [40-REQ-8.1]

**TS-40-54** — `standup` reads from DuckDB
Seed DuckDB with session data. Invoke `agent-fox standup`. Verify output.
Req: [40-REQ-8.2]

### End-to-End Session Audit Trail

**TS-40-55** — Full session lifecycle emits all expected events
Run a mock session through `NodeSessionRunner`. Verify the audit trail contains:
`session.start` (with archetype, model_id, prompt_template),
`tool.invocation` events (with param_summary),
`session.complete` (with archetype, model_id, prompt_template, tokens).
Req: [40-REQ-4.3], [40-REQ-11.1], [40-REQ-12.1], [40-REQ-12.2]

**TS-40-56** — Tool invocation events are not debug-gated
Run a session with `debug=False`. Verify `tool.invocation` events are still
emitted to the audit trail.
Req: [40-REQ-11.6]

---

## Property Tests

**TS-40-P1** — Run ID uniqueness
Generate 1000 run IDs. Verify all are unique.
Req: [40-REQ-4.2]

**TS-40-P2** — AuditEvent round-trip serialization
For any valid `AuditEvent`, serialize to JSON and deserialize. Verify equality.
Req: [40-REQ-4.1]

**TS-40-P3** — param_summary length bound
For any string input to `_derive_param_summary()`, verify the result is either
`None` or at most 120 characters.
Req: [40-REQ-11.3]

**TS-40-P4** — param_summary never raises
For any dict input to `_derive_param_summary()`, verify it returns without
raising.
Req: [40-REQ-11.E1]

**TS-40-P5** — Retention never deletes more than excess
For any N files and retention limit M, verify exactly `max(0, N - M)` files are
deleted.
Req: [40-REQ-6.1]

**TS-40-P6** — Flush idempotence
Flush with empty pending list. Verify no DuckDB writes and no errors.
Req: [40-REQ-2.3]
