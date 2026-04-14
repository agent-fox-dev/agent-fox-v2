---
Title: 05. Adopt MAGMA multi-graph memory architecture
Date: 2026-04-14
Status: Accepted
---

## Context

agent-fox accumulates knowledge across coding sessions — facts about the
codebase, gotchas, patterns, and causal relationships discovered during
implementation. This knowledge must be stored, maintained, and surfaced to
future sessions so the agent avoids repeating mistakes and benefits from prior
discoveries.

Early versions used a flat fact store (DuckDB `memory_facts` table) with
keyword-based retrieval and basic causal linking. As the project scaled to
50+ spec runs, three problems emerged:

1. **Semantic-only retrieval misses structural context.** Embedding similarity
   finds topically-related facts but cannot answer "what facts relate to this
   module's dependencies?" — a question that requires traversing code structure.

2. **Cross-spec knowledge is siloed.** Facts extracted in spec 3 and spec 7
   about the same module don't know about each other. Redundant facts
   accumulate; genuine patterns go unrecognized.

3. **Stale knowledge persists.** Facts referencing deleted files or heavily
   refactored code remain at full confidence, polluting context with outdated
   information.

The MAGMA paper (Jiang et al., "A Multi-Graph based Agentic Memory
Architecture for AI Agents", arXiv:2601.03236, January 2026) proposes a
multi-graph memory architecture that addresses these problems through
orthogonal graph representations and policy-guided retrieval.

## Decision Drivers

- Knowledge must be retrievable by **structure** (code topology), not only by
  **semantics** (embedding similarity).
- Cross-spec facts must be consolidated: redundancies merged, patterns
  elevated, stale entries decayed or removed.
- The solution must integrate with the existing DuckDB-based knowledge store
  and per-session harvest pipeline without requiring a migration to an external
  graph database.
- Retrieval latency must not block session startup — precomputed caches are
  acceptable.

## Options Considered

### Option A: Full MAGMA replication

Implement all four MAGMA graphs (semantic, temporal, causal, entity) with
policy-guided beam-search retrieval, query intent classification
(Why/When/Entity), Reciprocal Rank Fusion for anchor scoring, and
salience-based token budgeting for narrative synthesis.

**Pros:**
- Theoretically optimal retrieval quality (0.700 judge score on LoCoMo
  benchmark, 18-45% above baselines).
- Adversarial query robustness from multi-signal fusion.

**Cons:**
- MAGMA's retrieval policy is designed for conversational memory (human
  dialogues) — the Why/When/Entity intent taxonomy doesn't map cleanly to a
  coding agent's queries (which are more like "what do I need to know about
  this module before editing it?").
- Full temporal graph (immutable chronological chain) adds storage and
  complexity with unclear value — coding facts don't have the same temporal
  narrative structure as human conversations.
- Significant implementation effort for the adaptive traversal policy,
  RRF fusion, and narrative synthesis stages.

### Option B: Selective MAGMA adoption — graphs and consolidation first

Implement MAGMA's storage substrate (entity graph, causal graph, semantic
embeddings) and its asynchronous consolidation architecture, but defer the
adaptive retrieval policy. Use the existing keyword + causal retrieval path,
augmented with entity-graph queries, as the initial retrieval mechanism.

**Pros:**
- Solves the three identified problems (structural retrieval, cross-spec
  consolidation, staleness detection) without over-engineering retrieval.
- Entity graph is domain-adapted: nodes are codebase structures
  (files, modules, classes, functions) rather than abstract entity
  references — a better fit for a coding agent.
- Consolidation pipeline maps cleanly to MAGMA's dual-stream architecture
  (fast harvest path + slow consolidation path at sync barriers).
- Retrieval policy can be added incrementally once the graph substrate proves
  its value.

**Cons:**
- Leaves MAGMA's strongest innovation (policy-guided traversal) unimplemented.
- Retrieval remains caller-driven rather than query-adaptive — the system
  doesn't yet dynamically decide which graph to prioritize based on what the
  agent is asking.

### Option C: Custom graph without MAGMA influence

Design a bespoke knowledge graph tailored entirely to code-agent needs without
reference to MAGMA's architecture.

**Pros:**
- No conceptual impedance mismatch with a conversational-memory paper.

**Cons:**
- Loses the benefit of MAGMA's well-evaluated design: the ablation study
  demonstrates that each graph contributes non-substitutable value.
- Higher risk of ad-hoc design decisions without a principled framework.

## Decision

We adopted **Option B: selective MAGMA adoption** — implement the multi-graph
storage substrate and asynchronous consolidation, defer the adaptive retrieval
policy. This was implemented across three specs:

- **Spec 94** (cross-spec vector retrieval): Semantic graph — `VectorSearch`
  over `memory_embeddings` using DuckDB cosine distance.
- **Spec 95** (entity graph): Entity graph — `entity_graph`, `entity_edges`,
  `fact_entities` tables with tree-sitter-based static analysis for entity
  extraction and BFS traversal for structural queries.
- **Spec 96** (knowledge consolidation): Asynchronous consolidation pipeline —
  6-step process (entity refresh, fact linking, git verification, cross-spec
  merging, pattern promotion, causal pruning) triggered at sync barriers.

The rationale: MAGMA's multi-graph substrate is a prerequisite for any future
retrieval policy work. Building the graphs first gives us immediate value
(structural queries, staleness detection, cross-spec dedup) while creating the
foundation for adaptive retrieval later.

## What Is Implemented vs. MAGMA

### Implemented (aligned with MAGMA)

