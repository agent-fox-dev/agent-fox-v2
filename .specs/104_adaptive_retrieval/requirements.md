# Requirements Document

## Introduction

This spec replaces agent-fox's sequential, single-signal fact retrieval
pipeline with a unified retriever that fuses four signals (keyword, vector,
entity graph, causal chain) via Reciprocal Rank Fusion, applies adaptive
signal weights derived from task context, and assembles context with causal
ordering and salience-based token budgeting.

## Glossary

- **RRF (Reciprocal Rank Fusion)**: A rank-aggregation method that combines
  multiple ranked lists into a single score per item:
  `score(d) = sum(1 / (k + rank_i(d)))` for each signal `i` where `d`
  appears. `k` is a smoothing constant (typically 60).
- **Signal**: A single retrieval method that produces a ranked list of facts.
  The four signals are: keyword, vector, entity, causal.
- **Intent profile**: A set of per-signal weight multipliers derived from the
  session's task context (archetype, node status, task metadata).
- **Anchor set**: The set of candidate facts produced by fusing all signal
  rankings via weighted RRF.
- **Salience score**: The final weighted RRF score for a fact, determining
  its position and detail level in the assembled context.
- **Token budget**: Maximum total character length for the formatted context
  block injected into the system prompt.
- **Touched files**: Files that the current task's spec or prior sessions
  have modified, extracted from `tasks.md` paths or session history.

## Requirements

### Requirement 1: Multi-Signal Retrieval

**User Story:** As the orchestrator, I want facts retrieved from all four
knowledge signals in parallel, so that no relevant fact is missed because
it only scores well on a non-primary signal.

#### Acceptance Criteria

[104-REQ-1.1] WHEN the retriever is invoked for a session, THE system SHALL
query all four signals (keyword, vector, entity graph, causal chain) AND
return a ranked list from each signal.

[104-REQ-1.2] THE keyword signal SHALL query `memory_facts` using spec name
matching and keyword overlap, returning facts ranked by keyword match count
plus recency bonus, AND return the ranked list to the fusion stage.

[104-REQ-1.3] THE vector signal SHALL embed the task description, query
`memory_embeddings` via cosine similarity, AND return the ranked list of
`SearchResult` items to the fusion stage.

[104-REQ-1.4] THE entity signal SHALL call `find_related_facts` with the
session's touched file paths, AND return the ranked list of entity-linked
facts to the fusion stage.

[104-REQ-1.5] THE causal signal SHALL traverse `fact_causes` from same-spec
facts up to depth 3, AND return the ranked list of causally-linked facts
(ordered by proximity) to the fusion stage.

#### Edge Cases

[104-REQ-1.E1] IF a signal produces zero results (e.g., no embeddings exist,
no entity graph populated, no causal links), THEN THE system SHALL proceed
with the remaining signals and exclude the empty signal from RRF scoring.

[104-REQ-1.E2] IF all four signals produce zero results, THEN THE system
SHALL return an empty context block.

[104-REQ-1.E3] IF the vector signal fails (embedding error, DuckDB error),
THEN THE system SHALL log a warning and proceed with the remaining signals.

### Requirement 2: Reciprocal Rank Fusion

**User Story:** As the orchestrator, I want the four ranked lists fused into
a single scored set, so that facts appearing across multiple signals get
promoted.

#### Acceptance Criteria

[104-REQ-2.1] WHEN the retriever has collected ranked lists from all
available signals, THE system SHALL compute a weighted RRF score for every
unique fact using the formula:
`score(fact) = sum(weight_i / (k + rank_i(fact)))` for each signal `i` where
the fact appears, AND return the facts sorted by descending score.

[104-REQ-2.2] THE RRF smoothing constant `k` SHALL default to 60.

[104-REQ-2.3] THE system SHALL deduplicate facts across signals by fact ID
before scoring, so that the same fact appearing in multiple signals
contributes one entry with an aggregated score.

#### Edge Cases

[104-REQ-2.E1] IF a fact appears in only one signal's ranked list, THEN THE
system SHALL score it using only that signal's weight and rank (no penalty
for absence from other signals).

### Requirement 3: Adaptive Intent Weighting

**User Story:** As the orchestrator, I want retrieval weights to adapt to
the session's task context, so that a retry-after-failure session gets more
causal context and a fresh structural session gets more entity context.

#### Acceptance Criteria

[104-REQ-3.1] WHEN the retriever is invoked, THE system SHALL derive an
intent profile (four signal weights) from the session context: archetype
name, node status (fresh attempt vs. retry after failure), and available
task metadata (spec name, task group).

[104-REQ-3.2] THE system SHALL apply the intent profile weights as
multipliers on each signal's contribution to the RRF formula.

