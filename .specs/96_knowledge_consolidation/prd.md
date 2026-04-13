# Knowledge Consolidation Agent

## Problem

The agent-fox knowledge system extracts facts per-session and runs basic
dedup/contradiction detection at harvest time. But there is no higher-level
pass that analyzes knowledge quality across specs. After dozens of specs, the
knowledge base accumulates:

- **Redundant facts** across specs (Spec 3 and Spec 7 both record facts about
  the auth module, but neither knows about the other).
- **Stale facts** that reference files or functions that have since been deleted
  or heavily refactored.
- **Unrecognized patterns** -- the same gotcha appears in 4+ specs but is never
  elevated to a cross-cutting pattern.
- **Redundant causal chains** -- A->B->C exists alongside a direct A->C edge,
  and the intermediate step B adds no value.

Night Shift analyzes code quality. The knowledge system needs an equivalent
that analyzes knowledge quality.

## Solution

A post-spec consolidation pass that runs automatically during the
orchestrator's sync barrier (when specs complete) and at end-of-run. The pass
executes six ordered steps:

1. **Entity graph refresh** -- Run `analyze_codebase()` (spec 95) to update
   the structural representation of the codebase.
2. **Fact-entity linking** -- Run `link_facts()` (spec 95) for facts that
   lack entity links.
3. **Git verification** -- For facts with entity links, check if referenced
   files still exist and whether they have changed significantly since the
   fact was created. Supersede facts for deleted files; halve confidence for
   significantly changed files.
4. **Cross-spec fact merging** -- Find clusters of similar facts from
   different specs via embedding similarity. Send each cluster to an LLM to
   decide: merge (supersede originals with one consolidated fact) or link
   (add causal edges).
5. **Pattern promotion** -- Detect facts that recur as similar patterns
   across 3+ specs. Use an LLM to confirm genuine patterns. Create new
   pattern facts with elevated confidence.
6. **Causal chain pruning** -- Identify redundant chains A->B->C where A->C
   also exists. Use an LLM to evaluate whether B is still meaningful. Remove
   redundant intermediate edges.

## Design Decisions

1. **Trigger: sync barrier + end-of-run.** Consolidation runs during the sync
   barrier sequence (after existing knowledge compaction and lifecycle cleanup)
   when `completed_spec_names()` detects newly completed specs. It also runs at
   end-of-run for any remaining completed specs. The sync barrier provides
   natural exclusive write access since session dispatch is paused.

2. **LLM decides merge vs. link.** When similar facts from different specs are
   found, an LLM classifies each cluster as "merge" or "link." Merging creates
   a single consolidated fact and supersedes the originals. Linking adds causal
   edges between related facts without modifying them.

3. **LLM detects patterns.** Pattern promotion uses an LLM to confirm that a
   cluster of similar facts across 3+ specs represents a genuine recurring
   pattern, rather than relying on heuristic matching (same keywords, same
   category).

4. **Entity graph integration.** This spec wires spec 95's standalone entity
   graph into the orchestration pipeline. The consolidation pass calls
   `analyze_codebase()` to refresh the graph, `link_facts()` to connect new
   facts to entities, and uses `fact_entities` links for git verification.

5. **Git verification uses spec 95 fact-entity links.** File reference
   resolution for staleness checking relies on the `fact_entities` junction
   table from spec 95, not regex parsing of fact content.

6. **Confidence adjustment for stale facts (REVISIT).** When git verification
   finds that a fact's referenced file has been deleted, the fact is superseded
   via a consolidation sentinel UUID. When a file has changed significantly
   (configurable threshold, default >50% lines modified), the fact's stored
   confidence is halved. *This threshold and reduction factor should be
   revisited after real-world usage data is available.*

7. **LLM evaluates causal chain intermediates.** When a redundant chain
   A->B->C is found (with A->C also existing), an LLM evaluates whether B
   provides independent value. If not, intermediate edges A->B and B->C are
   removed while A->C is preserved.

8. **DuckDB side effects only.** The consolidation pass produces only DuckDB
   mutations (supersessions, confidence updates, new facts, causal edges,
   edge removals). No reports or output files are generated.

9. **Exclusive write access during consolidation.** The sync barrier already
   pauses session dispatch, providing natural exclusive access to the knowledge
   DB. No concurrent sessions can write during consolidation.

10. **Shared budget, separate reporting.** Consolidation LLM calls share the
    run's cost budget. Costs are tracked and reported separately via audit
    events so they can be distinguished from session costs.

11. **Re-processing is acceptable.** If the orchestrator restarts and
    consolidation runs twice on the same spec, the second run is safe: merges
    are idempotent (already-superseded facts won't cluster again), and git
    verification re-checks current state.

12. **Pattern promotion creates new facts.** Rather than mutating existing
    facts' categories, pattern promotion creates a new fact with
    category=PATTERN and confidence=0.9, linked to the original facts via
    causal edges.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 95_entity_graph | 2 | 1 | Tests need entity graph tables and entity_store CRUD for fixtures; spec 95 group 2 creates migration v8 and entity_store.py |
| 95_entity_graph | 4 | 4 | Entity graph integration calls analyze_codebase (group 3), link_facts, find_related_facts (group 4); group 4 is the earliest providing the full callable API |
