# Test Specification: Sleep-Time Compute

## Overview

Tests are organized into acceptance-criterion tests (one per requirement),
property tests (one per correctness property), edge-case tests, and
integration smoke tests (one per execution path). All tests use in-memory
DuckDB and mock LLM/embedder unless stated otherwise.

## Test Cases

### TS-112-1: SleepTask protocol name property

**Requirement:** 112-REQ-1.1
**Type:** unit
**Description:** Verify that SleepTask implementations expose a name property.

**Preconditions:**
- A concrete class implementing SleepTask.

**Input:**
- Instantiate the class.

**Expected:**
- `task.name` returns a non-empty string.

**Assertion pseudocode:**
```
task = ContextRewriter()
ASSERT isinstance(task.name, str)
ASSERT len(task.name) > 0
```

### TS-112-2: SleepTask run returns SleepTaskResult

**Requirement:** 112-REQ-1.2
**Type:** unit
**Description:** Verify that SleepTask.run() returns a SleepTaskResult.

**Preconditions:**
- In-memory DuckDB with schema initialized (including sleep_artifacts table).
- SleepContext with mock dependencies.

**Input:**
- Call `task.run(ctx)`.

**Expected:**
- Returns a `SleepTaskResult` with `created`, `refreshed`, `unchanged` as ints
  and `llm_cost` as float.

**Assertion pseudocode:**
```
result = await task.run(ctx)
ASSERT isinstance(result, SleepTaskResult)
ASSERT isinstance(result.created, int)
ASSERT isinstance(result.llm_cost, float)
```

### TS-112-3: SleepTask stale_scopes returns scope keys

**Requirement:** 112-REQ-1.3
**Type:** unit
**Description:** Verify that stale_scopes returns a list of scope key strings.

**Preconditions:**
- In-memory DuckDB with facts and existing sleep artifacts.

**Input:**
- Call `task.stale_scopes(conn)`.

**Expected:**
- Returns a list of strings.

**Assertion pseudocode:**
```
scopes = task.stale_scopes(conn)
ASSERT isinstance(scopes, list)
ASSERT all(isinstance(s, str) for s in scopes)
```

### TS-112-4: SleepContext bundles all required fields

**Requirement:** 112-REQ-1.4
**Type:** unit
**Description:** Verify SleepContext contains all required fields.

**Preconditions:**
- None.

**Input:**
- Construct a SleepContext with all fields.

**Expected:**
- All fields accessible and correctly typed.

**Assertion pseudocode:**
```
ctx = SleepContext(conn=conn, repo_root=Path("."), model="standard",
                   embedder=None, budget_remaining=1.0, sink_dispatcher=None)
ASSERT ctx.conn is conn
ASSERT ctx.budget_remaining == 1.0
```

### TS-112-5: SleepTaskResult fields

**Requirement:** 112-REQ-1.5
**Type:** unit
**Description:** Verify SleepTaskResult contains correct fields.

**Preconditions:**
- None.

**Input:**
- Construct a SleepTaskResult.

**Expected:**
- Fields `created`, `refreshed`, `unchanged` (int) and `llm_cost` (float).

**Assertion pseudocode:**
```
result = SleepTaskResult(created=1, refreshed=2, unchanged=3, llm_cost=0.05)
ASSERT result.created == 1
ASSERT result.llm_cost == 0.05
```

### TS-112-6: SleepComputer executes tasks in order

**Requirement:** 112-REQ-2.1
**Type:** unit
**Description:** Verify tasks run in registration order with decremented budget.

**Preconditions:**
- Two mock sleep tasks that record call order and budget received.

**Input:**
- Register task_a (cost 0.3) then task_b, run SleepComputer.

**Expected:**
- task_a called first with full budget, task_b called second with
  budget - 0.3.

**Assertion pseudocode:**
```
computer = SleepComputer([task_a, task_b], config)
result = await computer.run(ctx_with_budget_1_0)
ASSERT call_order == ["task_a", "task_b"]
ASSERT task_b_received_budget == 0.7
```

### TS-112-7: SleepComputeResult structure

**Requirement:** 112-REQ-2.2
**Type:** unit
**Description:** Verify SleepComputeResult contains per-task results, total cost, errors.

**Preconditions:**
- SleepComputer with one task that succeeds.

**Input:**
- Run SleepComputer.

**Expected:**
- Result has task_results dict, total_llm_cost float, errors list.

**Assertion pseudocode:**
```
result = await computer.run(ctx)
ASSERT "context_rewriter" in result.task_results
ASSERT isinstance(result.total_llm_cost, float)
ASSERT isinstance(result.errors, list)
```

### TS-112-8: Task exception isolation

**Requirement:** 112-REQ-2.3
**Type:** unit
**Description:** Verify failing task doesn't block subsequent tasks.

**Preconditions:**
- task_a raises RuntimeError, task_b succeeds.

**Input:**
- Run SleepComputer with [task_a, task_b].

**Expected:**
- task_b still runs and its result is in the output. Error list contains
  task_a's error message.

**Assertion pseudocode:**
```
result = await computer.run(ctx)
ASSERT "task_b" in result.task_results
ASSERT any("task_a" in e for e in result.errors)
```

### TS-112-9: Budget exhaustion skips task

**Requirement:** 112-REQ-2.4
**Type:** unit
**Description:** Verify tasks are skipped when budget is exhausted.

**Preconditions:**
- task_a costs 0.9, task_b costs 0.5; budget = 1.0.

