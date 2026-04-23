# Requirements Document

## Introduction

This specification removes knowledge system components that produced no
demonstrated value during real coding sessions. The remaining system retains
only review-findings carry-forward, operational telemetry, and infrastructure.

## Glossary

- **Gotcha**: A surprising or non-obvious finding extracted by LLM from a
  session transcript. Being removed by this spec.
- **Errata index**: A table mapping spec names to errata document file paths.
  Being removed by this spec.
- **Review finding**: An unresolved observation from a reviewer archetype
  (skeptic, oracle) persisted in the `review_findings` table. Being retained.
- **Verification result**: A per-requirement PASS/FAIL verdict from the
  verifier archetype. Being retained.
- **Causal link**: A `fact_causes` edge from a superseded record to its
  replacement. Write-only; being removed.
- **Supersession**: The process of marking old review/verification records
  with a `superseded_by` session ID when new records are inserted for the
  same spec and task group.
- **FoxKnowledgeProvider**: The concrete `KnowledgeProvider` implementation
  that orchestrates retrieval and ingestion.
- **KnowledgeProvider protocol**: The `typing.Protocol` interface defining
  `ingest()` and `retrieve()` methods.

## Requirements

### Requirement 1: Remove gotcha system

**User Story:** As a maintainer, I want to remove the gotcha extraction and
storage system, so that sessions stop paying for LLM calls that produce noise.

#### Acceptance Criteria

[116-REQ-1.1] WHEN the knowledge system is deployed, THE system SHALL NOT
contain the `gotcha_extraction.py` module.

[116-REQ-1.2] WHEN the knowledge system is deployed, THE system SHALL NOT
contain the `gotcha_store.py` module.

[116-REQ-1.3] WHEN `FoxKnowledgeProvider.ingest()` is called, THE system
SHALL perform no LLM calls and return immediately.

[116-REQ-1.4] WHEN `FoxKnowledgeProvider.retrieve()` is called, THE system
SHALL NOT query or return any `[GOTCHA]`-prefixed items.

#### Edge Cases

[116-REQ-1.E1] IF the `gotchas` table still exists in a database from a
prior migration, THEN THE system SHALL still function correctly (the table
is ignored, not queried).

### Requirement 2: Remove errata index

**User Story:** As a maintainer, I want to remove the errata index system,
so that dead code that was never wired into production is eliminated.

#### Acceptance Criteria

[116-REQ-2.1] WHEN the knowledge system is deployed, THE system SHALL NOT
contain the `errata_store.py` module.

[116-REQ-2.2] WHEN `FoxKnowledgeProvider.retrieve()` is called, THE system
SHALL NOT query or return any `[ERRATA]`-prefixed items.

### Requirement 3: Remove blocking history

**User Story:** As a maintainer, I want to remove the blocking history and
threshold learning system, so that broken recording code and unreachable
learning logic are eliminated.

#### Acceptance Criteria

[116-REQ-3.1] WHEN the knowledge system is deployed, THE system SHALL NOT
contain the `blocking_history.py` module.

[116-REQ-3.2] WHEN a security blocking decision occurs, THE system SHALL NOT
attempt to record it in a `blocking_history` table.

#### Edge Cases

[116-REQ-3.E1] IF the engine's `result_handler` previously imported
`blocking_history`, THEN THE system SHALL remove that import and the
`record_blocking_decision` call.

### Requirement 4: Drop unused database tables

**User Story:** As a maintainer, I want unused tables removed from the
database schema, so that the schema accurately reflects live components.

#### Acceptance Criteria

[116-REQ-4.1] WHEN schema migration v18 is applied, THE system SHALL DROP
the following tables if they exist: `gotchas`, `errata_index`,
`blocking_history`, `sleep_artifacts`, `memory_facts`, `memory_embeddings`,
`entity_graph`, `entity_edges`, `fact_entities`, `fact_causes`.

