# Implementation Plan: Review Archetype Output Visibility

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in five groups: (1) failing tests, (2) JSONL response
logging and audit events (Level 1 logging), (3) enriched blocking reasons
(Level 1 blocking), (4) CLI findings command and status summary (Level 2
introspection), (5) wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_jsonl_response.py tests/unit/engine/test_review_audit_events.py tests/unit/engine/test_block_reason_enrichment.py tests/unit/cli/test_findings_cmd.py tests/unit/reporting/test_findings_report.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create JSONL response logging tests
    - Create `tests/unit/knowledge/test_jsonl_response.py`
    - Translate TS-84-1, TS-84-2 (response field written)
    - Translate TS-84-E1 (truncation at 100k)
    - _Test Spec: TS-84-1, TS-84-2, TS-84-E1_

  - [x] 1.2 Create audit event emission tests
    - Create `tests/unit/engine/test_review_audit_events.py`
    - Translate TS-84-3, TS-84-4, TS-84-5 (persisted events for each archetype)
    - Translate TS-84-E2 (emission failure does not raise)
    - _Test Spec: TS-84-3, TS-84-4, TS-84-5, TS-84-E2_

  - [x] 1.3 Create blocking reason enrichment tests
    - Create `tests/unit/engine/test_block_reason_enrichment.py`
    - Translate TS-84-6 (finding IDs in reason)
    - Translate TS-84-7 (cap at 3 IDs)
    - _Test Spec: TS-84-6, TS-84-7_

  - [x] 1.4 Create findings CLI and reporting tests
    - Create `tests/unit/cli/test_findings_cmd.py`
    - Create `tests/unit/reporting/test_findings_report.py`
    - Translate TS-84-8 through TS-84-13 (query, filter, format)
    - Translate TS-84-14, TS-84-15 (status summary)
    - Translate TS-84-E3, TS-84-E4, TS-84-E5 (edge cases)
    - _Test Spec: TS-84-8 through TS-84-15, TS-84-E3, TS-84-E4, TS-84-E5_

  - [x] 1.5 Create property tests
    - Create `tests/property/test_review_visibility_props.py`
    - Translate TS-84-P1 through TS-84-P6
    - _Test Spec: TS-84-P1, TS-84-P2, TS-84-P3, TS-84-P4, TS-84-P5, TS-84-P6_

  - [x] 1.6 Create integration smoke tests
    - Create `tests/integration/test_review_visibility_smoke.py`
    - Translate TS-84-SMOKE-1 through TS-84-SMOKE-5
    - _Test Spec: TS-84-SMOKE-1 through TS-84-SMOKE-5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check`

- [x] 2. JSONL response logging and audit events
  - [x] 2.1 Add response field to JSONL sink
    - Modify `JsonlSink.record_session_outcome()` in
      `agent_fox/knowledge/jsonl_sink.py` to include the `response` field
    - Add truncation logic: if `len(response) > 100_000`, write
      `response[:100_000] + "[truncated]"`
    - _Requirements: 84-REQ-1.1, 84-REQ-1.2, 84-REQ-1.E1_

  - [x] 2.2 Add new AuditEventType members
    - Add `REVIEW_FINDINGS_PERSISTED`, `REVIEW_VERDICTS_PERSISTED`,
      `REVIEW_DRIFT_PERSISTED` to `AuditEventType` in
      `agent_fox/knowledge/audit.py`
    - _Requirements: 84-REQ-2.1, 84-REQ-2.2, 84-REQ-2.3_

  - [x] 2.3 Emit audit events after successful persistence
    - Modify `persist_review_findings()` in
      `agent_fox/engine/review_persistence.py`
    - After `insert_findings()`: emit `review.findings_persisted` with count
      and severity summary
    - After `insert_verdicts()`: emit `review.verdicts_persisted` with count,
      pass_count, fail_count
    - After `insert_drift_findings()`: emit `review.drift_persisted` with
      count and severity summary
    - Wrap emission in try/except to satisfy 84-REQ-2.E1
    - _Requirements: 84-REQ-2.1, 84-REQ-2.2, 84-REQ-2.3, 84-REQ-2.E1_

  - [x] 2.V Verify task group 2
    - [x] JSONL tests pass: `uv run pytest -q tests/unit/knowledge/test_jsonl_response.py`
    - [x] Audit event tests pass: `uv run pytest -q tests/unit/engine/test_review_audit_events.py`
    - [x] Property tests TS-84-P1, TS-84-P2 pass
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check`
    - [x] Requirements 84-REQ-1.1, 1.2, 1.E1, 2.1, 2.2, 2.3, 2.E1 met