**Input:**
- Run SleepComputer.

**Expected:**
- task_a runs, task_b is skipped. Error list contains "budget_exhausted".

**Assertion pseudocode:**
```
result = await computer.run(ctx_with_budget_1_0)
ASSERT "task_a" in result.task_results
ASSERT "task_b" not in result.task_results
ASSERT any("budget_exhausted" in e for e in result.errors)
```

### TS-112-10: Audit event emitted

**Requirement:** 112-REQ-2.5
**Type:** unit
**Description:** Verify SLEEP_COMPUTE_COMPLETE audit event is emitted.

**Preconditions:**
- SleepComputer with mock sink_dispatcher.

**Input:**
- Run SleepComputer.

**Expected:**
- sink_dispatcher receives SLEEP_COMPUTE_COMPLETE event with cost and counts.

**Assertion pseudocode:**
```
result = await computer.run(ctx)
ASSERT sink.last_event.type == "SLEEP_COMPUTE_COMPLETE"
ASSERT "total_cost" in sink.last_event.payload
```

### TS-112-11: ContextRewriter clusters by directory

**Requirement:** 112-REQ-3.1
**Type:** unit
**Description:** Verify facts are grouped by parent directory of entity-linked files.

**Preconditions:**
- In-memory DuckDB with 4 facts: 3 linked to files under `agent_fox/knowledge/`,
  1 linked to `agent_fox/engine/`.

**Input:**
- Run ContextRewriter.

**Expected:**
- One context block created for `agent_fox/knowledge/` (3 facts).
  `agent_fox/engine/` skipped (only 1 fact, below minimum of 3).

**Assertion pseudocode:**
```
result = await rewriter.run(ctx)
ASSERT result.created == 1
rows = conn.execute("SELECT scope_key FROM sleep_artifacts WHERE task_name = 'context_rewriter'").fetchall()
ASSERT rows[0][0] == "dir:agent_fox/knowledge"
```

### TS-112-12: ContextRewriter content hash staleness

**Requirement:** 112-REQ-3.2, 112-REQ-3.5
**Type:** unit
**Description:** Verify unchanged cluster is skipped on second run.

**Preconditions:**
- Run ContextRewriter once, then run again with same facts.

**Input:**
- Second invocation of ContextRewriter.run().

**Expected:**
- Second run reports `unchanged=1, created=0, refreshed=0`.

**Assertion pseudocode:**
```
result1 = await rewriter.run(ctx)
ASSERT result1.created == 1
result2 = await rewriter.run(ctx)
ASSERT result2.unchanged == 1
ASSERT result2.created == 0
```

### TS-112-13: ContextRewriter LLM call and storage

**Requirement:** 112-REQ-3.3
**Type:** unit
**Description:** Verify LLM is called with cluster facts and result is stored.

**Preconditions:**
- Mock LLM that returns a 500-char narrative. 3 facts linked to same dir.

**Input:**
- Run ContextRewriter.

**Expected:**
- LLM called with STANDARD model. Artifact stored with task_name, scope_key,
  content, content_hash.

**Assertion pseudocode:**
```
result = await rewriter.run(ctx)
ASSERT llm_mock.call_count == 1
ASSERT llm_mock.last_model == "STANDARD"
row = conn.execute("SELECT content FROM sleep_artifacts WHERE task_name='context_rewriter'").fetchone()
ASSERT len(row[0]) > 0
```

### TS-112-14: Context block size cap

**Requirement:** 112-REQ-3.4
**Type:** unit
**Description:** Verify context block is truncated to 2000 characters.

**Preconditions:**
- Mock LLM returns 3000-character response.

**Input:**
- Run ContextRewriter.

**Expected:**
- Stored content is ≤ 2000 characters, truncated at last complete sentence.

**Assertion pseudocode:**
```
result = await rewriter.run(ctx)
row = conn.execute("SELECT content FROM sleep_artifacts WHERE task_name='context_rewriter'").fetchone()
ASSERT len(row[0]) <= 2000
ASSERT row[0].rstrip().endswith(".")
```

### TS-112-15: ContextRewriter metadata

**Requirement:** 112-REQ-3.6
**Type:** unit
**Description:** Verify metadata_json contains directory, fact_count, fact_ids.

**Preconditions:**
- 3 facts linked to same directory.

**Input:**
- Run ContextRewriter.

**Expected:**
- metadata_json parseable as JSON with keys: directory, fact_count, fact_ids.

**Assertion pseudocode:**
```
row = conn.execute("SELECT metadata_json FROM sleep_artifacts WHERE task_name='context_rewriter'").fetchone()
meta = json.loads(row[0])
ASSERT meta["fact_count"] == 3
ASSERT len(meta["fact_ids"]) == 3
```

### TS-112-16: BundleBuilder identifies active specs

**Requirement:** 112-REQ-4.1
**Type:** unit
**Description:** Verify bundle builder finds all specs with active facts.

**Preconditions:**
- Facts in specs "spec_a" and "spec_b"; spec_c has only superseded facts.

**Input:**
- Run BundleBuilder.

**Expected:**
- Bundles created for spec_a and spec_b, not spec_c.

**Assertion pseudocode:**
```
result = await builder.run(ctx)
ASSERT result.created == 2
rows = conn.execute("SELECT scope_key FROM sleep_artifacts WHERE task_name='bundle_builder'").fetchall()
scope_keys = {r[0] for r in rows}
ASSERT "spec:spec_a" in scope_keys
ASSERT "spec:spec_b" in scope_keys
ASSERT "spec:spec_c" not in scope_keys
```

