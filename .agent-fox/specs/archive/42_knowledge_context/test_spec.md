# Test Specification

## Overview

Tests are organized by requirement area. All tests requiring DuckDB use an
in-memory connection with schema migrations applied. Tests use the existing
`ReviewFinding`, `DriftFinding`, and `VerificationResult` dataclasses from
`agent_fox/knowledge/review_store.py`.

## Test Commands

```bash
# Spec tests
uv run pytest tests/unit/knowledge/test_knowledge_context.py tests/unit/session/test_context_assembly.py -v

# Property tests
uv run pytest tests/property/knowledge/test_knowledge_context_props.py -v

# All spec + property tests
uv run pytest tests/unit/knowledge/test_knowledge_context.py tests/unit/session/test_context_assembly.py tests/property/knowledge/test_knowledge_context_props.py -v

# Full suite
uv run pytest -x -q
```

## Unit Tests

### Causal Traversal with Review Findings

**File:** `tests/unit/knowledge/test_knowledge_context.py`

#### TS-42-1: traverse_with_reviews returns CausalFact and review findings

**Setup:** Insert two memory facts with a causal link. Insert a ReviewFinding
for the same spec as one of the facts.

**Action:** Call `traverse_with_reviews()` with the cause fact ID.

**Assert:**
- Result contains CausalFact objects for both facts.
- Result contains the ReviewFinding object.
- All items are deduplicated by ID.

**Requirement:** 42-REQ-1.1

#### TS-42-2: traverse_with_reviews includes drift findings

**Setup:** Insert a memory fact. Insert a DriftFinding for the same spec.

**Action:** Call `traverse_with_reviews()` with the fact ID.

**Assert:** Result contains both the CausalFact and the DriftFinding.

**Requirement:** 42-REQ-1.1

#### TS-42-3: traverse_with_reviews includes verification results

**Setup:** Insert a memory fact. Insert a VerificationResult for the same spec.

**Action:** Call `traverse_with_reviews()` with the fact ID.

**Assert:** Result contains both the CausalFact and the VerificationResult.

**Requirement:** 42-REQ-1.1

#### TS-42-4: traverse_with_reviews deduplicates across seeds

**Setup:** Insert three facts: A -> B (causal link), both in the same spec.
Insert one ReviewFinding for that spec.

**Action:** Call `traverse_with_reviews()` for fact A, then for fact B.

**Assert:** The ReviewFinding ID appears exactly once in each result.

**Requirement:** 42-REQ-1.3

#### TS-42-E1: traverse_with_reviews with no findings returns only CausalFacts

**Setup:** Insert two memory facts with a causal link. No review/drift/verification records.

**Action:** Call `traverse_with_reviews()`.

**Assert:** Result contains only CausalFact objects. Result length equals
the number of traversed facts.

**Requirement:** 42-REQ-1.E1

#### TS-42-E2: traverse_with_reviews handles missing tables gracefully

**Setup:** Create a DuckDB connection with only `memory_facts` and
`fact_causes` tables (no review/drift/verification tables).

**Action:** Call `traverse_with_reviews()`.

**Assert:** Returns CausalFact objects without error. No exceptions raised.

**Requirement:** 42-REQ-1.E2

### select_context_with_causal Uses traverse_with_reviews

**File:** `tests/unit/session/test_context_assembly.py`

#### TS-42-5: select_context_with_causal includes review findings in result

**Setup:** Insert facts and a ReviewFinding for the same spec. Provide
keyword_facts matching one of the inserted facts.

**Action:** Call `select_context_with_causal()`.

**Assert:** The returned list includes an entry representing the review finding,
distinguishable from regular fact dicts.

**Requirement:** 42-REQ-1.1, 42-REQ-1.2

### Confidence-Aware Fact Filtering

**File:** `tests/unit/knowledge/test_knowledge_context.py`

#### TS-42-6: select_relevant_facts filters below threshold

**Setup:** Create facts with confidence values 0.3, 0.5, 0.7, 0.9.

**Action:** Call `select_relevant_facts()` with `confidence_threshold=0.5`.

**Assert:** Only facts with confidence >= 0.5 appear in results.
The fact with confidence 0.3 is excluded.

**Requirement:** 42-REQ-2.1

#### TS-42-7: confidence threshold 0.0 includes all facts

**Setup:** Create facts with confidence values 0.0, 0.1, 0.5, 1.0.

**Action:** Call `select_relevant_facts()` with `confidence_threshold=0.0`.

**Assert:** All four facts are eligible for inclusion.

**Requirement:** 42-REQ-2.E1

#### TS-42-8: confidence threshold 1.0 includes only perfect confidence

**Setup:** Create facts with confidence values 0.9, 0.99, 1.0.

**Action:** Call `select_relevant_facts()` with `confidence_threshold=1.0`.

**Assert:** Only the fact with confidence exactly 1.0 passes the filter.

**Requirement:** 42-REQ-2.E2

#### TS-42-9: config confidence threshold is clamped

**Setup:** Create a `KnowledgeConfig` with `confidence_threshold=-0.5`.

**Assert:** The resulting value is clamped to 0.0.

**Setup:** Create a `KnowledgeConfig` with `confidence_threshold=1.5`.

**Assert:** The resulting value is clamped to 1.0.

**Requirement:** 42-REQ-2.3

### Pre-Computed Fact Ranking Cache

**File:** `tests/unit/knowledge/test_knowledge_context.py`

#### TS-42-10: precompute_fact_rankings produces cache entries

**Setup:** Insert 5 facts into DuckDB across 2 specs.

**Action:** Call `precompute_fact_rankings()` with both spec names.

