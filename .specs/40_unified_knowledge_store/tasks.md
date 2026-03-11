# Tasks

- [ ] 1. Write failing tests for all requirements
  - [ ] 1.1 Unit tests for package consolidation (TS-40-01, TS-40-02)
  - [ ] 1.2 Unit tests for audit event model, enums, run ID (TS-40-03 through TS-40-06)
  - [ ] 1.3 Unit tests for enriched tool call records (TS-40-07 through TS-40-12)
  - [ ] 1.4 Unit tests for model interaction records (TS-40-13 through TS-40-18)
  - [ ] 1.5 Unit tests for in-memory state machine (TS-40-19 through TS-40-23)
  - [ ] 1.6 Unit tests for DuckDB primary persistence (TS-40-24, TS-40-25)
  - [ ] 1.7 Unit tests for audit event persistence and sink dispatch (TS-40-26 through TS-40-32)
  - [ ] 1.8 Unit tests for log retention (TS-40-33 through TS-40-35)
  - [ ] 1.9 Unit tests for schema migration (TS-40-36, TS-40-37)
  - [ ] 1.10 Unit tests for knowledge ingestion audit trail (TS-40-38 through TS-40-41)
  - [ ] 1.11 Integration tests for CLI audit command (TS-40-42 through TS-40-52)
  - [ ] 1.12 Integration tests for reporting migration (TS-40-53, TS-40-54)
  - [ ] 1.13 Integration tests for end-to-end session audit trail (TS-40-55, TS-40-56)
  - [ ] 1.14 Property tests (TS-40-P1 through TS-40-P6)

- [ ] 2. Audit event data model and enums
  - [ ] 2.1 Create `knowledge/audit.py` with `AuditEvent` dataclass, `EventType` enum (20 variants), `Severity` enum, `generate_run_id()`, and `serialize_event()` helper
  - [ ] 2.2 Add `_derive_param_summary()` function using existing `abbreviate_arg()` — returns shortened file path or abbreviated first string arg (≤120 chars) or None
  - [ ] 2.3 Add prompt_template resolution helper that maps archetype name → template filename via `ARCHETYPE_REGISTRY`, defaulting to `"unknown"`

- [ ] 3. DuckDB migration and audit_events table
  - [ ] 3.1 Add new versioned migration creating `audit_events` table with columns: id (UUID PK), timestamp, run_id, event_type, node_id, session_id, archetype, severity, payload (JSON)
  - [ ] 3.2 Add indexes on run_id, event_type, node_id, timestamp
  - [ ] 3.3 Verify migration idempotency and upgrade from prior schema version

- [ ] 4. Sink protocol extension and implementations
  - [ ] 4.1 Add `emit_audit_event(event: AuditEvent)` method to `SessionSink` protocol
  - [ ] 4.2 Extend `SinkDispatcher` to dispatch `emit_audit_event` to all sinks
  - [ ] 4.3 Implement `DuckDBSink.emit_audit_event()` — INSERT into `audit_events`
  - [ ] 4.4 Create `AuditJsonlSink` — appends JSON lines to `audit_{run_id}.jsonl` under `.agent-fox/audit/`, flush after each write

- [ ] 5. Tool invocation and model interaction event emission
  - [ ] 5.1 Wire `tool.invocation` event emission into `_execute_query()` message loop — emit on every `ToolUseMessage` with `tool_name` and `param_summary` (unconditional, not debug-gated)
  - [ ] 5.2 Wire `tool.error` event emission for failed tool uses
  - [ ] 5.3 Capture `prompt_template` in `NodeSessionRunner._build_prompts()` from `ArchetypeEntry.templates[0]`
  - [ ] 5.4 Wire `session.start` event emission with archetype, model_id, prompt_template, attempt
  - [ ] 5.5 Wire `session.complete` event emission with archetype, model_id, prompt_template, tokens, cost, duration_ms, files_touched
  - [ ] 5.6 Wire `session.fail` event emission with archetype, model_id, prompt_template, error_message, attempt
  - [ ] 5.7 Deprecate (but retain) legacy `record_tool_call()` / `record_tool_error()` paths

