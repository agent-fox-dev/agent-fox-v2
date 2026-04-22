# Design Document: Knowledge System Decoupling

## Overview

This spec removes the low-value knowledge pipeline from agent-fox and
introduces a `KnowledgeProvider` protocol as the clean boundary between the
engine and any knowledge implementation. A `NoOpKnowledgeProvider` serves as
the default until spec 115 provides a real implementation.

## Architecture

The current architecture has 35+ knowledge modules imported at 63+ call sites
across engine, nightshift, session, and CLI. After this spec:

```
Engine / Nightshift / Session / CLI
         │
         ├── KnowledgeProvider protocol  (new boundary)
         │        │
         │        └── NoOpKnowledgeProvider  (default)
         │
         ├── review_store.py  (direct, retained)
         ├── audit.py  (direct, retained)
         ├── sink.py + duckdb_sink.py  (direct, retained)
         ├── db.py + migrations.py  (direct, retained)
         ├── blocking_history.py  (direct, retained)
         └── agent_trace.py  (direct, retained)
```

### KnowledgeProvider Protocol

```python
# agent_fox/knowledge/provider.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class KnowledgeProvider(Protocol):
    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict,
    ) -> None: ...

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
    ) -> list[str]: ...


class NoOpKnowledgeProvider:
    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict,
    ) -> None:
        pass

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
    ) -> list[str]:
        return []
```

### Integration Points

#### Pre-Session (Retrieval)

**Current** (`session_lifecycle.py` lines 262-285):
```python
retriever = AdaptiveRetriever(db, embedder, config.retrieval)
context = retriever.retrieve(spec_name, task_description, touched_files)
```

**After:**
```python
knowledge_items = provider.retrieve(spec_name, task_description)
```

The `provider` is passed to the session lifecycle from the engine, which
receives it at construction time.

#### Post-Session (Ingestion)

**Current** (`knowledge_harvest.py` lines 65-211):
```python
facts = extract_session_facts(transcript, ...)
tool_facts = extract_tool_calls(tool_log, ...)
sync_facts_to_duckdb(db, facts + tool_facts)
embedder.generate_batch(new_facts)
dedup_new_facts(db, new_facts, ...)
detect_contradictions(db, new_facts, ...)
store_causal_links(db, session_id, facts)
```

**After:**
```python
provider.ingest(session_id, spec_name, {
    "touched_files": touched_files,
    "commit_sha": commit_sha,
    "session_status": outcome.status,
})
```

#### Sync Barrier

**Current** (`barrier.py` lines 144-302):
```python
run_cleanup(db, config)
run_consolidation(db, embedder, config)
compact(db, config)
SleepComputer(db).run(context)
render_summary(db)
```

**After:**
```python
# Only rendering remains (summary of session outcomes, not knowledge)
render_summary(db)
```

#### Engine Construction

**Current** (`run.py` / `engine.py`):
```python
embedder = EmbeddingGenerator(config.knowledge)
# embedder threaded through engine, session_lifecycle, barrier
```

**After:**
```python
provider = NoOpKnowledgeProvider()  # or configured provider
# provider threaded through engine to session_lifecycle
```

### Files Deleted

#### `agent_fox/knowledge/` — Modules Removed

| File | Reason |
|------|--------|
| `extraction.py` | Fact extraction via LLM — never fired during sessions |
| `embeddings.py` | Sentence-transformer embedding generation |
| `search.py` | Vector similarity search |
| `retrieval.py` | 4-signal AdaptiveRetriever + RetrievalConfig re-export |
| `causal.py` | Causal chain storage and traversal |
| `lifecycle.py` | Fact dedup, contradiction detection, decay cleanup |
| `contradiction.py` | LLM contradiction classification |
| `consolidation.py` | Knowledge consolidation pipeline |
| `compaction.py` | Knowledge compaction |
| `entity_linker.py` | Fact-entity linking via git diff |
| `entity_query.py` | Entity graph traversal |
| `entity_store.py` | Entity graph CRUD |
| `entities.py` | Entity data models |
| `static_analysis.py` | Tree-sitter static analysis dispatcher |
| `git_mining.py` | Git pattern mining |
| `doc_mining.py` | Documentation mining |
| `sleep_compute.py` | Sleep-time compute pipeline |
| `code_analysis.py` | LLM code analysis for onboarding |
| `onboard.py` | Onboarding orchestrator |
| `project_model.py` | Project model aggregation |
| `query_oracle.py` | Oracle RAG pipeline |
| `query_patterns.py` | Pattern detection |
| `query_temporal.py` | Temporal query construction |
| `rendering.py` | Markdown summary rendering |
| `store.py` | Fact store with JSONL export |
| `ingest.py` | Background ingestion orchestrator |
| `facts.py` | Fact dataclass and related types |

#### `agent_fox/knowledge/lang/` — Entire Directory

All 17 language analyzers for tree-sitter static analysis.

#### `agent_fox/knowledge/sleep_tasks/` — Entire Directory

BundleBuilder, ContextRewriter, and related sleep task implementations.

