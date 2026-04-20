# Test Specification: Knowledge Consolidation Agent

## Overview

Tests validate the consolidation pipeline across four layers: unit tests for
each step (git verification, merging, promotion, pruning), property-based
tests for correctness invariants, edge case tests for error handling, and
integration smoke tests for the two execution paths. All DuckDB tests use
real in-memory connections. LLM calls and subprocess (`git diff`) are mocked.

## Test Cases

### TS-96-1: Pipeline step ordering and result

**Requirement:** 96-REQ-1.1
**Type:** unit
**Description:** Verify the pipeline executes all six steps in order and
returns a complete `ConsolidationResult`.

**Preconditions:**
- DuckDB with migrations applied (including v8). A few active facts exist.

**Input:**
- `run_consolidation(conn, repo_root, specs, model)` with mocked LLM and
  subprocess.

**Expected:**
- `ConsolidationResult` has non-None values for all step results.
- Steps executed in order (verified via call order tracking).

**Assertion pseudocode:**
```
result = await run_consolidation(conn, repo_root, specs, model)
ASSERT result.verification is not None
ASSERT result.merging is not None
ASSERT result.promotion is not None
ASSERT result.pruning is not None
```

### TS-96-2: Step failure isolation

**Requirement:** 96-REQ-1.2
**Type:** unit
**Description:** Verify that a failing step does not block subsequent steps.

**Preconditions:**
- Mock `_verify_against_git` to raise RuntimeError.

**Input:**
- `run_consolidation(...)`.

**Expected:**
- `verification` is None in result. `errors` contains "git_verification".
- Merging, promotion, and pruning steps still executed.

**Assertion pseudocode:**
```
result = await run_consolidation(conn, repo_root, specs, model)
ASSERT result.verification is None
ASSERT "git_verification" in result.errors
ASSERT result.merging is not None
```

### TS-96-3: Audit event emission

**Requirement:** 96-REQ-1.3
**Type:** unit
**Description:** Verify `consolidation.complete` audit event is emitted.

**Preconditions:**
- Mock sink dispatcher.

**Input:**
- `run_consolidation(conn, repo_root, specs, model, sink_dispatcher=mock_sink)`.

**Expected:**
- `mock_sink.dispatch` called with event_type `consolidation.complete`.

**Assertion pseudocode:**
```
await run_consolidation(...)
ASSERT mock_sink.dispatch.called
event = mock_sink.dispatch.call_args
ASSERT event.event_type == "consolidation.complete"
```

### TS-96-4: Entity graph refresh

**Requirement:** 96-REQ-2.1
**Type:** unit
**Description:** Verify that `analyze_codebase` is called during entity
graph refresh.

**Preconditions:**
- Mock `analyze_codebase` to return AnalysisResult(5, 3, 0).

**Input:**
- `_refresh_entity_graph(conn, repo_root)`.

**Expected:**
- Returns AnalysisResult from `analyze_codebase`.

**Assertion pseudocode:**
```
result = _refresh_entity_graph(conn, repo_root)
ASSERT mock_analyze.called_with(repo_root, conn)
ASSERT result.entities_upserted == 5
```

### TS-96-5: Unlinked fact detection and linking

**Requirement:** 96-REQ-2.2
**Type:** unit
**Description:** Verify unlinked facts are detected and passed to
`link_facts`.

**Preconditions:**
- 3 active facts: 2 with entity links, 1 without.
- Mock `link_facts` to return LinkResult(1, 1, 0).

**Input:**
- `_link_unlinked_facts(conn, repo_root)`.

**Expected:**
- `link_facts` called with the 1 unlinked fact.

**Assertion pseudocode:**
```
result = _link_unlinked_facts(conn, repo_root)
ASSERT len(mock_link.call_args.facts) == 1
ASSERT result.facts_processed == 1
```

### TS-96-6: Consolidation result includes entity counts

**Requirement:** 96-REQ-2.3
**Type:** unit
**Description:** Verify entity graph results appear in ConsolidationResult.

