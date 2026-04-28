# Requirements Document

## Introduction

This specification defines the storage, retrieval, and injection of session
summaries into the agent-fox knowledge system. Session summaries are
natural-language descriptions of what a coding session accomplished, produced
by the Claude Code SDK at session completion. This spec adds a database table
to persist these summaries, extends the knowledge provider to serve them to
downstream sessions, and enhances the audit event payload to include them.

## Glossary

- **Session summary**: A natural-language string describing what a coding
  session accomplished, extracted from `.agent-fox/session-summary.json`
  written by the Claude Code SDK.
- **Knowledge provider**: The `FoxKnowledgeProvider` class that retrieves
  stored knowledge (review findings, errata, ADRs, verdicts) and formats it
  for injection into session prompts.
- **Injection**: The process of adding formatted knowledge items to a session's
  prompt context so the LLM can act on them.
- **Task group**: A numbered unit of work within a spec (e.g., task group 3 =
  "SQLite store implementation"). Sessions are dispatched per task group.
- **Node ID**: The unique identifier for a plan node, encoding spec name, task
  group, and optional sub-role (e.g., `01_audit_hub:3`,
  `01_audit_hub:1:reviewer:audit-review`).
- **Archetype**: The role of a session — `coder`, `reviewer`, or `verifier`.
- **Attempt**: The 1-indexed retry number for a task group. Attempt 1 is the
  first try; attempt 2+ are retries after review blocking.
- **Cross-spec summary**: A summary from a different spec than the one the
  current session is working on, served for cross-spec awareness.
- **Supersession**: The process of marking older records as replaced by newer
  ones (used for review findings but NOT for summaries).

## Requirements

### Requirement 1: Summary Persistence

**User Story:** As a system operator, I want session summaries stored in the
database so that they survive beyond the log output and can be queried by
downstream sessions and analysis tools.

#### Acceptance Criteria

[119-REQ-1.1] WHEN a session completes successfully AND a session summary is
available from the session artifacts, THE system SHALL insert a row into the
`session_summaries` table containing the summary text, node ID, run ID, spec
name, task group, archetype, and attempt number.

[119-REQ-1.2] THE `session_summaries` table SHALL have columns: `id` (UUID
primary key), `node_id` (VARCHAR), `run_id` (VARCHAR), `spec_name` (VARCHAR),
`task_group` (VARCHAR), `archetype` (VARCHAR), `attempt` (INTEGER), `summary`
(TEXT), and `created_at` (TIMESTAMP).

[119-REQ-1.3] WHEN multiple attempts of the same task group complete, THE
system SHALL retain all summaries (append-only) without superseding earlier
attempts.

[119-REQ-1.4] THE system SHALL create the `session_summaries` table via a
database migration (next available version number) AND update the base schema
DDL so that fresh databases include the table.

#### Edge Cases

[119-REQ-1.E1] IF the session summary artifact is missing (file does not exist,
JSON parse error, or SDK failure), THEN THE system SHALL store no row in
`session_summaries` for that session and log a debug-level message.

[119-REQ-1.E2] IF the session status is not "completed" (e.g., failed or
timed out), THEN THE system SHALL not store a summary row for that session.

[119-REQ-1.E3] IF the `session_summaries` table does not exist (database from
an older version that has not been migrated), THEN THE system SHALL handle the
missing table gracefully without crashing AND log a warning.

### Requirement 2: Summary Retrieval and Injection

**User Story:** As a coding agent starting task group N, I want to see
summaries of what prior task groups built so I can understand the current
state of the codebase without re-reading all prior code.

#### Acceptance Criteria

[119-REQ-2.1] WHEN `FoxKnowledgeProvider.retrieve()` is called for a session
with a known spec name and task group, THE system SHALL query the
`session_summaries` table for completed coder summaries from prior task groups
(groups 1..N-1 where N is the current task group) within the same spec and
current run, AND return them formatted with the prefix `[CONTEXT]`.

[119-REQ-2.2] THE system SHALL format each injected summary as:
`[CONTEXT] (group {G}, attempt {A}) {summary_text}` where G is the task group
number and A is the attempt number.

[119-REQ-2.3] WHEN multiple attempts exist for the same task group, THE system
SHALL include only the latest attempt's summary in the injection (highest
attempt number), to avoid redundancy while preserving the full history in the
database.

