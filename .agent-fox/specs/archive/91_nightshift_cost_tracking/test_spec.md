# Test Specification: Night-Shift Cost Tracking

## Overview

Tests verify that night-shift operations emit audit events to DuckDB so
costs appear in the status command. Test cases map to requirements and
correctness properties from the design document. Unit tests validate
individual components, property tests verify invariants across input
ranges, and integration smoke tests verify end-to-end wiring.

## Test Cases

### TS-91-1: NightShiftEngine accepts SinkDispatcher

**Requirement:** 91-REQ-1.1
**Type:** unit
**Description:** NightShiftEngine stores a provided SinkDispatcher.

**Preconditions:**
- A mock SinkDispatcher instance.

**Input:**
- `NightShiftEngine(config, platform, sink_dispatcher=mock_sink)`

**Expected:**
- `engine._sink` is the provided mock SinkDispatcher.

**Assertion pseudocode:**
```
mock_sink = MagicMock(spec=SinkDispatcher)
engine = NightShiftEngine(config, platform, sink_dispatcher=mock_sink)
ASSERT engine._sink is mock_sink
```

### TS-91-2: NightShiftEngine defaults to None sink

**Requirement:** 91-REQ-1.3
**Type:** unit
**Description:** NightShiftEngine works without a SinkDispatcher.

**Preconditions:**
- No SinkDispatcher provided.

**Input:**
- `NightShiftEngine(config, platform)`

**Expected:**
- `engine._sink` is None.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, platform)
ASSERT engine._sink is None
```

### TS-91-3: CLI creates SinkDispatcher with DuckDBSink

**Requirement:** 91-REQ-1.2
**Type:** unit
**Description:** The night_shift_cmd creates a SinkDispatcher backed by
DuckDBSink and passes it to NightShiftEngine.

**Preconditions:**
- Mock DuckDB connection available.
- Patch `open_knowledge_store` to return mock.

**Input:**
- Invoke `night_shift_cmd` via CliRunner.

**Expected:**
- NightShiftEngine is constructed with a non-None `sink_dispatcher`.

**Assertion pseudocode:**
```
# Patch NightShiftEngine.__init__ to capture kwargs
with patch("...NightShiftEngine") as MockEngine:
    runner.invoke(night_shift_cmd, [])
    call_kwargs = MockEngine.call_args.kwargs
    ASSERT "sink_dispatcher" in call_kwargs
    ASSERT call_kwargs["sink_dispatcher"] is not None
```

### TS-91-4: FixPipeline accepts SinkDispatcher

**Requirement:** 91-REQ-2.2
**Type:** unit
**Description:** FixPipeline stores a provided SinkDispatcher.

**Preconditions:**
- A mock SinkDispatcher instance.

**Input:**
- `FixPipeline(config, platform, sink_dispatcher=mock_sink)`

**Expected:**
- `pipeline._sink` is the mock SinkDispatcher.

**Assertion pseudocode:**
```
mock_sink = MagicMock(spec=SinkDispatcher)
pipeline = FixPipeline(config, platform, sink_dispatcher=mock_sink)
ASSERT pipeline._sink is mock_sink
```

### TS-91-5: process_issue generates unique run_id

**Requirement:** 91-REQ-2.1
**Type:** unit
**Description:** Each process_issue invocation generates a fresh run_id.

**Preconditions:**
- FixPipeline with mocked _run_session and platform.

**Input:**
- Call process_issue() twice with different issues.

**Expected:**
- Two distinct run_ids are generated (captured via patched generate_run_id).

**Assertion pseudocode:**
```
generated_ids = []
with patch("...generate_run_id", side_effect=lambda: (id := generate_run_id(), generated_ids.append(id), id)[-1]):
    await pipeline.process_issue(issue1, issue_body="fix bug")
    await pipeline.process_issue(issue2, issue_body="fix other bug")
