# Requirements Document

## Introduction

This specification fixes the knowledge harvest pipeline so that session-derived
facts and causal links flow into the knowledge graph after every successful
coder session. It addresses the root cause of the empty knowledge.duckdb
observed in the parking-fee-service run (2026-03-17): fact extraction silently
skips when the `.session-summary.json` artifact is absent, and causal link
extraction is never reached because it depends on fact extraction running first.

## Glossary

- **Fact**: A structured learning (1-2 sentences) extracted from a session
  transcript, categorized as gotcha, pattern, decision, convention,
  anti_pattern, or fragile_area. Stored in the `memory_facts` DuckDB table.
- **Causal link**: A directed edge in the `fact_causes` table connecting a
  cause fact to an effect fact. Represents a relationship where one learning
  led to or influenced another.
- **Knowledge harvest**: The process of extracting facts and causal links from
  a completed session and storing them in DuckDB.
- **Session summary text**: The `"summary"` field from `.session-summary.json`,
  produced by the coder session. Used as input to the fact extraction LLM.
- **Fallback input**: A structured text block (spec name, task group, node ID,
  commit diff) constructed when `.session-summary.json` is absent.
- **Causal context limit**: The maximum number of prior facts included in the
  causal extraction prompt. Default: 200. Configurable via
  `causal_context_limit` in `[orchestrator]`.
- **Non-superseded fact**: A fact whose `superseded_by` column is NULL — it has
  not been replaced by a newer fact.
- **Embedding**: A dense vector representation of a fact's content, stored in
  `memory_embeddings` and used for similarity search.
- **Audit event**: A structured record emitted to the sink dispatcher for
  observability. Stored in the `audit_events` DuckDB table.

## Requirements

### Requirement 1: Fact Extraction Trigger

**User Story:** As an operator, I want facts extracted from every successful
coder session, so that the knowledge graph accumulates learnings across
sessions.

#### Acceptance Criteria

1. [52-REQ-1.1] WHEN a coder session completes with status `"completed"`,
   THE engine SHALL call `extract_and_store_knowledge()` with the session
   summary text from `.session-summary.json`.

