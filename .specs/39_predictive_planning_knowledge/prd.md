# PRD: Predictive Planning and Knowledge Usage

## Problem

agent-fox has rich execution data (duration, cost, escalations, complexity
assessments) and a causal knowledge graph, but most of this data sits unused
during planning and dispatch. Ready tasks are ordered alphabetically. Memory
facts are not filtered by confidence. Review findings are siloed from the
causal graph. There is no predictive ordering, no file conflict detection,
and no project-level model for cost or stability estimation.

## Source

Research spike `docs/brainstorm/predictive-planning-and-knowledge.md`
(issue #146). All 10 prioritized recommendations are in scope.

## Goals

1. **Duration-based task ordering** with regression model fallback to presets
2. **Link review findings to causal graph** for richer downstream context
3. **Confidence-aware fact selection** with configurable threshold
4. **Pre-computed ranked facts** cached at plan time
5. **Project model** aggregating spec outcomes, module stability, archetype
   effectiveness
6. **Critical path forecasting** with learned duration weights
7. **Cross-task-group finding propagation** — review findings visible to
   downstream groups
8. **Predictive file conflict detection** — extract file impacts from specs,
   serialize conflicting parallel tasks
9. **Learned blocking thresholds** — adjust skeptic/oracle block_threshold
   from historical precision

## Scope

**In:** All 10 brainstorm items plus configurable presets for duration
estimation when historical data is sparse.

**Out:** Confidence normalization (spec 37), DuckDB hardening (spec 38),
cache discount modeling, remote dashboards, new CLI commands.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 37_confidence_normalization | 4 | 3 | Uses float confidence for threshold filtering in fact selection (group 3 needs parse_confidence from group 4 of spec 37) |
| 38_duckdb_hardening | 4 | 2 | All DuckDB queries assume non-optional connections; spec 38 group 4 hardens memory/prompt/routing which this spec's group 2+ uses |

## Clarifications

1. Duration ordering falls back to alphabetical when no historical data exists
2. Causal traversal extended to query across review_findings, verification_results,
   drift_findings tables (not promoted to memory_facts)
3. Confidence filtering threshold: configurable, default `>= 0.5`
4. Presets for duration estimation configurable in a single file
   (`agent_fox/routing/duration_presets.py` or config section)
5. Minimum data threshold before predictive ordering activates: configurable,
   default 10 outcomes
6. File conflict detection uses heuristic extraction from specs (regex-based)
7. Project model is a read-only aggregate — no write-back to specs