ASSERT len(set(generated_ids)) == 2
```

### TS-91-6: _run_session passes sink and run_id to run_session

**Requirement:** 91-REQ-3.3
**Type:** unit
**Description:** FixPipeline._run_session passes sink_dispatcher and
run_id through to the underlying run_session call.

**Preconditions:**
- FixPipeline with a mock SinkDispatcher.
- run_session patched to capture kwargs.

**Input:**
- Call _run_session() with a valid spec and workspace.

**Expected:**
- run_session is called with `sink_dispatcher=mock_sink` and
  `run_id=<non-empty string>`.

**Assertion pseudocode:**
```
with patch("...run_session", new_callable=AsyncMock) as mock_rs:
    pipeline._run_id = "test-run-id"
    await pipeline._run_session("fix_coder", workspace, spec=spec)
    call_kwargs = mock_rs.call_args.kwargs
    ASSERT call_kwargs["sink_dispatcher"] is mock_sink
    ASSERT call_kwargs["run_id"] == "test-run-id"
```

### TS-91-7: session.complete emitted after successful fix session

**Requirement:** 91-REQ-3.1
**Type:** unit
**Description:** A session.complete event with cost payload is emitted
after a successful _run_session call.

**Preconditions:**
- FixPipeline with mock SinkDispatcher.
- _run_session returns a successful SessionOutcome with known token counts.

**Input:**
- Call _run_triage() or _coder_review_loop() triggering one session.

**Expected:**
- emit_audit_event called with SESSION_COMPLETE, payload contains
  `archetype`, `cost` (float > 0), `input_tokens`, `output_tokens`.

**Assertion pseudocode:**
```
with patch("...emit_audit_event") as mock_emit:
    await pipeline._run_triage(spec, workspace)
    call_args = mock_emit.call_args
    ASSERT call_args.args[2] == AuditEventType.SESSION_COMPLETE
    payload = call_args.kwargs["payload"]
    ASSERT payload["archetype"] == "triage"
    ASSERT payload["cost"] > 0
    ASSERT payload["input_tokens"] > 0
```

### TS-91-8: session.fail emitted after failed fix session

**Requirement:** 91-REQ-3.2
**Type:** unit
**Description:** A session.fail event is emitted when _run_session raises.

**Preconditions:**
- FixPipeline with mock SinkDispatcher.
- _run_session raises an exception.

**Input:**
- Call _run_triage() where the inner session raises.

**Expected:**
- emit_audit_event called with SESSION_FAIL and error_message in payload.

**Assertion pseudocode:**
```
with patch("...run_session", side_effect=RuntimeError("boom")):
    with patch("...emit_audit_event") as mock_emit:
        result = await pipeline._run_triage(spec, workspace)
        # _run_triage catches exceptions and returns empty TriageResult
        calls = [c for c in mock_emit.call_args_list if c.args[2] == AuditEventType.SESSION_FAIL]
        ASSERT len(calls) >= 1
        ASSERT "boom" in calls[0].kwargs["payload"]["error_message"]
```

### TS-91-9: emit_auxiliary_cost emits session.complete

**Requirement:** 91-REQ-4.1
**Type:** unit
**Description:** The cost helper emits a session.complete event with
correct archetype and cost.

**Preconditions:**
- Mock SinkDispatcher.
- Mock API response with usage.input_tokens=100, usage.output_tokens=50.

**Input:**
- `emit_auxiliary_cost(sink, run_id, "hunt_critic", response, model_id, pricing)`

**Expected:**
- emit_audit_event called with SESSION_COMPLETE, archetype="hunt_critic",
  cost > 0, input_tokens=100, output_tokens=50.

**Assertion pseudocode:**
```
with patch("...emit_audit_event") as mock_emit:
    emit_auxiliary_cost(mock_sink, "run-1", "hunt_critic", response, "claude-opus-4-6", pricing)
    payload = mock_emit.call_args.kwargs["payload"]
    ASSERT payload["archetype"] == "hunt_critic"
    ASSERT payload["input_tokens"] == 100
    ASSERT payload["output_tokens"] == 50
    ASSERT payload["cost"] > 0
