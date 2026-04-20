# Test Specification: Comprehensive Token Tracking

## Overview

Tests validate that auxiliary LLM token usage is captured, pricing is
configurable, cost calculations use config-based pricing, per-archetype and
per-spec breakdowns are correct, and backward compatibility is maintained.
All test cases map to requirements and correctness properties.

## Test Cases

### TS-34-1: Accumulator Records Usage

**Requirement:** 34-REQ-1.1
**Type:** unit
**Description:** The token accumulator records input_tokens, output_tokens,
and model for each call.

**Preconditions:**
- Fresh accumulator (no prior recordings).

**Input:**
- `record_auxiliary_usage(100, 50, "claude-haiku-4-5")`
- `record_auxiliary_usage(200, 100, "claude-sonnet-4-6")`

**Expected:**
- `flush()` returns 2 entries with matching values.

**Assertion pseudocode:**
```
record_auxiliary_usage(100, 50, "claude-haiku-4-5")
record_auxiliary_usage(200, 100, "claude-sonnet-4-6")
entries = flush_auxiliary_usage()
ASSERT len(entries) == 2
ASSERT entries[0].input_tokens == 100
ASSERT entries[0].output_tokens == 50
ASSERT entries[0].model == "claude-haiku-4-5"
ASSERT entries[1].input_tokens == 200
```

### TS-34-2: Accumulator Reports Immediately

**Requirement:** 34-REQ-1.2
**Type:** unit
**Description:** After recording, `get_auxiliary_totals()` reflects the
new usage immediately.

**Preconditions:**
- Fresh accumulator.

**Input:**
- Record 100 input, 50 output.

**Expected:**
- `get_auxiliary_totals()` returns (100, 50).

**Assertion pseudocode:**
```
record_auxiliary_usage(100, 50, "claude-haiku-4-5")
input_total, output_total = get_auxiliary_totals()
ASSERT input_total == 100
ASSERT output_total == 50
```

### TS-34-3: Auxiliary Tokens Added to ExecutionState

**Requirement:** 34-REQ-1.3
**Type:** unit
**Description:** When a session record is added to ExecutionState, auxiliary
tokens are included in the totals.

**Preconditions:**
- ExecutionState with zero totals.
- Accumulator has recorded 100 input, 50 output tokens.
- A SessionRecord with 1000 input, 500 output tokens.

**Input:**
- Call `add_session_record(record)` which flushes the accumulator.

**Expected:**
- `state.total_input_tokens == 1100` (1000 session + 100 auxiliary)
- `state.total_output_tokens == 550` (500 session + 50 auxiliary)

**Assertion pseudocode:**
```
record_auxiliary_usage(100, 50, "claude-haiku-4-5")
session_record = SessionRecord(input_tokens=1000, output_tokens=500, ...)
state.add_session_record(session_record)
ASSERT state.total_input_tokens == 1100
ASSERT state.total_output_tokens == 550
```

### TS-34-4: Auxiliary Cost Added to ExecutionState

**Requirement:** 34-REQ-1.4
**Type:** unit
**Description:** Auxiliary token cost is included in `total_cost`.

**Preconditions:**
- Pricing config with haiku at $1/$5 per M tokens.
- Accumulator has 1000 input, 500 output on haiku.

**Input:**
- Flush and calculate cost.

**Expected:**
- Auxiliary cost = (1000/1M)*$1 + (500/1M)*$5 = $0.001 + $0.0025 = $0.0035

**Assertion pseudocode:**
```
record_auxiliary_usage(1000, 500, "claude-haiku-4-5")
aux_cost = calculate_auxiliary_cost(pricing_config)
ASSERT abs(aux_cost - 0.0035) < 0.0001
```

### TS-34-5: All Call Sites Instrumented

**Requirement:** 34-REQ-1.5
**Type:** unit
**Description:** All six auxiliary call sites call `record_auxiliary_usage`.

**Preconditions:**
- Source code of all six files.

**Input:**
- Grep each file for `record_auxiliary_usage`.

**Expected:**
- Each of the six files contains at least one call to `record_auxiliary_usage`.

