# Configuration Reference

Configuration lives in `.agent-fox/config.toml`. All fields are optional;
defaults are used for any absent field. Unknown top-level keys are logged and
ignored.

Run `agent-fox init` to generate a config file with all options documented as
commented-out entries. Re-running `init` merges new options into an existing
config non-destructively.

---

## `[orchestrator]`

Controls the execution engine.

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `parallel` | int | `1` | 1–8 | Max parallel sessions |
| `sync_interval` | int | `5` | 0+ | Sessions between sync barriers (0 = disabled) |
| `hot_load` | bool | `true` | | Scan for new specs at sync barriers |
| `max_retries` | int | `2` | 0+ | Retries per failed task |
| `session_timeout` | int | `30` | 1+ | Session timeout in minutes |
| `inter_session_delay` | int | `3` | 0+ | Seconds between sessions |
| `max_cost` | float | none | | Cost ceiling in USD |
| `max_sessions` | int | none | | Session count limit |
| `audit_retention_runs` | int | `20` | 1+ | Maximum runs to retain in the audit log |
| `max_blocked_fraction` | float | none | 0.0–1.0 | Stop the run when this fraction of nodes are blocked |
| `max_budget_usd` | float | `2.0` | 0.0+ | Per-session SDK budget cap in USD (0 = unlimited) |

---

## `[routing]`

Controls adaptive model routing — automatic selection of the cheapest model
tier that can handle each task, with escalation on failure.

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `retries_before_escalation` | int | `1` | 0–3 | Retries at same tier before escalating |
| `training_threshold` | int | `20` | 5–1000 | Min outcomes before training statistical model |
| `accuracy_threshold` | float | `0.75` | 0.5–1.0 | Min accuracy to prefer statistical over heuristic |
| `retrain_interval` | int | `10` | 5–100 | New outcomes between retraining cycles |

See the [ADR](adr/adaptive-model-routing.md) for design rationale.

---

## `[models]`

Model tier assignment for different roles.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `coding` | string | `"ADVANCED"` | Model tier for coding sessions |
| `coordinator` | string | `"STANDARD"` | Model tier for coordination |
| `memory_extraction` | string | `"SIMPLE"` | Model tier for fact extraction |
| `fallback_model` | string | `"claude-sonnet-4-6"` | Fallback model ID when primary is unavailable (empty string = no fallback) |

Model tiers: `SIMPLE`, `STANDARD`, `ADVANCED`. You can also specify a model ID
directly (e.g., `claude-sonnet-4-6`).

The `fallback_model` is passed directly to the Claude SDK — it may reference
any model known to the API, including models not in the local model registry.
Set to an empty string to disable fallback entirely.

---

## `[hooks]`

