# Test Specification: Config Generation

## Overview

Tests validate that the config generation system correctly introspects Pydantic
models, produces complete and valid TOML templates, merges existing configs
non-destructively, and handles edge cases gracefully. Test cases map directly
to requirements in `requirements.md` and correctness properties in `design.md`.

## Test Cases

### TS-33-1: Template Contains All Fields

**Requirement:** 33-REQ-1.1
**Type:** unit
**Description:** The generated template includes a commented entry for every
field in `AgentFoxConfig` and its nested models.

**Preconditions:**
- `AgentFoxConfig` model is importable.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Output contains commented entries for every field across all 10 sections
  (orchestrator, routing, models, hooks, security, theme, platform, knowledge,
  archetypes, tools) and subsections (archetypes.instances,
  archetypes.skeptic_settings, archetypes.oracle_settings).

**Assertion pseudocode:**
```
template = generate_default_config()
FOR EACH section IN extract_schema(AgentFoxConfig):
    FOR EACH field IN section.fields:
        ASSERT f"# {field.name} =" IN template
```

### TS-33-2: Template Includes Descriptions and Bounds

**Requirement:** 33-REQ-1.2
**Type:** unit
**Description:** Each field entry includes a description comment and valid
range where applicable.

**Preconditions:**
- `AgentFoxConfig` model is importable.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Fields with clamping bounds include range in comment (e.g., `(1-8, default: 1)`).
- Fields without bounds include just default (e.g., `(default: true)`).

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT "1-8" IN template  # parallel bounds
ASSERT ">=0" IN template   # sync_interval bounds
ASSERT "default: 1" IN template  # parallel default
ASSERT "default: true" IN template  # playful default
```

### TS-33-3: Template Has Correct Section Headers

**Requirement:** 33-REQ-1.3
**Type:** unit
**Description:** The template emits proper TOML section headers including
nested sub-tables.

**Preconditions:**
- None.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Contains `# [orchestrator]`, `# [routing]`, `# [models]`, `# [hooks]`,
  `# [security]`, `# [theme]`, `# [platform]`, `# [knowledge]`,
  `# [archetypes]`, `# [tools]`.
- Contains sub-table headers: `# [archetypes.instances]`,
  `# [archetypes.skeptic_settings]`, `# [archetypes.oracle_settings]`.

**Assertion pseudocode:**
```
template = generate_default_config()
FOR EACH section IN ["orchestrator", "routing", "models", "hooks", "security",
                      "theme", "platform", "knowledge", "archetypes", "tools"]:
    ASSERT f"# [{section}]" IN template
ASSERT "# [archetypes.instances]" IN template
ASSERT "# [archetypes.skeptic_settings]" IN template
ASSERT "# [archetypes.oracle_settings]" IN template
```

### TS-33-4: Template Uncommented Is Valid TOML

**Requirement:** 33-REQ-1.4
**Type:** unit
**Description:** Removing all `# ` prefixes from the template produces valid
TOML that loads without error.

**Preconditions:**
- None.

**Input:**
- Generate template, strip `# ` prefix from every line that starts with `# `.

**Expected:**
- The uncommented text parses as valid TOML.
- `load_config` accepts it without errors.

**Assertion pseudocode:**
```
template = generate_default_config()
uncommented = strip_comment_prefixes(template)
config = load_config(write_to_tmp(uncommented))
ASSERT isinstance(config, AgentFoxConfig)
```

### TS-33-5: Template Field Ordering Matches Model

**Requirement:** 33-REQ-1.5
**Type:** unit
**Description:** Fields in the template appear in the same order as in the
Pydantic model definitions.

**Preconditions:**
- None.

**Input:**
- Generate template. Extract field names in order of appearance.

**Expected:**
- For each section, the field order matches `model_fields` iteration order.

**Assertion pseudocode:**
```
template = generate_default_config()
template_fields = extract_field_names_in_order(template, section="orchestrator")
model_fields = list(OrchestratorConfig.model_fields.keys())
ASSERT template_fields == model_fields
```

### TS-33-6: Merge Preserves Active User Values

