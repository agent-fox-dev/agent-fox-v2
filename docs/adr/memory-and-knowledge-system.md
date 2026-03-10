# ADR: Memory and Knowledge System

**Status:** Accepted
**Date:** 2026-03-10

## Context

agent-fox runs many autonomous coding sessions across many specs. Without
persistent memory, each new session starts blind: the same mistakes get made
repeatedly, architectural decisions are re-litigated, and patterns across
sessions are invisible.

We need a system that:

1. Captures durable, structured knowledge from every coding session.
2. Allows that knowledge to be queried semantically at planning and session
   start time ("what do we know about X?").
3. Records session telemetry (outcomes, token usage, file touches) so usage
   patterns and regressions can be analyzed.
4. Persists quality-assurance records (Skeptic findings, Verifier verdicts)
   across re-runs with a supersession mechanism.
5. Ingests external knowledge sources (ADR documents, git history) to
   supplement session-extracted facts.

## Decision

We build a two-layer memory system:

- **Primary layer** – A JSONL flat file (`.agent-fox/memory.jsonl`) that is
  the authoritative, durable source of truth for extracted facts. It survives
  DuckDB failures and is human-readable.
- **Secondary layer** – A DuckDB database (`.agent-fox/knowledge.duckdb`) that
  indexes all facts with vector embeddings, stores session telemetry, quality
  records, and causal links, and answers semantic queries.

The system degrades gracefully: if DuckDB is unavailable, facts are written to
JSONL only and sessions continue without interruption.

---

## How Information Enters the System

### 1. Session Fact Extraction

After every coding session completes, `extract_and_store_knowledge()` in
`engine/knowledge_harvest.py` runs:

1. The full session transcript is sent to a **SIMPLE**-tier LLM with a
   structured extraction prompt asking for facts in six categories (see below).
2. The LLM responds with a JSON array of fact objects.
3. Facts are appended to `.agent-fox/memory.jsonl` (always).
4. If DuckDB is available, each fact is also written to the `memory_facts`
   table and a local `sentence-transformers` model (`all-MiniLM-L6-v2`,
   384 dimensions) generates a vector embedding stored in `memory_embeddings`.
5. A second LLM call extracts **causal links** between the new facts and all
   prior facts, and the links are stored in the `fact_causes` table.

### 2. External Knowledge Ingestion (`agent-fox ingest`)

The `KnowledgeIngestor` in `knowledge/ingest.py` pulls two additional sources
into `memory_facts`:

| Source | `category` value | Deduplicated by |
|--------|------------------|-----------------|
| ADR markdown files under `docs/adr/` | `adr` | `spec_name` (filename) |
| Git commit messages (`git log`) | `git` | `commit_sha` |

Each ingested item receives an embedding and is skipped on subsequent runs if
already present.

### 3. Session Outcome Recording

The `DuckDBSink` in `knowledge/duckdb_sink.py` records a row in
`session_outcomes` for every session completion — even failed ones. The
`SessionSink` protocol is fan-out: a `SinkDispatcher` can dispatch to both
`DuckDBSink` (structured) and `JsonlSink` (raw audit log) simultaneously.

### 4. Quality Records (Skeptic / Verifier)

After Skeptic and Verifier sessions finish, their structured findings are
written to `review_findings` and `verification_results` via
`knowledge/review_store.py`. Re-running a review for the same
`(spec_name, task_group)` **supersedes** the prior records and inserts causal
links from old to new, preserving the full audit trail.

### 5. Adaptive Routing History

The routing subsystem persists every complexity assessment and execution outcome
to `complexity_assessments` and `execution_outcomes`. This data trains a
logistic regression model that improves model-tier predictions over time.

---

## Database Structure

The DuckDB database at `.agent-fox/knowledge.duckdb` contains the following
tables. The schema is versioned and evolved through a forward-only migration
runner (`knowledge/migrations.py`).

### Schema Versions

