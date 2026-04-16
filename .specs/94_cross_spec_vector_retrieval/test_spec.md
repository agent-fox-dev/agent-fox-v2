# Test Specification: Cross-Spec Vector Retrieval

## Overview

Tests verify that cross-spec vector retrieval correctly extracts subtask
descriptions, embeds them, searches across all facts, merges results with
spec-specific facts (deduplicating by ID), and degrades gracefully on
failure. Unit tests cover individual functions, property tests verify
invariants across generated inputs, and integration smoke tests verify the
full pipeline end-to-end.

## Test Cases

### TS-94-1: Extract subtask descriptions from task group

**Requirement:** 94-REQ-1.1
**Type:** unit
**Description:** Verify that `extract_subtask_descriptions` returns the first
non-metadata bullet from each subtask in a task group.

**Preconditions:**
- A `tasks.md` file exists with a task group containing subtasks with bullet
  points.

**Input:**
- `spec_dir`: directory containing a `tasks.md` with task group 2 having
  subtasks 2.1 ("Add config field" with bullet "Add `push_fix_branch` field")
  and 2.2 ("Update naming" with bullet "Modify branch naming function").
- `task_group`: 2

**Expected:**
- Returns `["Add `push_fix_branch` field", "Modify branch naming function"]`

**Assertion pseudocode:**
```
result = extract_subtask_descriptions(spec_dir, 2)
ASSERT result == ["Add `push_fix_branch` field", "Modify branch naming function"]
```

### TS-94-2: Skip metadata bullets during extraction

**Requirement:** 94-REQ-1.2
**Type:** unit
**Description:** Verify that bullets starting with `_` are skipped and the
next non-metadata bullet is returned.

**Preconditions:**
- A `tasks.md` file with a subtask whose first bullet is
  `_Requirements: 93-REQ-1.1_` and second bullet is
  "Create the config dataclass".

**Input:**
- `spec_dir`: directory with the above `tasks.md`
- `task_group`: matching group number

**Expected:**
- Returns `["Create the config dataclass"]`

**Assertion pseudocode:**
```
result = extract_subtask_descriptions(spec_dir, task_group)
ASSERT result == ["Create the config dataclass"]
```

### TS-94-3: Concatenate descriptions and embed

**Requirement:** 94-REQ-2.1
**Type:** unit
**Description:** Verify that extracted descriptions are concatenated with
newlines and passed to `embed_text`.

**Preconditions:**
- Mock `EmbeddingGenerator` with `embed_text` returning a fixed embedding.
- Mock `VectorSearch` returning empty results.

**Input:**
- Descriptions: `["Add config field", "Update branch naming"]`

**Expected:**
- `embed_text` is called with `"Add config field\nUpdate branch naming"`
- The embedding vector is passed to `VectorSearch.search`

**Assertion pseudocode:**
```
embedder = MockEmbeddingGenerator()
embedder.embed_text.return_value = [0.1, 0.2, ...]
result = retrieve_cross_spec_facts(knowledge_db, config, spec_dir, 2, embedder, [])
ASSERT embedder.embed_text.called_with("Add config field\nUpdate branch naming")
```

### TS-94-4: Vector search uses configured top_k

**Requirement:** 94-REQ-2.2
**Type:** unit
**Description:** Verify that `VectorSearch.search` is called with the
configured `cross_spec_top_k` value.

**Preconditions:**
- `KnowledgeConfig` with `cross_spec_top_k = 10`.
- Mock `VectorSearch`.

**Input:**
- An embedding vector from the mock embedder.

**Expected:**
- `VectorSearch.search` called with `top_k=10` and
  `exclude_superseded=True`.

**Assertion pseudocode:**
```
config.knowledge.cross_spec_top_k = 10
# ... trigger retrieval
ASSERT vector_search.search.called_with(embedding, top_k=10, exclude_superseded=True)
```

### TS-94-5: Merge cross-spec facts with spec-specific facts

**Requirement:** 94-REQ-3.1
**Type:** unit
**Description:** Verify that cross-spec SearchResults are converted to Fact
objects and merged with spec-specific facts, deduplicating by ID.

