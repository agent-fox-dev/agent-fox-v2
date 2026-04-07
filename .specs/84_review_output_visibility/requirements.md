# Requirements Document

## Introduction

This spec adds observability and introspection for review archetype outputs
(skeptic, verifier, oracle). It covers raw response logging, audit events
for successful persistence, enriched blocking reasons, and a CLI command
for querying review findings.

## Glossary

- **Review archetype**: An agent archetype (skeptic, verifier, oracle) that
  produces structured feedback about code quality, requirement compliance,
  or spec drift.
- **Finding**: A structured observation from a skeptic session, with severity
  (critical, major, minor, observation), description, and optional
  requirement reference. Stored in the `review_findings` DuckDB table.
- **Verdict**: A per-requirement PASS/FAIL judgment from a verifier session.
  Stored in the `verification_results` DuckDB table.
- **Drift finding**: A structured observation from an oracle session about
  divergence between spec and implementation. Stored in the `drift_findings`
  DuckDB table.
- **JSONL sink**: The `JsonlSink` class that writes session outcome records
  to `.agent-fox/state.jsonl`.
- **Audit event**: A structured event emitted via `SinkDispatcher` and
  recorded in audit JSONL files under `.agent-fox/audit/`.
- **Blocking reason**: A human-readable string stored in
  `ExecutionState.blocked_reasons` explaining why a task was blocked.
- **Active finding**: A finding that has not been superseded by a newer
  finding for the same (spec_name, task_group).

## Requirements

### Requirement 1: Raw Response Logging

**User Story:** As an operator, I want review archetype responses persisted
to disk so I can debug parse failures and verify agent behavior.

#### Acceptance Criteria

1. [84-REQ-1.1] WHEN the JSONL sink records a session outcome, THE system
   SHALL include the `response` field value in the JSONL record.

2. [84-REQ-1.2] WHEN the `response` field is empty, THE system SHALL write
   an empty string for the field rather than omitting it.

#### Edge Cases

1. [84-REQ-1.E1] IF the `response` field exceeds 100,000 characters, THEN
   THE system SHALL truncate it to 100,000 characters and append
   `"[truncated]"`.

### Requirement 2: Findings Persistence Audit Events

**User Story:** As an operator, I want confirmation that review findings
were successfully persisted so I can distinguish "no findings" from "parse
succeeded but insert failed."

#### Acceptance Criteria

1. [84-REQ-2.1] WHEN review findings are successfully inserted into
   DuckDB, THE system SHALL emit a `review.findings_persisted` audit event
   with payload containing `archetype`, `count`, `severity_summary`
   (mapping severity to count), and `spec_name`, AND return the count
   of persisted findings to the caller.

2. [84-REQ-2.2] WHEN verification verdicts are successfully inserted into
   DuckDB, THE system SHALL emit a `review.verdicts_persisted` audit event
   with payload containing `archetype`, `count`, `pass_count`,
   `fail_count`, and `spec_name`.

3. [84-REQ-2.3] WHEN drift findings are successfully inserted into DuckDB,
   THE system SHALL emit a `review.drift_persisted` audit event with
   payload containing `archetype`, `count`, `severity_summary`, and
   `spec_name`.

#### Edge Cases

1. [84-REQ-2.E1] IF the audit event emission itself fails, THEN THE system
   SHALL log a warning and continue without raising.

### Requirement 3: Enriched Blocking Reasons

**User Story:** As an operator, I want to know which specific findings
caused a skeptic to block a task so I can resolve the issue without manual
DuckDB queries.

#### Acceptance Criteria

1. [84-REQ-3.1] WHEN a skeptic blocks a task due to critical findings, THE
   system SHALL include in the blocking reason string: the count of
   critical findings, up to 3 finding IDs, and a comma-separated list of
   truncated descriptions (max 60 chars each).

2. [84-REQ-3.2] WHEN the blocking reason is rendered in `agent-fox status`,
   THE system SHALL display the enriched reason including finding IDs and
   descriptions.

#### Edge Cases

1. [84-REQ-3.E1] IF there are more than 3 critical findings, THEN THE
   system SHALL show the first 3 IDs and append "and N more".

### Requirement 4: Findings CLI Command

**User Story:** As an operator, I want to query review findings from the
command line so I can inspect what review archetypes found without manually
querying DuckDB.

#### Acceptance Criteria

1. [84-REQ-4.1] WHEN `agent-fox findings` is invoked, THE system SHALL
   query DuckDB for active (non-superseded) review findings and display
   them in a formatted table with columns: severity, archetype, spec,
   description (truncated to 80 chars), and created_at.

2. [84-REQ-4.2] WHEN `--spec NAME` is provided, THE system SHALL filter
   results to findings matching the given spec name.

3. [84-REQ-4.3] WHEN `--severity LEVEL` is provided, THE system SHALL
   filter results to findings at or above the given severity level
   (critical > major > minor > observation).

4. [84-REQ-4.4] WHEN `--archetype NAME` is provided, THE system SHALL
   filter results to the specified archetype's table (skeptic for
   review_findings, verifier for verification_results, oracle for
   drift_findings) AND return the filtered result set to the caller.

5. [84-REQ-4.5] WHEN `--run RUN_ID` is provided, THE system SHALL filter
   results to findings from sessions within the given run.

6. [84-REQ-4.6] WHEN `--json` is provided, THE system SHALL output results
   as a JSON array instead of a formatted table.

#### Edge Cases

1. [84-REQ-4.E1] IF no DuckDB database exists at the default path, THEN
   THE system SHALL print "No knowledge database found" and exit with
   code 0.

2. [84-REQ-4.E2] IF the query returns zero results, THEN THE system SHALL
   print "No findings match the given filters" and exit with code 0.

### Requirement 5: Status Findings Summary

**User Story:** As an operator, I want `agent-fox status` to surface
specs with unresolved critical or major findings so problems are visible
at a glance.

#### Acceptance Criteria

1. [84-REQ-5.1] WHEN `agent-fox status` is invoked AND the knowledge
   database exists, THE system SHALL include a "Review Findings" section
   listing each spec that has active critical or major findings, with
   counts per severity level.

2. [84-REQ-5.2] WHEN no specs have active critical or major findings, THE
   system SHALL omit the "Review Findings" section entirely.

#### Edge Cases

1. [84-REQ-5.E1] IF the knowledge database cannot be opened, THEN THE
   system SHALL omit the "Review Findings" section and log a debug message.