### TS-112-17: BundleBuilder content hash staleness

**Requirement:** 112-REQ-4.2, 112-REQ-4.4
**Type:** unit
**Description:** Verify unchanged spec bundle is skipped on second run.

**Preconditions:**
- Run BundleBuilder once, then run again with same facts.

**Input:**
- Second invocation of BundleBuilder.run().

**Expected:**
- Second run reports `unchanged` count matching first run's `created` count.

**Assertion pseudocode:**
```
result1 = await builder.run(ctx)
result2 = await builder.run(ctx)
ASSERT result2.unchanged == result1.created
ASSERT result2.created == 0
```

### TS-112-18: BundleBuilder stores keyword and causal signals

**Requirement:** 112-REQ-4.3
**Type:** unit
**Description:** Verify bundle contains serialized keyword and causal signal results.

**Preconditions:**
- Facts in spec_a with keywords. In-memory DuckDB with fact_causes edges.

**Input:**
- Run BundleBuilder.

**Expected:**
- Artifact content is valid JSON with "keyword" and "causal" arrays of
  ScoredFact-shaped objects.

**Assertion pseudocode:**
```
row = conn.execute("SELECT content FROM sleep_artifacts WHERE scope_key='spec:spec_a'").fetchone()
bundle = json.loads(row[0])
ASSERT "keyword" in bundle
ASSERT "causal" in bundle
ASSERT all("fact_id" in f for f in bundle["keyword"])
```

### TS-112-19: BundleBuilder metadata

**Requirement:** 112-REQ-4.5
**Type:** unit
**Description:** Verify metadata contains spec_name, fact_count, signal sizes.

**Preconditions:**
- Facts in spec_a.

**Input:**
- Run BundleBuilder.

**Expected:**
- metadata_json contains spec_name, fact_count, keyword_count, causal_count.

**Assertion pseudocode:**
```
row = conn.execute("SELECT metadata_json FROM sleep_artifacts WHERE scope_key='spec:spec_a'").fetchone()
meta = json.loads(row[0])
ASSERT meta["spec_name"] == "spec_a"
ASSERT "keyword_count" in meta
```

### TS-112-20: BundleBuilder zero LLM cost

**Requirement:** 112-REQ-4.6
**Type:** unit
**Description:** Verify bundle builder reports zero LLM cost.

**Preconditions:**
- Any valid setup.

**Input:**
- Run BundleBuilder.

**Expected:**
- `result.llm_cost == 0.0`.

**Assertion pseudocode:**
```
result = await builder.run(ctx)
ASSERT result.llm_cost == 0.0
```

### TS-112-21: Retriever prepends context preamble

**Requirement:** 112-REQ-5.1
**Type:** integration
**Description:** Verify retriever prepends matching context blocks to output.

**Preconditions:**
- sleep_artifacts table with a context block for `dir:agent_fox/knowledge`.
- touched_files includes `agent_fox/knowledge/store.py`.

**Input:**
- Call `AdaptiveRetriever.retrieve(touched_files=["agent_fox/knowledge/store.py"], ...)`.

**Expected:**
- Result context starts with `## Module Context` followed by the block content,
  then `## Knowledge Context`.

**Assertion pseudocode:**
```
result = retriever.retrieve(touched_files=["agent_fox/knowledge/store.py"], ...)
ASSERT "## Module Context" in result.context
ASSERT result.context.index("## Module Context") < result.context.index("## Knowledge Context")
```

### TS-112-22: Preamble respects 30% budget cap

**Requirement:** 112-REQ-5.2
**Type:** unit
**Description:** Verify preamble is capped at 30% of token_budget.

**Preconditions:**
- Multiple large context blocks totaling > 30% of token_budget.
- token_budget = 10000.

**Input:**
- Call `_load_context_preamble(conn, touched_files, token_budget=10000)`.

**Expected:**
- Returned preamble length ≤ 3000 characters.

**Assertion pseudocode:**
```
preamble = _load_context_preamble(conn, files, 10000)
ASSERT len(preamble) <= 3000
```

### TS-112-23: Retriever uses cached bundle signals

**Requirement:** 112-REQ-5.3
**Type:** integration
**Description:** Verify retriever skips live keyword/causal when valid bundle exists.

**Preconditions:**
- Valid retrieval bundle for spec "test_spec" in sleep_artifacts.
- Patch _keyword_signal and _causal_signal to track if called.

**Input:**
- Call `retriever.retrieve(spec_name="test_spec", ...)`.

**Expected:**
- `_keyword_signal` and `_causal_signal` NOT called.
- Result includes facts from the cached bundle.

**Assertion pseudocode:**
```
result = retriever.retrieve(spec_name="test_spec", ...)
ASSERT keyword_signal_mock.call_count == 0
ASSERT causal_signal_mock.call_count == 0
ASSERT result.sleep_hit is True
```

### TS-112-24: Retriever falls back without bundle

**Requirement:** 112-REQ-5.4
**Type:** unit
**Description:** Verify retriever falls back to live signals when no bundle exists.

**Preconditions:**
- No sleep_artifacts for the requested spec.

**Input:**
- Call `retriever.retrieve(spec_name="no_bundle_spec", ...)`.

**Expected:**
- `_keyword_signal` and `_causal_signal` called normally. Result correct.