| MAGMA Concept | agent-fox Component | Notes |
|---------------|---------------------|-------|
| **Entity graph** | `entity_graph` + `entity_edges` + `fact_entities` (spec 95) | Domain-adapted: nodes are code structures (file, module, class, function); edges are `contains`, `imports`, `extends`. MAGMA uses abstract entity nodes for people/places/concepts. |
| **Causal graph** | `fact_causes` table, causal chain pruning (spec 96) | Directed edges between facts. LLM evaluates redundant intermediaries (A->B->C with direct A->C). |
| **Semantic graph** | `memory_embeddings` + `VectorSearch` (spec 94) | Cosine similarity over embeddings. Cross-spec merging clusters at >0.85 threshold. |
| **Dual-stream ingestion** | Fast: per-session `extract_and_store_knowledge`. Slow: `run_consolidation` at sync barriers. | Maps to MAGMA's synaptic ingestion (non-blocking) vs. structural consolidation (async LLM). |
| **Consolidation** | 6-step pipeline in `consolidation.py` (spec 96) | Entity refresh, fact linking, git verification, cross-spec merging, pattern promotion, causal pruning. |
| **Staleness detection** | Git verification step supersedes facts when linked files are deleted; halves confidence when files change >50% (spec 96) | MAGMA doesn't address staleness — this is an agent-fox addition beyond the paper. |
| **Pattern elevation** | Facts spanning 3+ specs promoted to `category=pattern` with LLM confirmation (spec 96) | Not in MAGMA. agent-fox extends the consolidation concept. |

### Not Implemented (gaps relative to MAGMA)

| MAGMA Concept | Status | Impact |
|---------------|--------|--------|
| **Temporal graph** | No explicit temporal edges between facts. Timestamps exist on facts (`created_at`) but are not a traversable graph structure. | Low impact for coding agents. Code facts don't have the narrative temporal structure that MAGMA's temporal backbone supports. Temporal ordering is implicitly available via timestamps if needed. |
| **Query intent classification** | Not present. No decomposition of queries into Why/When/Entity types. | Medium impact. The system cannot dynamically adjust retrieval strategy based on what the agent needs. All queries follow the same keyword + causal path. |
| **Adaptive traversal policy** | Not present. Entity graph BFS traversal uses uniform edge weighting. No beam search with `S(n_j|n_i, q) = exp(lambda_1 * phi + lambda_2 * sim)`. | High impact. This is MAGMA's core retrieval innovation. Without it, the four graphs are queried independently rather than fused into a coherent retrieval signal. |
| **Reciprocal Rank Fusion** | Not present. Vector search and entity-graph retrieval are separate code paths invoked by different callers. No unified anchor scoring. | High impact. Related to the missing adaptive policy. Multiple retrieval signals exist but aren't combined. |
| **Narrative synthesis** | Not present. Facts are injected into system prompts as a flat list via `enhance_with_causal`. No topological ordering, provenance scaffolding, or salience-based token budgeting. | Medium impact. Context quality depends on how facts are arranged; flat injection may include irrelevant facts or present them in suboptimal order. |

### Intentional Divergences (not gaps)

| MAGMA | agent-fox | Rationale |
|-------|-----------|-----------|
| Abstract entity nodes (people, places, concepts) | Code-structural entities (files, modules, classes, functions) | Domain adaptation. A coding agent needs codebase topology, not entity resolution across dialogue timelines. |
| Immutable temporal chain | Mutable fact lifecycle (supersession, confidence decay) | Code facts become stale; MAGMA's conversational memories don't. Mutability is necessary. |
| Single-agent memory | Multi-archetype memory (coder, reviewer, auditor share facts) | agent-fox's multi-archetype design means facts flow between agent roles — a dimension MAGMA doesn't address. |
| No staleness handling | Git verification + confidence decay | MAGMA doesn't need this (conversation history doesn't go stale). Coding agents do. |

## Consequences

### Positive

- The entity graph enables structural queries ("what facts relate to this
  module's import chain?") that pure vector search cannot answer.
- Cross-spec consolidation reduces fact redundancy and surfaces patterns that
  individual session harvests miss.
- Git verification automatically decays or removes facts about deleted or
  heavily refactored code.
- The multi-graph substrate is in place as a foundation for future adaptive
  retrieval work.

### Negative / Trade-offs

- The highest-value MAGMA innovation — policy-guided traversal — is not yet
  implemented. The graphs exist but retrieval doesn't fuse them intelligently.
- Current fact injection (`select_relevant_facts` + `enhance_with_causal`) is
  keyword-based with causal augmentation. It doesn't leverage the entity graph
  for retrieval, only for consolidation.
- The entity graph is populated during consolidation (sync barriers) rather
  than incrementally during sessions. There can be a lag between code changes
  and entity graph updates.

### Neutral / Follow-up actions

- A future spec should implement **adaptive retrieval** that fuses entity-graph
  traversal, vector search, and causal chain following into a unified retrieval
  path — analogous to MAGMA's policy-guided traversal but adapted for
  code-agent query patterns (e.g., "what do I need to know before editing this
  module?" rather than Why/When/Entity).
- Consider whether **context assembly** (the narrative synthesis stage) should
  order facts by causal precedence and apply token budgeting, rather than flat
  injection.
- The temporal graph is intentionally deferred. Revisit if session ordering
  proves important for fact relevance (e.g., "what did we learn in recent
  sessions about this area?").

## References

- Jiang, D., Li, Y., Li, G., Li, B. "MAGMA: A Multi-Graph based Agentic
  Memory Architecture for AI Agents." arXiv:2601.03236, January 2026.
  https://arxiv.org/abs/2601.03236
- Spec 94: `.specs/archive/94_cross_spec_vector_retrieval/`
- Spec 95: `.specs/95_entity_graph/`
- Spec 96: `.specs/96_knowledge_consolidation/`
- Spec 102: `.specs/102_multilang_entity_graph/` (multi-language extension)
