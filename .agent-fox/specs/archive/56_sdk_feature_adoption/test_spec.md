# Test Specification: Claude SDK Feature Adoption

## Overview

Tests cover configuration parsing, default resolution, parameter passthrough
to `ClaudeCodeOptions`, validation error rejection, and SDK compatibility
fallback. A mock `ClaudeBackend` captures the options constructed to verify
passthrough without hitting the real SDK.

## Test Cases

### TS-56-1: max_turns Config Parsing

**Requirement:** 56-REQ-1.1
**Type:** unit
**Description:** Verify `max_turns` per archetype is parsed from config.

**Preconditions:**
- Config TOML contains `[archetypes.max_turns]` with `coder = 150`.

**Input:**
- Load config from TOML string.

**Expected:**
- `config.archetypes.max_turns["coder"]` == 150.

**Assertion pseudocode:**
```
config = load_config(toml_with_max_turns)
ASSERT config.archetypes.max_turns["coder"] == 150
```

### TS-56-2: max_turns Passed to ClaudeCodeOptions

**Requirement:** 56-REQ-1.2
**Type:** unit
**Description:** Verify `max_turns` is forwarded to SDK options.

**Preconditions:**
- Mock backend captures constructed options.

**Input:**
- Execute session with archetype "oracle", max_turns=50.

**Expected:**
- Captured options contain `max_turns=50`.

**Assertion pseudocode:**
```
options = capture_options_from_execute(archetype="oracle", max_turns=50)
ASSERT options.max_turns == 50
```

### TS-56-3: max_turns Defaults Per Archetype

**Requirement:** 56-REQ-1.3
**Type:** unit
**Description:** Verify default max_turns values for each archetype.

**Preconditions:**
- No max_turns override in config.

**Input:**
- Resolve max_turns for each archetype.

**Expected:**
- coder=200, oracle=50, skeptic=50, verifier=75, auditor=50,
  librarian=100, cartographer=100, coordinator=30.

**Assertion pseudocode:**
```
expected = {"coder": 200, "oracle": 50, "skeptic": 50, "verifier": 75,
            "auditor": 50, "librarian": 100, "cartographer": 100,
            "coordinator": 30}
for arch, turns in expected.items():
    ASSERT resolve_max_turns(default_config, arch) == turns
```

### TS-56-4: max_turns Zero Means Unlimited

**Requirement:** 56-REQ-1.4
**Type:** unit
**Description:** Verify max_turns=0 results in no max_turns in options.

**Preconditions:**
- Config sets `coder = 0`.

**Input:**
- Resolve max_turns for "coder".

**Expected:**
- Returns None (no max_turns passed to SDK).

**Assertion pseudocode:**
```
ASSERT resolve_max_turns(config_with_zero, "coder") is None
```

### TS-56-5: max_budget_usd Config Parsing

**Requirement:** 56-REQ-2.1
**Type:** unit
**Description:** Verify `max_budget_usd` is parsed from config.

**Preconditions:**
- Config TOML contains `max_budget_usd = 5.0` under `[orchestrator]`.

**Input:**
- Load config.

**Expected:**
- `config.orchestrator.max_budget_usd` == 5.0.

**Assertion pseudocode:**
```
config = load_config(toml_with_budget)
ASSERT config.orchestrator.max_budget_usd == 5.0
```

### TS-56-6: max_budget_usd Passed to ClaudeCodeOptions

**Requirement:** 56-REQ-2.2
**Type:** unit
**Description:** Verify `max_budget_usd` is forwarded to SDK options.

**Preconditions:**
- Mock backend captures options.

**Input:**
- Execute session with max_budget_usd=3.0.

**Expected:**
- Captured options contain `max_budget_usd=3.0`.

**Assertion pseudocode:**
```
options = capture_options_from_execute(max_budget_usd=3.0)
ASSERT options.max_budget_usd == 3.0
```

### TS-56-7: max_budget_usd Default

**Requirement:** 56-REQ-2.3
**Type:** unit
**Description:** Verify default max_budget_usd is 2.0.

**Preconditions:**
- Default config (no overrides).

**Input:**
- Load default config.