**Preconditions:**
- Mock entity graph functions.

**Input:**
- `run_consolidation(...)`.

**Expected:**
- `result.entity_refresh` is the AnalysisResult from `analyze_codebase`.
- `result.facts_linked` matches LinkResult.links_created.

**Assertion pseudocode:**
```
result = await run_consolidation(...)
ASSERT result.entity_refresh is not None
ASSERT result.facts_linked >= 0
```

### TS-96-7: Git verification queries fact-entity links

**Requirement:** 96-REQ-3.1
**Type:** unit
**Description:** Verify git verification queries facts with entity links.

**Preconditions:**
- 2 facts with file entity links, 1 fact without links.
- All linked files exist on disk.

**Input:**
- `_verify_against_git(conn, repo_root, threshold=0.5)`.

**Expected:**
- Only the 2 linked facts are checked.
- `VerificationResult.facts_checked == 2`.

**Assertion pseudocode:**
```
result = _verify_against_git(conn, repo_root, 0.5)
ASSERT result.facts_checked == 2
```

### TS-96-8: Supersede facts with all files deleted

**Requirement:** 96-REQ-3.2
**Type:** unit
**Description:** Verify facts are superseded when all linked files are
deleted.

**Preconditions:**
- Fact F linked to file entity "src/old.py". File does not exist on disk.

**Input:**
- `_verify_against_git(conn, repo_root, 0.5)`.

**Expected:**
- F.superseded_by == CONSOLIDATION_STALE_SENTINEL.
- `VerificationResult.superseded_count == 1`.

**Assertion pseudocode:**
```
result = _verify_against_git(conn, repo_root, 0.5)
ASSERT result.superseded_count == 1
fact = query_fact(conn, F.id)
ASSERT fact.superseded_by == str(CONSOLIDATION_STALE_SENTINEL)
```

### TS-96-9: Halve confidence for significantly changed files

**Requirement:** 96-REQ-3.3
**Type:** unit
**Description:** Verify confidence is halved when linked files changed >50%.

**Preconditions:**
- Fact F with confidence=0.8, commit_sha="abc123", linked to "src/foo.py".
- File exists. Mock `git diff --numstat` returns 60 insertions, 40 deletions.
  File has 100 lines. Change ratio = 1.0 > 0.5.

**Input:**
- `_verify_against_git(conn, repo_root, 0.5)`.

**Expected:**
- F.confidence updated to 0.4.
- `VerificationResult.decayed_count == 1`.

**Assertion pseudocode:**
```
result = _verify_against_git(conn, repo_root, 0.5)
ASSERT result.decayed_count == 1
fact = query_fact(conn, F.id)
ASSERT fact.confidence == 0.4
```

### TS-96-10: Verification result counts

**Requirement:** 96-REQ-3.4
**Type:** unit
**Description:** Verify VerificationResult contains correct counts.

**Preconditions:**
- 3 linked facts: 1 with deleted file, 1 significantly changed, 1 unchanged.

**Input:**
- `_verify_against_git(conn, repo_root, 0.5)`.

**Expected:**
- `VerificationResult(3, 1, 1, 1)`.

**Assertion pseudocode:**
```
result = _verify_against_git(conn, repo_root, 0.5)
ASSERT result.facts_checked == 3
ASSERT result.superseded_count == 1
ASSERT result.decayed_count == 1
ASSERT result.unchanged_count == 1
```

### TS-96-11: Cross-spec cluster detection

**Requirement:** 96-REQ-4.1
**Type:** unit
**Description:** Verify similar facts from different specs are clustered.

**Preconditions:**
- Facts F1 (spec_a) and F2 (spec_b) with cosine similarity 0.90.
- Fact F3 (spec_a) with similarity < 0.85 to both.

**Input:**
- `_merge_related_facts(conn, model, threshold=0.85, ...)`.

**Expected:**
- One cluster found: {F1, F2}. F3 not included.

