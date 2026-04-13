# Test Specification: Archetype Model v3 — Mode Infrastructure

## Overview

Tests verify that the mode infrastructure correctly extends the archetype
system. Acceptance criterion tests validate individual behaviors. Property
tests verify invariants across generated configurations. Smoke tests trace
end-to-end resolution paths.

## Test Cases

### TS-97-1: ModeConfig Dataclass Defaults

**Requirement:** 97-REQ-1.1
**Type:** unit
**Description:** Verify ModeConfig fields default to None.

**Preconditions:** None.

**Input:** `ModeConfig()` (no arguments)

**Expected:** All fields (`templates`, `injection`, `allowlist`, `model_tier`,
`max_turns`, `thinking_mode`, `thinking_budget`, `retry_predecessor`) are
`None`.

**Assertion pseudocode:**
```
mc = ModeConfig()
ASSERT mc.templates IS None
ASSERT mc.injection IS None
ASSERT mc.allowlist IS None
ASSERT mc.model_tier IS None
ASSERT mc.max_turns IS None
ASSERT mc.thinking_mode IS None
ASSERT mc.thinking_budget IS None
ASSERT mc.retry_predecessor IS None
```

### TS-97-2: ArchetypeEntry Modes Field

**Requirement:** 97-REQ-1.2
**Type:** unit
**Description:** Verify ArchetypeEntry has a modes dict defaulting to empty.

**Preconditions:** None.

**Input:** `ArchetypeEntry(name="test")`

**Expected:** `entry.modes == {}`

**Assertion pseudocode:**
```
entry = ArchetypeEntry(name="test")
ASSERT entry.modes == {}
ASSERT isinstance(entry.modes, dict)
```

### TS-97-3: resolve_effective_config With Valid Mode

**Requirement:** 97-REQ-1.3, 97-REQ-1.5
**Type:** unit
**Description:** Verify mode overrides are applied and non-overridden fields
are inherited.

**Preconditions:** An ArchetypeEntry with a mode that overrides `model_tier`
and `max_turns` but not `templates`.

**Input:**
```
entry = ArchetypeEntry(
    name="test",
    templates=["base.md"],
    default_model_tier="STANDARD",
    default_max_turns=200,
    modes={"fast": ModeConfig(model_tier="SIMPLE", max_turns=50)}
)
```

**Expected:** Resolved entry has `model_tier="SIMPLE"`,
`max_turns=50`, `templates=["base.md"]`.

**Assertion pseudocode:**
```
result = resolve_effective_config(entry, "fast")
ASSERT result.default_model_tier == "SIMPLE"
ASSERT result.default_max_turns == 50
ASSERT result.templates == ["base.md"]
```

### TS-97-4: resolve_effective_config With None Mode

**Requirement:** 97-REQ-1.4
**Type:** unit
**Description:** Verify None mode returns base entry unchanged.

**Preconditions:** An ArchetypeEntry with modes defined.

**Input:** `resolve_effective_config(entry, None)`

**Expected:** Result equals base entry (base fields preserved).

**Assertion pseudocode:**
```
entry = ArchetypeEntry(name="test", default_model_tier="ADVANCED",
    modes={"fast": ModeConfig(model_tier="SIMPLE")})
result = resolve_effective_config(entry, None)
ASSERT result.default_model_tier == "ADVANCED"
```

### TS-97-5: Node Mode Field

**Requirement:** 97-REQ-2.1
**Type:** unit
**Description:** Verify Node has a mode field defaulting to None.

**Preconditions:** None.

**Input:** `Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)`

**Expected:** `node.mode is None`

**Assertion pseudocode:**
```
node = Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)
ASSERT node.mode IS None
node_with_mode = Node(id="s:1", spec_name="s", group_number=1, title="t",
    optional=False, mode="pre-review")
ASSERT node_with_mode.mode == "pre-review"
```

### TS-97-6: Node Serialization Round-Trip

**Requirement:** 97-REQ-2.2
**Type:** unit
**Description:** Verify mode persists through JSON serialization.

**Preconditions:** Node with mode="pre-review".

**Input:** Serialize node to dict/JSON, deserialize back.

**Expected:** Deserialized node has `mode="pre-review"`.

**Assertion pseudocode:**
```
node = Node(id="s:0", spec_name="s", group_number=0, title="t",
    optional=False, mode="pre-review")
serialized = serialize_node(node)
ASSERT "mode" in serialized
ASSERT serialized["mode"] == "pre-review"
deserialized = deserialize_node(serialized)
ASSERT deserialized.mode == "pre-review"
```

