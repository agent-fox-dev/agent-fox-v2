# PRD: Adaptive Retrieval with Multi-Signal Fusion

## Problem

agent-fox has four knowledge retrieval signals — keyword matching, vector
similarity, causal chain traversal, and entity graph traversal — but they
operate in isolation. The current pipeline runs them sequentially with
hardcoded budgets (40 keyword + 10 causal slots), the entity graph is not
used for retrieval at all, and the assembled context is a flat markdown list
with no structural ordering.

This produces three concrete problems:

1. **Signal isolation.** A fact that scores moderately on keywords, moderately
   on vector similarity, and is linked to a touched entity never surfaces
   because no single signal ranks it high enough. Reciprocal Rank Fusion (RRF)
   would promote it.

2. **No adaptive weighting.** A "coder" session on a previously-failed node
   needs causal context ("what went wrong last time?"), while an "auditor"
   session needs structural context ("what depends on this module?"). The
   current pipeline applies the same retrieval strategy to both.

3. **Flat context injection.** Facts are dumped as a markdown bullet list.
   There is no ordering by relevance, no causal precedence, no provenance
   metadata, and no token budgeting. High-value facts get the same treatment
   as marginally-relevant ones.

## Solution

Replace the current retrieval chain (`select_relevant_facts` →
`enhance_with_causal` → `_retrieve_cross_spec_facts`) with a unified
retriever that:

1. **Runs all four signals in parallel** — keyword, vector, entity graph BFS,
   causal chain — producing four ranked lists.

2. **Fuses results via Reciprocal Rank Fusion (RRF)** — combining the four
   ranked lists into unified anchor scores using the standard RRF formula:
   `score = sum(1 / (k + rank_i))` across all signals.

3. **Applies adaptive signal weights** derived from task context — the
   retriever infers an intent profile from the session's archetype, node
   status (fresh vs. retry), and task metadata, then scales each signal's
   contribution to the RRF score.

4. **Orders context by relevance and causal precedence** — the top-N facts
   are arranged with causes before effects, highest-salience facts expanded
   and low-salience facts summarized to a single line, and provenance
   metadata (spec name, confidence) included.

### Intent Derivation

Rather than classifying a free-text query (as MAGMA does), the retriever
derives intent from the task context automatically:

- **Archetype** — coders need structural + causal context; auditors need
  structural context; reviewers need semantic context.
- **Node status** — a retry after failure should weight causal signals
  higher ("what went wrong?"); a fresh attempt should weight structural
  signals higher ("what relates to this code?").
- **Task metadata** — spec name, task group number, and touched files
  provide implicit structural anchors.

### Configuration

Default weights ship with sensible values. Users can override them in
`config.toml` under a `[knowledge.retrieval]` section. No per-archetype
config is needed initially — the system derives weights automatically.

## Non-Goals

- Adding new retrieval signals beyond the four that already exist.
- Changing how facts are stored, extracted, or consolidated.
- Modifying the entity graph, causal graph, or embedding infrastructure.
- Implementing MAGMA's temporal graph (timestamps on facts are sufficient).

## Clarifications

1. **Intent derivation** is automatic from task context (archetype + node
   status + task metadata), not from free-text query classification.
2. **Adaptive weights** change per-session based on task context — not
   static per-archetype.
3. **Entity graph** is queried live per-session via `find_related_facts`
   using touched files from the task — no precomputation.
4. **Narrative synthesis** (ordered context with provenance and token
   budgeting) is in scope.
5. **Full replacement** — the new retriever replaces the existing
   `select_relevant_facts` → `enhance_with_causal` →
   `_retrieve_cross_spec_facts` chain entirely.
6. **Configuration** — defaults that just work, with optional overrides in
   `config.toml`.
7. **Facts without embeddings** participate in RRF with a vector score of 0.
8. **Live computation** per-session — no precomputed cache required.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 95_entity_graph | 4 | 2 | Uses `find_related_facts` and `traverse_neighbors` from entity_query.py; group 4 is where entity_linker and entity_query were implemented |
| 94_cross_spec_vector_retrieval | 5 | 2 | Uses `VectorSearch.search` for the vector signal; group 5 is the wiring verification confirming VectorSearch is live |
