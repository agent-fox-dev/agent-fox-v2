# Test Specification: Remove Coordinator Archetype

## Overview

Tests verify complete removal of the coordinator archetype from all layers:
registry, template, graph builder, prompt system, spec parser, and model
config. Each test asserts absence rather than presence.

## Test Cases

### TS-62-1: Coordinator Absent from Registry

**Requirement:** 62-REQ-1.1
**Type:** unit
**Description:** Verify the archetype registry does not contain a coordinator entry.

**Preconditions:**
- `ARCHETYPE_REGISTRY` is imported from `agent_fox.session.archetypes`.

**Input:**
- None (inspect registry keys).

**Expected:**
- `"coordinator"` is not in `ARCHETYPE_REGISTRY`.

**Assertion pseudocode:**
```
ASSERT "coordinator" NOT IN ARCHETYPE_REGISTRY
```

### TS-62-2: get_archetype Falls Back for Coordinator

**Requirement:** 62-REQ-1.2
**Type:** unit
**Description:** Verify `get_archetype("coordinator")` returns the coder fallback.

**Preconditions:**
- `get_archetype` imported from `agent_fox.session.archetypes`.

**Input:**
- `get_archetype("coordinator")`

**Expected:**
- Returns the `"coder"` archetype entry.
- A warning is logged.

**Assertion pseudocode:**
```
result = get_archetype("coordinator")
ASSERT result.name == "coder"
ASSERT warning logged containing "coordinator"
```

### TS-62-3: Coordinator Template Deleted

**Requirement:** 62-REQ-2.1
**Type:** unit
**Description:** Verify the coordinator.md template file does not exist.

**Preconditions:**
- Template directory path known.

**Input:**
- Check for `agent_fox/_templates/prompts/coordinator.md`.

**Expected:**
- File does not exist.

**Assertion pseudocode:**
```
template_path = TEMPLATES_DIR / "prompts" / "coordinator.md"
ASSERT NOT template_path.exists()
```

### TS-62-4: build_graph Rejects coordinator_overrides

**Requirement:** 62-REQ-3.1
**Type:** unit
**Description:** Verify `build_graph()` does not accept a `coordinator_overrides` parameter.

**Preconditions:**
- `build_graph` imported from `agent_fox.graph.builder`.

**Input:**
- Inspect function signature.

**Expected:**
- `"coordinator_overrides"` not in parameter names.

**Assertion pseudocode:**
```
import inspect
sig = inspect.signature(build_graph)
ASSERT "coordinator_overrides" NOT IN sig.parameters
```

### TS-62-5: _apply_coordinator_overrides Removed

**Requirement:** 62-REQ-3.2
**Type:** unit
**Description:** Verify the builder module has no `_apply_coordinator_overrides` function.

**Preconditions:**
- `agent_fox.graph.builder` module imported.

**Input:**
- Check for attribute.

**Expected:**
- `_apply_coordinator_overrides` does not exist on the module.

**Assertion pseudocode:**
```
import agent_fox.graph.builder as builder_mod
ASSERT NOT hasattr(builder_mod, "_apply_coordinator_overrides")
```

### TS-62-6: Prompt Role Mapping Excludes Coordinator

**Requirement:** 62-REQ-4.1
**Type:** unit
**Description:** Verify the prompt role mapping does not contain coordinator.

**Preconditions:**
- Role mapping dict accessible from `agent_fox.session.prompt`.

**Input:**
- Inspect role mapping keys.

**Expected:**
- `"coordinator"` not present.

**Assertion pseudocode:**
```
from agent_fox.session.prompt import _ROLE_TO_ARCHETYPE  # or equivalent
ASSERT "coordinator" NOT IN _ROLE_TO_ARCHETYPE
```

### TS-62-7: Parser Known Archetypes Excludes Coordinator

**Requirement:** 62-REQ-5.1
**Type:** unit
**Description:** Verify the spec parser's known archetypes set does not include coordinator.

**Preconditions:**
- Known archetypes set accessible from `agent_fox.spec.parser`.

**Input:**
- Inspect the set.

**Expected:**
- `"coordinator"` not present.

**Assertion pseudocode:**
```
from agent_fox.spec.parser import _KNOWN_ARCHETYPES  # or equivalent
ASSERT "coordinator" NOT IN _KNOWN_ARCHETYPES
```