```

### TS-91-10: emit_auxiliary_cost is no-op when sink is None

**Requirement:** 91-REQ-4.E1
**Type:** unit
**Description:** No error when sink is None.

**Preconditions:**
- sink_dispatcher is None.

**Input:**
- `emit_auxiliary_cost(None, "run-1", "hunt_critic", response, model_id, pricing)`

**Expected:**
- No exception raised. No audit event emitted.

**Assertion pseudocode:**
```
# Should not raise
emit_auxiliary_cost(None, "run-1", "hunt_critic", response, model_id, pricing)
```

### TS-91-11: nightshift/audit.py module removed

**Requirement:** 91-REQ-5.1
**Type:** unit
**Description:** The JSONL-based audit module no longer exists.

**Preconditions:**
- None.

**Input:**
- Check filesystem for `agent_fox/nightshift/audit.py`.

**Expected:**
- File does not exist.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/nightshift/audit.py").exists()
```

### TS-91-12: Engine uses standard emit_audit_event

**Requirement:** 91-REQ-5.2, 91-REQ-5.3
**Type:** unit
**Description:** NightShiftEngine calls the standard audit helper for
operational events, not the removed JSONL module.

**Preconditions:**
- NightShiftEngine source code.

**Input:**
- Inspect imports of engine.py.

**Expected:**
- No import from `agent_fox.nightshift.audit`.
- Import from `agent_fox.engine.audit_helpers`.

**Assertion pseudocode:**
```
source = Path("agent_fox/nightshift/engine.py").read_text()
ASSERT "from agent_fox.nightshift.audit" NOT IN source
ASSERT "from agent_fox.engine.audit_helpers" IN source
```

### TS-91-13: DaemonRunner uses standard emit_audit_event

**Requirement:** 91-REQ-5.3
**Type:** unit
**Description:** DaemonRunner calls the standard audit helper.

**Preconditions:**
- DaemonRunner source code.

**Input:**
- Inspect imports of daemon.py.

**Expected:**
- No import from `agent_fox.nightshift.audit`.

**Assertion pseudocode:**
```
source = Path("agent_fox/nightshift/daemon.py").read_text()
ASSERT "from agent_fox.nightshift.audit" NOT IN source
```

## Property Test Cases

### TS-91-P1: Cost calculation accuracy

**Property:** Property 2 from design.md
**Validates:** 91-REQ-3.1
**Type:** property
**Description:** The cost in emitted session.complete events matches the
output of calculate_cost() for any valid token counts.

**For any:** input_tokens in [0, 1_000_000], output_tokens in [0, 500_000],
cache_read_input_tokens in [0, 500_000], cache_creation_input_tokens in
[0, 500_000]

**Invariant:** `payload["cost"] == calculate_cost(input_tokens,
output_tokens, model_id, pricing, cache_read=..., cache_creation=...)`

**Assertion pseudocode:**
```
FOR ANY (in_tok, out_tok, cache_r, cache_c) IN st.integers(0, 1_000_000):
    expected = calculate_cost(in_tok, out_tok, model_id, pricing,
                              cache_read_input_tokens=cache_r,
                              cache_creation_input_tokens=cache_c)
    outcome = make_outcome(input_tokens=in_tok, output_tokens=out_tok,
                           cache_read=cache_r, cache_creation=cache_c)
    pipeline._emit_session_event(outcome, "fix_coder", run_id)
    payload = captured_event.payload
    ASSERT payload["cost"] == expected
```

### TS-91-P2: Graceful degradation with None sink

**Property:** Property 3 from design.md
**Validates:** 91-REQ-1.3, 91-REQ-2.E1, 91-REQ-4.E1
**Type:** property
**Description:** No exception is raised when sink is None, regardless of
input parameters.

**For any:** archetype in ["triage", "fix_coder", "fix_reviewer",
"hunt_critic", "batch_triage", "staleness_check", "quality_gate"],
run_id in arbitrary strings

**Invariant:** `emit_auxiliary_cost(None, run_id, archetype, ...)` completes
without raising.

**Assertion pseudocode:**
```
FOR ANY archetype IN st.sampled_from([...]), run_id IN st.text(min_size=0, max_size=50):
    emit_auxiliary_cost(None, run_id, archetype, mock_response, model_id, pricing)
    # No exception
```

### TS-91-P3: Run ID uniqueness

