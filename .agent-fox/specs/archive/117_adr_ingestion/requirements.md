# Requirements Document

## Introduction

This document specifies the requirements for ingesting Architecture Decision
Records (ADRs) into the agent-fox knowledge system. After each coding session,
the system detects new or modified ADR files, validates them against the MADR
format, stores valid entries in DuckDB, and retrieves relevant ADR summaries
to guide future sessions.

## Glossary

- **ADR**: Architecture Decision Record — a structured document capturing an
  architectural decision, its context, considered alternatives, and rationale.
- **MADR**: Markdown Architectural Decision Records — a specific ADR template
  format (version 4.0.0) with mandatory sections: Context and Problem
  Statement, Considered Options, and Decision Outcome.
- **Ingestion**: The process of parsing, validating, and storing an ADR file
  into the knowledge database.
- **Supersession**: Replacing an existing database entry with a newer version
  when the source file has been modified (detected via content hash change).
- **Content hash**: SHA-256 digest of the ADR file content, used to detect
  modifications and prevent redundant re-ingestion.
- **Spec reference**: A reference to a specification number or name extracted
  from ADR content, used for matching ADRs to coding sessions.
- **Keyword**: A significant word extracted from the ADR title, used for
  topic-based matching during retrieval.

## Requirements

### Requirement 1: ADR Detection

**User Story:** As a project maintainer, I want the system to detect when a
coding session creates or modifies an ADR file, so that architectural decisions
are automatically captured.

#### Acceptance Criteria

1. [117-REQ-1.1] WHEN a coding session completes and `touched_files` is
   available, THE system SHALL filter the list for paths matching
   `docs/adr/*.md` (files directly under `docs/adr/`, not in subdirectories)
   AND return the matching paths to the caller for ADR processing.
2. [117-REQ-1.2] WHEN no paths in `touched_files` match `docs/adr/*.md`,
   THE system SHALL return an empty list AND skip all ADR processing.
3. [117-REQ-1.3] WHEN a matching path refers to a file that no longer exists
   on disk (e.g., deleted ADR), THE system SHALL skip that path AND log a
   DEBUG message.

#### Edge Cases

1. [117-REQ-1.E1] IF `touched_files` is empty or None, THEN THE system
   SHALL return an empty list without error.
2. [117-REQ-1.E2] IF a path in `touched_files` matches `docs/adr/*.md` but
   uses a non-`.md` extension variant (e.g., `.markdown`), THEN THE system
   SHALL exclude it.

### Requirement 2: MADR Parsing

**User Story:** As a project maintainer, I want ADR files parsed into a
structured representation, so that their content can be validated and stored.

#### Acceptance Criteria

1. [117-REQ-2.1] WHEN given the text content of an ADR file, THE system SHALL
   extract the title (first H1 heading), status, considered options list,
   chosen option, and justification AND return them as a structured ADREntry
   to the caller.
2. [117-REQ-2.2] WHEN the ADR file contains YAML frontmatter with a `status`
   field, THE system SHALL use that value as the ADR status.
3. [117-REQ-2.3] WHEN the ADR file has no YAML frontmatter but contains a
   `## Status` section, THE system SHALL extract the status from the first
   non-empty line of that section's body.
4. [117-REQ-2.4] WHEN neither YAML frontmatter nor a `## Status` section is
   present, THE system SHALL default the status to `"proposed"`.
5. [117-REQ-2.5] WHEN the `## Considered Options` section (or accepted
   synonym) contains a bullet list, THE system SHALL extract each bullet item
   as a considered option string. Accepted synonyms for the section heading
   are: `Considered Options`, `Options Considered`, `Considered Alternatives`.
6. [117-REQ-2.6] WHEN the `## Decision Outcome` section (or accepted synonym
   `Decision`) contains a `Chosen option:` line or starts with
   `Chosen option:`, THE system SHALL extract the chosen option name and the
   justification text that follows the `because` keyword AND return both to
   the caller.

#### Edge Cases

1. [117-REQ-2.E1] IF the content has no H1 heading, THEN THE system SHALL
   return None (parse failure).
2. [117-REQ-2.E2] IF the content cannot be decoded as UTF-8, THEN THE system
   SHALL return None AND log a WARNING.

### Requirement 3: MADR Validation

**User Story:** As a project maintainer, I want the system to validate that
ADR files follow MADR format with at least 3 considered options, so that
architectural decisions meet quality standards.

#### Acceptance Criteria

1. [117-REQ-3.1] WHEN an ADREntry is validated, THE system SHALL check for the
   presence of all mandatory MADR sections: a context section (heading matching
   `Context and Problem Statement` or `Context`), a considered options section
   (heading matching `Considered Options`, `Options Considered`, or
   `Considered Alternatives`), and a decision outcome section (heading matching
   `Decision Outcome` or `Decision`) AND return a validation result indicating
   pass or fail with a list of diagnostic messages.
2. [117-REQ-3.2] WHEN the considered options list contains fewer than 3 items,
   THE system SHALL mark the validation as failed AND include a diagnostic
   message stating the count and the minimum required.
3. [117-REQ-3.3] WHEN the chosen option is empty or missing, THE system SHALL
   mark the validation as failed AND include a diagnostic message.
4. [117-REQ-3.4] WHEN validation passes, THE system SHALL return
   `passed=True` with an empty diagnostics list.

#### Edge Cases

1. [117-REQ-3.E1] IF the ADREntry has a None or empty title, THEN THE system
   SHALL mark the validation as failed.

