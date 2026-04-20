# Requirements Document

## Introduction

This document specifies the Time Vision temporal reasoning capabilities for
agent-fox v2: causal link extraction, causal graph storage and traversal,
temporal queries, predictive pattern detection, timeline rendering, and
enhanced context selection. Time Vision builds on the DuckDB knowledge store
(spec 11) and Fox Ball (spec 12) to turn accumulated session data into
actionable causal knowledge.

## Glossary

| Term | Definition |
|------|-----------|
| Causal link | A directed edge from a cause fact to an effect fact in the causal graph |
| Causal graph | The directed acyclic graph formed by all causal links in `fact_causes` |
| Causal chain | A path through the causal graph from a root cause to its downstream effects |
| Fact provenance | Metadata attached to a fact: source spec name, session ID, and commit SHA |
| Temporal query | A natural-language question that requires traversing the causal graph to answer |
| Timeline | An ordered, indented text representation of a causal chain with timestamps and provenance |
| Pattern | A recurring co-occurrence detected in the causal graph (e.g., "module X changes -> test Y breaks") |
| Harvest | The post-session phase where memory facts are extracted from the session context |
| Root fact | A fact with no incoming causal links -- the start of a causal chain |

## Requirements

### Requirement 1: Fact Provenance

**User Story:** As a developer, I want every fact in the knowledge store to
carry provenance metadata so that I can trace where knowledge came from.

#### Acceptance Criteria

1. [13-REQ-1.1] WHEN a fact is stored in the `memory_facts` table, THE system
   SHALL populate the `spec_name`, `session_id`, and `commit_sha` columns with
   the source spec name, the session identifier, and the commit SHA that
   produced the fact.
2. [13-REQ-1.2] WHEN provenance metadata is unavailable (e.g., no commit yet),
   THE system SHALL store the fact with NULL values for the missing provenance
   fields rather than rejecting the fact.

---

### Requirement 2: Causal Link Extraction

**User Story:** As a developer, I want the system to automatically identify
cause-effect relationships between facts so that the causal graph grows
organically with each session.

#### Acceptance Criteria

1. [13-REQ-2.1] WHEN the memory extraction prompt runs after a session, THE
   system SHALL include instructions that direct the extraction model to
   identify cause-effect relationships between the current session's facts and
   prior facts.
2. [13-REQ-2.2] WHEN the extraction model identifies a causal relationship,
   THE system SHALL store it as a row in the `fact_causes` table with the
   cause fact's ID and the effect fact's ID.

#### Edge Cases

1. [13-REQ-2.E1] IF the extraction model fails to identify any causal links,
   THEN THE system SHALL store the extracted facts without causal metadata and
   log an informational message. This is non-fatal -- Time Vision queries will
   have reduced coverage but will not fail.
2. [13-REQ-2.E2] IF a causal link references a fact ID that does not exist in
   `memory_facts`, THEN THE system SHALL skip that link and log a warning
   rather than inserting a dangling reference.

---

### Requirement 3: Causal Graph Storage and Traversal

**User Story:** As a developer of agent-fox, I want to query the causal graph
to find causes and effects of a given fact so that temporal reasoning can
follow causal chains.

#### Acceptance Criteria

1. [13-REQ-3.1] THE system SHALL provide a function
   `store_causal_links(conn, links: list[tuple[str, str]])` that accepts a
   list of (cause_id, effect_id) tuples and inserts them into the
   `fact_causes` table using `INSERT OR IGNORE` for idempotent batch
   insertion.
2. [13-REQ-3.2] THE system SHALL support querying the direct causes of a
   given fact (all rows where `effect_id` matches the fact). Direct cause
   queries are handled internally by `traverse_causal_chain()` with
   `max_depth=1, direction="causes"` via private helper
   `_get_direct_cause_ids()`. The public API is `traverse_causal_chain()`.
