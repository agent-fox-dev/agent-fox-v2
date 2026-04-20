# Test Specification: Adaptive Retrieval with Multi-Signal Fusion

## Overview

Tests validate the four individual signals, RRF fusion with adaptive weights,
intent profile derivation, context assembly with causal ordering and token
budgeting, session lifecycle integration, and legacy removal. Each acceptance
criterion maps to at least one test case; each correctness property maps to a
property-based test.

## Test Cases

### TS-104-1: Keyword signal returns ranked facts

**Requirement:** 104-REQ-1.2
**Type:** unit
**Description:** Verify keyword signal queries memory_facts and returns
ranked results.

**Preconditions:**
- DuckDB with 5 facts: 2 matching spec "myspec", 3 with overlapping keywords.

**Input:**
- `spec_name="myspec"`, `keywords=["auth", "session"]`

**Expected:**
- Returns list of ScoredFact with spec-matching and keyword-matching facts.
- Facts are ranked by keyword match count + recency.

**Assertion pseudocode:**
```
results = _keyword_signal("myspec", ["auth", "session"], conn, 0.5)
ASSERT len(results) >= 2
ASSERT results[0].spec_name == "myspec" OR keyword_overlap > 0
ASSERT all(r.score > 0 for r in results)
```

### TS-104-2: Vector signal returns similarity-ranked facts

**Requirement:** 104-REQ-1.3
**Type:** unit
**Description:** Verify vector signal embeds task description and returns
cosine-ranked results.

**Preconditions:**
- DuckDB with 3 facts with embeddings in memory_embeddings.
- Mock EmbeddingGenerator that returns a fixed embedding.

**Input:**
- `task_description="implement auth middleware"`

**Expected:**
- Returns list of ScoredFact ordered by cosine similarity.

**Assertion pseudocode:**
```
results = _vector_signal("implement auth middleware", conn, embedder)
ASSERT len(results) >= 1
ASSERT results[0].score >= results[-1].score
```

### TS-104-3: Entity signal returns BFS-traversed facts

**Requirement:** 104-REQ-1.4
**Type:** unit
**Description:** Verify entity signal calls find_related_facts and returns
entity-linked facts.

**Preconditions:**
- DuckDB with entity_graph containing file entities and fact_entities links.
- 2 facts linked to entity for "agent_fox/knowledge/search.py".

**Input:**
- `touched_files=["agent_fox/knowledge/search.py"]`

**Expected:**
- Returns list containing the 2 linked facts.

**Assertion pseudocode:**
```
results = _entity_signal(["agent_fox/knowledge/search.py"], conn)
ASSERT len(results) == 2
ASSERT all(r.fact_id in expected_ids for r in results)
```

### TS-104-4: Causal signal returns depth-ordered facts

**Requirement:** 104-REQ-1.5
**Type:** unit
**Description:** Verify causal signal traverses fact_causes and returns
proximity-ordered facts.

**Preconditions:**
- DuckDB with fact A → fact B → fact C causal chain, all in spec "myspec".

**Input:**
- `spec_name="myspec"`

**Expected:**
- Returns facts ordered by causal proximity (depth ascending).

**Assertion pseudocode:**
```
results = _causal_signal("myspec", conn)
ASSERT len(results) >= 2
# B should appear before C (closer to A)
```

### TS-104-5: Empty signal gracefully excluded

**Requirement:** 104-REQ-1.E1
**Type:** unit
**Description:** Verify RRF works when one or more signals return empty lists.

**Preconditions:**
- Two signals with results, two empty.

**Input:**
- `signal_lists={"keyword": [fact_a, fact_b], "vector": [], "entity": [fact_a], "causal": []}`

**Expected:**
- RRF produces results from keyword and entity signals only.

**Assertion pseudocode:**
```
result = weighted_rrf_fusion(signal_lists, default_profile, k=60)
ASSERT len(result) == 2  # fact_a, fact_b
ASSERT result[0].fact_id == "a"  # appears in 2 signals, higher score
```

### TS-104-6: All signals empty returns empty context

**Requirement:** 104-REQ-1.E2
**Type:** unit
**Description:** Verify empty result when all signals produce nothing.

**Preconditions:**
- All four signals return empty lists.

**Input:**
- `signal_lists={"keyword": [], "vector": [], "entity": [], "causal": []}`

**Expected:**
- Fusion returns empty list. Context string is empty.