**Preconditions:**
- Spec-specific facts: `[Fact(id="aaa"), Fact(id="bbb")]`
- Cross-spec results: `[SearchResult(fact_id="bbb"), SearchResult(fact_id="ccc")]`

**Input:**
- The above fact lists.

**Expected:**
- Merged result: 3 facts with IDs `["aaa", "bbb", "ccc"]`
- `bbb` appears only once (spec-specific version kept)

**Assertion pseudocode:**
```
merged = merge_cross_spec_facts(spec_facts, cross_spec_results)
ASSERT len(merged) == 3
ASSERT [f.id for f in merged] == ["aaa", "bbb", "ccc"]
```

### TS-94-6: Merge happens before causal enhancement

**Requirement:** 94-REQ-3.2
**Type:** unit
**Description:** Verify that cross-spec facts are present in the fact list
when `enhance_with_causal` is called.

**Preconditions:**
- Mock `_enhance_with_causal` to capture its input.
- Spec-specific facts: `[Fact(id="aaa")]`
- Cross-spec results: `[SearchResult(fact_id="ccc")]`

**Input:**
- Trigger `_build_prompts` with the above setup.

**Expected:**
- `_enhance_with_causal` receives a list containing facts with IDs
  `["aaa", "ccc"]`.

**Assertion pseudocode:**
```
# Mock _enhance_with_causal to capture args
runner._build_prompts(repo_root, attempt=1, previous_error=None)
causal_input = enhance_with_causal_mock.call_args[0][0]
ASSERT {f.id for f in causal_input} == {"aaa", "ccc"}
```

### TS-94-7: Config field cross_spec_top_k default value

**Requirement:** 94-REQ-4.1
**Type:** unit
**Description:** Verify that `KnowledgeConfig` has a `cross_spec_top_k`
field defaulting to 15.

**Preconditions:**
- Default `KnowledgeConfig` instance.

**Input:**
- `KnowledgeConfig()` with no overrides.

**Expected:**
- `config.cross_spec_top_k == 15`

**Assertion pseudocode:**
```
config = KnowledgeConfig()
ASSERT config.cross_spec_top_k == 15
```

### TS-94-8: cross_spec_top_k zero disables retrieval

**Requirement:** 94-REQ-4.2
**Type:** unit
**Description:** Verify that setting `cross_spec_top_k=0` causes
cross-spec retrieval to be skipped entirely.

**Preconditions:**
- `KnowledgeConfig` with `cross_spec_top_k = 0`.
- Mock embedder available.

**Input:**
- Trigger `_retrieve_cross_spec_facts`.

**Expected:**
- Returns spec-specific facts unchanged.
- `embed_text` is never called.

**Assertion pseudocode:**
```
config.knowledge.cross_spec_top_k = 0
result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
ASSERT result == spec_facts
ASSERT embedder.embed_text.not_called
```

### TS-94-9: Embedder passed through factory

**Requirement:** 94-REQ-6.1
**Type:** unit
**Description:** Verify that the session runner factory creates an
`EmbeddingGenerator` and passes it to each `NodeSessionRunner`.

**Preconditions:**
- Mock `EmbeddingGenerator` constructor.

**Input:**
- Call the factory to create a runner.

**Expected:**
- The returned runner has a non-None `_embedder` attribute.

**Assertion pseudocode:**
```
factory = session_runner_factory(config, knowledge_db, ...)
runner = factory(node_id="spec:2", archetype="coder")
ASSERT runner._embedder is not None
```

### TS-94-10: No embedder skips retrieval

**Requirement:** 94-REQ-6.2
**Type:** unit
**Description:** Verify that when no embedder is provided, cross-spec
retrieval is skipped.

**Preconditions:**
- `NodeSessionRunner` created with `embedder=None`.

**Input:**
- Spec-specific facts: `[Fact(id="aaa")]`
- Trigger `_retrieve_cross_spec_facts`.

**Expected:**
- Returns spec-specific facts unchanged.

**Assertion pseudocode:**
```
runner = NodeSessionRunner(..., embedder=None)
result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
ASSERT result == spec_facts
```

