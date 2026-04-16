# Test Specification: Reviewer Consolidation

## Overview

Tests verify that the reviewer consolidation correctly replaces 5 separate
archetypes with mode-bearing reviewer and coder entries, updates injection
and convergence dispatch, and enforces the new config schema.

## Test Cases

### TS-98-1: Reviewer Entry With Modes

**Requirement:** 98-REQ-1.1
**Type:** unit
**Description:** Verify reviewer archetype has all 4 modes in registry.

**Preconditions:** None.
**Input:** `ARCHETYPE_REGISTRY["reviewer"]`
**Expected:** Entry has modes dict with keys `"pre-review"`, `"drift-review"`,
`"audit-review"`, `"fix-review"`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["reviewer"]
ASSERT set(entry.modes.keys()) == {"pre-review", "drift-review", "audit-review", "fix-review"}
```

### TS-98-2: Pre-review Mode Config

**Requirement:** 98-REQ-1.2
**Type:** unit
**Description:** Verify pre-review has no shell, auto_pre injection, STANDARD tier.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "pre-review")`
**Expected:** allowlist=[], injection="auto_pre", model_tier="STANDARD".

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "pre-review")
ASSERT cfg.default_allowlist == []
ASSERT cfg.injection == "auto_pre"
ASSERT cfg.default_model_tier == "STANDARD"
```

### TS-98-3: Drift-review Mode Config

**Requirement:** 98-REQ-1.3
**Type:** unit
**Description:** Verify drift-review has analysis allowlist and auto_pre injection.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "drift-review")`
**Expected:** allowlist includes `["ls","cat","git","grep","find","head","tail","wc"]`,
injection="auto_pre", model_tier="STANDARD".

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "drift-review")
ASSERT "grep" in cfg.default_allowlist
ASSERT cfg.injection == "auto_pre"
ASSERT cfg.default_model_tier == "STANDARD"
```

### TS-98-4: Audit-review Mode Config

**Requirement:** 98-REQ-1.4
**Type:** unit
**Description:** Verify audit-review has extended allowlist, auto_mid, retry.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "audit-review")`
**Expected:** allowlist includes `"uv"`, injection="auto_mid",
retry_predecessor=True.

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "audit-review")
ASSERT "uv" in cfg.default_allowlist
ASSERT cfg.injection == "auto_mid"
ASSERT cfg.retry_predecessor is True
```

### TS-98-5: Fix-review Mode Config

**Requirement:** 98-REQ-1.5
**Type:** unit
**Description:** Verify fix-review has ADVANCED tier, no injection, extended allowlist.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "fix-review")`
**Expected:** model_tier="ADVANCED", injection=None, allowlist includes "make".

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], "fix-review")
ASSERT cfg.default_model_tier == "ADVANCED"
ASSERT cfg.injection IS None
ASSERT "make" in cfg.default_allowlist
```

### TS-98-6: Coder Fix Mode

**Requirement:** 98-REQ-2.1, 98-REQ-2.2
**Type:** unit
**Description:** Verify coder fix mode matches former fix_coder config.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["coder"], "fix")`
**Expected:** templates=["fix_coding.md"], model_tier="STANDARD",
max_turns=300, thinking adaptive with 64k.

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["coder"], "fix")
ASSERT cfg.templates == ["fix_coding.md"]
ASSERT cfg.default_model_tier == "STANDARD"
ASSERT cfg.default_max_turns == 300
ASSERT cfg.default_thinking_mode == "adaptive"
ASSERT cfg.default_thinking_budget == 64000
```

### TS-98-7: Template File Exists

**Requirement:** 98-REQ-3.1
**Type:** unit
**Description:** Verify reviewer.md template exists and contains mode sections.

**Preconditions:** None.
**Input:** Read `agent_fox/_templates/prompts/reviewer.md`.
**Expected:** File exists, contains markers for all 4 modes.

**Assertion pseudocode:**
```
content = read_template("reviewer.md")
ASSERT "pre-review" in content.lower()
ASSERT "drift-review" in content.lower()
ASSERT "audit-review" in content.lower()
ASSERT "fix-review" in content.lower()
```

### TS-98-8: collect_enabled_auto_pre Returns Reviewer Modes

**Requirement:** 98-REQ-4.1
**Type:** unit
**Description:** Verify auto_pre collection returns reviewer mode entries.

**Preconditions:** Config with reviewer enabled.
**Input:** `collect_enabled_auto_pre(config)`
**Expected:** Returns entries with name="reviewer" and modes "pre-review" and
"drift-review". No entries with name "skeptic" or "oracle".

**Assertion pseudocode:**
```
entries = collect_enabled_auto_pre(config)
names = [(e.name, e.mode) for e in entries]
ASSERT ("reviewer", "pre-review") in names
ASSERT ("reviewer", "drift-review") in names
ASSERT not any(e.name in ("skeptic", "oracle") for e in entries)
```

### TS-98-9: Injection Creates Reviewer Mode Nodes

**Requirement:** 98-REQ-4.2, 98-REQ-4.3
**Type:** integration
**Description:** Verify ensure_graph_archetypes creates reviewer mode nodes.

**Preconditions:** TaskGraph with coder nodes, reviewer enabled.
**Input:** `ensure_graph_archetypes(graph, config)`
**Expected:** Graph contains nodes with archetype="reviewer" and modes
"pre-review", "drift-review". No nodes with archetype "skeptic" or "oracle".

**Assertion pseudocode:**
```
ensure_graph_archetypes(graph, config)
reviewer_nodes = [n for n in graph.nodes.values() if n.archetype == "reviewer"]
modes = {n.mode for n in reviewer_nodes}
ASSERT "pre-review" in modes
old_names = {n.archetype for n in graph.nodes.values()}
ASSERT "skeptic" not in old_names
ASSERT "oracle" not in old_names
```

### TS-98-10: Drift-review Gating

**Requirement:** 98-REQ-4.4
**Type:** unit
**Description:** Verify drift-review is skipped when spec has no existing code.

**Preconditions:** Spec path with no existing code references.
**Input:** `collect_enabled_auto_pre(config, spec_path=no_code_spec)`
**Expected:** Returns pre-review but not drift-review.

**Assertion pseudocode:**
```
entries = collect_enabled_auto_pre(config, spec_path=no_code_spec)
modes = [e.mode for e in entries if e.name == "reviewer"]
ASSERT "pre-review" in modes
ASSERT "drift-review" not in modes
```

### TS-98-11: Convergence Dispatch Pre-review

**Requirement:** 98-REQ-5.1
**Type:** unit
**Description:** Verify pre-review routes to skeptic convergence.

**Preconditions:** Mock convergence results.
**Input:** `converge_reviewer(results, mode="pre-review")`
**Expected:** Uses majority-gated blocking (skeptic algorithm).

**Assertion pseudocode:**
```
# Results with 1/3 instances reporting a critical finding
result = converge_reviewer(three_instance_results, mode="pre-review",
    block_threshold=3)