**Assertion pseudocode:**
```
result = weighted_rrf_fusion(signal_lists, default_profile, k=60)
ASSERT result == []
```

### TS-104-7: Vector signal failure logged and skipped

**Requirement:** 104-REQ-1.E3
**Type:** unit
**Description:** Verify vector signal failure doesn't crash the retriever.

**Preconditions:**
- Mock embedder that raises RuntimeError.
- Other signals configured to return results.

**Input:**
- Call `retrieve()` with failing embedder.

**Expected:**
- No exception raised.
- Warning logged.
- Results from other 3 signals still present.

**Assertion pseudocode:**
```
retriever = AdaptiveRetriever(conn, config, embedder=failing_embedder)
result = retriever.retrieve(...)  # must not raise
ASSERT "vector" NOT IN result.signal_counts OR result.signal_counts["vector"] == 0
ASSERT result.anchor_count > 0  # other signals contributed
```

### TS-104-8: RRF formula produces correct scores

**Requirement:** 104-REQ-2.1
**Type:** unit
**Description:** Verify weighted RRF formula computation.

**Preconditions:**
- Two signals: keyword=[A(rank1), B(rank2)], entity=[B(rank1), C(rank2)].
- Profile: keyword_weight=1.0, entity_weight=2.0.

**Input:**
- `k=60`

**Expected:**
- A: score = 1.0/(60+1) = 0.01639
- B: score = 1.0/(60+2) + 2.0/(60+1) = 0.01613 + 0.03279 = 0.04892
- C: score = 2.0/(60+2) = 0.03226
- Order: B > C > A

**Assertion pseudocode:**
```
result = weighted_rrf_fusion(lists, profile, k=60)
ASSERT result[0].fact_id == "B"
ASSERT result[1].fact_id == "C"
ASSERT result[2].fact_id == "A"
ASSERT abs(result[0].score - 0.04892) < 0.001
```

### TS-104-9: RRF deduplication

**Requirement:** 104-REQ-2.3
**Type:** unit
**Description:** Verify same fact appearing in multiple signals produces one entry.

**Preconditions:**
- Fact X appears in keyword (rank 1) and vector (rank 3).

**Input:**
- `signal_lists` with X in two lists.

**Expected:**
- Output contains exactly one entry for X.
- Score aggregates both signals.

**Assertion pseudocode:**
```
result = weighted_rrf_fusion(lists, default_profile, k=60)
x_entries = [r for r in result if r.fact_id == "X"]
ASSERT len(x_entries) == 1
ASSERT x_entries[0].score > 1.0 / (60 + 1)  # more than single-signal
```

### TS-104-10: Intent profile for coder/retry

**Requirement:** 104-REQ-3.1, 104-REQ-3.3
**Type:** unit
**Description:** Verify coder retry session gets high causal weight.

**Preconditions:** None.

**Input:**
- `archetype="coder"`, `node_status="retry"`

**Expected:**
- `causal_weight == 2.0`, higher than other weights.

**Assertion pseudocode:**
```
profile = derive_intent_profile("coder", "retry")
ASSERT profile.causal_weight == 2.0
ASSERT profile.keyword_weight == 0.8
ASSERT profile.entity_weight == 1.0
ASSERT profile.vector_weight == 0.6
```

### TS-104-11: Unknown archetype falls back to default

**Requirement:** 104-REQ-3.E1
**Type:** unit
**Description:** Verify unknown archetype produces balanced weights.

**Preconditions:** None.

**Input:**
- `archetype="unknown_thing"`, `node_status="fresh"`

**Expected:**
- All weights equal 1.0.

**Assertion pseudocode:**
```
profile = derive_intent_profile("unknown_thing", "fresh")
ASSERT profile.keyword_weight == 1.0
ASSERT profile.vector_weight == 1.0
ASSERT profile.entity_weight == 1.0
ASSERT profile.causal_weight == 1.0
```

### TS-104-12: Context ordered by causal precedence

**Requirement:** 104-REQ-4.1
**Type:** unit
**Description:** Verify causal predecessors appear before effects in output.

**Preconditions:**
- DuckDB with facts A → B in fact_causes.
- Both facts in anchor set.

**Input:**
- `anchors=[B(score=0.9), A(score=0.5)]`

**Expected:**
- In formatted output, A's section appears before B's section despite lower score.

