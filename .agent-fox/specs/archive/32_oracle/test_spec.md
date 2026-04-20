# Test Specification: Oracle Agent Archetype

## Overview

This test specification defines test contracts for the oracle archetype feature.
Tests are organized into acceptance criterion tests (TS-32-N), property tests
(TS-32-PN), and edge case tests (TS-32-EN). Each test maps to a specific
requirement or correctness property from the requirements and design documents.

## Test Cases

### TS-32-1: Oracle Archetype Registry Entry

**Requirement:** 32-REQ-1.1
**Type:** unit
**Description:** Verify the oracle entry exists in the archetype registry with
correct fields.

**Preconditions:**
- `ARCHETYPE_REGISTRY` is initialized.

**Input:**
- Look up key `"oracle"` in `ARCHETYPE_REGISTRY`.

**Expected:**
- Entry exists with `name="oracle"`, `injection="auto_pre"`,
  `task_assignable=True`, `default_model_tier="STANDARD"`,
  `templates=["oracle.md"]`, `default_allowlist` containing
  `["ls", "cat", "git", "grep", "find", "head", "tail", "wc"]`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["oracle"]
ASSERT entry.name == "oracle"
ASSERT entry.injection == "auto_pre"
ASSERT entry.task_assignable == True
ASSERT entry.default_model_tier == "STANDARD"
ASSERT "oracle.md" in entry.templates
ASSERT set(entry.default_allowlist) == {"ls", "cat", "git", "grep", "find", "head", "tail", "wc"}
```

### TS-32-2: Oracle Enabled via Config

**Requirement:** 32-REQ-1.2
**Type:** unit
**Description:** Verify oracle is recognized as enabled when config sets
`oracle = true`.

**Preconditions:**
- ArchetypesConfig with `oracle=True`.

**Input:**
- `_is_archetype_enabled("oracle", config)`.

**Expected:**
- Returns `True`.

**Assertion pseudocode:**
```
config = ArchetypesConfig(oracle=True)
ASSERT _is_archetype_enabled("oracle", config) == True
```

### TS-32-3: Oracle Node Injected in Graph

**Requirement:** 32-REQ-2.1
**Type:** unit
**Description:** Verify oracle node is injected before the first coder group
with proper edge.

**Preconditions:**
- One spec with task groups [1, 2, 3]. Oracle enabled, skeptic disabled.

**Input:**
- `build_graph(specs, task_groups, cross_deps, archetypes_config)`.

**Expected:**
- Graph contains node `{spec}:0` with `archetype="oracle"`.
- Edge from `{spec}:0` to `{spec}:1` with `kind="intra_spec"`.

**Assertion pseudocode:**
```
graph = build_graph(specs, groups, [], ArchetypesConfig(oracle=True))
ASSERT "{spec}:0" in graph.nodes
ASSERT graph.nodes["{spec}:0"].archetype == "oracle"
ASSERT Edge("{spec}:0", "{spec}:1", "intra_spec") in graph.edges
```

### TS-32-4: Dual auto_pre (Oracle + Skeptic) Parallel Nodes

**Requirement:** 32-REQ-2.2, 32-REQ-3.1, 32-REQ-3.3
**Type:** unit
**Description:** When both oracle and skeptic are enabled, both get distinct
node IDs and both connect to the first coder group.

**Preconditions:**
- One spec with task groups [1, 2]. Both oracle and skeptic enabled.

**Input:**
- `build_graph(specs, task_groups, cross_deps, archetypes_config)`.

**Expected:**
- Graph contains `{spec}:0:oracle` and `{spec}:0:skeptic` (or `{spec}:0`).
- Both have intra_spec edges to `{spec}:1`.
- No edge between `{spec}:0:oracle` and `{spec}:0:skeptic`.

**Assertion pseudocode:**
```
config = ArchetypesConfig(oracle=True, skeptic=True)
graph = build_graph(specs, groups, [], config)
oracle_id = "{spec}:0:oracle"
skeptic_id = "{spec}:0:skeptic"
ASSERT oracle_id in graph.nodes
ASSERT skeptic_id in graph.nodes
ASSERT Edge(oracle_id, "{spec}:1", "intra_spec") in graph.edges
ASSERT Edge(skeptic_id, "{spec}:1", "intra_spec") in graph.edges
edges_between = [e for e in graph.edges if (e.source == oracle_id and e.target == skeptic_id) or (e.source == skeptic_id and e.target == oracle_id)]
ASSERT len(edges_between) == 0
```

### TS-32-5: Single auto_pre Backward Compatibility

**Requirement:** 32-REQ-3.2
**Type:** unit
**Description:** When only one auto_pre archetype is enabled, the node ID uses
the `{spec}:0` format.

**Preconditions:**
- One spec. Only oracle enabled (skeptic disabled).

**Input:**
- `build_graph(specs, task_groups, cross_deps, archetypes_config)`.

**Expected:**
- Node ID is `{spec}:0` (no archetype suffix).

**Assertion pseudocode:**
```
config = ArchetypesConfig(oracle=True, skeptic=False)
graph = build_graph(specs, groups, [], config)
ASSERT "{spec}:0" in graph.nodes
ASSERT graph.nodes["{spec}:0"].archetype == "oracle"
```

### TS-32-6: Parse Oracle Output - Valid JSON

**Requirement:** 32-REQ-6.1, 32-REQ-6.2
**Type:** unit
**Description:** Verify parse_oracle_output extracts drift findings from valid
JSON.

**Preconditions:**
- None.

**Input:**
- Response text containing:
  ```json
  {"drift_findings": [
    {"severity": "critical", "description": "File removed", "artifact_ref": "foo.py"},
    {"severity": "minor", "description": "Function renamed", "spec_ref": "design.md"}
  ]}
  ```

**Expected:**
- Returns list of 2 DriftFinding instances with matching fields.

**Assertion pseudocode:**
```
response = '```json\n{"drift_findings": [{"severity": "critical", "description": "File removed", "artifact_ref": "foo.py"}, {"severity": "minor", "description": "Function renamed", "spec_ref": "design.md"}]}\n```'
findings = parse_oracle_output(response, "spec_a", "0", "sess_1")
ASSERT len(findings) == 2
ASSERT findings[0].severity == "critical"
ASSERT findings[0].description == "File removed"
ASSERT findings[0].artifact_ref == "foo.py"
ASSERT findings[1].severity == "minor"
ASSERT findings[1].spec_ref == "design.md"
```

### TS-32-7: DriftFinding Dataclass Fields

**Requirement:** 32-REQ-6.3
**Type:** unit
**Description:** Verify DriftFinding has all required fields.

**Preconditions:**
- None.

**Input:**
- Construct a DriftFinding with all fields.

**Expected:**
- All fields accessible and frozen.

**Assertion pseudocode:**
```
f = DriftFinding(id="uuid", severity="critical", description="test",
    spec_ref="design.md", artifact_ref="foo.py",
    spec_name="spec_a", task_group="0", session_id="sess_1")
