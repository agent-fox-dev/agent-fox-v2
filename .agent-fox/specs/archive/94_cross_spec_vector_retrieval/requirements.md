# Requirements Document

## Introduction

Cross-spec vector retrieval adds semantic search across the entire knowledge
store during session context assembly. When a coding session loads facts, the
system embeds the current task group's subtask descriptions and retrieves
semantically relevant facts from ALL specs -- not just the current one. These
cross-spec facts are merged with spec-specific facts and enhanced with causal
context before injection into the session prompt.

## Glossary

- **Cross-spec fact**: A fact from the knowledge store whose `spec_name`
  differs from the current session's spec. Cross-spec facts are retrieved via
  vector similarity search rather than keyword/spec-name matching.
- **Subtask description**: The first non-metadata bullet point under a subtask
  entry in `tasks.md` (e.g., "Create rate limiting middleware class"). These
  describe concrete implementation steps.
- **Metadata bullet**: A `tasks.md` bullet whose text begins with an
  underscore character (`_`), indicating a reference annotation rather than
  implementation detail (e.g., `_Requirements: 93-REQ-1.1_` or
  `_Test Spec: TS-93-1_`).
- **Fact ID**: The UUID primary key of a fact in the `memory_facts` table,
  used for deduplication during merge.
- **cross_spec_top_k**: The maximum number of facts returned by cross-spec
  vector search; a configurable field on `KnowledgeConfig`.
- **Spec-specific facts**: Facts returned by the existing
  `select_relevant_facts()` / fact cache pipeline, filtered by spec name and
  keyword overlap.
- **Causal enhancement**: The `enhance_with_causal()` step that augments a
  fact set with causally-linked facts from the DuckDB knowledge store.

## Requirements

### Requirement 1: Subtask Description Extraction

**User Story:** As a coding agent, I want the system to extract descriptive
text from my current task group so that it can find relevant knowledge from
other specs.

#### Acceptance Criteria

1. [94-REQ-1.1] WHEN assembling context for a coding session, THE system
   SHALL parse the current spec's `tasks.md`, locate the task group matching
   the session's task group number, extract the first non-metadata bullet
   point from each subtask within that group, AND return the extracted
   descriptions as a list of strings to the caller.

2. [94-REQ-1.2] WHEN extracting subtask descriptions, THE system SHALL skip
   bullet points whose text begins with an underscore character (`_`), as
   these are metadata annotations (requirement references, test spec links).

#### Edge Cases

1. [94-REQ-1.E1] IF `tasks.md` does not exist for the current spec, THEN
   THE system SHALL return an empty list and cross-spec retrieval SHALL be
   skipped.

2. [94-REQ-1.E2] IF the current task group contains no subtasks or no
   subtasks with non-metadata bullet points, THEN THE system SHALL return
   an empty list and cross-spec retrieval SHALL be skipped.

### Requirement 2: Cross-Spec Embedding and Search

**User Story:** As a coding agent, I want the system to find semantically
relevant facts from across all specs so that I have the full context needed
for my task.

#### Acceptance Criteria

1. [94-REQ-2.1] WHEN subtask descriptions are extracted (non-empty list),
   THE system SHALL concatenate them with newline separators into a single
   query string AND generate an embedding using
   `EmbeddingGenerator.embed_text()`.

2. [94-REQ-2.2] WHEN an embedding is generated, THE system SHALL call
   `VectorSearch.search()` with the embedding, `top_k` set to the configured
   `cross_spec_top_k`, and `exclude_superseded=True`, searching across ALL
   facts in the knowledge store, AND return the search results to the caller
   for merging.

#### Edge Cases

1. [94-REQ-2.E1] IF `EmbeddingGenerator.embed_text()` returns `None`, THEN
   THE system SHALL silently skip cross-spec retrieval and continue with
   spec-specific facts only.

2. [94-REQ-2.E2] IF `VectorSearch.search()` returns an empty list, THEN THE
   system SHALL continue with spec-specific facts only (no merge needed).

### Requirement 3: Fact Merging and Deduplication

**User Story:** As a coding agent, I want cross-spec facts merged with my
spec-specific facts without duplicates so that I receive a clean, unified
fact set.

#### Acceptance Criteria

1. [94-REQ-3.1] WHEN cross-spec search results are returned, THE system
   SHALL convert each `SearchResult` to a `Fact`-compatible object and merge
   with the spec-specific fact list, removing any fact whose ID already
   appears in the spec-specific set, AND return the merged list to the caller.

2. [94-REQ-3.2] THE system SHALL perform the merge BEFORE passing facts to
   causal enhancement (`enhance_with_causal`), so that cross-spec facts
   receive the same causal expansion as spec-specific facts.

#### Edge Cases

1. [94-REQ-3.E1] IF all cross-spec search results have IDs that already
   appear in the spec-specific set, THEN THE system SHALL return the
   spec-specific set unchanged (no new facts added).

### Requirement 4: Configuration

**User Story:** As a project operator, I want to configure the number of
cross-spec facts retrieved so that I can balance context richness against
prompt size.

#### Acceptance Criteria

1. [94-REQ-4.1] THE system SHALL expose a `cross_spec_top_k` field on
   `KnowledgeConfig` with a default value of 15, type `int`, and a minimum
   value of 0.

2. [94-REQ-4.2] WHEN `cross_spec_top_k` is set to 0, THE system SHALL skip
   cross-spec retrieval entirely (treating it as disabled).

### Requirement 5: Graceful Degradation

**User Story:** As a system operator, I want cross-spec retrieval to never
break session startup so that sessions always proceed even without this
enhancement.

#### Acceptance Criteria

1. [94-REQ-5.1] IF any step in the cross-spec retrieval pipeline raises an
   exception (task parsing, embedding generation, vector search, fact
   conversion, or merge), THEN THE system SHALL catch the exception, continue
   with spec-specific facts only, and not emit a user-visible log message
   (debug-level logging is permitted).

### Requirement 6: EmbeddingGenerator Sharing

**User Story:** As a system operator, I want the embedding model loaded only
once per run, not once per session, so that cross-spec retrieval does not add
significant startup latency.

#### Acceptance Criteria

1. [94-REQ-6.1] WHEN creating session runners via the factory, THE factory
   SHALL accept an optional `EmbeddingGenerator` instance and pass it to each
   `NodeSessionRunner`, so that a single embedding model is shared across all
   sessions in a run.

2. [94-REQ-6.2] IF no `EmbeddingGenerator` is provided to the runner, THEN
   THE system SHALL silently skip cross-spec retrieval.