**Assertion pseudocode:**
```
context = assemble_ranked_context(anchors, conn, config)
pos_a = context.index("A content")
pos_b = context.index("B content")
ASSERT pos_a < pos_b
```

### TS-104-13: Provenance metadata in output

**Requirement:** 104-REQ-4.2
**Type:** unit
**Description:** Verify each fact in output includes spec name, confidence,
and salience tier.

**Preconditions:**
- Anchor set with 1 fact: spec="03_auth", confidence=0.9, score=top 20%.

**Input:**
- Single fact in anchor set.

**Expected:**
- Output contains "spec: 03_auth", "confidence: 0.9", "[high]".

**Assertion pseudocode:**
```
context = assemble_ranked_context([fact], conn, config)
ASSERT "spec: 03_auth" IN context
ASSERT "confidence: 0.9" IN context
ASSERT "[high]" IN context
```

### TS-104-14: Token budget respected

**Requirement:** 104-REQ-4.3
**Type:** unit
**Description:** Verify output does not exceed token budget.

**Preconditions:**
- 50 facts with large content (1000 chars each).
- `token_budget=5000`

**Input:**
- `config.token_budget = 5000`

**Expected:**
- Output length ≤ 5000 characters.
- Low-salience facts omitted.

**Assertion pseudocode:**
```
context = assemble_ranked_context(large_anchors, conn, config)
ASSERT len(context) <= 5000
```

### TS-104-15: Under-budget renders all facts fully

**Requirement:** 104-REQ-4.E1
**Type:** unit
**Description:** Verify all facts rendered in full when budget allows.

**Preconditions:**
- 3 small facts (100 chars each).
- `token_budget=30000`

**Input:**
- 3 facts, ample budget.

**Expected:**
- All 3 facts rendered in full (no "omitted" markers).

**Assertion pseudocode:**
```
context = assemble_ranked_context(small_anchors, conn, config)
ASSERT "omitted" NOT IN context
ASSERT all(fact.content IN context FOR fact IN small_anchors)
```

### TS-104-16: Config defaults used when section absent

**Requirement:** 104-REQ-5.E1
**Type:** unit
**Description:** Verify default RetrievalConfig values when config is absent.

**Preconditions:**
- KnowledgeConfig without retrieval section.

**Input:**
- Access `config.knowledge.retrieval`.

**Expected:**
- `rrf_k=60`, `max_facts=50`, `token_budget=30000`.

**Assertion pseudocode:**
```
config = KnowledgeConfig()
ASSERT config.retrieval.rrf_k == 60
ASSERT config.retrieval.max_facts == 50
ASSERT config.retrieval.token_budget == 30000
```

### TS-104-17: select_relevant_facts removed

**Requirement:** 104-REQ-6.1
**Type:** unit
**Description:** Verify the old function no longer exists.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Attempt to import `select_relevant_facts` from `agent_fox.knowledge.filtering`.

**Expected:**
- ImportError raised.

**Assertion pseudocode:**
```
TRY:
    from agent_fox.knowledge.filtering import select_relevant_facts
    FAIL("should not be importable")
EXCEPT ImportError:
    PASS
```

### TS-104-18: RankedFactCache removed

**Requirement:** 104-REQ-6.4
**Type:** unit
**Description:** Verify precomputed cache classes no longer exist.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Attempt to import `RankedFactCache` from `agent_fox.engine.fact_cache`.

**Expected:**
- ImportError raised.

**Assertion pseudocode:**
```
TRY:
    from agent_fox.engine.fact_cache import RankedFactCache
    FAIL("should not be importable")
EXCEPT ImportError:
    PASS
```

## Property Test Cases

### TS-104-P1: RRF score monotonicity

**Property:** Property 1 from design.md
**Validates:** 104-REQ-2.1, 104-REQ-2.E1
**Type:** property
**Description:** Adding a fact to more signals can only increase its score.

**For any:** Fact d, two signal sets S1 ⊂ S2 where d appears in both,
arbitrary IntentProfile, k in [1, 200].

**Invariant:** `score(d, S2) >= score(d, S1)`

**Assertion pseudocode:**
```
FOR ANY d, S1, S2 WHERE S1 ⊂ S2:
    score1 = weighted_rrf_fusion(S1, profile, k)[d].score
    score2 = weighted_rrf_fusion(S2, profile, k)[d].score
    ASSERT score2 >= score1
```

### TS-104-P2: RRF deduplication invariant