### Requirement 4: ADR Storage

**User Story:** As a project maintainer, I want validated ADR files stored in
the knowledge database with structured metadata, so that they can be queried
and used in future sessions.

#### Acceptance Criteria

1. [117-REQ-4.1] WHEN a validated ADREntry is stored, THE system SHALL insert
   a row into the `adr_entries` DuckDB table with: id, file_path, title,
   status, chosen_option, considered_options (as TEXT[]), summary, content_hash,
   keywords (as TEXT[]), spec_refs (as TEXT[]), and created_at timestamp.
2. [117-REQ-4.2] THE system SHALL compute the content_hash as the hex-encoded
   SHA-256 digest of the raw file content (UTF-8 bytes).
3. [117-REQ-4.3] WHEN a DuckDB migration is applied, THE system SHALL create
   the `adr_entries` table with the schema defined in the design document AND
   register the migration in the migrations registry.
4. [117-REQ-4.4] WHEN the `adr_entries` table does not exist (e.g., migration
   not yet applied), THE system SHALL log a DEBUG message AND return without
   error.

#### Edge Cases

1. [117-REQ-4.E1] IF the database connection is unavailable, THEN THE system
   SHALL log a WARNING AND return 0 rows inserted.
2. [117-REQ-4.E2] IF a row with the same file_path and content_hash already
   exists (duplicate ingestion), THEN THE system SHALL skip insertion AND
   return 0.

### Requirement 5: ADR Supersession

**User Story:** As a project maintainer, I want modified ADR files to supersede
their previous database entries, so that sessions always see the latest
architectural decisions.

#### Acceptance Criteria

1. [117-REQ-5.1] WHEN ingesting an ADR file whose file_path already has an
   active entry (superseded_at IS NULL) in the database with a different
   content_hash, THE system SHALL set `superseded_at` on the existing entry
   to the current UTC timestamp AND insert the new entry.
2. [117-REQ-5.2] WHEN ingesting an ADR file whose file_path already has an
   active entry with the same content_hash, THE system SHALL skip ingestion
   AND return the existing entry unchanged.
3. [117-REQ-5.3] THE system SHALL never delete superseded entries — they
   remain in the database for historical reference with a non-NULL
   `superseded_at` value.

#### Edge Cases

1. [117-REQ-5.E1] IF the file_path has only superseded entries (all have
   non-NULL `superseded_at`) and no active entry, THEN THE system SHALL
   insert the new entry as active (superseded_at IS NULL).

### Requirement 6: ADR Retrieval and Prompt Injection

**User Story:** As a coding agent, I want relevant ADRs included in my session
context based on spec and topic matching, so that my implementation respects
established architectural decisions.

#### Acceptance Criteria

1. [117-REQ-6.1] WHEN retrieving knowledge for a session, THE system SHALL
   query active ADR entries (superseded_at IS NULL) that match the current
   spec_name via spec_refs OR have keyword overlap with the task_description
   AND return the matching entries to the caller.
2. [117-REQ-6.2] WHEN formatting an ADR for prompt injection, THE system SHALL
   produce a string in the format:
   `[ADR] {title}: Chose "{chosen_option}" over {other_options}. {justification}`
   AND return the formatted strings as a list to the caller.
3. [117-REQ-6.3] WHEN the FoxKnowledgeProvider retrieves knowledge, THE system
   SHALL include ADR results alongside review findings and errata in the
   returned list, capped at `max_items` total.
4. [117-REQ-6.4] THE system SHALL extract spec references from ADR content at
   ingestion time using patterns: `(\d+)-REQ-` (requirement references),
   `spec[_\s]+(\d+)` (prose references), and `(\d{1,3}_[a-z][a-z_]+)` (spec
   folder names) AND store the extracted spec identifiers in the `spec_refs`
   column.
5. [117-REQ-6.5] THE system SHALL extract keywords from the ADR title at
   ingestion time by splitting on whitespace and hyphens, lowercasing,
   filtering words shorter than 3 characters and common stop words, AND
   storing the result in the `keywords` column.

#### Edge Cases

1. [117-REQ-6.E1] IF the `adr_entries` table does not exist, THEN THE system
   SHALL return an empty list without error.
2. [117-REQ-6.E2] IF no ADRs match the spec_name or task_description, THEN
   THE system SHALL return an empty list.

### Requirement 7: Validation Warnings

**User Story:** As a project maintainer, I want the system to emit warnings
when ADR validation fails, so that I can address format issues without
disrupting the pipeline.

#### Acceptance Criteria

1. [117-REQ-7.1] WHEN an ADR file fails MADR validation, THE system SHALL log
   a WARNING message containing the file path and the list of diagnostic
   messages from the validation result.
2. [117-REQ-7.2] WHEN an ADR file fails MADR validation, THE system SHALL emit
   an audit event of type `ADR_VALIDATION_FAILED` with severity WARNING,
   including the file path and diagnostics in the payload.
3. [117-REQ-7.3] WHEN an ADR file fails validation, THE system SHALL NOT
   ingest it into the database AND SHALL NOT block the session or pipeline.
4. [117-REQ-7.4] WHEN an ADR file passes validation and is successfully
   ingested, THE system SHALL emit an audit event of type `ADR_INGESTED`
   with severity INFO, including the file path, title, and number of
   considered options in the payload.

#### Edge Cases

1. [117-REQ-7.E1] IF the audit event emission fails (e.g., sink unavailable),
   THEN THE system SHALL log a DEBUG message AND continue without error.