## Edge Case Tests

### TS-94-E1: tasks.md does not exist

**Requirement:** 94-REQ-1.E1
**Type:** unit
**Description:** Verify extraction returns empty list when tasks.md is
missing.

**Preconditions:**
- `spec_dir` exists but contains no `tasks.md`.

**Input:**
- `spec_dir`: path to directory without `tasks.md`
- `task_group`: 2

**Expected:**
- Returns `[]`

**Assertion pseudocode:**
```
result = extract_subtask_descriptions(empty_spec_dir, 2)
ASSERT result == []
```

### TS-94-E2: Task group not found in tasks.md

**Requirement:** 94-REQ-1.E2
**Type:** unit
**Description:** Verify extraction returns empty list when the task group
number doesn't exist in `tasks.md`.

**Preconditions:**
- `tasks.md` exists with groups 1 and 2 but not group 5.

**Input:**
- `task_group`: 5

**Expected:**
- Returns `[]`

**Assertion pseudocode:**
```
result = extract_subtask_descriptions(spec_dir, 5)
ASSERT result == []
```

### TS-94-E3: Subtasks with only metadata bullets

**Requirement:** 94-REQ-1.E2
**Type:** unit
**Description:** Verify extraction returns empty list when all subtask
bullets are metadata annotations.

**Preconditions:**
- `tasks.md` with subtask whose only bullets are `_Requirements: ..._` and
  `_Test Spec: ..._`.

**Input:**
- `task_group`: matching group number

**Expected:**
- Returns `[]`

**Assertion pseudocode:**
```
result = extract_subtask_descriptions(spec_dir, task_group)
ASSERT result == []
```

### TS-94-E4: embed_text returns None

**Requirement:** 94-REQ-2.E1
**Type:** unit
**Description:** Verify that when embedding fails, spec-specific facts are
returned unchanged.

**Preconditions:**
- Mock embedder with `embed_text` returning `None`.
- Spec-specific facts: `[Fact(id="aaa")]`

**Input:**
- Valid descriptions extracted.

**Expected:**
- Returns `[Fact(id="aaa")]` unchanged.

**Assertion pseudocode:**
```
embedder.embed_text.return_value = None
result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
ASSERT result == spec_facts
```

### TS-94-E5: All search results are duplicates

**Requirement:** 94-REQ-3.E1
**Type:** unit
**Description:** Verify merge returns spec-specific set unchanged when all
cross-spec results already exist.

**Preconditions:**
- Spec-specific facts: `[Fact(id="aaa"), Fact(id="bbb")]`
- Cross-spec results: `[SearchResult(fact_id="aaa"), SearchResult(fact_id="bbb")]`

**Input:**
- The above lists.

**Expected:**
- Merged list is identical to spec-specific facts (length 2).

**Assertion pseudocode:**
```
merged = merge_cross_spec_facts(spec_facts, cross_spec_results)
ASSERT len(merged) == 2
ASSERT merged == spec_facts
```

### TS-94-E6: Vector search returns empty list

**Requirement:** 94-REQ-2.E2
**Type:** unit
**Description:** Verify that when vector search returns no results,
spec-specific facts are returned unchanged.

**Preconditions:**
- Mock embedder returning a valid embedding.
- Mock `VectorSearch.search` returning `[]`.
- Spec-specific facts: `[Fact(id="aaa")]`

**Input:**
- Valid descriptions extracted, valid embedding generated.

**Expected:**
- Returns `[Fact(id="aaa")]` unchanged (no merge step executed).

**Assertion pseudocode:**
```
embedder.embed_text.return_value = [0.1, 0.2, ...]
vector_search.search.return_value = []
result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
ASSERT result == spec_facts
```

### TS-94-E7: Exception during retrieval

**Requirement:** 94-REQ-5.1

**Type:** unit
**Description:** Verify that an exception in the retrieval pipeline is
caught and spec-specific facts are returned.

**Preconditions:**
- Mock embedder that raises `RuntimeError` from `embed_text`.
- Spec-specific facts: `[Fact(id="aaa")]`

**Input:**
- Trigger `_retrieve_cross_spec_facts`.

