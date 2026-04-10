> **SUPERSEDED** by spec 89_simplify_routing.

# Test Specification: Archetype Model Tier Defaults

## Overview

Tests verify that the archetype registry defaults, the escalation ladder
ceiling, the config override priority chain, and the end-to-end model
selection all behave correctly after the tier reassignment.

## Test Cases

### TS-57-1: Skeptic Default Tier Is ADVANCED

**Requirement:** 57-REQ-1.1
**Type:** unit
**Description:** Verify the Skeptic archetype entry defaults to ADVANCED.

**Preconditions:**
- No config overrides applied.

**Input:**
- Look up `ARCHETYPE_REGISTRY["skeptic"]`.

**Expected:**
- `default_model_tier == "ADVANCED"`

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["skeptic"]
ASSERT entry.default_model_tier == "ADVANCED"
```

### TS-57-2: Oracle Default Tier Is ADVANCED

**Requirement:** 57-REQ-1.2
**Type:** unit
**Description:** Verify the Oracle archetype entry defaults to ADVANCED.

**Preconditions:**
- No config overrides applied.

**Input:**
- Look up `ARCHETYPE_REGISTRY["oracle"]`.

**Expected:**
- `default_model_tier == "ADVANCED"`

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["oracle"]
ASSERT entry.default_model_tier == "ADVANCED"
```

### TS-57-3: Verifier Default Tier Is ADVANCED

**Requirement:** 57-REQ-1.3
**Type:** unit
**Description:** Verify the Verifier archetype entry defaults to ADVANCED.

**Preconditions:**
- No config overrides applied.

**Input:**
- Look up `ARCHETYPE_REGISTRY["verifier"]`.

**Expected:**
- `default_model_tier == "ADVANCED"`

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["verifier"]
ASSERT entry.default_model_tier == "ADVANCED"
```

### TS-57-4: Coder Default Tier Is STANDARD

**Requirement:** 57-REQ-1.4
**Type:** unit
**Description:** Verify the Coder archetype entry defaults to STANDARD.

**Preconditions:**
- No config overrides applied.

**Input:**
- Look up `ARCHETYPE_REGISTRY["coder"]`.

**Expected:**
- `default_model_tier == "STANDARD"`

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["coder"]
ASSERT entry.default_model_tier == "STANDARD"
```

### TS-57-5: Remaining Archetypes Default to STANDARD

**Requirement:** 57-REQ-1.5
**Type:** unit
**Description:** Verify Auditor, Librarian, Cartographer, and Coordinator all default to STANDARD.

**Preconditions:**
- No config overrides applied.

**Input:**
- Look up each archetype in `ARCHETYPE_REGISTRY`.

**Expected:**
- All four have `default_model_tier == "STANDARD"`

**Assertion pseudocode:**
```
FOR name IN ["auditor", "librarian", "cartographer", "coordinator"]:
    entry = ARCHETYPE_REGISTRY[name]
    ASSERT entry.default_model_tier == "STANDARD"
```

### TS-57-6: Escalation Ladder Ceiling Is Always ADVANCED

**Requirement:** 57-REQ-2.1
**Type:** unit
**Description:** Verify that the orchestrator's `_assess_node` creates an escalation ladder with `tier_ceiling = ADVANCED`.

**Preconditions:**
- Orchestrator initialized with a graph containing a Coder node.
- Assessment pipeline is None (fallback path).

**Input:**
- Call `_assess_node(node_id)` for a Coder node.

**Expected:**
- The created `EscalationLadder` has `_tier_ceiling == ModelTier.ADVANCED`.

**Assertion pseudocode:**
```
orchestrator._assess_node("spec:1")
ladder = orchestrator._routing.ladders["spec:1"]
ASSERT ladder._tier_ceiling == ModelTier.ADVANCED
```

### TS-57-7: STANDARD Agent Escalates to ADVANCED

**Requirement:** 57-REQ-2.2
**Type:** unit
**Description:** Verify that a STANDARD-starting ladder escalates to ADVANCED after retries exhausted.

**Preconditions:**
- `EscalationLadder(starting_tier=STANDARD, tier_ceiling=ADVANCED, retries_before_escalation=1)`.

**Input:**
- Record 2 failures (1 retry + 1 to trigger escalation).

**Expected:**
- `current_tier == ModelTier.ADVANCED` after the 2nd failure.

