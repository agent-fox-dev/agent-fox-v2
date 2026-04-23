# agent-fox Get-Well Plan

Consolidated from three independent audits (audit1.md, audit2.md, audit3.md).
Each item notes which audit(s) raised it and includes enough context to implement
without further investigation.

---

## Legend

| Tag | Meaning |
|-----|---------|
| `[A1]` `[A2]` `[A3]` | Corroborating audits |
| **Bug** | Correctness defect — should fix first |
| **Cleanup** | Dead code / cruft removal |
| **Smell** | Code-quality issue |
| **Perf** | Performance improvement |
| **Arch** | Structural / architectural change |
| **Type** | Type-safety / annotation gap |
| **Test** | Missing test coverage |

---

## Part 1 — Bugs (fix first)

### B-1 · Daemon stop emits START audit event `[A3]`
**File:** `nightshift/daemon.py:418`  
**Impact:** Breaks audit trail — every daemon shutdown is logged as a start.  
**Fix:** Replace `AuditEventType.NIGHT_SHIFT_START` with the correct stop event type.

---

### B-2 · `assert` used as runtime validation `[A1][A2][A3]`
**Files:**
- `dispatch.py` — `assert orch._graph_sync is not None  # noqa: S101`
- `knowledge/migrations.py:228` — `assert dim in _ALLOWED_EMBEDDING_DIMS`
- `graph/persistence.py:153–154, 163` — asserts on DB query results

**Impact:** Assertions are stripped by `python -O`. Under optimization they raise
`AttributeError`/`TypeError` instead of a meaningful error.  
**Fix:** Replace every `assert` in production paths with `if … is None: raise RuntimeError(…)`
or an appropriate typed exception from `core/errors.py`.

---

### B-3 · Barrier recovery pushes after a failed pull `[A3]`
**File:** `engine/barrier.py:54–95`  
**Impact:** `sync_develop_bidirectional()` logs a pull error but continues to push,
potentially fast-forwarding remote to stale commits.  
**Fix:** Return early (or re-raise) when the pull step fails; do not proceed to push.

---

### B-4 · Staleness verification has contradictory semantics `[A3]`
**File:** `nightshift/staleness.py:184–198`  
**Impact:** AI failure path marks an issue obsolete if it is closed on GitHub;
AI success path marks it obsolete only if AI says so **and** it is still open.
The two branches invert the "open" condition.  
**Fix:** Reconcile both branches to a single consistent rule: mark obsolete when AI
confirms AND the issue is closed, or remove the per-path override entirely.

---

### B-5 · Config hot-reload has no lock `[A3]`
**File:** `engine/engine.py:272, 316–337`  
**Impact:** A config reload mid-dispatch can expose partially-updated config state
to concurrent workers.  
**Fix:** Wrap `_config_reloader` access with an `asyncio.Lock` (or `threading.RLock`
if the reloader runs in a thread); at minimum document the threading contract.

---

### B-6 · Silent mode fallthrough in `resolve_max_turns` `[A3]`
**File:** `engine/sdk_params.py:22–108`  
**Impact:** An unrecognised mode string silently falls through to defaults;
a typo in a config produces wrong max-turns with no diagnostic.  
**Fix:** Add a `KNOWN_MODES` set (or use the `NodeMode` StrEnum proposed in T-3)
and raise `ValueError` for unrecognised values.

---

### B-7 · Unsafe IPv6 URL parsing `[A3]`
**File:** `platform/github.py:50–93`  
**Impact:** `rsplit(":", 1)` mis-splits addresses like `[2001:db8::1]:8080`,
producing a wrong host and port.  
**Fix:** Replace the manual split with `urllib.parse.urlparse()`.

---

### B-8 · DNS failure silently allowed through `[A3]`
**File:** `platform/github.py:96–100`  
**Impact:** On `OSError`/`UnicodeError` the URL is accepted without any warning,
making connectivity issues invisible until a later API call fails.  
**Fix:** Log a `WARNING` when DNS resolution fails, even if the URL is allowed through.

---

### B-9 · `_reset_blocked_tasks` persists every pending node, not only reset ones `[A1]`
**File:** `engine/engine.py:1551–1574`  
**Impact:** On every resume, O(n) DB writes are issued for all pending nodes instead of
only the ones just unblocked.  
**Fix:** Collect the node IDs that actually changed from `blocked` → `pending` in the
loop and call `persist_node_status` only for those.

