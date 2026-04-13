# Test Specification: Archetype Profiles

## Overview

Tests verify profile loading, 3-layer prompt assembly, init command, and
custom archetype extensibility. Unit tests cover individual functions.
Property tests verify invariants across configurations. Smoke tests trace
end-to-end paths.

## Test Cases

### TS-99-1: 3-Layer Prompt Order

**Requirement:** 99-REQ-1.1
**Type:** unit
**Description:** Verify prompt layers appear in correct order.

**Preconditions:** CLAUDE.md exists, profile exists, task context available.
**Input:** `build_system_prompt(context, archetype="coder", project_dir=tmp)`
**Expected:** Output contains project context before profile content,
profile content before task context.

**Assertion pseudocode:**
```
prompt = build_system_prompt(ctx, archetype="coder", project_dir=tmp)
idx_claude = prompt.index(claude_md_content)
idx_profile = prompt.index(profile_content)
idx_task = prompt.index(task_context_marker)
ASSERT idx_claude < idx_profile < idx_task
```

### TS-99-2: Project Profile Override

**Requirement:** 99-REQ-1.2, 99-REQ-1.3
**Type:** unit
**Description:** Verify project profile replaces package default.

**Preconditions:** Both project and default profiles exist for "coder".
**Input:** `load_profile("coder", project_dir=tmp_with_custom_profile)`
**Expected:** Returns project profile content, not default.

**Assertion pseudocode:**
```
write(tmp / ".agent-fox/profiles/coder.md", "CUSTOM CODER PROFILE")
content = load_profile("coder", project_dir=tmp)
ASSERT content == "CUSTOM CODER PROFILE"
ASSERT "default" not in content.lower()
```

### TS-99-3: Default Profile Fallback

**Requirement:** 99-REQ-1.2
**Type:** unit
**Description:** Verify fallback to package default when no project profile.

**Preconditions:** No project profile exists.
**Input:** `load_profile("coder", project_dir=tmp_empty)`
**Expected:** Returns package default profile content.

**Assertion pseudocode:**
```
content = load_profile("coder", project_dir=tmp_empty)
ASSERT len(content) > 0
ASSERT "Identity" in content  # default profile has sections
```

### TS-99-4: Default Profiles Exist

**Requirement:** 99-REQ-2.1
**Type:** unit
**Description:** Verify all built-in archetypes have default profiles.

**Preconditions:** None.
**Input:** Check package for each built-in archetype profile.
**Expected:** Files exist for coder, reviewer, verifier, maintainer.

**Assertion pseudocode:**
```
for name in ["coder", "reviewer", "verifier", "maintainer"]:
    content = load_profile(name, project_dir=None)
    ASSERT len(content) > 0
```

### TS-99-5: Default Profile Structure

**Requirement:** 99-REQ-2.2
**Type:** unit
**Description:** Verify default profiles contain 4 required sections.

**Preconditions:** None.
**Input:** Read each default profile.
**Expected:** Each contains Identity, Rules, Focus areas, Output format.

**Assertion pseudocode:**
```
for name in ["coder", "reviewer", "verifier", "maintainer"]:
    content = load_profile(name, project_dir=None)
    ASSERT "## Identity" in content
    ASSERT "## Rules" in content
    ASSERT "## Focus" in content  # "Focus areas" or "Focus Areas"
    ASSERT "## Output" in content  # "Output format" or "Output Format"
```

### TS-99-6: Init Profiles Creates Files

**Requirement:** 99-REQ-3.1
**Type:** unit
**Description:** Verify init --profiles copies default profiles.

**Preconditions:** Empty project directory.
**Input:** `init_profiles(project_dir=tmp)`
**Expected:** Files created in `.agent-fox/profiles/` for all built-in archetypes.
Returns list of paths.

**Assertion pseudocode:**
```
paths = init_profiles(project_dir=tmp)
ASSERT len(paths) >= 4
for name in ["coder", "reviewer", "verifier", "maintainer"]:
    ASSERT (tmp / ".agent-fox/profiles" / f"{name}.md").exists()
```

### TS-99-7: Init Profiles Preserves Existing

**Requirement:** 99-REQ-3.2
**Type:** unit
**Description:** Verify init --profiles skips existing files.

**Preconditions:** Project has custom coder.md profile.
**Input:** `init_profiles(project_dir=tmp)` after writing custom coder.md.
**Expected:** coder.md preserved, other profiles created.

**Assertion pseudocode:**
```
profiles_dir = tmp / ".agent-fox/profiles"
profiles_dir.mkdir(parents=True)
(profiles_dir / "coder.md").write_text("MY CUSTOM CODER")
paths = init_profiles(project_dir=tmp)
ASSERT "coder.md" not in [p.name for p in paths]
ASSERT (profiles_dir / "coder.md").read_text() == "MY CUSTOM CODER"
```

