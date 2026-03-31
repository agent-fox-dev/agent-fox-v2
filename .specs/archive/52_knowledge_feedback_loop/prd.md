# PRD: Knowledge Harvest & Causal Graph

> Source: post-run analysis of parking-fee-service knowledge.duckdb
> (2026-03-17 runs). All 27 sessions completed but the knowledge graph
> was effectively inert — zero session-derived facts, zero causal links.

## Problem Statement

After a full agent-fox run across 9 specs (27 sessions, $14.99), the
knowledge.duckdb contains zero session-derived facts and zero causal links.
The only populated knowledge is 100 git-commit facts ingested verbatim — a
mirror of `git log` that adds no value over the log itself.

This means:

1. **No learning between sessions.** Session N cannot benefit from gotchas
   discovered in session N-1 because fact extraction never ran.
2. **No causal graph.** The `fact_causes` table is empty, so pattern detection
   and temporal queries return nothing.

### Root Cause

`extract_and_store_knowledge()` in `engine/knowledge_harvest.py` is called
only when a session summary artifact exists (`.session-summary.json`). If the
coder session does not write this file, extraction silently skips. The
parking-fee-service run produced zero session-derived facts, indicating
summaries were either not written or not found.

The `_extract_causal_links()` function exists and is called after fact
extraction. Since fact extraction itself never ran, causal link extraction
was never reached.

## Goals

1. **Session-derived facts flow into the knowledge graph** after every
   successful coder session, with embeddings and causal links.
2. **Causal links are extracted** when new facts are stored, populating the
   `fact_causes` table for pattern detection.
3. **Observability** — audit events record harvest outcomes for diagnosis.

## Non-Goals

- Changing the archetype prompt templates (Skeptic, Verifier, Oracle).
- Adding new DuckDB tables (all required tables already exist).
- Adding new columns to existing DuckDB tables.
- Changing the embedding model or vector dimensions.
- Implementing fact compaction or garbage collection.
- Review archetype persistence (see spec 53).
- Quality gate or complexity enrichment (see spec 54).

## Clarifications

- **Session summary text**: The `"summary"` field from `.session-summary.json`,
  read by `_read_session_artifacts()` in `session_lifecycle.py`. When this file
  is absent, the engine must provide a fallback input to the extraction LLM.
  The fallback is a structured text block containing the session's spec name,
  task group, node ID, and commit diff (`git diff` of the session's commits).
- **Transcript overflow**: If the summary text exceeds the extraction model's
  context window, it is truncated from the middle (preserving the first and
  last 25% of tokens) before being sent to the LLM.
- **Causal context window**: When the total non-superseded fact count exceeds
  the extraction model's context window, facts are ranked by embedding
  similarity to the new facts and the top N (configurable, default 200) are
  included. This is governed by the `causal_context_limit` config field.
- **Minimum fact threshold**: Causal link extraction is skipped when fewer
  than 5 non-superseded facts exist. This saves an LLM call per early session.
- **Existing function signatures** (verified 2026-03-29):
  - `extract_and_store_knowledge(transcript, spec_name, node_id, memory_extraction_model, knowledge_db, *, sink_dispatcher, run_id)` — async
  - `_extract_causal_links(new_facts, node_id, memory_extraction_model, knowledge_db)` — sync
  - `store_causal_links()` in `knowledge/causal.py` — stores to `fact_causes`
  - `extract_facts()` in `knowledge/extraction.py` — LLM-based extraction

## Requirements

### 1. Session Fact Extraction

| ID | Requirement |
|----|-------------|
| KFL-1.1 | WHEN a coder session completes successfully, THE engine SHALL call `extract_and_store_knowledge()` with the session summary text. IF the `.session-summary.json` file is absent or its `"summary"` field is empty, THE engine SHALL construct a fallback input from the session's spec name, task group, node ID, and commit diff. |
| KFL-1.2 | WHEN facts are extracted, THE engine SHALL insert them into `memory_facts` with `category`, `confidence`, `spec_name`, `session_id`, and `commit_sha` populated. No field SHALL be NULL except `supersedes`. |
| KFL-1.3 | WHEN facts are inserted, THE engine SHALL generate embeddings for each new fact and store them in `memory_embeddings`. IF embedding generation fails for a fact, THE engine SHALL log the failure at warning severity and continue — fact storage SHALL NOT be blocked. |
| KFL-1.4 | WHEN extraction produces zero facts from a non-empty input (> 0 characters), THE engine SHALL emit a warning-severity `harvest.empty` audit event to flag potential extraction prompt degradation. |
| KFL-1.5 | WHEN extraction succeeds with >= 1 fact, THE engine SHALL emit a `harvest.complete` audit event including: count of facts extracted, set of categories present, and count of causal links created. |

### 2. Causal Link Population

| ID | Requirement |
|----|-------------|
| KFL-2.1 | WHEN fact extraction produces >= 1 new fact AND the total non-superseded fact count is >= 5, THE engine SHALL invoke `_extract_causal_links()` to populate the `fact_causes` table. |
| KFL-2.2 | WHEN the total non-superseded fact count exceeds `causal_context_limit` (default 200), THE engine SHALL rank prior facts by embedding similarity to the new facts and include only the top N in the causal extraction prompt. |
| KFL-2.3 | THE engine SHALL store causal links with `INSERT OR IGNORE` semantics (idempotent — duplicate links are silently skipped). |
| KFL-2.4 | WHEN causal link extraction completes, THE engine SHALL emit a `fact.causal_links` audit event including: count of new links created and total link count in the graph. |
| KFL-2.5 | WHEN the total non-superseded fact count is < 5, THE engine SHALL skip causal link extraction and log a debug-level message noting the skip reason. |

## Dependencies

This spec has no cross-spec dependencies. It fixes the existing harvest
pipeline which is already wired into the engine.

## Out of Scope

- Review archetype output persistence (spec 53).
- Review-only run mode (spec 53).
- Post-session quality gate (spec 54).
- Complexity feature vector enrichment (spec 54).
- Modifying the `extract_facts()` LLM prompt.
- Changing the DuckDB schema or adding tables.