ASSERT f.id == "uuid"
ASSERT f.severity == "critical"
ASSERT f.spec_ref == "design.md"
ASSERT f.artifact_ref == "foo.py"
ASSERT f.superseded_by is None
```

### TS-32-8: Insert and Query Drift Findings

**Requirement:** 32-REQ-7.1, 32-REQ-7.2, 32-REQ-7.4
**Type:** integration
**Description:** Insert drift findings and query active ones back.

**Preconditions:**
- DuckDB in-memory connection with drift_findings table created.

**Input:**
- Insert 3 drift findings for spec "test_spec", task_group "0".
- Query active drift findings.

**Expected:**
- 3 findings returned, ordered by severity priority.

**Assertion pseudocode:**
```
conn = create_test_db()
findings = [DriftFinding(..., severity="major"), DriftFinding(..., severity="critical"), DriftFinding(..., severity="minor")]
insert_drift_findings(conn, findings)
result = query_active_drift_findings(conn, "test_spec")
ASSERT len(result) == 3
ASSERT result[0].severity == "critical"
ASSERT result[1].severity == "major"
ASSERT result[2].severity == "minor"
```

### TS-32-9: Supersession on Re-insert

**Requirement:** 32-REQ-7.3
**Type:** integration
**Description:** Re-inserting findings supersedes previous ones.

**Preconditions:**
- DuckDB with drift_findings table. First batch already inserted.

**Input:**
- Insert batch 1 (2 findings) for spec "s1", group "0".
- Insert batch 2 (1 finding) for spec "s1", group "0".
- Query active drift findings.

**Expected:**
- Only batch 2 findings returned (1 finding).

**Assertion pseudocode:**
```
insert_drift_findings(conn, batch_1)
insert_drift_findings(conn, batch_2)
result = query_active_drift_findings(conn, "s1", "0")
ASSERT len(result) == 1
ASSERT result[0].session_id == batch_2[0].session_id
```

### TS-32-10: Render Drift Context

**Requirement:** 32-REQ-8.1, 32-REQ-8.2
**Type:** unit
**Description:** Verify drift findings are rendered as grouped markdown.

**Preconditions:**
- DuckDB with active drift findings for spec "test_spec".

**Input:**
- `render_drift_context(conn, "test_spec")`.

**Expected:**
- Returns markdown string starting with `## Oracle Drift Report`.
- Contains `### Critical Findings` and `### Minor Findings` sections.
- Each finding description appears in the output.