**Property:** Property 2 from design.md
**Validates:** 104-REQ-2.3
**Type:** property
**Description:** Every fact ID appears at most once in fusion output.

**For any:** 1-4 signal lists with 0-50 facts each, arbitrary overlap.

**Invariant:** No duplicate fact IDs in output.

**Assertion pseudocode:**
```
FOR ANY signal_lists IN random_signal_lists():
    result = weighted_rrf_fusion(signal_lists, profile, k)
    ids = [r.fact_id for r in result]
    ASSERT len(ids) == len(set(ids))
```

### TS-104-P3: Weight application correctness

**Property:** Property 3 from design.md
**Validates:** 104-REQ-2.1, 104-REQ-3.2
**Type:** property
**Description:** Single-signal fact score equals weight / (k + rank).

**For any:** Signal name, weight in [0.1, 10.0], rank in [1, 100], k in [1, 200].

**Invariant:** Score equals weight / (k + rank) within floating-point tolerance.

**Assertion pseudocode:**
```
FOR ANY weight, rank, k:
    profile = IntentProfile(**{signal + "_weight": weight})
    lists = {signal: [fact_at_rank(rank)]}
    result = weighted_rrf_fusion(lists, profile, k)
    ASSERT abs(result[0].score - weight / (k + rank)) < 1e-10
```

### TS-104-P4: Graceful signal degradation

**Property:** Property 4 from design.md
**Validates:** 104-REQ-1.E1, 104-REQ-1.E2
**Type:** property
**Description:** Fusion works with any combination of empty/non-empty signals.

**For any:** 4 signal lists where 0-4 are empty, the rest contain 1-20 facts.

**Invariant:** No exception raised. Output length equals number of unique
facts across non-empty signals.

**Assertion pseudocode:**
```
FOR ANY signal_lists IN random_signal_lists_with_empties():
    result = weighted_rrf_fusion(signal_lists, profile, k)
    expected_count = len(set(f.id for l in signal_lists.values() for f in l))
    ASSERT len(result) == expected_count
```

### TS-104-P5: Causal ordering consistency

**Property:** Property 5 from design.md
**Validates:** 104-REQ-4.1
**Type:** property
**Description:** Causal predecessors always appear before effects.

**For any:** DAG of 2-10 facts with causal edges, arbitrary scores.

**Invariant:** For every edge A→B in causal graph, position(A) < position(B)
in output.

**Assertion pseudocode:**
```
FOR ANY causal_dag IN random_dags():
    context = assemble_ranked_context(anchors, conn_with_dag, config)
    FOR (a, b) IN causal_dag.edges:
        ASSERT context.index(a.content) < context.index(b.content)
```

### TS-104-P6: Token budget compliance

**Property:** Property 6 from design.md
**Validates:** 104-REQ-4.3
**Type:** property
**Description:** Output never exceeds configured token budget.

**For any:** 1-100 facts with content 10-5000 chars, token_budget in [500, 50000].

**Invariant:** `len(output) <= token_budget`

**Assertion pseudocode:**
```
FOR ANY anchors, budget IN random_anchors_and_budgets():
    config = RetrievalConfig(token_budget=budget)
    context = assemble_ranked_context(anchors, conn, config)
    ASSERT len(context) <= budget
```

### TS-104-P7: Default fallback profile

**Property:** Property 7 from design.md
**Validates:** 104-REQ-3.E1
**Type:** property
**Description:** Unknown archetypes produce all-1.0 profiles.

**For any:** Archetype string not in known set, any node_status string.

**Invariant:** All four weights equal 1.0.

**Assertion pseudocode:**
```
FOR ANY archetype IN text(), node_status IN text():
    IF archetype NOT IN {"coder", "auditor", "reviewer", "verifier"}:
        profile = derive_intent_profile(archetype, node_status)
        ASSERT profile == IntentProfile(1.0, 1.0, 1.0, 1.0)
```

## Edge Case Tests

### TS-104-E1: Empty signal excluded from RRF

**Requirement:** 104-REQ-1.E1
**Type:** unit
**Description:** Covered by TS-104-5.

### TS-104-E2: All signals empty

**Requirement:** 104-REQ-1.E2
**Type:** unit
**Description:** Covered by TS-104-6.

### TS-104-E3: Vector signal failure

**Requirement:** 104-REQ-1.E3
**Type:** unit
**Description:** Covered by TS-104-7.

### TS-104-E4: Single-signal fact scoring