**Assertion pseudocode:**
```
ladder = EscalationLadder(STANDARD, ADVANCED, retries_before_escalation=1)
ladder.record_failure()  # retry at STANDARD
ladder.record_failure()  # exhausted at STANDARD, escalate
ASSERT ladder.current_tier == ModelTier.ADVANCED
ASSERT ladder.is_exhausted == False
```

### TS-57-8: ADVANCED Agent Blocks After Exhaustion

**Requirement:** 57-REQ-2.3
**Type:** unit
**Description:** Verify that an ADVANCED-starting ladder becomes exhausted (no further escalation).

**Preconditions:**
- `EscalationLadder(starting_tier=ADVANCED, tier_ceiling=ADVANCED, retries_before_escalation=1)`.

**Input:**
- Record 2 failures.

**Expected:**
- `is_exhausted == True` after the 2nd failure.
- `current_tier` remains `ADVANCED`.

**Assertion pseudocode:**
```
ladder = EscalationLadder(ADVANCED, ADVANCED, retries_before_escalation=1)
ladder.record_failure()  # retry at ADVANCED
ladder.record_failure()  # exhausted, no higher tier
ASSERT ladder.is_exhausted == True
ASSERT ladder.current_tier == ModelTier.ADVANCED
```

### TS-57-9: Config Override Takes Precedence

**Requirement:** 57-REQ-3.1
**Type:** unit
**Description:** Verify that a config override for an archetype takes precedence over the registry default.

**Preconditions:**
- Config with `archetypes.models = {"coder": "ADVANCED"}`.

**Input:**
- Call `_resolve_model_tier()` for a Coder node.

**Expected:**
- Returns `"ADVANCED"` (config override), not `"STANDARD"` (registry default).

**Assertion pseudocode:**
```
config = make_config(archetypes_models={"coder": "ADVANCED"})
runner = NodeSessionRunner("spec:1", config, archetype="coder")
tier = runner._resolve_model_tier()
ASSERT tier == "ADVANCED"
```

### TS-57-10: No Config Override Falls Back to Registry

**Requirement:** 57-REQ-3.2
**Type:** unit
**Description:** Verify that without a config override, the registry default is used.

**Preconditions:**
- Config with empty `archetypes.models`.

**Input:**
- Call `_resolve_model_tier()` for a Skeptic node.

**Expected:**
- Returns `"ADVANCED"` (registry default).

**Assertion pseudocode:**
```
config = make_config(archetypes_models={})
runner = NodeSessionRunner("spec:0:skeptic", config, archetype="skeptic")
tier = runner._resolve_model_tier()
ASSERT tier == "ADVANCED"
```

### TS-57-11: Assessed Tier Overrides Everything

**Requirement:** 57-REQ-3.3
**Type:** unit
**Description:** Verify that an assessed tier from adaptive routing overrides both config and registry.

**Preconditions:**
- Config with `archetypes.models = {"coder": "ADVANCED"}`.
- `assessed_tier = ModelTier.SIMPLE`.

**Input:**
- Create `NodeSessionRunner` with `assessed_tier=SIMPLE`.

**Expected:**
- `_resolved_model_id` corresponds to the SIMPLE tier model.

**Assertion pseudocode:**
```
config = make_config(archetypes_models={"coder": "ADVANCED"})
runner = NodeSessionRunner("spec:1", config, archetype="coder", assessed_tier=ModelTier.SIMPLE)
ASSERT runner._resolved_model_id == "claude-haiku-4-5"
```

## Property Test Cases

### TS-57-P1: All Registry Defaults Match Spec

**Property:** Property 1 from design.md
**Validates:** 57-REQ-1.1, 57-REQ-1.2, 57-REQ-1.3, 57-REQ-1.4, 57-REQ-1.5
**Type:** property
**Description:** For any archetype in the registry, the default tier matches the specified mapping.

**For any:** archetype name drawn from `ARCHETYPE_REGISTRY.keys()`
**Invariant:** If name in `{skeptic, oracle, verifier}`, tier is ADVANCED; otherwise tier is STANDARD.

**Assertion pseudocode:**
```
advanced_set = {"skeptic", "oracle", "verifier"}
FOR ANY name IN ARCHETYPE_REGISTRY.keys():
    entry = ARCHETYPE_REGISTRY[name]
    IF name IN advanced_set:
        ASSERT entry.default_model_tier == "ADVANCED"
    ELSE:
        ASSERT entry.default_model_tier == "STANDARD"
```

### TS-57-P2: Ceiling Is Always ADVANCED