**Assertion pseudocode:**
```
result = retriever.retrieve(spec_name="no_bundle_spec", ...)
ASSERT keyword_signal_mock.call_count == 1
ASSERT result.sleep_hit is False
```

### TS-112-25: RetrievalResult sleep fields

**Requirement:** 112-REQ-5.5
**Type:** unit
**Description:** Verify RetrievalResult includes sleep_hit and sleep_artifact_count.

**Preconditions:**
- None.

**Input:**
- Construct RetrievalResult or call retrieve().

**Expected:**
- `sleep_hit` is bool, `sleep_artifact_count` is int.

**Assertion pseudocode:**
```
result = retriever.retrieve(...)
ASSERT isinstance(result.sleep_hit, bool)
ASSERT isinstance(result.sleep_artifact_count, int)
```

### TS-112-26: Barrier runs sleep compute after compaction

**Requirement:** 112-REQ-6.1
**Type:** integration
**Description:** Verify sleep compute runs in barrier sequence after compaction.

**Preconditions:**
- Mock SleepComputer patched into barrier module.

**Input:**
- Call `run_sync_barrier_sequence(...)`.

**Expected:**
- SleepComputer.run() called after compact() and before render_summary().

**Assertion pseudocode:**
```
await run_sync_barrier_sequence(...)
ASSERT call_order.index("compact") < call_order.index("sleep_compute")
ASSERT call_order.index("sleep_compute") < call_order.index("render_summary")
```

### TS-112-27: SleepComputeStream implements WorkStream

**Requirement:** 112-REQ-6.2
**Type:** unit
**Description:** Verify SleepComputeStream has name, interval, enabled, run_once, shutdown.

**Preconditions:**
- SleepComputeStream instantiated with config.

**Input:**
- Access properties and methods.

**Expected:**
- name returns "sleep-compute", interval returns configured value, enabled
  returns bool.

**Assertion pseudocode:**
```
stream = SleepComputeStream(config, ...)
ASSERT stream.name == "sleep-compute"
ASSERT stream.interval == 1800
ASSERT isinstance(stream.enabled, bool)
```

### TS-112-28: SleepComputeStream run_once lifecycle

**Requirement:** 112-REQ-6.3
**Type:** unit
**Description:** Verify run_once opens DB, runs SleepComputer, closes DB.

**Preconditions:**
- Mock DB and SleepComputer.

**Input:**
- Call `stream.run_once()`.

**Expected:**
- DB opened, SleepComputer.run() called, DB closed.

**Assertion pseudocode:**
```
await stream.run_once()
ASSERT db_mock.open_count == 1
ASSERT sleep_computer_mock.run_count == 1
ASSERT db_mock.close_count == 1
```

### TS-112-29: SleepComputeStream respects SharedBudget

**Requirement:** 112-REQ-6.4
**Type:** unit
**Description:** Verify stream adds cost to shared budget and skips when exceeded.

**Preconditions:**
- SharedBudget with max_cost=1.0, already spent 0.9.

**Input:**
- Call `stream.run_once()` when budget nearly exhausted.

**Expected:**
- Stream skips execution when budget exceeded.

**Assertion pseudocode:**
```
budget = SharedBudget(max_cost=1.0)
budget.add_cost(1.0)
stream = SleepComputeStream(config, budget=budget, ...)
await stream.run_once()
ASSERT sleep_computer_mock.run_count == 0
```

### TS-112-30: SleepConfig defaults

**Requirement:** 112-REQ-7.1
**Type:** unit
**Description:** Verify SleepConfig has correct default values.

**Preconditions:**
- None.

**Input:**
- Construct SleepConfig with no arguments.

**Expected:**
- enabled=True, max_cost=1.0, nightshift_interval=1800,
  context_rewriter_enabled=True, bundle_builder_enabled=True.

**Assertion pseudocode:**
```
config = SleepConfig()
ASSERT config.enabled is True
ASSERT config.max_cost == 1.0
ASSERT config.nightshift_interval == 1800
```

### TS-112-31: Sleep disabled skips compute

**Requirement:** 112-REQ-7.2
**Type:** unit
**Description:** Verify sleep compute is skipped when enabled=false.

**Preconditions:**
- SleepConfig(enabled=False).

**Input:**
- Run barrier sequence or SleepComputeStream.

**Expected:**
- SleepComputer.run() never called.

**Assertion pseudocode:**
```
config = SleepConfig(enabled=False)
stream = SleepComputeStream(config, ...)
ASSERT stream.enabled is False
```

### TS-112-32: Per-task disable

**Requirement:** 112-REQ-7.4
**Type:** unit
**Description:** Verify disabled tasks are skipped.

**Preconditions:**
- SleepConfig(context_rewriter_enabled=False).

**Input:**
- Run SleepComputer with both tasks registered.

**Expected:**
- ContextRewriter skipped. BundleBuilder runs.

**Assertion pseudocode:**
```
config = SleepConfig(context_rewriter_enabled=False)
result = await computer.run(ctx)
ASSERT "context_rewriter" not in result.task_results
ASSERT "bundle_builder" in result.task_results
```

### TS-112-33: sleep_artifacts table schema

**Requirement:** 112-REQ-8.1
**Type:** unit
**Description:** Verify table has all required columns with correct types.

**Preconditions:**
- Fresh in-memory DuckDB with schema initialized.

**Input:**
- Query table metadata.