---

### B-10 · `attempt_tracker` incremented before session runs `[A1]`
**File:** `engine/dispatch.py` — `_prepare_launch`  
**Impact:** If a session is interrupted mid-flight, the attempt counter is inflated by 1
for that node, skewing retry logic and UI display.  
**Fix:** Increment the attempt counter after the session runner returns (or on confirmed
dispatch), not before.

---

## Part 2 — Dead Code (remove)

### D-1 · `select_context_with_causal()` stub `[A2][A3]`
**Files:** `session/context.py:548–563`, re-exported from `session/prompt.py`  
**What:** Body returns `keyword_facts[:max_facts]`; `conn` and `causal_budget` params are silently ignored. Causal traversal was removed in spec 114.  
**Fix:** Delete the function, its re-export, and the tests that exercise it.

---

### D-2 · `causal_context_limit` orphaned config field `[A2]`
**File:** `core/config.py` — `OrchestratorConfig.causal_context_limit`  
**What:** Defined, clamped, and tested but never read in production code.  
**Fix:** Remove the field definition, its clamp logic, and any tests that reference it.

---

### D-3 · `_barrier_sync()` no-op with scaffolding `[A2][A3]`
**Files:** `engine/run.py` (`_barrier_sync`), `engine/engine.py` (barrier_callback param), `run_sync_barrier_sequence()`  
**What:** `_barrier_sync` sets a flag that nothing reads. The entire callback chain is vestigial from the removed knowledge consolidation pipeline.  
**Fix:** Delete `_barrier_sync`, the `barrier_callback` parameter on `Orchestrator.__init__`, and `run_sync_barrier_sequence()`. Remove the associated unit test.

---

### D-4 · `routing_assessments` / `routing_pipeline` vestigial params `[A2]`
**File:** `engine/result_handler.py` — `SessionResultHandler.__init__`  
**What:** Both are accepted, stored, and never read again.  
**Fix:** Remove both parameters and their instance attributes.

---

### D-5 · `_fill_parallel_pool` / `_process_completed_parallel` dead wrappers `[A1]`
**File:** `engine/engine.py:994–1024`  
**What:** Pure delegation wrappers that are never called; actual dispatch goes through `_dispatch_parallel()` directly.  
**Fix:** Delete both methods.

---

### D-6 · Dead fallback branches in `_get_parallel_dispatcher` and `_dispatch_serial` `[A1]`
**File:** `engine/engine.py:951–957, 967–977`  
**What:** Both use `getattr(self, "_xxx_dispatcher", None)` with fallback construction, but the dispatchers are always set in `__init__`. The lazy-creation paths are unreachable.  
**Fix:** Replace `getattr` guards with direct attribute access; add `__init__`-time assertions that the attributes are not `None`.

---

### D-7 · `FoxKnowledgeProvider.ingest()` documented no-op `[A2]`
**File:** `knowledge/fox_provider.py`  
**What:** After spec 116, `ingest()` does nothing. The protocol still requires it; `NodeSessionRunner._ingest_knowledge()` still calls it.  
**Fix:** Either remove the `ingest` method from the `KnowledgeProvider` protocol and all call sites, or split the protocol into `KnowledgeRetriever` / `KnowledgeIngester` so the no-op is explicit at the type level.

---

### D-8 · `_query_false_positives()` queries a dropped table `[A2][A3]`
**File:** `nightshift/engine.py` — `NightShiftEngine._query_false_positives()`  
**What:** `memory_facts` was dropped in migration v18. The method always returns `[]`; the `except Exception` swallows the table-missing error.  
**Fix:** Remove the method and pass `false_positives=None` directly to `consolidate_findings()`.

---

### D-9 · `_query_oracle_facts()` always returns `[]` `[A3]`
**File:** `fix/analyzer.py:338–348`  
**What:** Removed in spec 114. Always returns an empty list.  
**Fix:** Delete the method and remove its call sites.

---

### D-10 · `"severity_changed"` action in `nightshift/critic.py` is never produced `[A3]`
**File:** `nightshift/critic.py:340–347`  
**What:** The `_parse_critic_response()` parser never emits `"severity_changed"`, so the handler branch is unreachable.  
**Fix:** Delete the handler branch (or add it to the parser if the action is intended).

---

