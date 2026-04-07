# PRD: Review Archetype Output Visibility

## Problem

Review archetypes (skeptic, verifier, oracle) produce structured findings,
verdicts, and drift reports that are persisted to DuckDB. However, these
outputs are effectively invisible for operational introspection:

1. **Raw responses are discarded.** The JSONL sink records session metadata
   (tokens, duration, status) but not the `SessionOutcome.response` text.
   When parsing fails, there is no record of what the agent actually said.

2. **No audit trail for successful persistence.** The system emits
   `review.parse_failure` events but has no corresponding success event.
   Operators cannot confirm whether findings were actually persisted or
   silently lost.

3. **Blocking reasons are opaque.** When a skeptic blocks a task, the
   blocking reason is a generic string like "Retry limit exceeded" with no
   link to the specific findings that caused the block. Resolving the block
   requires manually querying DuckDB.

4. **No CLI access to review data.** The only way to see findings is via
   `agent-fox export --db`, which dumps the entire database with no
   filtering. There is no focused command for querying review findings by
   spec, severity, archetype, or run.

## Solution

### Level 1: Logging (low effort)

- Write `SessionOutcome.response` to the JSONL sink so raw responses are
  always on disk.
- Emit `review.findings_persisted` audit events with counts and severity
  summary when findings are successfully stored.
- Include finding IDs and a severity summary in `blocked_reasons` when a
  skeptic blocks a task (e.g., "2 critical findings (F-abc123, F-def456):
  missing error handling, no input validation").

### Level 2: Introspection (medium effort)

- Add `agent-fox findings` CLI command that queries the DuckDB review tables
  with filters: `--spec`, `--severity`, `--archetype`, `--run`, `--active-only`.
- Enhance `agent-fox status` to show a findings summary for specs with
  critical or major findings.

## Clarifications

- **Q: Storage format for raw responses?**
  A: Add `response` as a field to the existing session outcome JSONL record.
  No separate transcript files.

- **Q: CLI command structure?**
  A: New top-level `agent-fox findings` command, not a status subcommand.

- **Q: Blocking reason detail level?**
  A: Summary with finding IDs: "2 critical findings (F-abc123, F-def456):
  missing error handling, no input validation". Concise but actionable.

- **Q: Run ID filtering?**
  A: Yes, `--run` flag to scope findings to a specific orchestrator run.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 82_fix_pipeline_triage_reviewer | 2 | 2 | Uses review parser types (TriageResult, FixReviewResult) defined in group 2; group 2 is where data types and parsers are first implemented |
