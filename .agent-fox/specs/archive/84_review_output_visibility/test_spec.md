# Test Specification: Review Archetype Output Visibility

## Overview

Tests are organized by feature area: JSONL response logging (TS-84-1, 2),
audit event emission (TS-84-3 through 5), enriched blocking reasons
(TS-84-6, 7), CLI findings command (TS-84-8 through 13), and status
findings summary (TS-84-14, 15). Edge cases cover truncation, missing DB,
empty results, and audit emission failure. Property tests validate
invariants across generated inputs.

## Test Cases

### TS-84-1: JSONL sink writes response field

**Requirement:** 84-REQ-1.1
**Type:** unit
**Description:** Verify that `record_session_outcome()` includes the
`response` field in the JSONL record.

**Preconditions:**
- A `JsonlSink` instance writing to a temporary file.

**Input:**
- `SessionOutcome(response="{ \"findings\": [{\"severity\": \"critical\"}] }", status="completed", node_id="spec:0")`

**Expected:**
- The JSONL record contains a `"response"` key with the exact input value.

**Assertion pseudocode:**
```
sink = JsonlSink(tmp_path)
outcome = SessionOutcome(response='{"findings": []}', node_id="s:0")
sink.record_session_outcome(outcome)
record = read_last_jsonl_line(tmp_path)
ASSERT "response" in record
ASSERT record["response"] == outcome.response
```

### TS-84-2: JSONL sink writes empty response as empty string

**Requirement:** 84-REQ-1.2
**Type:** unit
**Description:** Verify that an empty response is written as `""`, not
omitted.

**Preconditions:**
- A `JsonlSink` instance writing to a temporary file.

**Input:**
- `SessionOutcome(response="", node_id="spec:0")`

**Expected:**
- The JSONL record contains `"response": ""`.

**Assertion pseudocode:**
```
sink = JsonlSink(tmp_path)
outcome = SessionOutcome(response="", node_id="s:0")
sink.record_session_outcome(outcome)
record = read_last_jsonl_line(tmp_path)
ASSERT record["response"] == ""
```

### TS-84-3: Findings persisted audit event emitted for skeptic

**Requirement:** 84-REQ-2.1
**Type:** unit
**Description:** Verify `review.findings_persisted` event is emitted
after successful skeptic finding insertion.

**Preconditions:**
- In-memory DuckDB with review tables created.
- A mock `SinkDispatcher` capturing emitted events.

**Input:**
- Call `persist_review_findings()` with a transcript containing valid
  skeptic JSON: `[{"severity": "critical", "description": "missing guard"}]`.

**Expected:**
- `SinkDispatcher.emit_audit_event` called with event type
  `review.findings_persisted`.
- Payload contains `archetype="skeptic"`, `count=1`,
  `severity_summary={"critical": 1}`.

**Assertion pseudocode:**
```
persist_review_findings(transcript, ..., archetype="skeptic", sink=mock_sink)
event = mock_sink.last_audit_event
ASSERT event.event_type == AuditEventType.REVIEW_FINDINGS_PERSISTED
ASSERT event.payload["count"] == 1
ASSERT event.payload["severity_summary"]["critical"] == 1
```

### TS-84-4: Verdicts persisted audit event emitted for verifier

**Requirement:** 84-REQ-2.2
**Type:** unit
**Description:** Verify `review.verdicts_persisted` event is emitted
after successful verifier verdict insertion.

**Preconditions:**
- In-memory DuckDB with review tables created.
- A mock `SinkDispatcher`.

**Input:**
- Call `persist_review_findings()` with a transcript containing valid
  verifier JSON: `[{"requirement_id": "REQ-1.1", "verdict": "PASS"}, {"requirement_id": "REQ-1.2", "verdict": "FAIL"}]`.

**Expected:**
- Event type `review.verdicts_persisted`.
- Payload contains `count=2`, `pass_count=1`, `fail_count=1`.

**Assertion pseudocode:**
```
persist_review_findings(transcript, ..., archetype="verifier", sink=mock_sink)
event = mock_sink.last_audit_event
ASSERT event.event_type == AuditEventType.REVIEW_VERDICTS_PERSISTED
ASSERT event.payload["pass_count"] == 1
ASSERT event.payload["fail_count"] == 1
```

