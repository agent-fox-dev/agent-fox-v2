# Implementation Plan: Structured Audit Log

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in ten groups: (1) write failing tests, (2) data model
and enums, (3) DuckDB migration, (4) sink protocol and implementations,
(5) session lifecycle events, (6) orchestrator and routing events,
(7) retention logic, (8) CLI command, (9) reporting migration,
(10) final checkpoint.

The ordering ensures the data model is built first, then persistence, then
event emission wiring, then consumer-facing features (retention, CLI,
reporting).

## Dependencies

| Spec | Relationship | Justification |
|------|-------------|---------------|
| 39 (package consolidation) | Blocks | All imports use `agent_fox.knowledge.*` paths |
| 34 (token tracking) | Uses | Token accumulator used for cost fields in session events |
| 27 (structured review records) | Uses | Review store CRUD imported for harvest events |
| 38 (DuckDB hardening) | Uses | DuckDB error handling patterns for sink operations |
| 11 (DuckDB knowledge store) | Extends | SessionSink protocol and SinkDispatcher extended |

## Test Commands

- Spec tests: `uv run pytest tests/unit/knowledge/test_audit.py tests/unit/knowledge/test_audit_sink.py tests/unit/cli/test_audit_cli.py -v`
- Property tests: `uv run pytest tests/property/knowledge/test_audit_props.py -v`
- Integration tests: `uv run pytest tests/integration/test_audit_events.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create `tests/unit/knowledge/test_audit.py`
    - Test class `TestAuditEventModel` with TS-40-1, TS-40-4, TS-40-E1
    - Test class `TestAuditEventTypeEnum` with TS-40-2
    - Test class `TestAuditSeverityEnum` with TS-40-3
    - Test class `TestRunIdGeneration` with TS-40-5, TS-40-6
    - _Test Spec: TS-40-1, TS-40-2, TS-40-3, TS-40-4, TS-40-5, TS-40-6, TS-40-E1_

  - [ ] 1.2 Create `tests/unit/knowledge/test_audit_sink.py`
    - Test class `TestSessionSinkProtocol` with TS-40-9
    - Test class `TestSinkDispatcherAudit` with TS-40-10, TS-40-11
    - Test class `TestDuckDBSinkAudit` with TS-40-12
    - Test class `TestAuditJsonlSink` with TS-40-13, TS-40-14, TS-40-15, TS-40-16
    - Test class `TestMigration` with TS-40-7, TS-40-8
    - _Test Spec: TS-40-7 through TS-40-16_

  - [ ] 1.3 Create `tests/unit/knowledge/test_audit_retention.py`
    - Test class `TestRetention` with TS-40-24, TS-40-25, TS-40-E2
    - _Test Spec: TS-40-24, TS-40-25, TS-40-E2_

  - [ ] 1.4 Create `tests/unit/cli/test_audit_cli.py`
    - Test class `TestAuditCLI` with TS-40-26 through TS-40-32
    - _Test Spec: TS-40-26 through TS-40-32_

  - [ ] 1.5 Create `tests/integration/test_audit_events.py`
    - Test class `TestSessionEvents` with TS-40-17, TS-40-18, TS-40-19
    - Test class `TestToolEvents` with TS-40-20
    - Test class `TestOrchestratorEvents` with TS-40-21, TS-40-22, TS-40-23
    - Test class `TestReportingMigration` with TS-40-33, TS-40-34
    - _Test Spec: TS-40-17 through TS-40-23, TS-40-33, TS-40-34_

  - [ ] 1.6 Create `tests/property/knowledge/test_audit_props.py`
    - Property tests TS-40-P1 through TS-40-P6
    - _Test Spec: TS-40-P1 through TS-40-P6_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings: `uv run ruff check tests/unit/knowledge/test_audit.py tests/unit/knowledge/test_audit_sink.py tests/unit/knowledge/test_audit_retention.py tests/unit/cli/test_audit_cli.py tests/integration/test_audit_events.py tests/property/knowledge/test_audit_props.py`
    - [ ] All existing tests still pass (no regressions)

- [ ] 2. Data model and enums
  - [ ] 2.1 Create `agent_fox/knowledge/audit.py`
    - `AuditSeverity` StrEnum with 4 values: `info`, `warning`, `error`, `critical`
    - `AuditEventType` StrEnum with 19 variants matching the event type table
    - `AuditEvent` frozen dataclass with fields: `run_id`, `event_type`,
      `severity` (default INFO), `node_id` (default ""), `session_id`
      (default ""), `archetype` (default ""), `payload` (default {}),
      `id` (default uuid4), `timestamp` (default UTC now)
    - `generate_run_id()` function returning `{YYYYMMDD}_{HHMMSS}_{short_hex}`
    - `default_severity_for(event_type)` helper mapping event types to default
      severities (session.fail -> error, run.limit_reached/git.conflict -> warning,
      all others -> info)
    - `event_to_json(event)` and `event_from_json(json_str)` for serialization
    - _Requirements: 40-REQ-1.1, 40-REQ-1.2, 40-REQ-1.3, 40-REQ-1.4, 40-REQ-1.E1,
      40-REQ-2.1, 40-REQ-2.E1_

  - [ ] 2.2 Export new types from `agent_fox/knowledge/__init__.py`
    - Export `AuditEvent`, `AuditEventType`, `AuditSeverity`, `generate_run_id`
    - _Requirements: module accessibility_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_audit.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_audit_props.py::TestRunIdFormat tests/property/knowledge/test_audit_props.py::TestEventSerializationRoundTrip tests/property/knowledge/test_audit_props.py::TestSeverityClassification -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/audit.py`
    - [ ] Requirements 40-REQ-1.*, 40-REQ-2.* met

