# Requirements Document

## Introduction

This document specifies the Fox Ball -- agent-fox's semantic knowledge oracle:
dual-write fact persistence, vector embedding generation, similarity search,
additional knowledge source ingestion, the `agent-fox ask` command (RAG
pipeline with synthesis and contradiction detection), and fact supersession
tracking. Every requirement traces to PRD requirements REQ-150 through REQ-158.

## Glossary

| Term | Definition |
|------|-----------|
| Dual-write | Writing a fact to both JSONL (source of truth) and DuckDB (queryable index) in a single operation |
| Embedding | A fixed-length vector representation of text content, enabling semantic similarity comparison |
| voyage-3 | Anthropic's embedding model producing 1024-dimensional vectors |
| Vector search | Finding records whose embedding vectors are most similar to a query vector, using cosine similarity |
| Cosine similarity | A measure of similarity between two vectors, ranging from -1 (opposite) to 1 (identical) |
| RAG | Retrieval-Augmented Generation -- embedding a query, retrieving relevant context, and synthesizing an answer |
| Top-k | The number of most-similar results returned from a vector search (default: 20) |
| Supersession | The relationship where a newer fact replaces or updates an older fact |
| Provenance | The origin metadata of a fact: source spec, session ID, commit SHA |
| Oracle | The synthesis component that generates grounded answers from retrieved facts |
| ADR | Architecture Decision Record -- a document in `docs/adr/` recording a design decision |
| Backfill | Retroactively generating embeddings for facts that were stored without them |

## Requirements

### Requirement 1: Dual-Write Fact Persistence

**User Story:** As a developer, I want every memory fact written to both JSONL
and DuckDB so that facts are queryable via vector search while the JSONL
source of truth is preserved.

#### Acceptance Criteria

1. [12-REQ-1.1] WHEN the system extracts a memory fact from a coding session,
   THE system SHALL write the fact to both the JSONL store (`.agent-fox/memory.jsonl`)
   and the DuckDB `memory_facts` table in a single logical operation.
2. [12-REQ-1.2] THE JSONL store SHALL remain the source of truth for fact
   content. THE DuckDB store SHALL be a queryable index that can be rebuilt
   from JSONL.
3. [12-REQ-1.3] WHEN writing to DuckDB, THE system SHALL populate all
   provenance fields: `id`, `content`, `category`, `spec_name`, `session_id`,
   `commit_sha`, `confidence`, and `created_at`.

#### Edge Cases

1. [12-REQ-1.E1] IF the DuckDB write fails (database unavailable, disk full),
   THEN THE system SHALL still write the fact to JSONL, log a warning, and
   continue without raising an exception. The JSONL write is never skipped.

---

### Requirement 2: Embedding Generation

**User Story:** As a developer, I want each memory fact to have a vector
embedding so that it can be found via semantic similarity search.

#### Acceptance Criteria

1. [12-REQ-2.1] WHEN a fact is written to DuckDB, THE system SHALL generate a
   vector embedding using the configured embedding model (default: Anthropic
   voyage-3, 1024 dimensions) and store it in the `memory_embeddings` table
   alongside the fact.
2. [12-REQ-2.2] THE system SHALL support batch embedding of multiple facts in
   a single API call for efficiency during bulk operations (e.g., ingestion
   of additional sources).

#### Edge Cases

1. [12-REQ-2.E1] IF embedding generation fails (API error, rate limit,
   network failure), THEN THE fact SHALL be written to both JSONL and DuckDB
   `memory_facts` without an embedding. A warning SHALL be logged. Missing
   embeddings may be backfilled later.
2. [12-REQ-2.E2] IF the embedding API fails during an `ask` query (preventing
   the question from being embedded), THEN THE system SHALL report the error
   and suggest retrying.

---

### Requirement 3: Vector Similarity Search

**User Story:** As a developer, I want to search the fact store using natural
language so that I can find relevant project knowledge by meaning, not just
keywords.

#### Acceptance Criteria