**Property:** Property 2 from design.md
**Validates:** 57-REQ-2.1
**Type:** property
**Description:** For any archetype, the escalation ceiling is ADVANCED.

**For any:** archetype name drawn from `ARCHETYPE_REGISTRY.keys()`
**Invariant:** An escalation ladder created for the archetype has `tier_ceiling == ADVANCED`.

**Assertion pseudocode:**
```
FOR ANY name IN ARCHETYPE_REGISTRY.keys():
    entry = ARCHETYPE_REGISTRY[name]
    starting = ModelTier(entry.default_model_tier)
    ladder = EscalationLadder(starting, ModelTier.ADVANCED, retries_before_escalation=1)
    ASSERT ladder._tier_ceiling == ModelTier.ADVANCED
```

### TS-57-P3: STANDARD Agents Reach ADVANCED Before Exhaustion

**Property:** Property 3 from design.md
**Validates:** 57-REQ-2.2
**Type:** property
**Description:** For any retries_before_escalation N, a STANDARD-starting ladder reaches ADVANCED before exhausting.

**For any:** `retries_before_escalation` in range [0, 3]
**Invariant:** After `N + 1` failures, `current_tier == ADVANCED` and `is_exhausted == False`.

**Assertion pseudocode:**
```
FOR ANY n IN range(0, 4):
    ladder = EscalationLadder(STANDARD, ADVANCED, retries_before_escalation=n)
    FOR i IN range(n + 1):
        ladder.record_failure()
    ASSERT ladder.current_tier == ModelTier.ADVANCED
    ASSERT ladder.is_exhausted == False
```

### TS-57-P4: ADVANCED Agents Exhaust Without Escalation

**Property:** Property 4 from design.md
**Validates:** 57-REQ-2.3
**Type:** property
**Description:** For any retries_before_escalation N, an ADVANCED-starting ladder exhausts without escalation.

**For any:** `retries_before_escalation` in range [0, 3]
**Invariant:** After `N + 1` failures, `is_exhausted == True` and `escalation_count == 0`.

**Assertion pseudocode:**
```
FOR ANY n IN range(0, 4):
    ladder = EscalationLadder(ADVANCED, ADVANCED, retries_before_escalation=n)
    FOR i IN range(n + 1):
        ladder.record_failure()
    ASSERT ladder.is_exhausted == True
    ASSERT ladder.escalation_count == 0
```

### TS-57-P5: Config Override Precedence

**Property:** Property 5 from design.md
**Validates:** 57-REQ-3.1, 57-REQ-3.2
**Type:** property
**Description:** For any archetype with a config override, the override is returned; without, the registry default is returned.

**For any:** archetype name drawn from `ARCHETYPE_REGISTRY.keys()`, optional override tier from `{SIMPLE, STANDARD, ADVANCED}`
**Invariant:** `_resolve_model_tier()` returns the override when set, otherwise the registry default.

**Assertion pseudocode:**
```
FOR ANY name IN ARCHETYPE_REGISTRY.keys():
    FOR ANY override IN [None, "SIMPLE", "STANDARD", "ADVANCED"]:
        config = make_config(archetypes_models={name: override} if override else {})
        runner = make_runner(archetype=name, config=config)
        result = runner._resolve_model_tier()
        IF override is not None:
            ASSERT result == override
        ELSE:
            ASSERT result == ARCHETYPE_REGISTRY[name].default_model_tier
```

### TS-57-12: Documentation Lists Default Tiers

**Requirement:** 57-REQ-4.1
**Type:** unit
**Description:** Verify the archetypes documentation contains default model tier for each archetype.

**Preconditions:**
- `docs/archetypes.md` exists.

**Input:**
- Read the file content.

**Expected:**
- Contains a table or list showing each archetype name and its default tier.
- Skeptic, Oracle, Verifier listed as ADVANCED.
- Coder, Auditor listed as STANDARD.

**Assertion pseudocode:**
```
content = read_file("docs/archetypes.md")
ASSERT "ADVANCED" in content
ASSERT "STANDARD" in content
FOR name IN ["skeptic", "oracle", "verifier"]:
    ASSERT name appears near "ADVANCED" in the document
```

### TS-57-13: Documentation Describes Config Override

**Requirement:** 57-REQ-4.2
**Type:** unit
**Description:** Verify the documentation explains how to override tiers via config.toml.

**Preconditions:**
- `docs/archetypes.md` exists.

**Input:**
- Read the file content.

