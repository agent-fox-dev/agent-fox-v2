Let me do a thorough analysis. I'll start by reading the key orientation files, then dive deep into the codebase.

Now let me read more key files — knowledge system, session, graph, and nightshift:

Now let me look at a few more areas — the `__pycache__` ghost modules, the `select_context_with_causal` dead code, and some other specific areas:

Now let me check a few more specific areas — the `__pycache__` ghost modules, the `_barrier_sync` no-op, and some other patterns:

Now I have a thorough picture of the codebase. Let me compile the full analysis:

I now have a comprehensive picture of the entire codebase. Here's the deep analysis:

---

## Deep Codebase Analysis

### 1. Dead Code

**`select_context_with_causal()` — zombie function**
In `session/context.py` (and re-exported from `session/prompt.py`), this function's body is a stub that just returns `keyword_facts[:max_facts]`. The causal traversal was removed in spec 114, but the function, its parameters (`conn`, `spec_name`, `causal_budget`), its tests, and its re-export all remain. The `conn` and `causal_budget` parameters are accepted and silently ignored. This is dead API surface that misleads readers.

**`causal_context_limit` config field — orphaned**
`OrchestratorConfig.causal_context_limit` (lines 166–175 of `config.py`) is defined, documented, clamped, and tested — but never read anywhere in the production codebase. The causal system it controlled was removed in spec 114. The field is pure config noise.

**`_barrier_sync()` — no-op with a test**
`engine/run.py` defines `_barrier_sync()` which does exactly one thing: sets `infra["_barrier_ingestion_ran"] = True`. There's a unit test that asserts this flag is set. The function exists only as a tombstone of the removed knowledge ingestion pipeline. The barrier callback wiring, the function, and its test can all be removed.

**`routing_assessments` and `routing_pipeline` in `SessionResultHandler`**
Both are accepted as constructor parameters, stored as instance attributes (`self._routing_assessments`, `self._routing_pipeline`), and never read again anywhere in the class or its callers. They're vestigial from a routing refactor.

**`_build_fallback_input()` in `NodeSessionRunner`**
This method uses `subprocess.run(["git", "diff", ...])` — a synchronous subprocess call inside an async class — to build a fallback transcript. It's only called when the agent trace is unavailable. The method is fine conceptually, but the `import subprocess` is buried inside the method body (a lazy import anti-pattern the codebase's own memory.md warns about), and the method duplicates git-running logic that already exists in `workspace/git.py`.

**`_query_false_positives()` in `NightShiftEngine`**
Queries `memory_facts WHERE category = 'anti_pattern'`. The `memory_facts` table was dropped in migration v18 (spec 116). On any database that has run migrations, this query will silently return `[]` (the `except Exception` swallows the error). The method is effectively always a no-op on current databases.

**Ghost `__pycache__` entries**
The `__pycache__` directories contain `.pyc` files for modules that no longer exist as source: `onboard.cpython-312.pyc` (cli), `assessment.cpython-312.pyc`, `knowledge_harvest.cpython-312.pyc`, `improve_report.cpython-312.pyc`, `fix_types.cpython-312.pyc`, `state.cpython-312.pyc` (nightshift), `stream.cpython-312.pyc`, `config.cpython-312.pyc` (nightshift), `extraction.cpython-312.pyc`, `ignore_ingest.cpython-312.pyc`, and many more. These are harmless but indicate the cleanup passes didn't run `find . -name __pycache__ -exec rm -rf {} +`.

---

### 2. Code Smells

**`dispatch.py` accesses private Orchestrator internals via `orch._*`**
`SerialDispatcher` and `ParallelDispatcher` both hold a reference to the `Orchestrator` and access `orch._graph_sync`, `orch._result_handler`, `orch._parallel_runner`, `orch._signal`, `orch._config`, `orch._run_id`, `orch._routing`, etc. This is a classic "feature envy" smell — the dispatchers know too much about the orchestrator's internals. The extraction was done to reduce file size, but the coupling is unchanged. The `assert orch._graph_sync is not None  # noqa: S101` guards are a symptom: they're runtime assertions on invariants that should be enforced by construction.

**`_get_node_archetype()` / `_get_node_mode()` duplicated**
These two methods exist identically in both `engine.py` (on `Orchestrator`) and `result_handler.py` (on `SessionResultHandler`). Both do the same thing: look up a node in `self._graph` and return its archetype/mode. The duplication exists because `SessionResultHandler` was extracted from `Orchestrator` but was given its own copy of `_graph` rather than a shared accessor.

**`SessionOutcome` has a `touched_paths: list[str]` field, but `session_lifecycle.py` constructs `SessionRecord` with `files_touched`**
There are two parallel "files touched" concepts: `SessionOutcome.touched_paths` (from `sink.py`) and `SessionRecord.files_touched` (from `state.py`). The `SessionOutcome` returned by `run_session()` doesn't populate `touched_paths` — that field is always empty. The actual file list comes from `harvest()` and is stored in `SessionRecord.files_touched`. The `touched_paths` field on `SessionOutcome` is misleading dead weight.

