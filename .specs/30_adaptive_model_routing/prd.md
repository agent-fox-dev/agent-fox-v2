# PRD: Adaptive Model Routing

## Problem Statement

agent-fox currently uses a static model assignment: each archetype has a fixed
model tier (e.g., coder = ADVANCED, skeptic = STANDARD), optionally overridden
in `config.toml`. Every task group in a spec runs at the same tier regardless of
its actual complexity. This leads to:

- **Wasted cost**: Simple tasks (writing test stubs, updating docs, config
  changes) consume expensive ADVANCED-tier tokens when SIMPLE would suffice.
- **Wasted time**: ADVANCED-tier models have higher latency; cheap models
  respond faster for straightforward work.
- **No learning**: The system does not accumulate knowledge about which tasks
  benefit from which model tiers, so operators cannot improve cost/quality
  trade-offs over time.

## Inspiration: CascadeFlow

[CascadeFlow](https://github.com/lemony-ai/cascadeflow) is an in-process
runtime that implements *speculative execution with quality validation*:

1. Attempts cheap/fast models first.
2. Validates response quality against configurable thresholds.
3. Escalates to expensive models only when validation fails.
4. Learns patterns over time to improve routing.

CascadeFlow operates at the **per-LLM-call** level, inside the agent loop. This
is too fine-grained for agent-fox, where the atomic execution unit is a **task
group session** (a full worktree lifecycle with hooks, prompts, execution,
harvest). However, the core ideas -- speculative execution, quality validation,
and pattern learning -- apply at the task-group level.

**Decision: Re-implement, not integrate.** CascadeFlow's architecture targets
per-call routing across 17+ providers. agent-fox needs task-group-level routing
within a single provider's tier system (SIMPLE/STANDARD/ADVANCED). The
re-implementation is scoped to agent-fox's execution model and data
infrastructure (DuckDB, session records, archetype registry).

## Feature Description

### Two-Layer Model Selection

Model selection operates in two layers:

1. **Pre-selection (complexity assessment)**: Before a task group executes,
   assess its complexity and select a starting model tier
   (SIMPLE/STANDARD/ADVANCED). The assessment uses a combination of heuristics
   (task group metadata, spec content, historical data) and AI assessment (LLM
   evaluates the task description). Over time, as the statistical model gains
   confidence from accumulated data, it takes precedence over LLM assessment
   (cheaper, faster).

2. **Speculative execution (escalation on failure)**: Execute the task group at
   the selected tier. If it fails, retry once at the same tier (the retry
   carries error context that may help the model succeed). If the retry also
   fails, escalate to the next higher tier and repeat. This continues until the
   task succeeds or the highest tier is exhausted.

### Provider-Aware Tiers

Model tiers (SIMPLE/STANDARD/ADVANCED) are provider-independent labels. The
existing `ModelRegistry` maps tiers to provider-specific models (e.g.,
Haiku/Sonnet/Opus for Anthropic). This mapping is already in place and does not
change. The adaptive routing system selects a *tier*, and the existing registry
resolves it to a concrete model.

### Quality Signals and Calibration

The system collects pre- and post-execution data for every task group:

**Pre-execution assessment:**
- Predicted complexity tier (SIMPLE/STANDARD/ADVANCED)
- Confidence score (0.0-1.0)
- Assessment method (heuristic, statistical, llm, hybrid)
- Feature vector: task group size (subtask count), spec word count, presence of
  property tests, edge case count, dependency count, archetype type

**Post-execution actuals:**
- Actual model tier used (after any escalation)
- Total tokens consumed
- Total cost
- Duration
- Number of attempts/escalations
- Session outcome (completed/failed)
- Files touched count

By comparing predictions against actuals, the system calibrates its future
assessments. The calibration loop:

1. Start with heuristic-only assessment (rule-based, zero history needed).
2. After accumulating N data points (configurable, default 20), train a
   statistical model (logistic regression on feature vectors).
3. When the statistical model's cross-validated accuracy exceeds a threshold
   (configurable, default 0.75), prefer it over heuristic assessment.
4. Periodically validate the statistical model against LLM assessment. When they
   diverge significantly, flag for review and continue using the higher-
   confidence method.

### Data Storage

All assessment and execution data is stored in DuckDB (the existing knowledge
store). New tables:

- `complexity_assessments`: Pre-execution predictions with feature vectors.
- `execution_outcomes`: Post-execution actuals linked to assessments.

These tables enable the statistical model to train on historical data and the
calibration loop to measure prediction accuracy.

### Retry and Escalation Semantics

The current retry logic (configurable `max_retries` in `OrchestratorConfig`) is
*replaced* by the escalation ladder:

1. Execute at the selected tier.
2. On failure: retry once at the same tier (configurable retries-before-escalation, default 1).
   Rationale: the error context from the first failure provides information
   that may help the same model succeed.
3. On second failure at the same tier: escalate to the next higher tier.
4. Repeat steps 2-3 at each tier until success or the highest tier is exhausted.
5. If the highest tier fails after its retries: mark the task as failed and
   cascade-block dependents (existing behavior).

The circuit breaker budget accounts for all speculative execution overhead
(failed attempts at lower tiers count toward cumulative cost).

### Default Behavior

Adaptive model routing is the **default behavior** -- not opt-in. The existing
static model assignment (archetype tier → config override → global default) is
replaced by the adaptive system. The config override mechanism remains as a
**ceiling**: if a user sets `archetypes.models.coder = "STANDARD"`, the adaptive
system will never escalate above STANDARD for coder tasks, but may still
start at SIMPLE.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 2 | 2 | Uses ModelTier, ModelEntry, MODEL_REGISTRY, resolve_model from core/models.py; group 2 (task 2.2) implements the model registry |
| 04_orchestrator | 3 | 3 | Modifies engine loop retry/escalation logic; group 3 (task 3.2) implements the orchestrator main loop with retry logic |
| 11_duckdb_knowledge_store | 2 | 2 | Adds new tables to DuckDB schema; group 2 (tasks 2.2-2.3) implements schema, migrations, and db.py |
| 26_agent_archetypes | 7 | 2 | Modifies model resolution in session_lifecycle.py; group 7 (task 7.1) implements archetype model resolution in NodeSessionRunner |

## Out of Scope

- **Cross-provider routing**: Only tiers within the configured provider are
  considered. Multi-provider support is a separate concern.
- **Per-LLM-call routing**: Routing happens at the task-group level, not per
  individual LLM call within a session.
- **Prompt-level optimization**: The system selects models, not prompts.
  Prompt engineering for cheaper models is out of scope.
- **Real-time model switching mid-session**: Once a session starts, it runs to
  completion at the selected tier.