**Assertion pseudocode:**
```
insert_drift_findings(conn, [critical_finding, minor_finding])
result = render_drift_context(conn, "test_spec")
ASSERT result is not None
ASSERT "## Oracle Drift Report" in result
ASSERT "### Critical Findings" in result
ASSERT critical_finding.description in result
ASSERT minor_finding.description in result
```

### TS-32-11: Block Threshold Exceeded

**Requirement:** 32-REQ-9.1, 32-REQ-9.2, 32-REQ-9.3
**Type:** unit
**Description:** Oracle blocks when critical findings exceed threshold.

**Preconditions:**
- Oracle settings with `block_threshold=2`.
- Oracle output with 3 critical findings.

**Input:**
- Check blocking logic with 3 critical findings against threshold 2.

**Expected:**
- Oracle node marked as failed.

**Assertion pseudocode:**
```
findings = [DriftFinding(severity="critical", ...) for _ in range(3)]
should_block = count_critical(findings) > block_threshold
ASSERT should_block == True
```

### TS-32-12: Oracle Config Defaults

**Requirement:** 32-REQ-10.1, 32-REQ-10.2, 32-REQ-10.3, 32-REQ-10.4
**Type:** unit
**Description:** Verify oracle config defaults.

**Preconditions:**
- Default ArchetypesConfig.

**Input:**
- Check oracle field and oracle_settings.

**Expected:**
- `oracle` defaults to `False`.
- `oracle_settings.block_threshold` defaults to `None`.

**Assertion pseudocode:**
```
config = ArchetypesConfig()
ASSERT config.oracle == False
ASSERT config.oracle_settings.block_threshold is None
```

### TS-32-13: Hot-loaded Specs Get Oracle Nodes

**Requirement:** 32-REQ-4.1, 32-REQ-4.2
**Type:** integration
**Description:** Newly hot-loaded specs receive oracle nodes.

**Preconditions:**
- Running task graph with oracle enabled. New spec "new_feature" discovered.

**Input:**
- Simulate hot_load_specs + oracle injection.

**Expected:**
- New spec has an oracle node in the graph.
- Oracle node is in "pending" state.

**Assertion pseudocode:**
```
updated_graph, new_specs = hot_load_specs(graph, specs_dir)
# After archetype injection for new specs:
ASSERT "new_feature:0:oracle" in updated_graph.nodes OR "new_feature:0" in updated_graph.nodes
ASSERT state.node_states[oracle_node_id] == "pending"
```

## Property Test Cases

### TS-32-P1: Registry Completeness

**Property:** Property 1 from design.md
**Validates:** 32-REQ-1.1, 32-REQ-1.3
**Type:** property
**Description:** Oracle registry entry always has required fields.

**For any:** N/A (deterministic — single registry lookup).
**Invariant:** The oracle entry has `injection="auto_pre"`,
`task_assignable=True`, and a non-empty `default_allowlist`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["oracle"]
ASSERT entry.injection == "auto_pre"
ASSERT entry.task_assignable == True
ASSERT len(entry.default_allowlist) > 0
```

### TS-32-P2: Multi-auto_pre Distinctness

**Property:** Property 2 from design.md
**Validates:** 32-REQ-2.2, 32-REQ-3.1, 32-REQ-3.3
**Type:** property
**Description:** With both oracle and skeptic enabled, auto_pre nodes are
distinct and both connect to the first coder group.

**For any:** spec with 1-10 task groups.
**Invariant:** Two distinct auto_pre nodes exist, both with edges to the first
coder group, and no edge between them.

**Assertion pseudocode:**
```
FOR ANY num_groups IN integers(1, 10):
    graph = build_graph_with_groups(num_groups, oracle=True, skeptic=True)
    auto_pre_nodes = [n for n in graph.nodes if n.group_number == 0]
    ASSERT len(auto_pre_nodes) == 2
    ASSERT auto_pre_nodes[0].id != auto_pre_nodes[1].id
    first_coder = f"{spec}:1"
    ASSERT all(Edge(n.id, first_coder, "intra_spec") in graph.edges for n in auto_pre_nodes)
    ASSERT not any(is_edge_between(auto_pre_nodes[0], auto_pre_nodes[1], graph.edges))