### TS-84-5: Drift persisted audit event emitted for oracle

**Requirement:** 84-REQ-2.3
**Type:** unit
**Description:** Verify `review.drift_persisted` event is emitted after
successful oracle drift finding insertion.

**Preconditions:**
- In-memory DuckDB with review tables created.
- A mock `SinkDispatcher`.

**Input:**
- Call `persist_review_findings()` with valid oracle JSON:
  `[{"severity": "major", "description": "spec divergence"}]`.

**Expected:**
- Event type `review.drift_persisted`.
- Payload contains `count=1`, `severity_summary={"major": 1}`.

**Assertion pseudocode:**
```
persist_review_findings(transcript, ..., archetype="oracle", sink=mock_sink)
event = mock_sink.last_audit_event
ASSERT event.event_type == AuditEventType.REVIEW_DRIFT_PERSISTED
ASSERT event.payload["count"] == 1
```

### TS-84-6: Enriched blocking reason includes finding IDs

**Requirement:** 84-REQ-3.1
**Type:** unit
**Description:** Verify that when a skeptic blocks a task, the blocking
reason includes finding IDs and truncated descriptions.

**Preconditions:**
- In-memory DuckDB with 2 critical findings inserted for a session.

**Input:**
- Call `evaluate_review_blocking()` with a skeptic session record and
  threshold=0.

**Expected:**
- `BlockDecision.reason` contains both finding IDs (8-char hex prefix).
- Reason contains truncated descriptions.
- Reason contains "2 critical finding(s)".

**Assertion pseudocode:**
```
decision = evaluate_review_blocking(record, config, conn)
ASSERT decision.should_block is True
ASSERT "2 critical" in decision.reason
ASSERT "F-" in decision.reason  # at least one finding ID
ASSERT len(decision.reason) < 500  # reasonably sized
```

### TS-84-7: Blocking reason caps at 3 finding IDs

**Requirement:** 84-REQ-3.E1
**Type:** unit
**Description:** Verify that when more than 3 critical findings exist,
only the first 3 IDs are shown with "and N more".

**Preconditions:**
- In-memory DuckDB with 5 critical findings inserted for a session.

**Input:**
- Call `evaluate_review_blocking()` with threshold=0.

**Expected:**
- Reason contains exactly 3 `F-` prefixed IDs.
- Reason contains "and 2 more".

**Assertion pseudocode:**
```
decision = evaluate_review_blocking(record, config, conn)
ASSERT decision.reason.count("F-") == 3
ASSERT "and 2 more" in decision.reason
```

### TS-84-8: Findings command displays table

**Requirement:** 84-REQ-4.1
**Type:** unit
**Description:** Verify `query_findings()` returns active findings and
`format_findings_table()` produces a readable table.

**Preconditions:**
- In-memory DuckDB with 3 findings (2 active, 1 superseded).

**Input:**
- `query_findings(conn, active_only=True)`

**Expected:**
- Returns 2 findings.
- `format_findings_table()` output contains severity, archetype, spec
  name, and description for each.

**Assertion pseudocode:**
```
rows = query_findings(conn, active_only=True)
ASSERT len(rows) == 2
table = format_findings_table(rows)
ASSERT "critical" in table
ASSERT "skeptic" in table
```

### TS-84-9: Findings command filters by spec

**Requirement:** 84-REQ-4.2
**Type:** unit
**Description:** Verify `--spec` filter narrows results to matching spec.

**Preconditions:**
- DuckDB with findings from specs "foo" and "bar".

**Input:**
- `query_findings(conn, spec="foo")`

**Expected:**
- Only findings from spec "foo" returned.

**Assertion pseudocode:**
```
rows = query_findings(conn, spec="foo")
ASSERT all(r.spec_name == "foo" for r in rows)
```

### TS-84-10: Findings command filters by severity

**Requirement:** 84-REQ-4.3
**Type:** unit
**Description:** Verify `--severity` filter returns findings at or above
the given level.

**Preconditions:**
- DuckDB with findings at critical, major, minor, observation severities.

**Input:**
- `query_findings(conn, severity="major")`

**Expected:**
- Only critical and major findings returned (not minor or observation).

