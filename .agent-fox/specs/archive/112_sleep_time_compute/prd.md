> **SUPERSEDED** by spec 114_knowledge_decoupling

# PRD: Sleep-Time Compute

## Problem Statement

The knowledge system currently performs all retrieval computation at query time:
four signals (keyword, vector, entity, causal) are computed, fused via RRF, and
assembled into context on every session start. This is redundant when the
underlying fact base hasn't changed between sessions.

Inspired by the *Sleep-time Compute* paradigm (Lin et al., 2025 —
arXiv:2504.13171), this spec introduces an offline pre-computation pipeline
that runs during idle periods to produce enriched, pre-digested knowledge
artifacts. These artifacts make future retrieval faster (fewer signals to
compute live) and richer (LLM-synthesized narrative summaries that capture
cross-fact relationships raw facts cannot express alone).

## Goals

1. **Context re-representation** — During idle time, cluster active facts by
   source directory and synthesize structured narrative summaries per cluster.
   These summaries capture cross-fact relationships and module-level context
   that individual facts miss. At retrieval time, they are prepended to the
   assembled context as a preamble.

2. **Pre-computed retrieval bundles** — Pre-run the keyword and causal signals
   for each active spec (these signals depend only on `spec_name`, not on
   session-specific parameters). Cache the scored fact lists so the retriever
   can skip those two signal computations when a valid bundle exists.

3. **Open architecture** — Define a `SleepTask` protocol so that future
   pre-computation strategies (anticipated Q&A, cross-spec summaries,
   dependency-graph pre-scoring, etc.) can be added by implementing a single
   interface and registering with the orchestrator.

## Non-Goals

- Replacing the existing four-signal retrieval pipeline. Sleep artifacts
  supplement or accelerate it; they do not replace it.
- Running LLM inference during active sessions. Sleep compute runs only at
  sync barriers and during nightshift daemon idle periods.
- Pre-computing vector or entity signals. These depend on session-specific
  parameters (`task_description`, `touched_files`) that are unknown at sleep
  time.

## Design Decisions

1. **Directory-based clustering** (not entity-graph neighborhoods or
   embedding-based clusters). Facts are grouped by the directory of their
   entity-linked files (e.g., all facts linked to files under
   `agent_fox/knowledge/` form one cluster). Facts without entity links are
   grouped under a `_general` scope. Rationale: simple, deterministic, aligns
   with developer mental models of the codebase.

2. **Structured narrative** for context blocks — not free-form prose or raw
   bullet points. Each block has a heading (directory path) and a concise
   narrative that explains how the facts in that cluster relate to each other.
   Predictable format, predictable token cost.

3. **Context preamble integration** — Context blocks are prepended to the
   assembled retrieval context rather than injected as a 5th RRF signal.
   Closest to the paper's c′ substitution model and avoids retuning RRF
   weights.

4. **Pre-compute keyword + causal only** — These two signals depend only on
   `spec_name` and can be fully pre-computed. Vector (needs `task_description`)
   and entity (needs `touched_files`) remain live. This halves the signal
   computations at query time when a valid bundle exists.

5. **STANDARD model tier** for context re-representation LLM calls. Higher
   quality than SIMPLE; justified because context blocks are amortized across
   many sessions.

6. **Content-hash staleness** — A SHA-256 hash of sorted active fact IDs +
   confidences per scope. Deterministic, no false negatives. When the hash
   changes, the artifact is stale and regenerated at the next sleep window.

7. **Unified `sleep_artifacts` table** — All sleep task outputs stored in one
   table with a `task_name` discriminator. Cleaner for the open architecture;
   new tasks don't require schema migrations.

8. **Dual trigger points** — Sleep compute runs at sync barriers (after
   compaction, before summary rendering) AND as a nightshift work stream.
   Both from the start.

9. **Minimum cluster size of 3** — A directory cluster needs at least 3 active
   facts before a context block is generated. Same threshold as pattern
   promotion in consolidation.

10. **Context block size cap of 2000 characters** — Per-block limit keeps the
    preamble from dominating the token budget.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 96_knowledge_consolidation | (complete) | 1 | Uses consolidation's entity graph and fact-entity links; sleep compute runs after consolidation at barriers |
| 104_adaptive_retrieval | (complete) | 1 | Modifies AdaptiveRetriever to consume sleep artifacts; uses existing signal functions for bundle pre-computation |

## Source

Source: Input provided by user via interactive prompt
