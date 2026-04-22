# Implementation Tasks: Knowledge System Decoupling

## Task Group 1: Protocol Definition and NoOp Implementation

### Tasks

- [ ] Create `agent_fox/knowledge/provider.py` with `KnowledgeProvider` protocol
  and `NoOpKnowledgeProvider` class
  - Protocol: `@runtime_checkable`, two methods: `ingest()`, `retrieve()`
  - NoOp: `ingest()` returns None, `retrieve()` returns `[]`
  - Ref: [114-REQ-1.1], [114-REQ-1.2], [114-REQ-1.3], [114-REQ-1.4],
    [114-REQ-2.1], [114-REQ-2.2], [114-REQ-2.3]

- [ ] Write tests for protocol and NoOp in
  `tests/unit/knowledge/test_provider.py`
  - TC-1.1 through TC-1.5, TC-2.1, TC-2.2
  - Ref: [114-REQ-10.2]

### Verification

```bash
uv run pytest tests/unit/knowledge/test_provider.py -v
```

Confirm: protocol is runtime-checkable, NoOp satisfies it, retrieve returns
empty list, ingest is side-effect-free.

---

## Task Group 2: Engine Integration Points

### Tasks

- [ ] Modify `engine/engine.py` to accept `KnowledgeProvider` in constructor
  - Remove end-of-run consolidation call (lines ~657-680)
  - Remove `EmbeddingGenerator` imports and threading
  - Pass provider to session lifecycle
  - Ref: [114-REQ-3.1], [114-REQ-4.1]

- [ ] Modify `engine/session_lifecycle.py` to use `KnowledgeProvider`
  - Remove `AdaptiveRetriever`, `EmbeddingGenerator`, `RetrievalConfig` imports
  - Replace retrieval block (lines ~262-285) with `provider.retrieve()` call
  - Wrap retrieve in try/except, log warning on failure, proceed with empty context
  - Replace knowledge harvest call with `provider.ingest()` call
  - Wrap ingest in try/except, log warning on failure, continue
  - Ref: [114-REQ-3.1], [114-REQ-3.2], [114-REQ-3.E1], [114-REQ-4.1],
    [114-REQ-4.2], [114-REQ-4.E1]

- [ ] Delete `engine/knowledge_harvest.py`
  - Ref: [114-REQ-4.3]

- [ ] Modify `engine/run.py`
  - Remove `EmbeddingGenerator` construction
  - Remove `run_background_ingestion` import and call
  - Construct `NoOpKnowledgeProvider` (or configured provider) and pass to engine
  - Ref: [114-REQ-2.4]

- [ ] Write tests in `tests/unit/engine/test_session_lifecycle_provider.py`
  - TC-4.1: retrieve exception does not block session start
  - TC-5.1: ingest exception does not block session completion
  - Ref: [114-REQ-3.E1], [114-REQ-4.E1]

### Verification

```bash
uv run pytest tests/unit/engine/test_session_lifecycle_provider.py -v
python -c "from agent_fox.engine import engine, session_lifecycle, run"
```

Confirm: engine modules import cleanly, error isolation works.

---

## Task Group 3: Barrier and Nightshift Cleanup

### Tasks

- [ ] Modify `engine/barrier.py`
  - Remove imports: `run_consolidation`, `compact`, `SleepComputer`,
    `SleepContext`, `BundleBuilder`, `ContextRewriter`, `run_cleanup`
  - Remove consolidation, compaction, sleep compute calls from
    `run_sync_barrier_sequence()`
  - Keep rendering and session outcome cleanup
  - Ref: [114-REQ-5.1], [114-REQ-5.2]

- [ ] Modify `engine/reset.py`
  - Remove `compaction` import

- [ ] Modify `nightshift/engine.py`
  - Remove `EmbeddingGenerator` import and construction
  - Ref: [114-REQ-6.1]

- [ ] Modify `nightshift/streams.py`
  - Remove sleep compute work stream
  - Remove `SleepComputer`, `SleepContext`, `BundleBuilder`, `ContextRewriter`
    imports
  - Ref: [114-REQ-6.2], [114-REQ-6.3]

- [ ] Modify `nightshift/ignore_ingest.py`
  - Remove `Fact`, `_write_fact`, `EmbeddingGenerator`, `SinkDispatcher`
    imports from knowledge modules that are being deleted
  - Ref: [114-REQ-6.4]

- [ ] Modify `nightshift/dedup.py`
  - Remove `EmbeddingGenerator` import
  - Ref: [114-REQ-6.4]

- [ ] Modify `nightshift/ignore_filter.py`
  - Remove `EmbeddingGenerator` import
  - Ref: [114-REQ-6.4]

- [ ] Write tests in `tests/unit/engine/test_barrier_cleanup.py`
  - TC-9.1: barrier source has no removed imports
  - TC-9.2: barrier still runs rendering
  - Ref: [114-REQ-5.1], [114-REQ-5.2]

### Verification

```bash
uv run pytest tests/unit/engine/test_barrier_cleanup.py -v
python -c "from agent_fox.engine import barrier; from agent_fox.nightshift import engine, streams"
```