**Expected:**
- `config.orchestrator.max_budget_usd` == 2.0.

**Assertion pseudocode:**
```
config = load_default_config()
ASSERT config.orchestrator.max_budget_usd == 2.0
```

### TS-56-8: fallback_model Config Parsing

**Requirement:** 56-REQ-3.1
**Type:** unit
**Description:** Verify `fallback_model` is parsed from config.

**Preconditions:**
- Config TOML contains `fallback_model = "claude-haiku-4-5"` under `[models]`.

**Input:**
- Load config.

**Expected:**
- `config.models.fallback_model` == "claude-haiku-4-5".

**Assertion pseudocode:**
```
config = load_config(toml_with_fallback)
ASSERT config.models.fallback_model == "claude-haiku-4-5"
```

### TS-56-9: fallback_model Passed to ClaudeCodeOptions

**Requirement:** 56-REQ-3.2
**Type:** unit
**Description:** Verify `fallback_model` is forwarded to SDK options.

**Preconditions:**
- Mock backend captures options.

**Input:**
- Execute session with fallback_model="claude-sonnet-4-6".

**Expected:**
- Captured options contain `fallback_model="claude-sonnet-4-6"`.

**Assertion pseudocode:**
```
options = capture_options_from_execute(fallback_model="claude-sonnet-4-6")
ASSERT options.fallback_model == "claude-sonnet-4-6"
```

### TS-56-10: fallback_model Default

**Requirement:** 56-REQ-3.3
**Type:** unit
**Description:** Verify default fallback_model is "claude-sonnet-4-6".

**Preconditions:**
- Default config.

**Input:**
- Load default config.

**Expected:**
- `config.models.fallback_model` == "claude-sonnet-4-6".

**Assertion pseudocode:**
```
config = load_default_config()
ASSERT config.models.fallback_model == "claude-sonnet-4-6"
```

### TS-56-11: fallback_model Empty String Means No Fallback

**Requirement:** 56-REQ-3.4
**Type:** unit
**Description:** Verify empty fallback_model results in no fallback in options.

**Preconditions:**
- Config sets `fallback_model = ""`.

**Input:**
- Resolve fallback for session.

**Expected:**
- No `fallback_model` passed to SDK options.

**Assertion pseudocode:**
```
options = capture_options_from_execute(fallback_model="")
ASSERT "fallback_model" not in options OR options.fallback_model is None
```

### TS-56-12: Thinking Config Parsing

**Requirement:** 56-REQ-4.1
**Type:** unit
**Description:** Verify thinking config per archetype is parsed.

**Preconditions:**
- Config TOML contains `[archetypes.thinking.coder]` with
  `mode = "enabled"`, `budget_tokens = 20000`.

**Input:**
- Load config.

**Expected:**
- `config.archetypes.thinking["coder"].mode` == "enabled".
- `config.archetypes.thinking["coder"].budget_tokens` == 20000.

**Assertion pseudocode:**
```
config = load_config(toml_with_thinking)
ASSERT config.archetypes.thinking["coder"].mode == "enabled"
ASSERT config.archetypes.thinking["coder"].budget_tokens == 20000
```

### TS-56-13: Thinking Passed to ClaudeCodeOptions

**Requirement:** 56-REQ-4.2
**Type:** unit
**Description:** Verify thinking config is forwarded to SDK options.

**Preconditions:**
- Mock backend captures options.

**Input:**
- Execute session with thinking={"type": "adaptive", "budget_tokens": 10000}.

**Expected:**
- Captured options contain `thinking` dict.

**Assertion pseudocode:**
```
options = capture_options_from_execute(
    thinking={"type": "adaptive", "budget_tokens": 10000}
)
ASSERT options.thinking["type"] == "adaptive"
ASSERT options.thinking["budget_tokens"] == 10000
```

### TS-56-14: Thinking Defaults

**Requirement:** 56-REQ-4.3
**Type:** unit
**Description:** Verify coder defaults to adaptive thinking, others disabled.

**Preconditions:**
- Default config.

**Input:**
- Resolve thinking for coder and oracle.

**Expected:**
- Coder: mode=adaptive, budget_tokens=10000.
- Oracle: None (disabled).

