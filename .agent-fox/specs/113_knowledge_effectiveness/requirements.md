# Requirements Document

## Introduction

The knowledge system captures, stores, and retrieves facts from coding sessions
to improve subsequent sessions. This spec addresses six effectiveness failures
identified during a production evaluation: transcript input mismatch, git commit
noise, dead entity signal, unused audit reports, weak compaction, and missing
cold-start handling.

## Glossary

- **Fact**: A discrete piece of knowledge stored in `memory_facts` with content,
  category, confidence, and optional embeddings.
- **Transcript**: The full sequence of assistant messages produced during a
  coding session, as recorded by `AgentTraceSink` in the agent trace JSONL file.
- **Session Summary**: A 1-3 sentence description written by the coding agent to
  `.agent-fox/session-summary.json` at session end. Distinct from the transcript.
- **Entity Signal**: One of four retrieval signals in `AdaptiveRetriever` that
  uses the entity graph to find facts related to code files.
- **Touched Files**: The list of file paths modified by a coding session,
  available in `session_outcomes.touched_path` after harvest.
- **Audit Report**: A markdown document written by the audit-review archetype to
  `.agent-fox/audit/`, containing structured assessment of coder output.
- **Cold Start**: The state where no facts exist for the current spec and no
  global facts exceed the confidence threshold.
- **Compaction**: The process of deduplicating, superseding, and pruning facts
  to keep the knowledge store concise and high-signal.
- **AdaptiveRetriever**: The unified retrieval class that fuses keyword, vector,
  entity, and causal signals via weighted Reciprocal Rank Fusion.

## Requirements

### Requirement 1: Full Transcript Knowledge Extraction

**User Story:** As the orchestrator, I want knowledge extraction to receive the
full LLM conversation transcript so that actionable facts can be extracted from
sessions that produce substantive dialogue.

#### Acceptance Criteria

[113-REQ-1.1] WHEN a coder session completes successfully, THE system SHALL
reconstruct the full conversation transcript from the agent trace JSONL events
for that session's `node_id` AND pass it to `extract_and_store_knowledge()` as
the `transcript` parameter.

[113-REQ-1.2] WHEN the reconstructed transcript exceeds the minimum character
threshold, THE system SHALL invoke LLM-based fact extraction AND return the
list of extracted facts to the caller for storage.

[113-REQ-1.3] THE system SHALL continue to use the session summary from
`session-summary.json` for the session log message AND for the
`_build_fallback_input` path when trace events are unavailable.

#### Edge Cases

[113-REQ-1.E1] IF the agent trace JSONL file does not exist or cannot be read,
THEN THE system SHALL fall back to `_build_fallback_input` (commit diff +
metadata) as the transcript source AND log a warning.

[113-REQ-1.E2] IF the reconstructed transcript contains zero assistant messages
for the given `node_id`, THEN THE system SHALL skip extraction AND log a debug
message.

### Requirement 2: LLM-Powered Git Commit Knowledge Extraction

**User Story:** As the knowledge system, I want to extract structured knowledge
from git commits rather than storing raw messages, so that the fact store
contains high-signal decisions and patterns instead of boilerplate.

#### Acceptance Criteria

[113-REQ-2.1] WHEN ingesting git commits, THE system SHALL batch commit messages
(up to 20 per batch) and call an LLM to extract structured facts (decisions,
patterns, gotchas, conventions) AND return the extracted facts with appropriate
categories and confidence scores.

[113-REQ-2.2] WHEN the LLM extraction yields zero facts from a batch of commits,
THE system SHALL NOT store any raw commit messages from that batch as facts.

[113-REQ-2.3] THE system SHALL assign each LLM-extracted git fact a confidence
value derived from the LLM response (high=0.9, medium=0.6, low=0.3) rather
than a fixed value.

#### Edge Cases

[113-REQ-2.E1] IF the LLM extraction call fails (timeout, API error), THEN THE
system SHALL skip the batch AND log a warning, continuing with subsequent
batches.

[113-REQ-2.E2] IF a commit message is shorter than 20 characters, THEN THE
system SHALL skip it without including it in the LLM batch.

### Requirement 3: Entity Signal Activation

**User Story:** As the retrieval system, I want the entity signal to receive
actual touched file paths so that code-structure-aware retrieval provides
relevant context to coding sessions.

#### Acceptance Criteria

