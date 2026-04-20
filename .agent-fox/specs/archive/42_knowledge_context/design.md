# Design Document

## Overview

This design integrates four knowledge context improvements into the existing
agent-fox architecture. Each change is scoped to modify existing modules with
minimal new abstractions. The causal traversal integration and finding
propagation extend existing functions in `prompt.py` and `causal.py`. The
confidence threshold propagation threads a config value through the session
lifecycle. The fact cache integration wires the existing `RankedFactCache`
into the orchestrator and session assembly paths.

## Architecture

### Module Map

```
agent_fox/
  core/
    config.py           # KnowledgeConfig (already has confidence_threshold,
                        #   fact_cache_enabled) -- no schema changes needed
  knowledge/
    causal.py           # traverse_with_reviews() -- already implemented
    review_store.py     # ReviewFinding, DriftFinding, VerificationResult
  memory/
    filter.py           # select_relevant_facts() -- already has threshold param
  engine/
    fact_cache.py       # RankedFactCache, precompute/get -- already implemented
    engine.py           # Orchestrator -- wire cache population at plan time
  session/
    prompt.py           # assemble_context(), select_context_with_causal(),
                        #   get_prior_group_findings(), render_prior_group_findings()
                        #   -- extend for cache usage and full finding propagation
```

### Existing State

Several components from the original spec 39 are already partially implemented:

- `traverse_with_reviews()` exists in `causal.py` but is not called from
  `select_context_with_causal()` (which still uses `traverse_causal_chain()`).
- `select_relevant_facts()` accepts `confidence_threshold` but callers pass
  the hard-coded default rather than the configured value.
- `RankedFactCache`, `precompute_fact_rankings()`, and `get_cached_facts()`
  exist in `engine/fact_cache.py` but are not wired into the session lifecycle.
- `get_prior_group_findings()` queries only `review_findings`, not
  `drift_findings` or `verification_results`.

## Detailed Design

### 1. Causal Traversal with Review Findings (REQ-1)

**Change:** In `agent_fox/session/prompt.py`, modify `select_context_with_causal()`
to call `traverse_with_reviews()` instead of `traverse_causal_chain()`.

```python
# Current (prompt.py line ~465):
from agent_fox.knowledge.causal import traverse_causal_chain

# Changed to:
from agent_fox.knowledge.causal import traverse_with_reviews
```

The function already deduplicates by `fact_id`. The change extends this to also
handle non-CausalFact objects (ReviewFinding, DriftFinding, VerificationResult)
returned by `traverse_with_reviews()`. These are rendered as structured items
with a type prefix in the causal context section.

**Rendering:** Non-CausalFact items are rendered with a type label:

```
- [review] [severity: major] Description text
- [drift] [severity: minor] Description text
- [verification] requirement_id: PASS/FAIL
```

**Deduplication:** The existing `seen_ids` set in `select_context_with_causal()`
handles deduplication across multiple traversal seeds, since all finding types
have an `id` field.

### 2. Confidence Threshold Propagation (REQ-2)

**Change:** Thread the configured threshold through the call chain:

1. `engine.py` (orchestrator) reads `config.knowledge.confidence_threshold`
   and passes it to session preparation.
2. Session preparation passes it to `select_relevant_facts()` and
   `precompute_fact_rankings()`.

The `KnowledgeConfig` already has the `confidence_threshold` field with
clamping validation. The only change is ensuring callers read from config
instead of relying on the function default.

**Interface change in session lifecycle:**

```python
# In the session preparation path, replace:
ranked = select_relevant_facts(all_facts, spec, keywords)
# With:
ranked = select_relevant_facts(
    all_facts, spec, keywords,
    confidence_threshold=config.knowledge.confidence_threshold,
)
```

### 3. Fact Ranking Cache Integration (REQ-3)

**Change:** Wire existing cache into the orchestrator and session assembly:

1. **Plan time (engine.py):** After building the execution plan, if
   `config.knowledge.fact_cache_enabled` is true, call
   `precompute_fact_rankings()` with all spec names in the plan and the
   configured confidence threshold. Store the result on the orchestrator
   instance.

2. **Session assembly (prompt.py or session lifecycle):** Before calling
   `select_relevant_facts()`, check `get_cached_facts()`. If it returns a
   valid list, use it. If it returns `None` (stale or missing), fall back
   to live computation.

3. **Staleness detection:** `get_cached_facts()` already compares
   `fact_count_at_creation` with the current count. The caller must query
   the current active fact count from DuckDB:

   ```sql
   SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL
   ```

**Cache lifetime:** The cache lives on the orchestrator instance for the
duration of a plan dispatch. It is not persisted to disk.

### 4. Cross-Task-Group Finding Propagation (REQ-4)

**Change:** Extend `get_prior_group_findings()` in `prompt.py` to also query
`drift_findings` and `verification_results` tables.

**Current implementation** queries only `review_findings`. The extended version
queries all three tables and returns a union of results, tagged by type.

**New data structure:** A lightweight tagged union for prior findings:

```python
@dataclass(frozen=True)
class PriorFinding:
    """A finding from a prior task group, tagged by type."""
    type: str          # "review" | "drift" | "verification"
    group: str         # task_group value
    severity: str      # severity or verdict
    description: str   # description or evidence
    created_at: str
```

**Return type change:** `get_prior_group_findings()` changes from returning
`list[ReviewFinding]` to returning `list[PriorFinding]`. The
`render_prior_group_findings()` function is updated accordingly.

**Rendering:** `render_prior_group_findings()` is updated to handle the
tagged findings:

```markdown
## Prior Group Findings

- [group 1] [review] [major] Description of review finding
- [group 1] [drift] [minor] Description of drift finding
- [group 2] [verification] REQ-1: PASS
```

All findings are sorted by `created_at` ascending.

## Correctness Properties

1. **Deduplication invariant:** No finding ID appears more than once in the
   assembled context, regardless of how many traversal seeds reference it.

2. **Confidence monotonicity:** Increasing the confidence threshold can only
   reduce the number of facts selected, never increase it. For thresholds
   T1 < T2: `|select(T2)| <= |select(T1)|`.

3. **Cache consistency:** If facts have not changed (count unchanged), cached
   rankings produce identical results to live computation.

4. **Group boundary invariant:** Prior group findings for group K never
   include findings from group K or later.

5. **Completeness:** Prior group findings include all three finding types
   (review, drift, verification), not a subset.

## Error Handling

- **Missing tables:** Pre-migration databases may lack `review_findings`,
  `drift_findings`, or `verification_results`. Queries against missing tables
  are caught by the existing exception handlers in `causal.py` query helpers
  and return empty lists.

- **Cache miss:** When `get_cached_facts()` returns `None`, callers fall back
  to live computation without error.

- **Empty results:** All rendering functions handle empty input by returning
  `None` or empty string, which causes the section to be omitted from context.

## Testing Strategy

- Unit tests verify each component in isolation with DuckDB in-memory fixtures.
- Property tests verify confidence monotonicity and deduplication invariants.
- Integration tests verify the full assembly path from config through rendering.