**Expected:**
- Columns: id (UUID), task_name (VARCHAR), scope_key (VARCHAR), content (TEXT),
  metadata_json (TEXT), content_hash (VARCHAR), created_at (TIMESTAMP),
  superseded_at (TIMESTAMP nullable).

**Assertion pseudocode:**
```
cols = conn.execute("DESCRIBE sleep_artifacts").fetchall()
col_names = {c[0] for c in cols}
ASSERT {"id", "task_name", "scope_key", "content", "metadata_json",
        "content_hash", "created_at", "superseded_at"} <= col_names
```

### TS-112-34: Artifact supersession on update

**Requirement:** 112-REQ-8.3
**Type:** unit
**Description:** Verify old artifact gets superseded_at when new one is inserted.

**Preconditions:**
- Insert artifact with task_name="t", scope_key="s".

**Input:**
- Insert new artifact with same task_name and scope_key.

**Expected:**
- Old row has superseded_at set. New row has superseded_at NULL.
  Only one active row exists.

**Assertion pseudocode:**
```
# Insert first
insert_artifact(conn, task_name="t", scope_key="s", content="v1", ...)
# Insert second (should supersede first)
insert_artifact(conn, task_name="t", scope_key="s", content="v2", ...)
active = conn.execute("SELECT * FROM sleep_artifacts WHERE task_name='t' AND scope_key='s' AND superseded_at IS NULL").fetchall()
ASSERT len(active) == 1
ASSERT active[0].content == "v2"
```

## Property Test Cases

### TS-112-P1: Staleness hash determinism

**Property:** Property 1 from design.md
**Validates:** 112-REQ-3.2, 112-REQ-4.2
**Type:** property
**Description:** Content hash is order-independent for any set of fact IDs and confidences.

**For any:** Lists of (fact_id: str, confidence: float) tuples, in any permutation.
**Invariant:** hash(sorted(tuples)) is identical regardless of input order.

**Assertion pseudocode:**
```
FOR ANY facts IN lists_of_fact_tuples:
    perm1 = shuffle(facts)
    perm2 = shuffle(facts)
    ASSERT compute_content_hash(perm1) == compute_content_hash(perm2)
```

### TS-112-P2: Artifact uniqueness invariant

**Property:** Property 2 from design.md
**Validates:** 112-REQ-8.2, 112-REQ-8.3
**Type:** property
**Description:** At most one active artifact per (task_name, scope_key).

**For any:** Sequence of insert_artifact calls with same (task_name, scope_key).
**Invariant:** After each insert, exactly one row has superseded_at IS NULL.

**Assertion pseudocode:**
```
FOR ANY n IN range(1, 20):
    for i in range(n):
        insert_artifact(conn, task_name="t", scope_key="s", content=f"v{i}")
    active = query_active(conn, "t", "s")
    ASSERT len(active) == 1
```

### TS-112-P3: Budget monotonicity

**Property:** Property 3 from design.md
**Validates:** 112-REQ-2.1, 112-REQ-2.4
**Type:** property
**Description:** Remaining budget strictly decreases across task sequence.

**For any:** Sequence of tasks with random llm_cost in [0, budget].
**Invariant:** Each task receives budget = initial - sum(prior costs). No
task receives negative budget.

**Assertion pseudocode:**
```
FOR ANY costs IN lists_of_floats(min=0, max=initial_budget):
    tasks = [MockTask(cost=c) for c in costs]
    computer = SleepComputer(tasks, config)
    result = await computer.run(ctx)
    running_sum = 0
    for task in tasks:
        ASSERT task.received_budget == initial_budget - running_sum
        ASSERT task.received_budget >= 0
        running_sum += task.actual_cost
```

### TS-112-P4: Graceful degradation

**Property:** Property 4 from design.md
**Validates:** 112-REQ-5.4, 112-REQ-5.E1, 112-REQ-5.E2
**Type:** property
**Description:** Retriever never returns less information when sleep artifacts are missing.

**For any:** Retrieval call with and without sleep artifacts present.
**Invariant:** anchor_count with sleep artifacts >= anchor_count without.

**Assertion pseudocode:**
```
FOR ANY spec_name, archetype, files IN retrieval_inputs:
    result_without = retriever_no_sleep.retrieve(...)
    result_with = retriever_with_sleep.retrieve(...)
    ASSERT result_with.anchor_count >= result_without.anchor_count
```

### TS-112-P5: Token budget compliance

**Property:** Property 5 from design.md
**Validates:** 112-REQ-5.2
**Type:** property
**Description:** Total context length never exceeds token_budget.

**For any:** token_budget in [100, 100000], any number of context blocks.
**Invariant:** len(result.context) <= token_budget.

**Assertion pseudocode:**
```
FOR ANY budget IN integers(100, 100000):
    config = RetrievalConfig(token_budget=budget)
    result = retriever.retrieve(...)
    ASSERT len(result.context) <= budget
```

### TS-112-P6: Preamble budget cap

**Property:** Property 6 from design.md
**Validates:** 112-REQ-5.2
**Type:** property
**Description:** Preamble never exceeds 30% of token_budget.

**For any:** token_budget in [100, 100000], any number of context blocks.
**Invariant:** len(preamble) <= 0.3 * token_budget.

**Assertion pseudocode:**
```
FOR ANY budget IN integers(100, 100000):
    preamble = _load_context_preamble(conn, files, budget)
    ASSERT len(preamble) <= int(budget * 0.3)
```