2. [52-REQ-1.2] IF the `.session-summary.json` file is absent or its
   `"summary"` field is empty, THEN THE engine SHALL construct a fallback input
   containing the session's spec name, task group, node ID, and commit diff
   (`git diff` of the session's commits), and pass it to
   `extract_and_store_knowledge()`.

3. [52-REQ-1.3] WHEN `extract_and_store_knowledge()` raises an exception,
   THE engine SHALL log the error at warning severity and continue — the
   session SHALL NOT be marked as failed.

#### Edge Cases

1. [52-REQ-1.E1] IF the session has no commits (empty commit diff), THEN THE
   fallback input SHALL still include spec name, task group, and node ID. The
   commit diff section SHALL be omitted.

2. [52-REQ-1.E2] IF the session status is not `"completed"` (e.g., failed or
   timed out), THE engine SHALL NOT invoke fact extraction.

### Requirement 2: Fact Storage

**User Story:** As an operator, I want extracted facts stored with full
provenance metadata, so that I can trace each learning back to its source
session.

#### Acceptance Criteria

1. [52-REQ-2.1] WHEN facts are extracted, THE engine SHALL insert each fact
   into `memory_facts` with `category`, `confidence`, `spec_name`,
   `session_id`, and `commit_sha` populated. No field except `supersedes`
   SHALL be NULL.

2. [52-REQ-2.2] THE engine SHALL use `INSERT OR IGNORE` semantics for fact
   insertion so that duplicate facts (same UUID) are silently skipped.

#### Edge Cases

1. [52-REQ-2.E1] IF the LLM returns a fact with an invalid category (not in
   the `Category` enum), THEN THE engine SHALL skip that fact and log a
   warning.

### Requirement 3: Embedding Generation

**User Story:** As an operator, I want embeddings generated for every new fact,
so that similarity search and causal context ranking work correctly.

#### Acceptance Criteria

1. [52-REQ-3.1] WHEN facts are inserted into `memory_facts`, THE engine SHALL
   generate embeddings for each new fact and store them in
   `memory_embeddings`.

2. [52-REQ-3.2] IF embedding generation fails for a fact, THEN THE engine
   SHALL log the failure at warning severity. Fact storage SHALL NOT be
   blocked — the fact remains in `memory_facts` without an embedding.

#### Edge Cases

1. [52-REQ-3.E1] IF the embedding model is unavailable (network error or model
   not found), THEN THE engine SHALL log one warning per batch and skip
   embedding generation for all facts in the batch.

### Requirement 4: Harvest Audit Events

**User Story:** As an operator, I want audit events emitted for every harvest
outcome, so that I can diagnose extraction failures.

#### Acceptance Criteria

1. [52-REQ-4.1] WHEN extraction succeeds with >= 1 fact, THE engine SHALL emit
   a `harvest.complete` audit event with payload containing: `fact_count`
   (integer), `categories` (list of strings), and `causal_link_count`
   (integer).

2. [52-REQ-4.2] WHEN extraction produces zero facts from a non-empty input
   (length > 0), THE engine SHALL emit a warning-severity `harvest.empty`
   audit event to flag potential extraction prompt degradation.

#### Edge Cases

1. [52-REQ-4.E1] IF the sink dispatcher is None or `run_id` is empty, THEN
   THE engine SHALL skip audit event emission without error.

### Requirement 5: Causal Link Extraction Trigger

**User Story:** As an operator, I want causal links extracted after every
successful fact extraction, so that the causal graph stays connected across
sessions.

#### Acceptance Criteria

1. [52-REQ-5.1] WHEN fact extraction produces >= 1 new fact AND the total
   non-superseded fact count in `memory_facts` is >= 5, THE engine SHALL
   invoke `_extract_causal_links()`.

2. [52-REQ-5.2] WHEN the total non-superseded fact count is < 5, THE engine
   SHALL skip causal link extraction and log a debug-level message:
   `"Skipping causal extraction: insufficient facts ({count} < 5)"`.

#### Edge Cases

1. [52-REQ-5.E1] IF fact extraction produced >= 1 fact but embedding generation
   failed for all facts, THE engine SHALL still attempt causal link extraction
   (causal extraction does not require embeddings when fact count <=
   `causal_context_limit`).

### Requirement 6: Causal Context Window

**User Story:** As an operator, I want the causal extraction prompt to include
relevant prior facts without exceeding the model's context window.

#### Acceptance Criteria

1. [52-REQ-6.1] WHEN the total non-superseded fact count exceeds
   `causal_context_limit` (default 200), THE engine SHALL rank prior facts by
   embedding similarity to the new facts and include only the top N in the
   causal extraction prompt.

2. [52-REQ-6.2] WHEN the total non-superseded fact count is <=
   `causal_context_limit`, THE engine SHALL include all non-superseded facts
   in the causal extraction prompt.

#### Edge Cases

1. [52-REQ-6.E1] IF some prior facts lack embeddings, THEN those facts SHALL
   be excluded from similarity ranking but SHALL be appended to the context
   after the similarity-ranked facts (up to the limit).

### Requirement 7: Causal Link Storage

**User Story:** As an operator, I want causal links stored idempotently with
referential integrity, so that the causal graph is consistent.

#### Acceptance Criteria

1. [52-REQ-7.1] THE engine SHALL store causal links in `fact_causes` with
   `INSERT OR IGNORE` semantics — duplicate links (same cause_id + effect_id)
   SHALL be silently skipped.

2. [52-REQ-7.2] WHEN causal link extraction completes, THE engine SHALL emit
   a `fact.causal_links` audit event with payload containing:
   `new_link_count` (integer) and `total_link_count` (integer).

#### Edge Cases

1. [52-REQ-7.E1] IF a causal link references a fact ID that does not exist in
   `memory_facts`, THEN THE engine SHALL skip that link and log a warning
   with the missing fact ID.