Confirm: barrier and nightshift modules import cleanly without removed modules.

---

## Task Group 4: Module Deletion

### Tasks

- [ ] Delete knowledge modules listed in [114-REQ-7.1]:
  `extraction.py`, `embeddings.py`, `search.py`, `retrieval.py`, `causal.py`,
  `lifecycle.py`, `contradiction.py`, `consolidation.py`, `compaction.py`,
  `entity_linker.py`, `entity_query.py`, `entity_store.py`, `entities.py`,
  `static_analysis.py`, `git_mining.py`, `doc_mining.py`, `sleep_compute.py`,
  `code_analysis.py`, `onboard.py`, `project_model.py`, `query_oracle.py`,
  `query_patterns.py`, `query_temporal.py`, `rendering.py`, `store.py`,
  `ingest.py`, `facts.py`

- [ ] Delete `agent_fox/knowledge/lang/` directory entirely
  - Ref: [114-REQ-7.2]

- [ ] Delete `agent_fox/knowledge/sleep_tasks/` directory entirely
  - Ref: [114-REQ-7.3]

- [ ] Update `agent_fox/knowledge/__init__.py` to reference only retained modules

- [ ] Fix remaining imports in session, fix, reporting, and graph modules:
  - `session/context.py`: remove causal imports (keep review_store)
  - `fix/analyzer.py`: remove EmbeddingGenerator, VectorSearch, Oracle, facts imports
  - `reporting/status.py`: remove store import
  - `graph/planner.py`: verify db import still works (db.py is retained)

### Verification

```bash
python -c "import agent_fox"
ls agent_fox/knowledge/lang/ 2>&1 | grep -q "No such file"
ls agent_fox/knowledge/sleep_tasks/ 2>&1 | grep -q "No such file"
ls agent_fox/engine/knowledge_harvest.py 2>&1 | grep -q "No such file"
```

Confirm: all listed files and directories are gone, import succeeds.

---

## Task Group 5: Configuration and CLI Cleanup

### Tasks

- [ ] Simplify `KnowledgeConfig` in `core/config.py`
  - Remove: `embedding_model`, `embedding_dimensions`, `ask_top_k`,
    `ask_synthesis_model`, `confidence_threshold`, `fact_cache_enabled`,
    `dedup_similarity_threshold`, `contradiction_similarity_threshold`,
    `contradiction_model`, `decay_half_life_days`, `decay_floor`,
    `cleanup_fact_threshold`, `cleanup_enabled`
  - Remove `retrieval: RetrievalConfig` and `sleep: SleepConfig` fields
  - Delete `RetrievalConfig` and `SleepConfig` classes
  - Keep `store_path` with default
  - Ensure `extra="ignore"` for backward compatibility
  - Ref: [114-REQ-8.1] through [114-REQ-8.5]

- [ ] Remove or disable `cli/onboard.py` command
  - Ref: [114-REQ-9.1]

- [ ] Clean up `cli/nightshift.py` — remove EmbeddingGenerator import
  - Ref: [114-REQ-9.2]

- [ ] Clean up `cli/status.py` — remove project_model import
  - Ref: [114-REQ-9.3]

- [ ] Verify `cli/plan.py` still works with db.open_knowledge_store
  - Ref: [114-REQ-9.4]

- [ ] Write config backward compatibility test in
  `tests/unit/core/test_config_knowledge.py`
  - TC-6.1: old fields are ignored
  - TC-6.2: store_path default preserved

### Verification

```bash
uv run pytest tests/unit/core/test_config_knowledge.py -v
python -c "from agent_fox.cli import onboard" 2>&1  # should fail or show disabled
python -c "from agent_fox.core.config import KnowledgeConfig; c = KnowledgeConfig(); print(c.store_path)"
```

Confirm: config loads with old fields, store_path default works, CLI commands
import cleanly.

---

## Task Group 6: Test Suite Cleanup and Final Verification

### Tasks

- [ ] Identify and delete test files that exclusively test removed modules
  - Tests for: extraction, embeddings, search, retrieval, causal, lifecycle,
    contradiction, consolidation, compaction, entity_linker, entity_query,
    entity_store, static_analysis, git_mining, doc_mining, sleep_compute,
    code_analysis, onboard, project_model, query_oracle, query_patterns,
    query_temporal, rendering, store, ingest, facts, knowledge_harvest
  - Ref: [114-REQ-7.E1], [114-REQ-10.4]

- [ ] Update remaining test files that import from deleted modules
  - Ref: [114-REQ-7.E1]

- [ ] Write import isolation test in `tests/unit/test_import_isolation.py`
  - TC-3.1: engine modules don't import removed modules
  - TC-3.2: nightshift modules don't import removed modules
  - TC-3.3: full import succeeds
  - TC-7.1 through TC-7.4: deleted files don't exist
  - TC-10.1: CLI modules don't import removed modules

- [ ] Run `make check` — full lint + test suite
  - Ref: [114-REQ-10.1]

### Verification

```bash
make check
```

Confirm: zero test failures, zero lint errors, zero import errors.
All correctness properties (CP-1 through CP-7) validated.