**Assertion pseudocode:**
```
rows = query_findings(conn, severity="major")
ASSERT all(r.severity in ("critical", "major") for r in rows)
```

### TS-84-11: Findings command filters by archetype

**Requirement:** 84-REQ-4.4
**Type:** unit
**Description:** Verify `--archetype` filter queries the correct table.

**Preconditions:**
- DuckDB with skeptic findings and verifier verdicts.

**Input:**
- `query_findings(conn, archetype="verifier")`

**Expected:**
- Only verifier verdicts returned (archetype="verifier" on each row).

**Assertion pseudocode:**
```
rows = query_findings(conn, archetype="verifier")
ASSERT all(r.archetype == "verifier" for r in rows)
```

### TS-84-12: Findings command filters by run ID

**Requirement:** 84-REQ-4.5
**Type:** unit
**Description:** Verify `--run` filter scopes findings to sessions within
the given run.

**Preconditions:**
- DuckDB with findings from two different runs (session IDs contain run
  context).

**Input:**
- `query_findings(conn, run_id="run-abc")`

**Expected:**
- Only findings from the specified run returned.

**Assertion pseudocode:**
```
rows = query_findings(conn, run_id="run-abc")
ASSERT len(rows) > 0
ASSERT all(r is from run "run-abc" for r in rows)
```

### TS-84-13: Findings command JSON output

**Requirement:** 84-REQ-4.6
**Type:** unit
**Description:** Verify `--json` flag produces valid JSON array output.

**Preconditions:**
- DuckDB with 2 active findings.

**Input:**
- `format_findings_table(findings, json_output=True)`

**Expected:**
- Output is a valid JSON array with 2 elements.
- Each element has keys: id, severity, archetype, spec_name, description.

**Assertion pseudocode:**
```
output = format_findings_table(findings, json_output=True)
data = json.loads(output)
ASSERT isinstance(data, list)
ASSERT len(data) == 2
ASSERT "severity" in data[0]
```

### TS-84-14: Status includes findings summary

**Requirement:** 84-REQ-5.1
**Type:** unit
**Description:** Verify status report includes findings summary when
critical or major findings exist.

**Preconditions:**
- DuckDB with 1 critical and 2 major findings for spec "my_spec".

**Input:**
- `generate_status(state, plan, conn)`

**Expected:**
- `StatusReport.findings_summary` is non-empty.
- Contains entry for "my_spec" with critical=1, major=2.

**Assertion pseudocode:**
```
report = generate_status(state, plan, conn)
ASSERT len(report.findings_summary) == 1
ASSERT report.findings_summary[0].spec_name == "my_spec"
ASSERT report.findings_summary[0].critical == 1
ASSERT report.findings_summary[0].major == 2
```

### TS-84-15: Status omits findings summary when none

**Requirement:** 84-REQ-5.2
**Type:** unit
**Description:** Verify status report omits findings section when no
critical or major findings exist.

**Preconditions:**
- DuckDB with only minor and observation findings.

**Input:**
- `generate_status(state, plan, conn)`

**Expected:**
- `StatusReport.findings_summary` is empty.

**Assertion pseudocode:**
```
report = generate_status(state, plan, conn)
ASSERT report.findings_summary == []
```

## Edge Case Tests

### TS-84-E1: Response truncation at 100k characters

**Requirement:** 84-REQ-1.E1
**Type:** unit
**Description:** Verify response exceeding 100,000 chars is truncated
with `[truncated]` marker.

**Preconditions:**
- A `JsonlSink` instance.

**Input:**
- `SessionOutcome(response="x" * 150_000)`

**Expected:**
- JSONL record `response` field is exactly 100,011 chars (100,000 +
  `[truncated]`).
- Ends with `[truncated]`.

**Assertion pseudocode:**
```
sink.record_session_outcome(SessionOutcome(response="x" * 150_000))
record = read_last_jsonl_line(tmp_path)
ASSERT record["response"].endswith("[truncated]")
ASSERT len(record["response"]) == 100_011
```

### TS-84-E2: Audit emission failure does not raise

**Requirement:** 84-REQ-2.E1
**Type:** unit
**Description:** Verify that if audit event emission raises, the system
logs a warning but does not propagate the exception.