**Requirement:** 33-REQ-2.1
**Type:** unit
**Description:** Merging preserves all uncommented user-set values.

**Preconditions:**
- An existing config.toml with active (uncommented) values.

**Input:**
```toml
[orchestrator]
parallel = 4
session_timeout = 60
```

**Expected:**
- Output contains `parallel = 4` and `session_timeout = 60` (active, not commented).

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 4\nsession_timeout = 60\n"
merged = merge_existing_config(existing)
ASSERT "parallel = 4" IN merged
ASSERT "session_timeout = 60" IN merged
ASSERT NOT starts_with_comment("parallel = 4", merged)
```

### TS-33-7: Merge Adds Missing Fields

**Requirement:** 33-REQ-2.2
**Type:** unit
**Description:** Merging adds fields present in schema but missing from file.

**Preconditions:**
- An existing config.toml with only `[orchestrator]` section.

**Input:**
```toml
[orchestrator]
parallel = 4
```

**Expected:**
- Output contains commented entries for all other orchestrator fields
  (sync_interval, hot_load, max_retries, etc.) and all other sections.

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 4\n"
merged = merge_existing_config(existing)
ASSERT "# sync_interval = 5" IN merged
ASSERT "# [routing]" IN merged
ASSERT "# [theme]" IN merged
```

### TS-33-8: Merge Preserves User Comments

**Requirement:** 33-REQ-2.3
**Type:** unit
**Description:** User comments not managed by the generator are preserved.

**Preconditions:**
- Config with user comments.

**Input:**
```toml
# My custom note about this project
[orchestrator]
# I set this high for the big repo
parallel = 8
```

**Expected:**
- Both user comments appear in the merged output.

**Assertion pseudocode:**
```
existing = "# My custom note about this project\n[orchestrator]\n# I set this high for the big repo\nparallel = 8\n"
merged = merge_existing_config(existing)
ASSERT "My custom note about this project" IN merged
ASSERT "I set this high for the big repo" IN merged
```

### TS-33-9: Merge Marks Deprecated Fields

**Requirement:** 33-REQ-2.4
**Type:** unit
**Description:** Active fields not in the schema are marked DEPRECATED.

**Preconditions:**
- Config with an unrecognized field.

**Input:**
```toml
[orchestrator]
parallel = 4
removed_old_option = "value"
```

**Expected:**
- Output contains `# DEPRECATED: 'removed_old_option' is no longer recognized`
  and the value is commented out.

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 4\nremoved_old_option = \"value\"\n"
merged = merge_existing_config(existing)
ASSERT "DEPRECATED" IN merged
ASSERT "'removed_old_option'" IN merged
```

### TS-33-10: Merge No-Op When Already Current

**Requirement:** 33-REQ-2.5
**Type:** unit
**Description:** Merging a fully up-to-date config produces identical output.

**Preconditions:**
- A config that was freshly generated by the current schema.

**Input:**
- Generate a fresh config, then merge it.

**Expected:**
- Output is byte-for-byte identical to the input.

**Assertion pseudocode:**
```
fresh = generate_default_config()
merged = merge_existing_config(fresh)
ASSERT merged == fresh
```

### TS-33-11: Fresh Config Loads With All Defaults

**Requirement:** 33-REQ-3.1
**Type:** integration
**Description:** A freshly generated config.toml (all commented) loads and
returns all default values.

**Preconditions:**
- None.

**Input:**
- Generate template, write to file, load with `load_config`.

**Expected:**
- Returns `AgentFoxConfig()` with all defaults.

**Assertion pseudocode:**
```
template = generate_default_config()
config = load_config(write_to_tmp(template))
ASSERT config.orchestrator.parallel == 1
ASSERT config.theme.playful == True
ASSERT config.models.coding == "ADVANCED"
```

### TS-33-12: Schema Extraction Returns All Sections

**Requirement:** 33-REQ-4.1
**Type:** unit
**Description:** `extract_schema` returns entries for every section in
AgentFoxConfig.

**Preconditions:**
- None.

**Input:**
- Call `extract_schema(AgentFoxConfig)`.

**Expected:**
- Returns SectionSpecs for all 10 top-level sections.

**Assertion pseudocode:**
```
schema = extract_schema(AgentFoxConfig)
section_paths = {s.path for s in schema}
ASSERT section_paths == {"orchestrator", "routing", "models", "hooks",
    "security", "theme", "platform", "knowledge", "archetypes", "tools"}
