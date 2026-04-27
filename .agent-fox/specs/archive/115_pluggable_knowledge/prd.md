# PRD: Pluggable Knowledge Provider

## Problem Statement

After spec 114 removes the low-value knowledge pipeline, the engine has a
`KnowledgeProvider` protocol with a no-op implementation. The system runs
cleanly but has no knowledge system — agents cannot learn from past sessions.

The old system failed because it was:

- **Scattered** — 35+ files, 63+ import sites, embedded in engine, nightshift,
  session, and CLI modules with no clear boundary.
- **Noisy** — 50 facts injected into every session via 4-signal vector
  retrieval, most irrelevant. 56% of facts were generic git-category noise.
- **Write-heavy, read-light** — the system eagerly extracted, embedded,
  deduplicated, contradiction-checked, and compacted facts, but retrieval
  returned bulk results with no quality filtering.
- **Structurally broken** — entity graph had only "contains" edges, causal
  chains were never consumed, fact extraction never fired during sessions,
  contradiction detection found nothing, compaction was append-only.

This spec builds a new knowledge system behind the `KnowledgeProvider` protocol.
The design inverts the old system's priorities: hard to write to, easy to read
from. Only genuinely surprising or actionable knowledge enters the store.
Retrieval is scoped, small, and high-signal.

## Goals

1. **Implement the KnowledgeProvider protocol** with a real provider that stores
   and retrieves scoped knowledge.

2. **Gotcha store** — capture only things that surprised an agent or caused
   unexpected behavior. Not generic patterns, not raw commit messages, not
   file-contains-function facts. A gotcha is: "X looks like it should work
   but actually Y because Z."

3. **Review carry-forward** — when a reviewer identifies critical or major
   findings that were not resolved before the next coder session starts, inject
   those findings into the coder's context. This is the mechanism that already
   works (review findings influenced 5 documented coder behaviors); formalize
   it as a knowledge provider capability.

4. **Errata index** — pointer from spec name to errata documents. When a spec's
   implementation diverges from the spec (a known, accepted divergence), the
   errata doc explains why. The knowledge provider surfaces the relevant errata
   when a session starts for that spec.

5. **Scoped retrieval** — retrieve 5-10 items filtered by `spec_name`, not 50
   by vector similarity across the entire fact base. No embeddings required.
   Direct DuckDB queries with spec_name and category filters.

6. **Registration-based architecture** — the engine calls
   `KnowledgeProvider.retrieve()` and `KnowledgeProvider.ingest()`. The concrete
   provider is registered at startup via configuration. New providers can be
   swapped in without engine changes.

## Non-Goals

- Embedding-based vector search. Scoped keyword/direct lookup is sufficient for
  5-10 items per session.
- Entity graph reconstruction. The old entity graph provided no value; this
  system does not attempt to rebuild it.
- Cross-spec knowledge synthesis. Each spec's knowledge is scoped to that spec.
  Global knowledge (gotchas that apply everywhere) uses a `_global` scope.
- Real-time fact extraction during sessions. Ingestion happens post-session,
  not mid-conversation. The old system's attempt at live extraction never worked.
- Causal chain tracking. The old causal graph was never consumed.

## Design Decisions

1. **Three knowledge categories.** The provider stores three types of knowledge:
   - **Gotcha** — surprising behavior, subtle bugs, non-obvious constraints.
     Written by the LLM at end-of-session when prompted "what surprised you?"
   - **Review finding** — unresolved critical/major findings from prior review
     sessions. These already exist in `review_store`; the provider reads them
     at retrieval time.
   - **Errata** — spec divergence pointers. Stored as `(spec_name, file_path)`
     pairs where `file_path` points to the errata document.

2. **LLM-gated ingestion for gotchas.** At end-of-session, the provider prompts
   the LLM: "Based on this session, what was surprising or non-obvious? What
   would you want to know if you were starting a new session on this spec?"
   The LLM returns 0-3 gotcha candidates. Each is stored with `spec_name`,
   `category='gotcha'`, and a confidence score. If the LLM returns nothing,
   nothing is stored. This is the "hard to write to" principle.

3. **Gotcha deduplication by content hash.** Before storing a gotcha, compute a
   SHA-256 hash of the normalized text. If a gotcha with the same hash already
   exists for the same spec, skip it. Simple, deterministic, no embedding
   similarity needed.

4. **Retrieve returns a flat list of strings.** The protocol's `retrieve()`
   returns `list[str]` — formatted text blocks ready for prompt injection. The
   engine does not need to understand the internal structure of knowledge items.
   Each string is prefixed with its category (`[GOTCHA]`, `[REVIEW]`,
   `[ERRATA]`) for LLM context.

5. **DuckDB storage in the existing knowledge database.** Gotchas are stored in
   a new `gotchas` table. Review findings are read from the existing
   `review_findings` table (no duplication). Errata entries are stored in a new
   `errata_index` table. No new database file.

6. **10-item retrieval cap.** `retrieve()` returns at most 10 items total:
   up to 5 gotchas (by recency), all unresolved critical/major review findings
   for the spec, and all errata pointers for the spec. If the total exceeds 10,
   gotchas are trimmed first (review findings and errata take priority).

7. **SIMPLE model tier for gotcha extraction.** The extraction prompt is short
   and the output is 0-3 sentences. Haiku-class models are sufficient. This
   keeps per-session knowledge overhead under $0.01.

8. **No embeddings, no vector search.** All retrieval is by direct column
   filters (`spec_name`, `category`, `status`). The old system's embedding
   pipeline (sentence-transformers, 384-dim, cosine similarity) added
   complexity without improving relevance. Scoped direct lookup is simpler
   and more predictable.

9. **Configuration via KnowledgeProviderConfig.** A new config section under
   `SDKConfig` specifying: provider class path, gotcha extraction model tier,
   max retrieval items, and gotcha TTL (days after which gotchas are
   auto-expired). Defaults: `max_items=10`, `gotcha_ttl_days=90`,
   `model_tier=SIMPLE`.

10. **Gotcha expiry.** Gotchas older than `gotcha_ttl_days` are marked expired
    and excluded from retrieval. This prevents unbounded accumulation — the
    primary failure mode of the old system.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 114_knowledge_decoupling | 1 | 1 | Implements the KnowledgeProvider protocol defined in spec 114 group 1; group 1 is where the protocol is first defined |

## Source

Source: Input provided by user via interactive prompt