**Assertion pseudocode:**
```
result = _merge_related_facts(conn, model, 0.85, emb)
ASSERT result.clusters_found >= 1
```

### TS-96-12: LLM merge classification

**Requirement:** 96-REQ-4.2
**Type:** unit
**Description:** Verify LLM is called for each cluster to decide merge/link.

**Preconditions:**
- One cluster of 2 facts. Mock LLM returns {"action": "merge", "content": "..."}.

**Input:**
- `_merge_related_facts(conn, model, 0.85, emb)`.

**Expected:**
- LLM called with the cluster facts.

**Assertion pseudocode:**
```
result = _merge_related_facts(conn, model, 0.85, emb)
ASSERT mock_llm.called
```

### TS-96-13: Merge action creates consolidated fact

**Requirement:** 96-REQ-4.3
**Type:** unit
**Description:** Verify merge creates new fact and supersedes originals.

**Preconditions:**
- Cluster {F1, F2}. Mock LLM returns "merge" with content.

**Input:**
- `_merge_related_facts(conn, model, 0.85, emb)`.

**Expected:**
- New fact created with LLM content.
- F1 and F2 superseded_by == new fact ID.
- `MergeResult.consolidated_created == 1, facts_merged == 2`.

**Assertion pseudocode:**
```
result = _merge_related_facts(conn, model, 0.85, emb)
ASSERT result.consolidated_created == 1
ASSERT result.facts_merged == 2
ASSERT query_fact(conn, F1.id).superseded_by is not None
```

### TS-96-14: Link action adds causal edges

**Requirement:** 96-REQ-4.4
**Type:** unit
**Description:** Verify link decision adds causal edges without modifying
facts.

**Preconditions:**
- Cluster {F1, F2}. Mock LLM returns "link".

**Input:**
- `_merge_related_facts(conn, model, 0.85, emb)`.

**Expected:**
- Causal edge added between F1 and F2.
- Neither F1 nor F2 superseded.
- `MergeResult.facts_linked >= 1`.

**Assertion pseudocode:**
```
result = _merge_related_facts(conn, model, 0.85, emb)
ASSERT result.facts_linked >= 1
ASSERT query_fact(conn, F1.id).superseded_by is None
```

### TS-96-15: Pattern candidate detection (3+ specs)

**Requirement:** 96-REQ-5.1
**Type:** unit
**Description:** Verify similar facts from 3+ specs are identified as
pattern candidates.

**Preconditions:**
- Similar facts from spec_a, spec_b, spec_c (similarity > 0.85).

**Input:**
- `_promote_patterns(conn, model)`.

**Expected:**
- At least one candidate group found with facts from 3 distinct specs.

**Assertion pseudocode:**
```
result = _promote_patterns(conn, model)
ASSERT result.candidates_found >= 1
```

### TS-96-16: LLM pattern confirmation

**Requirement:** 96-REQ-5.2
**Type:** unit
**Description:** Verify LLM is called to confirm patterns.

**Preconditions:**
- One candidate group. Mock LLM returns {"is_pattern": true, "description": "..."}.

**Input:**
- `_promote_patterns(conn, model)`.

**Expected:**
- LLM called with candidate facts.

**Assertion pseudocode:**
```
result = _promote_patterns(conn, model)
ASSERT mock_llm.called
```

### TS-96-17: Pattern fact creation

**Requirement:** 96-REQ-5.3
**Type:** unit
**Description:** Verify confirmed pattern creates new fact with causal edges.

**Preconditions:**
- Mock LLM confirms pattern with description.

**Input:**
- `_promote_patterns(conn, model)`.

**Expected:**
- New fact: category=PATTERN, confidence=0.9, content=LLM description.
- Causal edges from original facts to pattern fact.

**Assertion pseudocode:**
```
result = _promote_patterns(conn, model)
ASSERT result.pattern_facts_created == 1
pattern = query_latest_pattern_fact(conn)
ASSERT pattern.category == "pattern"
ASSERT pattern.confidence == 0.9
```