**`SinkDispatcher` has two dispatch mechanisms**
The core protocol methods (`record_session_outcome`, `record_tool_call`, etc.) use `self._dispatch(method, *args)` — a clean generic dispatcher. But the trace-specific methods (`record_session_init`, `record_assistant_message`, `record_tool_use`, etc.) each have their own hand-rolled `for sink in self._sinks: if hasattr(sink, method): try: sink.method(...) except: ...` loop. This is ~150 lines of near-identical boilerplate. A single `_dispatch_optional(method, **kwargs)` helper would collapse all of it.

**`Orchestrator.__init__` has 17 parameters**
The constructor signature is extremely wide. Several of these (`audit_dir`, `audit_db_conn`, `knowledge_db_conn`, `sink_dispatcher`, `platform`) are infrastructure concerns that could be grouped into a single `OrchestratorInfra` dataclass, making the construction site in `run.py` cleaner and the class easier to test.

**`_REVIEW_ARCHETYPES` frozenset defined in `session_lifecycle.py` but used in `dispatch.py`**
The frozenset `{"reviewer", "skeptic", "verifier", "oracle", "auditor"}` is defined in `session_lifecycle.py` and imported into `dispatch.py`. It's a cross-cutting constant that logically belongs in `archetypes.py` alongside the registry, not in a lifecycle module.

**`_iter_valid_items()` in `review_parser.py` — good extraction, but the three callers still have near-identical warning messages**
The shared generator was a good refactor, but `parse_review_findings`, `parse_verification_results`, and `parse_drift_findings` each end with `if not results: logger.warning("No valid X extracted from Y output")`. This pattern could be pushed into a thin wrapper.

---

### 3. Anti-Patterns

**`assert` used as control flow in production code**
`dispatch.py` uses `assert orch._graph_sync is not None  # noqa: S101` (and similar) as runtime guards. These are suppressed by `-O` (optimized Python) and are semantically wrong — they're not debugging assertions, they're precondition checks. They should be `if ... is None: raise RuntimeError(...)` or the invariant should be enforced at construction time.

**Lazy imports inside method bodies — inconsistently applied**
The codebase's own `memory.md` documents this as a gotcha: "Moving imports from function-local scope to module-level is necessary for test patches to work correctly." Yet `session/context.py` has `from agent_fox.knowledge.review_store import ...` inside `render_drift_context()`, `render_review_context()`, `render_verification_context()`, and `_migrate_legacy_files()`. `result_handler.py` has `from agent_fox.knowledge.errata import ...` inside `_generate_errata()`. `engine/state.py` has `from agent_fox.core.config import PricingConfig` inside `update_state_with_session()`. These are inconsistent with the module-level import style used elsewhere and make mocking harder.

**`subprocess.run` inside an async method without `asyncio.create_subprocess_exec`**
`NodeSessionRunner._build_fallback_input()` calls `subprocess.run(["git", "diff", ...])` synchronously inside what is effectively an async execution context. This blocks the event loop for the duration of the git diff. The rest of the workspace module uses `run_git()` which is properly async. This is an inconsistency that could cause latency spikes under parallel execution.

**`_BUDGET_EXHAUST_RATIO = 0.9` magic constant inline in `_run_and_harvest()`**
A magic number with no named constant at module scope. It's buried inside a method, making it invisible to configuration and hard to find.

**`content_hash` imported from `core.models` but used only in `engine.py`**
`content_hash` is a SHA-256 utility that lives in `core/models.py` alongside the model registry. It has nothing to do with models — it's a general utility. It's used in `engine.py` for config hashing. It should live in `core/utils.py` or similar.

**`MagicMock` directory at workspace root**
There's a `MagicMock/mock.knowledge.store_path/` directory at the repo root — a leaked test artifact from a mock that was configured with a real path. This is a test hygiene issue.

---

### 4. Optimization Opportunities (without sacrificing clarity)

**`GraphSync.ready_tasks()` iterates all nodes on every call**
The method does a full O(n) scan of `node_states` on every call, then calls `_compute_spec_fan_out()` which does another O(n) scan of `_dependents`. In parallel mode, `ready_tasks()` is called after every completed task. For large graphs (100+ nodes), maintaining an incremental "pending with all deps completed" set — updated only when a node transitions — would reduce this to O(1) amortized.

**`GraphSync._compute_spec_fan_out()` recomputed on every `ready_tasks()` call**
The fan-out weights are derived from the static edge structure, which never changes after construction. This should be computed once in `__init__` and cached.

**`TaskGraph.predecessors()` and `TaskGraph.successors()` are O(|edges|) linear scans**
Both methods scan the entire edge list on every call. `GraphSync` already builds an adjacency dict (`_edges`) and reverse adjacency dict (`_dependents`) at construction. `TaskGraph` should do the same, or these methods should be removed in favor of using `GraphSync` directly.

