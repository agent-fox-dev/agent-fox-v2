# Test Specification: Config Simplification

## Overview

Tests verify the config template simplification across three dimensions:
template generation (visible sections, promoted fields, footer), merge behavior
(hidden section handling, value preservation), and code defaults (verifier
instances). Property tests validate invariants across generated inputs.

## Test Cases

### TS-68-1: Template Contains Only Visible Sections

**Requirement:** 68-REQ-1.1
**Type:** unit
**Description:** Verify that `generate_default_config()` output contains only
sections from the visible set.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Output contains `[orchestrator]`, `[models]`, `[archetypes]`,
  `[archetypes.instances]`, `[archetypes.thinking.coder]` as active or
  commented section headers.
- Output does NOT contain `[routing]`, `[theme]`, `[platform]`, `[knowledge]`,
  `[pricing]`, `[planning]`, `[blocking]`, `[hooks]`, `[night_shift]`.

**Assertion pseudocode:**
```
template = generate_default_config()
FOR EACH visible IN visible_sections:
    ASSERT visible appears as section header in template
FOR EACH hidden IN hidden_sections:
    ASSERT hidden does NOT appear as section header in template
```

### TS-68-2: Template Omits Hidden Sections

**Requirement:** 68-REQ-1.2
**Type:** unit
**Description:** Verify that hidden sections are completely absent from
template output.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- No line in the output matches `[routing]`, `# [routing]`, `[theme]`,
  `# [theme]`, etc. for any hidden section.

**Assertion pseudocode:**
```
template = generate_default_config()
hidden = ["routing", "theme", "platform", "knowledge", "pricing",
          "planning", "blocking", "hooks", "night_shift"]
FOR EACH section IN hidden:
    ASSERT f"[{section}]" NOT IN template
    ASSERT f"# [{section}]" NOT IN template
```

### TS-68-3: Template Contains Footer

**Requirement:** 68-REQ-6.1
**Type:** unit
**Description:** Verify the template ends with the reference doc footer.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Output contains exactly one line matching
  `## For all configuration options, see docs/config-reference.md`.

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT template.count("docs/config-reference.md") == 1
ASSERT "## For all configuration options, see docs/config-reference.md" IN template
```

### TS-68-4: Template Line Count Within Bound

**Requirement:** 68-REQ-1.4
**Type:** unit
**Description:** Verify the simplified template does not exceed 60 lines.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Line count <= 60.

**Assertion pseudocode:**
```
template = generate_default_config()
lines = template.strip().split("\n")
ASSERT len(lines) <= 60
```

### TS-68-5: Quality Gate Promoted

**Requirement:** 68-REQ-2.1
**Type:** unit
**Description:** Verify `quality_gate` appears as an active field with
value `"make check"`.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Output contains uncommented line `quality_gate = "make check"`.

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT 'quality_gate = "make check"' IN template
ASSERT NOT line starts with '#' for the quality_gate line
```

### TS-68-6: Verifier Instances Promoted

**Requirement:** 68-REQ-2.2
**Type:** unit
**Description:** Verify `archetypes.instances.verifier` appears as active
field with value `2`.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Output contains uncommented `verifier = 2` under `[archetypes.instances]`.

**Assertion pseudocode:**
```
template = generate_default_config()
parsed = toml_parse(template)
ASSERT parsed["archetypes"]["instances"]["verifier"] == 2
```

### TS-68-7: Archetype Toggles Promoted

**Requirement:** 68-REQ-2.3
**Type:** unit
**Description:** Verify all quality archetype toggles are promoted and active.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- Template parses with `archetypes.skeptic = true`,
  `archetypes.verifier = true`, `archetypes.oracle = true`,
  `archetypes.auditor = true`.

**Assertion pseudocode:**
```
template = generate_default_config()
parsed = toml_parse(template)
FOR EACH toggle IN ["skeptic", "verifier", "oracle", "auditor"]:
    ASSERT parsed["archetypes"][toggle] == True
```

### TS-68-8: Budget and Model Promoted

**Requirement:** 68-REQ-2.4, 68-REQ-2.5
**Type:** unit
**Description:** Verify `max_budget_usd` and `models.coding` are promoted.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- `orchestrator.max_budget_usd = 5.0` and `models.coding = "ADVANCED"` are
  active in parsed output.

**Assertion pseudocode:**
```
template = generate_default_config()
parsed = toml_parse(template)
ASSERT parsed["orchestrator"]["max_budget_usd"] == 5.0
ASSERT parsed["models"]["coding"] == "ADVANCED"
```

### TS-68-9: Verifier Default Changed

