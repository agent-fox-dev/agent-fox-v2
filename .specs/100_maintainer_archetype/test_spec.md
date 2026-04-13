# Test Specification: Maintainer Archetype

## Overview

Tests verify the maintainer archetype definition, triage absorption,
extraction stub, and nightshift integration. Unit tests cover types and
registry. Property tests verify invariants. Smoke tests trace triage flow.

## Test Cases

### TS-100-1: Maintainer Entry With Modes

**Requirement:** 100-REQ-1.1
**Type:** unit
**Description:** Verify maintainer archetype has hunt and extraction modes.

**Preconditions:** None.
**Input:** `ARCHETYPE_REGISTRY["maintainer"]`
**Expected:** Entry has modes dict with keys `"hunt"` and `"extraction"`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["maintainer"]
ASSERT set(entry.modes.keys()) == {"hunt", "extraction"}
```

### TS-100-2: Hunt Mode Config

**Requirement:** 100-REQ-1.2
**Type:** unit
**Description:** Verify hunt mode has correct allowlist and tier.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["maintainer"], "hunt")`
**Expected:** allowlist=["ls","cat","git","wc","head","tail"],
model_tier="STANDARD", task_assignable=False.

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["maintainer"], "hunt")
ASSERT set(cfg.default_allowlist) == {"ls", "cat", "git", "wc", "head", "tail"}
ASSERT cfg.default_model_tier == "STANDARD"
ASSERT cfg.task_assignable is False
```

### TS-100-3: Extraction Mode Config

**Requirement:** 100-REQ-1.3
**Type:** unit
**Description:** Verify extraction mode has no shell access.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["maintainer"], "extraction")`
**Expected:** allowlist=[], model_tier="STANDARD", task_assignable=False.

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["maintainer"], "extraction")
ASSERT cfg.default_allowlist == []
ASSERT cfg.default_model_tier == "STANDARD"
```

### TS-100-4: Maintainer Not Task Assignable

**Requirement:** 100-REQ-1.4
**Type:** unit
**Description:** Verify maintainer base entry is not task assignable.

**Preconditions:** None.
**Input:** `ARCHETYPE_REGISTRY["maintainer"]`
**Expected:** task_assignable=False.

**Assertion pseudocode:**
```
ASSERT ARCHETYPE_REGISTRY["maintainer"].task_assignable is False
```

### TS-100-5: Triage Removed From Registry

**Requirement:** 100-REQ-2.1
**Type:** unit
**Description:** Verify triage is not in the registry.

**Preconditions:** None.
**Input:** Check ARCHETYPE_REGISTRY keys.
**Expected:** "triage" not in registry.

**Assertion pseudocode:**
```
ASSERT "triage" not in ARCHETYPE_REGISTRY
```

### TS-100-6: Triage Uses Maintainer Hunt

**Requirement:** 100-REQ-2.2
**Type:** unit
**Description:** Verify run_batch_triage resolves model tier from
maintainer:hunt.

**Preconditions:** Mock resolve_model_tier to capture args.
**Input:** Call `run_batch_triage(issues, edges, config)`.
**Expected:** resolve_model_tier called with ("maintainer", mode="hunt").

**Assertion pseudocode:**
```
with mock(resolve_model_tier) as m:
    run_batch_triage(issues, edges, config)
    ASSERT m.called_with(config, "maintainer", mode="hunt")
```

### TS-100-7: Maintainer Template Exists

**Requirement:** 100-REQ-3.1
**Type:** unit
**Description:** Verify maintainer.md template exists with mode sections.

**Preconditions:** None.
**Input:** Read maintainer.md template.
**Expected:** File exists, contains hunt and extraction sections.

**Assertion pseudocode:**
```
content = read_template("maintainer.md")
ASSERT "hunt" in content.lower()
ASSERT "extraction" in content.lower()
```

### TS-100-8: ExtractionInput Dataclass

**Requirement:** 100-REQ-4.1
**Type:** unit
**Description:** Verify ExtractionInput has required fields.

**Preconditions:** None.
**Input:** `ExtractionInput(session_id="s1", transcript="...",
spec_name="spec", archetype="coder")`
**Expected:** All fields accessible, frozen.

**Assertion pseudocode:**
```
ei = ExtractionInput(session_id="s1", transcript="hello",
    spec_name="test", archetype="coder")
