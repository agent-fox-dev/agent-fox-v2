# PRD: Knowledge System Pruning

## Problem

Analysis of three agent-fox 3.2.0 test runs (building a 9-spec Rust/Go
microservices project) revealed that the knowledge system is largely
non-functional or producing noise. Of the 22 database tables, 10 have zero
rows. The gotcha extraction system — spec 115's main contribution — produces
36% outright garbage (complaints about missing context), while the remaining
"real" gotchas are speculative rather than observed. The errata index is never
populated because `register_errata` is never called from production code.
Blocking history records zero decisions despite blocking actually occurring.

Meanwhile, one pipeline demonstrably contributed: the review findings
carry-forward loop. Coders received unresolved critical/major findings from
the reviewer and addressed them (e.g., "Addressed all 4 Skeptic major
findings"). Verification results (161 PASS / 7 FAIL) provided genuine
validation.

## Objective

Remove all knowledge system components that did NOT contribute value during
coding sessions. Keep only the subsystems with evidence of positive impact.
The result is a leaner, honest system where every remaining component
actually works.

## What to Remove

### 1. Gotcha extraction and storage

**Files:** `gotcha_extraction.py`, `gotcha_store.py`
**Table:** `gotchas`
**Evidence:**
- 246 gotchas stored across 3 runs; 36% (89) are empty complaints like
  `"**Spec**: unknown"`, `"**Touched files**: none"`, `"**Status**: completed"`
- Every session produces exactly 3 gotchas regardless of content (fixed quota)
- 19 gotcha texts appear identically across 2+ unrelated specs
- "Real" gotchas are speculative ("NATS message ordering may...") rather than
  observed findings from the session
- The extraction prompt receives only spec_name, touched_files, and
  session_status — insufficient context to produce useful insights
- Each extraction costs ~$0.01 per session (Haiku call) for zero demonstrated
  value

### 2. Errata index

**Files:** `errata_store.py`
**Table:** `errata_index`
**Evidence:**
- 0 rows populated across all 3 runs
- `register_errata()` is called from exactly one place in production code:
  `fox_provider._query_errata()` calls `query_errata()` (read-only).
  The write path (`register_errata()`) has no production callers — only test
  code calls it
- The coder archetype creates errata documents on disk but never registers
  them in the index

### 3. Blocking history and threshold learning

**Files:** `blocking_history.py`
**Table:** `blocking_history`
**Evidence:**
- 0 rows despite blocking occurring (test 1: `09_mock_apps:1` was
  security-blocked, cascading to 7 downstream nodes)
- `record_blocking_decision()` IS called from `result_handler.py:226` but the
  recording silently fails (swallowed by `except Exception`)
- Even if fixed, threshold learning requires 20+ decisions —  with ~1 blocking
  event per 83-task run, this would take 20+ full runs to activate
- The fixed-threshold blocking in the engine works fine without learned
  thresholds

### 4. Sleep artifacts

**Table:** `sleep_artifacts`
**Evidence:**
- 0 rows; no production code writes to or reads from this table
- Feature was specced (spec 112) but code paths were never implemented

### 5. Legacy empty tables

**Tables:** `memory_facts`, `memory_embeddings`, `entity_graph`,
`entity_edges`, `fact_entities`
**Evidence:**
- All 0 rows; population code was removed in spec 114
- Tables remain as schema debris

### 6. Causal link table

**Table:** `fact_causes`
**Evidence:**
- 0 rows across all 3 runs
- Only written by `review_store._insert_causal_links()` during supersession
- Never read by any code (write-only table)
- Supersession is already tracked via the `superseded_by` column on
  review_findings/verification_results/drift_findings

### 7. Dead configuration and column

- `KnowledgeProviderConfig.gotcha_ttl_days` — unused after gotcha removal
- `KnowledgeProviderConfig.model_tier` — unused after gotcha removal
- `session_outcomes.retrieval_summary` column — all NULL across every session

## What to Keep

### Review findings carry-forward (demonstrated value)
- `review_store.py` (insert_findings, insert_verdicts, insert_drift_findings,
  query_active_findings, query_active_verdicts)
- Tables: `review_findings`, `verification_results`, `drift_findings`
- Evidence: coders received and acted on review findings; verification
  produced genuine PASS/FAIL verdicts

### Operational telemetry (infrastructure)
- `duckdb_sink.py`, `sink.py` (session_outcomes, tool_calls, tool_errors)
- `audit.py`, `agent_trace.py` (audit_events, conversation traces)
- Tables: `session_outcomes`, `tool_calls`, `tool_errors`, `audit_events`

### Core infrastructure
- `provider.py` (KnowledgeProvider protocol, NoOpKnowledgeProvider)
- `db.py` (KnowledgeDB connection lifecycle)
- `migrations.py` (schema management + new cleanup migration)
- `__init__.py` (package exports)

### Plan state (engine infrastructure)
- Tables: `plan_nodes`, `plan_edges`, `plan_meta`, `runs`, `schema_version`

## Design Decisions

1. **KnowledgeProvider protocol stays unchanged.** `ingest()` and `retrieve()`
   remain in the protocol for forward compatibility. `FoxKnowledgeProvider.ingest()`
   becomes a no-op. `retrieve()` returns only review findings.

2. **FoxKnowledgeProvider keeps its name.** Renaming to
   `ReviewOnlyKnowledgeProvider` would break config references and provide
   little benefit. The class may gain new features in the future.

3. **Tables are DROPped via a new migration (v18).** Leaving empty tables in
   the schema provides no value and obscures which components are live.
   Dropping them documents the decision explicitly.

4. **`fact_causes` and `_insert_causal_links()` are removed from review_store.**
   The supersession chain is already fully tracked via `superseded_by` columns.
   The causal link table is write-only — nothing reads it.

5. **`retrieval_summary` column is NOT dropped.** Dropping a column from a
   table in DuckDB requires a table rebuild. The column is harmless and could
   be populated in a future implementation. Not worth the migration complexity.

6. **drift_findings stays.** While 0 rows in these test runs (greenfield
   project), the drift-review code path fires on non-greenfield projects. The
   table is in the same module as review_findings and verification_results.

## Source

Source: Input provided by user via interactive prompt, based on analysis of
test run logs (`output_3.2.0_test{1,2,3}.log`) and the knowledge database
(`.agent-fox/knowledge.duckdb`) from the parking-fee-service project.