**Requirement:** 68-REQ-2.6
**Type:** unit
**Description:** Verify `ArchetypeInstancesConfig` default for verifier is 2.

**Preconditions:**
- None.

**Input:**
- Construct `ArchetypeInstancesConfig()` with no arguments.

**Expected:**
- `config.verifier == 2`.

**Assertion pseudocode:**
```
config = ArchetypeInstancesConfig()
ASSERT config.verifier == 2
```

### TS-68-10: Field Descriptions Are Meaningful

**Requirement:** 68-REQ-3.2
**Type:** unit
**Description:** Verify that promoted field descriptions are not mechanical
transformations of the field name.

**Preconditions:**
- No existing config file.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- For each promoted field, the `##` comment line above it is NOT equal to
  the field name with underscores replaced by spaces and title-cased.

**Assertion pseudocode:**
```
template = generate_default_config()
FOR EACH (section, field_name) IN _PROMOTED_DEFAULTS:
    mechanical = field_name.replace("_", " ").title()
    description_line = find_comment_above(template, field_name)
    ASSERT mechanical NOT IN description_line
```

### TS-68-11: Hidden Sections Still Load

**Requirement:** 68-REQ-1.5
**Type:** integration
**Description:** Verify that a config with manually-added hidden sections
loads correctly.

**Preconditions:**
- A config.toml containing the simplified template plus manually added
  `[routing]` and `[theme]` sections.

**Input:**
- Call `load_config(path)` on the augmented config.

**Expected:**
- Config loads without error.
- `config.routing.retries_before_escalation` equals the value set.
- `config.theme.playful` equals the value set.

**Assertion pseudocode:**
```
content = generate_default_config() + "\n[routing]\nretries_before_escalation = 2\n\n[theme]\nplayful = false\n"
write_file(path, content)
config = load_config(path)
ASSERT config.routing.retries_before_escalation == 2
ASSERT config.theme.playful == False
```

### TS-68-12: Merge Preserves Hidden Sections

**Requirement:** 68-REQ-1.E1
**Type:** unit
**Description:** Verify that merge preserves hidden sections already present
in an existing config.

**Preconditions:**
- An existing config containing `[routing]` section with active values.

**Input:**
- Call `merge_existing_config(existing_content)`.

**Expected:**
- Output contains `[routing]` section with original values.

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 4\n\n[routing]\nretries_before_escalation = 3\n"
result = merge_existing_config(existing)
ASSERT "[routing]" IN result
ASSERT "retries_before_escalation = 3" IN result
```

### TS-68-13: Merge Does Not Add Hidden Sections

**Requirement:** 68-REQ-5.3
**Type:** unit
**Description:** Verify that merge does not introduce hidden sections that
were not in the original config.

**Preconditions:**
- An existing config with only `[orchestrator]` and `[archetypes]`.

**Input:**
- Call `merge_existing_config(existing_content)`.

**Expected:**
- Output does NOT contain `[routing]`, `[theme]`, `[platform]`,
  `[knowledge]`, `[pricing]`, `[planning]`, `[blocking]`, `[hooks]`.

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 4\n\n[archetypes]\nskeptic = true\n"
result = merge_existing_config(existing)
hidden = ["routing", "theme", "platform", "knowledge", "pricing",
          "planning", "blocking", "hooks"]
FOR EACH section IN hidden:
    ASSERT f"[{section}]" NOT IN result
    ASSERT f"# [{section}]" NOT IN result
```

### TS-68-14: Merge on Empty Config

**Requirement:** 68-REQ-5.E2
**Type:** unit
**Description:** Verify that merging an empty config produces the simplified
template.

**Preconditions:**
- Empty string as existing config content.

**Input:**
- Call `merge_existing_config("")`.

**Expected:**
- Output equals `generate_default_config()`.

**Assertion pseudocode:**
```
result = merge_existing_config("")
expected = generate_default_config()
ASSERT result == expected
```

### TS-68-15: Config Reference Doc Exists

**Requirement:** 68-REQ-4.1
**Type:** unit
**Description:** Verify that `docs/config-reference.md` exists and has
required structure.

**Preconditions:**
- Repository checked out.

**Input:**
- Read `docs/config-reference.md`.

**Expected:**
- File exists.
- Contains a table of contents section.
- Contains every config section name as a heading.

**Assertion pseudocode:**
```
content = read_file("docs/config-reference.md")
ASSERT content is not empty
ASSERT "## Table of Contents" IN content OR "## Contents" IN content
FOR EACH section IN all_config_sections:
    ASSERT section appears as heading in content
```

### TS-68-16: Config Reference Covers All Fields