### D-11 · `NightShiftState.issues_created` / `.issues_fixed` never incremented `[A3]`
**File:** `nightshift/engine.py:46–58`  
**What:** Both fields are defined on the dataclass but no code ever writes to them.  
**Fix:** Either wire them up to the actual issue-creation and fix-confirmation paths, or remove the fields.

---

### D-12 · Custom exceptions in `core/errors.py` never raised `[A3]`
**File:** `core/errors.py:22–49` — `InitError`, `PlanError`, `WorkspaceError`, etc.  
**What:** All are defined but the codebase raises generic `Exception` or `ValueError` instead (see A-1 below).  
**Fix:** Either begin using them (preferred, see A-1) or remove the unused types to avoid misleading readers.

---

### D-13 · Unreachable line in `fix/clusterer.py` `[A3]`
**File:** `fix/clusterer.py:160`  
**What:** `seen_indices.add(idx)` appears directly after `raise ValueError(…)`.  
**Fix:** Delete the unreachable line.

---

### D-14 · Ghost `__pycache__` entries `[A2]`
**What:** `.pyc` files exist for source modules that no longer exist (e.g. `onboard.cpython-312.pyc`, `knowledge_harvest.cpython-312.pyc`, `stream.cpython-312.pyc`, and ~10 others).  
**Fix:** `find . -name __pycache__ -exec rm -rf {} +` and add a `.gitignore` rule for `__pycache__/`.

---

### D-15 · `MagicMock/` directory at repo root `[A2]`
**What:** A leaked test artifact from a mock configured with a real file path.  
**Fix:** Delete the directory; add `MagicMock/` to `.gitignore`.

---

### D-16 · `SessionOutcome.touched_paths` always empty `[A2][A3]`
**File:** `session/sink.py` — `SessionOutcome.touched_paths`  
**What:** The field is never populated; actual file list flows through `SessionRecord.files_touched`. This creates a false impression the session runner knows which files it touched.  
**Fix:** Remove the field from `SessionOutcome`, or populate it from `harvest()` output.

---

### D-17 · Migration create-then-drop cycle (v3/v13/v14/v18) `[A1]`
**File:** `knowledge/migrations.py`  
**What:** Migrations v3 and v13 create tables that v14 and v18 immediately drop. Every fresh install runs pointless DDL.  
**Fix:** Collapse the create+drop pairs into no-op stubs (following the `v5`/`v10` pattern) so the overhead disappears on new installs.

---

### D-18 · `KnowledgeDB._initialize_schema` is dead DDL `[A1]`
**File:** `knowledge/db.py`  
**What:** `_initialize_schema()` creates a 4-table subset that `_BASE_SCHEMA_DDL` in `migrations.py` supersedes. `KnowledgeDB.open()` runs both.  
**Fix:** Remove the inline DDL from `db.py` and have `open()` call `run_migrations()` directly.

---

## Part 3 — Code Smells & Anti-Patterns

### A-1 · Broad `except Exception: pass` throughout the codebase `[A1][A2][A3]`
**Scope:** 38 silent-swallow instances; ~234 broad catches across 72 files.  
**Key sites:**
- `engine/state.py:231–325` — five silent catches in `load_state_from_db`
- `cli/nightshift.py`, `engine/coverage.py` — `except Exception: pass`
- `nightshift/critic.py:356–359`

**Fix strategy:**
1. `DEBUG`-log with `exc_info=True` as the minimum for every silent catch.
2. Promote DB-query failures in `load_state_from_db` to `WARNING`.
3. Begin raising the typed exceptions from `core/errors.py` (see D-12) and catching them specifically at appropriate boundaries.
4. Document the three intended error-surfacing tiers (raise / log-and-default / swallow) as a brief `CONTRIBUTING` note, then enforce them in review.

---

### A-2 · `_ts` helper defined twice `[A1]`
**File:** `engine/state.py:588–593, 631–637`  
**What:** Identical `_ts()` function body inside both `load_run()` and `load_incomplete_run()`.  
**Fix:** Hoist to a module-level private function.

---

### A-3 · Inline imports inside method bodies `[A1][A2]`
**Key sites:**
- `result_handler.py:403–415` — three `from agent_fox.engine.state import …` inside `process()`
- `result_handler.py:361` — `from pathlib import Path` (already imported at line 17)
- `session/context.py` — four inline imports inside render methods
- `engine/state.py` — `from agent_fox.core.config import PricingConfig` inline
- `engine/engine.py` — multiple inline imports; some legitimately break cycles, others do not