Lifecycle hooks executed at various stages.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pre_code` | list[string] | `[]` | Scripts to run before each session |
| `post_code` | list[string] | `[]` | Scripts to run after each session |
| `sync_barrier` | list[string] | `[]` | Scripts to run at sync barriers |
| `timeout` | int | `300` | Hook timeout in seconds (min 1) |
| `modes` | dict | `{}` | Per-script failure mode (`"abort"` or `"warn"`) |

Default failure mode is `abort` (non-zero exit stops execution). Set a
script's mode to `"warn"` to log a warning and continue.

Hook environment variables: `AF_SPEC_NAME`, `AF_TASK_GROUP`, `AF_WORKSPACE`,
`AF_BRANCH`.

---

## `[security]`

Bash command security controls.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `bash_allowlist` | list[string] | none | Replace default command allowlist entirely |
| `bash_allowlist_extend` | list[string] | `[]` | Add commands to the default allowlist |

If both are set, `bash_allowlist` takes precedence (with a warning).

---

## `[theme]`

UI theme and output styling using [Rich](https://rich.readthedocs.io/) style
strings.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `playful` | bool | `true` | Use fox-themed messages |
| `header` | string | `"bold #ff8c00"` | Rich style for headers |
| `success` | string | `"bold green"` | Rich style for success |
| `error` | string | `"bold red"` | Rich style for errors |
| `warning` | string | `"bold yellow"` | Rich style for warnings |
| `info` | string | `"#daa520"` | Rich style for info |
| `tool` | string | `"bold #cd853f"` | Rich style for tool output |
| `muted` | string | `"dim"` | Rich style for muted text |

---

## `[platform]`

GitHub platform integration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `type` | string | `"none"` | Platform type: `"none"` or `"github"` |
| `auto_merge` | bool | `false` | Auto-merge approved PRs |

---

## `[knowledge]`

Knowledge store and fact selection.

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `store_path` | string | `".agent-fox/knowledge.duckdb"` | | DuckDB database path |
| `embedding_model` | string | `"all-MiniLM-L6-v2"` | | Embedding model name (sentence-transformers) |
| `embedding_dimensions` | int | `384` | | Embedding vector dimensions |
| `ask_top_k` | int | `20` | 1+ | Default top-k for knowledge queries |
| `ask_synthesis_model` | string | `"STANDARD"` | | Model for answer synthesis |
| `confidence_threshold` | float | `0.5` | 0.0–1.0 | Minimum confidence for fact inclusion in session context |
| `fact_cache_enabled` | bool | `true` | | Pre-compute fact rankings at plan time |

---

## `[archetypes]`

Enable or disable agent archetypes. See the [archetypes reference](archetypes.md)
for details on each archetype's role and workflow.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `coder` | bool | `true` | Enable coder archetype (cannot be disabled) |
| `skeptic` | bool | `true` | Enable skeptic archetype (spec review) |
| `verifier` | bool | `true` | Enable verifier archetype (post-code checks) |
| `oracle` | bool | `false` | Enable oracle archetype (spec drift detection) |
| `librarian` | bool | `false` | Enable librarian archetype (documentation) |
| `cartographer` | bool | `false` | Enable cartographer archetype (architecture mapping) |
| `auditor` | bool | `false` | Enable auditor archetype (test quality gate) |

### `[archetypes.instances]`

Control how many parallel instances of an archetype run. Multiple instances
produce independent findings that are then converged.

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `skeptic` | int | `1` | 1–5 | Number of skeptic instances |
| `verifier` | int | `1` | 1–5 | Number of verifier instances |
| `auditor` | int | `1` | 1–5 | Number of auditor instances |

### `[archetypes.skeptic_settings]`

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `block_threshold` | int | `3` | 0+ | Block if majority-agreed critical findings exceed this count |

When a skeptic session completes, the engine counts its critical findings. If
the count exceeds `block_threshold`, the downstream coder task and all its
dependents are cascade-blocked. Blocking decisions are recorded to DuckDB for
threshold learning (see `[blocking]`).

### `[archetypes.oracle_settings]`

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `block_threshold` | int | none | 1+ | Block if critical drift findings exceed this count (omit for advisory only) |

When `block_threshold` is set, oracle findings above the threshold block the
downstream coder task. When omitted (`none`), the oracle is advisory-only —
findings are recorded but do not prevent execution.

### `[archetypes.auditor_config]`

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `min_ts_entries` | int | `5` | 1+ | Minimum test_spec entries to trigger auditor injection |
| `max_retries` | int | `2` | 0+ | Maximum auditor-coder retry iterations |

### `[archetypes.models]`

Per-archetype model tier overrides. These act as tier ceilings — the system
may start lower but never escalates above the configured tier.

```toml
[archetypes.models]
coder = "STANDARD"    # coder tasks will never use ADVANCED
oracle = "STANDARD"   # oracle sessions use STANDARD tier
```

### `[archetypes.allowlists]`

Per-archetype bash command allowlists.

```toml
[archetypes.allowlists]
oracle = ["ls", "cat", "git", "grep", "find", "head", "tail", "wc"]
```

### `[archetypes.max_turns]`

Per-archetype SDK turn limits. Each key is an archetype name; the value is the
maximum number of request-response turns the SDK will execute per session.
Set to `0` to allow unlimited turns.

Default values when not configured:

| Archetype | Default |
|-----------|---------|
| `coder` | `200` |
| `oracle` | `50` |
| `skeptic` | `50` |
| `verifier` | `75` |
| `auditor` | `50` |
| `librarian` | `100` |
| `cartographer` | `100` |
| `coordinator` | `30` |

Example:

```toml
[archetypes.max_turns]
coder = 150       # override coder to 150 turns
oracle = 0        # unlimited turns for oracle
```

Negative values are rejected at startup.

### `[archetypes.thinking]`

Per-archetype extended thinking configuration. Extended thinking allocates a
token budget for the model to reason before producing its response.

Each entry is a sub-table named after the archetype:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `mode` | string | `"disabled"` | Thinking mode: `"enabled"`, `"adaptive"`, or `"disabled"` |
| `budget_tokens` | int | `10000` | Token budget for thinking (required > 0 when mode is `"enabled"`) |

Default thinking configuration:

| Archetype | Default mode | Default budget |
|-----------|-------------|----------------|
| `coder` | `"adaptive"` | `10000` |
| all others | `"disabled"` | `10000` |

- `"enabled"` — model always performs extended thinking.
- `"adaptive"` — model decides when to use extended thinking.
- `"disabled"` — no extended thinking (default for most archetypes).

Example:

```toml
[archetypes.thinking.coder]
mode = "enabled"
budget_tokens = 20000