### TS-97-7: PerArchetypeConfig Modes Field

**Requirement:** 97-REQ-3.1
**Type:** unit
**Description:** Verify PerArchetypeConfig accepts nested modes dict.

**Preconditions:** None.

**Input:**
```
config = PerArchetypeConfig(
    model_tier="STANDARD",
    modes={"pre-review": PerArchetypeConfig(allowlist=[])}
)
```

**Expected:** `config.modes["pre-review"].allowlist == []`

**Assertion pseudocode:**
```
pac = PerArchetypeConfig(
    model_tier="STANDARD",
    modes={"pre-review": PerArchetypeConfig(allowlist=[])}
)
ASSERT "pre-review" in pac.modes
ASSERT pac.modes["pre-review"].allowlist == []
```

### TS-97-8: TOML Config Parsing With Modes

**Requirement:** 97-REQ-3.2
**Type:** unit
**Description:** Verify TOML with nested mode sections parses correctly.

**Preconditions:** TOML string with `[archetypes.overrides.reviewer.modes.pre-review]`.

**Input:**
```toml
[archetypes.overrides.reviewer]
model_tier = "STANDARD"

[archetypes.overrides.reviewer.modes.pre-review]
allowlist = []
max_turns = 60
```

**Expected:** Parsed config has reviewer override with pre-review mode
containing empty allowlist and max_turns=60.

**Assertion pseudocode:**
```
config = parse_toml(toml_string)
reviewer = config.archetypes.overrides["reviewer"]
ASSERT reviewer.model_tier == "STANDARD"
pre = reviewer.modes["pre-review"]
ASSERT pre.allowlist == []
ASSERT pre.max_turns == 60
```

### TS-97-9: resolve_model_tier With Mode

**Requirement:** 97-REQ-4.1
**Type:** unit
**Description:** Verify mode-specific model tier takes precedence.

**Preconditions:** Config with archetype-level and mode-level model tier
overrides.

**Input:** `resolve_model_tier(config, "reviewer", mode="pre-review")`

**Expected:** Returns mode-level override, not archetype-level.

**Assertion pseudocode:**
```
config = make_config(overrides={
    "reviewer": PerArchetypeConfig(
        model_tier="ADVANCED",
        modes={"pre-review": PerArchetypeConfig(model_tier="SIMPLE")}
    )
})
result = resolve_model_tier(config, "reviewer", mode="pre-review")
ASSERT result == "SIMPLE"
```

### TS-97-10: resolve_model_tier Mode Fallback

**Requirement:** 97-REQ-3.3
**Type:** unit
**Description:** Verify fallback to archetype-level when mode has no override.

**Preconditions:** Config with archetype-level override but no mode-level.

**Input:** `resolve_model_tier(config, "reviewer", mode="pre-review")`

**Expected:** Returns archetype-level override.

**Assertion pseudocode:**
```
config = make_config(overrides={
    "reviewer": PerArchetypeConfig(model_tier="ADVANCED", modes={})
})
result = resolve_model_tier(config, "reviewer", mode="pre-review")
ASSERT result == "ADVANCED"
```

### TS-97-11: resolve_security_config With Empty Allowlist Mode

**Requirement:** 97-REQ-4.4, 97-REQ-5.2
**Type:** unit
**Description:** Verify empty allowlist mode produces SecurityConfig that
blocks all Bash.

**Preconditions:** Registry entry with mode having `allowlist=[]`.

**Input:** `resolve_security_config(config, "reviewer", mode="pre-review")`

**Expected:** Returns SecurityConfig with `bash_allowlist=[]`.

**Assertion pseudocode:**
```
# Registry has reviewer with pre-review mode: allowlist=[]
result = resolve_security_config(config, "reviewer", mode="pre-review")
ASSERT result IS NOT None
ASSERT result.bash_allowlist == []
```

### TS-97-12: Security Hook Blocks All Bash With Empty Allowlist

**Requirement:** 97-REQ-5.2
**Type:** unit
**Description:** Verify hook blocks any Bash command when allowlist is empty.

**Preconditions:** SecurityConfig with `bash_allowlist=[]`.

**Input:** Hook invoked with `tool_name="Bash"`, `command="ls"`.

**Expected:** Returns `{"decision": "block", "message": ...}`.

**Assertion pseudocode:**
```
hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
result = hook(tool_name="Bash", tool_input={"command": "ls"})
ASSERT result["decision"] == "block"
```

### TS-97-13: NodeSessionRunner Passes Mode

**Requirement:** 97-REQ-5.3
**Type:** unit
**Description:** Verify NodeSessionRunner stores and uses mode for resolution.

