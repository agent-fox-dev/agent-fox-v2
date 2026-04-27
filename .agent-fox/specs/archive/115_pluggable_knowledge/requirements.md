# Requirements Document

## Introduction

This specification defines the requirements for a pluggable knowledge provider
that implements the `KnowledgeProvider` protocol defined in spec 114. The
provider stores and retrieves scoped, high-signal knowledge — gotchas, review
carry-forward, and errata pointers — behind a clean interface.

## Glossary

- **KnowledgeProvider**: Protocol defined in spec 114 with `ingest()` and
  `retrieve()` methods. This spec implements it.
- **Gotcha**: A surprising or non-obvious finding from a coding session.
  Something that looks like it should work but doesn't, or a hidden constraint
  that caused unexpected behavior.
- **Review finding**: A finding from a reviewer session stored in
  `review_findings` table. This spec reads them at retrieval time; it does not
  create them.
- **Errata**: A documented divergence between a spec and its implementation.
  Stored as `(spec_name, file_path)` pairs pointing to errata documents in
  `docs/errata/`.
- **Scoped retrieval**: Retrieval filtered by `spec_name` rather than by vector
  similarity across the entire knowledge base.
- **Gotcha TTL**: Time-to-live in days. Gotchas older than this are excluded
  from retrieval.
- **Content hash**: SHA-256 of normalized gotcha text, used for deduplication.
- **Model tier**: LLM model class. SIMPLE = Haiku-class. STANDARD = Sonnet-class.

## Requirements

### Requirement 1: FoxKnowledgeProvider Class

**User Story:** As a system operator, I want a concrete knowledge provider that
stores and retrieves scoped knowledge, so that agents benefit from past session
learnings.

#### Acceptance Criteria

[115-REQ-1.1] THE `FoxKnowledgeProvider` class SHALL implement the
`KnowledgeProvider` protocol defined in spec 114.

[115-REQ-1.2] WHEN `isinstance(FoxKnowledgeProvider(...), KnowledgeProvider)`
is called, THE system SHALL return `True`.

[115-REQ-1.3] THE `FoxKnowledgeProvider` constructor SHALL accept a
`KnowledgeDB` connection and a `KnowledgeProviderConfig` configuration object.

#### Edge Cases

[115-REQ-1.E1] IF the `KnowledgeDB` connection is closed when a method is
called, THEN THE system SHALL raise a descriptive error rather than a generic
DuckDB error.

### Requirement 2: Gotcha Ingestion

**User Story:** As a coding agent, I want surprising findings from my session
to be captured, so that future sessions for the same spec can benefit from my
experience.

#### Acceptance Criteria

[115-REQ-2.1] WHEN `ingest()` is called after a session, THE system SHALL
prompt an LLM with the session context and ask "What was surprising or
non-obvious? What would you want to know if starting a new session on this
spec?" AND store 0-3 gotcha candidates returned by the LLM.

[115-REQ-2.2] THE gotcha extraction prompt SHALL use the SIMPLE model tier.

[115-REQ-2.3] WHEN the LLM returns zero gotcha candidates, THE system SHALL
store nothing and return without error.

[115-REQ-2.4] EACH stored gotcha SHALL include: `spec_name`, `category`
(literal `"gotcha"`), `text` (the gotcha content), `content_hash` (SHA-256 of
normalized text), `session_id` (originating session), and `created_at`
(UTC timestamp).

[115-REQ-2.5] WHEN `ingest()` is called with a context where
`session_status` is not `"completed"`, THE system SHALL skip gotcha extraction
and return immediately.

#### Edge Cases

[115-REQ-2.E1] IF a gotcha with the same `content_hash` already exists for the
same `spec_name`, THEN THE system SHALL skip that gotcha without error.

[115-REQ-2.E2] IF the LLM call for gotcha extraction fails, THEN THE system
SHALL log a WARNING and return without storing any gotchas.

[115-REQ-2.E3] IF the LLM returns more than 3 gotcha candidates, THEN THE
system SHALL store only the first 3.

### Requirement 3: Gotcha Retrieval

**User Story:** As a coding agent starting a new session, I want to see gotchas
from prior sessions on the same spec, so that I avoid repeating mistakes.

#### Acceptance Criteria

[115-REQ-3.1] WHEN `retrieve()` is called, THE system SHALL query gotchas
filtered by `spec_name` and ordered by `created_at` descending (most recent
first).

[115-REQ-3.2] THE system SHALL exclude gotchas whose `created_at` is older
than `gotcha_ttl_days` from the configured TTL.

[115-REQ-3.3] THE system SHALL return at most 5 gotchas per retrieval call.

[115-REQ-3.4] EACH returned gotcha string SHALL be prefixed with `[GOTCHA] `.

#### Edge Cases

[115-REQ-3.E1] IF no gotchas exist for the given `spec_name`, THEN THE system
SHALL return an empty contribution from the gotcha category (other categories
may still contribute items).

### Requirement 4: Review Carry-Forward

**User Story:** As a coding agent, I want to see unresolved critical and major
review findings from prior sessions on my spec, so that I address known issues.

#### Acceptance Criteria

[115-REQ-4.1] WHEN `retrieve()` is called, THE system SHALL query the existing
`review_findings` table for findings matching the given `spec_name` with
severity `critical` or `major` and status `open` or `in_progress`.

[115-REQ-4.2] THE system SHALL include all matching review findings in the
retrieval result, not subject to the gotcha limit.

[115-REQ-4.3] EACH returned review finding string SHALL be prefixed with
`[REVIEW] ` and include the finding's severity, category, and description.

#### Edge Cases

