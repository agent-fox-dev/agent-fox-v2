# Requirements Document

## Introduction

This specification defines the requirements for decoupling the knowledge system
from the agent-fox engine and nightshift modules. Low-value knowledge components
are removed. High-value operational components are retained. A KnowledgeProvider
protocol defines the clean boundary between the engine and any knowledge
implementation.

## Glossary

- **KnowledgeProvider**: A `typing.Protocol` defining the interface between the
  engine and a knowledge implementation. Has `ingest()` and `retrieve()` methods.
- **NoOpKnowledgeProvider**: An implementation of KnowledgeProvider that does
  nothing — `ingest()` is a no-op, `retrieve()` returns an empty list.
- **Engine**: The orchestrator module (`agent_fox/engine/`) that schedules and
  runs coding, review, and verification sessions.
- **Nightshift**: The daemon module (`agent_fox/nightshift/`) that runs
  background maintenance tasks.
- **SessionSink**: Existing protocol for recording session events (outcomes,
  tool calls, audit events). Not part of the knowledge system being removed.
- **Review store**: The `review_findings` and `verification_results` tables and
  their CRUD operations. High-value, retained.
- **Fact**: The old knowledge system's data unit (`knowledge/facts.py`). Being
  removed along with the pipeline that produces and consumes them.
- **AdaptiveRetriever**: The old 4-signal RRF retrieval engine. Being removed.
- **Sleep compute**: The old pre-computation pipeline that ran during idle
  periods. Being removed.

## Requirements

### Requirement 1: KnowledgeProvider Protocol Definition

**User Story:** As a developer extending agent-fox, I want a clear protocol for
knowledge ingestion and retrieval, so that I can implement custom knowledge
providers without modifying engine code.

#### Acceptance Criteria

[114-REQ-1.1] THE system SHALL define a `KnowledgeProvider` protocol in
`agent_fox/knowledge/provider.py` with an `ingest(session_id: str, spec_name: str, context: dict[str, Any]) -> None` method and a `retrieve(spec_name: str, task_description: str) -> list[str]` method.

[114-REQ-1.2] THE `KnowledgeProvider` protocol SHALL be a `typing.Protocol`
class decorated with `@runtime_checkable`.

[114-REQ-1.3] THE `retrieve()` method SHALL return a list of strings, where
each string is a formatted text block ready for prompt injection.

[114-REQ-1.4] THE `ingest()` method SHALL accept a context dictionary
containing session metadata (touched files, commit SHA, session outcome status)
and return None.

#### Edge Cases

[114-REQ-1.E1] IF a class implements only one of the two protocol methods,
THEN `isinstance(obj, KnowledgeProvider)` SHALL return `False`.

### Requirement 2: NoOpKnowledgeProvider Implementation

**User Story:** As an operator, I want the engine to function correctly without
any knowledge system, so that removing the old pipeline does not break execution.

#### Acceptance Criteria

[114-REQ-2.1] THE `NoOpKnowledgeProvider` SHALL implement the
`KnowledgeProvider` protocol.

[114-REQ-2.2] WHEN `NoOpKnowledgeProvider.ingest()` is called, THE system
SHALL return immediately without performing any action.

[114-REQ-2.3] WHEN `NoOpKnowledgeProvider.retrieve()` is called, THE system
SHALL return an empty list.

[114-REQ-2.4] THE engine SHALL use `NoOpKnowledgeProvider` as the default
provider when no other provider is configured.

#### Edge Cases

[114-REQ-2.E1] WHEN `NoOpKnowledgeProvider.retrieve()` is called with any
combination of arguments, THE system SHALL return an empty list without raising
exceptions.

### Requirement 3: Engine Integration — Retrieval Point

**User Story:** As a coder agent, I want knowledge context injected at session
start through the provider protocol, so that knowledge retrieval is decoupled
from the retrieval implementation.

#### Acceptance Criteria

[114-REQ-3.1] WHEN a session is being prepared, THE engine SHALL call
`KnowledgeProvider.retrieve(spec_name, task_description)` AND include the
returned strings in the session context.