**Preconditions:**
- Mock sink that raises `RuntimeError` on `emit_audit_event()`.

**Input:**
- Call `persist_review_findings()` with valid findings.

**Expected:**
- Findings are still inserted to DuckDB.
- No exception propagates.

**Assertion pseudocode:**
```
mock_sink.emit_audit_event = Mock(side_effect=RuntimeError)
persist_review_findings(transcript, ..., sink=mock_sink)  # no exception
ASSERT findings_in_db(conn) == 1  # still inserted
```

### TS-84-E3: No knowledge DB for findings command

**Requirement:** 84-REQ-4.E1
**Type:** unit
**Description:** Verify graceful exit when no DB exists.

**Preconditions:**
- No `.agent-fox/knowledge.duckdb` file.

**Input:**
- Invoke `findings_cmd` via Click test runner.

**Expected:**
- Output contains "No knowledge database found".
- Exit code 0.

**Assertion pseudocode:**
```
result = cli_runner.invoke(findings_cmd)
ASSERT result.exit_code == 0
ASSERT "No knowledge database found" in result.output
```

### TS-84-E4: Empty query result message

**Requirement:** 84-REQ-4.E2
**Type:** unit
**Description:** Verify message when no findings match filters.

**Preconditions:**
- DuckDB exists but has no findings.

**Input:**
- Invoke `findings_cmd` via Click test runner.

**Expected:**
- Output contains "No findings match the given filters".
- Exit code 0.

**Assertion pseudocode:**
```
result = cli_runner.invoke(findings_cmd, ["--spec", "nonexistent"])
ASSERT result.exit_code == 0
ASSERT "No findings match" in result.output
```

### TS-84-E5: Status findings with DB open failure

**Requirement:** 84-REQ-5.E1
**Type:** unit
**Description:** Verify status omits findings section when DB cannot be
opened.

**Preconditions:**
- DB path points to a non-existent file.

**Input:**
- `generate_status(state, plan, conn=None)`

**Expected:**
- `findings_summary` is empty.
- No exception raised.

**Assertion pseudocode:**
```
report = generate_status(state, plan, conn=None)
ASSERT report.findings_summary == []
```

## Property Test Cases

### TS-84-P1: Response truncation preserves prefix

**Property:** Property 1 from design.md
**Validates:** 84-REQ-1.1, 84-REQ-1.E1
**Type:** property
**Description:** For any response string, the JSONL record response
equals the input when under limit, or its 100k prefix + marker when over.

**For any:** string of length 0 to 200,000
**Invariant:** If `len(s) <= 100_000`, record response == s. If
`len(s) > 100_000`, record response == `s[:100_000] + "[truncated]"`.

**Assertion pseudocode:**
```
FOR ANY s IN text(max_size=200_000):
    truncated = truncate_response(s)
    IF len(s) <= 100_000:
        ASSERT truncated == s
    ELSE:
        ASSERT truncated == s[:100_000] + "[truncated]"
```

### TS-84-P2: Audit event count matches insertion count

**Property:** Property 2 from design.md
**Validates:** 84-REQ-2.1
**Type:** property
**Description:** For any list of valid findings, the audit event count
field equals the number of successfully inserted records.

**For any:** list of 1–20 findings with valid severities
**Invariant:** `event.payload["count"]` equals the number of rows in
`review_findings` table after insert.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy, min_size=1, max_size=20):
    persist_and_capture_event(findings, sink)
    ASSERT sink.last_event.payload["count"] == count_rows(conn)
```

### TS-84-P3: Block reason finding ID count capped at 3

**Property:** Property 3 from design.md
**Validates:** 84-REQ-3.1, 84-REQ-3.E1
**Type:** property
**Description:** For any number of critical findings, the blocking reason
contains at most 3 finding IDs.

**For any:** 1–10 critical findings
**Invariant:** The reason string contains min(n, 3) occurrences of the
`F-` prefix pattern. If n > 3, contains "and {n-3} more".

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 10):
    reason = _format_block_reason(archetype, n_findings, ...)
    id_count = reason.count("F-")
    ASSERT id_count == min(n, 3)
    IF n > 3:
        ASSERT f"and {n - 3} more" in reason
```