- [ ] 3. DuckDB migration
  - [ ] 3.1 Add `_migrate_v6()` to `agent_fox/knowledge/migrations.py`
    - Create `audit_events` table with columns: `id` (VARCHAR PRIMARY KEY),
      `timestamp` (TIMESTAMP NOT NULL), `run_id` (VARCHAR NOT NULL),
      `event_type` (VARCHAR NOT NULL), `node_id` (VARCHAR), `session_id`
      (VARCHAR), `archetype` (VARCHAR), `severity` (VARCHAR NOT NULL),
      `payload` (JSON NOT NULL)
    - Create indexes: `idx_audit_run_id` on `run_id`, `idx_audit_event_type`
      on `event_type`
    - Register in `MIGRATIONS` list with `version=6`
    - _Requirements: 40-REQ-3.1, 40-REQ-3.2, 40-REQ-3.3_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_audit_sink.py::TestMigration -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/migrations.py`
    - [ ] Requirements 40-REQ-3.* met

- [ ] 4. Sink protocol extension and implementations
  - [ ] 4.1 Add `emit_audit_event()` to `SessionSink` protocol in
    `agent_fox/knowledge/sink.py`
    - Add method: `def emit_audit_event(self, event: AuditEvent) -> None: ...`
    - Import `AuditEvent` from `agent_fox.knowledge.audit`
    - _Requirements: 40-REQ-4.1_

  - [ ] 4.2 Add `emit_audit_event()` to `SinkDispatcher`
    - Dispatch to all sinks via `_dispatch("emit_audit_event", event)`
    - _Requirements: 40-REQ-4.2, 40-REQ-4.E1_

  - [ ] 4.3 Add `emit_audit_event()` to `DuckDBSink` in
    `agent_fox/knowledge/duckdb_sink.py`
    - INSERT into `audit_events` table with JSON-serialized payload
    - _Requirements: 40-REQ-5.1, 40-REQ-5.2_

  - [ ] 4.4 Create `AuditJsonlSink` class in `agent_fox/knowledge/audit.py`
    - Constructor takes `audit_dir: Path` and `run_id: str`
    - Creates directory on init
    - `emit_audit_event()` appends JSON line with all fields
    - Other SessionSink methods are no-ops
    - Handles OSError on write gracefully (log warning)
    - _Requirements: 40-REQ-6.1, 40-REQ-6.2, 40-REQ-6.3, 40-REQ-6.4, 40-REQ-6.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_audit_sink.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_audit_props.py::TestDualWriteConsistency -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/sink.py agent_fox/knowledge/duckdb_sink.py agent_fox/knowledge/audit.py`
    - [ ] Requirements 40-REQ-4.*, 40-REQ-5.*, 40-REQ-6.* met