```

### TS-33-13: Schema Auto-Discovers New Fields

**Requirement:** 33-REQ-4.2
**Type:** unit
**Description:** Adding a field to a config model automatically appears in
the extracted schema without generator changes.

**Preconditions:**
- A test Pydantic model simulating a config section.

**Input:**
- Create a model with fields A and B, extract schema, add field C, re-extract.

**Expected:**
- Second extraction includes field C.

**Assertion pseudocode:**
```
class TestModel(BaseModel):
    a: int = 1
    b: str = "x"
schema1 = extract_schema_for_model(TestModel)
ASSERT len(schema1.fields) == 2
# Dynamically add field c
TestModelV2 = create_model("TestModelV2", a=(int, 1), b=(str, "x"), c=(bool, True))
schema2 = extract_schema_for_model(TestModelV2)
ASSERT len(schema2.fields) == 3
```

### TS-33-14: MemoryConfig Removed

**Requirement:** 33-REQ-5.1
**Type:** unit
**Description:** `AgentFoxConfig` no longer has a `memory` field.

**Preconditions:**
- None.

**Input:**
- Inspect `AgentFoxConfig.model_fields`.

**Expected:**
- `"memory"` is not in `model_fields`.

**Assertion pseudocode:**
```
ASSERT "memory" NOT IN AgentFoxConfig.model_fields
```

### TS-33-15: Memory Section Ignored on Load

**Requirement:** 33-REQ-5.2
**Type:** unit
**Description:** A TOML file with `[memory]` section loads without error.

**Preconditions:**
- None.

**Input:**
```toml
[memory]
model = "ADVANCED"
```

**Expected:**
- `load_config` returns `AgentFoxConfig()` with defaults, no error.

**Assertion pseudocode:**
```
config = load_config(write_to_tmp("[memory]\nmodel = \"ADVANCED\"\n"))
ASSERT isinstance(config, AgentFoxConfig)
```

## Edge Case Tests

### TS-33-E1: None Default Representation

**Requirement:** 33-REQ-1.E1
**Type:** unit
**Description:** Fields with `None` default show "not set by default" comment.

**Preconditions:**
- None.

**Input:**
- Generate template.

**Expected:**
- `max_cost` entry contains "not set by default".

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT "not set by default" IN template
# And it appears near max_cost
lines = template.split("\n")
max_cost_idx = find_line_containing("max_cost", lines)
ASSERT "not set by default" IN lines[max_cost_idx - 1]
```

### TS-33-E2: Empty List Default

**Requirement:** 33-REQ-1.E2
**Type:** unit
**Description:** Fields with `[]` default render as `[]` in TOML.

**Preconditions:**
- None.

**Input:**
- Generate template.

**Expected:**
- `pre_code` entry has value `[]`.

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT "# pre_code = []" IN template
```

### TS-33-E3: Empty Dict Default

**Requirement:** 33-REQ-1.E3
**Type:** unit
**Description:** Fields with `{}` default render as `{}` in TOML.

**Preconditions:**
- None.

**Input:**
- Generate template.

**Expected:**
- `modes` entry has value `{}`.

**Assertion pseudocode:**
```
template = generate_default_config()
# tomlkit may render empty inline table
ASSERT "# modes" IN template
```

### TS-33-E4: Alias Used in Template

**Requirement:** 33-REQ-3.E1
**Type:** unit
**Description:** Fields with aliases use the alias as the TOML key.

**Preconditions:**
- `ArchetypesConfig.skeptic_config` has alias `skeptic_settings`.

**Input:**
- Generate template.

**Expected:**
- Template contains `[archetypes.skeptic_settings]`, not
  `[archetypes.skeptic_config]`.

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT "skeptic_settings" IN template
ASSERT "skeptic_config" NOT IN template
```

