# Requirements Document

## Introduction

This specification defines automated fact lifecycle management for the
agent-fox knowledge store. It adds three mechanisms to combat knowledge
staleness: embedding-based deduplication on ingestion, LLM-powered
contradiction detection, and age-based confidence decay with auto-supersession.
These mechanisms integrate into the existing knowledge harvest pipeline and
orchestrator end-of-run flow.

## Glossary

- **Active fact**: A fact in `memory_facts` where `superseded_by IS NULL`.
- **Supersession**: Marking a fact as replaced by setting its `superseded_by`
  column to another fact's UUID (or its own UUID for self-supersession).
- **Self-supersession**: Marking a fact as superseded by itself
  (`superseded_by = id`), used when no specific replacement exists (e.g.,
  decay expiration, compaction removal).
- **Cosine similarity**: A measure of angular distance between two embedding
  vectors, ranging from -1 to 1. Higher values indicate greater semantic
  similarity.
- **Dedup threshold**: The cosine similarity value above which two facts are
  considered near-duplicates (default: 0.92).
- **Contradiction**: Two facts about the same topic where the newer fact
  invalidates the older (e.g., "use API v1" vs. "use API v2"). Determined by
  LLM classification, not string or embedding comparison alone.
- **Candidate pair**: A (new fact, existing fact) tuple with cosine similarity
  above a configurable threshold, identified as worth evaluating for
  contradiction.
- **Effective confidence**: A fact's stored confidence modified by age-based
  decay. Used only during cleanup to determine auto-supersession eligibility.
- **Half-life**: The number of days after which a fact's effective confidence
  is halved (default: 90 days).
- **Decay floor**: The minimum effective confidence below which a fact is
  auto-superseded (default: 0.1).
- **Fact count threshold**: The number of active facts above which end-of-run
  cleanup runs age-based decay (default: 500).

## Requirements

### Requirement 1: Embedding-Based Deduplication on Ingestion

**User Story:** As the knowledge store, I want to detect and suppress
near-duplicate facts at ingestion time, so that the context window is not
wasted on semantically equivalent facts.

#### Acceptance Criteria

[90-REQ-1.1] WHEN a new fact is extracted and its embedding is computed, THE
system SHALL query active facts for cosine similarity against the new fact's
embedding and identify all existing facts with similarity above the configured
dedup threshold.

[90-REQ-1.2] WHEN a near-duplicate existing fact is identified (similarity
above dedup threshold), THE system SHALL supersede the older fact by setting
its `superseded_by` to the new fact's UUID, AND insert the new fact as active.

[90-REQ-1.3] WHEN multiple existing facts exceed the dedup threshold for a
single new fact, THE system SHALL supersede all of them with the new fact's
UUID.

[90-REQ-1.4] WHERE the dedup threshold is configurable, THE system SHALL
read it from `config.knowledge.dedup_similarity_threshold` with a default
of 0.92.

[90-REQ-1.5] WHEN deduplication supersedes one or more facts, THE system
SHALL log the count of superseded facts and their IDs at INFO level.

#### Edge Cases

[90-REQ-1.E1] IF the new fact has no embedding (embedding generation failed),
THEN THE system SHALL skip deduplication and insert the fact without
similarity checks.

[90-REQ-1.E2] IF no existing facts have embeddings, THEN THE system SHALL
skip deduplication and insert the new fact normally.

### Requirement 2: LLM-Powered Contradiction Detection

**User Story:** As the knowledge store, I want to detect when a new fact
contradicts an existing one, so that outdated knowledge is automatically
retired.

#### Acceptance Criteria

[90-REQ-2.1] WHEN new facts are extracted from a session transcript, THE
system SHALL identify candidate contradiction pairs by querying existing
active facts with cosine similarity above a configurable contradiction
candidate threshold (default: 0.8) against each new fact's embedding.

[90-REQ-2.2] WHEN candidate pairs are identified, THE system SHALL call an
LLM with both facts and a classification prompt, AND the LLM SHALL return a
structured JSON verdict: `{"contradicts": bool, "reason": str}`.

[90-REQ-2.3] WHEN the LLM verdict confirms a contradiction
(`contradicts: true`), THE system SHALL supersede the older fact by setting
its `superseded_by` to the new fact's UUID.

[90-REQ-2.4] WHEN the LLM verdict denies a contradiction
(`contradicts: false`), THE system SHALL take no action on the existing fact.

[90-REQ-2.5] THE system SHALL process contradiction candidates in batches,
sending at most 10 candidate pairs per LLM call to amortize API overhead.

[90-REQ-2.6] WHEN contradiction detection supersedes one or more facts, THE
system SHALL log each supersession with the reason from the LLM verdict at
INFO level.

[90-REQ-2.7] WHERE the contradiction candidate threshold is configurable, THE
system SHALL read it from
`config.knowledge.contradiction_similarity_threshold` with a default of 0.8.

[90-REQ-2.8] WHERE the model used for contradiction classification is
configurable, THE system SHALL read it from
`config.knowledge.contradiction_model` with a default of `"SIMPLE"`.

#### Edge Cases