### TS-99-8: Custom Archetype Profile

**Requirement:** 99-REQ-4.1
**Type:** unit
**Description:** Verify custom archetype detected from profile existence.

**Preconditions:** Profile at `.agent-fox/profiles/deployer.md`.
**Input:** `has_custom_profile("deployer", project_dir=tmp)`
**Expected:** Returns True.

**Assertion pseudocode:**
```
(tmp / ".agent-fox/profiles/deployer.md").write_text("# Deployer")
ASSERT has_custom_profile("deployer", project_dir=tmp) is True
ASSERT has_custom_profile("unknown", project_dir=tmp) is False
```

### TS-99-9: Custom Archetype Permission Preset

**Requirement:** 99-REQ-4.2
**Type:** unit
**Description:** Verify custom archetype inherits permission preset.

**Preconditions:** Config with `archetypes.custom.deployer.permissions = "coder"`.
**Input:** `get_archetype("deployer", project_dir=tmp, config=cfg)`
**Expected:** Returns ArchetypeEntry with coder's allowlist.

**Assertion pseudocode:**
```
entry = get_archetype("deployer", project_dir=tmp, config=cfg_with_deployer)
coder = ARCHETYPE_REGISTRY["coder"]
ASSERT entry.default_allowlist == coder.default_allowlist
```

### TS-99-10: Custom Archetype In Task Group

**Requirement:** 99-REQ-4.3
**Type:** integration
**Description:** Verify custom archetype works in task graph execution.

**Preconditions:** Profile + config + Node(archetype="deployer").
**Input:** Build prompt for deployer archetype.
**Expected:** Prompt uses deployer profile content.

**Assertion pseudocode:**
```
prompt = build_system_prompt(ctx, archetype="deployer", project_dir=tmp)
ASSERT "Deployer" in prompt
```

### TS-99-11: load_profile Strips Frontmatter

**Requirement:** 99-REQ-5.3
**Type:** unit
**Description:** Verify YAML frontmatter is stripped from profiles.

**Preconditions:** Profile with frontmatter.
**Input:** `load_profile("test_arch", project_dir=tmp)`
**Expected:** Returned content has no frontmatter delimiters.

**Assertion pseudocode:**
```
write(tmp / ".agent-fox/profiles/test_arch.md",
    "---\nname: test\n---\n# Profile Content")
content = load_profile("test_arch", project_dir=tmp)
ASSERT content.strip().startswith("# Profile Content")
ASSERT "---" not in content
```

### TS-99-12: load_profile Function Signature

**Requirement:** 99-REQ-5.1, 99-REQ-5.2
**Type:** unit
**Description:** Verify load_profile accepts archetype and project_dir.

**Preconditions:** None.
**Input:** `load_profile("coder", project_dir=None)`
**Expected:** Returns package default content.

**Assertion pseudocode:**
```
content = load_profile("coder", project_dir=None)
ASSERT isinstance(content, str)
ASSERT len(content) > 0
```

## Property Test Cases

### TS-99-P1: 3-Layer Order

**Property:** Property 1 from design.md
**Validates:** 99-REQ-1.1
**Type:** property
**Description:** Project context always precedes profile precedes task context.

**For any:** Archetype name, valid project dir, valid context.
**Invariant:** In the assembled prompt, the three layers appear in order.

**Assertion pseudocode:**
```
FOR ANY archetype IN built_in_archetypes:
    prompt = build_system_prompt(ctx, archetype=archetype, project_dir=tmp)
    ASSERT layer_order_correct(prompt)
```

### TS-99-P2: Project Override Precedence

**Property:** Property 2 from design.md
**Validates:** 99-REQ-1.2, 99-REQ-1.3
**Type:** property
**Description:** Project profile always takes precedence over default.

**For any:** Archetype with both project and default profiles.
**Invariant:** load_profile returns project content.

**Assertion pseudocode:**
```
FOR ANY archetype IN built_in_archetypes:
    write(project_dir / f".agent-fox/profiles/{archetype}.md", f"CUSTOM:{archetype}")
    content = load_profile(archetype, project_dir=project_dir)
    ASSERT content.startswith(f"CUSTOM:{archetype}")
```

### TS-99-P3: Default Profile Completeness

**Property:** Property 3 from design.md
**Validates:** 99-REQ-2.1
**Type:** property
**Description:** Every built-in archetype has a default profile.

**For any:** Built-in archetype name.
**Invariant:** load_profile(name, project_dir=None) returns non-empty string.