ASSERT ei.session_id == "s1"
ASSERT ei.transcript == "hello"
ASSERT ei.mode is None
```

### TS-100-9: ExtractionResult Dataclass

**Requirement:** 100-REQ-4.2
**Type:** unit
**Description:** Verify ExtractionResult has required fields.

**Preconditions:** None.
**Input:** `ExtractionResult()`
**Expected:** defaults: facts=[], session_id="", status="not_implemented".

**Assertion pseudocode:**
```
er = ExtractionResult()
ASSERT er.facts == []
ASSERT er.status == "not_implemented"
```

### TS-100-10: extract_knowledge Stub

**Requirement:** 100-REQ-4.3
**Type:** unit
**Description:** Verify stub returns empty result without error.

**Preconditions:** None.
**Input:** `extract_knowledge(ExtractionInput(...))`
**Expected:** Returns ExtractionResult with status="not_implemented".

**Assertion pseudocode:**
```
result = extract_knowledge(ExtractionInput(
    session_id="s1", transcript="...", spec_name="spec", archetype="coder"))
ASSERT result.status == "not_implemented"
ASSERT result.facts == []
ASSERT result.session_id == "s1"
```

### TS-100-11: Nightshift Model Tier Resolution

**Requirement:** 100-REQ-5.1
**Type:** unit
**Description:** Verify nightshift resolves STANDARD tier for triage.

**Preconditions:** Default config.
**Input:** `resolve_model_tier(config, "maintainer", mode="hunt")`
**Expected:** Returns "STANDARD".

**Assertion pseudocode:**
```
tier = resolve_model_tier(config, "maintainer", mode="hunt")
ASSERT tier == "STANDARD"
```

## Property Test Cases

### TS-100-P1: Maintainer Mode Config

**Property:** Property 1 from design.md
**Validates:** 100-REQ-1.1, 100-REQ-1.2, 100-REQ-1.3
**Type:** property
**Description:** Each maintainer mode resolves to correct permissions.

**For any:** Mode in {"hunt", "extraction"}.
**Invariant:** Resolved config matches expected allowlist and tier.

**Assertion pseudocode:**
```
EXPECTED = {
    "hunt": (["ls","cat","git","wc","head","tail"], "STANDARD"),
    "extraction": ([], "STANDARD"),
}
FOR ANY mode IN EXPECTED:
    cfg = resolve_effective_config(ARCHETYPE_REGISTRY["maintainer"], mode)
    ASSERT (sorted(cfg.default_allowlist), cfg.default_model_tier) == (sorted(EXPECTED[mode][0]), EXPECTED[mode][1])
```

### TS-100-P2: Triage Removed

**Property:** Property 2 from design.md
**Validates:** 100-REQ-2.1
**Type:** property
**Description:** Triage not in registry.

**For any:** N/A (deterministic check).
**Invariant:** "triage" not in ARCHETYPE_REGISTRY.

**Assertion pseudocode:**
```
ASSERT "triage" not in ARCHETYPE_REGISTRY
```

### TS-100-P3: Extraction Stub Safety

**Property:** Property 3 from design.md
**Validates:** 100-REQ-4.3, 100-REQ-4.E1
**Type:** property
**Description:** Extraction stub never raises, always returns valid result.

**For any:** ExtractionInput with arbitrary string fields.
**Invariant:** extract_knowledge returns ExtractionResult with
status="not_implemented" and does not raise.

**Assertion pseudocode:**
```
FOR ANY session_id: str, transcript: str, spec: str, arch: str:
    inp = ExtractionInput(session_id=session_id, transcript=transcript,
        spec_name=spec, archetype=arch)
    result = extract_knowledge(inp)
    ASSERT isinstance(result, ExtractionResult)
    ASSERT result.status == "not_implemented"
```

### TS-100-P4: Nightshift Resolution

**Property:** Property 4 from design.md
**Validates:** 100-REQ-5.1, 100-REQ-5.2
**Type:** property
**Description:** Nightshift triage always resolves via maintainer:hunt.

**For any:** Valid config.
**Invariant:** resolve_model_tier(config, "maintainer", mode="hunt") returns
a valid tier string.

**Assertion pseudocode:**
```
FOR ANY config: valid AgentFoxConfig:
    tier = resolve_model_tier(config, "maintainer", mode="hunt")
    ASSERT tier in {"SIMPLE", "STANDARD", "ADVANCED"}
