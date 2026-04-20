# PRD: Knowledge Context Improvements

## Problem

Agent-fox's session context assembly has four gaps that reduce the quality of
information available to coding agents during task execution:

1. **Causal traversal ignores review findings.** The causal graph traversal
   (`traverse_causal_chain`) follows fact-to-fact edges in the `fact_causes`
   table but does not surface review findings, drift findings, or verification
   results linked to the same specs. The `traverse_with_reviews()` function
   exists but is not wired into session context assembly.

2. **No confidence-based pre-filtering.** The `select_relevant_facts()` function
   in `agent_fox/knowledge/filtering.py` (post spec 39 consolidation) accepts a `confidence_threshold` parameter
   and filters before keyword scoring, but this threshold is not propagated from
   the `KnowledgeConfig` through the session lifecycle. Callers use the
   hard-coded default (0.5) instead of the user's configured value.

3. **Fact ranking is recomputed every session.** The `RankedFactCache` in
   `agent_fox/engine/fact_cache.py` exists but is not integrated into the
   session context assembly path. Each session independently loads all facts and
   runs keyword scoring, wasting time on repeated computation.

4. **Prior group findings are incomplete.** The `get_prior_group_findings()`
   function in `agent_fox/session/prompt.py` queries only `review_findings`.
   It does not include drift findings or verification results from prior task
   groups, missing important context about known issues.

## Source

Extracted from the predictive planning and knowledge research spike
(`docs/brainstorm/predictive-planning-and-knowledge.md`, issue #146). These
four features were originally part of spec 39 (package consolidation) but are
now tracked independently for focused implementation.

## Goals

1. Wire `traverse_with_reviews()` into session context assembly so that causal
   traversal surfaces review, drift, and verification findings alongside
   memory facts.

2. Propagate the configured `confidence_threshold` from `KnowledgeConfig`
   through the session lifecycle to `select_relevant_facts()`, replacing
   hard-coded defaults.

3. Integrate `RankedFactCache` into the session context assembly path: populate
   the cache at plan time, use cached rankings during context assembly, and
   invalidate when facts change.

4. Extend cross-task-group finding propagation to include drift findings and
   verification results from prior groups, not just review findings.

## Non-Goals

- Duration ordering for ready tasks (spec 41).
- Project model and critical path analysis (spec 43).
- File conflict detection and blocking thresholds (spec 43).
- Audit logging (spec 40).
- Changes to the causal graph schema or `fact_causes` table structure.
- Changes to the DuckDB migration system.

## Dependencies

| Spec | Relationship | Justification |
|------|-------------|---------------|
| 37 (confidence normalization) | Requires | Float confidence values in [0.0, 1.0] |
| 38 (DuckDB hardening) | Requires | Non-optional DuckDB connections |

## Success Metrics

- Causal context assembly includes review/drift/verification findings when
  they exist for traversed specs.
- Configured confidence threshold is used (not hard-coded default) in all
  fact selection paths.
- Fact ranking is computed once at plan time and reused across sessions for
  the same spec, with correct invalidation on fact changes.
- Task group K receives drift findings and verification results from groups
  1 through K-1 alongside review findings.
