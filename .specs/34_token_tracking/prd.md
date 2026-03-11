# PRD: Comprehensive Token Tracking

> Source: [GitHub Issue #147](https://github.com/agent-fox-dev/agent-fox-v2/issues/147)

## Problem

Token usage and cost reporting in agent-fox v2 significantly underreports
actual consumption. The system only tracks tokens from Claude Code SDK sessions
(coding, skeptic, verifier, oracle archetypes) but misses all direct Anthropic
API calls made for auxiliary tasks:

- Memory fact extraction (`memory/extraction.py`)
- Causal link extraction (`engine/knowledge_harvest.py`)
- AI spec validation (`spec/ai_validation.py` — 4 call sites)
- Fix clusterer (`fix/clusterer.py`)
- Routing complexity assessment (`routing/assessor.py`)
- Knowledge query synthesis (`knowledge/query.py`)

Additionally, model pricing is hardcoded in `core/models.py` and may be stale.
There is no per-archetype or per-spec cost breakdown. `SessionRecord` lacks an
`archetype` field, preventing archetype-level analysis.

## Goals

1. **Track all token consumption** — every LLM call, whether via the Claude
   Code SDK or direct Anthropic API, must contribute to reported totals.
2. **Configurable pricing** — model pricing lives in `config.toml` with current
   Claude values as defaults. Users can update pricing without code changes.
3. **Per-archetype cost tracking** — add `archetype` to `SessionRecord` so
   reporting can break down costs by archetype.
4. **Per-spec cost aggregation** — `agent-fox status` shows cost per spec.
5. **Accurate reporting** — costs reported by agent-fox should closely
   approximate actual Anthropic billing (within full-price estimation; prompt
   caching discounts are not modeled).

## Scope

### In Scope

- A lightweight token accumulator that auxiliary LLM call sites report to.
- Accumulator totals folded into `ExecutionState` at session boundaries.
- New `[pricing]` config section with per-model input/output prices, defaulting
  to current Claude pricing.
- `calculate_cost()` reads pricing from config instead of hardcoded
  `ModelEntry` fields.
- Add `archetype` field to `SessionRecord`.
- Add per-spec cost aggregation to `StatusReport` and `agent-fox status` output.
- Update `MODEL_REGISTRY` to remove pricing fields (moved to config).
- Verify and update current pricing values against Anthropic's published rates.

### Out of Scope

- Prompt caching discount modeling.
- Remote/cloud cost dashboards or telemetry.
- New CLI commands (reporting via existing `status`, `standup` commands).
- Token efficiency metrics (tokens per file, per test).
- Cost estimation for remaining tasks.

## Clarifications

1. **All token consumption tracked** — both SDK sessions and direct
   `client.messages.create()` calls.
2. **Full-price estimation acceptable** — no cache modeling. This may
   overestimate vs. Anthropic billing, which is preferable to underestimating.
3. **Pricing in config.toml** — new `[pricing]` section with per-model
   input/output prices. Defaults match current Claude API pricing.
4. **`archetype` added to `SessionRecord`** — trivial change, enables
   per-archetype reporting in `status` and `standup`.
5. **Per-spec cost in `status`** — aggregate session costs by spec prefix
   of `node_id`.
6. **No new CLI commands** — enhance existing `status` output.
7. **No `--cost` flag** — cost info shown by default in `status`.