# Verify skeptic convergence semantics applied
ASSERT result matches expected_skeptic_output
```

### TS-98-12: Convergence Dispatch Audit-review

**Requirement:** 98-REQ-5.3
**Type:** unit
**Description:** Verify audit-review routes to auditor convergence.

**Preconditions:** Mock audit convergence results.
**Input:** `converge_reviewer(results, mode="audit-review")`
**Expected:** Uses union/worst-verdict-wins (auditor algorithm).

**Assertion pseudocode:**
```
result = converge_reviewer(audit_results, mode="audit-review")
ASSERT result matches expected_auditor_output
```

### TS-98-13: Verifier STANDARD Tier

**Requirement:** 98-REQ-6.1
**Type:** unit
**Description:** Verify verifier defaults to STANDARD model tier.

**Preconditions:** None.
**Input:** `ARCHETYPE_REGISTRY["verifier"]`
**Expected:** `default_model_tier == "STANDARD"`.

**Assertion pseudocode:**
```
ASSERT ARCHETYPE_REGISTRY["verifier"].default_model_tier == "STANDARD"
```

### TS-98-14: Verifier Single Instance

**Requirement:** 98-REQ-6.2
**Type:** unit
**Description:** Verify verifier instances clamped to 1.

**Preconditions:** Config with verifier=3.
**Input:** `clamp_instances("verifier", 3)`
**Expected:** Returns 1.

**Assertion pseudocode:**
```
ASSERT clamp_instances("verifier", 3) == 1
```

### TS-98-15: Old Entries Removed

**Requirement:** 98-REQ-7.1
**Type:** unit
**Description:** Verify removed archetypes are not in registry.

**Preconditions:** None.
**Input:** Check ARCHETYPE_REGISTRY keys.
**Expected:** No entries for skeptic, oracle, auditor, fix_reviewer, fix_coder.

**Assertion pseudocode:**
```
for name in ["skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder"]:
    ASSERT name not in ARCHETYPE_REGISTRY