**Requirement:** 104-REQ-2.E1
**Type:** unit
**Description:** Verify fact in one signal gets single-signal score (no penalty).

**Preconditions:**
- Fact X in keyword signal only (rank 1). Profile keyword_weight=1.5.

**Input:**
- `k=60`

**Expected:**
- X score = 1.5 / (60+1) = 0.02459

**Assertion pseudocode:**
```
result = weighted_rrf_fusion({"keyword": [X]}, profile, k=60)
ASSERT abs(result[0].score - 1.5/61) < 1e-10
```

### TS-104-E5: Unknown archetype fallback

**Requirement:** 104-REQ-3.E1
**Type:** unit
**Description:** Covered by TS-104-11.

### TS-104-E6: Under-budget full rendering

**Requirement:** 104-REQ-4.E1
**Type:** unit
**Description:** Covered by TS-104-15.

### TS-104-E7: Missing config section

**Requirement:** 104-REQ-5.E1
**Type:** unit
**Description:** Covered by TS-104-16.

### TS-104-E8: Legacy import cleanup

**Requirement:** 104-REQ-6.E1
**Type:** unit
**Description:** Verify no remaining imports of removed functions.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Search all `.py` files for imports of `select_relevant_facts`,
  `enhance_with_causal`, `_retrieve_cross_spec_facts`,
  `RankedFactCache`, `precompute_fact_rankings`.

**Expected:**
- Zero matches (excluding test files that specifically test removal).

**Assertion pseudocode:**
```
matches = grep("select_relevant_facts|enhance_with_causal|RankedFactCache|precompute_fact_rankings",
               "agent_fox/**/*.py")
ASSERT len(matches) == 0
```

### TS-104-19: memory.jsonl export/import functions removed

**Requirement:** 104-REQ-7.1
**Type:** unit
**Description:** Verify JSONL export/import functions no longer exist.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Attempt to import `export_facts_to_jsonl` and `load_facts_from_jsonl`
  from `agent_fox.knowledge.store`.

**Expected:**
- ImportError or AttributeError raised for both.

**Assertion pseudocode:**
```
FOR name IN ["export_facts_to_jsonl", "load_facts_from_jsonl"]:
    TRY:
        getattr(importlib.import_module("agent_fox.knowledge.store"), name)
        FAIL("should not be importable")
    EXCEPT AttributeError:
        PASS
```

### TS-104-20: read_all_facts DuckDB-only (no JSONL fallback)

**Requirement:** 104-REQ-7.2, 104-REQ-7.E1
**Type:** unit
**Description:** Verify read_all_facts returns empty list when DuckDB is
unavailable, with no JSONL fallback.

**Preconditions:**
- No DuckDB connection available.
- A `memory.jsonl` file exists on disk with facts (to prove it is NOT read).

**Input:**
- Call `read_all_facts(conn=None)`.

**Expected:**
- Returns empty list.
- The JSONL file is NOT read.

**Assertion pseudocode:**
```
# Create a JSONL file with facts to prove it's ignored
write_jsonl(path, [some_fact])
result = read_all_facts(conn=None)
ASSERT result == []
```

### TS-104-21: MEMORY_PATH constant removed

**Requirement:** 104-REQ-7.1
**Type:** unit
**Description:** Verify MEMORY_PATH is no longer defined in paths module.

**Preconditions:**
- Codebase at HEAD after implementation.

**Input:**
- Attempt to import `MEMORY_PATH` from `agent_fox.core.paths`.

**Expected:**
- ImportError or AttributeError raised.

**Assertion pseudocode:**
```
TRY:
    from agent_fox.core.paths import MEMORY_PATH
    FAIL("should not be importable")
EXCEPT (ImportError, AttributeError):
    PASS
```

## Integration Smoke Tests

### TS-104-SMOKE-1: Full retrieval pipeline end-to-end

**Execution Path:** Path 1 from design.md
**Description:** Verify the full retrieval pipeline from NodeSessionRunner
through to formatted context string, using real AdaptiveRetriever with
in-memory DuckDB.

**Setup:**
- In-memory DuckDB with memory_facts (5 facts), memory_embeddings (3),
  entity_graph + fact_entities (2 linked), fact_causes (1 chain A→B).
- Mock EmbeddingGenerator returning fixed embeddings.
- Real AdaptiveRetriever, real weighted_rrf_fusion, real assemble_ranked_context.