**Preconditions:** Mock config and archetype registry.

**Input:** `NodeSessionRunner(node_id="s:0", config=cfg, archetype="reviewer",
mode="pre-review")`

**Expected:** Internal `_mode` field is "pre-review", resolution calls include
mode.

**Assertion pseudocode:**
```
runner = NodeSessionRunner(node_id="s:0", config=cfg,
    archetype="reviewer", mode="pre-review", ...)
ASSERT runner._mode == "pre-review"
```

## Property Test Cases

### TS-97-P1: Mode Override Semantics

**Property:** Property 1 from design.md
**Validates:** 97-REQ-1.3, 97-REQ-1.5
**Type:** property
**Description:** Non-None mode fields always override the base entry.

**For any:** ArchetypeEntry with randomly generated base fields and a
ModeConfig with a randomly chosen subset of fields set to non-None values.
**Invariant:** For every non-None field in ModeConfig, the resolved entry's
corresponding field equals the ModeConfig value.

**Assertion pseudocode:**
```
FOR ANY base: ArchetypeEntry, mode_cfg: ModeConfig:
    entry = replace(base, modes={"m": mode_cfg})
    resolved = resolve_effective_config(entry, "m")
    FOR field IN ModeConfig.fields:
        IF getattr(mode_cfg, field) IS NOT None:
            ASSERT getattr(resolved, mapped_field(field)) == getattr(mode_cfg, field)
```

### TS-97-P2: Mode Inheritance Semantics

**Property:** Property 2 from design.md
**Validates:** 97-REQ-1.5
**Type:** property
**Description:** None mode fields inherit the base entry value.

**For any:** ArchetypeEntry with randomly generated base fields and a
ModeConfig with a randomly chosen subset of fields set to None.
**Invariant:** For every None field in ModeConfig, the resolved entry's
corresponding field equals the base entry value.

**Assertion pseudocode:**
```
FOR ANY base: ArchetypeEntry, mode_cfg: ModeConfig:
    entry = replace(base, modes={"m": mode_cfg})
    resolved = resolve_effective_config(entry, "m")
    FOR field IN ModeConfig.fields:
        IF getattr(mode_cfg, field) IS None:
            ASSERT getattr(resolved, mapped_field(field)) == getattr(base, mapped_field(field))
```

### TS-97-P3: Null Mode Identity

**Property:** Property 3 from design.md
**Validates:** 97-REQ-1.4, 97-REQ-4.E1
**Type:** property
**Description:** None mode always returns a value equivalent to the base entry.

**For any:** ArchetypeEntry with arbitrary modes dict.
**Invariant:** resolve_effective_config(entry, None) has the same field values
as the base entry (excluding the modes field itself).

**Assertion pseudocode:**
```
FOR ANY entry: ArchetypeEntry:
    resolved = resolve_effective_config(entry, None)
    FOR field IN ArchetypeEntry.fields - {"modes"}:
        ASSERT getattr(resolved, field) == getattr(entry, field)
```

### TS-97-P4: Resolution Priority Chain

**Property:** Property 4 from design.md
**Validates:** 97-REQ-3.3, 97-REQ-4.1, 97-REQ-4.2, 97-REQ-4.3, 97-REQ-4.4
**Type:** property
**Description:** Config mode override beats config archetype override beats
registry mode beats registry base.

**For any:** 4-tuple of (config_mode_value, config_arch_value,
registry_mode_value, registry_base_value) where each is either None or a
valid value, and at least one is non-None.
**Invariant:** The resolved value equals the first non-None value in the
priority order.

**Assertion pseudocode:**
```
FOR ANY (cm, ca, rm, rb) WHERE at least one is not None:
    config = make_config_with_values(cm, ca)
    registry = make_registry_with_values(rm, rb)
    result = resolve_field(config, registry, archetype, mode)
    expected = first_non_none(cm, ca, rm, rb)
    ASSERT result == expected
```

### TS-97-P5: Empty Allowlist Blocks All Bash

**Property:** Property 5 from design.md
**Validates:** 97-REQ-5.2
**Type:** property
**Description:** An empty allowlist blocks every possible command.

**For any:** Command string (non-empty).
**Invariant:** The security hook returns `{"decision": "block"}`.

**Assertion pseudocode:**
```
hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
FOR ANY cmd: non_empty_string:
    result = hook(tool_name="Bash", tool_input={"command": cmd})
    ASSERT result["decision"] == "block"
```

### TS-97-P6: Serialization Round-Trip