**Expected:**
- Returns `[Fact(id="aaa")]` unchanged.
- No exception propagated to caller.

**Assertion pseudocode:**
```
embedder.embed_text.side_effect = RuntimeError("model load failed")
result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
ASSERT result == spec_facts
```

## Property Test Cases

### TS-94-P1: Deduplication invariant

**Property:** Property 1 from design.md
**Validates:** 94-REQ-3.1, 94-REQ-3.E1
**Type:** property
**Description:** Merged result never contains duplicate fact IDs.

**For any:** Two lists of facts (spec-specific and cross-spec) with
arbitrary IDs drawn from a finite alphabet, sizes 0-50 each.
**Invariant:** The set of IDs in the merged result has the same cardinality
as the list length (no duplicates), and every spec-specific fact ID is
present.

**Assertion pseudocode:**
```
FOR ANY spec_facts IN list_of_facts(0..50), cross_facts IN list_of_facts(0..50):
    merged = merge_cross_spec_facts(spec_facts, cross_facts)
    ids = [f.id for f in merged]
    ASSERT len(ids) == len(set(ids))  # no duplicates
    ASSERT set(f.id for f in spec_facts).issubset(set(ids))  # spec facts preserved
```

### TS-94-P2: Budget independence

**Property:** Property 2 from design.md
**Validates:** 94-REQ-4.1, 94-REQ-2.2
**Type:** property
**Description:** Cross-spec retrieval respects its own top_k bound.

**For any:** `cross_spec_top_k` in range 0-50, mock VectorSearch returning
exactly `top_k` results.
**Invariant:** The number of cross-spec facts in the merged result is at
most `cross_spec_top_k`.

**Assertion pseudocode:**
```
FOR ANY top_k IN integers(0, 50):
    config.knowledge.cross_spec_top_k = top_k
    cross_results = generate_search_results(count=top_k)
    merged = merge_cross_spec_facts([], cross_results)
    ASSERT len(merged) <= top_k
```

### TS-94-P3: Graceful degradation identity

**Property:** Property 3 from design.md
**Validates:** 94-REQ-5.1, 94-REQ-2.E1
**Type:** property
**Description:** On any failure, output equals input spec-specific facts.

**For any:** A list of spec-specific facts and an exception type drawn from
`[RuntimeError, ValueError, OSError, duckdb.Error]`.
**Invariant:** When the embedder raises the exception, the result is
identical to the input fact list.

**Assertion pseudocode:**
```
FOR ANY spec_facts IN list_of_facts(0..20), exc IN sampled_exceptions:
    embedder.embed_text.side_effect = exc
    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
    ASSERT result == spec_facts
```

### TS-94-P4: Metadata bullet exclusion

**Property:** Property 4 from design.md
**Validates:** 94-REQ-1.2
**Type:** property
**Description:** Extracted descriptions never start with underscore.

**For any:** Generated `tasks.md` content with a mix of metadata and
non-metadata bullets (text starting with `_` and text not starting with
`_`), with at least one subtask.
**Invariant:** Every string in the extracted list does not start with `_`.

**Assertion pseudocode:**
```
FOR ANY tasks_content IN generated_tasks_md():
    write tasks_content to spec_dir / "tasks.md"
    result = extract_subtask_descriptions(spec_dir, 1)
    FOR EACH desc IN result:
        ASSERT not desc.startswith("_")
```

### TS-94-P5: Superseded exclusion

**Property:** Property 5 from design.md
**Validates:** 94-REQ-2.2
**Type:** property
**Description:** Vector search never returns superseded facts.

**For any:** A knowledge store with a mix of active and superseded facts.
**Invariant:** All returned SearchResult fact IDs correspond to facts with
`superseded_by IS NULL`.

**Assertion pseudocode:**
```
FOR ANY facts IN generated_facts_with_superseded():
    insert facts into knowledge store
    results = vector_search.search(query_embedding, exclude_superseded=True)
    FOR EACH result IN results:
        ASSERT facts[result.fact_id].superseded_by IS NULL
```

## Integration Smoke Tests

