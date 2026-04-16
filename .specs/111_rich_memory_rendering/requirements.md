# Requirements Document: Rich Memory Rendering (Spec 111)

## Introduction

This document specifies the requirements for enriching the `docs/memory.md`
rendering with causal chains, entity links, supersession history, and relative
age metadata from the DuckDB knowledge store. The implementation modifies only
`agent_fox/knowledge/rendering.py`.

## Glossary

| Term | Definition |
|------|------------|
| **Enrichment** | Additional metadata (causal links, entity paths, superseded content, age) loaded from DuckDB and rendered alongside each fact. |
| **Causal chain** | A directed relationship between facts stored in `fact_causes`. A cause-effect pair means the cause fact led to or explains the effect fact. |
| **Entity link** | An association between a fact and a code entity (file) stored in `fact_entities` joined to `entity_graph`. |
| **Supersession** | When a newer fact replaces an older one. The old fact's `superseded_by` column points to the new fact's ID. |
| **Relative age** | A human-readable duration since the fact's `created_at` timestamp (e.g., "14d ago", "3mo ago"). |
| **Summary header** | A brief section at the top of `memory.md` showing aggregate statistics (fact count, last-updated date). |
| **Enrichment data** | A container holding all enrichment lookups (causes, effects, entity paths, superseded content) keyed by fact ID. |

## Requirements

### Requirement 1: Summary Header

**User Story:** As a reader of memory.md, I want to see a quick overview of
the knowledge base state, so I can tell at a glance how much knowledge exists
and when it was last updated.

#### Acceptance Criteria

1. [111-REQ-1.1] WHEN `render_summary()` produces a non-empty document, THE
   system SHALL include a summary line immediately after the `# Agent-Fox
   Memory` heading showing the total number of active facts and the date of
   the most recent fact's `created_at` timestamp.

2. [111-REQ-1.2] THE system SHALL format the summary line as:
   `_N facts | last updated: YYYY-MM-DD_` where N is the total active fact
   count and YYYY-MM-DD is the date portion of the most recent `created_at`.

#### Edge Cases

1. [111-REQ-1.E1] IF all facts have missing or unparseable `created_at`
   values, THEN THE system SHALL omit the "last updated" portion and render
   only `_N facts_`.

---

### Requirement 2: Relative Age Display

**User Story:** As a reader of memory.md, I want to see how old each fact is,
so I can judge whether it's still relevant.

#### Acceptance Criteria

1. [111-REQ-2.1] WHEN rendering a fact, THE system SHALL compute the relative
   age from the fact's `created_at` timestamp to the current date and display
   it inline in the metadata parenthetical.

2. [111-REQ-2.2] THE system SHALL format relative age as: "Xd ago" for ages
   under 60 days, "Xmo ago" for ages from 60 days to under 365 days, and
   "Xy ago" for ages of 365 days or more, where X is a whole number.

3. [111-REQ-2.3] THE system SHALL render each fact's metadata parenthetical
   as: `_(spec: {spec_name}, confidence: {confidence}, {age})_`.

#### Edge Cases

1. [111-REQ-2.E1] IF a fact's `created_at` is missing or unparseable, THEN
   THE system SHALL omit the age portion from the metadata and render the
   parenthetical without it.

---

### Requirement 3: Fact Ordering

**User Story:** As a reader, I want the most important facts to appear first
within each category, so I can focus on high-confidence knowledge.

#### Acceptance Criteria

1. [111-REQ-3.1] WHEN rendering facts within a category, THE system SHALL
   sort facts by confidence descending, then by `created_at` descending
   (newest first among equal confidence).

#### Edge Cases

1. [111-REQ-3.E1] IF facts have identical confidence and identical or missing
   `created_at`, THEN THE system SHALL maintain a stable order (no crash or
   randomization).

---

### Requirement 4: Entity Path Annotations

**User Story:** As a reader, I want to see which code files are associated
with each fact, so I can locate the relevant code.

#### Acceptance Criteria

1. [111-REQ-4.1] WHEN a fact has associated entities in `fact_entities` joined
   to `entity_graph` (where `entity_type = 'FILE'` and `deleted_at IS NULL`),
   THE system SHALL render the entity paths as indented sub-bullets under the
   fact, each prefixed with `files:`.

2. [111-REQ-4.2] THE system SHALL display at most 3 entity paths per fact AND
   append `+N more` to the last displayed path when more than 3 exist, where
   N is the number of undisplayed paths.

#### Edge Cases

1. [111-REQ-4.E1] IF a fact has no associated entities, THEN THE system SHALL
   render no entity sub-bullet for that fact.

---

### Requirement 5: Causal Link Annotations

**User Story:** As a reader, I want to see what caused a fact or what a fact
led to, so I can understand the causal context.

#### Acceptance Criteria

1. [111-REQ-5.1] WHEN a fact has causal predecessors in `fact_causes` (where
   the fact is the effect), THE system SHALL render up to 2 cause facts as
   indented sub-bullets prefixed with `cause:`, with content truncated to 60
   characters.

2. [111-REQ-5.2] WHEN a fact has causal successors in `fact_causes` (where
   the fact is the cause), THE system SHALL render up to 2 effect facts as
   indented sub-bullets prefixed with `effect:`, with content truncated to 60
   characters.

#### Edge Cases

1. [111-REQ-5.E1] IF a fact has no causal links, THEN THE system SHALL render
   no causal sub-bullets for that fact.

2. [111-REQ-5.E2] IF a causal-linked fact has been superseded (its
   `superseded_by IS NOT NULL`), THEN THE system SHALL still render it if
   it is within the limit, since the causal relationship is historical context.

---

### Requirement 6: Supersession Annotations

**User Story:** As a reader, I want to see what a fact replaced, so I
understand the evolution of knowledge.

#### Acceptance Criteria

1. [111-REQ-6.1] WHEN a fact superseded an older fact (the older fact's
   `superseded_by` equals this fact's ID), THE system SHALL render the
   superseded fact's content as an indented sub-bullet prefixed with
   `replaces:`, truncated to 80 characters.

#### Edge Cases

1. [111-REQ-6.E1] IF a fact did not supersede any older fact, THEN THE system
   SHALL render no supersession sub-bullet for that fact.

---

### Requirement 7: Enrichment Loading and Graceful Degradation

**User Story:** As a system operator, I want rendering to succeed even when
enrichment data is unavailable, so that memory.md is always generated.

#### Acceptance Criteria

1. [111-REQ-7.1] WHEN rendering facts, THE system SHALL load all enrichment
   data (causal links, entity paths, superseded content) in batch queries
   keyed by fact IDs, AND pass the enrichment data to the per-fact renderer.

2. [111-REQ-7.2] THE system SHALL execute at most 4 enrichment queries
   regardless of fact count: one for causes, one for effects, one for entity
   paths, and one for superseded content.

#### Edge Cases

1. [111-REQ-7.E1] IF any enrichment query fails (table missing, SQL error,
   connection error), THEN THE system SHALL log a warning and continue
   rendering with empty enrichment data for that category, never aborting
   the rendering process.

2. [111-REQ-7.E2] IF the DuckDB connection is None, THEN THE system SHALL
   skip all enrichment loading and render facts in the basic format (content,
   spec, confidence, age only).
