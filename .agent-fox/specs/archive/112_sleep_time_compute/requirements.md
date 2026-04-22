> **SUPERSEDED** by spec 114_knowledge_decoupling

# Requirements Document

## Introduction

This document specifies the sleep-time compute pipeline for the agent-fox
knowledge system. The pipeline runs during idle periods (sync barriers and
nightshift daemon) to pre-process knowledge facts into enriched artifacts
that make future retrieval faster and richer. The architecture is extensible
via a `SleepTask` protocol.

## Glossary

| Term | Definition |
|------|-----------|
| **Sleep-time compute** | Pre-computation performed during idle periods (between active sessions) to enrich the knowledge base for future retrieval. Contrasted with test-time compute (at query time). |
| **Sleep task** | A pluggable unit of pre-computation that implements the `SleepTask` protocol. Each task produces artifacts stored in the `sleep_artifacts` table. |
| **Sleep artifact** | A pre-computed output stored in the database, produced by a sleep task. Has a scope key, content, content hash for staleness detection, and metadata. |
| **Context block** | A sleep artifact produced by the context re-representation task: a structured narrative summary of facts in a directory cluster. |
| **Retrieval bundle** | A sleep artifact produced by the bundle builder task: cached pre-scored fact lists for keyword and causal signals for a specific spec. |
| **Scope key** | A string that identifies the scope of a sleep artifact (e.g., `dir:agent_fox/knowledge` for a context block, `spec:01_core_foundation` for a retrieval bundle). |
| **Content hash** | A SHA-256 hash of the inputs that produced an artifact. Used for staleness detection: if the current hash differs from the stored hash, the artifact is stale. |
| **SleepComputer** | The orchestrator that runs registered sleep tasks in sequence, managing budgets and error isolation. |
| **SleepContext** | A bundle of resources (DB connection, repo root, model name, embedder, budget, sink dispatcher) passed to each sleep task's `run()` method. |

## Requirements

### Requirement 1: Sleep Task Protocol

**User Story:** As a developer extending the knowledge system, I want a
well-defined protocol for sleep-time pre-computation tasks, so that I can add
new pre-computation strategies without modifying the orchestrator.

#### Acceptance Criteria

1. [112-REQ-1.1] THE `SleepTask` protocol SHALL define a `name` property
   that returns a unique string identifier for the task.

2. [112-REQ-1.2] THE `SleepTask` protocol SHALL define an async `run` method
   that accepts a `SleepContext` and returns a `SleepTaskResult` containing
   the count of artifacts created, artifacts refreshed, artifacts unchanged,
   and the LLM cost incurred.

3. [112-REQ-1.3] THE `SleepTask` protocol SHALL define a `stale_scopes`
   method that accepts a DuckDB connection and returns a list of scope key
   strings whose artifacts need regeneration.

4. [112-REQ-1.4] THE `SleepContext` dataclass SHALL bundle: a DuckDB
   connection, repo root path, model name string, optional
   `EmbeddingGenerator`, remaining budget as a float, and optional
   `SinkDispatcher`.

5. [112-REQ-1.5] THE `SleepTaskResult` dataclass SHALL contain: `created`
   count (int), `refreshed` count (int), `unchanged` count (int), and
   `llm_cost` (float).

#### Edge Cases

1. [112-REQ-1.E1] IF a class implements `SleepTask` but its `run` method is
   not async, THEN the type checker SHALL flag the incompatibility at
   development time (enforced via `Protocol` typing, not runtime check).

### Requirement 2: Sleep Computer Orchestrator

**User Story:** As the knowledge system operator, I want a central orchestrator
that runs all registered sleep tasks with budget control and error isolation,
so that one failing task does not block others.

#### Acceptance Criteria

1. [112-REQ-2.1] WHEN `SleepComputer.run()` is called, THE system SHALL
   execute each registered sleep task in registration order, passing a
   `SleepContext` with the remaining budget decremented by prior tasks' costs.

2. [112-REQ-2.2] THE `SleepComputer.run()` method SHALL return a
   `SleepComputeResult` containing: a dict mapping task name to its
   `SleepTaskResult`, total LLM cost across all tasks, and a list of error
   strings.

3. [112-REQ-2.3] IF a sleep task raises an exception during `run()`, THEN
   THE system SHALL log the error, record it in the result's error list, and
   continue to the next task.

4. [112-REQ-2.4] IF the remaining budget drops to zero or below before a
   task begins, THEN THE system SHALL skip that task and record a
   `"budget_exhausted"` entry in the error list.

5. [112-REQ-2.5] WHEN `SleepComputer.run()` completes, THE system SHALL
   emit an audit event of type `SLEEP_COMPUTE_COMPLETE` with the total cost
   and per-task result counts.

#### Edge Cases

1. [112-REQ-2.E1] IF no sleep tasks are registered, THEN `SleepComputer.run()`
   SHALL return an empty result with zero cost and no errors.

2. [112-REQ-2.E2] IF all registered tasks are skipped due to budget
   exhaustion, THEN THE result SHALL contain a `"budget_exhausted"` entry for
   each skipped task and a total cost of zero.

### Requirement 3: Context Re-representation Task