**Property:** Property 4 from design.md
**Validates:** 91-REQ-2.1
**Type:** property
**Description:** Multiple calls to generate_run_id produce unique values.

**For any:** n in [2, 100]

**Invariant:** `len(set(ids)) == n`

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(2, 100):
    ids = [generate_run_id() for _ in range(n)]
    ASSERT len(set(ids)) == n
```

## Edge Case Tests

### TS-91-E1: DuckDB unavailable at startup

**Requirement:** 91-REQ-1.E1
**Type:** unit
**Description:** Night-shift proceeds without audit when DuckDB cannot
be opened.

**Preconditions:**
- `open_knowledge_store` raises an exception.

**Input:**
- Invoke night_shift_cmd.

**Expected:**
- Warning is logged.
- NightShiftEngine is created with `sink_dispatcher=None`.
- No crash.

**Assertion pseudocode:**
```
with patch("...open_knowledge_store", side_effect=Exception("db locked")):
    with patch("...NightShiftEngine") as MockEngine:
        runner.invoke(night_shift_cmd, [])
        ASSERT MockEngine.call_args.kwargs.get("sink_dispatcher") is None
```

### TS-91-E2: Audit write failure during fix session

**Requirement:** 91-REQ-3.E1
**Type:** unit
**Description:** The fix pipeline continues when audit event write fails.

**Preconditions:**
- FixPipeline with a SinkDispatcher whose emit_audit_event raises.

**Input:**
- Run a fix session to completion.

**Expected:**
- Fix session returns FixMetrics normally.
- Warning logged about audit failure.

**Assertion pseudocode:**
```
mock_sink.emit_audit_event.side_effect = RuntimeError("write failed")
metrics = await pipeline.process_issue(issue, issue_body="fix it")
ASSERT metrics.sessions_run > 0  # pipeline completed despite audit failure
```

### TS-91-E3: Empty run_id skips emission

**Requirement:** 91-REQ-2.E1
**Type:** unit
**Description:** When run_id is empty, emit_audit_event returns without
error (existing guard).

**Preconditions:**
- SinkDispatcher is not None, run_id is "".

**Input:**
- `emit_audit_event(sink, "", SESSION_COMPLETE, payload={...})`

**Expected:**
- No event emitted. No exception.

**Assertion pseudocode:**
```
emit_audit_event(mock_sink, "", AuditEventType.SESSION_COMPLETE, payload={"cost": 1.0})
ASSERT mock_sink.emit_audit_event.call_count == 0
```

## Integration Smoke Tests

### TS-91-SMOKE-1: Fix session costs appear in status report

**Execution Path:** Path 1 from design.md
**Description:** A complete fix pipeline run emits session.complete events
that build_status_report_from_audit aggregates into costs.

**Setup:**
- Real in-memory DuckDB connection with schema initialized.
- DuckDBSink wrapping that connection.
- SinkDispatcher with the DuckDBSink.
- FixPipeline with mocked run_session (returns SessionOutcome with known tokens).
- Mock platform (add_issue_comment, close_issue, etc.).

**Trigger:**
- `await pipeline.process_issue(issue, issue_body="fix the bug")`

**Expected side effects:**
- DuckDB `audit_events` table contains `session.complete` rows.
- `build_status_report_from_audit(conn)` returns a report where
  `total_cost > 0` and `cost_by_archetype` contains keys for the
  fix session archetypes used.

**Must NOT satisfy with:**
- Mock of emit_audit_event (must use real emit path).
- Mock of DuckDBSink (must write to real in-memory DuckDB).

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
init_schema(conn)
sink = SinkDispatcher([DuckDBSink(conn)])
pipeline = FixPipeline(config, mock_platform, sink_dispatcher=sink)
# Patch run_session to return mock SessionOutcome
with patch("...run_session", return_value=mock_outcome):
    await pipeline.process_issue(issue, issue_body="fix bug")

report = build_status_report_from_audit(conn)
ASSERT report is not None
ASSERT report.total_cost > 0
ASSERT any(k in report.cost_by_archetype for k in ["triage", "fix_coder", "fix_reviewer"])
```

### TS-91-SMOKE-2: Auxiliary costs appear in status report