**Assertion pseudocode:**
```
files = [
    "agent_fox/memory/extraction.py",
    "agent_fox/engine/knowledge_harvest.py",
    "agent_fox/spec/ai_validation.py",
    "agent_fox/fix/clusterer.py",
    "agent_fox/routing/assessor.py",
    "agent_fox/knowledge/query.py",
]
FOR EACH file IN files:
    content = read_file(file)
    ASSERT "record_auxiliary_usage" IN content
```

### TS-34-6: Pricing Config With Defaults

**Requirement:** 34-REQ-2.1, 34-REQ-2.2
**Type:** unit
**Description:** `PricingConfig` provides per-model pricing with correct
defaults.

**Preconditions:**
- Default `AgentFoxConfig()`.

**Input:**
- Access `config.pricing.models`.

**Expected:**
- Contains entries for haiku, sonnet, opus with correct prices.

**Assertion pseudocode:**
```
config = AgentFoxConfig()
haiku = config.pricing.models["claude-haiku-4-5"]
ASSERT haiku.input_price_per_m == 1.00
ASSERT haiku.output_price_per_m == 5.00
opus = config.pricing.models["claude-opus-4-6"]
ASSERT opus.input_price_per_m == 15.00
ASSERT opus.output_price_per_m == 75.00
```

### TS-34-7: calculate_cost Uses Config Pricing

**Requirement:** 34-REQ-2.3
**Type:** unit
**Description:** `calculate_cost` uses pricing from config, not hardcoded.

**Preconditions:**
- Custom pricing config with haiku at $10/$50 per M.

**Input:**
- `calculate_cost(1_000_000, 1_000_000, "claude-haiku-4-5", custom_pricing)`

**Expected:**
- Cost = $10 + $50 = $60 (using custom prices, not defaults).

**Assertion pseudocode:**
```
custom = PricingConfig(models={"claude-haiku-4-5": ModelPricing(10.0, 50.0)})
cost = calculate_cost(1_000_000, 1_000_000, "claude-haiku-4-5", custom)
ASSERT cost == 60.0
```

### TS-34-8: Unknown Model Falls Back to Zero

**Requirement:** 34-REQ-2.4
**Type:** unit
**Description:** `calculate_cost` returns 0 for unknown model IDs.

**Preconditions:**
- Default pricing config (no entry for "unknown-model").

**Input:**
- `calculate_cost(1000, 500, "unknown-model", default_pricing)`

**Expected:**
- Returns 0.0 and logs a warning.

**Assertion pseudocode:**
```
pricing = PricingConfig()
cost = calculate_cost(1000, 500, "unknown-model", pricing)
ASSERT cost == 0.0
ASSERT warning_logged("unknown-model")
```

### TS-34-9: SessionRecord Has Archetype Field

**Requirement:** 34-REQ-3.1
**Type:** unit
**Description:** `SessionRecord` includes an `archetype` field defaulting
to `"coder"`.

**Preconditions:**
- None.

**Input:**
- Create `SessionRecord` without specifying archetype.

**Expected:**
- `record.archetype == "coder"`.

**Assertion pseudocode:**
```
record = SessionRecord(node_id="spec:1", attempt=1, status="completed",
    input_tokens=0, output_tokens=0, cost=0.0, duration_ms=0,
    error_message=None, timestamp="2026-01-01T00:00:00Z")
ASSERT record.archetype == "coder"
```

### TS-34-10: Archetype Populated From Runner

**Requirement:** 34-REQ-3.2
**Type:** unit
**Description:** `NodeSessionRunner` populates the archetype field.

**Preconditions:**
- A session executed with archetype="skeptic".

**Input:**
- The returned `SessionRecord`.

**Expected:**
- `record.archetype == "skeptic"`.

**Assertion pseudocode:**
```
record = run_session_with_archetype("skeptic")
ASSERT record.archetype == "skeptic"
```

### TS-34-11: Status Shows Per-Archetype Cost

**Requirement:** 34-REQ-3.3
**Type:** unit
**Description:** `StatusReport` includes per-archetype cost breakdown.