```

### TS-32-P3: Backward-compatible Node IDs

**Property:** Property 3 from design.md
**Validates:** 32-REQ-3.2
**Type:** property
**Description:** Single auto_pre archetype uses `{spec}:0` format.

**For any:** single auto_pre archetype (oracle only or skeptic only).
**Invariant:** The auto_pre node ID is `{spec}:0` without archetype suffix.

**Assertion pseudocode:**
```
FOR ANY archetype IN ["oracle", "skeptic"]:
    config = make_config_with_only(archetype)
    graph = build_graph(spec, groups, [], config)
    ASSERT f"{spec}:0" in graph.nodes
    ASSERT not any(":0:" in nid for nid in graph.nodes)
```

### TS-32-P4: Drift Finding Roundtrip

**Property:** Property 4 from design.md
**Validates:** 32-REQ-6.1, 32-REQ-6.2, 32-REQ-6.3
**Type:** property
**Description:** Valid JSON roundtrips through parse_oracle_output.

**For any:** list of 1-20 drift findings with valid severities and non-empty
descriptions.
**Invariant:** parse_oracle_output returns exactly N findings with matching
severity and description fields.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(drift_finding_strategy, min_size=1, max_size=20):
    json_text = format_oracle_json(findings)
    parsed = parse_oracle_output(json_text, "spec", "0", "sess")
    ASSERT len(parsed) == len(findings)
    FOR i IN range(len(findings)):
        ASSERT parsed[i].severity == findings[i]["severity"]
        ASSERT parsed[i].description == findings[i]["description"]
```

### TS-32-P5: Supersession Integrity

**Property:** Property 5 from design.md
**Validates:** 32-REQ-7.1, 32-REQ-7.3, 32-REQ-7.4
**Type:** property
**Description:** Only the most recent insertion is returned by active query.

**For any:** sequence of 2-5 batches of 1-10 drift findings for the same
(spec_name, task_group).
**Invariant:** query_active_drift_findings returns only findings from the last
batch.

**Assertion pseudocode:**
```
FOR ANY batches IN lists(batch_strategy, min_size=2, max_size=5):
    conn = create_test_db()
    for batch in batches:
        insert_drift_findings(conn, batch)
    result = query_active_drift_findings(conn, spec_name, task_group)
    last_batch = batches[-1]
    ASSERT len(result) == len(last_batch)
    ASSERT all(r.session_id == last_batch[0].session_id for r in result)
```

### TS-32-P6: Block Threshold Monotonicity

**Property:** Property 6 from design.md
**Validates:** 32-REQ-9.1, 32-REQ-9.2, 32-REQ-9.E1
**Type:** property
**Description:** Blocking occurs iff critical count > threshold.

**For any:** threshold T in [1, 10], critical count C in [0, 15].
**Invariant:** should_block(C, T) == (C > T).

**Assertion pseudocode:**
```
FOR ANY (threshold, critical_count) IN (integers(1, 10), integers(0, 15)):
    findings = make_findings(critical_count)
    ASSERT should_block(findings, threshold) == (critical_count > threshold)
```

### TS-32-P7: Context Rendering Completeness

**Property:** Property 7 from design.md
**Validates:** 32-REQ-8.1, 32-REQ-8.2, 32-REQ-8.E1
**Type:** property
**Description:** All finding descriptions appear in rendered context.

**For any:** 1-10 drift findings with distinct descriptions.
**Invariant:** Each description appears in the rendered markdown. Empty list
returns None.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(drift_finding_strategy, min_size=0, max_size=10):
    conn = create_test_db()
    insert_drift_findings(conn, findings)
    result = render_drift_context(conn, spec_name)
    IF len(findings) == 0:
        ASSERT result is None
    ELSE:
        ASSERT result is not None
        FOR f IN findings:
            ASSERT f.description in result
```

### TS-32-P8: Hot-load Injection

**Property:** Property 8 from design.md
**Validates:** 32-REQ-4.1, 32-REQ-4.2
**Type:** property
**Description:** Hot-loaded specs get oracle nodes in pending state.

**For any:** 1-5 newly discovered specs with valid tasks.md.
**Invariant:** Each new spec has an oracle node in "pending" state.

**Assertion pseudocode:**
```
FOR ANY new_specs IN lists(spec_strategy, min_size=1, max_size=5):
    graph, state = simulate_hot_load(existing_graph, new_specs, oracle=True)
    FOR spec IN new_specs:
        oracle_node = find_oracle_node(graph, spec.name)
        ASSERT oracle_node is not None
        ASSERT state.node_states[oracle_node.id] == "pending"
