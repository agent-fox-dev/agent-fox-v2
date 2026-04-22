# PRD: Knowledge System Decoupling

## Problem Statement

The knowledge system is deeply entangled with the engine and nightshift modules.
An end-to-end evaluation on a 9-spec parking-fee-service build (83 sessions,
$147 cost) established that the majority of the knowledge pipeline produces no
actionable value:

- **50 facts injected into every session** regardless of relevance (hard cap).
- **56% of facts** are generic "git" category with no spec association.
- **Entity graph** has 2,116 entities but only "contains" edges — no call-graph
  or dependency edges. The entity signal always receives `touched_files=[]`.
- **Causal chains** are tracked but never consumed by any downstream component.
- **Fact extraction** never fires during sessions (2,000-char transcript
  minimum vs 350-918 char summaries). All facts are ingested at end-of-run.
- **Contradiction detection** found 0 contradictions across 641 facts.
- **Compaction** superseded 1 of 166 facts — append-only noise accumulation.
- **Sleep-time compute** pre-computes bundles for a retrieval pipeline that
  returns noise.

Meanwhile, the components that genuinely influence agent behavior are:

- **Review findings** — 80 pre-review findings influenced coder behavior in 5
  documented instances, via direct prompt injection (not the embedding pipeline).
- **Session outcomes** — operational data (tokens, duration, touched files)
  consumed by the engine for scheduling and reporting.
- **Audit events** — structured event log used for observability.
- **Blocking history** — decision tracking for convergence detection.

The knowledge system's 35+ files import into 15+ engine/nightshift/session/CLI
files at 63+ call sites. This coupling prevents replacing the knowledge system
without touching most of the codebase. This spec untangles those dependencies
so the low-value components can be removed cleanly.

## Goals

1. **Define a KnowledgeProvider protocol** that captures the boundary between
   the engine and any knowledge implementation. The engine calls this protocol;
   it never imports knowledge internals directly.

2. **Remove all low-value knowledge components** — the embedding pipeline,
   vector search, 4-signal retrieval, fact extraction, causal chains,
   contradiction detection, entity graph, sleep compute, static analysis,
   onboarding, compaction, consolidation, and the 17 language analyzers.

3. **Keep high-value operational components** — review store, DuckDB sink
   (session outcomes), audit events, session sink protocol, blocking history,
   agent trace, and schema migrations.

4. **Clean up all engine integration points** so that removed components leave
   no dead imports, dead config, or dead code paths.

5. **Provide a no-op KnowledgeProvider** implementation so the engine runs
   correctly with zero knowledge overhead until spec 115 introduces a real
   implementation.

6. **Supersede specs 112 and 113** — both attempted to improve a system that
   should be replaced, not patched.

## Non-Goals

- Building a new knowledge system (that is spec 115).
- Changing the review findings system (it already works).
- Modifying the SessionSink protocol or DuckDB sink (they are operational, not
  knowledge).
- Removing the audit event system.
- Changing the engine's session scheduling or task graph logic.

## Design Decisions

1. **KnowledgeProvider as a Python Protocol.** The boundary is a
   `typing.Protocol` with two methods: `ingest(session_id, spec_name, context)`
   and `retrieve(spec_name, task_description) -> list[str]`. The engine calls
   these at well-defined points (post-session for ingest, pre-session for
   retrieve). No other knowledge imports are permitted in engine code.

2. **NoOpKnowledgeProvider as the initial implementation.** `ingest()` is a
   no-op. `retrieve()` returns an empty list. This makes the engine functional
   immediately after removal with zero knowledge overhead.

3. **Review findings remain a direct dependency, not behind the protocol.**
   Review findings are consumed by the session context builder and the preflight
   module via `review_store.py`. They are high-value and tightly integrated.
   Routing them through a generic knowledge protocol would add indirection with
   no benefit. They stay as direct imports.

4. **Audit, sink, and DuckDB connection management stay in `knowledge/`.**
   These modules (`audit.py`, `sink.py`, `duckdb_sink.py`, `db.py`,
   `migrations.py`, `blocking_history.py`, `agent_trace.py`) are operational
   infrastructure, not the knowledge pipeline. They remain in place and continue
   to be imported directly. A future refactor could move them to a dedicated
   `storage/` package, but that is out of scope.

5. **KnowledgeConfig is simplified.** Fields related to removed components
   (embedding model, dedup thresholds, contradiction thresholds, decay settings,
   sleep config, retrieval config) are removed from `KnowledgeConfig`. Only
   `store_path` remains. A new `KnowledgeProviderConfig` may be introduced by
   spec 115.

6. **Engine files cleaned up in-place.** `session_lifecycle.py` loses its
   retrieval context assembly. `knowledge_harvest.py` is deleted entirely.
   `barrier.py` loses consolidation/compaction/sleep-compute calls.
   `engine.py` loses end-of-run consolidation. Nightshift files lose embedding
   and sleep-compute imports.

7. **facts.py and store.py are removed.** The `Fact` dataclass and fact store
   are part of the old pipeline. The new system (spec 115) will define its own
   data model. Any code that imports `Fact` is part of the removal set.

8. **Removed modules are deleted, not stubbed.** No backward-compatibility
   shims, no re-exports, no deprecation warnings. The files are deleted and all
   imports are removed. If something breaks, it surfaces immediately in tests.

9. **The `knowledge/lang/` directory (17 language analyzers) is deleted
   entirely.** These power the tree-sitter static analysis for the entity graph,
   which is being removed.

10. **Schema tables for removed features are left in place.** The DuckDB tables
    (`memory_facts`, `memory_embeddings`, `entity_graph`, `entity_edges`,
    `causal_links`, `sleep_artifacts`, etc.) are not dropped. Existing databases
    continue to work. The tables simply stop being written to or read from. A
    future migration can drop them.

## Supersedes

This spec supersedes:

- **Spec 112 (Sleep-Time Compute):** The sleep compute pipeline pre-computes
  artifacts for a retrieval system that is being removed. There is no value in
  optimizing a system that produces noise.
- **Spec 113 (Knowledge Effectiveness):** This spec attempted to fix the
  existing knowledge pipeline (full transcript capture, LLM git extraction,
  entity signal activation, cold-start skip). The evaluation showed the
  fundamental architecture is flawed — fixing individual components does not
  address the core problem of irrelevant fact injection.

## Dependencies

This spec has no upstream dependencies. It is a removal/refactoring spec that
operates on the existing codebase.

Spec 115 (Pluggable Knowledge Provider) depends on this spec — it implements
the KnowledgeProvider protocol defined here.

## Source

Source: Input provided by user via interactive prompt