**User Story:** As a session agent, I want pre-synthesized module-level
summaries in my retrieval context, so that I understand cross-fact
relationships without needing to infer them from individual facts.

#### Acceptance Criteria

1. [112-REQ-3.1] WHEN the context re-representation task runs, THE system
   SHALL query active (non-superseded) facts that have entity links, group
   them by the parent directory of their linked files, and identify clusters
   with 3 or more facts.

2. [112-REQ-3.2] FOR EACH qualifying directory cluster, THE system SHALL
   compute a content hash (SHA-256 of sorted fact IDs concatenated with their
   confidence values) and compare it to the stored hash for that scope key.

3. [112-REQ-3.3] WHEN a cluster's content hash differs from its stored
   artifact's hash (or no artifact exists), THE system SHALL call the LLM
   (STANDARD model tier) with the cluster's fact contents and a prompt
   requesting a structured narrative summary, and store the result as a sleep
   artifact with `task_name = "context_rewriter"` and `scope_key =
   "dir:<directory_path>"`.

4. [112-REQ-3.4] THE generated context block SHALL NOT exceed 2000 characters.
   IF the LLM output exceeds 2000 characters, THEN THE system SHALL truncate
   it at the last complete sentence within the limit.

5. [112-REQ-3.5] WHEN a cluster's content hash matches its stored artifact's
   hash, THE system SHALL skip regeneration and count the artifact as
   unchanged, returning it in the `SleepTaskResult`.

6. [112-REQ-3.6] THE context re-representation task SHALL store the directory
   path, fact count, and fact IDs in the artifact's `metadata_json` field.

#### Edge Cases

1. [112-REQ-3.E1] IF a fact is linked to files in multiple directories, THEN
   THE system SHALL include it in every qualifying cluster that contains at
   least one of its linked files.

2. [112-REQ-3.E2] IF no directory clusters have 3 or more facts, THEN THE
   task SHALL return a result with zero created/refreshed artifacts and no
   errors.

3. [112-REQ-3.E3] IF the LLM call fails for a cluster, THEN THE system SHALL
   log a warning, skip that cluster, and continue to the next cluster.

### Requirement 4: Retrieval Bundle Task

**User Story:** As the retrieval system, I want pre-computed keyword and causal
signal results for each spec, so that I can skip those signal computations at
query time when the fact base hasn't changed.

#### Acceptance Criteria

1. [112-REQ-4.1] WHEN the retrieval bundle task runs, THE system SHALL
   identify all specs that have active (non-superseded) facts in the
   `memory_facts` table.

2. [112-REQ-4.2] FOR EACH spec with active facts, THE system SHALL compute a
   content hash (SHA-256 of sorted fact IDs concatenated with their confidence
   values for that spec) and compare it to the stored hash for scope key
   `"spec:<spec_name>"`.

3. [112-REQ-4.3] WHEN a spec's content hash differs from its stored bundle's
   hash (or no bundle exists), THE system SHALL compute the keyword signal
   (via `_keyword_signal`) and causal signal (via `_causal_signal`) for that
   spec, serialize the resulting `ScoredFact` lists to JSON, and store the
   result as a sleep artifact with `task_name = "bundle_builder"` and
   `scope_key = "spec:<spec_name>"`.

4. [112-REQ-4.4] WHEN a spec's content hash matches its stored bundle's hash,
   THE system SHALL skip recomputation and count the bundle as unchanged.

5. [112-REQ-4.5] THE retrieval bundle task SHALL store the spec name, fact
   count, and signal sizes (keyword count, causal count) in the artifact's
   `metadata_json` field.

6. [112-REQ-4.6] THE retrieval bundle task SHALL NOT require LLM calls. It
   SHALL report `llm_cost = 0.0` in its result.

#### Edge Cases

1. [112-REQ-4.E1] IF a spec has zero active facts, THEN THE system SHALL
   skip that spec and not create a bundle for it.

2. [112-REQ-4.E2] IF the keyword or causal signal computation raises an
   exception for a spec, THEN THE system SHALL log a warning, skip that
   spec, and continue to the next.

### Requirement 5: Retriever Integration

**User Story:** As a session agent, I want the retriever to use pre-computed
sleep artifacts when available, so that retrieval is faster and context is
richer without changing my interaction with the retriever.

#### Acceptance Criteria

1. [112-REQ-5.1] WHEN `AdaptiveRetriever.retrieve()` is called, THE system
   SHALL query `sleep_artifacts` for valid (non-superseded) context blocks
   whose scope keys match directories containing any of the `touched_files`,
   and prepend their content as a `## Module Context` preamble before the
   existing `## Knowledge Context` section.

2. [112-REQ-5.2] THE context preamble SHALL be subject to the retrieval
   `token_budget`: the total length of preamble plus knowledge context SHALL
   NOT exceed `token_budget`. IF the preamble alone exceeds 30% of
   `token_budget`, THEN THE system SHALL truncate it to 30% and include only
   the highest-relevance blocks (most touched files in the cluster).