**Fix:** Audit all in-method imports. Move those that do not break circular imports to module level. For those that do break cycles, add a `# circular-import: …` comment explaining why.

---

### A-4 · `subprocess.run` blocking inside async context `[A2]`
**File:** `session/session.py` (or `NodeSessionRunner`) — `_build_fallback_input()`  
**What:** `subprocess.run(["git", "diff", …])` blocks the event loop. The async `run_git()` in `workspace/git.py` already exists.  
**Fix:** Replace with `await run_git(...)` from `workspace/git.py`.

---

### A-5 · `_prepare_launch` returns a 7-element positional tuple `[A1]`
**File:** `engine/dispatch.py:55–62`  
**What:** Callers unpack `(_, attempt, previous_error, node_archetype, node_instances, assessed_tier, node_mode)` by position. Adding or reordering any field silently breaks every caller.  
**Fix:** Replace with a `@dataclass` (or `NamedTuple`) `LaunchParams`.

---

### A-6 · Mixed `conn.sql()` vs `conn.execute()` `[A1]`
**File:** `engine/state.py`  
**What:** `load_state_from_db` uses `conn.sql()` for SELECT and `conn.execute()` for mutations. `conn.sql()` does not support parameterized queries, which is an injection risk if parameters are ever added.  
**Fix:** Standardise all queries in `state.py` to `conn.execute()`.

---

### A-7 · `hasattr(state.run_status, "value")` unnecessary guard `[A1]`
**File:** `engine/engine.py:737–741`  
**What:** `RunStatus` is a `StrEnum`; every member has `.value`. The guard exists because `ExecutionState.run_status` is typed `str`, not `RunStatus`. This is a root-cause type annotation error.  
**Fix:** Type `ExecutionState.run_status` as `RunStatus` (or `RunStatus | str` during transition) and remove the `hasattr` guard.

---

### A-8 · `_init_run` returns a union type forcing `isinstance` in callers `[A1]`
**File:** `engine/engine.py:430–432`  
**What:** Returns `ExecutionState | tuple[ExecutionState, dict, dict]`; callers must `isinstance`-check.  
**Fix:** Introduce a `RunInitResult` dataclass with an `early_exit: bool` field and a single `state: ExecutionState` plus optional auxiliary dicts.

---

### A-9 · `SinkDispatcher` has two dispatch mechanisms `[A2]`
**File:** `knowledge/sink.py:136–291`  
**What:** Protocol methods use a clean `_dispatch(method, *args)` helper; trace methods each have hand-rolled `for sink in self._sinks: hasattr / try / except` loops — ~150 lines of near-identical boilerplate.  
**Fix:** Introduce `_dispatch_optional(method_name, **kwargs)` and collapse all trace-method loops into single-line calls.

---

### A-10 · `hasattr`-based duck typing in `SinkDispatcher` `[A3]`
**File:** `knowledge/sink.py`  
**What:** `hasattr(sink, "record_session_init")` bypasses static type checking. The protocol methods are known at write time.  
**Fix:** Define the `SinkProtocol` as a `@runtime_checkable Protocol` (or use `isinstance` checks against it). See also T-2.

---

### A-11 · `_coverage_tool` uses `None` / `False` as tri-state `[A1]`
**File:** `engine/result_handler.py:86`  
**What:** `None` means "not yet checked", `False` means "no tool found", `CoverageTool` means "found". This is confusing.  
**Fix:** Replace with a `CoverageToolState` enum: `UNCHECKED`, `UNAVAILABLE`, `AVAILABLE(tool)`.

---

### A-12 · `_interleave_by_spec` calls `_is_auto_pre` twice per node `[A1]`
**File:** `engine/graph_sync.py:144–157`  
**What:** Two separate list comprehensions each call `_is_auto_pre(n)`, so each node is evaluated twice.  
**Fix:** Single-pass partition: `pre, regular = [], []` with one loop.

---

### A-13 · Session ID uses colon delimiter in a colon-containing field `[A1]`
**File:** `engine/result_handler.py:352`  
**What:** `session_id = f"{record.node_id}:{record.attempt}"` is ambiguous when `node_id` itself contains colons (e.g. `spec:1:reviewer:audit-review`).  
**Fix:** Use a delimiter that cannot appear in node IDs (e.g. `#` or `|`), or use a dedicated `SessionId` type with a stable serialisation.

---