- [ ] 5. Session lifecycle and tool events
  - [ ] 5.1 Wire `session.start` event in `agent_fox/engine/session_lifecycle.py`
    - Emit before SDK call with payload: `archetype`, `model_id`,
      `prompt_template`, `attempt`
    - _Requirements: 40-REQ-7.1_

  - [ ] 5.2 Wire `session.complete` event in `agent_fox/engine/session_lifecycle.py`
    - Emit after successful SDK result with payload: `archetype`, `model_id`,
      `prompt_template`, `tokens`, `cost`, `duration_ms`, `files_touched`
    - _Requirements: 40-REQ-7.2_

  - [ ] 5.3 Wire `session.fail` event in `agent_fox/engine/session_lifecycle.py`
    - Emit with severity `error` and payload: `archetype`, `model_id`,
      `prompt_template`, `error_message`, `attempt`
    - _Requirements: 40-REQ-7.3_

  - [ ] 5.4 Wire `harvest.complete` event in `agent_fox/engine/session_lifecycle.py`
    - Emit after post-session harvest with payload: `commit_sha`,
      `facts_extracted`, `findings_persisted`
    - _Requirements: 40-REQ-11.3_

  - [ ] 5.5 Wire `tool.invocation` and `tool.error` events in
    `agent_fox/session/session.py`
    - Use `abbreviate_arg` for `param_summary`
    - _Requirements: 40-REQ-8.1, 40-REQ-8.2, 40-REQ-8.3_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest tests/integration/test_audit_events.py::TestSessionEvents tests/integration/test_audit_events.py::TestToolEvents -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/engine/session_lifecycle.py agent_fox/session/session.py`
    - [ ] Requirements 40-REQ-7.*, 40-REQ-8.*, 40-REQ-11.3 met

- [ ] 6. Orchestrator, routing, harvest, and knowledge events
  - [ ] 6.1 Generate run ID and wire `run.start` / `run.complete` in
    `agent_fox/engine/engine.py`
    - Call `generate_run_id()` at start of `execute()`
    - Propagate run ID to sink dispatcher and session runners
    - Emit `run.start` with `plan_hash`, `total_nodes`, `parallel`
    - Emit `run.complete` with `total_sessions`, `total_cost`, `duration_ms`,
      `run_status`
    - Register `AuditJsonlSink` in the sink dispatcher at engine start
    - _Requirements: 40-REQ-2.1, 40-REQ-2.2, 40-REQ-9.1, 40-REQ-9.2_

  - [ ] 6.2 Wire `run.limit_reached` in `agent_fox/engine/engine.py`
    - Emit with severity `warning` and payload: `limit_type`, `limit_value`
    - _Requirements: 40-REQ-9.3_

  - [ ] 6.3 Wire `session.retry` and `task.status_change` in
    `agent_fox/engine/engine.py`
    - `session.retry` with `attempt`, `reason`
    - `task.status_change` with `from_status`, `to_status`, `reason`
    - _Requirements: 40-REQ-7.4, 40-REQ-9.4_

  - [ ] 6.4 Wire `sync.barrier` in `agent_fox/engine/engine.py`
    - Emit with `completed_nodes`, `pending_nodes`
    - _Requirements: 40-REQ-9.5_

  - [ ] 6.5 Wire `model.escalation` and `model.assessment` in
    `agent_fox/routing/router.py`
    - `model.escalation` with `from_tier`, `to_tier`, `reason`
    - `model.assessment` with `predicted_tier`, `confidence`, `method`
    - _Requirements: 40-REQ-10.1, 40-REQ-10.2_

  - [ ] 6.6 Wire `git.merge` and `git.conflict` in
    `agent_fox/engine/knowledge_harvest.py`
    - `git.merge` with `branch`, `commit_sha`, `files_touched`
    - `git.conflict` with severity `warning` and `branch`, `strategy`, `error`
    - _Requirements: 40-REQ-11.1, 40-REQ-11.2_

  - [ ] 6.7 Wire `fact.extracted` in `agent_fox/engine/knowledge_harvest.py`
    - Emit with `fact_count`, `categories`
    - _Requirements: 40-REQ-11.4_

  - [ ] 6.8 Wire `fact.compacted` in `agent_fox/knowledge/compaction.py`
    - Emit with `facts_before`, `facts_after`, `superseded_count`
    - _Requirements: 40-REQ-11.5_

  - [ ] 6.9 Wire `knowledge.ingested` in `agent_fox/knowledge/ingest.py`
    - Emit with `source_type`, `source_path`, `item_count`
    - _Requirements: 40-REQ-11.6_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests pass: `uv run pytest tests/integration/test_audit_events.py::TestOrchestratorEvents -v`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_audit_props.py::TestEventCompleteness -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/engine/engine.py agent_fox/routing/router.py agent_fox/engine/knowledge_harvest.py agent_fox/knowledge/compaction.py agent_fox/knowledge/ingest.py`
    - [ ] Requirements 40-REQ-2.*, 40-REQ-9.*, 40-REQ-10.*, 40-REQ-11.* met

