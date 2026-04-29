# Design Document: Knowledge Retrieval Fixes

## Overview

This spec fixes four bugs in the knowledge system's retrieval pipeline.
All changes are in two modules (`fox_provider.py`, `summary_store.py`),
one engine module (`engine.py`), and one session lifecycle module
(`session_lifecycle.py` or `result_handler.py`). No new tables, no new
dependencies, no new CLI commands.

## Architecture

```mermaid
flowchart TD
    Engine["engine.py<br/>generate_run_id()"] -->|set_run_id| Provider["FoxKnowledgeProvider"]
    Provider -->|retrieve()| SL["session_lifecycle.py<br/>assemble_context()"]
    Provider -->|_query_reviews| RS["review_store.py"]
    Provider -->|_query_same_spec_summaries| SS["summary_store.py"]
    Provider -->|_query_cross_spec_summaries| SS
    Provider -->|_query_prior_run| RS
    RH["result_handler.py<br/>session completion"] -->|ingest()| Provider
    RH -->|generate_reviewer_summary| Provider
    RH -->|generate_verifier_summary| Provider
```

### Module Responsibilities

1. `knowledge/fox_provider.py` -- Receives `run_id` from engine, queries
   all knowledge sources, formats items for prompt injection.
2. `knowledge/summary_store.py` -- CRUD for `session_summaries` table.
   Query filter updated to include all archetypes.
3. `knowledge/review_store.py` -- CRUD for `review_findings` and
   `verification_results`. New query for prior-run findings.
4. `engine/engine.py` -- Calls `set_run_id()` on the knowledge provider
   after generating the run ID.
5. `engine/session_lifecycle.py` or `engine/result_handler.py` -- Generates
   reviewer/verifier summaries at session completion and passes them to
   `ingest()`.

## Execution Paths

### Path 1: run_id wiring (Fix 1)

1. `engine/engine.py: Engine._init_run` -- calls `generate_run_id()` -> `str`
2. `engine/engine.py: Engine._init_run` -- calls `knowledge_provider.set_run_id(run_id)`
3. (later) `engine/session_lifecycle.py: SessionLifecycle._assemble_context` -- calls `knowledge_provider.retrieve(spec_name, task_description, task_group, session_id)`
4. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve` -- calls `_query_same_spec_summaries(conn, spec_name, task_group)` which uses `self._run_id`
5. `knowledge/fox_provider.py: FoxKnowledgeProvider._query_same_spec_summaries` -- calls `summary_store.query_same_spec_summaries(conn, spec_name, task_group, run_id)` -> `list[SummaryRecord]`
6. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve` -- returns formatted `[CONTEXT]` items to caller

### Path 2: Pre-review finding elevation (Fix 2)

1. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve` -- calls `_query_reviews(conn, spec_name, task_group, task_description)`
2. `knowledge/fox_provider.py: FoxKnowledgeProvider._query_reviews` -- calls `review_store.query_active_findings(conn, spec_name, task_group)` with `include_prereview=True` when `task_group != "0"` -> `list[ReviewFinding]`
3. `knowledge/review_store.py: query_active_findings` -- returns findings where `task_group IN (?, '0')` instead of `task_group = ?`
4. `knowledge/fox_provider.py: FoxKnowledgeProvider._query_cross_group_reviews` -- calls `review_store.query_cross_group_findings(conn, spec_name, task_group)` which now excludes group 0 to avoid duplication -> `list[ReviewFinding]`
5. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve` -- group 0 findings appear in `reviews` (tracked) rather than `cross_group_items` (untracked)

### Path 3: Reviewer/verifier summary generation (Fix 3)

1. `engine/session_lifecycle.py: SessionLifecycle._finalize_session` -- detects archetype is `reviewer` or `verifier`
2. `engine/session_lifecycle.py: SessionLifecycle._finalize_session` -- calls `generate_archetype_summary(archetype, session_output)` -> `str`
3. `engine/session_lifecycle.py: SessionLifecycle._finalize_session` -- sets `context["summary"] = summary`
4. `knowledge/fox_provider.py: FoxKnowledgeProvider.ingest` -- calls `_store_summary(conn, session_id, spec_name, context)`
5. `knowledge/summary_store.py: insert_summary` -- inserts row into `session_summaries`
6. (later) `knowledge/summary_store.py: query_same_spec_summaries` -- returns summaries from all archetypes (filter removed)

### Path 4: Cross-run finding carry-forward (Fix 4)

1. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve` -- calls `_query_prior_run_findings(conn, spec_name)`
2. `knowledge/review_store.py: query_prior_run_findings(conn, spec_name, current_run_id, max_items)` -> `list[ReviewFinding]`
3. `knowledge/review_store.py: query_prior_run_verdicts(conn, spec_name, current_run_id, max_items)` -> `list[VerificationResult]`
4. `knowledge/fox_provider.py: FoxKnowledgeProvider.retrieve` -- formats as `[PRIOR-RUN]` items, appends to result list (not tracked)

## Components and Interfaces

### FoxKnowledgeProvider changes

```python
class FoxKnowledgeProvider:
    def set_run_id(self, run_id: str) -> None:
        """Set the current run ID for summary queries."""
        self._run_id = run_id if run_id else None
```

### review_store.py new functions

```python
def query_active_findings(
    conn, spec_name, task_group=None, include_prereview=False
) -> list[ReviewFinding]:
    """When include_prereview=True and task_group is not '0',
    query task_group IN (task_group, '0') instead of task_group = ?."""