#### `agent_fox/engine/knowledge_harvest.py`

Entire file deleted — extraction/lifecycle/causal orchestration.

### Files Modified

| File | Change |
|------|--------|
| `engine/session_lifecycle.py` | Remove AdaptiveRetriever, EmbeddingGenerator, RetrievalConfig imports. Replace retrieval block with `provider.retrieve()` call. |
| `engine/engine.py` | Remove end-of-run consolidation call. Accept KnowledgeProvider in constructor. Remove EmbeddingGenerator threading. |
| `engine/barrier.py` | Remove consolidation, compaction, sleep compute imports and calls. Keep rendering and session outcome cleanup. |
| `engine/run.py` | Remove EmbeddingGenerator construction, background ingestion. Construct KnowledgeProvider. |
| `engine/reset.py` | Remove compaction import. |
| `nightshift/engine.py` | Remove EmbeddingGenerator import and construction. |
| `nightshift/streams.py` | Remove sleep compute work stream. |
| `nightshift/ignore_ingest.py` | Remove Fact, git_mining, EmbeddingGenerator imports. |
| `nightshift/dedup.py` | Remove EmbeddingGenerator import. |
| `nightshift/ignore_filter.py` | Remove EmbeddingGenerator import. |
| `core/config.py` | Remove RetrievalConfig, SleepConfig. Simplify KnowledgeConfig to retain only `store_path`. |
| `cli/onboard.py` | Remove or disable onboard command. |
| `cli/nightshift.py` | Remove EmbeddingGenerator import. |
| `cli/status.py` | Remove project_model import. |
| `session/context.py` | Remove causal imports. Keep review_store imports (retained). |
| `fix/analyzer.py` | Remove EmbeddingGenerator, VectorSearch, Oracle, facts imports. |
| `reporting/status.py` | Remove store import. |
| `knowledge/__init__.py` | Update to reflect retained modules only. |

### Files Retained (No Changes)

| File | Reason |
|------|--------|
| `knowledge/review_store.py` | High-value: review findings influence coder behavior |
| `knowledge/duckdb_sink.py` | Operational: session outcome recording |
| `knowledge/audit.py` | Operational: structured event log |
| `knowledge/sink.py` | Operational: SessionSink protocol, SinkDispatcher |
| `knowledge/db.py` | Operational: DuckDB connection management |
| `knowledge/migrations.py` | Operational: schema migration runner |
| `knowledge/blocking_history.py` | Operational: blocking decision tracking |
| `knowledge/agent_trace.py` | Operational: JSONL trace logs |

### Configuration Changes

**Before:**
```python
class KnowledgeConfig(BaseModel):
    store_path: str = ".agent-fox/knowledge.duckdb"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    ask_top_k: int = 15
    ask_synthesis_model: str = "..."
    confidence_threshold: float = 0.6
    fact_cache_enabled: bool = True
    dedup_similarity_threshold: float = 0.92
    contradiction_similarity_threshold: float = 0.85
    contradiction_model: str = "..."
    decay_half_life_days: float = 30.0
    decay_floor: float = 0.3
    cleanup_fact_threshold: float = 0.2
    cleanup_enabled: bool = True
    retrieval: RetrievalConfig
    sleep: SleepConfig
```

**After:**
```python
class KnowledgeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    store_path: str = ".agent-fox/knowledge.duckdb"
```

The `extra="ignore"` ensures existing config files with old fields still parse
without errors.

## Correctness Properties

### CP-1: No Dead Imports

**Property:** After all changes, `python -c "import agent_fox"` succeeds with
zero `ImportError` exceptions.

**Validation:** [114-REQ-7.5], [114-REQ-10.1]

### CP-2: Protocol Satisfaction

**Property:** `isinstance(NoOpKnowledgeProvider(), KnowledgeProvider)` returns
`True`.

**Validation:** [114-REQ-1.2], [114-REQ-2.1]

### CP-3: Engine Isolation

**Property:** No file in `agent_fox/engine/` imports any module listed in the
"Modules Removed" table above.

**Validation:** [114-REQ-3.2], [114-REQ-4.2], [114-REQ-5.1]

### CP-4: Nightshift Isolation

**Property:** No file in `agent_fox/nightshift/` imports `EmbeddingGenerator`,
`SleepComputer`, `SleepContext`, `BundleBuilder`, or `ContextRewriter`.

**Validation:** [114-REQ-6.1], [114-REQ-6.2], [114-REQ-6.3]

### CP-5: Config Backward Compatibility

**Property:** A config file containing all old KnowledgeConfig fields loads
without raising `ValidationError`.

**Validation:** [114-REQ-8.5]

### CP-6: Retrieval Error Isolation

**Property:** If `KnowledgeProvider.retrieve()` raises any exception, the
session still starts successfully with empty knowledge context.

**Validation:** [114-REQ-3.E1]

### CP-7: Review Store Independence

**Property:** `review_store.py` functions (`query_active_findings`,
`insert_findings`) continue to work identically before and after the
decoupling.

**Validation:** [114-REQ-10.1]