**Property:** Property 6 from design.md
**Validates:** 97-REQ-2.2
**Type:** property
**Description:** Node mode survives serialization round-trip.

**For any:** Mode value (None or arbitrary string).
**Invariant:** serialize then deserialize preserves mode.

**Assertion pseudocode:**
```
FOR ANY mode: Optional[str]:
    node = Node(id="s:0", spec_name="s", group_number=0, title="t",
        optional=False, mode=mode)
    ASSERT deserialize(serialize(node)).mode == mode
```

## Edge Case Tests

### TS-97-E1: Unknown Mode Fallback

**Requirement:** 97-REQ-1.E1
**Type:** unit
**Description:** Unknown mode falls back to base entry with warning.

**Preconditions:** ArchetypeEntry with modes={"fast": ModeConfig(...)}.

**Input:** `resolve_effective_config(entry, "unknown_mode")`

**Expected:** Returns base entry, logs warning.

**Assertion pseudocode:**
```
entry = ArchetypeEntry(name="test", default_model_tier="STANDARD",
    modes={"fast": ModeConfig(model_tier="SIMPLE")})
result = resolve_effective_config(entry, "unknown_mode")
ASSERT result.default_model_tier == "STANDARD"
ASSERT warning_logged("unknown_mode")
```

### TS-97-E2: Empty Modes Dict

**Requirement:** 97-REQ-1.E2
**Type:** unit
**Description:** Empty modes dict treated as no modes.

**Preconditions:** ArchetypeEntry with modes={}.

**Input:** `resolve_effective_config(entry, "any_mode")`

**Expected:** Returns base entry, logs warning.

**Assertion pseudocode:**
```
entry = ArchetypeEntry(name="test", default_model_tier="STANDARD", modes={})
result = resolve_effective_config(entry, "any_mode")
ASSERT result.default_model_tier == "STANDARD"
```

### TS-97-E3: Node With None Mode

**Requirement:** 97-REQ-2.E1
**Type:** unit
**Description:** Node with None mode behaves as current implementation.

**Preconditions:** None.

**Input:** `Node(id="s:1", spec_name="s", group_number=1, title="t",
optional=False, mode=None)`

**Expected:** String representation does not contain mode info.

**Assertion pseudocode:**
```
node = Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)
ASSERT node.mode IS None
ASSERT ":" not in repr_archetype_part(node)  # no mode suffix
```

### TS-97-E4: Config Missing Mode Section Fallback

**Requirement:** 97-REQ-3.E1
**Type:** unit
**Description:** Missing mode config section falls back to archetype level.

**Preconditions:** Config with archetype override but no mode overrides.

**Input:** `resolve_max_turns(config, "reviewer", mode="pre-review")`

**Expected:** Returns archetype-level value, not registry default.

**Assertion pseudocode:**
```
config = make_config(overrides={
    "reviewer": PerArchetypeConfig(max_turns=100, modes={})
})
result = resolve_max_turns(config, "reviewer", mode="pre-review")
ASSERT result == 100
```

### TS-97-E5: None Mode Resolution Identity

**Requirement:** 97-REQ-4.E1
**Type:** unit
**Description:** mode=None produces identical results to current behavior.

**Preconditions:** Standard config without modes.

**Input:** `resolve_model_tier(config, "coder", mode=None)`

**Expected:** Same as `resolve_model_tier(config, "coder")` (current API).

**Assertion pseudocode:**
```
result_with_none = resolve_model_tier(config, "coder", mode=None)
result_without = resolve_model_tier(config, "coder")
ASSERT result_with_none == result_without
```

### TS-97-E6: Mode Allowlist None Inherits Base

**Requirement:** 97-REQ-5.E1
**Type:** unit
**Description:** Mode with None allowlist inherits base archetype allowlist.

**Preconditions:** Registry entry with base allowlist=["ls","cat"] and mode
with allowlist=None.

**Input:** `resolve_security_config(config, "test_arch", mode="m")`

**Expected:** Returns SecurityConfig with base allowlist ["ls","cat"].

**Assertion pseudocode:**
```
# Registry: test_arch has default_allowlist=["ls","cat"],
#           modes={"m": ModeConfig(allowlist=None)}
result = resolve_security_config(config, "test_arch", mode="m")
ASSERT result.bash_allowlist == ["ls", "cat"]
```

## Integration Smoke Tests

### TS-97-SMOKE-1: End-to-End Mode Resolution

**Execution Path:** Path 1 from design.md
**Description:** Verify that a Node with mode flows through
NodeSessionRunner to produce mode-specific model resolution.