### TS-84-P4: Severity filter monotonicity

**Property:** Property 4 from design.md
**Validates:** 84-REQ-4.3
**Type:** property
**Description:** For any severity filter, all returned findings are at
or above that severity level.

**For any:** severity in {critical, major, minor, observation} and a DB
with findings at all severity levels
**Invariant:** Every returned finding's severity is >= the filter level
in the ordering critical > major > minor > observation.

**Assertion pseudocode:**
```
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "observation": 3}
FOR ANY filter_sev IN sampled_from(SEVERITY_ORDER.keys()):
    rows = query_findings(conn, severity=filter_sev)
    FOR row IN rows:
        ASSERT SEVERITY_ORDER[row.severity] <= SEVERITY_ORDER[filter_sev]
```

### TS-84-P5: Findings table row count matches query count

**Property:** Property 5 from design.md
**Validates:** 84-REQ-4.1, 84-REQ-4.6
**Type:** property
**Description:** For any non-empty findings list, the formatted table
has exactly as many data rows as findings, and JSON output has the same
length.

**For any:** list of 1–20 FindingRow objects
**Invariant:** Table output has `len(findings)` data rows. JSON output
parses to list of `len(findings)` items.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(finding_row_strategy, min_size=1, max_size=20):
    table = format_findings_table(findings)
    json_out = format_findings_table(findings, json_output=True)
    ASSERT json.loads(json_out) has len(findings) items
```

### TS-84-P6: Status summary omits specs without critical/major

**Property:** Property 6 from design.md
**Validates:** 84-REQ-5.1, 84-REQ-5.2
**Type:** property
**Description:** For any set of findings, the status summary only
includes specs that have at least one critical or major finding.

**For any:** DB with findings at various severities across multiple specs
**Invariant:** Every spec in the summary has `critical > 0 or major > 0`.
No spec with only minor/observation findings appears.

**Assertion pseudocode:**
```
FOR ANY findings_set IN generated_findings_across_specs():
    summary = query_findings_summary(conn)
    FOR entry IN summary:
        ASSERT entry.critical > 0 or entry.major > 0
```

## Integration Smoke Tests

### TS-84-SMOKE-1: Response persisted end-to-end

**Execution Path:** Path 1 from design.md
**Description:** Verify that a session outcome with response text
produces a JSONL record containing that text.

**Setup:** Real `JsonlSink` writing to a temp file. No mocks on sink
internals.

**Trigger:** Call `sink.record_session_outcome(outcome)` with a
non-empty response.

**Expected side effects:**
- JSONL file contains one line with `"response"` key matching the input.

**Must NOT satisfy with:** Mocking `_write_event` or the file I/O.

**Assertion pseudocode:**
```
sink = JsonlSink(tmp_path)
outcome = SessionOutcome(response="test output", node_id="s:0")
sink.record_session_outcome(outcome)
line = read_jsonl(tmp_path)[-1]
ASSERT line["response"] == "test output"
```

### TS-84-SMOKE-2: Findings persistence emits audit event end-to-end

**Execution Path:** Path 2 from design.md
**Description:** Verify real `persist_review_findings()` inserts to
DuckDB and emits the audit event.

**Setup:** In-memory DuckDB with tables created. Real
`SinkDispatcher` with a `CapturingSink` that records events.

**Trigger:** `persist_review_findings(transcript, ..., sink=dispatcher)`
with valid skeptic JSON.

**Expected side effects:**
- Rows present in `review_findings` table.
- `CapturingSink` received a `review.findings_persisted` event.

**Must NOT satisfy with:** Mocking `insert_findings` or
`emit_audit_event`.

**Assertion pseudocode:**
```
dispatcher = SinkDispatcher([capturing_sink])
persist_review_findings(json_transcript, ..., sink=dispatcher)
ASSERT count_rows(conn, "review_findings") > 0
ASSERT capturing_sink.events[-1].event_type == "review.findings_persisted"
```

### TS-84-SMOKE-3: Findings CLI command end-to-end

**Execution Path:** Path 4 from design.md
**Description:** Verify the CLI command queries real DuckDB and produces
formatted output.

**Setup:** Temp DuckDB with review tables populated with test findings.
Patch `DEFAULT_DB_PATH` to the temp DB.

**Trigger:** Invoke `findings_cmd` via Click test runner.

**Expected side effects:**
- Output contains finding descriptions from the DB.
- Exit code 0.

**Must NOT satisfy with:** Mocking `query_findings` or
`format_findings_table`.

**Assertion pseudocode:**
```
populate_db(tmp_db, findings=[...])
with patch("DEFAULT_DB_PATH", tmp_db):
    result = cli_runner.invoke(findings_cmd)