def query_prior_run_findings(
    conn, spec_name, current_run_id, max_items=5
) -> list[ReviewFinding]:
    """Active critical/major findings NOT from the current run."""

def query_prior_run_verdicts(
    conn, spec_name, current_run_id, max_items=5
) -> list[VerificationResult]:
    """Active FAIL verdicts NOT from the current run."""
```

### summary_store.py change

```python
def query_same_spec_summaries(
    conn, spec_name, task_group, run_id, max_items=5
) -> list[SummaryRecord]:
    """Remove archetype='coder' filter. Return all archetypes."""
```

### Summary generation function

```python
def generate_archetype_summary(
    archetype: str,
    findings: list | None = None,
    verdicts: list | None = None,
) -> str:
    """Generate a summary string for reviewer or verifier sessions."""
```

## Data Models

No new tables. No schema changes. All changes are query-level.

The `review_findings` table already has a `session_id` column that encodes
the run_id (the session_id format includes the run context). For cross-run
queries, we use the `runs` table to identify prior runs:

```sql
SELECT rf.* FROM review_findings rf
JOIN runs r ON rf.created_at BETWEEN r.started_at AND COALESCE(r.completed_at, CURRENT_TIMESTAMP)
WHERE rf.spec_name = ?
  AND rf.superseded_by IS NULL
  AND r.id != ?
  AND rf.severity IN ('critical', 'major')
ORDER BY CASE rf.severity WHEN 'critical' THEN 0 ELSE 1 END, rf.description
LIMIT ?
```

Alternative (simpler): since findings don't have a `run_id` column, use the
`created_at` timestamp of the current run's start to identify "prior"
findings -- anything created before the current run started.

## Operational Readiness

No new observability hooks needed. Existing log lines already report
retrieval counts. The existing `Retrieved X review + Y errata + ...` log
line will now show non-zero values for context and cross-spec items,
providing immediate verification that the fix works.

## Correctness Properties

### Property 1: run_id Enables Summary Retrieval

*For any* FoxKnowledgeProvider instance with `set_run_id(R)` called where
R is a non-empty string, `_query_same_spec_summaries()` and
`_query_cross_spec_summaries()` SHALL query the database using R as the
run_id filter (not return early).

**Validates: Requirements 120-REQ-1.1, 120-REQ-1.2, 120-REQ-1.4, 120-REQ-1.5**

### Property 2: Pre-Review Findings Are Tracked

*For any* `retrieve()` call with `task_group != "0"`, group 0 findings
SHALL appear in the primary review results (tracked via finding_injections)
and SHALL NOT appear in the cross-group results.

**Validates: Requirements 120-REQ-2.1, 120-REQ-2.2, 120-REQ-2.3**

### Property 3: All Archetypes Produce Summaries

*For any* completed session regardless of archetype (coder, reviewer,
verifier), the session context dict SHALL contain a non-empty `summary`
field.

**Validates: Requirements 120-REQ-3.1, 120-REQ-3.2**

### Property 4: Summary Retrieval Includes All Archetypes

*For any* `query_same_spec_summaries()` call, the result SHALL include
summaries from all archetypes, not just coder summaries.

**Validates: Requirements 120-REQ-3.3, 120-REQ-3.4**

### Property 5: Prior-Run Findings Are Surfaced

*For any* `retrieve()` call where the database contains active
critical/major findings from a prior run for the same spec, those findings
SHALL appear in the result with a `[PRIOR-RUN]` prefix.

**Validates: Requirements 120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.3**

### Property 6: Prior-Run Findings Are Not Tracked

*For any* prior-run finding served via `retrieve()`, the finding ID SHALL
NOT be recorded in `finding_injections`.

**Validates: Requirements 120-REQ-4.4**

### Property 7: No Duplication Between Review and Cross-Group

*For any* finding that appears in the primary review results (including
elevated group 0 findings), that finding SHALL NOT also appear in the
cross-group results.

**Validates: Requirements 120-REQ-2.3, 120-REQ-2.E2**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| `set_run_id()` never called | Summary queries return empty | 120-REQ-1.E1 |
| `set_run_id("")` called | Treated as unset, summaries return empty | 120-REQ-1.E2 |
| No group 0 findings exist | Only same-group findings returned | 120-REQ-2.E1 |
| Reviewer completes with 0 findings | Summary says "no findings" | 120-REQ-3.E1 |
| Verifier completes with 0 verdicts | Summary says "no verdicts" | 120-REQ-3.E2 |
| No prior runs in database | Empty prior-run context | 120-REQ-4.E1 |
| All prior findings superseded | Empty prior-run context | 120-REQ-4.E2 |
| Missing tables (fresh DB) | Graceful empty return | 120-REQ-4.E3 |

## Technology Stack

- Python 3.12+
- DuckDB (existing dependency)
- No new dependencies

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and merged into `develop`
7. Feature branch is merged back to `develop`
8. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- **Unit tests** for each new/modified function in `fox_provider.py`,
  `review_store.py`, and `summary_store.py`. Use in-memory DuckDB.
- **Property tests** for the no-duplication invariant (Property 7) and
  the run_id gating behavior (Property 1).
- **Integration test** that runs a full retrieve-ingest-retrieve cycle
  to verify summaries flow end-to-end.