```

## Edge Case Tests

### TS-32-E1: Oracle Disabled

**Requirement:** 32-REQ-1.E1
**Type:** unit
**Description:** No oracle nodes when oracle is disabled.

**Preconditions:**
- ArchetypesConfig with `oracle=False`.

**Input:**
- `build_graph(specs, task_groups, cross_deps, config)`.

**Expected:**
- No nodes with `archetype="oracle"` in the graph.

**Assertion pseudocode:**
```
config = ArchetypesConfig(oracle=False)
graph = build_graph(specs, groups, [], config)
oracle_nodes = [n for n in graph.nodes.values() if n.archetype == "oracle"]
ASSERT len(oracle_nodes) == 0
```

### TS-32-E2: Empty Spec (No Coder Groups)

**Requirement:** 32-REQ-2.E1
**Type:** unit
**Description:** No oracle injection for spec with no coder groups.

**Preconditions:**
- Spec with empty task_groups list. Oracle enabled.

**Input:**
- `build_graph([spec_with_no_groups], {}, [], config)`.

**Expected:**
- No oracle node for that spec.

**Assertion pseudocode:**
```
graph = build_graph([empty_spec], {"empty_spec": []}, [], ArchetypesConfig(oracle=True))
ASSERT "empty_spec:0" not in graph.nodes
```

### TS-32-E3: Legacy Plan Compatibility

**Requirement:** 32-REQ-3.E1
**Type:** unit
**Description:** Runtime injection adds oracle node when plan has existing
skeptic :0 node.

**Preconditions:**
- Plan.json with `{spec}:0` node (archetype=skeptic).
- Oracle enabled in config.

**Input:**
- `_ensure_archetype_nodes(plan_data, config)`.

**Expected:**
- Oracle node added with a distinct ID (not overwriting skeptic).
- Both nodes have edges to the first coder group.

**Assertion pseudocode:**
```
plan_data = {"nodes": {"{spec}:0": {"archetype": "skeptic", ...}}}
config = ArchetypesConfig(oracle=True, skeptic=True)
_ensure_archetype_nodes(plan_data, config)
ASSERT "{spec}:0" in plan_data["nodes"]  # skeptic preserved
oracle_nodes = [n for n in plan_data["nodes"] if "oracle" in plan_data["nodes"][n].get("archetype", "")]
ASSERT len(oracle_nodes) == 1
```

### TS-32-E4: No Valid JSON in Oracle Output

**Requirement:** 32-REQ-6.E1
**Type:** unit
**Description:** Parser returns empty list for non-JSON output.

**Preconditions:**
- None.

**Input:**
- `parse_oracle_output("No drift found, everything looks good.", ...)`.

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
result = parse_oracle_output("No drift found.", "spec", "0", "sess")
ASSERT result == []
```

### TS-32-E5: Finding Missing Required Fields

**Requirement:** 32-REQ-6.E2
**Type:** unit
**Description:** Entries without severity or description are skipped.

**Preconditions:**
- None.

**Input:**
- JSON with one valid entry and one entry missing "description".

**Expected:**
- Returns list with only the valid entry.

**Assertion pseudocode:**
```
json_text = '{"drift_findings": [{"severity": "major", "description": "ok"}, {"severity": "minor"}]}'
result = parse_oracle_output(json_text, "spec", "0", "sess")
ASSERT len(result) == 1
ASSERT result[0].description == "ok"
```

### TS-32-E6: No Drift Findings - Context Omitted

**Requirement:** 32-REQ-8.E1
**Type:** unit
**Description:** render_drift_context returns None when no findings exist.

**Preconditions:**
- DuckDB with empty drift_findings table.

**Input:**
- `render_drift_context(conn, "spec_with_no_findings")`.

**Expected:**
- Returns `None`.

**Assertion pseudocode:**
```
result = render_drift_context(conn, "spec_with_no_findings")
ASSERT result is None
```

### TS-32-E7: Advisory Mode (No block_threshold)

**Requirement:** 32-REQ-9.E1
**Type:** unit
**Description:** Without block_threshold, oracle always completes.

**Preconditions:**
- Oracle settings with `block_threshold=None`.
- Oracle output with 10 critical findings.