ASSERT result.exit_code == 0
ASSERT "missing guard" in result.output  # description from test data
```

### TS-84-SMOKE-4: Status findings summary end-to-end

**Execution Path:** Path 5 from design.md
**Description:** Verify status report includes findings summary from
real DuckDB data.

**Setup:** Temp DuckDB with critical findings. Real `generate_status()`
call.

**Trigger:** `generate_status(state, plan, conn=tmp_conn)`

**Expected side effects:**
- `StatusReport.findings_summary` contains the spec with critical
  findings.

**Must NOT satisfy with:** Mocking `query_findings_summary`.

**Assertion pseudocode:**
```
populate_db(tmp_conn, findings=[critical_finding])
report = generate_status(state, plan, conn=tmp_conn)
ASSERT len(report.findings_summary) > 0
```

### TS-84-SMOKE-5: Enriched blocking reason end-to-end

**Execution Path:** Path 3 from design.md
**Description:** Verify `evaluate_review_blocking()` with real DuckDB
findings produces an enriched reason with finding IDs.

**Setup:** In-memory DuckDB with critical findings inserted. Real
`evaluate_review_blocking()`.

**Trigger:** Call with a skeptic session record and threshold=0.

**Expected side effects:**
- `BlockDecision.should_block` is True.
- `BlockDecision.reason` contains `F-` prefixed finding IDs and
  descriptions.

**Must NOT satisfy with:** Mocking `query_findings_by_session` or
`_format_block_reason`.

**Assertion pseudocode:**
```
insert_findings(conn, [critical_finding_1, critical_finding_2])
decision = evaluate_review_blocking(record, config, conn)
ASSERT decision.should_block
ASSERT "F-" in decision.reason
ASSERT "critical" in decision.reason
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 84-REQ-1.1 | TS-84-1 | unit |
| 84-REQ-1.2 | TS-84-2 | unit |
| 84-REQ-1.E1 | TS-84-E1 | unit |
| 84-REQ-2.1 | TS-84-3 | unit |
| 84-REQ-2.2 | TS-84-4 | unit |
| 84-REQ-2.3 | TS-84-5 | unit |
| 84-REQ-2.E1 | TS-84-E2 | unit |
| 84-REQ-3.1 | TS-84-6 | unit |
| 84-REQ-3.2 | TS-84-14 | unit |
| 84-REQ-3.E1 | TS-84-7 | unit |
| 84-REQ-4.1 | TS-84-8 | unit |
| 84-REQ-4.2 | TS-84-9 | unit |
| 84-REQ-4.3 | TS-84-10 | unit |
| 84-REQ-4.4 | TS-84-11 | unit |
| 84-REQ-4.5 | TS-84-12 | unit |
| 84-REQ-4.6 | TS-84-13 | unit |
| 84-REQ-4.E1 | TS-84-E3 | unit |
| 84-REQ-4.E2 | TS-84-E4 | unit |
| 84-REQ-5.1 | TS-84-14 | unit |
| 84-REQ-5.2 | TS-84-15 | unit |
| 84-REQ-5.E1 | TS-84-E5 | unit |
| Property 1 | TS-84-P1 | property |
| Property 2 | TS-84-P2 | property |
| Property 3 | TS-84-P3 | property |
| Property 4 | TS-84-P4 | property |
| Property 5 | TS-84-P5 | property |
| Property 6 | TS-84-P6 | property |
| Path 1 | TS-84-SMOKE-1 | integration |
| Path 2 | TS-84-SMOKE-2 | integration |
| Path 3 | TS-84-SMOKE-5 | integration |
| Path 4 | TS-84-SMOKE-3 | integration |
| Path 5 | TS-84-SMOKE-4 | integration |