[90-REQ-2.E1] IF the LLM call fails (API error, timeout, malformed response),
THEN THE system SHALL log a warning and skip contradiction detection for that
batch without blocking fact ingestion.

[90-REQ-2.E2] IF a new fact has no embedding, THEN THE system SHALL skip
contradiction detection for that fact.

[90-REQ-2.E3] IF the LLM response is not valid JSON or is missing the
`contradicts` field, THEN THE system SHALL treat it as a non-contradiction
(no supersession).

### Requirement 3: Age-Based Confidence Decay with Auto-Supersession

**User Story:** As the knowledge store, I want old facts to lose confidence
over time and eventually be retired, so that the knowledge base stays fresh
without manual intervention.

#### Acceptance Criteria

[90-REQ-3.1] WHEN cleanup runs, THE system SHALL compute each active fact's
effective confidence using the formula:
`effective = stored_confidence * (0.5 ^ (age_days / half_life_days))`.

[90-REQ-3.2] WHEN a fact's effective confidence falls below the configured
decay floor, THE system SHALL mark it as self-superseded
(`superseded_by = id`).

[90-REQ-3.3] WHERE the half-life is configurable, THE system SHALL read it
from `config.knowledge.decay_half_life_days` with a default of 90.

[90-REQ-3.4] WHERE the decay floor is configurable, THE system SHALL read it
from `config.knowledge.decay_floor` with a default of 0.1.

[90-REQ-3.5] WHEN decay auto-supersedes facts, THE system SHALL log the
count of expired facts at INFO level.

[90-REQ-3.6] THE system SHALL NOT modify the stored `confidence` column in
`memory_facts`. Effective confidence is computed on-the-fly during cleanup;
the original confidence is preserved for auditability.

#### Edge Cases

[90-REQ-3.E1] IF a fact has no `created_at` timestamp (NULL or unparseable),
THEN THE system SHALL skip decay for that fact and log a warning.

[90-REQ-3.E2] IF the computed age is zero or negative (fact created in the
future due to clock skew), THEN THE system SHALL treat the fact as having
zero decay (effective confidence equals stored confidence).

### Requirement 4: End-of-Run Cleanup Integration

**User Story:** As the orchestrator, I want fact lifecycle cleanup to run
automatically at the end of each orchestrator run, so that the knowledge
base is maintained without manual intervention.

#### Acceptance Criteria

[90-REQ-4.1] WHEN an orchestrator run completes (reaches COMPLETED status),
THE system SHALL run fact lifecycle cleanup as part of the end-of-run flow,
after knowledge harvesting and before the sync barrier.

[90-REQ-4.2] WHEN the active fact count exceeds the configured fact count
threshold, THE system SHALL run age-based decay and auto-supersession across
all active facts.

[90-REQ-4.3] WHERE the fact count threshold is configurable, THE system SHALL
read it from `config.knowledge.cleanup_fact_threshold` with a default of 500.

[90-REQ-4.4] WHERE end-of-run cleanup is independently disableable, THE
system SHALL read `config.knowledge.cleanup_enabled` (default: true) to
control whether cleanup runs.

[90-REQ-4.5] WHEN cleanup runs, THE system SHALL emit a `fact.cleanup` audit
event with payload containing: `facts_expired` (decay count),
`facts_deduped` (dedup count), `facts_contradicted` (contradiction count),
and `active_facts_remaining`.

[90-REQ-4.6] THE cleanup function SHALL return a summary dataclass containing
the counts from [90-REQ-4.5] to the caller for logging and reporting.

#### Edge Cases

[90-REQ-4.E1] IF cleanup is disabled via configuration, THEN THE system SHALL
skip all cleanup steps and log a DEBUG message.

[90-REQ-4.E2] IF the DuckDB connection is unavailable during cleanup, THEN
THE system SHALL log a warning and skip cleanup without blocking the
orchestrator run.

### Requirement 5: Dedup and Contradiction in Harvest Pipeline

**User Story:** As the knowledge harvest pipeline, I want to check new facts
against the existing knowledge base immediately after extraction, so that
duplicates and contradictions are caught before they accumulate.

#### Acceptance Criteria

[90-REQ-5.1] WHEN `extract_and_store_knowledge()` finishes extracting and
storing new facts, THE system SHALL run embedding-based deduplication
(Requirement 1) on the newly inserted facts against the existing knowledge
base.

[90-REQ-5.2] WHEN `extract_and_store_knowledge()` finishes deduplication, THE
system SHALL run contradiction detection (Requirement 2) on the surviving
new facts against the existing knowledge base.

[90-REQ-5.3] THE system SHALL run deduplication before contradiction detection,
so that duplicates are removed before spending LLM calls on contradiction
checks.

[90-REQ-5.4] WHEN deduplication or contradiction detection supersedes facts
during harvesting, THE system SHALL include the counts in the
`harvest.complete` audit event payload.

#### Edge Cases

[90-REQ-5.E1] IF all new facts are removed by deduplication, THEN THE system
SHALL skip contradiction detection and emit the `harvest.complete` event with
zero contradiction count.