**Input:**
- Check blocking logic.

**Expected:**
- Oracle node marked as completed (not failed).

**Assertion pseudocode:**
```
should_block = check_oracle_block(findings=10_critical, threshold=None)
ASSERT should_block == False
```

### TS-32-E8: Block Threshold Clamped

**Requirement:** 32-REQ-10.E1
**Type:** unit
**Description:** Non-positive block_threshold is clamped to 1.

**Preconditions:**
- None.

**Input:**
- `OracleSettings(block_threshold=0)`.

**Expected:**
- `block_threshold` clamped to 1.

**Assertion pseudocode:**
```
settings = OracleSettings(block_threshold=0)
ASSERT settings.block_threshold == 1
```

### TS-32-E9: Hot-load Failure Skips Oracle

**Requirement:** 32-REQ-4.E1
**Type:** unit
**Description:** When hot-loading fails for a spec, oracle injection is skipped.

**Preconditions:**
- A spec without tasks.md discovered at sync barrier.

**Input:**
- hot_load_specs with invalid spec.

**Expected:**
- No oracle node for the invalid spec. Other specs unaffected.

**Assertion pseudocode:**
```
graph, new_specs = hot_load_specs(graph, specs_dir_with_invalid)
ASSERT "invalid_spec" not in new_specs
# Oracle injection only runs for valid new specs
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 32-REQ-1.1 | TS-32-1 | unit |
| 32-REQ-1.2 | TS-32-2 | unit |
| 32-REQ-1.3 | TS-32-1 | unit |
| 32-REQ-1.E1 | TS-32-E1 | unit |
| 32-REQ-2.1 | TS-32-3 | unit |
| 32-REQ-2.2 | TS-32-4 | unit |
| 32-REQ-2.3 | TS-32-3 | unit |
| 32-REQ-2.E1 | TS-32-E2 | unit |
| 32-REQ-3.1 | TS-32-4 | unit |
| 32-REQ-3.2 | TS-32-5 | unit |
| 32-REQ-3.3 | TS-32-4 | unit |
| 32-REQ-3.E1 | TS-32-E3 | unit |
| 32-REQ-4.1 | TS-32-13 | integration |
| 32-REQ-4.2 | TS-32-13 | integration |
| 32-REQ-4.E1 | TS-32-E9 | unit |
| 32-REQ-5.1 | TS-32-6 | unit |
| 32-REQ-5.2 | TS-32-6 | unit |
| 32-REQ-5.3 | TS-32-6 | unit |
| 32-REQ-5.4 | TS-32-6 | unit |
| 32-REQ-5.E1 | TS-32-E4 | unit |
| 32-REQ-5.E2 | TS-32-E5 | unit |
| 32-REQ-6.1 | TS-32-6 | unit |
| 32-REQ-6.2 | TS-32-6 | unit |
| 32-REQ-6.3 | TS-32-7 | unit |
| 32-REQ-6.E1 | TS-32-E4 | unit |
| 32-REQ-6.E2 | TS-32-E5 | unit |
| 32-REQ-7.1 | TS-32-8 | integration |
| 32-REQ-7.2 | TS-32-8 | integration |
| 32-REQ-7.3 | TS-32-9 | integration |
| 32-REQ-7.4 | TS-32-8 | integration |
| 32-REQ-7.E1 | TS-32-E9 | unit |
| 32-REQ-8.1 | TS-32-10 | unit |
| 32-REQ-8.2 | TS-32-10 | unit |
| 32-REQ-8.E1 | TS-32-E6 | unit |
| 32-REQ-9.1 | TS-32-11 | unit |
| 32-REQ-9.2 | TS-32-11 | unit |
| 32-REQ-9.3 | TS-32-11 | unit |
| 32-REQ-9.E1 | TS-32-E7 | unit |
| 32-REQ-10.1 | TS-32-12 | unit |
| 32-REQ-10.2 | TS-32-12 | unit |
| 32-REQ-10.3 | TS-32-12 | unit |
| 32-REQ-10.4 | TS-32-12 | unit |
| 32-REQ-10.E1 | TS-32-E8 | unit |
| Property 1 | TS-32-P1 | property |
| Property 2 | TS-32-P2 | property |
| Property 3 | TS-32-P3 | property |
| Property 4 | TS-32-P4 | property |
| Property 5 | TS-32-P5 | property |
| Property 6 | TS-32-P6 | property |
| Property 7 | TS-32-P7 | property |
| Property 8 | TS-32-P8 | property |
