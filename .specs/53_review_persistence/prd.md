# PRD: Review Archetype Persistence & Review-Only Mode

> Source: post-run analysis of parking-fee-service knowledge.duckdb
> (2026-03-17 runs). Skeptic, Verifier, and Oracle archetypes were enabled
> but produced zero persisted records.

## Problem Statement

Skeptic, Verifier, and Oracle are enabled in config and injected into the task
graph, but the parking-fee-service run shows zero rows in `review_findings`,
`verification_results`, and `drift_findings`. Either the archetype sessions
did not run, their output was not parsed, or parsed output was not persisted.

Additionally, there is no way to run review archetypes against
already-implemented code without re-running coder sessions. The second
parking-fee-service run was a no-op — it found no coder work and exited
without running any review archetypes.

## Goals

1. **Review archetypes produce persistent records** — Skeptic findings,
   Verifier verdicts, and Oracle drift findings are stored in DuckDB and
   surfaced in subsequent sessions.
2. **A dedicated review-only run mode** allows a post-implementation sweep
   without re-running coder sessions.

## Non-Goals

- Changing archetype prompt templates or output schemas.
- Adding new archetypes.
- Adding new DuckDB tables (review tables already exist).
- Knowledge harvest fixes (see spec 52).
- Quality gate or complexity enrichment (see spec 54).

## Clarifications

- **Existing persistence functions** (verified 2026-03-29):
  - `insert_findings(conn, findings: list[ReviewFinding]) -> int` in `knowledge/review_store.py`
  - `insert_verdicts(conn, verdicts: list[VerificationResult]) -> int` in `knowledge/review_store.py`
  - Drift findings: no dedicated insert function exists yet — one must be added
    following the pattern of `insert_findings()`.
- **Structured JSON output**: Archetype sessions are expected to produce JSON
  conforming to the `ReviewFinding`, `VerificationResult`, and `DriftFinding`
  dataclasses in `review_store.py`. The parsing step must extract JSON from the
  session's output text (which may contain markdown or prose around the JSON).
- **"When a retry is triggered"**: Refers to the existing `max_retries`
  mechanism in `OrchestratorConfig` (default 2). When a task group fails and
  is retried, the coder prompt for the retry session should include
  non-superseded critical/major findings from prior review passes.
- **"Implementation artifacts"**: Source files (`.py`, `.ts`, `.go`, etc.) in
  the spec's workspace directory, excluding test files and config files.
- **Read-only enforcement**: Via the existing `read_only` flag in archetype
  registration (Oracle and Skeptic already use `allowed_commands` allowlists
  that exclude write operations). In review-only mode, this flag is set for
  all archetype sessions.

## Requirements

### 1. Review Output Persistence

| ID | Requirement |
|----|-------------|
| RP-1.1 | WHEN a Skeptic session completes, THE engine SHALL extract JSON from its output and call `insert_findings()` for each finding. Findings SHALL be stored in `review_findings` with severity, description, requirement_ref, spec_name, task_group, and session_id populated. |
| RP-1.2 | WHEN a Verifier session completes, THE engine SHALL extract JSON from its output and call `insert_verdicts()` for each verdict. Verdicts SHALL be stored in `verification_results` with requirement_id, verdict (PASS/FAIL/PARTIAL), evidence, spec_name, task_group, and session_id populated. |
| RP-1.3 | WHEN an Oracle session completes, THE engine SHALL extract JSON from its output and store each drift finding in `drift_findings` with severity, description, spec_ref, artifact_ref, spec_name, task_group, and session_id populated. |
| RP-1.4 | WHEN a new finding or verdict is inserted for the same `spec_name` + `requirement_ref` (or `requirement_id`), THE engine SHALL set the `superseded_by` column of prior matching rows to the new row's ID. |
| RP-1.5 | IF an archetype session completes but produces no parseable JSON, THEN THE engine SHALL emit a warning-severity `review.parse_failure` audit event with the raw output truncated to 2000 characters for diagnosis. The parse failure SHALL NOT block the run. |

### 2. Review Context in Retries

| ID | Requirement |
|----|-------------|
| RP-2.1 | WHEN a coder session is a retry (retry count > 0), THE context assembly step SHALL query non-superseded critical and major review findings for the current spec and include them in the coder prompt. |
| RP-2.2 | THE included findings SHALL be formatted as a structured block (spec name, severity, description, requirement ref) so the coder can address them. |

### 3. Review-Only Run Mode

| ID | Requirement |
|----|-------------|
| RP-3.1 | THE CLI SHALL accept a `--review-only` flag. WHEN set, THE engine SHALL skip all coder sessions and execute only enabled review archetypes (Skeptic, Verifier, Oracle) against the current codebase state. |
| RP-3.2 | WHILE in review-only mode, THE task graph SHALL contain only review archetype nodes. Skeptic and Oracle nodes SHALL be created for each spec that has source files in its workspace. Verifier nodes SHALL be created for each spec that has a `requirements.md`. |
| RP-3.3 | WHILE in review-only mode, THE engine SHALL emit `run.start` and `run.complete` audit events with a `mode: "review_only"` field in the payload. |
| RP-3.4 | WHILE in review-only mode, ALL archetype sessions SHALL run with write access disabled (read-only workspace via the archetype `read_only` flag). THE engine SHALL NOT modify any source files. |
| RP-3.5 | WHEN a review-only run completes, THE engine SHALL print a summary listing: total findings by severity, total verdicts by status (PASS/FAIL/PARTIAL), and total drift findings by severity. |

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 52_knowledge_feedback_loop | 2 | 1 | Review persistence reads from the same DuckDB instance that harvest writes to; harvest must be functional for review findings to have causal context. Group 2 of spec 52 completes the harvest pipeline. |

## Out of Scope

- Knowledge harvest pipeline (spec 52).
- Quality gate (spec 54).
- Complexity enrichment (spec 54).
- Modifying archetype prompt templates.
- Adding new DuckDB tables or columns.