**Trigger:** Call `retriever.retrieve(spec_name="myspec", archetype="coder",
node_status="fresh", touched_files=["search.py"], task_description="fix search")`.

**Expected side effects:**
- `RetrievalResult.context` is a non-empty string.
- `signal_counts` has entries for all signals that found results.
- `intent_profile` matches coder/fresh weights.
- Context contains at least one fact with provenance metadata.
- If A→B causal pair both present, A appears before B.

**Must NOT satisfy with:**
- Mocking `weighted_rrf_fusion` (must be real).
- Mocking `assemble_ranked_context` (must be real).
- Mocking individual signal functions (must be real).

**Assertion pseudocode:**
```
retriever = AdaptiveRetriever(conn, config, embedder)
result = retriever.retrieve(
    spec_name="myspec", archetype="coder", node_status="fresh",
    touched_files=["search.py"], task_description="fix search")

ASSERT len(result.context) > 0
ASSERT result.intent_profile.entity_weight == 1.5  # coder/fresh
ASSERT result.anchor_count >= 1
ASSERT "spec:" IN result.context
```

### TS-104-SMOKE-2: Legacy retrieval chain removed

**Execution Path:** Path 2 from design.md
**Description:** Verify none of the removed functions are importable.

**Setup:**
- Codebase at HEAD after implementation.

**Trigger:** Attempt imports of all removed symbols.

**Expected side effects:**
- All imports raise ImportError.

**Must NOT satisfy with:**
- The functions still existing but being unused.

**Assertion pseudocode:**
```
FOR name IN ["select_relevant_facts", "RankedFactCache",
             "precompute_fact_rankings", "get_cached_facts"]:
    TRY:
        importlib.import_module(...).getattr(name)
        FAIL
    EXCEPT (ImportError, AttributeError):
        PASS
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 104-REQ-1.1 | TS-104-SMOKE-1 | integration |
| 104-REQ-1.2 | TS-104-1 | unit |
| 104-REQ-1.3 | TS-104-2 | unit |
| 104-REQ-1.4 | TS-104-3 | unit |
| 104-REQ-1.5 | TS-104-4 | unit |
| 104-REQ-1.E1 | TS-104-5 | unit |
| 104-REQ-1.E2 | TS-104-6 | unit |
| 104-REQ-1.E3 | TS-104-7 | unit |
| 104-REQ-2.1 | TS-104-8 | unit |
| 104-REQ-2.2 | TS-104-8 | unit |
| 104-REQ-2.3 | TS-104-9 | unit |
| 104-REQ-2.E1 | TS-104-E4 | unit |
| 104-REQ-3.1 | TS-104-10 | unit |
| 104-REQ-3.2 | TS-104-8 | unit |
| 104-REQ-3.3 | TS-104-10 | unit |
| 104-REQ-3.E1 | TS-104-11 | unit |
| 104-REQ-4.1 | TS-104-12 | unit |
| 104-REQ-4.2 | TS-104-13 | unit |
| 104-REQ-4.3 | TS-104-14 | unit |
| 104-REQ-4.E1 | TS-104-15 | unit |
| 104-REQ-5.1 | TS-104-SMOKE-1 | integration |
| 104-REQ-5.2 | TS-104-SMOKE-1 | integration |
| 104-REQ-5.3 | TS-104-16 | unit |
| 104-REQ-5.E1 | TS-104-16 | unit |
| 104-REQ-6.1 | TS-104-17 | unit |
| 104-REQ-6.2 | TS-104-SMOKE-2 | integration |
| 104-REQ-6.3 | TS-104-SMOKE-2 | integration |
| 104-REQ-6.4 | TS-104-18 | unit |
| 104-REQ-6.E1 | TS-104-E8 | unit |
| Property 1 | TS-104-P1 | property |
| Property 2 | TS-104-P2 | property |
| Property 3 | TS-104-P3 | property |
| Property 4 | TS-104-P4 | property |
| Property 5 | TS-104-P5 | property |
| Property 6 | TS-104-P6 | property |
| 104-REQ-7.1 | TS-104-19, TS-104-21 | unit |
| 104-REQ-7.2 | TS-104-20 | unit |
| 104-REQ-7.3 | TS-104-E8 | unit |
| 104-REQ-7.4 | TS-104-21 | unit |
| 104-REQ-7.E1 | TS-104-20 | unit |
| Property 7 | TS-104-P7 | property |