### TS-96-18: Redundant chain detection

**Requirement:** 96-REQ-6.1
**Type:** unit
**Description:** Verify redundant chains A->B->C with direct A->C are found.

**Preconditions:**
- Causal edges: A->B, B->C, A->C.

**Input:**
- `_prune_redundant_chains(conn, model)`.

**Expected:**
- One chain found: (A, B, C).

**Assertion pseudocode:**
```
result = _prune_redundant_chains(conn, model)
ASSERT result.chains_evaluated >= 1
```

### TS-96-19: LLM chain evaluation

**Requirement:** 96-REQ-6.2
**Type:** unit
**Description:** Verify LLM is called to evaluate intermediate B.

**Preconditions:**
- Chain (A, B, C). Mock LLM returns {"meaningful": false}.

**Input:**
- `_prune_redundant_chains(conn, model)`.

**Expected:**
- LLM called with facts A, B, C.

**Assertion pseudocode:**
```
result = _prune_redundant_chains(conn, model)
ASSERT mock_llm.called
```

### TS-96-20: Redundant edge removal

**Requirement:** 96-REQ-6.3
**Type:** unit
**Description:** Verify edges A->B and B->C are removed when B is not
meaningful, while A->C is preserved.

**Preconditions:**
- Chain (A, B, C). Mock LLM says B not meaningful.

**Input:**
- `_prune_redundant_chains(conn, model)`.

**Expected:**
- Edge A->B removed.
- Edge B->C removed.
- Edge A->C preserved.
- `PruneResult.edges_removed == 2`.

**Assertion pseudocode:**
```
result = _prune_redundant_chains(conn, model)
ASSERT result.edges_removed == 2
ASSERT not edge_exists(conn, A.id, B.id)
ASSERT not edge_exists(conn, B.id, C.id)
ASSERT edge_exists(conn, A.id, C.id)
```

### TS-96-21: Barrier triggers consolidation on completed specs

**Requirement:** 96-REQ-7.1
**Type:** integration
**Description:** Verify sync barrier calls consolidation when specs complete.

**Preconditions:**
- Mock `completed_spec_names()` to return {"spec_a"}.
- Mock `run_consolidation`.

**Input:**
- `run_sync_barrier_sequence(...)`.

**Expected:**
- `run_consolidation` called with completed_specs={"spec_a"}.

**Assertion pseudocode:**
```
await run_sync_barrier_sequence(...)
ASSERT mock_consolidation.called
ASSERT "spec_a" in mock_consolidation.call_args.completed_specs
```

### TS-96-22: End-of-run consolidation

**Requirement:** 96-REQ-7.2
**Type:** integration
**Description:** Verify end-of-run calls consolidation for unconsolidated
specs.

**Preconditions:**
- completed_spec_names = {"spec_a", "spec_b"}.
- _consolidated_specs = {"spec_a"} (already consolidated at barrier).

**Input:**
- End-of-run cleanup block.

**Expected:**
- `run_consolidation` called with completed_specs={"spec_b"}.

**Assertion pseudocode:**
```
remaining = completed - already_consolidated
ASSERT remaining == {"spec_b"}
```

### TS-96-23: Exclusive write access

**Requirement:** 96-REQ-7.3
**Type:** unit
**Description:** Verify consolidation runs within the sync barrier (which
holds exclusive access).

**Preconditions:**
- Barrier sequence with consolidation hook.

**Input:**
- Inspect call ordering within `run_sync_barrier_sequence`.

