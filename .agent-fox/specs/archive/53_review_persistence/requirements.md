# Requirements Document

## Introduction

This specification fixes the review archetype persistence pipeline so that
Skeptic findings, Verifier verdicts, and Oracle drift findings are parsed from
archetype session output and stored in DuckDB. It also adds a review-only run
mode that executes only review archetypes against an existing codebase without
running coder sessions.

## Glossary

- **Review archetype**: A non-coder archetype (Skeptic, Verifier, Oracle) that
  analyzes code quality, requirement compliance, or spec drift.
- **Skeptic**: An archetype that identifies bugs, risks, and code quality
  issues. Produces `ReviewFinding` records.
- **Verifier**: An archetype that checks whether code satisfies requirements.
  Produces `VerificationResult` records with PASS/FAIL verdicts.
- **Oracle**: An archetype that detects drift between specs and implementation.
  Produces `DriftFinding` records.
- **Structured JSON output**: JSON conforming to the `ReviewFinding`,
  `VerificationResult`, or `DriftFinding` dataclasses in
  `knowledge/review_store.py`, embedded in the archetype session's text output.
- **Supersession**: When a new finding/verdict replaces a prior one for the
  same spec + reference. The prior row's `superseded_by` column is set to the
  new row's ID.
- **Review-only mode**: A run mode where only review archetypes execute against
  the current codebase. No coder sessions run, no source files are modified.
- **Active finding**: A finding whose `superseded_by` column is NULL.
- **Retry**: A subsequent attempt at a task group after a prior attempt failed,
  governed by `max_retries` in `OrchestratorConfig`.
- **Allowlist**: The set of shell commands an archetype is permitted to execute,
  defined in `ArchetypeEntry.default_allowlist`.

## Requirements

### Requirement 1: Skeptic Finding Persistence

**User Story:** As an operator, I want Skeptic findings stored in DuckDB, so
that code quality issues are tracked across sessions.

#### Acceptance Criteria

1. [53-REQ-1.1] WHEN a Skeptic session completes, THE engine SHALL extract
   JSON from its output text and call `insert_findings()` for each parsed
   `ReviewFinding`. Each finding SHALL have `severity`, `description`,
   `requirement_ref`, `spec_name`, `task_group`, and `session_id` populated.

2. [53-REQ-1.2] WHEN a new Skeptic finding is inserted for the same
   `spec_name` and `task_group`, THE engine SHALL set the `superseded_by`
   column of prior active findings for that spec + task_group to the new
   finding's ID.

#### Edge Cases

1. [53-REQ-1.E1] IF the Skeptic session output contains no valid JSON, THEN
   THE engine SHALL emit a warning-severity `review.parse_failure` audit event
   with the raw output truncated to 2000 characters. The parse failure SHALL
   NOT block the run.

### Requirement 2: Verifier Verdict Persistence

**User Story:** As an operator, I want Verifier verdicts stored in DuckDB, so
that requirement compliance is tracked.

#### Acceptance Criteria

1. [53-REQ-2.1] WHEN a Verifier session completes, THE engine SHALL extract
   JSON from its output text and call `insert_verdicts()` for each parsed
   `VerificationResult`. Each verdict SHALL have `requirement_id`, `verdict`
   (PASS or FAIL), `evidence`, `spec_name`, `task_group`, and `session_id`
   populated.

2. [53-REQ-2.2] WHEN a new verdict is inserted for the same `spec_name` and
   `task_group`, THE engine SHALL set the `superseded_by` column of prior
   active verdicts for that spec + task_group to the new verdict's ID.

#### Edge Cases

1. [53-REQ-2.E1] IF the Verifier session output contains no valid JSON, THEN
   THE engine SHALL emit a warning-severity `review.parse_failure` audit event
   with the raw output truncated to 2000 characters.

### Requirement 3: Oracle Drift Finding Persistence

**User Story:** As an operator, I want Oracle drift findings stored in DuckDB,
so that spec-implementation divergence is tracked.

#### Acceptance Criteria