[archetypes.thinking.verifier]
mode = "adaptive"
budget_tokens = 8000
```

Unrecognised `mode` values and `budget_tokens <= 0` with `mode = "enabled"`
are rejected at startup.

---

---

## `[pricing]`

Configurable per-model pricing for cost calculations. If this section is
absent, built-in defaults matching current Anthropic API rates are used.

### `[pricing.models.<model-id>]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `input_price_per_m` | float | varies | USD per million input tokens |
| `output_price_per_m` | float | varies | USD per million output tokens |
| `cache_read_price_per_m` | float | varies | USD per million cache-read input tokens |
| `cache_creation_price_per_m` | float | varies | USD per million cache-creation input tokens |

Default pricing:

| Model | Input $/M | Output $/M | Cache Read $/M | Cache Create $/M |
|-------|-----------|------------|----------------|------------------|
| `claude-haiku-4-5` | `1.00` | `5.00` | `0.10` | `1.25` |
| `claude-sonnet-4-6` | `3.00` | `15.00` | `0.30` | `3.75` |
| `claude-opus-4-6` | `5.00` | `25.00` | `0.50` | `6.25` |

Negative pricing values are clamped to zero with a warning.

Example:

```toml
[pricing.models.claude-sonnet-4-6]
input_price_per_m = 3.00
output_price_per_m = 15.00
cache_read_price_per_m = 0.30
cache_creation_price_per_m = 3.75
```

---

## `[planning]`

Planning and dispatch configuration.

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `duration_ordering` | bool | `true` | | Sort ready tasks by predicted duration (shortest first) |
| `min_outcomes_for_historical` | int | `10` | 1–1000 | Min outcomes before using historical duration data |
| `min_outcomes_for_regression` | int | `30` | 5–10000 | Min outcomes before training duration regression model |
| `file_conflict_detection` | bool | `false` | | Detect file conflicts between parallel tasks |

---

## `[blocking]`

Blocking threshold learning configuration.

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `learn_thresholds` | bool | `false` | | Learn blocking thresholds from history |
| `min_decisions_for_learning` | int | `20` | 1–1000 | Min blocking decisions before learning thresholds |
| `max_false_negative_rate` | float | `0.1` | 0.0–1.0 | Maximum acceptable false negative rate |