3. [13-REQ-3.3] THE system SHALL support querying the direct effects of a
   given fact (all rows where `cause_id` matches the fact). Direct effect
   queries are handled internally by `traverse_causal_chain()` with
   `max_depth=1, direction="effects"` via private helper
   `_get_direct_effect_ids()`. The public API is `traverse_causal_chain()`.
4. [13-REQ-3.4] THE system SHALL provide a function to traverse a causal
   chain from a given fact, following cause-effect links up to a configurable
   maximum depth (default: 10), returning all facts in the chain with their
   depth level.

#### Edge Cases

1. [13-REQ-3.E1] IF a duplicate causal link is inserted (same cause_id and
   effect_id), THEN THE system SHALL silently ignore the duplicate rather
   than raising an error (idempotent insert).

---

### Requirement 4: Temporal Queries

**User Story:** As a developer, I want to ask temporal questions like "what
happened last time we changed the auth module?" and get timeline-structured
answers grounded in the causal graph.

#### Acceptance Criteria

1. [13-REQ-4.1] WHEN the user submits a temporal query via the `ask` command,
   THE system SHALL use vector similarity search to find relevant facts, then
   traverse the causal graph from those facts to construct a timeline of
   causally linked events.
2. [13-REQ-4.2] THE `temporal_query()` function SHALL return a `Timeline`
   object containing the causal chain. Synthesis of a natural-language answer
   from the timeline is the responsibility of the caller (e.g., the `ask`
   command), not of `temporal_query()` itself. This separation keeps the
   temporal module focused on graph traversal and timeline construction.

---

### Requirement 5: Predictive Pattern Detection

**User Story:** As a developer, I want the system to detect recurring
cause-effect patterns so that I can anticipate likely breakage before it
happens.

#### Acceptance Criteria

1. [13-REQ-5.1] THE system SHALL provide a batch computation that analyzes
   historical co-occurrences in the `fact_causes` table and
   `session_outcomes` table to identify recurring file-to-file patterns by
   grouping on `changed.touched_path` and `failed.touched_path` (e.g.,
   "changes to src/auth/login.py -> tests/test_payments.py failures").
2. [13-REQ-5.2] Each detected pattern SHALL include: the trigger condition,
   the observed effect, the number of occurrences, the last occurrence
   timestamp, and a confidence indicator.
3. [13-REQ-5.3] THE system SHALL provide an `agent-fox patterns` CLI command
   that triggers pattern detection and displays the results.

#### Edge Cases

1. [13-REQ-5.E1] IF no patterns are detected (insufficient data), THEN THE
   system SHALL display a message explaining that more session history is
   needed and exit successfully.

---

### Requirement 6: Timeline Rendering

**User Story:** As a developer, I want causal timelines displayed as readable
indented text chains in the CLI so that I can trace the causal flow at a
glance.

#### Acceptance Criteria

1. [13-REQ-6.1] THE system SHALL render timelines as indented text chains
   where each node shows: the fact content, the timestamp, the source spec
   name, the session ID, the commit SHA (if available), and the causal
   relationship type (cause, effect, or root).
2. [13-REQ-6.2] THE indentation depth SHALL correspond to the node's
   position in the causal chain (root at depth 0, direct effects at depth 1,
   etc.).
3. [13-REQ-6.3] THE timeline format SHALL always be plain text with no ANSI
   escape codes, suitable for piping to other tools. The `use_color`
   parameter is accepted for interface compatibility but is reserved for
   future use; the current implementation always emits plain text regardless
   of its value.

---

### Requirement 7: Context Enhancement

**User Story:** As a developer, I want the system to use causal graph data
to select better context for coding sessions so that the agent has access to
causally relevant history.

#### Acceptance Criteria

1. [13-REQ-7.1] BEFORE each coding session, THE system SHALL query the
   causal graph to find facts causally linked to the current task's spec
   name and touched files, and include them in the session context alongside
   keyword-matched facts.
2. [13-REQ-7.2] Causally-linked facts SHALL be additive -- they augment the
   existing keyword-matched context selection (REQ-061), not replace it. The
   combined context SHALL remain within the 50-fact budget.