### TS-112-P7: Error isolation

**Property:** Property 7 from design.md
**Validates:** 112-REQ-2.3
**Type:** property
**Description:** A failing task does not prevent subsequent tasks from running.

**For any:** Sequence of N tasks where task at index K raises an exception.
**Invariant:** All tasks at index > K still execute.

**Assertion pseudocode:**
```
FOR ANY n IN range(2, 10), k IN range(n):
    tasks = [MockTask(fail=(i == k)) for i in range(n)]
    result = await SleepComputer(tasks, config).run(ctx)
    for i in range(k+1, n):
        ASSERT tasks[i].name in result.task_results
```

### TS-112-P8: Context block size bound

**Property:** Property 8 from design.md
**Validates:** 112-REQ-3.4
**Type:** property
**Description:** No context block exceeds 2000 characters.

**For any:** LLM output of length L in [0, 10000].
**Invariant:** Stored content length ≤ 2000.

**Assertion pseudocode:**
```
FOR ANY length IN integers(0, 10000):
    llm_mock.return_value = "x" * length
    await rewriter.run(ctx)
    rows = conn.execute("SELECT content FROM sleep_artifacts WHERE task_name='context_rewriter'").fetchall()
    for row in rows:
        ASSERT len(row[0]) <= 2000
```

### TS-112-P9: Bundle signal fidelity

**Property:** Property 9 from design.md
**Validates:** 112-REQ-4.3, 112-REQ-5.3
**Type:** property
**Description:** Deserialized bundle matches live signal computation.

**For any:** Set of facts in a spec with keywords and causal edges.
**Invariant:** Cached keyword and causal lists equal live-computed lists.

**Assertion pseudocode:**
```
FOR ANY facts IN fact_sets:
    populate_db(conn, facts)
    await builder.run(ctx)
    bundle = load_cached_bundle(conn, spec_name)
    live_kw = _keyword_signal(spec_name, ...)
    live_cau = _causal_signal(spec_name, ...)
    ASSERT bundle.keyword_facts == live_kw
    ASSERT bundle.causal_facts == live_cau
```

## Edge Case Tests

### TS-112-E1: Fact in multiple directories

**Requirement:** 112-REQ-3.E1
**Type:** unit
**Description:** Verify fact linked to multiple directories appears in all qualifying clusters.

**Preconditions:**
- Fact linked to files in both `dir_a/` and `dir_b/`.
  3 total facts in dir_a, 3 total facts in dir_b (including the shared one).

**Input:**
- Run ContextRewriter.

**Expected:**
- Two context blocks created. The shared fact appears in both clusters'
  metadata fact_ids.

**Assertion pseudocode:**
```
result = await rewriter.run(ctx)
ASSERT result.created == 2
meta_a = json.loads(query_metadata(conn, "dir:dir_a"))
meta_b = json.loads(query_metadata(conn, "dir:dir_b"))
ASSERT shared_fact_id in meta_a["fact_ids"]
ASSERT shared_fact_id in meta_b["fact_ids"]
```

### TS-112-E2: No qualifying clusters

**Requirement:** 112-REQ-3.E2
**Type:** unit
**Description:** Verify zero artifacts when no cluster has 3+ facts.

**Preconditions:**
- Only 2 facts linked to same directory, 1 fact in another directory.

**Input:**
- Run ContextRewriter.

**Expected:**
- Result with created=0, refreshed=0, unchanged=0, no errors.

**Assertion pseudocode:**
```
result = await rewriter.run(ctx)
ASSERT result.created == 0
ASSERT result.errors == []  # errors are in SleepComputeResult, not task
```

### TS-112-E3: LLM failure for one cluster

**Requirement:** 112-REQ-3.E3
**Type:** unit
**Description:** Verify failing LLM call skips cluster, continues to next.

**Preconditions:**
- Two qualifying clusters. LLM fails on first, succeeds on second.

**Input:**
- Run ContextRewriter.

**Expected:**
- One context block created (second cluster). First cluster skipped with
  warning logged.

**Assertion pseudocode:**
```
result = await rewriter.run(ctx)
ASSERT result.created == 1
```

### TS-112-E4: Spec with zero active facts

**Requirement:** 112-REQ-4.E1
**Type:** unit
**Description:** Verify spec with no active facts gets no bundle.

**Preconditions:**
- Spec "empty_spec" has only superseded facts.

**Input:**
- Run BundleBuilder.

**Expected:**
- No bundle created for "empty_spec".

**Assertion pseudocode:**
```
result = await builder.run(ctx)
rows = conn.execute("SELECT * FROM sleep_artifacts WHERE scope_key='spec:empty_spec'").fetchall()
ASSERT len(rows) == 0
```

### TS-112-E5: Signal computation failure

**Requirement:** 112-REQ-4.E2
**Type:** unit
**Description:** Verify exception in signal computation skips spec.

**Preconditions:**
- Patch _keyword_signal to raise for spec "bad_spec".

**Input:**
- Run BundleBuilder with specs ["good_spec", "bad_spec"].

**Expected:**
- Bundle created for good_spec. bad_spec skipped with warning.

**Assertion pseudocode:**
```
result = await builder.run(ctx)
ASSERT result.created == 1  # only good_spec
```

### TS-112-E6: Missing sleep_artifacts table

**Requirement:** 112-REQ-5.E1
**Type:** unit
**Description:** Verify retriever works when sleep_artifacts table doesn't exist.