[115-REQ-4.E1] IF no unresolved critical/major findings exist for the spec,
THEN THE system SHALL return an empty contribution from the review category.

[115-REQ-4.E2] IF the `review_findings` table does not exist (fresh database),
THEN THE system SHALL return an empty contribution without error.

### Requirement 5: Errata Index

**User Story:** As a coding agent, I want to see errata pointers for my spec,
so that I know where the implementation intentionally diverges from the spec.

#### Acceptance Criteria

[115-REQ-5.1] THE system SHALL store errata entries as `(spec_name, file_path)`
pairs in an `errata_index` table, where `file_path` points to an errata
document in `docs/errata/`.

[115-REQ-5.2] WHEN `retrieve()` is called, THE system SHALL query the
`errata_index` table for entries matching the given `spec_name`.

[115-REQ-5.3] EACH returned errata string SHALL be prefixed with `[ERRATA] `
and include the file path.

[115-REQ-5.4] THE system SHALL provide a function to register and unregister
errata entries, callable from CLI or programmatically, AND return the
registered entry to the caller.

#### Edge Cases

[115-REQ-5.E1] IF no errata entries exist for the spec, THEN THE system SHALL
return an empty contribution from the errata category.

[115-REQ-5.E2] IF an errata entry references a file that does not exist on
disk, THEN THE system SHALL still return the entry (the file may exist in a
different worktree or branch).

### Requirement 6: Retrieval Composition and Caps

**User Story:** As a system operator, I want total retrieval results capped at
a reasonable number, so that agent context is not flooded with knowledge items.

#### Acceptance Criteria

[115-REQ-6.1] WHEN `retrieve()` is called, THE system SHALL return at most
`max_items` total items (default 10) across all categories.

[115-REQ-6.2] WHEN the total across categories exceeds `max_items`, THE system
SHALL trim gotchas first (review findings and errata take priority).

[115-REQ-6.3] THE system SHALL return items in category order: errata first,
then review findings, then gotchas.

#### Edge Cases

[115-REQ-6.E1] IF all categories are empty, THEN THE system SHALL return an
empty list.

[115-REQ-6.E2] IF review findings and errata alone exceed `max_items`, THEN
THE system SHALL return all review findings and errata (no gotchas) even if
the total exceeds `max_items`.

### Requirement 7: Gotcha Expiry

**User Story:** As a system operator, I want old gotchas to expire
automatically, so that the knowledge base does not grow without bound.

#### Acceptance Criteria

[115-REQ-7.1] THE system SHALL exclude gotchas older than `gotcha_ttl_days`
(default 90) from retrieval results.

[115-REQ-7.2] THE system SHALL NOT delete expired gotchas from the database;
they are excluded from queries only.

#### Edge Cases

[115-REQ-7.E1] IF `gotcha_ttl_days` is set to 0, THEN THE system SHALL
exclude all gotchas from retrieval (TTL of 0 means immediate expiry).

### Requirement 8: Configuration

**User Story:** As a system operator, I want the knowledge provider to be
configurable, so that I can tune retrieval limits and gotcha behavior.

#### Acceptance Criteria

[115-REQ-8.1] THE system SHALL define a `KnowledgeProviderConfig` class with
fields: `max_items` (int, default 10), `gotcha_ttl_days` (int, default 90),
`model_tier` (str, default "SIMPLE").

[115-REQ-8.2] THE `KnowledgeProviderConfig` SHALL be a nested field in the
existing `KnowledgeConfig` class.

[115-REQ-8.3] THE `KnowledgeProviderConfig` SHALL use
`ConfigDict(extra="ignore")` for forward compatibility.

### Requirement 9: Schema Migration

**User Story:** As a system operator, I want new tables created automatically,
so that the knowledge provider works on both fresh and existing databases.

#### Acceptance Criteria

[115-REQ-9.1] THE system SHALL create a `gotchas` table with columns:
`id` (VARCHAR PRIMARY KEY), `spec_name` (VARCHAR NOT NULL),
`category` (VARCHAR NOT NULL DEFAULT 'gotcha'), `text` (VARCHAR NOT NULL),
`content_hash` (VARCHAR NOT NULL), `session_id` (VARCHAR NOT NULL),
`created_at` (TIMESTAMP NOT NULL).

[115-REQ-9.2] THE system SHALL create an `errata_index` table with columns:
`spec_name` (VARCHAR NOT NULL), `file_path` (VARCHAR NOT NULL),
`created_at` (TIMESTAMP NOT NULL), with a composite primary key on
`(spec_name, file_path)`.

[115-REQ-9.3] THE tables SHALL be created via the existing migration framework
in `knowledge/migrations.py`.

[115-REQ-9.4] WHEN the database already contains these tables (idempotent
migration), THE system SHALL not error.

### Requirement 10: Provider Registration

**User Story:** As a developer, I want the knowledge provider registered at
startup, so that the engine uses the correct provider without hardcoding.

#### Acceptance Criteria

[115-REQ-10.1] WHEN the engine starts, THE system SHALL construct a
`FoxKnowledgeProvider` using the configured `KnowledgeDB` and
`KnowledgeProviderConfig`, and pass it as the engine's `KnowledgeProvider`.

[115-REQ-10.2] THE `FoxKnowledgeProvider` SHALL replace the
`NoOpKnowledgeProvider` as the default provider.

[115-REQ-10.3] THE engine SHALL NOT import any module from
`agent_fox/knowledge/` other than `provider.py`, `db.py`, `review_store.py`,
`audit.py`, `sink.py`, `duckdb_sink.py`, `blocking_history.py`,
`agent_trace.py`, and `migrations.py` — the boundary established in spec 114.