### A-14 · `node_id.split(":", 1)` duplicated; `parse_node_id` exists but isn't used `[A1]`
**Files:** `engine/result_handler.py:415–417`, `engine/engine.py`, possibly others.  
**Fix:** Replace all ad-hoc splits with `parse_node_id()`.

---

### A-15 · `_REVIEW_ARCHETYPES` is a private constant imported across modules `[A1][A2]`
**File:** `engine/session_lifecycle.py`; imported by `dispatch.py`, `engine.py`, `graph_sync.py`.  
**What:** A leading-underscore name being re-imported as public API.  
**Fix:** Rename to `REVIEW_ARCHETYPES` and move to `engine/archetypes.py` alongside the archetype registry. Add a comment explaining the legacy names (`"skeptic"`, `"oracle"`, `"auditor"`) kept for backward-compat with old DB records.

---

### A-16 · `duckdb` imported with `# noqa: F401` `[A1]`
**Files:** `knowledge/db.py`, `knowledge/migrations.py`  
**What:** The import is needed for the type annotation `duckdb.DuckDBPyConnection` but the noqa comment indicates the real fix was deferred.  
**Fix:** Add `from __future__ import annotations` and move the `duckdb` import inside a `TYPE_CHECKING` block.

---

### A-17 · `_BUDGET_EXHAUST_RATIO` magic number inline `[A2]`
**File:** `engine/session.py` (or `_run_and_harvest`)  
**Fix:** Define `_BUDGET_EXHAUST_RATIO: float = 0.9` at module scope with a brief comment.

---

### A-18 · `content_hash` lives in the wrong module `[A2]`
**File:** `core/models.py`  
**What:** A SHA-256 utility used by `engine.py` for config hashing has nothing to do with the model registry.  
**Fix:** Move to `core/utils.py` (create if needed) and update the single import site in `engine.py`.

---

### A-19 · `Orchestrator.__init__` has 17 parameters `[A2]`
**File:** `engine/engine.py`  
**Fix:** Group infrastructure concerns into an `OrchestratorInfra` dataclass:
`audit_dir`, `audit_db_conn`, `knowledge_db_conn`, `sink_dispatcher`, `platform`.
The construction site in `run.py` becomes `OrchestratorInfra(…)` passed as one argument.

---

### A-20 · `_get_node_archetype()` / `_get_node_mode()` duplicated `[A2][A3]`
**Files:** `engine/engine.py` (on `Orchestrator`) and `engine/result_handler.py` (on `SessionResultHandler`).  
**Fix:** Move to a shared `graph_accessors.py` helper module (or onto `TaskGraph` itself) and import from both classes.

---

### A-21 · Branch/label sanitization duplicated `[A3]`
**Files:** `nightshift/spec_builder.py:38–46`, `fix/spec_gen.py:31–43`  
**What:** Nearly identical slug-sanitization routines, both dropping accented characters.  
**Fix:** Extract a shared `sanitize_slug(text: str) -> str` utility in `core/utils.py` using `unicodedata.normalize("NFKD", …)`.

---

### A-22 · `Orchestrator._repo_root` has a stale comment `[A2]`
**File:** `engine/engine.py`  
**What:** The docstring mentions `run_consolidation` which was removed in spec 114.  
**Fix:** Remove the stale reference from the comment.

---

## Part 4 — Performance

### P-1 · `_compute_spec_fan_out()` recomputed on every `ready_tasks()` call `[A1][A2]`
**File:** `engine/graph_sync.py`  
**What:** Fan-out weights are derived from static edge structure (never changes after construction) but recomputed on every call to `ready_tasks()`, which is called after every completed task.  
**Fix:** Compute once in `GraphSync.__init__` and cache as `self._spec_fan_out`.

---

### P-2 · `ready_tasks()` / `is_stalled()` double-compute `[A1][A2]`
**File:** `engine/graph_sync.py`  
**What:** The orchestration loop calls `ready_tasks()` then, finding it empty, calls `is_stalled()` which calls `ready_tasks()` again internally.  
**Fix:** Accept an optional pre-computed `ready: list[str]` parameter in `is_stalled()`, or return `(tasks, is_stalled)` as a single call result.

---

### P-3 · `_spec_round_robin` uses `list.pop(0)` — O(n) per call `[A1][A2]`
**File:** `engine/graph_sync.py` (and potentially `graph/graph_sync.py`)  
**Fix:** Replace `list(g)` with `collections.deque(g)` and `pop(0)` with `popleft()`.