### TS-33-E5: Invalid TOML Skips Merge

**Requirement:** 33-REQ-2.E1
**Type:** unit
**Description:** Merge on invalid TOML logs a warning and returns the
original content unchanged.

**Preconditions:**
- None.

**Input:**
- `"[broken toml }{"` as existing content.

**Expected:**
- `merge_existing_config` returns the original string unchanged.
- A warning is logged.

**Assertion pseudocode:**
```
bad = "[broken toml }{"
result = merge_existing_config(bad)
ASSERT result == bad
ASSERT warning_logged("invalid TOML")
```

### TS-33-E6: Empty Config Treated as Fresh

**Requirement:** 33-REQ-2.E2
**Type:** unit
**Description:** An empty or whitespace-only config is treated as fresh
generation.

**Preconditions:**
- None.

**Input:**
- `""` and `"  \n\n  "` as existing content.

**Expected:**
- Output matches `generate_default_config()`.

**Assertion pseudocode:**
```
fresh = generate_default_config()
ASSERT merge_existing_config("") == fresh
ASSERT merge_existing_config("  \n\n  ") == fresh
```

### TS-33-E7: Factory Default Resolved

**Requirement:** 33-REQ-4.E1
**Type:** unit
**Description:** Fields with `default_factory` have their factory invoked
for the template value.

**Preconditions:**
- None.

**Input:**
- Extract schema for `HookConfig` which has `Field(default_factory=list)`.

**Expected:**
- `pre_code` field has default `[]`, not a factory object.

**Assertion pseudocode:**
```
schema = extract_schema(AgentFoxConfig)
hooks_section = find_section(schema, "hooks")
pre_code = find_field(hooks_section, "pre_code")
ASSERT pre_code.default == []
```

## Property Test Cases

### TS-33-P1: Template Completeness

**Property:** Property 1 from design.md
**Validates:** 33-REQ-1.1, 33-REQ-1.2, 33-REQ-4.2
**Type:** property
**Description:** Every scalar field in every section appears as a commented
entry in the generated template.

**For any:** `AgentFoxConfig` model (fixed, but validated structurally)
**Invariant:** The count of commented field entries in the template equals the
count of scalar fields across all sections in the extracted schema.

**Assertion pseudocode:**
```
schema = extract_schema(AgentFoxConfig)
template = generate_default_config()
total_scalar_fields = count_scalar_fields(schema)
total_commented_entries = count_commented_field_lines(template)
ASSERT total_commented_entries == total_scalar_fields
```

### TS-33-P2: Round-Trip Default Equivalence

**Property:** Property 2 from design.md
**Validates:** 33-REQ-1.4, 33-REQ-3.2
**Type:** property
**Description:** Uncommenting all fields and loading produces defaults.

**For any:** generated template (deterministic)
**Invariant:** The loaded config from the uncommented template is field-equal
to `AgentFoxConfig()`.

**Assertion pseudocode:**
```
template = generate_default_config()
uncommented = strip_comment_prefixes(template)
config = load_config(write_to_tmp(uncommented))
default = AgentFoxConfig()
FOR EACH section_name IN AgentFoxConfig.model_fields:
    ASSERT getattr(config, section_name) == getattr(default, section_name)
```

### TS-33-P3: Merge Value Preservation

**Property:** Property 3 from design.md
**Validates:** 33-REQ-2.1, 33-REQ-2.5
**Type:** property
**Description:** Active user values survive merge unchanged.

**For any:** TOML string with random valid field overrides from the schema
**Invariant:** Every active field in the input appears active with the same
value in the output.

**Assertion pseudocode:**
```
FOR ANY overrides IN random_valid_config_overrides():
    existing = render_toml(overrides)
    merged = merge_existing_config(existing)
    FOR EACH key, value IN overrides:
        ASSERT active_value(merged, key) == value
```

### TS-33-P4: Merge Completeness