[114-REQ-3.2] THE engine SHALL NOT import `AdaptiveRetriever`,
`EmbeddingGenerator`, `VectorSearch`, `RetrievalConfig`, or any retrieval
module directly.

[114-REQ-3.3] WHEN the provider returns an empty list, THE engine SHALL
proceed with session preparation without adding knowledge context.

#### Edge Cases

[114-REQ-3.E1] IF `KnowledgeProvider.retrieve()` raises an exception, THEN
THE engine SHALL log the error at WARNING level, return an empty knowledge
context, and proceed with session preparation.

### Requirement 4: Engine Integration — Ingestion Point

**User Story:** As a system operator, I want knowledge ingestion to happen at a
single well-defined point after each session, so that the engine does not
scatter knowledge calls throughout session lifecycle.

#### Acceptance Criteria

[114-REQ-4.1] WHEN a session completes, THE engine SHALL call
`KnowledgeProvider.ingest(session_id, spec_name, context)` exactly once,
where `context` includes at minimum `touched_files`, `commit_sha`, and
`session_status`.

[114-REQ-4.2] THE engine SHALL NOT import `extract_session_facts`,
`extract_tool_calls`, `store_causal_links`, `dedup_new_facts`,
`detect_contradictions`, `extract_and_store_knowledge`,
`run_background_ingestion`, or any extraction/lifecycle module directly.

[114-REQ-4.3] THE `knowledge_harvest.py` file SHALL be deleted entirely.

#### Edge Cases

[114-REQ-4.E1] IF `KnowledgeProvider.ingest()` raises an exception, THEN THE
engine SHALL log the error at WARNING level and continue without retrying.

### Requirement 5: Barrier Cleanup

**User Story:** As a developer, I want sync barriers to not call removed
knowledge components, so that barrier execution is fast and error-free.

#### Acceptance Criteria

[114-REQ-5.1] THE `barrier.py` file SHALL NOT import or call
`run_consolidation`, `compact`, `SleepComputer`, `SleepContext`,
`BundleBuilder`, `ContextRewriter`, `run_cleanup`, or `render_summary`.

[114-REQ-5.2] WHEN a sync barrier runs, THE system SHALL still execute its
operational steps (worktree verification, develop sync, hot-load, barrier
callback, config reload) but SHALL NOT execute consolidation, compaction,
lifecycle cleanup, rendering, or sleep compute steps.

#### Edge Cases

[114-REQ-5.E1] IF a barrier is triggered with an existing database containing
old knowledge tables (memory_facts, entity_graph, etc.), THEN THE system SHALL
not attempt to read from or write to those tables.

### Requirement 6: Nightshift Cleanup

**User Story:** As a developer, I want the nightshift daemon to not depend on
removed knowledge components, so that background processes run without dead
code paths.

#### Acceptance Criteria

[114-REQ-6.1] THE nightshift module SHALL NOT import `EmbeddingGenerator`
from `agent_fox.knowledge.embeddings`.

[114-REQ-6.2] THE nightshift module SHALL NOT import `SleepComputer`,
`SleepContext`, `BundleBuilder`, or `ContextRewriter` from sleep compute
modules.

[114-REQ-6.3] THE nightshift `streams.py` SHALL NOT include a sleep compute
work stream.

[114-REQ-6.4] THE nightshift files `ignore_ingest.py`, `dedup.py`, and
`ignore_filter.py` SHALL NOT import from removed knowledge modules.

[114-REQ-6.5] THE `ingest_ignore_signals()` function in `ignore_ingest.py`
SHALL be converted to a no-op (return immediately without storing facts),
since its `Fact`-based and `_write_fact`-based storage mechanism is removed
with the knowledge pipeline.

#### Edge Cases

[114-REQ-6.E1] IF the nightshift daemon is started with an existing database
containing old sleep artifacts, THEN THE system SHALL not attempt to read from
or write to the `sleep_artifacts` table.

### Requirement 7: Module Deletion

**User Story:** As a developer, I want removed knowledge modules deleted (not
stubbed), so that dead code does not accumulate.

#### Acceptance Criteria