### TS-94-SMOKE-1: Full cross-spec retrieval pipeline

**Execution Path:** Path 1 from design.md
**Description:** Verify that cross-spec facts appear in assembled context
when a real knowledge store contains facts from multiple specs.

**Setup:**
- Real DuckDB knowledge store with facts from spec "03_auth" (content:
  "API uses JWT with RS256 signing") and spec "12_rate_limiting" (content:
  "Rate limiter config uses token bucket algorithm").
- Real embeddings generated for both facts.
- `tasks.md` for spec "12_rate_limiting" with task group 2 containing a
  subtask with bullet "Implement rate limiting middleware for API endpoints".
- Real `EmbeddingGenerator` and `VectorSearch` (not mocked).

**Trigger:**
- Call `_retrieve_cross_spec_facts(spec_dir, spec_12_facts)` where
  `spec_12_facts` contains only the rate limiting fact.

**Expected side effects:**
- The merged result contains both the rate limiting fact AND the JWT/auth
  fact from spec "03_auth" (retrieved via semantic similarity).
- The JWT fact's content appears in the merged list.

**Must NOT satisfy with:**
- Mocking `VectorSearch` (the real cosine distance search must run).
- Mocking `EmbeddingGenerator` (real embeddings must be generated).

**Assertion pseudocode:**
```
knowledge_db = setup_real_knowledge_store(auth_fact, rate_limit_fact)
embedder = EmbeddingGenerator(config.knowledge)
runner = NodeSessionRunner(..., knowledge_db=knowledge_db, embedder=embedder)
merged = runner._retrieve_cross_spec_facts(spec_dir, [rate_limit_fact])
ASSERT any("JWT" in f.content for f in merged)
ASSERT len(merged) >= 2
```

### TS-94-SMOKE-2: Graceful degradation with empty knowledge store

**Execution Path:** Path 2 from design.md
**Description:** Verify that cross-spec retrieval degrades gracefully when
the knowledge store has no embeddings.

**Setup:**
- Real DuckDB knowledge store with facts but NO embeddings in
  `memory_embeddings` table.
- Real `EmbeddingGenerator`.

**Trigger:**
- Call `_retrieve_cross_spec_facts(spec_dir, spec_facts)`.

**Expected side effects:**
- Returns `spec_facts` unchanged.
- No exception raised.

**Must NOT satisfy with:**
- Mocking the knowledge store connection.

**Assertion pseudocode:**
```
knowledge_db = setup_knowledge_store_no_embeddings(some_facts)
embedder = EmbeddingGenerator(config.knowledge)
runner = NodeSessionRunner(..., knowledge_db=knowledge_db, embedder=embedder)
result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)
ASSERT result == spec_facts
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 94-REQ-1.1 | TS-94-1 | unit |
| 94-REQ-1.2 | TS-94-2 | unit |
| 94-REQ-1.E1 | TS-94-E1 | unit |
| 94-REQ-1.E2 | TS-94-E2, TS-94-E3 | unit |
| 94-REQ-2.1 | TS-94-3 | unit |
| 94-REQ-2.2 | TS-94-4 | unit |
| 94-REQ-2.E1 | TS-94-E4 | unit |
| 94-REQ-2.E2 | TS-94-E6 | unit |
| 94-REQ-3.1 | TS-94-5 | unit |
| 94-REQ-3.2 | TS-94-6 | unit |
| 94-REQ-3.E1 | TS-94-E5 | unit |
| 94-REQ-4.1 | TS-94-7 | unit |
| 94-REQ-4.2 | TS-94-8 | unit |
| 94-REQ-5.1 | TS-94-E7 | unit |
| 94-REQ-6.1 | TS-94-9 | unit |
| 94-REQ-6.2 | TS-94-10 | unit |
| Property 1 | TS-94-P1 | property |
| Property 2 | TS-94-P2 | property |
| Property 3 | TS-94-P3 | property |
| Property 4 | TS-94-P4 | property |
| Property 5 | TS-94-P5 | property |
| Path 1 | TS-94-SMOKE-1 | integration |
| Path 2 | TS-94-SMOKE-2 | integration |