---

### P-4 · `_init_error_tracker` is O(nodes × history) `[A1]`
**File:** `engine/engine.py:1627–1643`  
**What:** For each pending node, a list comprehension scans the entire `session_history`.  
**Fix:** Pre-group `session_history` by `node_id` with a `defaultdict(list)` before the outer loop.

---

### P-5 · `load_state_from_db` queries `plan_nodes` twice `[A1]`
**File:** `engine/state.py:229–241`  
**Fix:** Merge into one query: `SELECT id, status, blocked_reason FROM plan_nodes` and unpack both fields.

---

### P-6 · `cleanup_stale_runs` SELECT then UPDATE `[A1]`
**File:** `engine/state.py:515–554`  
**Fix:** Use DuckDB's `RETURNING` clause: `UPDATE runs SET status = 'interrupted' … RETURNING count(*)` to get the count in a single round-trip.

---

### P-7 · `_supersede_active_records` SELECT then UPDATE `[A1]`
**File:** `knowledge/review_store.py:127–151`  
**Fix:** Use a single `UPDATE … RETURNING id::VARCHAR` to capture superseded IDs without a preliminary SELECT.

---

### P-8 · `TaskGraph.predecessors()` / `successors()` are O(|edges|) `[A2]`
**File:** `graph/task_graph.py`  
**What:** Both methods do a linear scan over the full edge list. `GraphSync` already builds adjacency dicts.  
**Fix:** Build forward and reverse adjacency dicts in `TaskGraph.__init__` and return from those, or deprecate these methods in favour of `GraphSync` accessors.

---

### P-9 · `json.JSONDecoder()` created per loop iteration `[A3]`
**File:** `core/json_extraction.py:146` — `_scan_bracket_arrays()`  
**Fix:** Hoist `_DECODER = json.JSONDecoder()` to module level and reuse it.

---

### P-10 · `dep_graph.py` edge removal is O(n) `[A3]`
**File:** `nightshift/dep_graph.py:122`  
**What:** `working_edges.remove(edge_to_remove)` on a list.  
**Fix:** Convert `working_edges` to a `set` so removal is O(1).

---

### P-11 · Critical path backtracking has no depth/count limit `[A3]`
**File:** `graph/critical_path.py:138–165`  
**What:** `_backtrack_paths()` recursively enumerates all critical paths, which can explode exponentially for graphs with many disjoint critical paths.  
**Fix:** Add a `max_paths: int = 64` guard; stop backtracking once the limit is reached and log a `DEBUG` notice.

---

### P-12 · Convergence sort recomputes normalization on every comparison `[A3]`
**File:** `session/convergence.py:85–91`  
**What:** `normalize_finding(f)[1]` is called inside the sort key, so it runs O(n log n) times.  
**Fix:** Pre-compute normalized descriptions in a single pass before sorting.

---

### P-13 · `_inject_cache_control` joins all content blocks for token estimate `[A2]`
**File:** `engine/client.py`  
**What:** Full string join of all content blocks is done just to estimate length.  
**Fix:** Sum `len(block.get("text", ""))` for each block without joining.

---

### P-14 · `load_config()` re-reads from disk at every CLI entry point `[A3]`
**Files:** `cli/app.py`, `cli/code.py`, `cli/nightshift.py`, `cli/plan.py`  
**What:** No caching; each entry point calls `load_config()` independently.  
**Fix:** Cache the result in a module-level `_cached_config` and expose a `get_config()` accessor, or accept it as a CLI-level singleton threaded through the command group.

---

### P-14 · `load_config()` re-reads from disk at every CLI entry point `[A3]`
**Files:** `cli/app.py`, `cli/code.py`, `cli/nightshift.py`, `cli/plan.py`  
**What:** No caching; each entry point calls `load_config()` independently.  
**Fix:** Cache the result in a module-level `_cached_config` and expose a `get_config()` accessor, or accept it as a CLI-level singleton threaded through the command group.

---

## Part 5 — Architecture

### C-1 · God object: `Orchestrator` (1,800+ lines, 70+ methods) `[A1][A2][A3]`
**File:** `engine/engine.py`  
**What:** Owns task dispatch, circuit breaking, graph sync, state management, audit emission,
config reloading, routing, preflight, conflict detection, watch mode, barrier execution,
issue summary posting, and shutdown. Dispatchers access its private attributes typed as `Any`.