- [ ] 3. Enriched blocking reasons
  - [ ] 3.1 Add `_format_block_reason()` helper
    - Add to `agent_fox/engine/result_handler.py`
    - Accept archetype, findings list, threshold, spec_name, task_group
    - Format: "{Archetype} found N critical finding(s) (threshold: T) for
      spec:group — F-id1: desc…, F-id2: desc…"
    - Cap at 3 IDs, append "and N more" if exceeded
    - Truncate each description to 60 chars
    - _Requirements: 84-REQ-3.1, 84-REQ-3.E1_

  - [ ] 3.2 Wire enriched reason into `evaluate_review_blocking()`
    - Replace the existing generic reason string (line 134-138) with a call
      to `_format_block_reason(archetype, findings, threshold, spec, group)`
    - Pass the `findings` list (already queried) to the formatter
    - _Requirements: 84-REQ-3.1, 84-REQ-3.2_

  - [ ] 3.V Verify task group 3
    - [ ] Blocking tests pass: `uv run pytest -q tests/unit/engine/test_block_reason_enrichment.py`
    - [ ] Property test TS-84-P3 passes
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 84-REQ-3.1, 3.2, 3.E1 met

- [ ] 4. CLI findings command and status summary
  - [ ] 4.1 Create `reporting/findings.py` module
    - Define `FindingRow` and `FindingsSummary` dataclasses
    - Implement `query_findings()` with spec, severity, archetype, run_id,
      active_only filters
    - Implement `query_findings_summary()` returning per-spec counts of
      critical/major findings
    - Implement `format_findings_table()` for table and JSON output
    - _Requirements: 84-REQ-4.1, 84-REQ-4.2, 84-REQ-4.3, 84-REQ-4.4,
      84-REQ-4.5, 84-REQ-4.6_

  - [ ] 4.2 Create `cli/findings.py` command
    - Define `findings_cmd` with Click options: `--spec`, `--severity`,
      `--archetype`, `--run`, `--json`
    - Open read-only DuckDB connection (handle missing DB: 84-REQ-4.E1)
    - Call `query_findings()`, handle empty result (84-REQ-4.E2)
    - Output via `format_findings_table()`
    - _Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-4.E1, 84-REQ-4.E2_

  - [ ] 4.3 Register command in `cli/app.py`
    - Import `findings_cmd` and add `main.add_command(findings_cmd, name="findings")`
    - _Requirements: 84-REQ-4.1_

  - [ ] 4.4 Add findings summary to status report
    - Add `findings_summary: list[FindingsSummary]` field to `StatusReport`
      in `reporting/status.py`
    - Call `query_findings_summary()` in `generate_status()` when DB
      connection is available
    - Handle DB open failure gracefully (84-REQ-5.E1)
    - Render "Review Findings" section in status output when non-empty
    - _Requirements: 84-REQ-5.1, 84-REQ-5.2, 84-REQ-5.E1_

  - [ ] 4.V Verify task group 4
    - [ ] CLI tests pass: `uv run pytest -q tests/unit/cli/test_findings_cmd.py`
    - [ ] Reporting tests pass: `uv run pytest -q tests/unit/reporting/test_findings_report.py`
    - [ ] Property tests TS-84-P4, TS-84-P5, TS-84-P6 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 84-REQ-4.*, 84-REQ-5.* met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1: JsonlSink.record_session_outcome → state.jsonl contains
      response field
    - Path 2: persist_review_findings → insert_findings → emit
      review.findings_persisted audit event
    - Path 3: evaluate_review_blocking → _format_block_reason →
      BlockDecision.reason → blocked_reasons
    - Path 4: findings_cmd → query_findings → format_findings_table → stdout
    - Path 5: generate_status → query_findings_summary → StatusReport
    - Confirm no function in any chain is a stub
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - `insert_findings()` return count → used in audit event payload
    - `query_findings()` return list → consumed by format_findings_table
    - `query_findings_summary()` return list → assigned to
      StatusReport.findings_summary
    - `_format_block_reason()` return str → assigned to BlockDecision.reason
    - Grep for callers, confirm none discards the return
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All TS-84-SMOKE-* tests pass using real components (not stubbed)
    - _Test Spec: TS-84-SMOKE-1, TS-84-SMOKE-2, TS-84-SMOKE-3,
      TS-84-SMOKE-4, TS-84-SMOKE-5_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit: justified or replaced
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 84-REQ-1.1 | TS-84-1 | 2.1 | test_jsonl_response.py |
| 84-REQ-1.2 | TS-84-2 | 2.1 | test_jsonl_response.py |
| 84-REQ-1.E1 | TS-84-E1 | 2.1 | test_jsonl_response.py |
| 84-REQ-2.1 | TS-84-3 | 2.2, 2.3 | test_review_audit_events.py |
| 84-REQ-2.2 | TS-84-4 | 2.2, 2.3 | test_review_audit_events.py |
| 84-REQ-2.3 | TS-84-5 | 2.2, 2.3 | test_review_audit_events.py |
| 84-REQ-2.E1 | TS-84-E2 | 2.3 | test_review_audit_events.py |
| 84-REQ-3.1 | TS-84-6 | 3.1, 3.2 | test_block_reason_enrichment.py |
| 84-REQ-3.2 | TS-84-14 | 3.2 | test_findings_report.py |
| 84-REQ-3.E1 | TS-84-7 | 3.1 | test_block_reason_enrichment.py |
| 84-REQ-4.1 | TS-84-8 | 4.1, 4.2, 4.3 | test_findings_cmd.py, test_findings_report.py |
| 84-REQ-4.2 | TS-84-9 | 4.1 | test_findings_report.py |
| 84-REQ-4.3 | TS-84-10 | 4.1 | test_findings_report.py |
| 84-REQ-4.4 | TS-84-11 | 4.1 | test_findings_report.py |
| 84-REQ-4.5 | TS-84-12 | 4.1 | test_findings_report.py |
| 84-REQ-4.6 | TS-84-13 | 4.1 | test_findings_report.py |
| 84-REQ-4.E1 | TS-84-E3 | 4.2 | test_findings_cmd.py |
| 84-REQ-4.E2 | TS-84-E4 | 4.2 | test_findings_cmd.py |
| 84-REQ-5.1 | TS-84-14 | 4.4 | test_findings_report.py |
| 84-REQ-5.2 | TS-84-15 | 4.4 | test_findings_report.py |
| 84-REQ-5.E1 | TS-84-E5 | 4.4 | test_findings_report.py |
| Property 1 | TS-84-P1 | 2.1 | test_review_visibility_props.py |
| Property 2 | TS-84-P2 | 2.3 | test_review_visibility_props.py |
| Property 3 | TS-84-P3 | 3.1 | test_review_visibility_props.py |
| Property 4 | TS-84-P4 | 4.1 | test_review_visibility_props.py |
| Property 5 | TS-84-P5 | 4.1 | test_review_visibility_props.py |
| Property 6 | TS-84-P6 | 4.4 | test_review_visibility_props.py |

## Notes

- The `response` field in JSONL records may contain large JSON strings from
  review archetypes. The 100k truncation limit prevents unbounded disk growth.
- The `query_findings()` function queries all three review tables
  (review_findings, verification_results, drift_findings) and unifies results
  into `FindingRow` objects with an `archetype` discriminator.
- The `--run` filter requires joining findings to sessions via session_id,
  which encodes the run context. The exact join strategy depends on how
  session_id is structured (typically `node_id:attempt`).
- Existing tests in `tests/unit/engine/test_review_parse_resilience.py` may
  need minor updates if they assert on the exact set of audit events emitted
  during persistence.