**Assertion pseudocode:**
```
coder_thinking = resolve_thinking(default_config, "coder")
ASSERT coder_thinking == {"type": "adaptive", "budget_tokens": 10000}

oracle_thinking = resolve_thinking(default_config, "oracle")
ASSERT oracle_thinking is None
```

### TS-56-15: Protocol Extended With New Parameters

**Requirement:** 56-REQ-5.3
**Type:** unit
**Description:** Verify `AgentBackend.execute()` signature includes new
optional parameters.

**Preconditions:**
- `AgentBackend` is importable.

**Input:**
- Inspect `execute` method signature.

**Expected:**
- Signature includes `max_turns`, `max_budget_usd`, `fallback_model`,
  `thinking` as keyword-only parameters.

**Assertion pseudocode:**
```
import inspect
sig = inspect.signature(AgentBackend.execute)
param_names = set(sig.parameters.keys())
ASSERT "max_turns" in param_names
ASSERT "max_budget_usd" in param_names
ASSERT "fallback_model" in param_names
ASSERT "thinking" in param_names
```

## Property Test Cases

### TS-56-P1: Turn Limit Passthrough Invariant

**Property:** Property 1 from design.md
**Validates:** 56-REQ-1.1, 56-REQ-1.2
**Type:** property
**Description:** For any positive max_turns, the value passes through to
options unchanged.

**For any:** max_turns in integers(1, 1000)
**Invariant:** Captured options.max_turns == input max_turns.

**Assertion pseudocode:**
```
FOR ANY max_turns IN integers(1, 1000):
    options = capture_options(max_turns=max_turns)
    ASSERT options.max_turns == max_turns
```

### TS-56-P2: Zero Turns Means Unlimited

**Property:** Property 2 from design.md
**Validates:** 56-REQ-1.4
**Type:** property
**Description:** max_turns=0 always results in no max_turns in options.

**For any:** archetype in ARCHETYPE_REGISTRY.keys()
**Invariant:** resolve_max_turns(config_with_zero, archetype) is None.

**Assertion pseudocode:**
```
FOR ANY archetype IN ARCHETYPE_REGISTRY.keys():
    config = make_config(max_turns={archetype: 0})
    ASSERT resolve_max_turns(config, archetype) is None
```

### TS-56-P3: Budget Cap Passthrough Invariant

**Property:** Property 3 from design.md
**Validates:** 56-REQ-2.1, 56-REQ-2.2
**Type:** property
**Description:** For any positive budget, the value passes through unchanged.

**For any:** budget in floats(0.01, 100.0)
**Invariant:** Captured options.max_budget_usd == budget.

**Assertion pseudocode:**
```
FOR ANY budget IN floats(0.01, 100.0):
    options = capture_options(max_budget_usd=budget)
    ASSERT options.max_budget_usd == budget
```

### TS-56-P4: Fallback Model Passthrough Invariant

**Property:** Property 4 from design.md
**Validates:** 56-REQ-3.1, 56-REQ-3.2
**Type:** property
**Description:** For any non-empty model string, it passes through unchanged.

**For any:** model_id in text(min_size=1, alphabet=ascii_lowercase+digits+"-")
**Invariant:** Captured options.fallback_model == model_id.

**Assertion pseudocode:**
```
FOR ANY model_id IN text(min_size=1):
    options = capture_options(fallback_model=model_id)
    ASSERT options.fallback_model == model_id
```

### TS-56-P5: Thinking Passthrough Invariant

**Property:** Property 5 from design.md
**Validates:** 56-REQ-4.1, 56-REQ-4.2
**Type:** property
**Description:** For any non-disabled thinking config, it passes through.

**For any:** mode in {"enabled", "adaptive"}, budget in integers(1, 50000)
**Invariant:** Captured options.thinking matches input.

**Assertion pseudocode:**
```
FOR ANY mode IN {"enabled", "adaptive"}, budget IN integers(1, 50000):
    thinking = {"type": mode, "budget_tokens": budget}
    options = capture_options(thinking=thinking)
    ASSERT options.thinking == thinking
```

### TS-56-P6: Config Override Wins Over Defaults