1. [53-REQ-3.1] WHEN an Oracle session completes, THE engine SHALL extract
   JSON from its output text and call `insert_drift_findings()` for each
   parsed `DriftFinding`. Each finding SHALL have `severity`, `description`,
   `spec_ref`, `artifact_ref`, `spec_name`, `task_group`, and `session_id`
   populated.

2. [53-REQ-3.2] WHEN a new drift finding is inserted for the same `spec_name`
   and `task_group`, THE engine SHALL set the `superseded_by` column of prior
   active drift findings for that spec + task_group to the new finding's ID.

#### Edge Cases

1. [53-REQ-3.E1] IF the Oracle session output contains no valid JSON, THEN
   THE engine SHALL emit a warning-severity `review.parse_failure` audit event
   with the raw output truncated to 2000 characters.

### Requirement 4: JSON Extraction from Output

**User Story:** As an operator, I want the engine to reliably extract JSON
from archetype output that may contain surrounding prose or markdown.

#### Acceptance Criteria

1. [53-REQ-4.1] THE engine SHALL extract JSON arrays from archetype output by
   searching for the first `[` and last `]` in the output text. If the
   extracted substring is valid JSON, it SHALL be parsed. If not, the engine
   SHALL try extracting from markdown code fences (```json ... ```).

2. [53-REQ-4.2] WHEN JSON extraction succeeds, THE engine SHALL validate each
   object against the expected dataclass fields. Objects missing required
   fields SHALL be skipped with a warning log.

#### Edge Cases

1. [53-REQ-4.E1] IF the output contains multiple JSON arrays, THEN THE engine
   SHALL use the first valid JSON array found.

### Requirement 5: Review Context in Retries

**User Story:** As an operator, I want coder retry sessions to see prior
review findings, so that the coder can address identified issues.

#### Acceptance Criteria

1. [53-REQ-5.1] WHEN a coder session is a retry (attempt > 1), THE context
   assembly step SHALL query active critical and major review findings for the
   current spec from `review_findings` and include them in the coder prompt.

2. [53-REQ-5.2] THE included findings SHALL be formatted as a structured block
   containing spec name, severity, description, and requirement reference.

#### Edge Cases

1. [53-REQ-5.E1] IF no active critical/major findings exist for the spec,
   THEN THE context assembly step SHALL not add a findings block to the prompt.

### Requirement 6: Review-Only CLI Flag

**User Story:** As an operator, I want to run only review archetypes against
existing code, so that I can validate implementation quality without
re-running coder sessions.

#### Acceptance Criteria

1. [53-REQ-6.1] THE CLI SHALL accept a `--review-only` flag on the `code`
   command. WHEN set, THE engine SHALL skip all coder sessions and execute
   only enabled review archetypes (Skeptic, Verifier, Oracle) against the
   current codebase state.

2. [53-REQ-6.2] WHILE in review-only mode, THE task graph SHALL contain only
   review archetype nodes. Skeptic and Oracle nodes SHALL be created for each
   spec that has source files (`.py`, `.ts`, `.go`, `.rs`, `.java`, `.js`)
   in its workspace. Verifier nodes SHALL be created for each spec that has a
   `requirements.md`.

3. [53-REQ-6.3] WHILE in review-only mode, THE engine SHALL emit `run.start`
   and `run.complete` audit events with a `mode: "review_only"` field in the
   payload.

4. [53-REQ-6.4] WHILE in review-only mode, ALL archetype sessions SHALL use
   their existing read-only allowlists. No archetype SHALL be permitted to
   execute commands outside its `default_allowlist`.

5. [53-REQ-6.5] WHEN a review-only run completes, THE engine SHALL print a
   summary listing: total findings by severity, total verdicts by status
   (PASS/FAIL), and total drift findings by severity.

#### Edge Cases

1. [53-REQ-6.E1] IF no specs have source files or `requirements.md`, THEN THE
   engine SHALL print a message "No specs eligible for review" and exit with
   code 0.

2. [53-REQ-6.E2] WHEN `--review-only` is combined with spec filters (e.g.
   `--spec 03_api`), THE engine SHALL apply the filter to restrict which specs
   are reviewed.