**Recommended extraction:**
| New class | Responsibilities pulled from `Orchestrator` |
|-----------|---------------------------------------------|
| `GraphStateManager` | State transitions, ready detection, cascade blocking |
| `DispatchCoordinator` | Serial/parallel dispatch selection and execution |
| `SessionLifecycleManager` | Result processing, escalation, blocking decisions |

**Migration path:** Extract one class at a time, injecting it as a constructor parameter on `Orchestrator`, then flip callers to use the extracted class directly. The `Any`-typed `orch` references in `dispatch.py` become properly typed dependency injections.

---

### C-2 · God object: `FixPipeline` (1,021 lines, 25+ methods) `[A3]`
**File:** `nightshift/fix_pipeline.py`  
**What:** Handles session running, comment posting, triage, coder-reviewer loop, spec building,
workspace management, metrics tracking, event emission, and prompt building.
`coder_reviewer.py` accesses its private methods directly.

**Fix:** Apply the same extraction pattern as C-1. Candidates: `FixWorkspaceManager`, `FixSessionRunner`, `FixReporter`.

---

### C-3 · Dispatcher/orchestrator coupling: `dispatch.py` accesses `orch._*` `[A1][A2]`
**File:** `engine/dispatch.py`  
**What:** `SerialDispatcher` and `ParallelDispatcher` hold `orch: Any` and access a dozen private attributes. The dependency contract is invisible to type checkers.  
**Fix:** Define an `OrchestratorProtocol` (or pass a narrowly-scoped `DispatchContext` dataclass) with only the attributes dispatchers actually need. This is the immediate prerequisite step before C-1.

---

### C-4 · No explicit node state machine `[A3]`
**File:** `engine/graph_sync.py`  
**What:** Node states are plain strings mutated via `mark_in_progress()` etc. with no enforcement of valid transitions.  
**Fix:** Introduce a `NodeState(StrEnum)`: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `FAILED` and a `transition(node_id, from_state, to_state)` helper that raises `InvalidTransitionError` for illegal moves.

---

### C-5 · `SessionRecord` ↔ `SessionOutcomeRecord` structural duplication `[A1][A2]`
**Files:** `engine/state.py:36–88`, `engine/result_handler.py:415–439`  
**What:** Two nearly-identical dataclasses with a manual mapping between them. `SessionOutcomeRecord`'s docstring says it "replaces the legacy SessionRecord" but the migration was never completed.  
**Fix:** Complete the migration: make `SessionRecord` a thin alias or view; write `SessionOutcomeRecord` directly from session completion data; remove the intermediate mapping in `process()`.

---

### C-6 · Circular imports in nightshift subsystem `[A3]`
**Cycles:**
- `nightshift.coder_reviewer ↔ nightshift.fix_pipeline ↔ session.review_parser`
- `graph/injection.py` ↔ spec helpers
- `graph/builder.py` ↔ `graph/spec_helpers`

**Fix:** Introduce a `nightshift/interfaces.py` (protocols/ABCs only) that both sides import, breaking the direct cycles. Evaluate whether `graph/injection.py`'s late imports can be eliminated by restructuring module initialization order.

---

### C-7 · No abstraction between session code and DuckDB `[A3]`
**Files:** `session/context.py`, `session/auditor_output.py`, `reporting/findings.py`  
**What:** These modules import DuckDB directly and query the DB inline rather than going through a store interface.  
**Fix:** Introduce thin store/repository classes (`FindingsStore`, `ContextStore`) that wrap the DuckDB queries. This also enables unit testing without a real DB.

---

### C-8 · `KnowledgeProvider` protocol requires `ingest()` which is always a no-op `[A2]`
**What:** See D-7. This is the protocol-level consequence of the removed ingestion pipeline.  
**Fix:** If ingestion is truly gone, remove the method from the protocol. If it may return, annotate `ingest()` as optional with a default no-op base implementation.

---

## Part 6 — Type Safety & Consistency

### T-1 · Magic strings for modes scattered everywhere `[A1][A3]`
**What:** `"pre-review"`, `"drift-review"`, `"audit-review"`, `"coder"` appear as literals across `graph/injection.py`, `archetypes.py`, `engine/sdk_params.py`, `dispatch.py`, `result_handler.py`, `session_lifecycle.py`.  
**Fix:** Introduce `class NodeMode(StrEnum): CODER = "coder"; PRE_REVIEW = "pre-review"; ...` in `engine/archetypes.py` (or a new `engine/modes.py`) and replace all literals.  
Also define `DEFAULT_ARCHETYPE: str = "coder"` as a module constant to replace the six scattered `"coder"` fallback literals.