**Property:** Property 6 from design.md
**Validates:** 56-REQ-5.1
**Type:** property
**Description:** Config overrides always take precedence over archetype
registry defaults.

**For any:** archetype in ARCHETYPE_REGISTRY, override_turns in integers(1, 500)
**Invariant:** resolve_max_turns returns the config value, not the default.

**Assertion pseudocode:**
```
FOR ANY archetype IN ARCHETYPE_REGISTRY, override IN integers(1, 500):
    config = make_config(max_turns={archetype: override})
    ASSERT resolve_max_turns(config, archetype) == override
```

### TS-56-P7: Validation Rejects Invalid Config

**Property:** Property 7 from design.md
**Validates:** 56-REQ-1.E1, 56-REQ-2.E2, 56-REQ-4.E1, 56-REQ-4.E2
**Type:** property
**Description:** Invalid config values always raise validation errors.

**For any:** negative_int in integers(-1000, -1)
**Invariant:** Config construction raises ValidationError.

**Assertion pseudocode:**
```
FOR ANY neg IN integers(-1000, -1):
    ASSERT_RAISES ValidationError:
        make_config(max_budget_usd=neg)
```

### TS-56-P8: SDK Compatibility Fallback

**Property:** Property 8 from design.md
**Validates:** 56-REQ-5.E1
**Type:** unit
**Description:** When SDK raises TypeError on a new param, execution
continues without that param.

**For any:** unsupported param name in {"max_turns", "thinking", "fallback_model"}
**Invariant:** Session completes (not raises) and warning is logged.

**Assertion pseudocode:**
```
FOR ANY param IN {"max_turns", "thinking", "fallback_model"}:
    backend = make_backend_that_rejects(param)
    result = run_session_with(backend, **{param: some_value})
    ASSERT result.status != "failed" OR "TypeError" not in result.error_message
```

## Edge Case Tests

### TS-56-E1: Negative max_turns Rejected

**Requirement:** 56-REQ-1.E1
**Type:** unit
**Description:** Verify negative max_turns raises validation error.

**Preconditions:**
- Config TOML contains `coder = -1` under `[archetypes.max_turns]`.

**Input:**
- Load config.

**Expected:**
- Raises ValidationError.

**Assertion pseudocode:**
```
ASSERT_RAISES ValidationError:
    load_config(toml_with_negative_max_turns)
```

### TS-56-E2: Zero Budget Means Unlimited

**Requirement:** 56-REQ-2.E1
**Type:** unit
**Description:** Verify max_budget_usd=0 results in no budget cap.

**Preconditions:**
- Config sets `max_budget_usd = 0`.

**Input:**
- Resolve budget for session.

**Expected:**
- No `max_budget_usd` passed to SDK options (or None).

**Assertion pseudocode:**
```
options = capture_options(max_budget_usd=0.0)
ASSERT options.max_budget_usd is None OR "max_budget_usd" not in options
```

### TS-56-E3: Negative Budget Rejected

**Requirement:** 56-REQ-2.E2
**Type:** unit
**Description:** Verify negative max_budget_usd raises validation error.

**Preconditions:**
- Config TOML contains `max_budget_usd = -1.0`.

**Input:**
- Load config.

**Expected:**
- Raises ValidationError.

**Assertion pseudocode:**
```
ASSERT_RAISES ValidationError:
    load_config(toml_with_negative_budget)
```

### TS-56-E4: Unknown Fallback Model Logs Warning

**Requirement:** 56-REQ-3.E1
**Type:** unit
**Description:** Verify unknown fallback model logs warning but doesn't fail.

**Preconditions:**
- Config sets `fallback_model = "unknown-model-99"`.

**Input:**
- Load config and resolve fallback.

**Expected:**
- No exception raised. Warning logged about unknown model.

**Assertion pseudocode:**
```
with capture_logs() as logs:
    config = load_config(toml_with_unknown_fallback)
    resolve_fallback(config)
ASSERT any("unknown-model-99" in log for log in logs.warnings)
```

### TS-56-E5: Invalid Thinking Mode Rejected

**Requirement:** 56-REQ-4.E1
**Type:** unit
**Description:** Verify unrecognised thinking mode raises validation error.