### TS-62-8: ModelConfig Has No Coordinator Field

**Requirement:** 62-REQ-6.1
**Type:** unit
**Description:** Verify ModelConfig does not have a coordinator field.

**Preconditions:**
- `ModelConfig` imported from `agent_fox.core.config`.

**Input:**
- Inspect model fields.

**Expected:**
- No field named `"coordinator"`.

**Assertion pseudocode:**
```
from agent_fox.core.config import ModelConfig
ASSERT "coordinator" NOT IN ModelConfig.model_fields
```

### TS-62-9: Two-Layer Archetype Assignment

**Requirement:** 62-REQ-3.3
**Type:** unit
**Description:** Verify that `build_graph()` applies tasks.md tag overrides
directly after defaults, with no intermediate coordinator layer.

**Preconditions:**
- A spec with a tasks.md tag `[archetype: verifier]` on a task group.

**Input:**
- Call `build_graph()` with a spec containing an archetype-tagged group.

**Expected:**
- The tagged group's archetype is set to the tasks.md tag value.

**Assertion pseudocode:**
```
specs = [spec_with_tagged_group]
task_groups = {"spec": [group_with_archetype_tag("verifier")]}
graph = build_graph(specs, task_groups, [])
ASSERT graph.nodes["spec:2"].archetype == "verifier"
```

## Edge Case Tests

### TS-62-E1: Config With Coordinator Field Loads Successfully

**Requirement:** 62-REQ-6.E1
**Type:** unit
**Description:** Verify that a config file containing a coordinator model tier
is loaded without error.

**Preconditions:**
- TOML content with `coordinator = "STANDARD"` under `[models]`.

**Input:**
- Load config from TOML string with coordinator field.

**Expected:**
- Config loads successfully, coordinator field is silently ignored.

**Assertion pseudocode:**
```
toml_content = "[models]\ncoordinator = \"STANDARD\"\n"
config = load_config_from_string(toml_content)
ASSERT NOT hasattr(config.models, "coordinator")
```

## Property Test Cases

### TS-62-P1: No Coordinator in Any Archetype Collection

**Property:** Property 1 from design.md
**Validates:** 62-REQ-1.1, 62-REQ-5.1
**Type:** property
**Description:** The string "coordinator" never appears in any archetype
enumeration.

**For any:** collection of archetype names drawn from the registry, parser, or
prompt mapping.
**Invariant:** "coordinator" is absent from every collection.

**Assertion pseudocode:**
```
all_collections = [
    set(ARCHETYPE_REGISTRY.keys()),
    _KNOWN_ARCHETYPES,
    set(_ROLE_TO_ARCHETYPE.keys()),
]
FOR collection IN all_collections:
    ASSERT "coordinator" NOT IN collection
```

### TS-62-P2: Config Tolerance

**Property:** Property 6 from design.md
**Validates:** 62-REQ-6.E1
**Type:** property
**Description:** Any TOML config with extra fields under `[models]` loads
without error.

**For any:** field name from a set of plausible extra fields (including
`"coordinator"`).
**Invariant:** `load_config()` succeeds and the extra field is not present on
the resulting `ModelConfig`.

**Assertion pseudocode:**
```
FOR ANY field_name IN ["coordinator", "planner", "reviewer", "analyzer"]:
    toml = f"[models]\n{field_name} = \"STANDARD\"\n"
    config = load_config_from_string(toml)
    ASSERT field_name NOT IN config.models.model_fields
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 62-REQ-1.1 | TS-62-1 | unit |
| 62-REQ-1.2 | TS-62-2 | unit |
| 62-REQ-2.1 | TS-62-3 | unit |
| 62-REQ-3.1 | TS-62-4 | unit |
| 62-REQ-3.2 | TS-62-5 | unit |
| 62-REQ-3.3 | TS-62-9 | unit |
| 62-REQ-4.1 | TS-62-6 | unit |
| 62-REQ-5.1 | TS-62-7 | unit |
| 62-REQ-6.1 | TS-62-8 | unit |
| 62-REQ-6.E1 | TS-62-E1 | unit |
| 62-REQ-7.1 | (make check) | integration |
| 62-REQ-7.2 | (manual audit) | integration |
| Property 1 | TS-62-P1 | property |
| Property 6 | TS-62-P2 | property |