**Expected:**
- Consolidation runs after lifecycle cleanup and before memory summary
  regeneration (within the barrier's exclusive window).

**Assertion pseudocode:**
```
call_order = track_call_order(barrier_sequence)
ASSERT call_order.index("consolidation") > call_order.index("lifecycle_cleanup")
ASSERT call_order.index("consolidation") < call_order.index("render_summary")
```

### TS-96-24: Separate cost reporting

**Requirement:** 96-REQ-7.4
**Type:** unit
**Description:** Verify consolidation costs are reported separately via
audit event.

**Preconditions:**
- Mock LLM returns costs. Mock sink dispatcher.

**Input:**
- `run_consolidation(...)` with LLM calls.

**Expected:**
- `consolidation.cost` audit event emitted with cost breakdown.

**Assertion pseudocode:**
```
await run_consolidation(...)
cost_events = [e for e in mock_sink.events if e.type == "consolidation.cost"]
ASSERT len(cost_events) == 1
ASSERT cost_events[0].payload.total_cost > 0
```

## Edge Case Tests

### TS-96-E1: Zero active facts

**Requirement:** 96-REQ-1.E1
**Type:** unit
**Description:** Verify zero-count result when no active facts exist.

**Preconditions:**
- Empty `memory_facts` table.

**Input:**
- `run_consolidation(...)`.

**Expected:**
- All counts zero. No LLM calls made.

**Assertion pseudocode:**
```
result = await run_consolidation(conn, repo_root, specs, model)
ASSERT result.total_llm_cost == 0.0
ASSERT mock_llm.call_count == 0
```

### TS-96-E2: Missing entity graph tables

**Requirement:** 96-REQ-1.E2
**Type:** unit
**Description:** Verify graceful skip when entity graph tables don't exist.

**Preconditions:**
- DuckDB with migrations up to v7 (no v8). Entity graph tables absent.

**Input:**
- `run_consolidation(...)`.

**Expected:**
- entity_refresh is None. Warning logged. Remaining steps execute.

**Assertion pseudocode:**
```
result = await run_consolidation(conn, repo_root, specs, model)
ASSERT result.entity_refresh is None
ASSERT "entity graph" in caplog.text.lower()
```

### TS-96-E3: Invalid repo root

**Requirement:** 96-REQ-2.E1
**Type:** unit
**Description:** Verify entity steps skipped when repo root is invalid.

**Preconditions:**
- `repo_root` points to non-existent directory.

**Input:**
- `run_consolidation(conn, Path("/nonexistent"), specs, model)`.

**Expected:**
- entity_refresh and facts_linked are None/0. Warning logged.
- Git verification and subsequent steps still run.

**Assertion pseudocode:**
```
result = await run_consolidation(conn, bad_path, specs, model)
ASSERT result.entity_refresh is None
```

### TS-96-E4: Fact without entity links

**Requirement:** 96-REQ-3.E1
**Type:** unit
**Description:** Verify facts without entity links are skipped in git
verification.

**Preconditions:**
- Fact F with no `fact_entities` rows.

**Input:**
- `_verify_against_git(conn, repo_root, 0.5)`.

**Expected:**
- F not checked. `facts_checked == 0`.

**Assertion pseudocode:**
```
result = _verify_against_git(conn, repo_root, 0.5)
ASSERT result.facts_checked == 0
```

### TS-96-E5: Fact without commit_sha

**Requirement:** 96-REQ-3.E2
**Type:** unit
**Description:** Verify only file existence is checked when commit_sha is
null.

**Preconditions:**
- Fact F with commit_sha=None, linked to existing file.

**Input:**
- `_verify_against_git(conn, repo_root, 0.5)`.

**Expected:**
- File existence checked (file exists -> unchanged).
- No git diff subprocess call for this fact.

**Assertion pseudocode:**
```
result = _verify_against_git(conn, repo_root, 0.5)
ASSERT result.unchanged_count == 1
ASSERT mock_subprocess.call_count == 0
```

### TS-96-E6: Embedding failure in clustering

**Requirement:** 96-REQ-4.E1
**Type:** unit
**Description:** Verify facts with failed embeddings are excluded from
clustering.

**Preconditions:**
- Facts F1, F2 with embeddings. F3 without embedding.

**Input:**
- `_merge_related_facts(conn, model, 0.85, emb)`.

**Expected:**
- F3 excluded from clusters. F1, F2 processed normally.

**Assertion pseudocode:**
```
result = _merge_related_facts(conn, model, 0.85, emb)
# F3 not in any cluster
```

### TS-96-E7: LLM failure for merge cluster

**Requirement:** 96-REQ-4.E2
**Type:** unit
**Description:** Verify cluster is skipped when LLM call fails.

**Preconditions:**
- One cluster. Mock LLM raises exception.

**Input:**
- `_merge_related_facts(conn, model, 0.85, emb)`.

**Expected:**
- Cluster skipped. Warning logged. MergeResult counts are zero.

**Assertion pseudocode:**
```
result = _merge_related_facts(conn, model, 0.85, emb)
ASSERT result.consolidated_created == 0
ASSERT "cluster" in caplog.text.lower()
```

### TS-96-E8: Duplicate pattern prevention

**Requirement:** 96-REQ-5.E1
**Type:** unit
**Description:** Verify pattern groups already linked to a pattern fact are
skipped.

**Preconditions:**
- Facts F1, F2, F3 from 3 specs, already linked to pattern fact P via causal
  edges.

**Input:**
- `_promote_patterns(conn, model)`.

**Expected:**
- Group {F1, F2, F3} skipped. No new pattern created.

**Assertion pseudocode:**
```
result = _promote_patterns(conn, model)
ASSERT result.pattern_facts_created == 0
```

### TS-96-E9: LLM failure for chain evaluation

**Requirement:** 96-REQ-6.E1
**Type:** unit
**Description:** Verify all edges preserved when LLM fails.

**Preconditions:**
- Chain A->B->C. Mock LLM raises exception.

**Input:**
- `_prune_redundant_chains(conn, model)`.

**Expected:**
- All edges preserved. Warning logged.

**Assertion pseudocode:**
```
result = _prune_redundant_chains(conn, model)
ASSERT result.edges_removed == 0
ASSERT edge_exists(conn, A.id, B.id)
```

### TS-96-E10: Cost budget exceeded

**Requirement:** 96-REQ-7.E1
**Type:** unit
**Description:** Verify consolidation aborts when cost budget is exceeded.

**Preconditions:**
- Very low remaining budget. Mock LLM returns cost exceeding budget.

**Input:**
- `run_consolidation(...)`.

**Expected:**
- Partial result returned. Cost not exceeded beyond budget.

**Assertion pseudocode:**
```
result = await run_consolidation(...)
ASSERT result.total_llm_cost <= budget_limit
ASSERT len(result.errors) > 0
```

### TS-96-E11: No completed specs

**Requirement:** 96-REQ-7.E2
**Type:** unit
**Description:** Verify consolidation skipped when no specs completed.

**Preconditions:**
- `completed_spec_names()` returns empty set.

**Input:**
- Consolidation check in sync barrier.

**Expected:**
- `run_consolidation` not called.

**Assertion pseudocode:**
```
await run_sync_barrier_sequence(...)
ASSERT mock_consolidation.not_called
```

## Property Test Cases

### TS-96-P1: Step independence

**Property:** Property 1 from design.md
**Validates:** 96-REQ-1.2
**Type:** property
**Description:** Failing steps do not block subsequent steps.

**For any:** Subset of steps that raise exceptions (generated as bitmask).
**Invariant:** Steps after a failing step still execute; `errors` list
matches the failed step names.

**Assertion pseudocode:**
```
FOR ANY failure_mask IN st.integers(0, 63):
    mock steps to fail per bitmask
    result = await run_consolidation(...)
    FOR EACH step NOT in failure_mask:
        ASSERT step result is not None
    ASSERT len(result.errors) == popcount(failure_mask)
```

### TS-96-P2: Git verification accuracy

**Property:** Property 2 from design.md
**Validates:** 96-REQ-3.2, 96-REQ-3.3
**Type:** property
**Description:** Facts with all files deleted are superseded; facts with at
least one existing file are not.

**For any:** Set of facts with random file existence patterns.
**Invariant:** superseded_by is set iff all linked files are absent.

**Assertion pseudocode:**
```
FOR ANY (facts, file_existence_map) IN fact_file_strategy:
    _verify_against_git(conn, repo_root, 0.5)
    FOR EACH fact:
        IF all_files_deleted(fact, file_existence_map):
            ASSERT fact.superseded_by == SENTINEL
        ELSE:
            ASSERT fact.superseded_by is None
```

### TS-96-P3: Merge idempotency

**Property:** Property 3 from design.md
**Validates:** 96-REQ-4.1, 96-REQ-4.3
**Type:** property
**Description:** Running merge twice does not duplicate consolidated facts.

**For any:** Set of facts with clusters.
**Invariant:** After two merge passes, consolidated fact count equals count
after first pass.

**Assertion pseudocode:**
```
FOR ANY facts IN fact_list_strategy:
    _merge_related_facts(conn, model, 0.85, emb)
    count_after_first = count_active_facts(conn)
    _merge_related_facts(conn, model, 0.85, emb)
    count_after_second = count_active_facts(conn)
    ASSERT count_after_first == count_after_second
```

### TS-96-P4: Pattern promotion threshold

**Property:** Property 4 from design.md
**Validates:** 96-REQ-5.1, 96-REQ-5.3
**Type:** property
**Description:** Pattern facts are only created from facts spanning 3+ specs.

**For any:** Set of facts with random spec names.
**Invariant:** Every created pattern fact has causal edges from facts in 3+
distinct spec_name values.

**Assertion pseudocode:**
```
FOR ANY facts IN fact_list_strategy:
    _promote_patterns(conn, model)
    FOR EACH new pattern fact:
        source_specs = get_source_spec_names(conn, pattern.id)
        ASSERT len(source_specs) >= 3
```

### TS-96-P5: Causal chain preservation

**Property:** Property 5 from design.md
**Validates:** 96-REQ-6.3
**Type:** property
**Description:** After pruning, direct A->C edge exists; A->B and B->C do not.

**For any:** Redundant chain (A, B, C) where LLM says B not meaningful.
**Invariant:** edge(A,C) exists; edge(A,B) and edge(B,C) do not.

**Assertion pseudocode:**
```
FOR ANY (A, B, C) IN chain_strategy:
    _prune_redundant_chains(conn, model)
    ASSERT edge_exists(conn, A.id, C.id)
    ASSERT not edge_exists(conn, A.id, B.id)
    ASSERT not edge_exists(conn, B.id, C.id)
```

### TS-96-P6: Confidence decay bounds

**Property:** Property 6 from design.md
**Validates:** 96-REQ-3.3
**Type:** property
**Description:** Halved confidence is always positive and less than original.

**For any:** Fact with confidence in (0.0, 1.0].
**Invariant:** After halving, 0 < new_confidence < original_confidence.

**Assertion pseudocode:**
```
FOR ANY confidence IN st.floats(min_value=0.01, max_value=1.0):
    halved = confidence / 2
    ASSERT halved > 0
    ASSERT halved < confidence
```

## Integration Smoke Tests

### TS-96-SMOKE-1: Full consolidation at sync barrier

**Execution Path:** Path 1 from design.md
**Description:** Verify that the sync barrier triggers a full consolidation
pipeline when a spec completes.

**Setup:**
- Real DuckDB with migrations v1-v8 applied.
- Entity graph populated with a small Python package (2 files, 1 class).
- 5 active facts across 2 specs, some with entity links, some without.
- Causal chain A->B->C with A->C.
- Mock subprocess for git diff.
- Mock LLM to return merge/pattern/prune decisions.
- Mock `completed_spec_names()` to return {"spec_a"}.

**Trigger:** `run_sync_barrier_sequence(...)`

**Expected side effects:**
- `analyze_codebase` called.
- `link_facts` called for unlinked facts.
- Git verification checks linked facts.
- LLM called for merge classification, pattern confirmation, chain evaluation.
- `ConsolidationResult` logged with non-zero counts.
- `consolidation.complete` audit event emitted.

**Must NOT satisfy with:** Mocked consolidation pipeline, mocked DuckDB
connection, mocked entity graph operations.

**Assertion pseudocode:**
```
await run_sync_barrier_sequence(...)
ASSERT mock_analyze_codebase.called
ASSERT mock_link_facts.called
ASSERT consolidation_result.verification.facts_checked > 0
ASSERT mock_llm.call_count >= 1
```

### TS-96-SMOKE-2: End-of-run consolidation for remaining specs

**Execution Path:** Path 2 from design.md
**Description:** Verify end-of-run triggers consolidation for specs not
consolidated during barriers.

**Setup:**
- Real DuckDB with facts.
- `_consolidated_specs = {"spec_a"}`.
- `completed_spec_names() = {"spec_a", "spec_b"}`.
- Mock LLM and subprocess.

**Trigger:** End-of-run cleanup block in engine.

**Expected side effects:**
- `run_consolidation` called with completed_specs={"spec_b"}.
- Full pipeline executes for spec_b.

**Must NOT satisfy with:** Mocked consolidation pipeline.

**Assertion pseudocode:**
```
await engine._run_final_consolidation()
ASSERT mock_run_consolidation.called
ASSERT mock_run_consolidation.call_args.completed_specs == {"spec_b"}
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 96-REQ-1.1 | TS-96-1 | unit |
| 96-REQ-1.2 | TS-96-2 | unit |
| 96-REQ-1.3 | TS-96-3 | unit |
| 96-REQ-1.E1 | TS-96-E1 | unit |
| 96-REQ-1.E2 | TS-96-E2 | unit |
| 96-REQ-2.1 | TS-96-4 | unit |
| 96-REQ-2.2 | TS-96-5 | unit |
| 96-REQ-2.3 | TS-96-6 | unit |
| 96-REQ-2.E1 | TS-96-E3 | unit |
| 96-REQ-3.1 | TS-96-7 | unit |
| 96-REQ-3.2 | TS-96-8 | unit |
| 96-REQ-3.3 | TS-96-9 | unit |
| 96-REQ-3.4 | TS-96-10 | unit |
| 96-REQ-3.E1 | TS-96-E4 | unit |
| 96-REQ-3.E2 | TS-96-E5 | unit |
| 96-REQ-4.1 | TS-96-11 | unit |
| 96-REQ-4.2 | TS-96-12 | unit |
| 96-REQ-4.3 | TS-96-13 | unit |
| 96-REQ-4.4 | TS-96-14 | unit |
| 96-REQ-4.E1 | TS-96-E6 | unit |
| 96-REQ-4.E2 | TS-96-E7 | unit |
| 96-REQ-5.1 | TS-96-15 | unit |
| 96-REQ-5.2 | TS-96-16 | unit |
| 96-REQ-5.3 | TS-96-17 | unit |
| 96-REQ-5.E1 | TS-96-E8 | unit |
| 96-REQ-6.1 | TS-96-18 | unit |
| 96-REQ-6.2 | TS-96-19 | unit |
| 96-REQ-6.3 | TS-96-20 | unit |
| 96-REQ-6.E1 | TS-96-E9 | unit |
| 96-REQ-7.1 | TS-96-21 | integration |
| 96-REQ-7.2 | TS-96-22 | integration |
| 96-REQ-7.3 | TS-96-23 | unit |
| 96-REQ-7.4 | TS-96-24 | unit |
| 96-REQ-7.E1 | TS-96-E10 | unit |
| 96-REQ-7.E2 | TS-96-E11 | unit |
| Property 1 | TS-96-P1 | property |
| Property 2 | TS-96-P2 | property |
| Property 3 | TS-96-P3 | property |
| Property 4 | TS-96-P4 | property |
| Property 5 | TS-96-P5 | property |
| Property 6 | TS-96-P6 | property |
| Path 1 | TS-96-SMOKE-1 | integration |
| Path 2 | TS-96-SMOKE-2 | integration |