[104-REQ-3.3] THE system SHALL provide default weight profiles that produce
reasonable results without configuration, AND return the computed intent
profile to the caller for observability.

#### Edge Cases

[104-REQ-3.E1] IF the archetype is unknown or the node status is not
available, THEN THE system SHALL fall back to a balanced default profile
where all four signal weights are equal (1.0).

### Requirement 4: Context Assembly with Ordering

**User Story:** As the orchestrator, I want the retrieved facts assembled
into a structured context block with causal ordering and provenance, so
that the agent receives well-organized knowledge.

#### Acceptance Criteria

[104-REQ-4.1] WHEN the retriever has produced a scored anchor set, THE
system SHALL select the top-N facts (configurable, default 50) and arrange
them with causal predecessors before their effects, AND return the formatted
context string to the caller.

[104-REQ-4.2] THE system SHALL include provenance metadata with each fact
in the formatted output: spec name, confidence level, and salience tier
(high/medium/low based on score percentile).

[104-REQ-4.3] THE system SHALL apply a configurable token budget (default
30,000 characters) to the context block: high-salience facts (top 20%)
are rendered in full, medium-salience facts (next 40%) are rendered as
one-line summaries, and low-salience facts (bottom 40%) are omitted if
the budget is exceeded.

#### Edge Cases

[104-REQ-4.E1] IF the total formatted context is under the token budget,
THEN THE system SHALL render all selected facts at full detail regardless
of salience tier.

### Requirement 5: Integration with Session Lifecycle

**User Story:** As a maintainer, I want the unified retriever wired into the
session lifecycle, replacing the current multi-step retrieval chain, so that
all sessions benefit from fused retrieval.

#### Acceptance Criteria

[104-REQ-5.1] WHEN `NodeSessionRunner._build_prompts` assembles knowledge
context, THE system SHALL call the unified retriever instead of the previous
chain (`select_relevant_facts` → `enhance_with_causal` →
`_retrieve_cross_spec_facts`).

[104-REQ-5.2] THE unified retriever's formatted context string SHALL be
passed to `assemble_context` in place of the previous `memory_facts` list.

[104-REQ-5.3] THE system SHALL accept retrieval configuration from
`config.toml` under `[knowledge.retrieval]` with keys: `rrf_k` (int,
default 60), `max_facts` (int, default 50), `token_budget` (int, default
30000), AND use these values during retrieval.

#### Edge Cases

[104-REQ-5.E1] IF the `[knowledge.retrieval]` section is absent from
`config.toml`, THEN THE system SHALL use default values for all retrieval
parameters.

### Requirement 6: Removal of Legacy Retrieval

**User Story:** As a maintainer, I want the old retrieval chain removed so
that there is a single, well-defined retrieval path.

#### Acceptance Criteria

[104-REQ-6.1] THE system SHALL remove the `select_relevant_facts` function
from `agent_fox/knowledge/filtering.py`.

[104-REQ-6.2] THE system SHALL remove the `enhance_with_causal` function
from `agent_fox/engine/session_lifecycle.py`.

[104-REQ-6.3] THE system SHALL remove the `_retrieve_cross_spec_facts`
method from `NodeSessionRunner`.

[104-REQ-6.4] THE system SHALL remove the `precompute_fact_rankings` function
and `RankedFactCache` dataclass from `agent_fox/engine/fact_cache.py`, since
precomputed caching is replaced by live retrieval.

#### Edge Cases

[104-REQ-6.E1] IF any module imports the removed functions, THEN THE system
SHALL update or remove those imports so that the codebase compiles without
errors.

### Requirement 7: Memory JSONL Removal

**User Story:** As a maintainer, I want the JSONL fact backup removed so that
DuckDB is the sole authoritative fact store with no stale fallback paths.

#### Acceptance Criteria

[104-REQ-7.1] THE system SHALL remove the `export_facts_to_jsonl` and
`load_facts_from_jsonl` functions from `agent_fox/knowledge/store.py`.

[104-REQ-7.2] THE system SHALL remove the JSONL fallback path from
`read_all_facts`, so that DuckDB is the only fact source.

[104-REQ-7.3] THE system SHALL remove all JSONL export calls from the
engine lifecycle (`_barrier_sync`, `_cleanup_infrastructure`, compaction,
barrier sync).

[104-REQ-7.4] THE system SHALL remove the `memory.jsonl` seed file creation
from `workspace/init_project.py` AND the `!.agent-fox/memory.jsonl`
exception from `.gitignore`.

#### Edge Cases

[104-REQ-7.E1] IF DuckDB is unavailable during `read_all_facts`, THEN THE
system SHALL return an empty fact list rather than falling back to JSONL.
