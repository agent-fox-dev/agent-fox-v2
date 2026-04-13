# Requirements Document

## Introduction

The knowledge consolidation agent is a post-spec quality pass for the agent-fox
knowledge system. It runs automatically during the orchestrator's sync barrier
and at end-of-run, performing six ordered steps: entity graph refresh,
fact-entity linking, git verification, cross-spec fact merging, pattern
promotion, and causal chain pruning. It wires spec 95's standalone entity graph
into the orchestration pipeline and adds LLM-powered knowledge quality
operations on top of the existing per-session dedup and contradiction
infrastructure.

## Glossary

- **Consolidation pass** -- A single execution of the six-step consolidation
  pipeline, triggered at sync barrier or end-of-run.
- **Consolidation result** -- The return value of a consolidation pass,
  containing per-step counts and total LLM cost.
- **Stale fact** -- A fact whose referenced files have been deleted or
  significantly changed since the fact was created.
- **Significant change** -- A file modification where the ratio of changed
  lines (insertions + deletions) to current file length exceeds a configurable
  threshold (default 0.5).
- **Consolidation sentinel** -- A deterministic UUID
  (`uuid5(NAMESPACE_DNS, "agent-fox.consolidation.stale")`) used as the
  `superseded_by` value for facts invalidated by consolidation.
- **Fact cluster** -- A group of semantically similar facts from different
  specs, identified via embedding cosine similarity above a configurable
  threshold.
- **Pattern fact** -- A new fact with category `pattern` and elevated
  confidence, created when an LLM confirms that a cluster of similar facts
  across 3+ specs represents a genuine recurring pattern.
- **Redundant chain** -- A causal chain A->B->C where a direct edge A->C also
  exists, making the intermediate step B a candidate for pruning.
- **Sync barrier** -- A periodic pause in session dispatch during which the
  orchestrator runs housekeeping tasks (compaction, lifecycle cleanup,
  consolidation).
- **Completed spec** -- A spec whose every task graph node has status
  "completed," as detected by `GraphSync.completed_spec_names()`.
- **Unlinked fact** -- A fact in `memory_facts` that has no corresponding row
  in `fact_entities`.

## Requirements

### Requirement 1: Consolidation Pipeline Orchestration

**User Story:** As the orchestrator, I want to run a consolidation pipeline
as an ordered sequence of knowledge-quality steps so that the knowledge base
improves automatically after specs complete.

#### Acceptance Criteria

1. [96-REQ-1.1] WHEN the consolidation pipeline is invoked, THE system SHALL
   execute steps in order: entity graph refresh, fact-entity linking, git
   verification, cross-spec merging, pattern promotion, causal chain pruning
   AND return a `ConsolidationResult` containing per-step counts and total
   LLM cost to the caller.

2. [96-REQ-1.2] IF any step raises an exception, THEN THE system SHALL log a
   warning, record the failure in the result, and continue with the next step.

3. [96-REQ-1.3] WHEN the consolidation pipeline completes, THE system SHALL
   emit a `consolidation.complete` audit event containing the full
   `ConsolidationResult`.

#### Edge Cases

1. [96-REQ-1.E1] IF the knowledge database contains zero active facts, THEN
   THE system SHALL return a `ConsolidationResult` with all counts set to
   zero and skip all LLM calls.

2. [96-REQ-1.E2] IF the consolidation pipeline is invoked but the entity graph
   tables do not exist (migration v8 not applied), THEN THE system SHALL skip
   the entity graph refresh and fact-entity linking steps, log a warning, and
   continue with git verification using an empty entity set.

### Requirement 2: Entity Graph Refresh and Fact Linking

**User Story:** As a knowledge system, I want to refresh the entity graph and
link unlinked facts to entities after each spec completes so that the
structural representation stays current.

#### Acceptance Criteria

1. [96-REQ-2.1] WHEN the entity graph refresh step runs, THE system SHALL call
   `analyze_codebase(repo_root, conn)` from the entity graph subsystem (spec
   95) to update the entity graph with the current codebase state.

2. [96-REQ-2.2] WHEN the fact-entity linking step runs, THE system SHALL
   identify all unlinked facts (facts with no row in `fact_entities`) AND call
   `link_facts(conn, unlinked_facts, repo_root)` to create entity links.

3. [96-REQ-2.3] WHEN both steps complete, THE system SHALL include the entity
   graph `AnalysisResult` and the `LinkResult` counts in the
   `ConsolidationResult` returned to the caller.

#### Edge Cases

1. [96-REQ-2.E1] IF the repository root path does not exist or is not a git
   repository, THEN THE system SHALL skip both entity graph steps, log a
   warning, and continue with remaining consolidation steps.

### Requirement 3: Git Verification

**User Story:** As a knowledge system, I want to verify that facts referencing
specific files are still valid by checking the current codebase state so that
stale knowledge is flagged or decayed.

#### Acceptance Criteria

1. [96-REQ-3.1] WHEN the git verification step runs, THE system SHALL query
   all active facts that have at least one `fact_entities` link to a file
   entity AND check whether each linked file still exists on disk.

2. [96-REQ-3.2] IF all file entities linked to a fact have been deleted from
   the codebase (file no longer exists on disk), THEN THE system SHALL set the
   fact's `superseded_by` to the consolidation sentinel UUID.

3. [96-REQ-3.3] IF a fact has a non-null `commit_sha` AND any of its linked
   files still exist but have changed significantly (change ratio exceeds
   the configured threshold), THEN THE system SHALL halve the fact's stored
   `confidence` value.