| Version | Description |
|---------|-------------|
| 1 | Initial schema (memory, session outcomes, causal graph, tool signals) |
| 2 | Review findings and verification results (Skeptic/Verifier records) |
| 3 | Complexity assessments and execution outcomes (adaptive routing) |

### Table Reference

#### `schema_version`
Tracks applied migrations.

| Column | Type | Description |
|--------|------|-------------|
| `version` | `INTEGER PK` | Schema version number |
| `applied_at` | `TIMESTAMP` | When the migration ran |
| `description` | `TEXT` | Human-readable migration label |

---

#### `memory_facts`
One row per extracted or ingested fact. The primary knowledge table.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK` | Unique fact identifier |
| `content` | `TEXT` | The fact text (1–2 sentences) |
| `category` | `TEXT` | `gotcha` \| `pattern` \| `decision` \| `convention` \| `anti_pattern` \| `fragile_area` \| `adr` \| `git` |
| `spec_name` | `TEXT` | Source specification name or ADR filename |
| `session_id` | `TEXT` | Node ID of the session that produced this fact |
| `commit_sha` | `TEXT` | Git commit SHA (for `git`-category facts) |
| `confidence` | `TEXT` | `high` \| `medium` \| `low` |
| `created_at` | `TIMESTAMP` | Insertion time |
| `superseded_by` | `UUID` | UUID of the fact that replaces this one (`NULL` = active) |

---

#### `memory_embeddings`
One row per fact that has a vector embedding. Facts without embeddings are
excluded from vector search but remain queryable by other means.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK → memory_facts` | References the parent fact |
| `embedding` | `FLOAT[384]` | 384-dimensional sentence-transformers vector |

---

#### `session_outcomes`
One row per file touched per session (or one `NULL` row if no files were
touched). Provides the raw material for pattern detection and telemetry.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK` | Row identifier |
| `spec_name` | `TEXT` | Specification name |
| `task_group` | `TEXT` | Task group label (e.g. `"3"`) |
| `node_id` | `TEXT` | Session node identifier |
| `touched_path` | `TEXT` | File path modified in this session (nullable) |
| `status` | `TEXT` | `completed` \| `failed` \| `timeout` |
| `input_tokens` | `INTEGER` | Tokens consumed from context |
| `output_tokens` | `INTEGER` | Tokens generated |
| `duration_ms` | `INTEGER` | Wall-clock session duration |
| `created_at` | `TIMESTAMP` | When the outcome was recorded |

---

#### `fact_causes`
Directed edges in the causal graph. Populated by LLM-assisted causal extraction
and by the review supersession mechanism.

| Column | Type | Description |
|--------|------|-------------|
| `cause_id` | `UUID` | ID of the causing fact |
| `effect_id` | `UUID` | ID of the caused fact |
| *(PK)* | | Composite `(cause_id, effect_id)` |

---

#### `tool_calls` *(debug mode only)*
Records every tool invocation. Written only when `DuckDBSink(debug=True)`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK` | Record ID |
| `session_id` | `TEXT` | Session that made the call |
| `node_id` | `TEXT` | Node identifier |
| `tool_name` | `TEXT` | Name of the tool invoked |
| `called_at` | `TIMESTAMP` | Invocation timestamp |

---

#### `tool_errors` *(debug mode only)*
Records every failed tool invocation. Written only when `DuckDBSink(debug=True)`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK` | Record ID |
| `session_id` | `TEXT` | Session that encountered the error |
| `node_id` | `TEXT` | Node identifier |
| `tool_name` | `TEXT` | Name of the tool that failed |
| `failed_at` | `TIMESTAMP` | Failure timestamp |

---

#### `review_findings` *(schema v2)*
Skeptic-archetype findings. Each re-run supersedes prior active records for
the same `(spec_name, task_group)`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK` | Record ID |
| `severity` | `TEXT` | `critical` \| `major` \| `minor` \| `observation` |
| `description` | `TEXT` | Finding text |
| `requirement_ref` | `TEXT` | Spec requirement ID, if applicable |
| `spec_name` | `TEXT` | Specification name |
| `task_group` | `TEXT` | Task group label |
| `session_id` | `TEXT` | Session that produced this finding |
| `superseded_by` | `TEXT` | Session ID that superseded this record (`NULL` = active) |
| `created_at` | `TIMESTAMP` | Record creation time |