```

## Edge Case Tests

### TS-100-E1: Triage Fallback

**Requirement:** 100-REQ-1.E1
**Type:** unit
**Description:** get_archetype("triage") warns and falls back to coder.

**Preconditions:** None.
**Input:** `get_archetype("triage")`
**Expected:** Returns coder entry, logs warning.

**Assertion pseudocode:**
```
entry = get_archetype("triage")
ASSERT entry.name == "coder"
ASSERT warning_logged("triage")
```

### TS-100-E2: Old Triage Config Key

**Requirement:** 100-REQ-2.E1
**Type:** unit
**Description:** Config with archetypes.triage logs deprecation.

**Preconditions:** Config TOML with unknown field handled by pydantic extra="ignore".
**Input:** Parse config with triage key.
**Expected:** No error (extra="ignore"), but deprecation warning logged if
explicit validation is added.

**Assertion pseudocode:**
```
# Config parsing does not fail (extra="ignore")
config = parse_config(toml_with_triage_key)
ASSERT config is not None
```

### TS-100-E3: Extraction Stub No Exception

**Requirement:** 100-REQ-4.E1
**Type:** unit
**Description:** extract_knowledge never raises.

**Preconditions:** None.
**Input:** Various ExtractionInput values including empty strings.
**Expected:** Always returns valid result.

**Assertion pseudocode:**
```
result = extract_knowledge(ExtractionInput(
    session_id="", transcript="", spec_name="", archetype=""))
ASSERT result.status == "not_implemented"
```

## Integration Smoke Tests

### TS-100-SMOKE-1: Nightshift Triage Via Maintainer

**Execution Path:** Path 1 from design.md
**Description:** Verify triage AI call uses maintainer:hunt resolution.

**Setup:** Real resolve_model_tier and resolve_security_config. Mock AI
call (external I/O). Real config with maintainer entry.

**Trigger:** `run_batch_triage(issues, edges, config)`

**Expected side effects:**
- Model tier resolved to "STANDARD" (from maintainer:hunt)
- Security config uses hunt allowlist

**Must NOT satisfy with:** Mocking resolve_model_tier or
resolve_security_config.

**Assertion pseudocode:**
```
# With real config and registry
tier = resolve_model_tier(config, "maintainer", mode="hunt")
ASSERT tier == "STANDARD"
sec = resolve_security_config(config, "maintainer", mode="hunt")
ASSERT sec is not None
ASSERT set(sec.bash_allowlist) == {"ls", "cat", "git", "wc", "head", "tail"}
```

### TS-100-SMOKE-2: Extraction Stub End-to-End

**Execution Path:** Path 2 from design.md
**Description:** Verify extraction stub is callable and returns valid result.

**Setup:** Real extraction module.

**Trigger:** `extract_knowledge(ExtractionInput(...))`

**Expected side effects:**
- Returns ExtractionResult with status="not_implemented"
- No exception, no side effects

**Must NOT satisfy with:** Mocking extract_knowledge.

**Assertion pseudocode:**
```
result = extract_knowledge(ExtractionInput(
    session_id="test", transcript="session content",
    spec_name="spec", archetype="coder"))
ASSERT result.status == "not_implemented"
ASSERT result.facts == []
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 100-REQ-1.1 | TS-100-1 | unit |
| 100-REQ-1.2 | TS-100-2 | unit |
| 100-REQ-1.3 | TS-100-3 | unit |
| 100-REQ-1.4 | TS-100-4 | unit |
| 100-REQ-1.E1 | TS-100-E1 | unit |
| 100-REQ-2.1 | TS-100-5 | unit |
| 100-REQ-2.2 | TS-100-6 | unit |
| 100-REQ-2.3 | TS-100-7 | unit |
| 100-REQ-2.E1 | TS-100-E2 | unit |
| 100-REQ-3.1 | TS-100-7 | unit |
| 100-REQ-3.2 | TS-100-7 | unit |
| 100-REQ-3.3 | TS-100-7 | unit |
| 100-REQ-4.1 | TS-100-8 | unit |
| 100-REQ-4.2 | TS-100-9 | unit |
| 100-REQ-4.3 | TS-100-10 | unit |
| 100-REQ-4.E1 | TS-100-E3 | unit |
| 100-REQ-5.1 | TS-100-11 | unit |
| 100-REQ-5.2 | TS-100-11 | unit |
| 100-REQ-5.3 | TS-100-6 | unit |
| Property 1 | TS-100-P1 | property |
| Property 2 | TS-100-P2 | property |
| Property 3 | TS-100-P3 | property |
| Property 4 | TS-100-P4 | property |