[113-REQ-3.1] WHEN assembling the task prompt for a coder session, THE system
SHALL query `session_outcomes` for all `touched_path` values from prior
completed sessions with the same `spec_name` AND pass the deduplicated list
to `AdaptiveRetriever.retrieve()` as `touched_files`.

[113-REQ-3.2] THE system SHALL limit the `touched_files` list to the 50 most
recently touched paths (by session `created_at`) to bound the entity graph
traversal cost.

#### Edge Cases

[113-REQ-3.E1] IF no prior sessions exist for the current spec (first session),
THEN THE system SHALL pass `touched_files=[]` AND the entity signal SHALL
return an empty result list.

### Requirement 4: Audit Report Consumption

**User Story:** As the orchestrator, I want audit report findings to be
persisted in the database and injected into subsequent coder prompts, so that
audit analysis influences code quality.

#### Acceptance Criteria

[113-REQ-4.1] WHEN an audit-review session completes and produces an audit
report, THE system SHALL parse the report into structured review findings AND
persist them in the `review_findings` table with `category='audit'`.

[113-REQ-4.2] WHEN assembling the task prompt for a coder session, THE system
SHALL include active audit findings for the current spec in the prompt context,
using the same injection mechanism as pre-review findings.

[113-REQ-4.3] THE system SHALL NOT delete audit report files until end-of-run
consolidation, so that they remain available for inspection during the run.

#### Edge Cases

[113-REQ-4.E1] IF the audit report cannot be parsed into structured findings,
THEN THE system SHALL log a warning AND retain the raw report file without
persisting findings.

### Requirement 5: Compaction and Noise Reduction

**User Story:** As the knowledge system, I want aggressive compaction and noise
filtering so that the fact store converges toward curated knowledge rather than
unbounded accumulation.

#### Acceptance Criteria

[113-REQ-5.1] WHEN compaction runs, THE system SHALL identify and supersede
facts whose content is a substring of another fact with equal or higher
confidence AND return the count of superseded facts.

[113-REQ-5.2] THE system SHALL apply a minimum content length filter of 50
characters during fact ingestion; facts shorter than this threshold SHALL NOT
be stored.

[113-REQ-5.3] WHEN the deduplication threshold (default 0.92 cosine similarity)
identifies near-duplicates, THE system SHALL keep the fact with higher
confidence (breaking ties by recency) AND supersede the other.

#### Edge Cases

[113-REQ-5.E1] IF compaction reduces the fact count by more than 50%, THEN THE
system SHALL log an info message reporting the before and after counts.

### Requirement 6: Cold-Start Detection and Skip

**User Story:** As the retrieval system, I want to skip retrieval overhead when
no facts exist, so that early sessions in a fresh project don't pay the cost of
four empty signal queries.

#### Acceptance Criteria

[113-REQ-6.1] WHEN `AdaptiveRetriever.retrieve()` is called, THE system SHALL
first execute a count query against `memory_facts` for facts matching the
current `spec_name` or having confidence >= the configured threshold AND return
the count to the caller.

[113-REQ-6.2] IF the count from [113-REQ-6.1] is zero, THEN THE system SHALL
skip all four signal queries AND return an empty `RetrievalResult` with a
`cold_start=True` flag AND log a debug message "Skipping retrieval: no facts
available (cold start)".

#### Edge Cases

[113-REQ-6.E1] IF the count query itself fails (database error), THEN THE
system SHALL proceed with normal retrieval rather than skipping, AND log a
warning.

### Requirement 7: Retrieval Quality Validation

**User Story:** As the orchestrator, I want retrieval quality metrics so that I
can measure whether the knowledge system is providing value to coding sessions.

#### Acceptance Criteria

[113-REQ-7.1] WHEN `AdaptiveRetriever.retrieve()` returns a non-empty result,
THE system SHALL emit a `knowledge.retrieval` audit event containing:
`spec_name`, `node_id`, `facts_returned` (count), `signals_active` (list of
signal names that returned non-empty results), `cold_start` (boolean), and
`token_budget_used` (integer).

[113-REQ-7.2] THE system SHALL include a `retrieval_summary` field in
`session_outcomes` that records the number of facts injected into the session
prompt AND the signal names that contributed facts.

#### Edge Cases

[113-REQ-7.E1] IF the audit event emission fails, THEN THE system SHALL
continue without blocking the session AND log a warning.