```

### TS-98-16: Config Reviewer Toggle

**Requirement:** 98-REQ-8.1
**Type:** unit
**Description:** Verify ArchetypesConfig has reviewer toggle, not old toggles.

**Preconditions:** None.
**Input:** `ArchetypesConfig()`
**Expected:** Has `reviewer=True`, does not have `skeptic`, `oracle`, `auditor`.

**Assertion pseudocode:**
```
cfg = ArchetypesConfig()
ASSERT cfg.reviewer is True
ASSERT not hasattr(cfg, "skeptic")
```

### TS-98-17: ReviewerConfig

**Requirement:** 98-REQ-8.2
**Type:** unit
**Description:** Verify ReviewerConfig replaces old per-review configs.

**Preconditions:** None.
**Input:** `ReviewerConfig()`
**Expected:** Has pre_review_block_threshold=3, drift_review_block_threshold=None,
audit_min_ts_entries=5, audit_max_retries=2.

**Assertion pseudocode:**
```
rc = ReviewerConfig()
ASSERT rc.pre_review_block_threshold == 3
ASSERT rc.drift_review_block_threshold is None
ASSERT rc.audit_min_ts_entries == 5
```

## Property Test Cases

### TS-98-P1: Mode-Archetype Mapping

**Property:** Property 1 from design.md
**Validates:** 98-REQ-1.1 through 98-REQ-1.5
**Type:** property
**Description:** Every reviewer mode resolves to the correct injection, allowlist, and tier.

**For any:** Mode name in `{"pre-review", "drift-review", "audit-review", "fix-review"}`.
**Invariant:** The resolved config matches the expected values for that mode.

**Assertion pseudocode:**
```
EXPECTED = {
    "pre-review": ([], "auto_pre", "STANDARD"),
    "drift-review": (analysis_list, "auto_pre", "STANDARD"),
    "audit-review": (extended_list, "auto_mid", "STANDARD"),
    "fix-review": (full_list, None, "ADVANCED"),
}
FOR ANY mode IN EXPECTED:
    cfg = resolve_effective_config(ARCHETYPE_REGISTRY["reviewer"], mode)
    ASSERT (cfg.default_allowlist, cfg.injection, cfg.default_model_tier) == EXPECTED[mode]
```

### TS-98-P2: Convergence Dispatch Correctness

**Property:** Property 2 from design.md
**Validates:** 98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3
**Type:** property
**Description:** converge_reviewer routes to correct algorithm by mode.

**For any:** Mode and valid results for that mode.
**Invariant:** Output matches direct call to the underlying algorithm.

**Assertion pseudocode:**
```
FOR mode IN ("pre-review", "drift-review"):
    ASSERT converge_reviewer(results, mode) == converge_skeptic(results)
ASSERT converge_reviewer(audit_results, "audit-review") == converge_auditor(audit_results)
```

### TS-98-P3: Injection Consistency

**Property:** Property 3 from design.md
**Validates:** 98-REQ-4.2, 98-REQ-4.3, 98-REQ-7.1
**Type:** property
**Description:** Injected nodes never use old archetype names.

**For any:** TaskGraph with reviewer enabled.
**Invariant:** After ensure_graph_archetypes, no node has archetype in
{"skeptic", "oracle", "auditor"}.

**Assertion pseudocode:**
```
FOR ANY graph: TaskGraph with reviewer enabled:
    ensure_graph_archetypes(graph, config)
    FOR node IN graph.nodes.values():
        ASSERT node.archetype not in {"skeptic", "oracle", "auditor"}