**Preconditions:**
- ExecutionState with sessions: 2 coder ($5 each), 1 skeptic ($3).

**Input:**
- Generate `StatusReport`.

**Expected:**
- `report.cost_by_archetype == {"coder": 10.0, "skeptic": 3.0}`.

**Assertion pseudocode:**
```
report = build_status_report(state_with_archetype_sessions)
ASSERT report.cost_by_archetype["coder"] == 10.0
ASSERT report.cost_by_archetype["skeptic"] == 3.0
```

### TS-34-12: Status Shows Per-Spec Cost

**Requirement:** 34-REQ-4.1
**Type:** unit
**Description:** `StatusReport` includes per-spec cost breakdown.

**Preconditions:**
- ExecutionState with sessions: spec_a:1 ($5), spec_a:2 ($3), spec_b:1 ($7).

**Input:**
- Generate `StatusReport`.

**Expected:**
- `report.cost_by_spec == {"spec_a": 8.0, "spec_b": 7.0}`.

**Assertion pseudocode:**
```
report = build_status_report(state_with_spec_sessions)
ASSERT report.cost_by_spec["spec_a"] == 8.0
ASSERT report.cost_by_spec["spec_b"] == 7.0
```

### TS-34-13: Spec Name Extracted From node_id

**Requirement:** 34-REQ-4.2
**Type:** unit
**Description:** Spec name is derived by stripping the last colon-separated
segment from `node_id`.

**Preconditions:**
- None.

**Input:**
- `"01_core_foundation:3"` → `"01_core_foundation"`
- `"26_agent_archetypes:0:skeptic"` → `"26_agent_archetypes:0"`

**Expected:**
- Correct spec name extraction.

**Assertion pseudocode:**
```
ASSERT extract_spec_name("01_core_foundation:3") == "01_core_foundation"
ASSERT extract_spec_name("26_agent_archetypes:0:skeptic") == "26_agent_archetypes:0"
```

### TS-34-14: ModelEntry Pricing Fields Removed

**Requirement:** 34-REQ-5.2
**Type:** unit
**Description:** `ModelEntry` no longer has pricing fields.

**Preconditions:**
- None.

**Input:**
- Inspect `ModelEntry` fields.

**Expected:**
- No `input_price_per_m` or `output_price_per_m` attributes.

**Assertion pseudocode:**
```
ASSERT NOT hasattr(ModelEntry, "input_price_per_m")
ASSERT NOT hasattr(ModelEntry, "output_price_per_m")
```

## Edge Case Tests

### TS-34-E1: Failed Auxiliary Call Records Zero

**Requirement:** 34-REQ-1.E1
**Type:** unit
**Description:** A failed auxiliary LLM call records zero tokens.

**Preconditions:**
- Fresh accumulator.

**Input:**
- Simulate a failed API call, then check accumulator.

**Expected:**
- Entry with input_tokens=0, output_tokens=0.

**Assertion pseudocode:**
```
# After handling a failed API call
record_auxiliary_usage(0, 0, "claude-haiku-4-5")
entries = flush_auxiliary_usage()
ASSERT len(entries) == 1
ASSERT entries[0].input_tokens == 0
```

### TS-34-E2: Missing Usage Data Records Zero

**Requirement:** 34-REQ-1.E2
**Type:** unit
**Description:** An API response without `usage` logs a warning and records
zero tokens.

**Preconditions:**
- Mock API response with no `usage` attribute.

**Input:**
- Process the response through the instrumented call site.

**Expected:**
- Zero tokens recorded, warning logged.

**Assertion pseudocode:**
```
response = MockResponse(usage=None)
# Instrumentation code should handle gracefully
ASSERT warning_logged("usage")
```

### TS-34-E3: Missing Pricing Section Uses Defaults

**Requirement:** 34-REQ-2.E1
**Type:** unit
**Description:** Config without `[pricing]` loads default prices.

**Preconditions:**
- Config TOML with no `[pricing]` section.

**Input:**
- `load_config(path_to_config)`.

**Expected:**
- `config.pricing` has default values for all models.

