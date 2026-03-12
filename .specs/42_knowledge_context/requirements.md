# Requirements Document

## Introduction

This specification improves the quality and completeness of knowledge context
assembled for coding sessions. It covers four areas: integrating causal graph
traversal with review findings, propagating configurable confidence thresholds,
wiring pre-computed fact ranking caches into session assembly, and extending
cross-task-group finding propagation to include all finding types.

## Glossary

| Term | Definition |
|------|------------|
| **Causal Traversal** | Breadth-first walk of the `fact_causes` graph starting from a seed fact, implemented by `traverse_causal_chain()` in `agent_fox/knowledge/causal.py`. |
| **Review Findings** | Skeptic review records stored in the `review_findings` table, queried via `agent_fox/knowledge/review_store.py`. |
| **Drift Findings** | Oracle drift records stored in the `drift_findings` table. |
| **Verification Results** | Verifier verdicts stored in the `verification_results` table. |
| **Confidence Threshold** | A float in [0.0, 1.0] below which facts are excluded from session context before keyword scoring. Configured via `knowledge.confidence_threshold`. |
| **RankedFactCache** | A dataclass in `agent_fox/engine/fact_cache.py` that holds pre-ranked facts for a spec, invalidated when the total fact count changes. |
| **Context Assembly** | The process of collecting spec documents, memory facts, and review findings into a prompt for a coding session, implemented in `agent_fox/session/prompt.py`. |
| **Prior Group Findings** | Active findings from task groups 1 through K-1 included in the context for task group K. |

## Requirements

### Requirement 1: Causal Traversal Includes Review Findings

**User Story:** As a coding agent, I want causal context traversal to surface
review findings, drift findings, and verification results linked to traversed
specs, so that I have complete awareness of known issues when working on
causally related facts.

#### Acceptance Criteria

1. [42-REQ-1.1] WHEN `select_context_with_causal()` assembles causal context, IT SHALL use `traverse_with_reviews()` instead of `traverse_causal_chain()` for each seed fact, so that review findings linked to traversed specs are included in the result.
2. [42-REQ-1.2] WHEN `traverse_with_reviews()` returns review findings, drift findings, or verification results, THE caller SHALL render them as structured items in the causal context section, distinguishing them from memory facts.
3. [42-REQ-1.3] THE system SHALL deduplicate review findings across multiple traversal seeds by their `id` field.

#### Edge Cases

1. [42-REQ-1.E1] IF no review findings, drift findings, or verification results exist for any traversed spec, THEN `traverse_with_reviews()` SHALL return only `CausalFact` objects and the context SHALL render without a findings subsection.
2. [42-REQ-1.E2] IF the review_findings, drift_findings, or verification_results tables do not exist (pre-migration database), THEN the query SHALL fail gracefully and return an empty list for that table.

### Requirement 2: Confidence-Aware Fact Filtering

**User Story:** As a system operator, I want to configure the minimum confidence
threshold for fact inclusion, so that low-confidence facts do not pollute session
context.

#### Acceptance Criteria

1. [42-REQ-2.1] WHEN the session lifecycle calls `select_relevant_facts()`, IT SHALL pass the `confidence_threshold` value from `KnowledgeConfig` rather than relying on the function's default parameter.
2. [42-REQ-2.2] WHEN `precompute_fact_rankings()` is called, IT SHALL accept and forward the configured `confidence_threshold` to `select_relevant_facts()`.
3. [42-REQ-2.3] THE `knowledge.confidence_threshold` config field SHALL be clamped to [0.0, 1.0] with a default of 0.5.

#### Edge Cases

1. [42-REQ-2.E1] IF `confidence_threshold` is set to 0.0, THEN all facts SHALL pass the confidence filter regardless of their confidence value.
2. [42-REQ-2.E2] IF `confidence_threshold` is set to 1.0, THEN only facts with confidence exactly 1.0 SHALL pass the filter.

### Requirement 3: Pre-Computed Fact Ranking Cache

**User Story:** As a system operator, I want fact rankings to be computed once
at plan time and reused across sessions for the same spec, so that context
assembly is faster for multi-group specs.

#### Acceptance Criteria

1. [42-REQ-3.1] WHEN `knowledge.fact_cache_enabled` is `true` AND the orchestrator begins plan dispatch, THE system SHALL call `precompute_fact_rankings()` for all specs in the plan.
2. [42-REQ-3.2] WHEN assembling session context for a spec that has a valid cache entry, THE system SHALL use `get_cached_facts()` instead of re-running `select_relevant_facts()`.
3. [42-REQ-3.3] WHEN `get_cached_facts()` detects that the current fact count differs from `fact_count_at_creation`, IT SHALL return `None` to signal cache invalidation, and the caller SHALL fall back to live computation.
4. [42-REQ-3.4] WHEN `knowledge.fact_cache_enabled` is `false`, THE system SHALL skip cache population and always use live fact computation.

#### Edge Cases

1. [42-REQ-3.E1] IF the knowledge store has zero facts, THEN `precompute_fact_rankings()` SHALL produce cache entries with empty `ranked_facts` lists rather than failing.
2. [42-REQ-3.E2] IF a spec name is not present in the cache (e.g., a spec added after plan time), THEN `get_cached_facts()` SHALL return `None` and the caller SHALL fall back to live computation.

### Requirement 4: Cross-Task-Group Finding Propagation

**User Story:** As a coding agent working on task group K, I want to see all
active findings (review, drift, and verification) from prior groups, so that I
can address or avoid repeating known issues.

#### Acceptance Criteria

1. [42-REQ-4.1] WHEN assembling context for task group K (where K > 1), THE system SHALL query `review_findings`, `drift_findings`, AND `verification_results` for groups 1 through K-1, filtering to active (non-superseded) records only.
2. [42-REQ-4.2] THE prior group findings section SHALL be rendered under the heading `## Prior Group Findings` with each finding prefixed by its group number and type (review, drift, or verification).
3. [42-REQ-4.3] THE prior group findings SHALL be ordered by `created_at` ascending within the rendered section.

#### Edge Cases

1. [42-REQ-4.E1] IF task group is 1, THEN the system SHALL NOT query for or render prior group findings.
2. [42-REQ-4.E2] IF no active findings exist from prior groups, THEN the `## Prior Group Findings` section SHALL be omitted from the context entirely.