**Assert:** Returns a dict with two entries. Each entry has a non-empty
`ranked_facts` list. Each entry has `fact_count_at_creation` matching
total active fact count.

**Requirement:** 42-REQ-3.1

#### TS-42-11: get_cached_facts returns cached facts when valid

**Setup:** Build a cache. Query with matching fact count.

**Action:** Call `get_cached_facts()` with correct `current_fact_count`.

**Assert:** Returns the cached `ranked_facts` list.

**Requirement:** 42-REQ-3.2

#### TS-42-12: get_cached_facts returns None on stale cache

**Setup:** Build a cache with fact_count_at_creation = 5.

**Action:** Call `get_cached_facts()` with `current_fact_count=6`.

**Assert:** Returns `None`.

**Requirement:** 42-REQ-3.3

#### TS-42-13: get_cached_facts returns None for missing spec

**Setup:** Build a cache for spec "alpha".

**Action:** Call `get_cached_facts()` with spec_name "beta".

**Assert:** Returns `None`.

**Requirement:** 42-REQ-3.E2

#### TS-42-E3: precompute with zero facts produces empty cache entries

**Setup:** DuckDB with schema but no facts.

**Action:** Call `precompute_fact_rankings()` with spec names.

**Assert:** Each cache entry has `ranked_facts = []` and
`fact_count_at_creation = 0`. No exception raised.

**Requirement:** 42-REQ-3.E1

#### TS-42-14: cache disabled skips population

**Setup:** Create config with `fact_cache_enabled=False`.

**Action:** Verify that the orchestrator path that calls
`precompute_fact_rankings()` is skipped.

**Assert:** No cache is populated. Context assembly uses live computation.

**Requirement:** 42-REQ-3.4

### Cross-Task-Group Finding Propagation

**File:** `tests/unit/session/test_context_assembly.py`

#### TS-42-15: prior findings include review findings from earlier groups

**Setup:** Insert ReviewFindings for spec "test_spec" in groups "1" and "2".

**Action:** Call `get_prior_group_findings()` with task_group=3.

**Assert:** Both findings from groups 1 and 2 are returned.

**Requirement:** 42-REQ-4.1

#### TS-42-16: prior findings include drift findings from earlier groups

**Setup:** Insert DriftFindings for spec "test_spec" in groups "1" and "2".

**Action:** Call extended `get_prior_group_findings()` with task_group=3.

**Assert:** Drift findings from both prior groups are included in results.

**Requirement:** 42-REQ-4.1

#### TS-42-17: prior findings include verification results from earlier groups

**Setup:** Insert VerificationResults for spec "test_spec" in groups "1" and "2".

**Action:** Call extended `get_prior_group_findings()` with task_group=3.

**Assert:** Verification results from both prior groups are included.

**Requirement:** 42-REQ-4.1

#### TS-42-18: prior findings exclude current and future groups

**Setup:** Insert findings for groups "1", "2", "3", "4".

**Action:** Call `get_prior_group_findings()` with task_group=3.

**Assert:** Only findings from groups 1 and 2 are returned. Findings from
groups 3 and 4 are excluded.

**Requirement:** 42-REQ-4.1

#### TS-42-19: render_prior_group_findings includes type labels

**Setup:** Create a list of PriorFinding objects with types "review", "drift",
and "verification".

**Action:** Call `render_prior_group_findings()`.

**Assert:** Output starts with `## Prior Group Findings`. Each line includes
the group number and type label (e.g., `[review]`, `[drift]`, `[verification]`).

**Requirement:** 42-REQ-4.2

#### TS-42-20: prior findings are ordered by created_at

**Setup:** Create findings with timestamps out of order.

**Action:** Call `render_prior_group_findings()`.

**Assert:** Rendered lines are in `created_at` ascending order.

**Requirement:** 42-REQ-4.3

#### TS-42-E4: task_group=1 returns no prior findings

**Action:** Call `get_prior_group_findings()` with task_group=1.

**Assert:** Returns an empty list.

**Requirement:** 42-REQ-4.E1

#### TS-42-E5: no active findings omits section

**Setup:** No findings in any table for the spec.

**Action:** Call `assemble_context()` with task_group=2.

**Assert:** The assembled context does not contain "Prior Group Findings".

**Requirement:** 42-REQ-4.E2

## Property Tests

**File:** `tests/property/knowledge/test_knowledge_context_props.py`

#### TS-42-P1: Confidence monotonicity

**Strategy:** Generate a list of facts with random confidence values and
two thresholds T1 < T2.

**Assert:** `len(select_relevant_facts(facts, spec, kw, confidence_threshold=T2))
<= len(select_relevant_facts(facts, spec, kw, confidence_threshold=T1))`.

**Requirement:** 42-REQ-2.1, 42-REQ-2.E1

#### TS-42-P2: Deduplication invariant

**Strategy:** Generate a set of facts and multiple traversal seeds that
overlap in spec coverage.

**Assert:** No `id` appears more than once in the combined traversal results.

**Requirement:** 42-REQ-1.3

#### TS-42-P3: Group boundary invariant

**Strategy:** Generate findings for groups 1 through N. Pick a target
group K in [1, N].

**Assert:** All findings returned by `get_prior_group_findings(task_group=K)`
have `task_group` values strictly less than K (as integers).

**Requirement:** 42-REQ-4.1

#### TS-42-P4: Cache staleness detection

**Strategy:** Generate a cache with `fact_count_at_creation = N`. Query with
`current_fact_count` values from 0 to 2*N.

**Assert:** `get_cached_facts()` returns a list only when
`current_fact_count == N`, returns `None` otherwise.

**Requirement:** 42-REQ-3.3