**Requirement:** 68-REQ-4.2
**Type:** unit
**Description:** Verify that every config field appears in the reference doc.

**Preconditions:**
- Repository checked out.

**Input:**
- Extract all field names from `extract_schema(AgentFoxConfig)`.
- Read `docs/config-reference.md`.

**Expected:**
- Every field name appears in the document.

**Assertion pseudocode:**
```
schema = extract_schema(AgentFoxConfig)
doc = read_file("docs/config-reference.md")
all_fields = collect_all_field_names(schema)
FOR EACH field_name IN all_fields:
    ASSERT field_name IN doc
```

### TS-68-17: Footer Not Duplicated on Merge

**Requirement:** 68-REQ-6.E1
**Type:** unit
**Description:** Verify that merging a config already containing the footer
does not duplicate it.

**Preconditions:**
- Existing config that already contains the footer comment.

**Input:**
- Call `merge_existing_config(existing_content)`.

**Expected:**
- Output contains exactly one occurrence of the footer.

**Assertion pseudocode:**
```
existing = generate_default_config()  # already has footer
result = merge_existing_config(existing)
ASSERT result.count("docs/config-reference.md") == 1
```

## Property Test Cases

### TS-68-P1: Template Always Valid TOML

**Property:** Property 1 from design.md
**Validates:** 68-REQ-1.E2
**Type:** property
**Description:** Any generated template parses as valid TOML.

**For any:** generated template output (no random input needed — deterministic)
**Invariant:** `toml.loads(template)` does not raise.

**Assertion pseudocode:**
```
template = generate_default_config()
ASSERT toml.loads(template) does not raise
```

### TS-68-P2: Visible Section Containment

**Property:** Property 2 from design.md
**Validates:** 68-REQ-1.1, 68-REQ-1.2
**Type:** property
**Description:** Every section header in the template references a visible
section.

**For any:** section header line in the generated template
**Invariant:** The section name is in `_VISIBLE_SECTIONS`.

**Assertion pseudocode:**
```
template = generate_default_config()
FOR ANY line matching r"\[?#?\s*\[(\S+)\]":
    section_name = extracted group
    ASSERT section_name IN _VISIBLE_SECTIONS
```

### TS-68-P3: Merge Value Preservation

**Property:** Property 6 from design.md
**Validates:** 68-REQ-5.1, 68-REQ-1.E1
**Type:** property
**Description:** Merging preserves every active key=value pair from the
original config.

**For any:** valid config content with random field values for known fields
**Invariant:** Every active `key = value` pair in the input appears in the
merged output.

**Assertion pseudocode:**
```
FOR ANY parallel IN st.integers(1, 8),
        max_budget IN st.floats(0.1, 100.0),
        skeptic IN st.booleans():
    existing = build_config(parallel=parallel, max_budget=max_budget, skeptic=skeptic)
    result = merge_existing_config(existing)
    ASSERT f"parallel = {parallel}" IN result
    ASSERT f"skeptic = {str(skeptic).lower()}" IN result
```

### TS-68-P4: No Hidden Section Injection

**Property:** Property 7 from design.md
**Validates:** 68-REQ-5.3
**Type:** property
**Description:** Merge never adds hidden sections not already present.

**For any:** config content containing a random subset of visible sections
**Invariant:** No hidden section appears in the merge output.

**Assertion pseudocode:**
```
FOR ANY sections IN st.subsets(visible_sections):
    existing = build_config_with_sections(sections)
    result = merge_existing_config(existing)
    FOR EACH hidden IN hidden_sections:
        ASSERT f"[{hidden}]" NOT IN result
```

### TS-68-P5: Footer Non-Duplication

**Property:** Property 9 from design.md
**Validates:** 68-REQ-6.E1
**Type:** property
**Description:** Repeated merges never duplicate the footer.

**For any:** number of merge iterations (1-5)
**Invariant:** Footer appears exactly once.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(1, 5):
    content = generate_default_config()
    FOR i IN range(n):
        content = merge_existing_config(content)
    ASSERT content.count("docs/config-reference.md") == 1
