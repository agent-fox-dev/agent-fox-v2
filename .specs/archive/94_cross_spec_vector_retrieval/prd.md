# Cross-Spec Vector Retrieval for Context Injection

> **Superseded by spec 104 (`adaptive_retrieval`).** The `AdaptiveRetriever`
> introduced in spec 104 replaces the single-signal cross-spec vector search
> with a unified multi-signal retriever (keyword, vector, entity graph, causal
> chain) fused via weighted Reciprocal Rank Fusion. The `cross_spec_top_k`
> config field from this spec was dead code and has been removed. Use
> `RetrievalConfig.vector_top_k` (default 50) under `[knowledge.retrieval]`
> instead.

## Problem

When the session lifecycle loads facts for a coding session, it filters by
spec name and keyword overlap, then enhances with causal context. Knowledge
from other specs that is semantically relevant to the current task does not
get injected unless it happens to share keywords or causal links with the
current spec's facts.

### Example

Spec 3 established that "the API uses JWT with RS256 signing." Spec 12 is
about adding rate limiting to the API. Spec 12's facts don't mention JWT,
but the coding agent needs to know about the auth architecture to implement
rate limiting correctly. If you only load Spec 12's facts, this knowledge
is missing.

## Solution

Before causal enhancement, perform a semantic vector search across ALL facts
in the knowledge store using the current task group's subtask descriptions
as the query. Merge the results with spec-specific facts (deduplicating by
fact ID) before passing them through causal enhancement.

### Steps

1. Parse the current task group from `tasks.md`
2. Extract the first non-metadata bullet point from each subtask
3. Concatenate descriptions and embed using `EmbeddingGenerator.embed_text()`
4. Run `VectorSearch.search()` across all non-superseded facts with a
   configurable `cross_spec_top_k` (default 15)
5. Merge with spec-specific facts, deduplicating by fact ID
6. Pass the merged set through existing causal enhancement

## Clarifications

- **Query source:** First bullet point of each subtask (not titles/headings),
  providing implementation-specific descriptions for better semantic matching.
- **Merge position:** Before causal enhancement, so cross-spec facts also
  get causal expansion.
- **Graceful degradation:** Silently skip if embedding generation or vector
  search fails -- no user-visible warning or exception.
- **Budget:** Cross-spec retrieval uses its own budget (`cross_spec_top_k`),
  independent of the spec-specific fact budget (50).
- **Freshness:** Computed fresh at session time (not cached at plan time) to
  ensure the latest facts are included, including those ingested by earlier
  sessions in the same run.
- **Embeddings:** Facts without embeddings are naturally excluded by the
  `VectorSearch` INNER JOIN -- this is expected and documented behavior.
- **EmbeddingGenerator sharing:** A single `EmbeddingGenerator` instance is
  shared across all session runners via the factory to avoid redundant model
  loading.