---

#### `verification_results` *(schema v2)*
Verifier-archetype verdicts. Same supersession semantics as `review_findings`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID PK` | Record ID |
| `requirement_id` | `TEXT` | Requirement being verified |
| `verdict` | `TEXT` | `PASS` \| `FAIL` |
| `evidence` | `TEXT` | Supporting evidence text |
| `spec_name` | `TEXT` | Specification name |
| `task_group` | `TEXT` | Task group label |
| `session_id` | `TEXT` | Session that produced this verdict |
| `superseded_by` | `TEXT` | Session ID that superseded this record (`NULL` = active) |
| `created_at` | `TIMESTAMP` | Record creation time |

---

#### `complexity_assessments` *(schema v3)*
One row per task group assessed by the adaptive routing system before execution.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR PK` | Assessment ID |
| `node_id` | `VARCHAR` | Task graph node identifier |
| `spec_name` | `VARCHAR` | Specification name |
| `task_group` | `INTEGER` | Task group number |
| `predicted_tier` | `VARCHAR` | `SIMPLE` \| `STANDARD` \| `ADVANCED` |
| `confidence` | `FLOAT` | Prediction confidence (0–1) |
| `assessment_method` | `VARCHAR` | `heuristic` \| `statistical` \| `hybrid` \| `llm` |
| `feature_vector` | `JSON` | Serialized `FeatureVector` dataclass |
| `tier_ceiling` | `VARCHAR` | Maximum tier allowed for this task |
| `created_at` | `TIMESTAMP` | When the assessment was made |

---

#### `execution_outcomes` *(schema v3)*
One row per completed task execution. References a `complexity_assessments`
row to close the feedback loop for model training.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR PK` | Outcome ID |
| `assessment_id` | `VARCHAR → complexity_assessments` | The prior prediction |
| `actual_tier` | `VARCHAR` | Model tier that was actually used |
| `total_tokens` | `INTEGER` | Total tokens consumed |
| `total_cost` | `FLOAT` | Estimated API cost |
| `duration_ms` | `INTEGER` | Wall-clock execution duration |
| `attempt_count` | `INTEGER` | Number of attempts (including retries) |
| `escalation_count` | `INTEGER` | Number of tier escalations |
| `outcome` | `VARCHAR` | `success` \| `failure` \| `timeout` |
| `files_touched_count` | `INTEGER` | Number of files modified |
| `created_at` | `TIMESTAMP` | When the outcome was recorded |

---

## What Can Be Queried from DuckDB

### Semantic (Vector) Search

The `Oracle` class in `knowledge/query.py` implements a RAG pipeline:

1. Embed a free-text question using `all-MiniLM-L6-v2`.
2. Run cosine similarity search over `memory_embeddings` via DuckDB's built-in
   `array_cosine_distance` function (requires the `vss` extension).
3. Retrieve the top-k facts (default: 20) from `memory_facts`.
4. Pass retrieved facts with provenance to a STANDARD-tier LLM for synthesis.

This powers the `agent-fox ask` command.

### Causal Timeline Queries

`temporal_query()` in `knowledge/query.py`:

1. Seeds the search with vector similarity to find relevant facts.
2. Traverses the `fact_causes` graph via breadth-first search (up to depth 10,
   bi-directionally by default).
3. Returns a `Timeline` of `TimelineNode` objects sorted by timestamp and depth,
   renderable as indented cause/effect chains.

### Recurring Pattern Detection

`detect_patterns()` in `knowledge/query.py` joins `session_outcomes` with
itself (within a 1-day window) and validates co-occurrence against the causal
graph to surface `(path_changed → failure_path)` patterns. Confidence is
assigned based on occurrence count: ≥5 = high, ≥3 = medium, 2 = low.

### Active Review Records

`query_active_findings()` and `query_active_verdicts()` in
`knowledge/review_store.py` return non-superseded Skeptic/Verifier records for
a given spec, enabling the convergence system to decide whether to block or
proceed.

### Routing Model Training Data

`query_outcomes()` in `routing/storage.py` returns
`(feature_vector_json, actual_tier)` pairs by joining `execution_outcomes` with
`complexity_assessments`. This feeds logistic regression retraining in the
adaptive routing subsystem.

### Direct SQL Queries

Because the store is a standard DuckDB file, any ad-hoc analysis can be done by
opening `.agent-fox/knowledge.duckdb` directly:

```sql
-- Total token spend by spec
SELECT spec_name, SUM(input_tokens + output_tokens) AS total_tokens
FROM session_outcomes
GROUP BY spec_name
ORDER BY total_tokens DESC;