**Assertion pseudocode:**
```
FOR ANY name IN {"coder", "reviewer", "verifier", "maintainer"}:
    content = load_profile(name, project_dir=None)
    ASSERT len(content) > 0
```

### TS-99-P4: Init Idempotence

**Property:** Property 4 from design.md
**Validates:** 99-REQ-3.2
**Type:** property
**Description:** Repeated init calls never overwrite existing profiles.

**For any:** Sequence of init calls with pre-existing files.
**Invariant:** Pre-existing file content is unchanged.

**Assertion pseudocode:**
```
write(project_dir / ".agent-fox/profiles/coder.md", "ORIGINAL")
init_profiles(project_dir)
init_profiles(project_dir)  # second call
ASSERT read(project_dir / ".agent-fox/profiles/coder.md") == "ORIGINAL"
```

### TS-99-P5: Custom Archetype Permission Inheritance

**Property:** Property 5 from design.md
**Validates:** 99-REQ-4.2, 99-REQ-4.4
**Type:** property
**Description:** Custom archetype inherits preset's permissions.

**For any:** Custom archetype with permissions preset pointing to a built-in.
**Invariant:** Resolved entry has same allowlist as the preset archetype.

**Assertion pseudocode:**
```
FOR ANY preset IN {"coder", "reviewer", "verifier"}:
    entry = get_archetype("custom", project_dir=tmp, config=cfg(permissions=preset))
    preset_entry = ARCHETYPE_REGISTRY[preset]
    ASSERT entry.default_allowlist == preset_entry.default_allowlist
```

## Edge Case Tests

### TS-99-E1: Missing CLAUDE.md

**Requirement:** 99-REQ-1.E1
**Type:** unit
**Description:** Prompt assembly works without CLAUDE.md.

**Preconditions:** Project dir with no CLAUDE.md.
**Input:** `build_system_prompt(ctx, archetype="coder", project_dir=tmp_no_claude)`
**Expected:** Prompt contains profile and task context, no error.

**Assertion pseudocode:**
```
prompt = build_system_prompt(ctx, archetype="coder", project_dir=tmp_no_claude)
ASSERT len(prompt) > 0
# No exception raised
```

### TS-99-E2: Missing Profile

**Requirement:** 99-REQ-1.E2
**Type:** unit
**Description:** Missing profile logs warning and uses empty string.

**Preconditions:** No profile for "nonexistent_archetype".
**Input:** `load_profile("nonexistent_archetype", project_dir=tmp)`
**Expected:** Returns empty string, logs warning.

**Assertion pseudocode:**
```
content = load_profile("nonexistent_archetype", project_dir=tmp)
ASSERT content == ""
ASSERT warning_logged("nonexistent_archetype")
```

### TS-99-E3: Init Creates Directories

**Requirement:** 99-REQ-3.E1
**Type:** unit
**Description:** Init creates .agent-fox/profiles/ if missing.

**Preconditions:** Project dir with no .agent-fox/.
**Input:** `init_profiles(project_dir=tmp)`
**Expected:** Directory created, files copied.

**Assertion pseudocode:**
```
ASSERT not (tmp / ".agent-fox").exists()
init_profiles(project_dir=tmp)
ASSERT (tmp / ".agent-fox/profiles").is_dir()
```

### TS-99-E4: Custom Without Preset

**Requirement:** 99-REQ-4.E1
**Type:** unit
**Description:** Custom archetype without preset defaults to coder.

**Preconditions:** Profile exists but no config preset.
**Input:** `get_archetype("deployer", project_dir=tmp, config=cfg_no_preset)`
**Expected:** Returns entry with coder permissions, logs warning.

**Assertion pseudocode:**
```
entry = get_archetype("deployer", project_dir=tmp, config=cfg_no_preset)
ASSERT entry.default_allowlist == ARCHETYPE_REGISTRY["coder"].default_allowlist
ASSERT warning_logged("deployer")
```

### TS-99-E5: Invalid Permission Preset

**Requirement:** 99-REQ-4.E2
**Type:** unit
**Description:** Non-existent preset raises config error.

**Preconditions:** Config with `deployer.permissions = "nonexistent"`.
**Input:** `get_archetype("deployer", project_dir=tmp, config=cfg_bad_preset)`
**Expected:** ConfigurationError raised.

**Assertion pseudocode:**
```
WITH RAISES ConfigurationError:
    get_archetype("deployer", project_dir=tmp, config=cfg_bad_preset)
```

### TS-99-E6: load_profile With None Project Dir

**Requirement:** 99-REQ-5.E1
**Type:** unit
**Description:** None project_dir uses package default only.