1. [12-REQ-3.1] THE system SHALL support vector similarity search over the
   `memory_embeddings` table, returning facts ranked by cosine similarity to
   a query embedding.
2. [12-REQ-3.2] THE search SHALL return the top-k most similar facts (default
   k from `KnowledgeConfig.ask_top_k`, default: 20), each including the fact
   content, provenance metadata, and similarity score.
3. [12-REQ-3.3] THE search SHALL exclude facts that have no embedding in the
   `memory_embeddings` table.

#### Edge Cases

1. [12-REQ-3.E1] IF the knowledge store contains no embedded facts, THEN THE
   search SHALL return an empty result set without error.

---

### Requirement 4: Additional Source Ingestion

**User Story:** As a developer, I want project knowledge beyond session-
extracted facts -- such as ADRs and git commits -- to be searchable alongside
session facts so that the Fox Ball reflects the full project history.

#### Acceptance Criteria

1. [12-REQ-4.1] THE system SHALL ingest Architecture Decision Records from
   `docs/adr/` as facts with `category="adr"`, parsing each markdown file
   into a fact with the ADR title and content.
2. [12-REQ-4.2] THE system SHALL ingest git commit messages as facts with
   `category="git"`, recording the commit SHA, author date, and message body.
3. [12-REQ-4.3] Ingested sources SHALL be embedded and stored in
   `memory_facts` and `memory_embeddings`, searchable alongside session facts.

---

### Requirement 5: Ask Command

**User Story:** As a developer, I want to run `agent-fox ask "question"` and
receive a grounded answer synthesized from my project's accumulated knowledge,
so that I can query institutional memory in natural language.

#### Acceptance Criteria

1. [12-REQ-5.1] WHEN the user runs `agent-fox ask "question"`, THE system
   SHALL embed the question, retrieve the top-k most similar facts from
   DuckDB, pass the retrieved facts with provenance to the synthesis model,
   and return a grounded natural-language answer.
2. [12-REQ-5.2] THE answer SHALL include source attributions listing which
   facts contributed, with provenance (spec name, session ID, commit SHA).
3. [12-REQ-5.3] THE `ask` command SHALL use a single API call (not streaming)
   with the configured synthesis model (default: STANDARD / Sonnet) for
   answer generation.

#### Edge Cases

1. [12-REQ-5.E1] IF the knowledge store is empty or contains no embedded
   facts, THEN THE system SHALL print a message explaining that no knowledge
   has been accumulated yet and suggest running coding sessions first.
2. [12-REQ-5.E2] IF the knowledge store is unavailable (corrupted, missing),
   THEN THE system SHALL report an error explaining the store is unavailable.

---

### Requirement 6: Contradiction Detection

**User Story:** As a developer, I want the Fox Ball to flag when retrieved
facts contradict each other so that I am aware of conflicting information
rather than receiving a silently biased answer.

#### Acceptance Criteria

1. [12-REQ-6.1] WHEN retrieved facts contradict each other, THE synthesis
   model SHALL flag the contradiction in the response, identifying the
   conflicting facts and their provenance.

---

### Requirement 7: Supersession Tracking

**User Story:** As a developer, I want the system to track when a newer fact
replaces an older one so that the knowledge base reflects the most current
understanding.

#### Acceptance Criteria

1. [12-REQ-7.1] THE system SHALL track fact supersession relationships in
   DuckDB by populating the `superseded_by` column in `memory_facts` when a
   newer fact replaces or updates an older one.
2. [12-REQ-7.2] WHEN a fact has been superseded, THE vector search SHALL
   deprioritize or exclude it in favor of the superseding fact.

---

### Requirement 8: Confidence Indicator

**User Story:** As a developer, I want the Fox Ball's answers to include a
confidence level so that I know how well-grounded the answer is.

#### Acceptance Criteria

1. [12-REQ-8.1] THE oracle answer SHALL include a confidence indicator
   ("high", "medium", or "low") based on the number and relevance of matching
   facts.