**Preconditions:**
- Config TOML contains `mode = "turbo"` under `[archetypes.thinking.coder]`.

**Input:**
- Load config.

**Expected:**
- Raises ValidationError.

**Assertion pseudocode:**
```
ASSERT_RAISES ValidationError:
    load_config(toml_with_invalid_mode)
```

### TS-56-E6: Zero Budget Tokens With Enabled Mode Rejected

**Requirement:** 56-REQ-4.E2
**Type:** unit
**Description:** Verify budget_tokens=0 with mode=enabled raises error.

**Preconditions:**
- Config TOML: mode="enabled", budget_tokens=0.

**Input:**
- Load config.

**Expected:**
- Raises ValidationError.

**Assertion pseudocode:**
```
ASSERT_RAISES ValidationError:
    load_config(toml_with_zero_budget_enabled)
```

### TS-56-E7: SDK TypeError Fallback

**Requirement:** 56-REQ-5.E1
**Type:** integration
**Description:** Verify TypeError from SDK is caught and session retries
without the unsupported parameter.

**Preconditions:**
- Mock ClaudeCodeOptions that raises TypeError on `thinking`.

**Input:**
- Execute session with thinking config.

**Expected:**
- Session completes. Warning logged about unsupported parameter.

**Assertion pseudocode:**
```
with mock_sdk_options_rejects("thinking"), capture_logs() as logs:
    result = run_session(thinking={"type": "adaptive", "budget_tokens": 10000})
ASSERT result.status in ("completed", "failed")  # not raised
ASSERT any("unsupported" in log.lower() or "TypeError" in log for log in logs.warnings)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 56-REQ-1.1 | TS-56-1, TS-56-P1 | unit, property |
| 56-REQ-1.2 | TS-56-2, TS-56-P1 | unit, property |
| 56-REQ-1.3 | TS-56-3 | unit |
| 56-REQ-1.4 | TS-56-4, TS-56-P2 | unit, property |
| 56-REQ-1.E1 | TS-56-E1, TS-56-P7 | unit, property |
| 56-REQ-2.1 | TS-56-5, TS-56-P3 | unit, property |
| 56-REQ-2.2 | TS-56-6, TS-56-P3 | unit, property |
| 56-REQ-2.3 | TS-56-7 | unit |
| 56-REQ-2.4 | TS-56-6 | unit |
| 56-REQ-2.E1 | TS-56-E2 | unit |
| 56-REQ-2.E2 | TS-56-E3, TS-56-P7 | unit, property |
| 56-REQ-3.1 | TS-56-8, TS-56-P4 | unit, property |
| 56-REQ-3.2 | TS-56-9, TS-56-P4 | unit, property |
| 56-REQ-3.3 | TS-56-10 | unit |
| 56-REQ-3.4 | TS-56-11 | unit |
| 56-REQ-3.E1 | TS-56-E4 | unit |
| 56-REQ-4.1 | TS-56-12, TS-56-P5 | unit, property |
| 56-REQ-4.2 | TS-56-13, TS-56-P5 | unit, property |
| 56-REQ-4.3 | TS-56-14 | unit |
| 56-REQ-4.4 | TS-56-13 | unit |
| 56-REQ-4.E1 | TS-56-E5, TS-56-P7 | unit, property |
| 56-REQ-4.E2 | TS-56-E6, TS-56-P7 | unit, property |
| 56-REQ-5.1 | TS-56-1, TS-56-P6 | unit, property |
| 56-REQ-5.2 | TS-56-2, TS-56-6, TS-56-9, TS-56-13 | unit |
| 56-REQ-5.3 | TS-56-15 | unit |
| 56-REQ-5.E1 | TS-56-E7, TS-56-P8 | integration, unit |
| Property 1 | TS-56-P1 | property |
| Property 2 | TS-56-P2 | property |
| Property 3 | TS-56-P3 | property |
| Property 4 | TS-56-P4 | property |
| Property 5 | TS-56-P5 | property |
| Property 6 | TS-56-P6 | property |
| Property 7 | TS-56-P7 | property |
| Property 8 | TS-56-P8 | unit |