-- Active critical findings
SELECT spec_name, task_group, description
FROM review_findings
WHERE severity = 'critical' AND superseded_by IS NULL
ORDER BY created_at DESC;

-- Prediction accuracy by assessment method
SELECT
    a.assessment_method,
    COUNT(*) AS total,
    SUM(CASE WHEN a.predicted_tier = o.actual_tier THEN 1 ELSE 0 END) AS correct,
    ROUND(100.0 * SUM(CASE WHEN a.predicted_tier = o.actual_tier THEN 1 ELSE 0 END) / COUNT(*), 1) AS accuracy_pct
FROM complexity_assessments a
JOIN execution_outcomes o ON o.assessment_id = a.id
GROUP BY a.assessment_method;

-- Facts most causally connected (highest out-degree)
SELECT CAST(f.id AS VARCHAR), f.content, COUNT(fc.effect_id) AS effects
FROM memory_facts f
JOIN fact_causes fc ON fc.cause_id = f.id
GROUP BY f.id, f.content
ORDER BY effects DESC
LIMIT 10;

-- Session success rate by spec
SELECT
    spec_name,
    COUNT(*) AS sessions,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_pct
FROM session_outcomes
GROUP BY spec_name;
```

The `dump_knowledge.py` dev script exports the store to
`.agent-fox/knowledge_dump.md` for quick offline review.

---

## Configuration

```toml
[knowledge]
store_path            = ".agent-fox/knowledge.duckdb"   # default
embedding_model       = "all-MiniLM-L6-v2"              # local, no API call
embedding_dimensions  = 384
ask_top_k             = 20   # facts retrieved per vector search
ask_synthesis_model   = "STANDARD"
```

---

## Trade-offs

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| Embedding model | Local `all-MiniLM-L6-v2` | No API cost or latency; runs on CPU/Apple Silicon; 384 dimensions are sufficient for intra-project knowledge |
| Primary store | JSONL flat file | Human-readable, zero dependencies, survives DuckDB failures |
| Secondary index | DuckDB + VSS extension | In-process, embeddable, supports both SQL analytics and vector search in a single file |
| Causal extraction | Second LLM call after every session | Enables timeline queries and pattern validation; best-effort (failures are silently swallowed) |
| Supersession | `superseded_by` column + causal links | Preserves full history while excluding stale facts from active queries; audit trail maintained |
| Graceful degradation | All DuckDB writes are best-effort | A DB failure never blocks session execution |

## Consequences

- The `.agent-fox/` directory should be project-local and gitignored.
- Embedding model download happens on first use (~80 MB for `all-MiniLM-L6-v2`).
- Long-running projects accumulate a growing DuckDB file; the `reset` command
  clears it when desired.
- The `fact_causes` graph can become large; the causal traversal caps depth at
  10 by default to prevent runaway queries.