**Assertion pseudocode:**
```
config = load_config(write_to_tmp("[orchestrator]\nparallel = 1\n"))
ASSERT "claude-haiku-4-5" IN config.pricing.models
ASSERT config.pricing.models["claude-haiku-4-5"].input_price_per_m == 1.00
```

### TS-34-E4: Negative Pricing Clamped to Zero

**Requirement:** 34-REQ-2.E2
**Type:** unit
**Description:** Negative pricing values are clamped to zero.

**Preconditions:**
- None.

**Input:**
- `ModelPricing(input_price_per_m=-5.0, output_price_per_m=-10.0)`

**Expected:**
- Both values clamped to 0.0, warning logged.

**Assertion pseudocode:**
```
pricing = ModelPricing(input_price_per_m=-5.0, output_price_per_m=-10.0)
ASSERT pricing.input_price_per_m == 0.0
ASSERT pricing.output_price_per_m == 0.0
```

### TS-34-E5: Old SessionRecord Without Archetype

**Requirement:** 34-REQ-3.E1
**Type:** unit
**Description:** Loading a SessionRecord from JSON without `archetype`
defaults to `"coder"`.

**Preconditions:**
- JSON dict without `archetype` key.

**Input:**
- Deserialize the dict to SessionRecord.

**Expected:**
- `record.archetype == "coder"`.

**Assertion pseudocode:**
```
data = {"node_id": "spec:1", "attempt": 1, "status": "completed",
    "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
    "duration_ms": 0, "timestamp": "2026-01-01T00:00:00Z"}
record = SessionRecord.from_dict(data)
ASSERT record.archetype == "coder"
```

### TS-34-E6: node_id Without Colon

**Requirement:** 34-REQ-4.E1
**Type:** unit
**Description:** A `node_id` without a colon uses the full ID as spec name.

**Preconditions:**
- None.

**Input:**
- `extract_spec_name("standalone_task")`

**Expected:**
- Returns `"standalone_task"`.

**Assertion pseudocode:**
```
ASSERT extract_spec_name("standalone_task") == "standalone_task"
```

## Property Test Cases

### TS-34-P1: Accumulator Completeness

**Property:** Property 1 from design.md
**Validates:** 34-REQ-1.1, 34-REQ-1.2
**Type:** property
**Description:** The accumulator records exactly N entries for N calls.

**For any:** N random auxiliary calls (1-100) with random token counts
**Invariant:** `len(flush()) == N` and `flush()` returns empty list on
second call.

**Assertion pseudocode:**
```
FOR ANY calls IN lists(tuples(integers(0,1M), integers(0,1M), model_ids)):
    reset_accumulator()
    FOR EACH (inp, out, model) IN calls:
        record_auxiliary_usage(inp, out, model)
    entries = flush_auxiliary_usage()
    ASSERT len(entries) == len(calls)
    ASSERT flush_auxiliary_usage() == []
```

### TS-34-P2: Token Conservation

**Property:** Property 2 from design.md
**Validates:** 34-REQ-1.3, 34-REQ-1.4
**Type:** property
**Description:** Reported totals equal session tokens plus auxiliary tokens.

**For any:** random session tokens and random auxiliary tokens
**Invariant:** `total = session_tokens + auxiliary_tokens`

**Assertion pseudocode:**
```
FOR ANY session_in, session_out, aux_calls IN valid_token_combos():
    record all aux_calls
    state = ExecutionState()
    state.add_session_record(SessionRecord(input_tokens=session_in, output_tokens=session_out, ...))
    expected_in = session_in + sum(a.input_tokens for a in aux_calls)
    expected_out = session_out + sum(a.output_tokens for a in aux_calls)
    ASSERT state.total_input_tokens == expected_in
    ASSERT state.total_output_tokens == expected_out
```

### TS-34-P3: Pricing Config Precedence

**Property:** Property 3 from design.md
**Validates:** 34-REQ-2.1, 34-REQ-2.3
**Type:** property
**Description:** Config prices are used, not hardcoded values.

**For any:** random pricing values and random token counts
**Invariant:** `cost == (in * price_in + out * price_out) / 1M`