- [ ] 7. Log retention
  - [ ] 7.1 Add `audit_retention_runs` config setting
    - Add field to the appropriate config model (default: 20)
    - _Requirements: 40-REQ-12.1_

  - [ ] 7.2 Implement `enforce_audit_retention()` in `agent_fox/knowledge/audit.py`
    - Query distinct `run_id` from `audit_events` ordered by `MIN(timestamp)`
    - Delete oldest runs beyond the retention limit from DuckDB
    - Delete corresponding JSONL files from `.agent-fox/audit/`
    - Handle JSONL deletion failure gracefully (log warning)
    - _Requirements: 40-REQ-12.1, 40-REQ-12.2, 40-REQ-12.E1, 40-REQ-12.E2_

  - [ ] 7.3 Call `enforce_audit_retention()` at orchestrator start
    - Wire into `engine.py` `execute()` after run ID generation
    - _Requirements: 40-REQ-12.2_

  - [ ] 7.V Verify task group 7
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_audit_retention.py -v`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_audit_props.py::TestRetentionBound -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/audit.py agent_fox/engine/engine.py`
    - [ ] Requirements 40-REQ-12.* met

- [ ] 8. CLI command
  - [ ] 8.1 Create `agent_fox/cli/audit.py`
    - `audit_cmd` Click command with options: `--list-runs`, `--run`,
      `--event-type`, `--node-id`, `--since`
    - `--list-runs` queries distinct run_ids with counts
    - `--since` supports ISO-8601 and relative durations (`24h`, `7d`)
    - Supports global `--json` flag for structured output
    - Handles missing DuckDB gracefully
    - _Requirements: 40-REQ-13.1 through 40-REQ-13.7, 40-REQ-13.E1,
      40-REQ-13.E2_

  - [ ] 8.2 Register `audit_cmd` in `agent_fox/cli/app.py`
    - Add to the main CLI group
    - _Requirements: 40-REQ-13.1_

  - [ ] 8.V Verify task group 8
    - [ ] Spec tests pass: `uv run pytest tests/unit/cli/test_audit_cli.py -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/cli/audit.py agent_fox/cli/app.py`
    - [ ] Requirements 40-REQ-13.* met

- [ ] 9. Reporting migration
  - [ ] 9.1 Add `build_status_report_from_audit()` to
    `agent_fox/reporting/status.py`
    - Query `session.complete` and `session.fail` events from `audit_events`
    - Compute total sessions, tokens, costs, per-archetype, per-spec breakdowns
    - _Requirements: 40-REQ-14.1_

  - [ ] 9.2 Update `agent_fox/reporting/status.py` to prefer DuckDB
    - Try DuckDB first, fall back to state.jsonl if unavailable
    - _Requirements: 40-REQ-14.1, 40-REQ-14.3_

  - [ ] 9.3 Update `agent_fox/reporting/standup.py` to read from DuckDB
    - Query recent audit events for standup report generation
    - Fall back to existing JSONL parsing if DuckDB unavailable
    - _Requirements: 40-REQ-14.2, 40-REQ-14.3_

  - [ ] 9.V Verify task group 9
    - [ ] Spec tests pass: `uv run pytest tests/integration/test_audit_events.py::TestReportingMigration -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/reporting/status.py agent_fox/reporting/standup.py`
    - [ ] Requirements 40-REQ-14.* met