---

### T-2 · `PlatformProtocol` is incomplete — evidenced by `type: ignore` comments `[A3]`
**File:** `nightshift/fix_pipeline.py:139, 795, 897, 919, 933`  
**Fix:** Add the missing method signatures to `PlatformProtocol` so that `isinstance` checks and `mypy` both pass without `# type: ignore`.

---

### T-3 · Triage tiers use string keys instead of an enum `[A3]`
**File:** `nightshift/triage.py:46–50`  
**Fix:** `class TriageTier(StrEnum): QUICK_WIN = "quick_win"; STRUCTURAL = "structural"; ...`

---

### T-4 · SQL table names interpolated as f-strings `[A3]`
**File:** `knowledge/review_store.py`  
**What:** Uses a whitelist validator but the pattern is still fragile.  
**Fix:** Replace with a `ReviewTable(StrEnum)` or a `Literal[…]` type and map to table names via a dict, removing the validator.

---

### T-5 · `~52%` of functions lack return-type annotations `[A3]`
**Well-annotated:** `core/`, `engine/state.py`, `platform/`  
**Poorly-annotated:** `cli/`, `workspace/git.py`, `nightshift/coder_reviewer.py`  
**Fix:** Add `mypy --strict` (or `pyright`) to CI, start with `cli/` and `workspace/git.py` as bounded first targets.

---

### T-6 · Migration source-definition order != version order `[A1]`
**File:** `knowledge/migrations.py:749–846`  
**What:** `_migrate_v14` is defined before `_migrate_v13` in source, and `v15` before `v14`. Disorienting for reviewers.  
**Fix:** Reorder function definitions to match version numbers.

---

## Part 7 — Test Coverage

### TC-1 · `engine/engine.py` (1,800 lines) has no unit tests `[A3]`
**Fix:** Start with the extracted classes from C-1 (they will be smaller and injectable), not the monolith itself. Write unit tests for `GraphStateManager` and `DispatchCoordinator` before the extraction lands.

---

### TC-2 · `ui/display.py`, `ui/progress.py` have no test files `[A3]`
**Fix:** Add `tests/ui/test_display.py` and `tests/ui/test_progress.py` with basic rendering-path smoke tests.

---

### TC-3 · `routing/escalation.py` has no dedicated test `[A3]`
**Fix:** Add `tests/routing/test_escalation.py`.

---

### TC-4 · `workspace/merge_agent.py` has no dedicated test `[A3]`
**Fix:** Add `tests/workspace/test_merge_agent.py` (use a fixture worktree or mock `run_git`).

---

### TC-5 · Coverage tool runs full test suite twice per coder session `[A1]`
**File:** `engine/coverage.py:135–149`  
**What:** `measure_coverage()` runs `pytest --cov -x -q` before and after every coder session, doubling CI time for slow suites.  
**Fix:** Add a `coverage_measurement: bool` config flag (default `true`) to `OrchestratorConfig` so it can be disabled per-node or globally. Alternatively, reuse the existing pytest run output instead of spawning a second process.

---

## Prioritised Implementation Order

The table below gives a suggested order that maximises unblocking and minimises
rework. Items within the same tier can be done in parallel.

| Tier | Items | Rationale |
|------|-------|-----------|
| **1 — Now** (correctness) | B-1, B-2, B-3, B-7, B-9, D-1, D-13 | Bugs with clear small fixes; dead code that misleads readers |
| **2 — Soon** (hygiene) | D-2 through D-18, A-2, A-14, A-16, A-17, A-22, P-9, P-10, P-12, T-6 | Standalone removals/renames; no dependencies |
| **3 — Sprint** (reliability) | A-1, B-4, B-5, B-6, B-8, B-10, A-3 through A-12, P-1 through P-8, P-11, P-13, P-14, T-1, T-3, T-4 | Broader patterns requiring consistent application across files |
| **4 — Milestone** (architecture) | C-3 → C-1 → C-2, C-4, C-5, C-6, C-7 | Must do C-3 first (OrchestratorProtocol); then extract classes |
| **5 — Ongoing** | T-2, T-5, TC-1 through TC-5 | Type coverage and test coverage are continuous efforts |