**Execution Path:** Path 2 from design.md
**Description:** Auxiliary AI calls emit session.complete events that the
status report aggregates.

**Setup:**
- Real in-memory DuckDB with schema.
- DuckDBSink + SinkDispatcher.
- Mock Anthropic API response with known token counts.

**Trigger:**
- `emit_auxiliary_cost(sink, run_id, "hunt_critic", response, model_id, pricing)`

**Expected side effects:**
- DuckDB `audit_events` table contains a `session.complete` row with
  archetype `hunt_critic`.
- `build_status_report_from_audit(conn)` includes `hunt_critic` in
  `cost_by_archetype`.

**Must NOT satisfy with:**
- Mock of emit_audit_event.
- Mock of DuckDBSink.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
init_schema(conn)
sink = SinkDispatcher([DuckDBSink(conn)])
emit_auxiliary_cost(sink, "run-1", "hunt_critic", mock_response, "claude-opus-4-6", pricing)

report = build_status_report_from_audit(conn)
ASSERT report.total_cost > 0
ASSERT "hunt_critic" in report.cost_by_archetype
```

### TS-91-SMOKE-3: No JSONL audit files written

**Execution Path:** Path 3 from design.md
**Description:** After the migration, night-shift operational events go to
DuckDB, not JSONL files.

**Setup:**
- Real in-memory DuckDB with schema.
- SinkDispatcher with DuckDBSink.
- Temporary directory as CWD (no `.agent-fox/audit/` exists).

**Trigger:**
- Create NightShiftEngine with SinkDispatcher.
- Call `_process_fix()` with a mocked pipeline.

**Expected side effects:**
- No files created under `.agent-fox/audit/`.
- DuckDB `audit_events` table contains `night_shift.fix_start` and
  `night_shift.fix_complete` events.

**Must NOT satisfy with:**
- Mock of emit_audit_event.

**Assertion pseudocode:**
```
audit_dir = tmp_path / ".agent-fox" / "audit"
ASSERT NOT audit_dir.exists()
# Verify DuckDB has the operational events
rows = conn.execute("SELECT event_type FROM audit_events WHERE event_type LIKE 'night_shift%'").fetchall()
ASSERT len(rows) >= 2
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 91-REQ-1.1 | TS-91-1 | unit |
| 91-REQ-1.2 | TS-91-3 | unit |
| 91-REQ-1.3 | TS-91-2 | unit |
| 91-REQ-1.E1 | TS-91-E1 | unit |
| 91-REQ-2.1 | TS-91-5 | unit |
| 91-REQ-2.2 | TS-91-4 | unit |
| 91-REQ-2.E1 | TS-91-E3 | unit |
| 91-REQ-3.1 | TS-91-7 | unit |
| 91-REQ-3.2 | TS-91-8 | unit |
| 91-REQ-3.3 | TS-91-6 | unit |
| 91-REQ-3.E1 | TS-91-E2 | unit |
| 91-REQ-4.1 | TS-91-9 | unit |
| 91-REQ-4.2 | TS-91-9 | unit |
| 91-REQ-4.3 | TS-91-9 | unit |
| 91-REQ-4.4 | TS-91-9 | unit |
| 91-REQ-4.E1 | TS-91-10 | unit |
| 91-REQ-5.1 | TS-91-11 | unit |
| 91-REQ-5.2 | TS-91-12 | unit |
| 91-REQ-5.3 | TS-91-13 | unit |
| 91-REQ-5.E1 | TS-91-E3 | unit |
| 91-REQ-6.1 | TS-91-SMOKE-1 | integration |
| 91-REQ-6.2 | TS-91-SMOKE-1 | integration |
| 91-REQ-6.3 | TS-91-SMOKE-2 | integration |
| Property 1 | — | (verified by TS-91-SMOKE-1 count check) |
| Property 2 | TS-91-P1 | property |
| Property 3 | TS-91-P2 | property |
| Property 4 | TS-91-P3 | property |
| Property 5 | TS-91-9 | unit |
| Property 6 | TS-91-SMOKE-3 | integration |
| Property 7 | TS-91-SMOKE-1 | integration |