4. [96-REQ-3.4] WHEN the git verification step completes, THE system SHALL
   return a `VerificationResult` containing counts of facts checked,
   superseded, decayed, and unchanged to the caller.

#### Edge Cases

1. [96-REQ-3.E1] IF a fact has no `fact_entities` links, THEN THE system SHALL
   skip that fact (it cannot be verified against the codebase).

2. [96-REQ-3.E2] IF a fact has no `commit_sha` but has entity links, THEN THE
   system SHALL only perform the file-existence check (not the change-ratio
   check).

### Requirement 4: Cross-Spec Fact Merging

**User Story:** As a knowledge system, I want to identify and consolidate
related facts across specs so that redundant knowledge is reduced and
cross-spec connections are made explicit.

#### Acceptance Criteria

1. [96-REQ-4.1] WHEN the cross-spec merging step runs, THE system SHALL find
   clusters of semantically similar active facts from different specs using
   embedding cosine similarity above a configurable threshold (default 0.85).

2. [96-REQ-4.2] WHEN a cluster of similar facts is found, THE system SHALL
   send the cluster to an LLM to classify the action as either "merge" or
   "link" AND return the classification and (if merge) the consolidated fact
   content.

3. [96-REQ-4.3] IF the LLM classifies a cluster as "merge," THEN THE system
   SHALL create a new consolidated fact with the LLM-generated content,
   category, and a confidence equal to the maximum confidence of the original
   facts AND supersede all original facts in the cluster by setting their
   `superseded_by` to the new fact's ID.

4. [96-REQ-4.4] IF the LLM classifies a cluster as "link," THEN THE system
   SHALL add causal edges between the facts in the cluster (connecting each
   fact to the others) without modifying the original facts.

#### Edge Cases

1. [96-REQ-4.E1] IF embedding generation fails for any fact in the similarity
   search, THEN THE system SHALL exclude that fact from clustering and
   continue.

2. [96-REQ-4.E2] IF the LLM call fails for a cluster, THEN THE system SHALL
   log a warning, skip that cluster, and continue with the remaining clusters.

### Requirement 5: Pattern Promotion

**User Story:** As a knowledge system, I want to detect recurring patterns
across specs and elevate them so that cross-cutting knowledge is explicitly
represented.

#### Acceptance Criteria

1. [96-REQ-5.1] WHEN the pattern promotion step runs, THE system SHALL
   identify groups of semantically similar active facts that appear across 3
   or more distinct spec names.

2. [96-REQ-5.2] WHEN a candidate pattern group is found, THE system SHALL
   send it to an LLM to confirm whether it represents a genuine recurring
   pattern AND return a synthesized pattern description if confirmed.

3. [96-REQ-5.3] IF the LLM confirms a pattern, THEN THE system SHALL create a
   new fact with category `pattern`, confidence 0.9, and the LLM-generated
   description AND add causal edges from each original fact to the new pattern
   fact.

#### Edge Cases

1. [96-REQ-5.E1] IF a candidate group contains facts that were already linked
   to an existing pattern fact (via causal edges), THEN THE system SHALL skip
   that group to avoid duplicate pattern facts.

### Requirement 6: Causal Chain Pruning

**User Story:** As a knowledge system, I want to identify and remove redundant
intermediate steps in causal chains so that the causal graph stays lean and
meaningful.

#### Acceptance Criteria

1. [96-REQ-6.1] WHEN the causal chain pruning step runs, THE system SHALL
   identify all causal chains A->B->C where a direct edge A->C also exists
   in `fact_causes`.

2. [96-REQ-6.2] WHEN a redundant chain is found, THE system SHALL send the
   three facts (A, B, C) to an LLM to evaluate whether B provides independent
   value as a causal intermediate.

3. [96-REQ-6.3] IF the LLM determines B is not meaningful, THEN THE system
   SHALL remove the edges A->B and B->C from `fact_causes` while preserving
   the direct edge A->C AND return the count of edges removed to the caller.

#### Edge Cases

1. [96-REQ-6.E1] IF the LLM call fails for a chain evaluation, THEN THE
   system SHALL preserve all existing edges (no pruning) and continue with
   the next chain.

### Requirement 7: Orchestrator Integration

**User Story:** As a user, I want consolidation to run automatically during
orchestration so that knowledge quality improves without manual intervention.

#### Acceptance Criteria

1. [96-REQ-7.1] WHEN the sync barrier sequence runs AND
   `completed_spec_names()` returns one or more newly completed specs, THE
   system SHALL invoke the consolidation pipeline for those specs.

2. [96-REQ-7.2] WHEN the orchestrator's end-of-run cleanup executes, THE
   system SHALL invoke the consolidation pipeline for all completed specs
   that were not yet consolidated during a prior sync barrier.

3. [96-REQ-7.3] WHILE the consolidation pipeline is executing, THE system
   SHALL hold exclusive write access to the knowledge DB (no concurrent
   session writes).

4. [96-REQ-7.4] THE system SHALL track LLM costs incurred by the consolidation
   pipeline separately from session costs AND emit a
   `consolidation.cost` audit event containing the consolidation-specific
   cost breakdown.

#### Edge Cases

1. [96-REQ-7.E1] IF the consolidation pipeline exceeds the run's remaining
   cost budget, THEN THE system SHALL abort the current step, return a partial
   `ConsolidationResult`, and allow the orchestrator to continue normally.

2. [96-REQ-7.E2] IF no specs have completed since the last consolidation pass,
   THEN THE system SHALL skip the consolidation pipeline entirely.
