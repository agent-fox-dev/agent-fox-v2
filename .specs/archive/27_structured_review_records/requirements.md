# Requirements Document

## Introduction

This specification defines structured knowledge records for Skeptic and
Verifier agent output. Instead of writing markdown files (`review.md`,
`verification.md`), these agents produce structured JSON that is ingested into
DuckDB tables. Context rendering, convergence, and GitHub issue filing all
operate on DB records rather than files.

## Glossary

- **Finding** — A single Skeptic review observation with a severity level and
  description. Stored in the `review_findings` table.
- **Verdict** — A single Verifier per-requirement assessment with a PASS/FAIL
  status and evidence. Stored in the `verification_results` table.
- **Supersession** — The process by which a re-run's records replace previous
  records for the same spec/task-group, preserving history via causal links.
- **Structured output** — A JSON block emitted by an agent in a well-defined
  schema, parsed by the session runner after agent completion.
- **Context rendering** — The process of querying DB records and formatting
  them as markdown for inclusion in a Coder agent's system prompt.
- **Convergence** — Multi-instance post-processing that merges or votes on
  findings/verdicts from parallel agent runs.
- **Block threshold** — The number of majority-agreed critical findings above
  which a Skeptic review blocks implementation.

## Requirements

### Requirement 1: Review Findings Schema

**User Story:** As a system operator, I want Skeptic findings stored as
structured records in DuckDB, so that they are queryable, linkable, and
lifecycle-managed.

#### Acceptance Criteria

1. [27-REQ-1.1] WHEN the knowledge store is opened, THE system SHALL ensure a
   `review_findings` table exists with columns: `id` (UUID PK), `severity`
   (TEXT), `description` (TEXT), `requirement_ref` (TEXT nullable),
   `spec_name` (TEXT), `task_group` (TEXT), `session_id` (TEXT),
   `superseded_by` (UUID nullable), `created_at` (TIMESTAMP).

2. [27-REQ-1.2] THE `review_findings` table SHALL be created idempotently via
   a schema migration that increments the schema version.

#### Edge Cases

1. [27-REQ-1.E1] IF the schema migration fails, THEN THE system SHALL log the
   error and raise a `KnowledgeStoreError`.

### Requirement 2: Verification Results Schema

**User Story:** As a system operator, I want Verifier verdicts stored as
structured records in DuckDB, so that they are queryable and support
majority-vote convergence.

#### Acceptance Criteria

1. [27-REQ-2.1] WHEN the knowledge store is opened, THE system SHALL ensure a
   `verification_results` table exists with columns: `id` (UUID PK),
   `requirement_id` (TEXT), `verdict` (TEXT), `evidence` (TEXT nullable),
   `spec_name` (TEXT), `task_group` (TEXT), `session_id` (TEXT),
   `superseded_by` (UUID nullable), `created_at` (TIMESTAMP).

2. [27-REQ-2.2] THE `verification_results` table SHALL be created idempotently
   via the same schema migration as `review_findings`.

#### Edge Cases

1. [27-REQ-2.E1] IF the schema migration has already been applied, THEN THE
   system SHALL skip migration without error.

### Requirement 3: Structured Agent Output Parsing

**User Story:** As a session runner, I want to parse structured JSON from
Skeptic/Verifier agent output, so that findings and verdicts are ingested
into DuckDB automatically.

#### Acceptance Criteria

1. [27-REQ-3.1] WHEN a Skeptic session completes, THE system SHALL extract
   all JSON blocks matching the review-finding schema from the agent's final
   response and insert them into the `review_findings` table.

2. [27-REQ-3.2] WHEN a Verifier session completes, THE system SHALL extract
   all JSON blocks matching the verification-result schema from the agent's
   final response and insert them into the `verification_results` table.

3. [27-REQ-3.3] THE system SHALL validate each extracted JSON block against
   the expected schema and discard blocks that do not conform, logging a
   warning for each discarded block.

#### Edge Cases

1. [27-REQ-3.E1] IF the agent's response contains no valid JSON blocks, THEN
   THE system SHALL log a warning and insert zero records.

2. [27-REQ-3.E2] IF a JSON block contains an unknown severity value, THEN THE
   system SHALL normalize it to "observation" and log a warning.

### Requirement 4: Supersession Lifecycle

**User Story:** As a system operator, I want re-runs to supersede previous
findings/verdicts, so that only the latest state is surfaced while full
history is preserved.

#### Acceptance Criteria

1. [27-REQ-4.1] WHEN new findings are ingested for a (spec_name, task_group) pair that already has active findings, THE system SHALL set `superseded_by` on all existing active findings to the session_id of the new run.

2. [27-REQ-4.2] WHEN new verdicts are ingested for a (spec_name, task_group) pair that already has active verdicts, THE system SHALL set `superseded_by` on all existing active verdicts.

3. [27-REQ-4.3] THE system SHALL insert a causal link from each superseded
   record to its superseding record.

#### Edge Cases