[116-REQ-4.2] WHEN schema migration v18 is applied, THE system SHALL NOT
drop or alter the following tables: `review_findings`,
`verification_results`, `drift_findings`, `session_outcomes`, `tool_calls`,
`tool_errors`, `audit_events`, `plan_nodes`, `plan_edges`, `plan_meta`,
`runs`, `schema_version`.

[116-REQ-4.3] WHEN migration v18 completes, THE system SHALL record the
migration in `schema_version` with version 18 and a description indicating
the tables were dropped.

#### Edge Cases

[116-REQ-4.E1] IF a table listed for removal does not exist (e.g., fresh
database or already dropped), THEN THE migration SHALL proceed without error
(use `DROP TABLE IF EXISTS`).

### Requirement 5: Remove causal links from review store

**User Story:** As a maintainer, I want the write-only causal link insertion
removed from review_store, so that the supersession logic is simplified to
use only the `superseded_by` column.

#### Acceptance Criteria

[116-REQ-5.1] WHEN review findings are superseded, THE system SHALL mark old
records via the `superseded_by` column but SHALL NOT insert rows into
`fact_causes`.

[116-REQ-5.2] WHEN the `_insert_causal_links` function is removed, THE
system SHALL still correctly supersede old review findings, verification
results, and drift findings.

### Requirement 6: Simplify FoxKnowledgeProvider

**User Story:** As a maintainer, I want FoxKnowledgeProvider simplified to
only retrieve review findings, so that the provider reflects what actually
works.

#### Acceptance Criteria

[116-REQ-6.1] WHEN `FoxKnowledgeProvider.retrieve()` is called with a
`spec_name`, THE system SHALL query active review findings for that spec
AND return them as `[REVIEW]`-prefixed strings, filtered to `critical` and
`major` severity.

[116-REQ-6.2] WHEN `FoxKnowledgeProvider.retrieve()` is called, THE system
SHALL return an empty list if no active critical/major findings exist for
the spec.

[116-REQ-6.3] THE `FoxKnowledgeProvider` class SHALL still satisfy the
`KnowledgeProvider` protocol (both `ingest()` and `retrieve()` methods
present with correct signatures).

#### Edge Cases

[116-REQ-6.E1] IF the `review_findings` table does not exist, THEN THE
system SHALL return an empty list without raising an exception.

### Requirement 7: Simplify configuration

**User Story:** As a maintainer, I want dead configuration fields removed,
so that the config schema matches available features.

#### Acceptance Criteria

[116-REQ-7.1] THE `KnowledgeProviderConfig` class SHALL NOT contain a
`gotcha_ttl_days` field.

[116-REQ-7.2] THE `KnowledgeProviderConfig` class SHALL NOT contain a
`model_tier` field.

[116-REQ-7.3] THE `KnowledgeProviderConfig` class SHALL retain the
`max_items` field with a default value of 10.

#### Edge Cases

[116-REQ-7.E1] IF an existing `config.toml` contains `gotcha_ttl_days` or
`model_tier` fields, THEN THE system SHALL ignore them without error
(Pydantic `model_config` with `extra = "ignore"` or equivalent).

### Requirement 8: Remove dead imports and references

**User Story:** As a maintainer, I want all references to removed components
cleaned up, so that the codebase has no broken or dead imports.

#### Acceptance Criteria

[116-REQ-8.1] THE system SHALL have no Python imports referencing
`gotcha_extraction`, `gotcha_store`, `errata_store`, or `blocking_history`
modules in any production code.

[116-REQ-8.2] THE `engine/reset.py` table list SHALL NOT include
`blocking_history`, `gotchas`, `errata_index`, `sleep_artifacts`,
`memory_facts`, `memory_embeddings`, `entity_graph`, `entity_edges`,
`fact_entities`, or `fact_causes`.

[116-REQ-8.3] THE `knowledge/__init__.py` SHALL export only
`KnowledgeProvider` and `NoOpKnowledgeProvider`.