```

### TS-98-P4: Verifier Single-Instance Invariant

**Property:** Property 4 from design.md
**Validates:** 98-REQ-6.2
**Type:** property
**Description:** Verifier always resolves to 1 instance.

**For any:** Instance count value (1-100).
**Invariant:** clamp_instances("verifier", n) == 1.

**Assertion pseudocode:**
```
FOR ANY n: int(1, 100):
    ASSERT clamp_instances("verifier", n) == 1
```

### TS-98-P5: Coder Fix Mode Equivalence

**Property:** Property 5 from design.md
**Validates:** 98-REQ-2.1, 98-REQ-2.2
**Type:** property
**Description:** Coder fix mode config matches former fix_coder.

**For any:** N/A (deterministic check).
**Invariant:** Resolved coder:fix config has same tier, turns, thinking as
fix_coder baseline.

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["coder"], "fix")
ASSERT cfg.default_model_tier == "STANDARD"
ASSERT cfg.default_max_turns == 300
ASSERT cfg.default_thinking_mode == "adaptive"
ASSERT cfg.default_thinking_budget == 64000
```

### TS-98-P6: Old Names Rejected

**Property:** Property 6 from design.md
**Validates:** 98-REQ-7.1
**Type:** property
**Description:** No old name appears in registry.

**For any:** Name in {"skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder"}.
**Invariant:** name not in ARCHETYPE_REGISTRY.

**Assertion pseudocode:**
```
FOR ANY name IN {"skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder"}:
    ASSERT name not in ARCHETYPE_REGISTRY
```

## Edge Case Tests

### TS-98-E1: Old Config Key Rejected

**Requirement:** 98-REQ-1.E1, 98-REQ-8.E1
**Type:** unit
**Description:** Config with old archetype keys raises validation error.

**Preconditions:** TOML config containing `archetypes.skeptic = true`.
**Input:** Parse config.
**Expected:** Validation error with message mentioning "reviewer" and mode names.

**Assertion pseudocode:**
```
WITH RAISES ValidationError as err:
    parse_config(toml_with_skeptic_key)
ASSERT "reviewer" in str(err)
```

### TS-98-E2: Coder Without Mode

**Requirement:** 98-REQ-2.E1
**Type:** unit
**Description:** Coder with mode=None behaves as before.

**Preconditions:** None.
**Input:** `resolve_effective_config(ARCHETYPE_REGISTRY["coder"], None)`
**Expected:** templates=["coding.md"], default coder config.

**Assertion pseudocode:**
```
cfg = resolve_effective_config(ARCHETYPE_REGISTRY["coder"], None)
ASSERT cfg.templates == ["coding.md"]
ASSERT cfg.default_max_turns == 300
```

### TS-98-E3: Reviewer Disabled

**Requirement:** 98-REQ-4.E1
**Type:** unit
**Description:** Disabled reviewer skips all mode injections.

**Preconditions:** Config with reviewer=false.
**Input:** `collect_enabled_auto_pre(config)`
**Expected:** No reviewer entries returned.

**Assertion pseudocode:**
```
config = make_config(reviewer=False)
entries = collect_enabled_auto_pre(config)
ASSERT not any(e.name == "reviewer" for e in entries)
```

### TS-98-E4: Unknown Convergence Mode

**Requirement:** 98-REQ-5.E1
**Type:** unit
**Description:** Unknown mode in converge_reviewer raises ValueError.

**Preconditions:** None.
**Input:** `converge_reviewer(results, mode="unknown")`
**Expected:** ValueError raised.

**Assertion pseudocode:**
```
WITH RAISES ValueError:
    converge_reviewer([], mode="unknown")
```

## Integration Smoke Tests

### TS-98-SMOKE-1: Pre-review End-to-End

**Execution Path:** Path 1 from design.md
**Description:** Verify pre-review injection through convergence.

**Setup:** Real registry, real injection, real convergence. Mock external I/O
(claude-code-sdk session).

**Trigger:** Build graph with coder nodes, run ensure_graph_archetypes, verify
pre-review node exists, simulate session results, run convergence.

**Expected side effects:**
- Graph contains reviewer:pre-review node
- Convergence uses skeptic algorithm

**Must NOT satisfy with:** Mocking injection or convergence logic.