**Property:** Property 4 from design.md
**Validates:** 33-REQ-2.2
**Type:** property
**Description:** After merge, every schema field appears in the output.

**For any:** subset of schema fields present in the existing config
**Invariant:** The merged output contains entries (active or commented) for
all fields in the schema.

**Assertion pseudocode:**
```
FOR ANY subset IN random_field_subsets(schema):
    existing = render_toml_with_subset(subset)
    merged = merge_existing_config(existing)
    FOR EACH field IN all_schema_fields():
        ASSERT field.name IN merged
```

### TS-33-P5: Deprecated Field Detection

**Property:** Property 5 from design.md
**Validates:** 33-REQ-2.4
**Type:** property
**Description:** Unknown active fields get DEPRECATED markers.

**For any:** TOML with random unknown field names injected
**Invariant:** Every unknown field name appears with a DEPRECATED prefix in
the output.

**Assertion pseudocode:**
```
FOR ANY unknown_fields IN random_unknown_field_names():
    existing = render_toml_with_unknowns(unknown_fields)
    merged = merge_existing_config(existing)
    FOR EACH name IN unknown_fields:
        ASSERT f"DEPRECATED" IN find_line_for(merged, name)
```

### TS-33-P6: Schema Extraction Determinism

**Property:** Property 6 from design.md
**Validates:** 33-REQ-1.5, 33-REQ-4.1
**Type:** property
**Description:** Multiple calls to extract_schema produce identical results.

**For any:** 10 sequential calls to `extract_schema(AgentFoxConfig)`
**Invariant:** All calls return structurally identical results.

**Assertion pseudocode:**
```
results = [extract_schema(AgentFoxConfig) for _ in range(10)]
FOR i IN range(1, 10):
    ASSERT results[i] == results[0]
```

### TS-33-P7: Merge Idempotency

**Property:** Property 7 from design.md
**Validates:** 33-REQ-2.5
**Type:** property
**Description:** Merging an already-merged config is a no-op.

**For any:** config that has been merged once
**Invariant:** `merge(merge(x)) == merge(x)`

**Assertion pseudocode:**
```
FOR ANY existing IN random_valid_configs():
    once = merge_existing_config(existing)
    twice = merge_existing_config(once)
    ASSERT twice == once
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 33-REQ-1.1 | TS-33-1 | unit |
| 33-REQ-1.2 | TS-33-2 | unit |
| 33-REQ-1.3 | TS-33-3 | unit |
| 33-REQ-1.4 | TS-33-4 | unit |
| 33-REQ-1.5 | TS-33-5 | unit |
| 33-REQ-1.E1 | TS-33-E1 | unit |
| 33-REQ-1.E2 | TS-33-E2 | unit |
| 33-REQ-1.E3 | TS-33-E3 | unit |
| 33-REQ-2.1 | TS-33-6 | unit |
| 33-REQ-2.2 | TS-33-7 | unit |
| 33-REQ-2.3 | TS-33-8 | unit |
| 33-REQ-2.4 | TS-33-9 | unit |
| 33-REQ-2.5 | TS-33-10 | unit |
| 33-REQ-2.E1 | TS-33-E5 | unit |
| 33-REQ-2.E2 | TS-33-E6 | unit |
| 33-REQ-3.1 | TS-33-11 | integration |
| 33-REQ-3.2 | TS-33-4 | unit |
| 33-REQ-3.E1 | TS-33-E4 | unit |
| 33-REQ-4.1 | TS-33-12 | unit |
| 33-REQ-4.2 | TS-33-13 | unit |
| 33-REQ-4.E1 | TS-33-E7 | unit |
| 33-REQ-5.1 | TS-33-14 | unit |
| 33-REQ-5.2 | TS-33-15 | unit |
| Property 1 | TS-33-P1 | property |
| Property 2 | TS-33-P2 | property |
| Property 3 | TS-33-P3 | property |
| Property 4 | TS-33-P4 | property |
| Property 5 | TS-33-P5 | property |
| Property 6 | TS-33-P6 | property |
| Property 7 | TS-33-P7 | property |
