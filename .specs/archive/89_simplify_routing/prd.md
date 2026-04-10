# PRD: Simplify Model Routing

## Problem

The adaptive model routing system was designed to predict the optimal model tier
(SIMPLE/STANDARD/ADVANCED) for each task before execution, using feature
extraction, statistical learning (logistic regression), and LLM-based
assessment. In practice, the prediction pipeline never accumulates enough
training data to activate (requires 20 outcomes per spec/task group; the repo
has ~4,800 sessions across 65 task groups). The heuristic fallback produces
near-uniform 50/50 Sonnet/Opus distribution regardless of task complexity.

Meanwhile, the **escalation ladder** -- retry at the same tier, then escalate to
a higher tier on repeated failure -- demonstrably works (100% coder success
after Sonnet-to-Opus escalation in production data). This mechanism is simple,
valuable, and independent of the prediction pipeline.

The prediction pipeline adds ~1,300 lines of source code, ~1,700 lines of tests,
and deep coupling through `AssessmentPipeline`, `FeatureVector`, DuckDB
persistence, and statistical model training -- all for a system that has never
produced a meaningfully different prediction than the archetype default.

## Goal

Remove the prediction pipeline while preserving the escalation ladder and
archetype defaults. The system should:

1. Always start sessions at the archetype's `default_model_tier`.
2. On failure, retry at the same tier (with error feedback / hints injected).
3. After `retries_before_escalation` failures at the same tier, escalate to the
   next tier up (STANDARD -> ADVANCED).
4. Continue retrying at the escalated tier until exhausted, then block the task.
5. Never call feature extraction, statistical model training, LLM assessment, or
   DuckDB outcome persistence for routing purposes.

## Scope

### Remove

| File | Lines | Reason |
|------|-------|--------|
| `agent_fox/routing/assessor.py` | 590 | Entire assessment pipeline orchestration |
| `agent_fox/routing/features.py` | 298 | Feature vector extraction from specs |
| `agent_fox/routing/calibration.py` | 196 | Statistical model (logistic regression) |
| `agent_fox/routing/duration.py` | 332 | Duration regression model + presets |
| `agent_fox/routing/core.py` (DuckDB functions) | ~105 | `persist_assessment`, `persist_outcome`, `count_outcomes`, `query_outcomes`, `_feature_vector_to_json` |
| `tests/test_routing/test_assessor.py` | 350 | Tests for removed assessor |
| `tests/test_routing/test_features.py` | 75 | Tests for removed features |
| `tests/test_routing/test_calibration.py` | 535 | Tests for removed calibration |
| `tests/test_routing/test_storage.py` | 300 | Tests for removed DuckDB persistence |
| `tests/test_routing/test_integration.py` | 304 | Integration tests for removed pipeline |
| `tests/test_routing/conftest.py` | 250 | Shared fixtures for removed tests |
| `tests/test_routing/helpers.py` | 151 | Shared helpers for removed tests |

### Simplify

| File | Change |
|------|--------|
| `agent_fox/engine/assessment.py` | Remove pipeline call; always create ladder from archetype default tier |
| `agent_fox/engine/result_handler.py` | Remove `record_node_outcome()` dead code path for pipeline recording |
| `agent_fox/engine/run.py` | Remove `AssessmentPipeline` construction; stop passing it to orchestrator |
| `agent_fox/engine/engine.py` | Remove `get_duration_hint` import/usage if present |
| `agent_fox/cli/status.py` | Remove `get_duration_hint` import/usage if present |
| `agent_fox/routing/core.py` | Keep dataclasses (`FeatureVector`, `ComplexityAssessment`, `ExecutionOutcome`); remove DuckDB functions |
| `agent_fox/core/config.py` | Remove prediction-only config fields from `RoutingConfig` (`training_threshold`, `accuracy_threshold`, `retrain_interval`) |

### Keep (no changes)

| File | Reason |
|------|--------|
| `agent_fox/routing/escalation.py` | Core escalation ladder logic |
| `agent_fox/archetypes.py` | Archetype registry with `default_model_tier` |
| `agent_fox/nightshift/fix_pipeline.py` | Already uses escalation ladder directly |
| `tests/test_routing/test_escalation.py` | Tests for kept escalation logic |
| `tests/test_routing/test_config.py` | Tests for kept routing config |

## Clarifications

- **Duration module**: Remove entirely (option a). Task ordering falls back to
  defaults. Duration presets are not essential.
- **Data types in core.py**: Keep all three dataclasses as-is (option a).
  `FeatureVector` may have empty/default fields but avoids breaking downstream
  references.
- **Assessment manager**: Simplify to always create a ladder from archetype
  defaults. No pipeline dependency. This ensures every node gets an escalation
  ladder (currently, with `pipeline=None`, `assess_node()` returns early and
  creates no ladder, falling back to legacy retry behavior).
- **Dead code in result_handler**: Remove the `record_node_outcome()` method
  and all references to `self._routing_pipeline` outcome recording.
- **Tests**: Delete test files for removed modules. Keep test_escalation.py
  and test_config.py. Clean up conftest/helpers to remove unused fixtures.

## Supersedes

- `30_adaptive_model_routing` -- prediction pipeline removed; escalation ladder
  retained.
- `57_archetype_model_tiers` -- tier prediction removed; archetype defaults
  retained as the sole tier source.

## Dependencies

No cross-spec dependencies. This is a standalone simplification of existing code.