3. [112-REQ-5.3] WHEN `AdaptiveRetriever.retrieve()` is called AND a valid
   retrieval bundle exists for the requested `spec_name` (matching content
   hash), THE system SHALL use the cached keyword and causal signal results
   from the bundle instead of recomputing them.

4. [112-REQ-5.4] WHEN no valid retrieval bundle exists for the requested
   `spec_name`, THE system SHALL fall back to live computation of keyword and
   causal signals (existing behavior, no degradation).

5. [112-REQ-5.5] THE `RetrievalResult` SHALL include a `sleep_hit` boolean
   field indicating whether pre-computed artifacts were used, and a
   `sleep_artifact_count` integer field with the number of artifacts consumed.

#### Edge Cases

1. [112-REQ-5.E1] IF `sleep_artifacts` table does not exist (schema not yet
   migrated), THEN THE retriever SHALL fall back to live computation with no
   error.

2. [112-REQ-5.E2] IF all context blocks are stale (superseded), THEN THE
   retriever SHALL skip the preamble and use only the standard knowledge
   context.

### Requirement 6: Barrier and Nightshift Integration

**User Story:** As the system operator, I want sleep compute to run
automatically during sync barriers and nightshift idle periods, so that
artifacts stay fresh without manual intervention.

#### Acceptance Criteria

1. [112-REQ-6.1] WHEN a sync barrier runs, THE system SHALL execute
   `SleepComputer.run()` after compaction and before memory summary rendering,
   passing the barrier's knowledge DB connection and a budget derived from the
   knowledge config.

2. [112-REQ-6.2] THE nightshift daemon SHALL include a `SleepComputeStream`
   work stream that implements the `WorkStream` protocol, with a configurable
   interval (default 1800 seconds / 30 minutes).

3. [112-REQ-6.3] WHEN `SleepComputeStream.run_once()` executes, THE system
   SHALL open a knowledge DB connection, instantiate a `SleepComputer` with
   the configured tasks, run it, and close the connection.

4. [112-REQ-6.4] THE `SleepComputeStream` SHALL respect the nightshift
   `SharedBudget`: it SHALL add its LLM cost to the shared budget after each
   run and skip execution if the budget is already exceeded.

#### Edge Cases

1. [112-REQ-6.E1] IF the knowledge DB connection is unavailable at barrier
   time, THEN THE system SHALL log a warning and skip sleep compute without
   blocking the barrier sequence.

2. [112-REQ-6.E2] IF `SleepComputeStream.run_once()` raises an exception,
   THEN THE nightshift daemon SHALL log the error and continue to the next
   cycle (standard work stream error handling).

### Requirement 7: Configuration

**User Story:** As a project maintainer, I want to configure sleep compute
behavior (enable/disable, budget, per-task settings), so that I can control
costs and tailor behavior to my project's needs.

#### Acceptance Criteria

1. [112-REQ-7.1] THE configuration system SHALL support a `[knowledge.sleep]`
   section in `config.toml` with the following fields: `enabled` (bool,
   default `true`), `max_cost` (float, default `1.0`), `nightshift_interval`
   (int seconds, default `1800`), `context_rewriter_enabled` (bool, default
   `true`), `bundle_builder_enabled` (bool, default `true`).

2. [112-REQ-7.2] WHEN `enabled` is `false`, THE system SHALL skip sleep
   compute at barriers and disable the `SleepComputeStream` in the nightshift
   daemon.

3. [112-REQ-7.3] THE `max_cost` field SHALL cap the total LLM cost per sleep
   compute invocation. WHEN the cap is reached, remaining tasks SHALL be
   skipped.

4. [112-REQ-7.4] WHEN a per-task enabled flag is `false`, THE `SleepComputer`
   SHALL skip that task during execution.

#### Edge Cases

1. [112-REQ-7.E1] IF the `[knowledge.sleep]` section is absent from
   `config.toml`, THEN THE system SHALL use default values for all fields.

### Requirement 8: Storage Schema

**User Story:** As the knowledge system, I want a unified storage table for
sleep artifacts with staleness tracking, so that all sleep tasks can persist
their outputs without per-task schema changes.

#### Acceptance Criteria

1. [112-REQ-8.1] THE system SHALL create a `sleep_artifacts` table with
   columns: `id` (UUID, primary key), `task_name` (VARCHAR), `scope_key`
   (VARCHAR), `content` (TEXT), `metadata_json` (TEXT), `content_hash`
   (VARCHAR), `created_at` (TIMESTAMP), `superseded_at` (TIMESTAMP, nullable).

2. [112-REQ-8.2] THE system SHALL enforce a unique constraint on
   `(task_name, scope_key)` for rows where `superseded_at IS NULL`, ensuring
   at most one active artifact per task-scope combination.

3. [112-REQ-8.3] WHEN a sleep task produces a new artifact for an existing
   task-scope combination, THE system SHALL set `superseded_at` on the old
   row to the current timestamp before inserting the new row.

4. [112-REQ-8.4] THE schema migration SHALL be added as the next version in
   the `schema_version` table, following the existing migration pattern in
   `db.py`.

#### Edge Cases

1. [112-REQ-8.E1] IF the `sleep_artifacts` table already exists when the
   migration runs, THEN THE migration SHALL be a no-op (idempotent).