**Setup:** Register a test archetype with modes in the registry (monkeypatch).
Create a minimal config with mode-specific overrides. Stub the claude-code-sdk
session creation (external I/O only).

**Trigger:** Instantiate `NodeSessionRunner` with `archetype="test_arch"`,
`mode="fast"`.

**Expected side effects:**
- `self._resolved_model_id` reflects the mode-specific model tier
- `self._resolved_security` reflects the mode-specific allowlist

**Must NOT satisfy with:** Mocking `resolve_model_tier` or
`resolve_security_config` — those are the components under test.

**Assertion pseudocode:**
```
# Monkeypatch registry with test archetype having mode "fast" → SIMPLE tier
runner = NodeSessionRunner(
    node_id="s:0", config=cfg, archetype="test_arch", mode="fast", ...
)
ASSERT runner._resolved_model_id == model_id_for("SIMPLE")
```

### TS-97-SMOKE-2: End-to-End Security Hook With Mode

**Execution Path:** Path 2 from design.md
**Description:** Verify that a mode with empty allowlist produces a hook that
blocks all Bash.

**Setup:** Register a test archetype with mode having `allowlist=[]`. Create
config. Do not mock security module.

**Trigger:** Instantiate `NodeSessionRunner`, extract the security hook, call
it with a Bash command.

**Expected side effects:**
- Hook returns `{"decision": "block"}` for any command

**Must NOT satisfy with:** Mocking `make_pre_tool_use_hook` or
`build_effective_allowlist`.

**Assertion pseudocode:**
```
runner = NodeSessionRunner(
    node_id="s:0", config=cfg, archetype="test_arch", mode="no-shell", ...
)
hook = make_pre_tool_use_hook(runner._resolved_security)
result = hook(tool_name="Bash", tool_input={"command": "ls"})
ASSERT result["decision"] == "block"
```

### TS-97-SMOKE-3: Graph Serialization With Mode

**Execution Path:** Path 4 from design.md
**Description:** Verify Node mode survives full TaskGraph
serialization/deserialization.

**Setup:** Build a TaskGraph with nodes that have various mode values. Use
real serialization, not mocks.

**Trigger:** Serialize TaskGraph to JSON, deserialize back.

**Expected side effects:**
- All nodes preserve their mode values

**Must NOT satisfy with:** Mocking the serialization/deserialization functions.

**Assertion pseudocode:**
```
graph = TaskGraph(nodes={
    "s:0": Node(id="s:0", ..., mode="pre-review"),
    "s:1": Node(id="s:1", ..., mode=None),
})
restored = deserialize(serialize(graph))
ASSERT restored.nodes["s:0"].mode == "pre-review"
ASSERT restored.nodes["s:1"].mode IS None
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 97-REQ-1.1 | TS-97-1 | unit |
| 97-REQ-1.2 | TS-97-2 | unit |
| 97-REQ-1.3 | TS-97-3 | unit |
| 97-REQ-1.4 | TS-97-4 | unit |
| 97-REQ-1.5 | TS-97-3 | unit |
| 97-REQ-1.E1 | TS-97-E1 | unit |
| 97-REQ-1.E2 | TS-97-E2 | unit |
| 97-REQ-2.1 | TS-97-5 | unit |
| 97-REQ-2.2 | TS-97-6 | unit |
| 97-REQ-2.3 | TS-97-5 | unit |
| 97-REQ-2.E1 | TS-97-E3 | unit |
| 97-REQ-3.1 | TS-97-7 | unit |
| 97-REQ-3.2 | TS-97-8 | unit |
| 97-REQ-3.3 | TS-97-10 | unit |
| 97-REQ-3.E1 | TS-97-E4 | unit |
| 97-REQ-4.1 | TS-97-9 | unit |
| 97-REQ-4.2 | TS-97-E4 | unit |
| 97-REQ-4.3 | TS-97-9 | unit |
| 97-REQ-4.4 | TS-97-11 | unit |
| 97-REQ-4.5 | TS-97-13 | unit |
| 97-REQ-4.E1 | TS-97-E5 | unit |
| 97-REQ-5.1 | TS-97-12 | unit |
| 97-REQ-5.2 | TS-97-12 | unit |
| 97-REQ-5.3 | TS-97-13 | unit |
| 97-REQ-5.E1 | TS-97-E6 | unit |
| Property 1 | TS-97-P1 | property |
| Property 2 | TS-97-P2 | property |
| Property 3 | TS-97-P3 | property |
| Property 4 | TS-97-P4 | property |
| Property 5 | TS-97-P5 | property |
| Property 6 | TS-97-P6 | property |