**`_spec_round_robin()` uses `list.pop(0)` in a loop**
`pop(0)` on a list is O(n). The function builds `queues = [list(g) for g in sorted_groups]` and then calls `q.pop(0)` in a loop. Using `collections.deque` with `popleft()` would make this O(1).

**`SinkDispatcher._dispatch()` uses `getattr(sink, method)(*args)` with string method names**
This bypasses static analysis and IDE support. The core protocol methods are known at write time — they could be dispatched directly. The string-based dispatch is only needed for the optional trace methods, which already use `hasattr` duck-typing.

**`_inject_cache_control()` in `client.py` estimates tokens with `len(text) // 4`**
This is a rough heuristic. For the threshold check, it's fine. But the function is called on every API request, and for large system prompts it does a full string join of all content blocks just to estimate length. A cheaper approach: sum `len(block.get("text", ""))` without joining.

---

### 5. Conceptual Improvements

**`FoxKnowledgeProvider.ingest()` is a documented no-op**
After spec 116 removed gotcha extraction, `ingest()` does nothing. The `KnowledgeProvider` protocol still requires it, and `NodeSessionRunner._ingest_knowledge()` still calls it. The call site, the method, and the protocol method could all be removed — or the protocol could be split into `KnowledgeRetriever` (retrieve only) and `KnowledgeIngester` (ingest), making the no-op nature explicit at the type level rather than hidden in a docstring.

**`_barrier_sync` / barrier callback wiring is vestigial infrastructure**
The `Orchestrator` accepts a `barrier_callback`, `run.py` passes `lambda: _barrier_sync(infra, config)`, and `_barrier_sync` sets a flag that nothing reads. The entire callback chain exists only as scaffolding from the removed knowledge consolidation pipeline. Removing it would simplify `Orchestrator.__init__`, `run_code()`, and `run_sync_barrier_sequence()`.

**`select_context_with_causal()` should be deleted, not stubbed**
The function is exported from `session/prompt.py` as a backward-compat re-export. But nothing in the production code calls it — only tests do. The tests themselves document "causal traversal was removed in spec 114." The right move is to delete the function and its tests, not maintain a stub with dead parameters.

**`SessionOutcome.touched_paths` vs `SessionRecord.files_touched` — two representations of the same concept**
`SessionOutcome` (the raw session result) has `touched_paths: list[str]` which is always empty. `SessionRecord` (the processed result) has `files_touched: list[str]` which is populated from `harvest()`. The `touched_paths` field on `SessionOutcome` should either be populated (from harvest, passed back) or removed. Currently it creates a false impression that the session runner knows which files it touched.

**`Orchestrator._repo_root` property comment reveals a historical bug**
The property exists to correct a double-nesting bug (`_agent_dir.parent`). This is fine, but the comment says "functions such as `MergeLock`, `verify_worktrees`, and `run_consolidation` expect the project root." `run_consolidation` was removed in spec 114. The comment is stale.

**`NightShiftEngine._query_false_positives()` queries a dropped table**
As noted above, `memory_facts` was dropped in migration v18. The method will always return `[]` on any migrated database. The false-positive mechanism it was meant to support (af:ignore signals stored as anti_pattern facts) is broken. Either the table needs to be recreated with the new schema, or the method should be removed and `false_positives=None` passed directly to `consolidate_findings()`.

**`ArchetypesConfig` uses `extra="forbid"` while all other configs use `extra="ignore"`**
This is intentional (to catch typos in archetype config), but it means `ArchetypesConfig` is the only model that will raise on unknown keys. The `reject_old_archetype_keys` validator already handles the known migration cases. The inconsistency is documented but worth noting as a potential surprise for users upgrading from old configs.

**`EscalationLadder` has no `reset()` method**
When `retry_predecessor` converts a review block to a coder retry, the coder's ladder has `record_failure()` called on it. But the ladder is never reset when the coder succeeds. If a coder succeeds after a review-triggered retry, its ladder still shows the failure. This is probably fine in practice (the ladder is per-run), but it means `attempt_count` and `escalation_count` on the ladder don't accurately reflect the coder's actual history.

**`_REVIEW_ARCHETYPES` includes legacy names `"skeptic"`, `"oracle"`, `"auditor"`**
These archetypes were consolidated into `"reviewer"` with modes in spec 98. The frozenset still includes the old names for backward compatibility with old session records in the DB. This is correct, but it means new code paths that check `archetype in _REVIEW_ARCHETYPES` will silently match old records. A comment explaining this would prevent future confusion.

---

### Summary

The codebase is well-structured and clearly the product of disciplined spec-driven development. The main issues are **residue from recent large refactors** (specs 114, 115, 116 removed significant knowledge system functionality) that left behind stubs, dead config fields, no-op methods, and vestigial wiring. The **dispatcher/orchestrator coupling** is the most significant structural smell. The **`__pycache__` ghost files** and the **`MagicMock/` directory** are minor hygiene issues. The **optimization opportunities** in `GraphSync` (fan-out caching, incremental ready-set) are the highest-value performance improvements for large graphs.