```

### TS-68-P6: Default Verifier Instances

**Property:** Property 10 from design.md
**Validates:** 68-REQ-2.6
**Type:** property
**Description:** Default-constructed config always has verifier=2.

**For any:** (deterministic — no random input)
**Invariant:** `ArchetypeInstancesConfig().verifier == 2`

**Assertion pseudocode:**
```
config = ArchetypeInstancesConfig()
ASSERT config.verifier == 2
```

## Edge Case Tests

### TS-68-E1: Merge Preserves Hidden Sections in Existing Config

**Requirement:** 68-REQ-1.E1
**Type:** unit
**Description:** Existing configs with hidden sections keep them after merge.

**Preconditions:**
- Config with `[routing]`, `[theme]`, and `[knowledge]` sections active.

**Input:**
- Call `merge_existing_config(existing_content)`.

**Expected:**
- All three hidden sections remain in output with original values.

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 2\n\n[routing]\nretries_before_escalation = 2\n\n[theme]\nplayful = false\n\n[knowledge]\nask_top_k = 50\n"
result = merge_existing_config(existing)
ASSERT "retries_before_escalation = 2" IN result
ASSERT "playful = false" IN result
ASSERT "ask_top_k = 50" IN result
```

### TS-68-E2: Template Parses Without Errors

**Requirement:** 68-REQ-1.E2
**Type:** unit
**Description:** Generated template is valid TOML.

**Preconditions:**
- None.

**Input:**
- Call `generate_default_config()`.

**Expected:**
- `tomlkit.parse(template)` succeeds.

**Assertion pseudocode:**
```
template = generate_default_config()
parsed = tomlkit.parse(template)
ASSERT parsed is not None
ASSERT no exception raised
```

### TS-68-E3: Deprecated Fields Marked

**Requirement:** 68-REQ-5.E1
**Type:** unit
**Description:** Deprecated fields are marked during merge.

**Preconditions:**
- Config with an unknown field `foo_bar = 42` in `[orchestrator]`.

**Input:**
- Call `merge_existing_config(existing_content)`.

**Expected:**
- Output contains `# DEPRECATED:` comment for `foo_bar`.

**Assertion pseudocode:**
```
existing = "[orchestrator]\nparallel = 2\nfoo_bar = 42\n"
result = merge_existing_config(existing)
ASSERT "DEPRECATED" IN result
ASSERT "foo_bar" IN result
```

### TS-68-E4: Description Fallback

**Requirement:** 68-REQ-3.E1
**Type:** unit
**Description:** Fields without explicit descriptions get a readable fallback.

**Preconditions:**
- A FieldSpec with no description in `_DEFAULT_DESCRIPTIONS`.

**Input:**
- Call `_get_description(model_class, field_name, field_info)` for a field
  not in the descriptions map.

**Expected:**
- Returns a title-cased version of the field name (fallback behavior).

**Assertion pseudocode:**
```
result = _get_description(SomeModel, "unknown_field", field_info_without_desc)
ASSERT result == "Unknown Field"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 68-REQ-1.1 | TS-68-1 | unit |
| 68-REQ-1.2 | TS-68-2 | unit |
| 68-REQ-1.3 | TS-68-3 | unit |
| 68-REQ-1.4 | TS-68-4 | unit |
| 68-REQ-1.5 | TS-68-11 | integration |
| 68-REQ-1.E1 | TS-68-12, TS-68-E1 | unit |
| 68-REQ-1.E2 | TS-68-E2 | unit |
| 68-REQ-2.1 | TS-68-5 | unit |
| 68-REQ-2.2 | TS-68-6 | unit |
| 68-REQ-2.3 | TS-68-7 | unit |
| 68-REQ-2.4 | TS-68-8 | unit |
| 68-REQ-2.5 | TS-68-8 | unit |
| 68-REQ-2.6 | TS-68-9 | unit |
| 68-REQ-2.E1 | (existing test) | — |
| 68-REQ-3.1 | TS-68-10 | unit |
| 68-REQ-3.2 | TS-68-10 | unit |
| 68-REQ-3.3 | TS-68-10 | unit |
| 68-REQ-3.E1 | TS-68-E4 | unit |
| 68-REQ-4.1 | TS-68-15 | unit |
| 68-REQ-4.2 | TS-68-16 | unit |
| 68-REQ-4.3 | TS-68-15 | unit |
| 68-REQ-4.4 | TS-68-15 | unit |
| 68-REQ-4.E1 | — | (process) |
| 68-REQ-5.1 | TS-68-12 | unit |
| 68-REQ-5.2 | TS-68-14 | unit |
| 68-REQ-5.3 | TS-68-13 | unit |
| 68-REQ-5.E1 | TS-68-E3 | unit |
| 68-REQ-5.E2 | TS-68-14 | unit |
| 68-REQ-6.1 | TS-68-3 | unit |
| 68-REQ-6.E1 | TS-68-17 | unit |
| Property 1 | TS-68-P1 | property |
| Property 2 | TS-68-P2 | property |
| Property 6 | TS-68-P3 | property |
| Property 7 | TS-68-P4 | property |
| Property 9 | TS-68-P5 | property |
| Property 10 | TS-68-P6 | property |
