# Predictive Planning and Knowledge Usage

Research spike for [issue #146](https://github.com/agent-fox-dev/agent-fox-v2/issues/146).

## Executive Summary

agent-fox already has rich execution data (duration, cost, escalations, complexity
assessments) and a causal knowledge graph, but most of this data sits unused during
planning and dispatch. The highest-ROI improvements are:

1. **Duration-based task ordering** (small effort, high impact) — sort ready tasks
   by predicted duration DESC so long tasks start first in parallel batches.
2. **Link review findings to causal graph** (small effort, high impact) — connect
   skeptic/oracle/verifier findings to memory facts so downstream sessions inherit
   context automatically.
3. **Predictive file conflict detection** (large effort, medium impact) — extract
   file-level impact from specs to anticipate merge conflicts before parallel dispatch.

---

## Part 1: Predictive Planning

### 1.1 Can execution history predict task duration?

**Current state:** Yes, the data exists. DuckDB stores `complexity_assessments` and
`execution_outcomes` (see `knowledge/migrations.py:63-95`). Each outcome record
includes `duration_ms`, `attempt_count`, `escalation_count`, `total_tokens`, and
`total_cost`. Feature vectors are stored at assessment time (`routing/storage.py`).

**Data available:**
- `duration_ms` per task execution
- `subtask_count`, `spec_word_count`, `edge_case_count`, `dependency_count` per
  assessment (`routing/features.py:20-61`)
- `actual_tier`, `predicted_tier`, `confidence` per assessment
- `archetype` type (coder/skeptic/oracle/verifier)

**Opportunity:** Train a regression model (not just the existing tier classifier) to
predict `duration_ms ~ features`. Use predictions for dispatch ordering and capacity
planning.

| Aspect | Detail |
|--------|--------|
| Effort | Medium (10-15 hours) |
| Impact | High (10-30% wall-clock reduction) |
| Files | `routing/features.py`, `routing/assessor.py`, new `routing/duration.py` |

### 1.2 Can we pre-fetch context before sessions start?

**Current state:** Context is assembled at session startup via `session/prompt.py:253-348`.
This involves: reading spec files (fast, on disk), querying DuckDB for review findings
and memory facts, and traversing the causal graph (`select_context_with_causal()` at
`prompt.py:351-451`). Fact selection uses keyword matching + recency scoring
(`memory/filter.py:19-86`).

**Bottlenecks identified:**
- Causal graph traversals run per-session (expensive BFS walks)
- Keyword relevance filtering computed at session time (no pre-ranking)
- Multiple sequential DB queries for review/verification/drift findings

**Opportunities:**

| Opportunity | Effort | Savings |
|-------------|--------|---------|
| Pre-compute ranked facts per spec at plan time | Small (4-6h) | 50-100ms/session |
| Pre-compute causal neighborhoods | Medium (8-12h) | 150-300ms/session |
| Batch pre-fetch for N parallel sessions | Medium (10-14h) | 30-50% fewer DB queries |

**Recommendation:** Start with pre-computed ranked facts (smallest effort, immediate
benefit). Causal neighborhood pre-computation is worth it if session count is high.

### 1.3 Can we anticipate merge conflicts?

**Current state:** No. File overlap between parallel tasks is not tracked. Conflicts
are detected only during harvest (`workspace/harvest.py:44-150`) and auto-resolved
with `-X theirs` as a last resort (line 124). The graph builder (`graph/builder.py`)
creates dependency edges from `tasks.md` but has no file-level awareness.

**The problem:** Parallel tasks can touch overlapping files without coordination.
The orchestrator dispatches ready tasks greedily (`engine/engine.py:1022-1069`) with
no awareness of potential file conflicts.

**Opportunity:** Extract file modification patterns from `tasks.md` and `test_spec.md`
using regex/heuristics. Build a file-level impact matrix per task group. During
parallel dispatch, check for overlaps and optionally serialize conflicting pairs.

| Aspect | Detail |
|--------|--------|
| Effort | Large (20-25 hours) |
| Impact | Medium (conflict awareness, fewer forced merges) |
| Risk | Extraction heuristics may have low accuracy initially |
| Files | `graph/builder.py`, new `graph/file_impacts.py`, `engine/engine.py` |

**Implementation phases:**
1. Feature extraction from specs (3-4h)
2. Schema and migration for `task_file_impacts` table (2h)
3. Graph builder integration (3-4h)
4. Orchestrator dispatch integration (5-6h)
5. Testing and validation (4-5h)

### 1.4 Can we optimize task ordering beyond topological sort?

**Current state:** Ready tasks are sorted alphabetically (`graph_sync.py:67`). No
prioritization by duration, complexity, or cost. Parallel dispatch fills the pool
greedily in this arbitrary order (`engine/engine.py:1022-1069`).

**Opportunities (ranked by effort/impact):**

| Strategy | Effort | Impact | Description |
|----------|--------|--------|-------------|
| Duration DESC | Small (4-6h) | High (10-25%) | Long tasks first in parallel batches |
| Complexity DESC | Small (3-4h) | Medium | ADVANCED tasks first |
| Critical path forecasting | Medium (12-15h) | High (30-40%) | Dynamic CPM with learned weights |
| Cost-aware ordering | Small (5-6h) | Medium | Minimize cost within time constraints |

**Recommendation:** Start with duration-based ordering. Data already exists in
`execution_outcomes`. Implementation is small: add `get_task_duration_hints()` to
`routing/storage.py`, pass hints to `ready_tasks()`, sort DESC.

---

## Part 2: Knowledge Usage

### 2.1 How effectively are facts used during sessions?

**Current state:** Facts flow through a well-designed pipeline:
1. Extracted from session transcripts into `.agent-fox/memory.jsonl`
2. Synced to DuckDB `memory_facts` table with embeddings
3. Selected via keyword matching + recency scoring (`memory/filter.py`)
4. Enhanced with causal neighbors (`prompt.py:351-451`)
5. Injected into session context as "## Memory Facts" section

**Selection algorithm:** `select_relevant_facts()` scores by keyword overlap count +
recency bonus (normalized 0-1). Budget: max 50 facts (40 keyword + 10 causal).

**Effectiveness gaps:**
- **No confidence filtering:** Low-confidence facts treated equally to high-confidence
- **No task-group awareness:** Only spec name used for scoping, not task group number
- **Static causal budget:** Fixed 10-fact causal allocation regardless of match quality
- **No obsolescence tracking:** Superseded facts not automatically filtered

**Quick wins:**
- Filter facts by `confidence >= "medium"` before scoring (small effort)
- Add task group to keyword matching for tighter scoping (small effort)
- Dynamic causal budget based on keyword match density (medium effort)

### 2.2 Are review findings influencing subsequent sessions?

**Current state:** Yes, but with significant isolation.

**What works:**
- Skeptic findings rendered into coder context via `render_review_context()`
  (`prompt.py:103-147`), grouped by severity
- Oracle drift rendered via `render_drift_context()` (`prompt.py:50-100`)
- Verifier verdicts rendered as requirement status table
- `coding.md` template explicitly instructs coders to address critical findings,
  triage major findings, and note minor ones
- Blocking logic enforces: skeptic blocks if critical findings exceed threshold
  (`session/convergence.py:40-101`), oracle blocks similarly (lines 125-193)

**What doesn't work:**
- **Review findings are siloed:** Stored in separate tables (`review_findings`,
  `verification_results`, `drift_findings`), never linked to `memory_facts` or
  the causal graph
- **No cross-task-group propagation:** Findings scoped to (spec, task_group) pairs;
  a critical finding in group 2 doesn't inform group 4's coder session unless
  the skeptic runs again
- **Static blocking thresholds:** `block_threshold` is configured manually, not
  learned from historical effectiveness
- **Weak verifier feedback:** Verifier FAIL triggers a coder retry, but the retry
  model is simple — it doesn't learn from patterns across multiple attempts

### 2.3 How do causal chains feed back into the system?

**Current state:** The causal graph (`knowledge/causal.py:1-194`) is implemented and
integrated:
- `store_causal_links()` persists directed edges in `fact_causes` table
- `traverse_causal_chain()` does BFS traversal with configurable depth/direction
- `_extract_causal_links()` in `engine/knowledge_harvest.py:100-170` uses LLM to
  discover links between new and prior facts
- `select_context_with_causal()` enriches session context with causally-linked facts

**Critical gap:** Review findings (skeptic, oracle, verifier) are stored in separate
tables and **never linked to the causal graph**. This means:
- A skeptic finding about "module X has a race condition" doesn't link to existing
  memory facts about module X's fragility
- Oracle drift findings don't create causal links to the facts they contradict
- The causal graph only connects `memory_facts` to each other, missing the review
  knowledge entirely

**Highest-value improvement:** Create causal links from review findings to related
memory facts. When a skeptic flags requirement X, link to existing facts about X.
This is a small code change in `knowledge_harvest.py` that would significantly
improve downstream context quality.

### 2.4 Can we build a "project model" from accumulated knowledge?

**Current state:** The pieces exist but are scattered:
- Feature extraction in `routing/features.py` scores spec complexity
- Execution outcomes track actual performance per task
- Memory facts capture patterns, gotchas, and decisions
- Causal graph links facts to each other

**What's missing:** A unified project model that aggregates:
- Module stability scores (which areas fail repeatedly?)
- Spec outcome history (which specs are expensive/slow/fragile?)
- Archetype effectiveness (do multi-skeptic instances improve blocking precision?)
- Temporal degradation (which knowledge is stale?)

**Conceptual project model:**

```python
@dataclass
class ProjectModel:
    # Learned from execution_outcomes
    spec_outcomes: dict[str, SpecMetrics]      # avg cost, duration, fail rate
    module_stability: dict[str, float]          # defect density from findings

    # Learned from review findings
    fragile_areas: list[str]                    # specs/modules with recurring issues
    archetype_effectiveness: dict[str, float]   # success rate per archetype config

    # Derived from causal graph + memory
    knowledge_staleness: dict[str, int]         # days since last validation
    active_drift_areas: list[str]               # specs with recent oracle drift
```

**Implementation path:**
1. New `knowledge/project_model.py` module (medium effort)
2. Aggregate queries over existing DuckDB tables
3. Expose to planner for task ordering and cost estimation
4. Update model after each execution cycle

---

## Prioritized Recommendations

| # | Improvement | Effort | Impact | Category |
|---|------------|--------|--------|----------|
| 1 | **Duration-based task ordering** — sort ready tasks by predicted duration DESC | Small (4-6h) | High | Planning |
| 2 | **Link review findings to causal graph** — connect skeptic/oracle findings to memory facts | Small (6-8h) | High | Knowledge |
| 3 | **Confidence-aware fact selection** — filter low-confidence facts, dynamic causal budget | Small (4-6h) | Medium | Knowledge |
| 4 | **Duration regression model** — predict task duration from feature vectors | Medium (10-15h) | High | Planning |
| 5 | **Pre-compute ranked facts** — at plan time, pre-score and cache fact rankings | Small (4-6h) | Medium | Planning |
| 6 | **Project model: spec outcome tracking** — aggregate failure rates, cost, duration per spec | Medium (10-12h) | Medium | Knowledge |
| 7 | **Critical path forecasting** — dynamic CPM scheduling with learned weights | Medium (12-15h) | High | Planning |
| 8 | **Cross-task-group finding propagation** — review findings visible to downstream groups | Medium (8-10h) | Medium | Knowledge |
| 9 | **Predictive file conflict detection** — extract file impacts, serialize conflicting tasks | Large (20-25h) | Medium | Planning |
| 10 | **Learned blocking thresholds** — adjust block_threshold from historical precision | Large (15-20h) | Low | Knowledge |

**Recommended execution order:** Items 1-3 are quick wins that can be done independently.
Item 4 builds on item 1. Items 5-8 form a coherent "knowledge improvement" batch.
Items 9-10 are larger investments for later.

---

## Key File References

| Area | File | Key Functions |
|------|------|---------------|
| Execution data | `routing/storage.py` | `persist_outcome()`, `query_outcomes()` |
| Feature extraction | `routing/features.py:20-61` | `extract_features()` |
| Assessment pipeline | `routing/assessor.py:210-313` | `AssessmentPipeline.assess()` |
| Fact selection | `memory/filter.py:19-86` | `select_relevant_facts()` |
| Causal graph | `knowledge/causal.py:1-194` | `store_causal_links()`, `traverse_causal_chain()` |
| Context assembly | `session/prompt.py:253-348` | `assemble_context()` |
| Causal context | `session/prompt.py:351-451` | `select_context_with_causal()` |
| Review rendering | `session/prompt.py:50-186` | `render_*_context()` |
| Review storage | `knowledge/review_store.py` | `insert_findings()`, `query_active_findings()` |
| Task dispatch | `engine/engine.py:1022-1069` | `_fill_pool()` |
| Ready detection | `engine/graph_sync.py:49-67` | `ready_tasks()` |
| Merge handling | `workspace/harvest.py:44-150` | `harvest()` |
| Knowledge harvest | `engine/knowledge_harvest.py:100-170` | `_extract_causal_links()` |
| DuckDB schema | `knowledge/migrations.py:63-95` | v3 migration (assessments/outcomes) |