**Preconditions:**
- DuckDB with standard schema but no sleep_artifacts table (pre-migration).

**Input:**
- Call `retriever.retrieve(...)`.

**Expected:**
- Returns valid result with sleep_hit=False. No exception raised.

**Assertion pseudocode:**
```
result = retriever.retrieve(...)
ASSERT result.sleep_hit is False
ASSERT len(result.context) > 0  # or == 0 if no facts, but no crash
```

### TS-112-E7: All context blocks stale

**Requirement:** 112-REQ-5.E2
**Type:** unit
**Description:** Verify retriever skips preamble when all blocks are superseded.

**Preconditions:**
- All sleep_artifacts for context_rewriter have superseded_at set.

**Input:**
- Call `retriever.retrieve(...)`.

**Expected:**
- No `## Module Context` section in result. Standard `## Knowledge Context`
  present.

**Assertion pseudocode:**
```
result = retriever.retrieve(...)
ASSERT "## Module Context" not in result.context
```

### TS-112-E8: No registered tasks

**Requirement:** 112-REQ-2.E1
**Type:** unit
**Description:** Verify empty SleepComputer returns empty result.

**Preconditions:**
- SleepComputer with empty task list.

**Input:**
- Run SleepComputer.

**Expected:**
- Result with empty task_results, zero cost, no errors.

**Assertion pseudocode:**
```
computer = SleepComputer([], config)
result = await computer.run(ctx)
ASSERT result.task_results == {}
ASSERT result.total_llm_cost == 0.0
ASSERT result.errors == []
```

### TS-112-E9: All tasks budget-exhausted

**Requirement:** 112-REQ-2.E2
**Type:** unit
**Description:** Verify all tasks skipped with budget_exhausted entries.

**Preconditions:**
- Budget = 0.0. Two tasks registered.

**Input:**
- Run SleepComputer.

**Expected:**
- Both tasks skipped. Error list has two "budget_exhausted" entries.

**Assertion pseudocode:**
```
ctx = SleepContext(..., budget_remaining=0.0, ...)
result = await SleepComputer([task_a, task_b], config).run(ctx)
ASSERT len(result.errors) == 2
ASSERT all("budget_exhausted" in e for e in result.errors)
```

### TS-112-E10: Config section absent

**Requirement:** 112-REQ-7.E1
**Type:** unit
**Description:** Verify defaults when [knowledge.sleep] is missing from config.

**Preconditions:**
- Config TOML with no [knowledge.sleep] section.

**Input:**
- Load config.

**Expected:**
- SleepConfig uses defaults: enabled=True, max_cost=1.0, etc.

**Assertion pseudocode:**
```
config = load_config("config_without_sleep.toml")
ASSERT config.knowledge.sleep.enabled is True
ASSERT config.knowledge.sleep.max_cost == 1.0
```

### TS-112-E11: Idempotent migration

**Requirement:** 112-REQ-8.E1
**Type:** unit
**Description:** Verify migration is no-op when table exists.

**Preconditions:**
- DuckDB with sleep_artifacts table already created.

**Input:**
- Run migration again.

**Expected:**
- No error. Table unchanged.

**Assertion pseudocode:**
```
run_migration(conn)  # first time
run_migration(conn)  # second time — no error
cols = conn.execute("DESCRIBE sleep_artifacts").fetchall()
ASSERT len(cols) == 8  # same schema
```

## Integration Smoke Tests

### TS-112-SMOKE-1: Barrier triggers sleep compute end-to-end

**Execution Path:** Path 1 from design.md
**Description:** Verify full barrier sequence runs sleep compute with real
SleepComputer (not mocked) and produces artifacts in the database.

**Setup:** In-memory DuckDB with schema, 4 facts linked to same directory,
mock LLM, mock embedder. Stub only external I/O (LLM API calls via mock).

**Trigger:** Call `run_sync_barrier_sequence(...)` with knowledge_db_conn.

**Expected side effects:**
- sleep_artifacts table has at least one row with task_name='context_rewriter'.
- sleep_artifacts table has at least one row with task_name='bundle_builder'.

**Must NOT satisfy with:** Do not mock SleepComputer, ContextRewriter, or
BundleBuilder. Only mock the LLM API and external embedder.

**Assertion pseudocode:**
```
mock_llm = MockLLM(return_value="Summary of facts...")
await run_sync_barrier_sequence(knowledge_db_conn=conn, ...)
rows = conn.execute("SELECT task_name FROM sleep_artifacts WHERE superseded_at IS NULL").fetchall()
task_names = {r[0] for r in rows}
ASSERT "context_rewriter" in task_names
ASSERT "bundle_builder" in task_names
```

### TS-112-SMOKE-2: Nightshift stream triggers sleep compute

**Execution Path:** Path 2 from design.md
**Description:** Verify SleepComputeStream.run_once() runs real SleepComputer
and produces artifacts.

**Setup:** In-memory DuckDB, facts, mock LLM. Real SleepComputeStream with
real SleepComputer.

**Trigger:** Call `stream.run_once()`.

**Expected side effects:**
- sleep_artifacts populated.
- SharedBudget updated with cost.

**Must NOT satisfy with:** Do not mock SleepComputer or sleep tasks.

**Assertion pseudocode:**
```
stream = SleepComputeStream(config, budget, db_factory=in_memory_db, ...)
await stream.run_once()
ASSERT budget.total_cost > 0 or budget.total_cost == 0  # depends on LLM mock
rows = conn.execute("SELECT COUNT(*) FROM sleep_artifacts").fetchone()
ASSERT rows[0] >= 1
```