[114-REQ-7.1] THE following files SHALL be deleted from `agent_fox/knowledge/`:
`extraction.py`, `embeddings.py`, `search.py`, `retrieval.py`, `causal.py`,
`lifecycle.py`, `contradiction.py`, `consolidation.py`, `compaction.py`,
`entity_linker.py`, `entity_query.py`, `entity_store.py`, `entities.py`,
`static_analysis.py`, `git_mining.py`, `doc_mining.py`, `sleep_compute.py`,
`code_analysis.py`, `onboard.py`, `project_model.py`, `query_oracle.py`,
`query_patterns.py`, `query_temporal.py`, `rendering.py`, `store.py`,
`ingest.py`, `facts.py`.

[114-REQ-7.2] THE `agent_fox/knowledge/lang/` directory SHALL be deleted
entirely, including all 17 language analyzer files.

[114-REQ-7.3] THE `agent_fox/knowledge/sleep_tasks/` directory SHALL be deleted
entirely.

[114-REQ-7.4] THE `agent_fox/engine/knowledge_harvest.py` file SHALL be
deleted.

[114-REQ-7.5] WHEN all deletions are complete, THE system SHALL have zero
import errors when running `python -c "import agent_fox"`.

#### Edge Cases

[114-REQ-7.E1] IF any test file imports a deleted module, THEN THE test file
SHALL be updated to remove the import or deleted if the test exclusively tests
removed functionality.

### Requirement 8: Configuration Cleanup

**User Story:** As an operator, I want the configuration to not reference
removed components, so that config validation does not fail on missing fields.

#### Acceptance Criteria

[114-REQ-8.1] THE `KnowledgeConfig` class SHALL remove fields related to
removed components: `embedding_model`, `embedding_dimensions`, `ask_top_k`,
`ask_synthesis_model`, `dedup_similarity_threshold`,
`contradiction_similarity_threshold`, `contradiction_model`,
`decay_half_life_days`, `decay_floor`, `cleanup_fact_threshold`,
`cleanup_enabled`, `confidence_threshold`, `fact_cache_enabled`.

[114-REQ-8.2] THE `RetrievalConfig` class SHALL be deleted entirely.

[114-REQ-8.3] THE `SleepConfig` class SHALL be deleted entirely.

[114-REQ-8.4] THE `KnowledgeConfig` class SHALL retain the `store_path` field.

[114-REQ-8.5] WHEN a configuration file contains fields for removed components,
THE system SHALL ignore those fields without raising validation errors
(Pydantic `extra="ignore"` behavior).

### Requirement 9: CLI Cleanup

**User Story:** As a developer, I want CLI commands that depend on removed
knowledge components to be updated or removed, so that the CLI does not break.

#### Acceptance Criteria

[114-REQ-9.1] THE `cli/onboard.py` file SHALL be deleted AND its import and
command registration SHALL be removed from `cli/app.py`, since the onboarding
pipeline is being deleted.

[114-REQ-9.2] THE `cli/nightshift.py` SHALL NOT import `EmbeddingGenerator`
from removed modules.

[114-REQ-9.3] THE `cli/status.py` SHALL NOT import from `project_model` or
`store` modules.

[114-REQ-9.4] THE `cli/plan.py` SHALL continue to function, updating its
import to use `db.open_knowledge_store` without depending on removed modules.

#### Edge Cases

[114-REQ-9.E1] IF a CLI command is invoked that previously depended on a
removed module, THEN THE system SHALL either function without that dependency
or display a clear error message indicating the feature was removed.

### Requirement 10: Test Suite Integrity

**User Story:** As a developer, I want the test suite to pass after all
removals, so that the decoupling does not introduce regressions.

#### Acceptance Criteria

[114-REQ-10.1] WHEN `make check` is run after all changes, THE system SHALL
pass all remaining tests with zero failures.

[114-REQ-10.2] THE system SHALL include unit tests for the `KnowledgeProvider`
protocol verifying that `NoOpKnowledgeProvider` satisfies the protocol.

[114-REQ-10.3] THE system SHALL include a test verifying that engine modules do
not import any deleted knowledge module.

[114-REQ-10.4] WHEN tests that exclusively test removed functionality are
identified, THE system SHALL delete those test files rather than leaving them
as dead code.