1. [27-REQ-4.E1] IF there are no existing records to supersede, THEN THE
   system SHALL insert the new records without modifying any prior records.

### Requirement 5: Context Rendering from DB

**User Story:** As a Coder agent, I want review findings and verification
results rendered into my context from live DB queries, so that I always see
the latest state without relying on stale files.

#### Acceptance Criteria

1. [27-REQ-5.1] WHEN building a system prompt for a Coder session, THE system SHALL query the `review_findings` table for active (non-superseded) findings matching the spec_name and render them as a `## Skeptic Review` markdown section.

2. [27-REQ-5.2] WHEN building a system prompt for a Coder session, THE system SHALL query the `verification_results` table for active (non-superseded) verdicts matching the spec_name and render them as a `## Verification Report` markdown section.

3. [27-REQ-5.3] THE rendered markdown SHALL match the format previously
   produced by the Skeptic/Verifier templates (severity-grouped findings,
   requirement-keyed verdict table) so that Coder agents experience no
   change in context structure.

#### Edge Cases

1. [27-REQ-5.E1] IF the knowledge store is unavailable, THEN THE system SHALL
   fall back to reading `review.md` and `verification.md` files if they exist.

2. [27-REQ-5.E2] IF no active findings or verdicts exist for the spec, THEN
   THE system SHALL omit the corresponding section from the prompt.

### Requirement 6: Convergence on DB Records

**User Story:** As a session orchestrator, I want multi-instance convergence
to operate on DB records, so that the parsing layer is eliminated.

#### Acceptance Criteria

1. [27-REQ-6.1] WHEN converging Skeptic results from multiple instances, THE system SHALL query `review_findings` for each instance's session_id and apply the existing union-dedup-majority-gate algorithm.

2. [27-REQ-6.2] WHEN converging Verifier results from multiple instances, THE system SHALL query `verification_results` for each instance's session_id and apply majority-vote.

3. [27-REQ-6.3] THE convergence result SHALL be written back to the DB as a
   new set of records with a convergence session_id, superseding the
   per-instance records.

#### Edge Cases

1. [27-REQ-6.E1] IF only one instance ran, THEN THE system SHALL skip
   convergence and use the single instance's records directly.

### Requirement 7: GitHub Issue Sourcing from DB

**User Story:** As a system operator, I want GitHub issues filed from DB
records, so that there is a single source of truth for findings.

#### Acceptance Criteria

1. [27-REQ-7.1] WHEN filing a GitHub issue for blocking findings, THE system SHALL query `review_findings` for active critical findings and format the issue body from those records.

2. [27-REQ-7.2] WHEN a re-run produces no critical findings, THE system SHALL
   close the existing GitHub issue if `close_if_empty` is set.

#### Edge Cases

1. [27-REQ-7.E1] IF the knowledge store is unavailable, THEN THE system SHALL
   fall back to the existing behavior (no issue filed, warning logged).

### Requirement 8: Skeptic Template Update

**User Story:** As a Skeptic agent, I want clear instructions to output
structured JSON, so that my findings are automatically ingested.

#### Acceptance Criteria

1. [27-REQ-8.1] THE Skeptic template SHALL instruct the agent to output
   findings as a JSON array with objects containing `severity`, `description`,
   and optional `requirement_ref` fields.

2. [27-REQ-8.2] THE Skeptic template SHALL retain the read-only constraint
   and severity classification guidance from the current template.

#### Edge Cases

1. [27-REQ-8.E1] IF the agent also writes a `review.md` file, THEN THE system
   SHALL prefer the structured JSON output over the file.

### Requirement 9: Verifier Template Update

**User Story:** As a Verifier agent, I want clear instructions to output
structured JSON, so that my verdicts are automatically ingested.

#### Acceptance Criteria

1. [27-REQ-9.1] THE Verifier template SHALL instruct the agent to output
   verdicts as a JSON array with objects containing `requirement_id`, `verdict`,
   and optional `evidence` fields.

2. [27-REQ-9.2] THE Verifier template SHALL retain the verification process
   guidance and PASS/FAIL criteria from the current template.

#### Edge Cases

1. [27-REQ-9.E1] IF the agent also writes a `verification.md` file, THEN THE
   system SHALL prefer the structured JSON output over the file.

### Requirement 10: Backward Compatibility

**User Story:** As a system operator, I want existing markdown files migrated
into DuckDB on first run, so that historical review data is not lost.

#### Acceptance Criteria

1. [27-REQ-10.1] WHEN the system detects a `review.md` file in a spec directory and no corresponding DB records exist, THE system SHALL parse the file and ingest findings into `review_findings`.

2. [27-REQ-10.2] WHEN the system detects a `verification.md` file in a spec directory and no corresponding DB records exist, THE system SHALL parse the file and ingest verdicts into `verification_results`.

#### Edge Cases

1. [27-REQ-10.E1] IF parsing of a legacy markdown file fails, THEN THE system
   SHALL log a warning and skip the file without blocking session startup.