**Assertion pseudocode:**
```
FOR ANY in_price, out_price, in_tokens, out_tokens IN valid_pricing_combos():
    pricing = PricingConfig(models={"test": ModelPricing(in_price, out_price)})
    cost = calculate_cost(in_tokens, out_tokens, "test", pricing)
    expected = (in_tokens * in_price + out_tokens * out_price) / 1_000_000
    ASSERT abs(cost - expected) < 0.0001
```

### TS-34-P4: Pricing Defaults Present

**Property:** Property 4 from design.md
**Validates:** 34-REQ-2.2, 34-REQ-2.E1, 34-REQ-5.1
**Type:** property
**Description:** Default config has pricing for all registered models.

**For any:** `AgentFoxConfig()` (deterministic)
**Invariant:** Every model in `MODEL_REGISTRY` has a pricing entry.

**Assertion pseudocode:**
```
config = AgentFoxConfig()
FOR EACH model_id IN MODEL_REGISTRY.keys():
    ASSERT model_id IN config.pricing.models
    ASSERT config.pricing.models[model_id].input_price_per_m > 0
```

### TS-34-P5: Archetype Preserved in Record

**Property:** Property 5 from design.md
**Validates:** 34-REQ-3.1, 34-REQ-3.2
**Type:** property
**Description:** Archetype field round-trips through serialization.

**For any:** archetype name from ["coder", "skeptic", "verifier", "oracle",
"librarian", "cartographer"]
**Invariant:** `deserialize(serialize(record)).archetype == archetype`

**Assertion pseudocode:**
```
FOR ANY archetype IN archetype_names:
    record = SessionRecord(..., archetype=archetype)
    data = record.to_dict()
    restored = SessionRecord.from_dict(data)
    ASSERT restored.archetype == archetype
```

### TS-34-P6: Per-Spec Aggregation Correct

**Property:** Property 6 from design.md
**Validates:** 34-REQ-4.1, 34-REQ-4.2
**Type:** property
**Description:** Per-spec costs sum correctly.

**For any:** list of SessionRecords with random specs and costs
**Invariant:** Per-spec totals equal sum of records with matching spec prefix.

**Assertion pseudocode:**
```
FOR ANY records IN lists(session_records_with_random_specs()):
    report = build_status_report_from_records(records)
    FOR EACH spec, expected_cost IN manual_aggregation(records):
        ASSERT abs(report.cost_by_spec[spec] - expected_cost) < 0.0001
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 34-REQ-1.1 | TS-34-1 | unit |
| 34-REQ-1.2 | TS-34-2 | unit |
| 34-REQ-1.3 | TS-34-3 | unit |
| 34-REQ-1.4 | TS-34-4 | unit |
| 34-REQ-1.5 | TS-34-5 | unit |
| 34-REQ-1.E1 | TS-34-E1 | unit |
| 34-REQ-1.E2 | TS-34-E2 | unit |
| 34-REQ-2.1 | TS-34-6 | unit |
| 34-REQ-2.2 | TS-34-6 | unit |
| 34-REQ-2.3 | TS-34-7 | unit |
| 34-REQ-2.4 | TS-34-8 | unit |
| 34-REQ-2.E1 | TS-34-E3 | unit |
| 34-REQ-2.E2 | TS-34-E4 | unit |
| 34-REQ-3.1 | TS-34-9 | unit |
| 34-REQ-3.2 | TS-34-10 | unit |
| 34-REQ-3.3 | TS-34-11 | unit |
| 34-REQ-3.E1 | TS-34-E5 | unit |
| 34-REQ-4.1 | TS-34-12 | unit |
| 34-REQ-4.2 | TS-34-13 | unit |
| 34-REQ-4.E1 | TS-34-E6 | unit |
| 34-REQ-5.1 | TS-34-6 | unit |
| 34-REQ-5.2 | TS-34-14 | unit |
| Property 1 | TS-34-P1 | property |
| Property 2 | TS-34-P2 | property |
| Property 3 | TS-34-P3 | property |
| Property 4 | TS-34-P4 | property |
| Property 5 | TS-34-P5 | property |
| Property 6 | TS-34-P6 | property |