**Preconditions:** None.
**Input:** `load_profile("coder", project_dir=None)`
**Expected:** Returns package default content.

**Assertion pseudocode:**
```
content = load_profile("coder", project_dir=None)
ASSERT len(content) > 0
```

## Integration Smoke Tests

### TS-99-SMOKE-1: Prompt With Project Profile

**Execution Path:** Path 1 from design.md
**Description:** End-to-end prompt assembly with custom project profile.

**Setup:** Create project dir with CLAUDE.md and custom coder profile.
Real profile loading, real prompt builder. Mock only claude-code-sdk.

**Trigger:** `build_system_prompt(ctx, archetype="coder", project_dir=tmp)`

**Expected side effects:**
- Prompt contains CLAUDE.md content
- Prompt contains custom profile content (not default)
- Prompt contains task context

**Must NOT satisfy with:** Mocking load_profile or build_system_prompt.

**Assertion pseudocode:**
```
write(tmp / "CLAUDE.md", "PROJECT RULES")
write(tmp / ".agent-fox/profiles/coder.md", "CUSTOM IDENTITY")
prompt = build_system_prompt(ctx, archetype="coder", project_dir=tmp)
ASSERT "PROJECT RULES" in prompt
ASSERT "CUSTOM IDENTITY" in prompt
ASSERT prompt.index("PROJECT RULES") < prompt.index("CUSTOM IDENTITY")
```

### TS-99-SMOKE-2: Custom Archetype Session

**Execution Path:** Path 3 from design.md
**Description:** End-to-end custom archetype resolution and prompt.

**Setup:** Project with deployer profile and config. Real archetype resolution,
real profile loading. Mock claude-code-sdk.

**Trigger:** Build prompt for archetype="deployer".

**Expected side effects:**
- get_archetype returns entry with coder permissions
- Prompt contains deployer profile content

**Must NOT satisfy with:** Mocking get_archetype or load_profile.

**Assertion pseudocode:**
```
write(tmp / ".agent-fox/profiles/deployer.md", "# Deployer Profile")
entry = get_archetype("deployer", project_dir=tmp, config=cfg)
ASSERT entry.default_allowlist == ARCHETYPE_REGISTRY["coder"].default_allowlist
prompt = build_system_prompt(ctx, archetype="deployer", project_dir=tmp)
ASSERT "Deployer Profile" in prompt
```

### TS-99-SMOKE-3: Init Then Load

**Execution Path:** Path 4 + Path 2 from design.md
**Description:** Init creates profiles that are then loadable.

**Setup:** Empty project dir. Real init and load functions.

**Trigger:** `init_profiles(tmp)` then `load_profile("coder", tmp)`

**Expected side effects:**
- Profiles created on disk
- Loaded profile matches default content

**Must NOT satisfy with:** Mocking init_profiles or load_profile.

**Assertion pseudocode:**
```
init_profiles(project_dir=tmp)
content = load_profile("coder", project_dir=tmp)
default = load_profile("coder", project_dir=None)
ASSERT content == default
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 99-REQ-1.1 | TS-99-1 | unit |
| 99-REQ-1.2 | TS-99-2, TS-99-3 | unit |
| 99-REQ-1.3 | TS-99-2 | unit |
| 99-REQ-1.E1 | TS-99-E1 | unit |
| 99-REQ-1.E2 | TS-99-E2 | unit |
| 99-REQ-2.1 | TS-99-4 | unit |
| 99-REQ-2.2 | TS-99-5 | unit |
| 99-REQ-2.3 | TS-99-4 | unit |
| 99-REQ-3.1 | TS-99-6 | unit |
| 99-REQ-3.2 | TS-99-7 | unit |
| 99-REQ-3.3 | TS-99-6 | unit |
| 99-REQ-3.E1 | TS-99-E3 | unit |
| 99-REQ-4.1 | TS-99-8 | unit |
| 99-REQ-4.2 | TS-99-9 | unit |
| 99-REQ-4.3 | TS-99-10 | integration |
| 99-REQ-4.4 | TS-99-9 | unit |
| 99-REQ-4.E1 | TS-99-E4 | unit |
| 99-REQ-4.E2 | TS-99-E5 | unit |
| 99-REQ-5.1 | TS-99-12 | unit |
| 99-REQ-5.2 | TS-99-12 | unit |
| 99-REQ-5.3 | TS-99-11 | unit |
| 99-REQ-5.E1 | TS-99-E6 | unit |
| Property 1 | TS-99-P1 | property |
| Property 2 | TS-99-P2 | property |
| Property 3 | TS-99-P3 | property |
| Property 4 | TS-99-P4 | property |
| Property 5 | TS-99-P5 | property |