[119-REQ-2.4] THE system SHALL sort injected summaries by task group number
ascending, so downstream sessions receive context in chronological build order.

[119-REQ-2.5] THE system SHALL cap same-spec summary injection at a
configurable maximum (default 5 items), applied after sorting by task group.

[119-REQ-2.6] THE system SHALL only inject summaries from coder sessions
(archetype = "coder"), not reviewer or verifier sessions.

#### Edge Cases

[119-REQ-2.E1] IF the current task group is 1 (the first group), THEN THE
system SHALL return zero same-spec summaries (there are no prior groups).

[119-REQ-2.E2] IF no coder summaries exist for prior task groups (e.g., all
prior sessions failed or produced no summary), THEN THE system SHALL return
an empty list of same-spec summaries without error.

[119-REQ-2.E3] IF the `session_summaries` table does not exist, THEN THE
system SHALL return an empty list of summaries without error AND log a
debug-level message.

### Requirement 3: Cross-Spec Summary Injection

**User Story:** As a coding agent working on spec B, I want to see summaries
of what spec A's sessions built when they modified shared files, so I can
avoid integration conflicts.

#### Acceptance Criteria

[119-REQ-3.1] WHEN `FoxKnowledgeProvider.retrieve()` is called, THE system
SHALL query the `session_summaries` table for completed coder summaries from
other specs within the current run AND return them formatted with the prefix
`[CROSS-SPEC]`.

[119-REQ-3.2] THE system SHALL format each cross-spec summary as:
`[CROSS-SPEC] ({spec_name}, group {G}) {summary_text}`.

[119-REQ-3.3] THE system SHALL cap cross-spec summary injection at a
configurable maximum (default 3 items), separate from the same-spec cap.

[119-REQ-3.4] THE system SHALL sort cross-spec summaries by `created_at`
descending (most recent first), so the latest changes from other specs are
prioritized.

[119-REQ-3.5] THE cross-spec query SHALL include only the latest attempt per
task group per spec, to avoid redundancy.

#### Edge Cases

[119-REQ-3.E1] IF no other specs have completed coder sessions in the current
run, THEN THE system SHALL return an empty list of cross-spec summaries
without error.

[119-REQ-3.E2] IF the current session has no `run_id` (e.g., standalone
session), THEN THE system SHALL skip cross-spec summary retrieval and return
an empty list.

### Requirement 4: Audit Event Enhancement

**User Story:** As a system operator reviewing audit logs, I want the session
summary included in the `session.complete` audit event so I can understand
what each session accomplished without querying the database.

#### Acceptance Criteria

[119-REQ-4.1] WHEN a `session.complete` audit event is emitted AND a session
summary is available, THE system SHALL include a `summary` field in the event
payload containing the full summary text.

[119-REQ-4.2] WHEN a `session.complete` audit event is emitted AND no session
summary is available, THE system SHALL omit the `summary` field from the
payload (not include a null or empty string).

#### Edge Cases

[119-REQ-4.E1] IF the summary text exceeds 2000 characters, THEN THE system
SHALL truncate it to 2000 characters in the audit event payload with a
trailing `...` marker, while storing the full text in the database table.

### Requirement 5: Summary Ingestion Wiring

**User Story:** As a developer maintaining the engine, I want the summary
storage to integrate cleanly with the existing session lifecycle and knowledge
provider infrastructure.

#### Acceptance Criteria

[119-REQ-5.1] WHEN `_ingest_knowledge()` is called after a successful session,
THE system SHALL pass the session summary string to the knowledge provider's
`ingest()` method via the context dictionary under the key `"summary"`.

[119-REQ-5.2] WHEN the knowledge provider's `ingest()` method receives a
non-None summary in the context, THE system SHALL insert it into the
`session_summaries` table AND return control to the caller.

[119-REQ-5.3] WHEN `_read_session_artifacts()` returns a summary, THE system
SHALL make that summary available to both the audit event emission and the
knowledge ingestion call, so both paths receive the same summary text.

#### Edge Cases

[119-REQ-5.E1] IF the database connection fails during summary insertion, THEN
THE system SHALL log a warning and continue without crashing the session
lifecycle.