- [ ] 6. Orchestrator-level event emission
  - [ ] 6.1 Generate run_id at start of `Orchestrator.run()` and pass through to sinks
  - [ ] 6.2 Emit `run.start` event with plan_hash, total_nodes, parallel flag
  - [ ] 6.3 Emit `run.complete` event with total_sessions, total_cost, duration_ms, run_status
  - [ ] 6.4 Emit `run.limit_reached` on cost/session/stall limits
  - [ ] 6.5 Emit `task.status_change` on node state transitions
  - [ ] 6.6 Emit `model.escalation` and `model.assessment` from routing
  - [ ] 6.7 Emit `sync.barrier` events
  - [ ] 6.8 Emit `git.merge`, `git.conflict`, `harvest.complete` from harvest lifecycle
  - [ ] 6.9 Emit `fact.extracted` and `fact.compacted` from knowledge harvest and compaction
  - [ ] 6.10 Emit `knowledge.ingested` from KnowledgeIngestor

- [ ] 7. Log retention
  - [ ] 7.1 Implement `enforce_retention()` — delete oldest JSONL files exceeding limit
  - [ ] 7.2 Call `enforce_retention()` at start of orchestrator run
  - [ ] 7.3 Add `audit_log_retention` config field under `[knowledge]` with default 20

- [ ] 8. Package consolidation
  - [ ] 8.1 Move all modules from `agent_fox/memory/` into `agent_fox/knowledge/`
  - [ ] 8.2 Update `agent_fox/knowledge/__init__.py` to re-export all public APIs
  - [ ] 8.3 Rewrite all imports from `agent_fox.memory.*` to `agent_fox.knowledge.*` across the codebase
  - [ ] 8.4 Delete `agent_fox/memory/` package
  - [ ] 8.5 Verify no remaining `agent_fox.memory` imports via grep

- [ ] 9. In-memory state machine
  - [ ] 9.1 Implement `KnowledgeStateMachine` with `add_fact()`, `add_finding()`, `flush()`, `load_facts()`
  - [ ] 9.2 Wire flush calls at end of task group, sync barriers, and session end
  - [ ] 9.3 Wire JSONL export after each flush
  - [ ] 9.4 Make DuckDB the primary read path for `load_all_facts()` and related functions

- [ ] 10. DuckDB primary fact persistence
  - [ ] 10.1 Switch `load_all_facts()`, `load_facts_by_spec()`, `select_relevant_facts()` to read from DuckDB
  - [ ] 10.2 Make `memory.jsonl` export derived from DuckDB (write-only, not read)
  - [ ] 10.3 Update `MemoryStore` to use DuckDB as primary store

- [ ] 11. CLI: `agent-fox audit`
  - [ ] 11.1 Create `agent_fox/cli/audit.py` with Click command
  - [ ] 11.2 Implement default human-readable chronological output
  - [ ] 11.3 Implement `--json` output mode
  - [ ] 11.4 Implement `--list-runs` with summary statistics
  - [ ] 11.5 Implement filters: `--event-type`, `--node-id`, `--since`, `--run`
  - [ ] 11.6 Implement AND-composed filter semantics
  - [ ] 11.7 Register audit command in main CLI group

- [ ] 12. Reporting migration
  - [ ] 12.1 Update `status.py` to query DuckDB instead of parsing state.jsonl/memory.jsonl
  - [ ] 12.2 Update `standup.py` to query DuckDB instead of parsing state.jsonl
  - [ ] 12.3 Verify output parity with legacy implementation

- [ ] 13. Checkpoint: full test suite and lint
  - [ ] 13.1 All spec-40 tests pass
  - [ ] 13.2 Full test suite passes (no regressions)
  - [ ] 13.3 Linter clean
  - [ ] 13.4 Documentation updated (cli-reference.md for audit command)