**Assertion pseudocode:**
```
graph = build_test_graph(coder_nodes=3)
ensure_graph_archetypes(graph, config_with_reviewer)
pre_nodes = [n for n in graph.nodes.values()
    if n.archetype == "reviewer" and n.mode == "pre-review"]
ASSERT len(pre_nodes) >= 1
# Simulate convergence
result = converge_reviewer(mock_findings, mode="pre-review", block_threshold=3)
ASSERT "findings" in result or hasattr(result, "findings")
```

### TS-98-SMOKE-2: Drift-review With Gating

**Execution Path:** Path 2 from design.md
**Description:** Verify drift-review gating works end-to-end.

**Setup:** Real injection with spec path pointing to a spec with no code refs.

**Trigger:** collect_enabled_auto_pre(config, spec_path=no_code_spec)

**Expected side effects:**
- Drift-review NOT in returned entries

**Must NOT satisfy with:** Mocking spec_has_existing_code.

**Assertion pseudocode:**
```
entries = collect_enabled_auto_pre(config, spec_path=no_code_spec)
ASSERT not any(e.mode == "drift-review" for e in entries)
entries_with_code = collect_enabled_auto_pre(config, spec_path=has_code_spec)
ASSERT any(e.mode == "drift-review" for e in entries_with_code)
```

### TS-98-SMOKE-3: Coder Fix Mode Session Setup

**Execution Path:** Path 4 from design.md
**Description:** Verify coder:fix mode resolves correct config in session.

**Setup:** Real registry, real SDK resolution. Mock claude-code-sdk.

**Trigger:** NodeSessionRunner(archetype="coder", mode="fix")

**Expected side effects:**
- Model tier resolved to STANDARD
- Template resolved to fix_coding.md

**Must NOT satisfy with:** Mocking resolve_model_tier or resolve_security_config.

**Assertion pseudocode:**
```
runner = NodeSessionRunner(node_id="s:1", config=cfg,
    archetype="coder", mode="fix", ...)
ASSERT runner._resolved_model_id == model_for("STANDARD")
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 98-REQ-1.1 | TS-98-1 | unit |
| 98-REQ-1.2 | TS-98-2 | unit |
| 98-REQ-1.3 | TS-98-3 | unit |
| 98-REQ-1.4 | TS-98-4 | unit |
| 98-REQ-1.5 | TS-98-5 | unit |
| 98-REQ-1.E1 | TS-98-E1 | unit |
| 98-REQ-2.1 | TS-98-6 | unit |
| 98-REQ-2.2 | TS-98-6 | unit |
| 98-REQ-2.E1 | TS-98-E2 | unit |
| 98-REQ-3.1 | TS-98-7 | unit |
| 98-REQ-3.2 | TS-98-7 | unit |
| 98-REQ-3.3 | TS-98-7 | unit |
| 98-REQ-4.1 | TS-98-8 | unit |
| 98-REQ-4.2 | TS-98-9 | integration |
| 98-REQ-4.3 | TS-98-9 | integration |
| 98-REQ-4.4 | TS-98-10 | unit |
| 98-REQ-4.5 | TS-98-8 | unit |
| 98-REQ-4.E1 | TS-98-E3 | unit |
| 98-REQ-5.1 | TS-98-11 | unit |
| 98-REQ-5.2 | TS-98-11 | unit |
| 98-REQ-5.3 | TS-98-12 | unit |
| 98-REQ-5.E1 | TS-98-E4 | unit |
| 98-REQ-6.1 | TS-98-13 | unit |
| 98-REQ-6.2 | TS-98-14 | unit |
| 98-REQ-6.3 | TS-98-13 | unit |
| 98-REQ-7.1 | TS-98-15 | unit |
| 98-REQ-7.2 | TS-98-15 | unit |
| 98-REQ-8.1 | TS-98-16 | unit |
| 98-REQ-8.2 | TS-98-17 | unit |
| 98-REQ-8.3 | TS-98-14 | unit |
| 98-REQ-8.E1 | TS-98-E1 | unit |
| Property 1 | TS-98-P1 | property |
| Property 2 | TS-98-P2 | property |
| Property 3 | TS-98-P3 | property |
| Property 4 | TS-98-P4 | property |
| Property 5 | TS-98-P5 | property |
| Property 6 | TS-98-P6 | property |
