# PRD: Fox Ball -- Semantic Knowledge Oracle

**Source:** `.specs/prd.md` -- REQ-150 through REQ-158.
`.specs/v2.md` -- Section 4 (Tail 1: The Fox Ball), embedding model,
dual-write strategy, RAG pipeline.

## Overview

Transform the flat JSONL fact store into a queryable semantic knowledge oracle.
Facts extracted from coding sessions are embedded as vectors and stored in
DuckDB alongside the existing JSONL store. The `agent-fox ask` command embeds
a natural-language question, retrieves semantically similar facts via vector
search, and synthesizes a grounded answer with provenance and contradiction
detection.

This is the Fox Ball -- the hoshi no tama -- the fox's accumulated power made
accessible to the developer.

## Problem Statement

agent-fox v1 stores knowledge as flat JSONL facts. These facts are useful for
future prompts but are not queryable by humans. A developer cannot ask "why did
we choose DuckDB over SQLite?" and get an answer grounded in project history.
The institutional knowledge exists but is locked inside the machine.

## Goals

- Dual-write memory facts to both JSONL (source of truth) and DuckDB
  (queryable index) on every fact extraction
- Generate vector embeddings for each fact using the Anthropic voyage-3 API
  and store them in the `memory_embeddings` table
- Provide vector similarity search over the fact store, returning facts
  ranked by cosine similarity
- Ingest additional knowledge sources (ADRs, git commits) as embedded facts
- Implement the `agent-fox ask` command: a single-round RAG pipeline that
  embeds a question, retrieves relevant facts, and synthesizes a grounded
  answer via the STANDARD model (Sonnet)
- Detect and flag contradictions when retrieved facts conflict
- Track fact supersession relationships in DuckDB

## Non-Goals

- Causal graph traversal and temporal queries -- that is spec 13 (Time Vision)
- Local embedding models (sentence-transformers) -- future enhancement
- Streaming answer generation -- single API call only
- Migrating existing v1 JSONL data into DuckDB -- future `--rebuild-knowledge`
- Automatic embedding backfill -- facts without embeddings are excluded from
  search until a future backfill command is implemented
- Conversational follow-up questions -- each `ask` query is independent
- Full-text search -- vector search is sufficient at agent-fox's scale

## Key Decisions

- **Anthropic voyage-3 for embeddings** -- same API key as coding models, no
  new vendor, 1024-dimensional vectors. Configured via `KnowledgeConfig`.
- **Dual-write, not replace** -- JSONL remains source of truth for fact
  content. DuckDB is a queryable index that can be rebuilt from JSONL if
  corrupted. JSONL deletion is data loss; DuckDB deletion is recoverable.
- **Embedding failure is non-fatal** -- if the embedding API fails, the fact
  is written to both JSONL and DuckDB without an embedding. A warning is
  logged. Facts without embeddings are excluded from vector search but
  retained in the database.
- **Single-round RAG** -- embed query, top-k vector search (default k=20),
  pass retrieved facts with provenance to Sonnet, return complete answer
  block. No streaming, no multi-turn.
- **Contradiction detection at query time** -- the synthesis model flags
  conflicting facts in its response. No automatic detection at write time
  (too expensive for marginal benefit).
- **Supersession via `superseded_by` column** -- the existing `supersedes`
  field in JSONL facts is mirrored to DuckDB's `superseded_by` column,
  linking old facts to their replacements.
- **Additional sources as first-class facts** -- ADRs are parsed as markdown
  and embedded with `source="adr"`; git commits are embedded with
  `source="git"`. They live in the same `memory_facts` and
  `memory_embeddings` tables.

## Dependencies

| Dependency | Spec | What This Spec Uses |
|------------|------|---------------------|
| Config system | 01 | `KnowledgeConfig` (embedding_model, embedding_dimensions, ask_top_k, ask_synthesis_model, store_path) |
| Error hierarchy | 01 | `KnowledgeStoreError`, `AgentFoxError` |
| Model registry | 01 | `resolve_model()` for synthesis model resolution |
| Logging | 01 | Named loggers for knowledge modules |
| Structured memory | 05 | Fact extraction pipeline (extends with DuckDB dual-write) |
| DuckDB knowledge store | 11 | `KnowledgeDB` connection manager, `memory_facts` and `memory_embeddings` tables, schema, graceful degradation |