**Expected:**
- Contains reference to `archetypes.models` or `models` config key.
- Contains an example of overriding a tier.

**Assertion pseudocode:**
```
content = read_file("docs/archetypes.md")
ASSERT "models" in content
ASSERT "config" in content.lower()
```

### TS-57-14: Documentation Explains Escalation

**Requirement:** 57-REQ-4.3
**Type:** unit
**Description:** Verify the documentation explains retry-then-escalate behavior.

**Preconditions:**
- `docs/archetypes.md` exists.

**Input:**
- Read the file content.

**Expected:**
- Contains description of escalation behavior (retry then escalate to ADVANCED).

**Assertion pseudocode:**
```
content = read_file("docs/archetypes.md")
ASSERT "escalat" in content.lower()
ASSERT "retry" in content.lower() OR "retries" in content.lower()
```

## Edge Case Tests

### TS-57-E1: Unknown Archetype Falls Back to Coder

**Requirement:** 57-REQ-1.E1
**Type:** unit
**Description:** Verify that looking up an unknown archetype returns the Coder entry.

**Preconditions:**
- `ARCHETYPE_REGISTRY` does not contain `"unknown_archetype"`.

**Input:**
- `get_archetype("unknown_archetype")`

**Expected:**
- Returns the Coder entry with `default_model_tier == "STANDARD"`.

**Assertion pseudocode:**
```
entry = get_archetype("unknown_archetype")
ASSERT entry.name == "coder"
ASSERT entry.default_model_tier == "STANDARD"
```

### TS-57-E2: Assessment Pipeline Failure Uses Archetype Default with ADVANCED Ceiling

**Requirement:** 57-REQ-2.E1
**Type:** unit
**Description:** Verify that when assessment fails, the ladder uses the archetype default as starting tier and ADVANCED as ceiling.

**Preconditions:**
- Assessment pipeline raises an exception.
- Node archetype is "coder" (default tier STANDARD).

**Input:**
- Call `_assess_node()` with a failing pipeline.

**Expected:**
- Ladder created with `starting_tier=STANDARD, tier_ceiling=ADVANCED`.

**Assertion pseudocode:**
```
pipeline = FailingPipeline()
orchestrator = make_orchestrator(pipeline=pipeline)
orchestrator._assess_node("spec:1")
ladder = orchestrator._routing.ladders["spec:1"]
ASSERT ladder.current_tier == ModelTier.STANDARD
ASSERT ladder._tier_ceiling == ModelTier.ADVANCED
```

### TS-57-E3: Invalid Config Tier Raises ConfigError

**Requirement:** 57-REQ-3.E1
**Type:** unit
**Description:** Verify that an invalid tier name in config raises ConfigError.

**Preconditions:**
- Config with `archetypes.models = {"coder": "INVALID_TIER"}`.

**Input:**
- Create `NodeSessionRunner` for a coder node.

**Expected:**
- `ConfigError` is raised.

**Assertion pseudocode:**
```
config = make_config(archetypes_models={"coder": "INVALID_TIER"})
ASSERT_RAISES ConfigError:
    NodeSessionRunner("spec:1", config, archetype="coder")
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 57-REQ-1.1 | TS-57-1 | unit |
| 57-REQ-1.2 | TS-57-2 | unit |
| 57-REQ-1.3 | TS-57-3 | unit |
| 57-REQ-1.4 | TS-57-4 | unit |
| 57-REQ-1.5 | TS-57-5 | unit |
| 57-REQ-2.1 | TS-57-6 | unit |
| 57-REQ-2.2 | TS-57-7 | unit |
| 57-REQ-2.3 | TS-57-8 | unit |
| 57-REQ-3.1 | TS-57-9 | unit |
| 57-REQ-3.2 | TS-57-10 | unit |
| 57-REQ-3.3 | TS-57-11 | unit |
| 57-REQ-1.E1 | TS-57-E1 | unit |
| 57-REQ-2.E1 | TS-57-E2 | unit |
| 57-REQ-3.E1 | TS-57-E3 | unit |
| Property 1 | TS-57-P1 | property |
| Property 2 | TS-57-P2 | property |
| Property 3 | TS-57-P3 | property |
| Property 4 | TS-57-P4 | property |
| 57-REQ-4.1 | TS-57-12 | unit |
| 57-REQ-4.2 | TS-57-13 | unit |
| 57-REQ-4.3 | TS-57-14 | unit |
| Property 5 | TS-57-P5 | property |
