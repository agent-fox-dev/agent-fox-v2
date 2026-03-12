# PRD: Project Model, Critical Path, and Predictive Planning

## Problem

Agent-fox dispatches tasks to agent sessions but lacks aggregate visibility
into project health, schedule risk, and conflict potential. Operators cannot
answer questions like "which specs fail most often?", "what is the critical
path through remaining work?", or "will these parallel tasks step on each
other's files?" without manually querying DuckDB or reading logs.

Additionally, blocking thresholds (the number of critical findings that cause
a skeptic or oracle to halt a spec) are statically configured. With enough
execution history, the system could learn better thresholds from outcomes.

## Source

Extracted from the project model, critical path forecasting, file conflict
detection, and learned blocking threshold components of the original spec 39
(package consolidation). The implementation code already exists in
`agent_fox/knowledge/project_model.py`, `agent_fox/graph/critical_path.py`,
`agent_fox/graph/file_impacts.py`, and `agent_fox/knowledge/blocking_history.py`
but lacks a dedicated spec with requirements, test contracts, and a task plan.

## Goals

1. Provide an aggregate project model summarizing spec outcomes, module
   stability, and archetype effectiveness from DuckDB execution history.
2. Compute the critical path through the task graph using duration hints as
   weights and report it in `agent-fox status` output.
3. Detect predicted file conflicts between parallel tasks using regex
   heuristics on spec documents. Serialize conflicting task pairs to prevent
   merge conflicts. Behind a config flag (default: off).
4. Learn optimal blocking thresholds from historical blocking decisions when
   sufficient data is available. Behind a config flag (default: off).

## Scope

**In:**
- Project model aggregation from DuckDB (read-only)
- Critical path computation using duration hints
- File conflict detection from tasks.md / design.md
- Learned blocking thresholds from blocking_history table
- Config flags for file conflict detection and threshold learning
- CLI status output for project model and critical path
- DuckDB tables: task_file_impacts, blocking_history, learned_thresholds

**Out:**
- Write-back from project model to DuckDB (read-only aggregate)
- Duration hint generation (handled by spec 41)
- DuckDB schema hardening (handled by spec 38)
- Knowledge package consolidation (handled by spec 39)

## Dependencies

| Spec | Relationship | Justification |
|------|-------------|---------------|
| 38 (DuckDB Hardening) | Must complete first | DuckDB is mandatory; project model queries require hardened connections |
| 39 (Package Consolidation) | Must complete first | Knowledge code lives in agent_fox/knowledge/ per spec 39 |
| 41 (Duration Ordering) | Must complete first | Duration hints used as weights for critical path computation |

## New Files

| File | Purpose |
|------|---------|
| `agent_fox/knowledge/project_model.py` | SpecMetrics, ProjectModel, build_project_model() |
| `agent_fox/graph/critical_path.py` | CriticalPathResult, compute_critical_path() |
| `agent_fox/graph/file_impacts.py` | FileImpact, extract_file_impacts(), detect_conflicts() |
| `agent_fox/knowledge/blocking_history.py` | BlockingDecision, record_blocking_decision(), compute_optimal_threshold() |

## Modified Files

| File | Change |
|------|--------|
| `agent_fox/cli/status.py` | Add --model output, critical path display |
| `agent_fox/engine/engine.py` | Serialize conflicting tasks when file_conflict_detection enabled |
| `agent_fox/session/convergence.py` | Use learned thresholds when learn_thresholds enabled |
| `agent_fox/core/config.py` | PlanningConfig.file_conflict_detection, BlockingConfig section |

## New DuckDB Tables

| Table | Columns | Purpose |
|-------|---------|---------|
| task_file_impacts | node_id, file_path, source | Predicted file modifications per task |
| blocking_history | id, spec_name, archetype, critical_count, threshold, blocked, outcome, created_at | Blocking decision log |
| learned_thresholds | archetype, threshold, confidence, sample_count, updated_at | Computed optimal thresholds |

## Clarifications

1. Project model is read-only: no write-back to DuckDB from the aggregate.
2. File conflict detection defaults to off. When enabled, conflicting parallel
   tasks are serialized (only one dispatched at a time).
3. Learned thresholds default to off. When enabled and sufficient history
   exists (>= 20 decisions), the system replaces the static threshold.
4. Critical path handles tied paths by reporting all paths with equal duration.
5. File impact extraction uses regex heuristics on backtick-quoted paths in
   spec documents. It is best-effort and may miss or over-report files.
6. Tasks with no predicted file impacts are always safe to dispatch in
   parallel (no-conflict assumption).