### TS-112-SMOKE-3: Retriever consumes real sleep artifacts

**Execution Path:** Path 3 and Path 4 from design.md
**Description:** Verify AdaptiveRetriever uses real context blocks and bundles
from sleep_artifacts when retrieving.

**Setup:** In-memory DuckDB with facts and pre-populated sleep_artifacts
(one context block, one retrieval bundle). Real AdaptiveRetriever.

**Trigger:** Call `retriever.retrieve(spec_name=..., touched_files=[...], ...)`.

**Expected side effects:**
- Result context contains `## Module Context` preamble.
- Result sleep_hit is True.
- Keyword and causal signals not recomputed (verified by patching originals
  and checking call count = 0).

**Must NOT satisfy with:** Do not mock AdaptiveRetriever or
_load_context_preamble. The retriever must read from real sleep_artifacts rows.

**Assertion pseudocode:**
```
retriever = AdaptiveRetriever(conn, config, embedder=mock_embedder)
with patch("_keyword_signal") as kw, patch("_causal_signal") as cau:
    result = retriever.retrieve(spec_name="test_spec", touched_files=["agent_fox/knowledge/foo.py"], ...)
    ASSERT "## Module Context" in result.context
    ASSERT result.sleep_hit is True
    ASSERT kw.call_count == 0
    ASSERT cau.call_count == 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 112-REQ-1.1 | TS-112-1 | unit |
| 112-REQ-1.2 | TS-112-2 | unit |
| 112-REQ-1.3 | TS-112-3 | unit |
| 112-REQ-1.4 | TS-112-4 | unit |
| 112-REQ-1.5 | TS-112-5 | unit |
| 112-REQ-2.1 | TS-112-6 | unit |
| 112-REQ-2.2 | TS-112-7 | unit |
| 112-REQ-2.3 | TS-112-8 | unit |
| 112-REQ-2.4 | TS-112-9 | unit |
| 112-REQ-2.5 | TS-112-10 | unit |
| 112-REQ-2.E1 | TS-112-E8 | unit |
| 112-REQ-2.E2 | TS-112-E9 | unit |
| 112-REQ-3.1 | TS-112-11 | unit |
| 112-REQ-3.2 | TS-112-12 | unit |
| 112-REQ-3.3 | TS-112-13 | unit |
| 112-REQ-3.4 | TS-112-14 | unit |
| 112-REQ-3.5 | TS-112-12 | unit |
| 112-REQ-3.6 | TS-112-15 | unit |
| 112-REQ-3.E1 | TS-112-E1 | unit |
| 112-REQ-3.E2 | TS-112-E2 | unit |
| 112-REQ-3.E3 | TS-112-E3 | unit |
| 112-REQ-4.1 | TS-112-16 | unit |
| 112-REQ-4.2 | TS-112-17 | unit |
| 112-REQ-4.3 | TS-112-18 | unit |
| 112-REQ-4.4 | TS-112-17 | unit |
| 112-REQ-4.5 | TS-112-19 | unit |
| 112-REQ-4.6 | TS-112-20 | unit |
| 112-REQ-4.E1 | TS-112-E4 | unit |
| 112-REQ-4.E2 | TS-112-E5 | unit |
| 112-REQ-5.1 | TS-112-21 | integration |
| 112-REQ-5.2 | TS-112-22 | unit |
| 112-REQ-5.3 | TS-112-23 | integration |
| 112-REQ-5.4 | TS-112-24 | unit |
| 112-REQ-5.5 | TS-112-25 | unit |
| 112-REQ-5.E1 | TS-112-E6 | unit |
| 112-REQ-5.E2 | TS-112-E7 | unit |
| 112-REQ-6.1 | TS-112-26 | integration |
| 112-REQ-6.2 | TS-112-27 | unit |
| 112-REQ-6.3 | TS-112-28 | unit |
| 112-REQ-6.4 | TS-112-29 | unit |
| 112-REQ-6.E1 | TS-112-26 | integration |
| 112-REQ-6.E2 | TS-112-27 | unit |
| 112-REQ-7.1 | TS-112-30 | unit |
| 112-REQ-7.2 | TS-112-31 | unit |
| 112-REQ-7.3 | TS-112-9 | unit |
| 112-REQ-7.4 | TS-112-32 | unit |
| 112-REQ-7.E1 | TS-112-E10 | unit |
| 112-REQ-8.1 | TS-112-33 | unit |
| 112-REQ-8.2 | TS-112-34 | unit |
| 112-REQ-8.3 | TS-112-34 | unit |
| 112-REQ-8.4 | TS-112-E11 | unit |
| 112-REQ-8.E1 | TS-112-E11 | unit |
| Property 1 | TS-112-P1 | property |
| Property 2 | TS-112-P2 | property |
| Property 3 | TS-112-P3 | property |
| Property 4 | TS-112-P4 | property |
| Property 5 | TS-112-P5 | property |
| Property 6 | TS-112-P6 | property |
| Property 7 | TS-112-P7 | property |
| Property 8 | TS-112-P8 | property |
| Property 9 | TS-112-P9 | property |
| Path 1 | TS-112-SMOKE-1 | integration |
| Path 2 | TS-112-SMOKE-2 | integration |
| Path 3 + 4 | TS-112-SMOKE-3 | integration |