- [ ] 10. Final checkpoint
  - [ ] 10.1 Update documentation
    - Update `docs/cli-reference.md` for `agent-fox audit` command
    - Document `audit_retention_runs` config setting
    - _Requirements: documentation_

  - [ ] 10.V Verify task group 10
    - [ ] All spec tests pass: `uv run pytest tests/unit/knowledge/test_audit.py tests/unit/knowledge/test_audit_sink.py tests/unit/knowledge/test_audit_retention.py tests/unit/cli/test_audit_cli.py tests/integration/test_audit_events.py tests/property/knowledge/test_audit_props.py -v`
    - [ ] Full test suite passes: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [ ] All 40-REQ-* acceptance criteria met
    - [ ] `make check` passes

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 40-REQ-1.1 | TS-40-1 | 2.1 | `test_audit.py::TestAuditEventModel::test_fields` |
| 40-REQ-1.2 | TS-40-2 | 2.1 | `test_audit.py::TestAuditEventTypeEnum::test_completeness` |
| 40-REQ-1.3 | TS-40-3 | 2.1 | `test_audit.py::TestAuditSeverityEnum::test_values` |
| 40-REQ-1.4 | TS-40-4 | 2.1 | `test_audit.py::TestAuditEventModel::test_auto_populate` |
| 40-REQ-1.E1 | TS-40-E1 | 2.1 | `test_audit.py::TestAuditEventModel::test_empty_optionals` |
| 40-REQ-2.1 | TS-40-5 | 2.1 | `test_audit.py::TestRunIdGeneration::test_format` |
| 40-REQ-2.E1 | TS-40-6 | 2.1 | `test_audit.py::TestRunIdGeneration::test_uniqueness` |
| 40-REQ-2.2 | TS-40-21 | 6.1 | `test_audit_events.py::TestOrchestratorEvents::test_run_start` |
| 40-REQ-3.1 | TS-40-7 | 3.1 | `test_audit_sink.py::TestMigration::test_creates_table` |
| 40-REQ-3.2 | TS-40-7 | 3.1 | `test_audit_sink.py::TestMigration::test_creates_indexes` |
| 40-REQ-3.3 | TS-40-8 | 3.1 | `test_audit_sink.py::TestMigration::test_registered` |
| 40-REQ-4.1 | TS-40-9 | 4.1 | `test_audit_sink.py::TestSessionSinkProtocol::test_has_method` |
| 40-REQ-4.2 | TS-40-10 | 4.2 | `test_audit_sink.py::TestSinkDispatcherAudit::test_dispatches` |
| 40-REQ-4.E1 | TS-40-11 | 4.2 | `test_audit_sink.py::TestSinkDispatcherAudit::test_swallows_failures` |
| 40-REQ-5.1 | TS-40-12 | 4.3 | `test_audit_sink.py::TestDuckDBSinkAudit::test_inserts` |
| 40-REQ-5.2 | TS-40-12 | 4.3 | `test_audit_sink.py::TestDuckDBSinkAudit::test_json_payload` |
| 40-REQ-6.1 | TS-40-14 | 4.4 | `test_audit_sink.py::TestAuditJsonlSink::test_writes_lines` |
| 40-REQ-6.2 | TS-40-13 | 4.4 | `test_audit_sink.py::TestAuditJsonlSink::test_creates_dir` |
| 40-REQ-6.3 | TS-40-14 | 4.4 | `test_audit_sink.py::TestAuditJsonlSink::test_json_format` |
| 40-REQ-6.4 | TS-40-15 | 4.4 | `test_audit_sink.py::TestAuditJsonlSink::test_noop_methods` |
| 40-REQ-6.E1 | TS-40-16 | 4.4 | `test_audit_sink.py::TestAuditJsonlSink::test_write_failure` |
| 40-REQ-7.1 | TS-40-17 | 5.1 | `test_audit_events.py::TestSessionEvents::test_session_start` |
| 40-REQ-7.2 | TS-40-18 | 5.2 | `test_audit_events.py::TestSessionEvents::test_session_complete` |
| 40-REQ-7.3 | TS-40-19 | 5.3 | `test_audit_events.py::TestSessionEvents::test_session_fail` |
| 40-REQ-7.4 | TS-40-17 | 6.3 | `test_audit_events.py::TestOrchestratorEvents::test_session_retry` |
| 40-REQ-8.1 | TS-40-20 | 5.5 | `test_audit_events.py::TestToolEvents::test_tool_invocation` |
| 40-REQ-8.2 | TS-40-20 | 5.5 | `test_audit_events.py::TestToolEvents::test_abbreviated_params` |
| 40-REQ-8.3 | TS-40-20 | 5.5 | `test_audit_events.py::TestToolEvents::test_tool_error` |
| 40-REQ-9.1 | TS-40-21 | 6.1 | `test_audit_events.py::TestOrchestratorEvents::test_run_start` |
| 40-REQ-9.2 | TS-40-22 | 6.1 | `test_audit_events.py::TestOrchestratorEvents::test_run_complete` |
| 40-REQ-9.3 | TS-40-23 | 6.2 | `test_audit_events.py::TestOrchestratorEvents::test_limit_reached` |
| 40-REQ-9.4 | TS-40-21 | 6.3 | `test_audit_events.py::TestOrchestratorEvents::test_task_status_change` |
| 40-REQ-9.5 | TS-40-21 | 6.4 | `test_audit_events.py::TestOrchestratorEvents::test_sync_barrier` |
| 40-REQ-10.1 | TS-40-21 | 6.5 | `test_audit_events.py::TestOrchestratorEvents::test_model_escalation` |
| 40-REQ-10.2 | TS-40-21 | 6.5 | `test_audit_events.py::TestOrchestratorEvents::test_model_assessment` |
| 40-REQ-11.1 | TS-40-21 | 6.6 | `test_audit_events.py::TestOrchestratorEvents::test_git_merge` |
| 40-REQ-11.2 | TS-40-21 | 6.6 | `test_audit_events.py::TestOrchestratorEvents::test_git_conflict` |
| 40-REQ-11.3 | TS-40-21 | 5.4 | `test_audit_events.py::TestSessionEvents::test_harvest_complete` |
| 40-REQ-11.4 | TS-40-21 | 6.7 | `test_audit_events.py::TestOrchestratorEvents::test_fact_extracted` |
| 40-REQ-11.5 | TS-40-21 | 6.8 | `test_audit_events.py::TestOrchestratorEvents::test_fact_compacted` |
| 40-REQ-11.6 | TS-40-21 | 6.9 | `test_audit_events.py::TestOrchestratorEvents::test_knowledge_ingested` |
| 40-REQ-12.1 | TS-40-24 | 7.1, 7.2 | `test_audit_retention.py::TestRetention::test_deletes_old` |
| 40-REQ-12.2 | TS-40-24 | 7.2, 7.3 | `test_audit_retention.py::TestRetention::test_deletes_old` |
| 40-REQ-12.E1 | TS-40-25 | 7.2 | `test_audit_retention.py::TestRetention::test_under_limit` |
| 40-REQ-12.E2 | TS-40-E2 | 7.2 | `test_audit_retention.py::TestRetention::test_jsonl_delete_failure` |
| 40-REQ-13.1 | TS-40-26 | 8.1, 8.2 | `test_audit_cli.py::TestAuditCLI::test_list_runs` |
| 40-REQ-13.2 | TS-40-26 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_list_runs` |
| 40-REQ-13.3 | TS-40-27 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_filter_by_run` |
| 40-REQ-13.4 | TS-40-28 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_filter_by_event_type` |
| 40-REQ-13.5 | TS-40-27 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_filter_by_node` |
| 40-REQ-13.6 | TS-40-29 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_filter_by_since` |
| 40-REQ-13.7 | TS-40-30 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_json_output` |
| 40-REQ-13.E1 | TS-40-31 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_no_events` |
| 40-REQ-13.E2 | TS-40-32 | 8.1 | `test_audit_cli.py::TestAuditCLI::test_missing_db` |
| 40-REQ-14.1 | TS-40-33 | 9.1, 9.2 | `test_audit_events.py::TestReportingMigration::test_status_from_audit` |
| 40-REQ-14.2 | TS-40-33 | 9.3 | `test_audit_events.py::TestReportingMigration::test_standup_from_audit` |
| 40-REQ-14.3 | TS-40-34 | 9.2, 9.3 | `test_audit_events.py::TestReportingMigration::test_fallback` |
| Property 1 | TS-40-P6 | 6.1 | `test_audit_props.py::TestEventCompleteness` |
| Property 2 | TS-40-P1 | 2.1 | `test_audit_props.py::TestRunIdFormat` |
| Property 3 | TS-40-P4 | 4.2, 4.3, 4.4 | `test_audit_props.py::TestDualWriteConsistency` |
| Property 4 | TS-40-P2 | 2.1 | `test_audit_props.py::TestEventSerializationRoundTrip` |
| Property 5 | TS-40-P5 | 7.2 | `test_audit_props.py::TestRetentionBound` |
| Property 6 | TS-40-P3 | 2.1 | `test_audit_props.py::TestSeverityClassification` |

## Notes

- The `SinkDispatcher` uses `_dispatch()` which calls `getattr(sink, method)`.
  If a sink does not implement `emit_audit_event`, the `AttributeError` is
  caught and logged as a warning. No code changes are needed in `_dispatch()`
  itself for this behavior.
- The `AuditJsonlSink` opens and closes the file on every write. This is
  intentional for simplicity and crash safety. Performance is acceptable
  because audit events are infrequent (tens per session, not thousands).
- Run ID generation uses UTC to avoid timezone ambiguity in the date/time
  portion.
- The event type count in the requirements says "20 variants" but the actual
  enum has 19 members. The discrepancy is because the original combined spec
  counted differently. The 19 listed types cover all required events.
- When wiring events into `engine.py`, the `run_id` must be passed through
  the session runner so that session-level events can reference it.
- Retention enforcement runs at orchestrator start (before `run.start` is
  emitted) to avoid counting the current run in the retention check.
