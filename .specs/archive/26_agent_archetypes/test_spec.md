# Test Specification: Agent Archetypes

## Overview

Tests are organized into three categories mapped to the requirements and
design documents:

1. **Acceptance criterion tests** (`TS-26-N`) — one per `26-REQ-X.Y` entry.
2. **Property tests** (`TS-26-PN`) — one per correctness property from
   design.md.
3. **Edge case tests** (`TS-26-EN`) — one per `26-REQ-X.EY` entry.

All tests use `pytest` and `pytest-asyncio`. Property tests use `hypothesis`.
Integration tests that invoke `gh` CLI use mocked subprocess calls.

Test file layout:

```
tests/unit/session/backends/test_protocol.py    — TS-26-1 through TS-26-4
tests/unit/session/backends/test_claude.py      — TS-26-5 through TS-26-8
tests/unit/session/test_archetypes.py           — TS-26-9 through TS-26-13
tests/unit/graph/test_builder_archetypes.py     — TS-26-14 through TS-26-18
tests/unit/core/test_config_archetypes.py       — TS-26-19 through TS-26-23
tests/unit/session/test_convergence.py          — TS-26-24 through TS-26-28
tests/unit/session/test_skeptic.py              — TS-26-29 through TS-26-33
tests/unit/session/test_verifier.py             — TS-26-34 through TS-26-37
tests/unit/session/test_github_issues.py        — TS-26-38 through TS-26-40
tests/unit/engine/test_retry_predecessor.py     — TS-26-41, TS-26-42
tests/unit/session/test_prompt_archetype.py     — TS-26-43
```

## Test Cases

### TS-26-1: AgentBackend is runtime-checkable Protocol

**Requirement:** 26-REQ-1.1
**Type:** unit
**Description:** Verify `AgentBackend` is a runtime-checkable `Protocol` with
the required members.

**Preconditions:**
- `AgentBackend` imported from `agent_fox.session.backends.protocol`.

**Input:**
- A class with `name` property, async `execute()`, and async `close()`.

**Expected:**
- `isinstance(instance, AgentBackend)` returns `True`.
- A class missing any member fails the `isinstance` check.

**Assertion pseudocode:**
```
valid = ConformingClass()
ASSERT isinstance(valid, AgentBackend) == True

invalid = ClassMissingExecute()
ASSERT isinstance(invalid, AgentBackend) == False
```

---

### TS-26-2: execute() accepts required parameters

**Requirement:** 26-REQ-1.2
**Type:** unit
**Description:** Verify `execute()` method signature accepts prompt,
system_prompt, model, cwd, and optional permission_callback.

**Preconditions:**
- A mock `AgentBackend` implementation.

**Input:**
- `execute("task", system_prompt="sp", model="m", cwd="/tmp")`
- `execute("task", system_prompt="sp", model="m", cwd="/tmp", permission_callback=cb)`

**Expected:**
- Both calls succeed without `TypeError`.

**Assertion pseudocode:**
```
backend = MockBackend()
result1 = await backend.execute("task", system_prompt="sp", model="m", cwd="/tmp")
ASSERT result1 is not None

result2 = await backend.execute("task", system_prompt="sp", model="m", cwd="/tmp", permission_callback=mock_cb)
ASSERT result2 is not None
```

---

### TS-26-3: Canonical message types are frozen dataclasses

**Requirement:** 26-REQ-1.3
**Type:** unit
**Description:** Verify `ToolUseMessage`, `AssistantMessage`, and
`ResultMessage` are frozen dataclasses with correct fields.

**Preconditions:**
- Message classes imported from `agent_fox.session.backends.protocol`.

**Input:**
- Construct each message type with valid arguments.

**Expected:**
- All three types are instantiable.
- Attempting to set an attribute raises `FrozenInstanceError`.

**Assertion pseudocode:**
```
tm = ToolUseMessage(tool_name="Bash", tool_input={"command": "ls"})
ASSERT tm.tool_name == "Bash"
ASSERT_RAISES FrozenInstanceError: tm.tool_name = "other"

am = AssistantMessage(content="thinking")
ASSERT am.content == "thinking"

rm = ResultMessage(status="completed", input_tokens=100, output_tokens=200,
                   duration_ms=5000, error_message=None, is_error=False)
ASSERT rm.input_tokens == 100
```

---

### TS-26-4: ResultMessage carries required fields

**Requirement:** 26-REQ-1.4
**Type:** unit
**Description:** Verify `ResultMessage` has all specified fields with correct
types.

**Preconditions:**
- `ResultMessage` imported.

**Input:**
- `ResultMessage(status="failed", input_tokens=0, output_tokens=0,
  duration_ms=0, error_message="timeout", is_error=True)`

**Expected:**
- All fields accessible and correctly typed.

**Assertion pseudocode:**
```
rm = ResultMessage(status="failed", input_tokens=0, output_tokens=0,
                   duration_ms=0, error_message="timeout", is_error=True)
ASSERT rm.status == "failed"
ASSERT rm.is_error == True
ASSERT rm.error_message == "timeout"
ASSERT isinstance(rm.input_tokens, int)
```

---

### TS-26-5: ClaudeBackend is in backends/claude.py

**Requirement:** 26-REQ-2.1
**Type:** unit
**Description:** Verify `ClaudeBackend` can be imported from the expected
module and satisfies the `AgentBackend` protocol.

**Preconditions:**
- `ClaudeBackend` importable from `agent_fox.session.backends.claude`.

**Input:**
- Instantiate `ClaudeBackend`.

**Expected:**
- `isinstance(ClaudeBackend(), AgentBackend)` is `True`.
- `ClaudeBackend().name` returns `"claude"`.

**Assertion pseudocode:**
```
backend = ClaudeBackend()
ASSERT isinstance(backend, AgentBackend)
ASSERT backend.name == "claude"
```

---

### TS-26-6: ClaudeBackend maps SDK types to canonical messages

**Requirement:** 26-REQ-2.2
**Type:** integration
**Description:** Verify the adapter maps SDK message types to canonical
types correctly.

**Preconditions:**
- Mock `ClaudeSDKClient` that yields known SDK message objects.

**Input:**
- A tool-use SDK message, a text SDK message, and a ResultMessage SDK message.

**Expected:**
- Stream yields `ToolUseMessage`, `AssistantMessage`, `ResultMessage` in order.

**Assertion pseudocode:**
```
backend = ClaudeBackend()
messages = collect(backend.execute(...))  # with mocked SDK client
ASSERT isinstance(messages[0], ToolUseMessage)
ASSERT isinstance(messages[1], AssistantMessage)
ASSERT isinstance(messages[-1], ResultMessage)
```

---

### TS-26-7: ClaudeBackend constructs options and streams

**Requirement:** 26-REQ-2.3
**Type:** integration
**Description:** Verify `execute()` constructs `ClaudeCodeOptions` with
correct parameters and yields messages from the response stream.

**Preconditions:**
- Mock `ClaudeSDKClient`.

**Input:**
- `execute("prompt", system_prompt="sp", model="claude-sonnet-4-6", cwd="/tmp")`

**Expected:**
- `ClaudeCodeOptions` constructed with matching `cwd`, `model`, `system_prompt`.
- At least one message yielded.

**Assertion pseudocode:**
```
backend = ClaudeBackend()
messages = collect(backend.execute("prompt", system_prompt="sp",
                                    model="claude-sonnet-4-6", cwd="/tmp"))
ASSERT len(messages) >= 1
ASSERT captured_options.model == "claude-sonnet-4-6"
ASSERT captured_options.cwd == "/tmp"
```

---

### TS-26-8: session.py has no claude_code_sdk imports

**Requirement:** 26-REQ-2.4
**Type:** unit
**Description:** Verify `session.py` does not import from `claude_code_sdk`.

**Preconditions:**
- `agent_fox/session/session.py` readable.

**Input:**
- Read the file content.

**Expected:**
- No line contains `from claude_code_sdk` or `import claude_code_sdk`.

**Assertion pseudocode:**
```
content = read_file("agent_fox/session/session.py")
ASSERT "claude_code_sdk" not in content
```

---

### TS-26-9: Registry contains all roster archetypes

**Requirement:** 26-REQ-3.1, 26-REQ-3.2
**Type:** unit
**Description:** Verify the archetype registry contains entries for coder,
skeptic, verifier, librarian, cartographer, and coordinator with valid fields.

**Preconditions:**
- `ARCHETYPE_REGISTRY` imported from `agent_fox.session.archetypes`.

**Input:**
- Query registry for each expected name.

**Expected:**
- All six names present. Each has non-empty `templates`, valid
  `default_model_tier`, and correct `task_assignable` flag.

**Assertion pseudocode:**
```
FOR name IN ["coder", "skeptic", "verifier", "librarian", "cartographer", "coordinator"]:
    entry = ARCHETYPE_REGISTRY[name]
    ASSERT entry.name == name
    ASSERT len(entry.templates) >= 1
    ASSERT entry.default_model_tier IN ["SIMPLE", "STANDARD", "ADVANCED"]
```

---

### TS-26-10: Coordinator is not task-assignable

**Requirement:** 26-REQ-3.3
**Type:** unit
**Description:** Verify the coordinator archetype has `task_assignable=False`
and that assigning it to a node falls back to coder.

**Preconditions:**
- Registry loaded.

**Input:**
- `get_archetype("coordinator")` then check `task_assignable`.

**Expected:**
- `task_assignable` is `False`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["coordinator"]
ASSERT entry.task_assignable == False
```

---

### TS-26-11: Per-archetype allowlist override

**Requirement:** 26-REQ-3.4
**Type:** unit
**Description:** Verify an archetype's allowlist override is used instead of
the global allowlist when configured.

**Preconditions:**
- Config with `archetypes.allowlists.skeptic = ["ls", "cat", "git"]`.

**Input:**
- Resolve allowlist for the "skeptic" archetype.

**Expected:**
- Effective allowlist is `{"ls", "cat", "git"}`, not the global default.

**Assertion pseudocode:**
```
config = make_config(archetypes_allowlists={"skeptic": ["ls", "cat", "git"]})
allowlist = resolve_allowlist("skeptic", config)
ASSERT allowlist == frozenset(["ls", "cat", "git"])
```

---

### TS-26-12: build_system_prompt uses registry

**Requirement:** 26-REQ-3.5
**Type:** unit
**Description:** Verify `build_system_prompt()` resolves templates from the
archetype registry instead of the hardcoded `_ROLE_TEMPLATES`.

**Preconditions:**
- Template files for "coder" archetype exist on disk.

**Input:**
- `build_system_prompt(context="ctx", task_group=1, spec_name="test_spec", archetype="coder")`

**Expected:**
- Output contains content from `coding.md` and `git-flow.md` templates.
- No reference to the old `_ROLE_TEMPLATES` dict in the module.

**Assertion pseudocode:**
```
result = build_system_prompt(context="ctx", task_group=1,
                              spec_name="test_spec", archetype="coder")
ASSERT "coding" content present in result
ASSERT "git-flow" content present in result

source = read_file("agent_fox/session/prompt.py")
ASSERT "_ROLE_TEMPLATES" not in source
```

---

### TS-26-13: Node dataclass has archetype and instances

**Requirement:** 26-REQ-4.1
**Type:** unit
**Description:** Verify the `Node` dataclass includes `archetype` and
`instances` fields with correct defaults.

**Preconditions:**
- `Node` imported from `agent_fox.graph.types`.

**Input:**
- `Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)`

**Expected:**
- `archetype` defaults to `"coder"`.
- `instances` defaults to `1`.

**Assertion pseudocode:**
```
node = Node(id="s:1", spec_name="s", group_number=1, title="t", optional=False)
ASSERT node.archetype == "coder"
ASSERT node.instances == 1
```

---

### TS-26-14: Plan serialization includes archetype fields

**Requirement:** 26-REQ-4.2
**Type:** unit
**Description:** Verify plan.json serialization includes `archetype` and
`instances` in node data.

**Preconditions:**
- A `TaskGraph` with nodes that have non-default archetype values.

**Input:**
- Serialize graph with a node having `archetype="skeptic"`, `instances=3`.

**Expected:**
- Serialized JSON contains `"archetype": "skeptic"` and `"instances": 3`.

**Assertion pseudocode:**
```
node = Node(id="s:0", ..., archetype="skeptic", instances=3)
graph = TaskGraph(nodes={"s:0": node}, edges=[], order=[])
save_plan(graph, plan_path)
data = json.loads(plan_path.read_text())
ASSERT data["nodes"]["s:0"]["archetype"] == "skeptic"
ASSERT data["nodes"]["s:0"]["instances"] == 3
```

---

### TS-26-15: Legacy plan.json defaults

**Requirement:** 26-REQ-4.3
**Type:** unit
**Description:** Verify loading a plan.json without archetype/instances fields
defaults to coder/1.

**Preconditions:**
- A plan.json file with nodes lacking `archetype` and `instances` keys.

**Input:**
- Load the plan via `load_plan()`.

**Expected:**
- All nodes have `archetype="coder"` and `instances=1`.

**Assertion pseudocode:**
```
plan_path.write_text(json.dumps({"nodes": {"s:1": {
    "id": "s:1", "spec_name": "s", "group_number": 1,
    "title": "t", "optional": false, "status": "pending"
}}, "edges": [], "order": []}))
graph = load_plan(plan_path)
ASSERT graph.nodes["s:1"].archetype == "coder"
ASSERT graph.nodes["s:1"].instances == 1
```

---

### TS-26-16: NodeSessionRunner uses archetype metadata

**Requirement:** 26-REQ-4.4
**Type:** integration
**Description:** Verify `NodeSessionRunner` reads the archetype from node
metadata and resolves the correct prompt templates and model tier.

**Preconditions:**
- Mock `run_session()`. Registry contains "librarian" archetype.

**Input:**
- Create `NodeSessionRunner` with `archetype="librarian"`.
- Call `execute()`.

**Expected:**
- `build_system_prompt()` called with `archetype="librarian"`.
- Model resolved from librarian's default tier (STANDARD).

**Assertion pseudocode:**
```
runner = NodeSessionRunner("spec:3", config, archetype="librarian")
record = await runner.execute("spec:3", attempt=1)
ASSERT captured_build_args.archetype == "librarian"
ASSERT captured_model_tier == "STANDARD"
```

---

### TS-26-17: tasks.md archetype tag extraction

**Requirement:** 26-REQ-5.1
**Type:** unit
**Description:** Verify `parse_tasks()` extracts `[archetype: X]` tags from
task group title lines.

**Preconditions:**
- A tasks.md file with `- [ ] 3. Update docs [archetype: cartographer]`.

**Input:**
- Parse the file via `parse_tasks()`.

**Expected:**
- Group 3 has `archetype="cartographer"`.
- The tag is stripped from the `title` field.

**Assertion pseudocode:**
```
tasks_md = "- [ ] 3. Update docs [archetype: cartographer]\n  - [ ] 3.1 sub\n"
write_file(path, tasks_md)
groups = parse_tasks(path)
ASSERT groups[0].archetype == "cartographer"
ASSERT "[archetype:" not in groups[0].title
ASSERT "Update docs" in groups[0].title
```

---

### TS-26-18: Three-layer assignment priority

**Requirement:** 26-REQ-5.2
**Type:** unit
**Description:** Verify the graph builder applies assignment layers in
correct priority order.

**Preconditions:**
- A spec with tasks.md tag `[archetype: librarian]` on group 3.
- Coordinator override setting group 3 to `cartographer`.
- Graph builder default would be `coder`.

**Input:**
- Build graph with all three layers providing values for the same node.

**Expected:**
- Node's archetype is `"librarian"` (tasks.md wins).

**Assertion pseudocode:**
```
task_groups = {"spec": [TaskGroupDef(number=3, ..., archetype="librarian")]}
coordinator_overrides = [Override(node="spec:3", archetype="cartographer")]
graph = build_graph(specs, task_groups, [], config, coordinator_overrides)
ASSERT graph.nodes["spec:3"].archetype == "librarian"
```

---

### TS-26-19: Skeptic auto-injection at group 0

**Requirement:** 26-REQ-5.3
**Type:** unit
**Description:** Verify the graph builder inserts a group-0 Skeptic node
when Skeptic is enabled.

**Preconditions:**
- Config with `archetypes.skeptic = true`.
- A spec with groups 1, 2, 3.

**Input:**
- Build graph.

**Expected:**
- Node `"spec:0"` exists with `archetype="skeptic"`.
- Edge from `"spec:0"` to `"spec:1"` exists.

**Assertion pseudocode:**
```
config = make_config(archetypes={"skeptic": True})
graph = build_graph(specs, task_groups, [], config)
ASSERT "spec:0" in graph.nodes
ASSERT graph.nodes["spec:0"].archetype == "skeptic"
ASSERT Edge(source="spec:0", target="spec:1", kind="intra_spec") in graph.edges
```

---

### TS-26-20: Auto-post injection as siblings

**Requirement:** 26-REQ-5.4
**Type:** unit
**Description:** Verify auto_post archetypes are injected as independent
siblings after the last Coder group.

**Preconditions:**
- Config with `archetypes.verifier = true`. Spec has groups 1-4.

**Input:**
- Build graph.

**Expected:**
- Verifier node exists after group 4.
- Verifier depends on group 4 (edge exists).
- No edges between sibling auto_post nodes.

**Assertion pseudocode:**
```
config = make_config(archetypes={"verifier": True})
graph = build_graph(specs, task_groups, [], config)
verifier_node = [n for n in graph.nodes.values() if n.archetype == "verifier"][0]
ASSERT any(e.source == "spec:4" and e.target == verifier_node.id for e in graph.edges)
```

---

### TS-26-21: Archetype assignment logged at INFO

**Requirement:** 26-REQ-5.5
**Type:** unit
**Description:** Verify archetype assignments are logged at INFO level.

**Preconditions:**
- Logger captured via `caplog`.

**Input:**
- Build graph with Skeptic enabled.

**Expected:**
- Log contains archetype assignment for each node at INFO level.

**Assertion pseudocode:**
```
with caplog at INFO:
    graph = build_graph(specs, task_groups, [], config)
ASSERT any("archetype" in record.message and "skeptic" in record.message
           for record in caplog.records)
```

---

### TS-26-22: ArchetypesConfig has enable/disable toggles

**Requirement:** 26-REQ-6.1
**Type:** unit
**Description:** Verify the `ArchetypesConfig` model has boolean toggles for
each roster archetype.

**Preconditions:**
- `ArchetypesConfig` importable from config module.

**Input:**
- Construct with `skeptic=True, verifier=False`.

**Expected:**
- Fields accessible and correctly typed.

**Assertion pseudocode:**
```
cfg = ArchetypesConfig(skeptic=True, verifier=False)
ASSERT cfg.skeptic == True
ASSERT cfg.verifier == False
ASSERT cfg.coder == True  # always
ASSERT cfg.librarian == False  # default
```

---

### TS-26-23: Instance count configuration

**Requirement:** 26-REQ-6.2
**Type:** unit
**Description:** Verify `archetypes.instances` sub-section sets per-archetype
instance counts.

**Preconditions:**
- Config TOML with `[archetypes.instances]` section.

**Input:**
- `skeptic = 3, verifier = 2`

**Expected:**
- `config.archetypes.instances.skeptic == 3`
- `config.archetypes.instances.verifier == 2`

**Assertion pseudocode:**
```
config = load_config_from_toml("[archetypes.instances]\nskeptic = 3\nverifier = 2")
ASSERT config.archetypes.instances.skeptic == 3
ASSERT config.archetypes.instances.verifier == 2
```

---

### TS-26-24: Model tier override per archetype

**Requirement:** 26-REQ-6.3
**Type:** unit
**Description:** Verify per-archetype model tier overrides in config.

**Preconditions:**
- Config with `archetypes.models.skeptic = "SIMPLE"`.

**Input:**
- Resolve model for "skeptic" archetype.

**Expected:**
- Model tier is "SIMPLE", not the registry default "STANDARD".

**Assertion pseudocode:**
```
config = make_config(archetypes_models={"skeptic": "SIMPLE"})
tier = resolve_archetype_model("skeptic", config)
ASSERT tier == "SIMPLE"
```

---

### TS-26-25: Allowlist override per archetype

**Requirement:** 26-REQ-6.4
**Type:** unit
**Description:** Verify per-archetype allowlist overrides in config.

**Preconditions:**
- Config with `archetypes.allowlists.skeptic = ["ls", "cat"]`.

**Input:**
- Resolve allowlist for "skeptic".

**Expected:**
- Allowlist is `["ls", "cat"]`, not global default.

**Assertion pseudocode:**
```
config = make_config(archetypes_allowlists={"skeptic": ["ls", "cat"]})
allowlist = resolve_archetype_allowlist("skeptic", config)
ASSERT allowlist == frozenset(["ls", "cat"])
```

---

### TS-26-26: Coder always enabled

**Requirement:** 26-REQ-6.5
**Type:** unit
**Description:** Verify setting `coder = false` is ignored with a warning.

**Preconditions:**
- Logger captured.

**Input:**
- `ArchetypesConfig(coder=False)`

**Expected:**
- `cfg.coder` is `True` regardless.
- Warning logged.

**Assertion pseudocode:**
```
with caplog at WARNING:
    cfg = ArchetypesConfig(coder=False)
ASSERT cfg.coder == True
ASSERT any("cannot be disabled" in r.message for r in caplog.records)
```

---

### TS-26-27: Multi-instance parallel dispatch

**Requirement:** 26-REQ-7.1
**Type:** integration
**Description:** Verify N independent sessions are dispatched in parallel
for a node with `instances > 1`.

**Preconditions:**
- Mock session runner that records call timestamps.

**Input:**
- Node with `instances=3`.

**Expected:**
- 3 sessions dispatched. All start within a small time window (parallel).

**Assertion pseudocode:**
```
runner = NodeSessionRunner("spec:0", config, archetype="skeptic", instances=3)
record = await runner.execute("spec:0", attempt=1)
ASSERT mock_session.call_count == 3
ASSERT max(start_times) - min(start_times) < 0.5  # near-simultaneous
```

---

### TS-26-28: Skeptic convergence union and dedup

**Requirement:** 26-REQ-7.2
**Type:** unit
**Description:** Verify Skeptic convergence unions findings across instances
and deduplicates by normalized `(severity, description)`.

**Preconditions:**
- Three instance outputs with overlapping findings.

**Input:**
```
instance_1: [("critical", "Missing edge case"), ("major", "Unclear requirement")]
instance_2: [("critical", "missing edge case"), ("minor", "Typo in doc")]
instance_3: [("critical", "Missing Edge Case"), ("major", "New concern")]
```

**Expected:**
- Merged set has 4 unique findings (after dedup of the critical one).

**Assertion pseudocode:**
```
merged, blocked = converge_skeptic(instances, block_threshold=3)
unique_normalized = {normalize_finding(f) for f in merged}
ASSERT len(unique_normalized) == 4
```

---

### TS-26-29: Skeptic critical majority gating

**Requirement:** 26-REQ-7.3
**Type:** unit
**Description:** Verify a critical finding only counts toward blocking if
it appears in >= ceil(N/2) instances.

**Preconditions:**
- 3 instances. A critical finding appears in only 1 instance.

**Input:**
```
instance_1: [("critical", "Issue A")]
instance_2: []
instance_3: []
```

**Expected:**
- Critical count for blocking purposes is 0 (finding in 1/3 < ceil(3/2)=2).
- Node is not blocked (assuming threshold > 0).

**Assertion pseudocode:**
```
merged, blocked = converge_skeptic(instances, block_threshold=3)
ASSERT blocked == False
```

---

### TS-26-30: Verifier majority vote

**Requirement:** 26-REQ-7.4
**Type:** unit
**Description:** Verify Verifier convergence uses majority vote for verdict.

**Preconditions:**
- 3 instance verdicts.

**Input:**
- Case 1: `["PASS", "PASS", "FAIL"]` → PASS (2/3 >= ceil(3/2)=2)
- Case 2: `["FAIL", "FAIL", "PASS"]` → FAIL (1/3 < 2)
- Case 3: `["PASS"]` → PASS (1/1 >= 1)

**Expected:**
- Verdicts as described.

**Assertion pseudocode:**
```
ASSERT converge_verifier(["PASS", "PASS", "FAIL"]) == "PASS"
ASSERT converge_verifier(["FAIL", "FAIL", "PASS"]) == "FAIL"
ASSERT converge_verifier(["PASS"]) == "PASS"
```

---

### TS-26-31: Convergence makes no LLM calls

**Requirement:** 26-REQ-7.5
**Type:** unit
**Description:** Verify the convergence module contains no imports that could
invoke LLM calls.

**Preconditions:**
- `agent_fox/session/convergence.py` readable.

**Input:**
- Read the module source code.

**Expected:**
- No imports of `claude_code_sdk`, `anthropic`, `openai`, or `langchain`.
- No `async` calls to external APIs.

**Assertion pseudocode:**
```
content = read_file("agent_fox/session/convergence.py")
FOR sdk IN ["claude_code_sdk", "anthropic", "openai", "langchain"]:
    ASSERT sdk not in content
```

---

### TS-26-32: Skeptic produces review.md

**Requirement:** 26-REQ-8.1
**Type:** unit
**Description:** Verify the Skeptic template instructs producing a structured
review file with severity categories.

**Preconditions:**
- Skeptic template file exists.

**Input:**
- Read `skeptic.md` template content.

**Expected:**
- Template references severity categories: critical, major, minor, observation.
- Template references output path `.specs/{spec_name}/review.md`.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/skeptic.md")
ASSERT "critical" in content.lower()
ASSERT "major" in content.lower()
ASSERT "review.md" in content
```

---

### TS-26-33: Skeptic files GitHub issue

**Requirement:** 26-REQ-8.2
**Type:** integration
**Description:** Verify Skeptic post-session logic files a GitHub issue with
structured findings using search-before-create.

**Preconditions:**
- Mock `gh` CLI subprocess. No existing issue.

**Input:**
- Skeptic completes with findings for spec "03_session".

**Expected:**
- `gh issue list --search` called first.
- `gh issue create` called with title `[Skeptic Review] 03_session`.

**Assertion pseudocode:**
```
await post_skeptic_session(spec_name="03_session", findings=sample_findings)
ASSERT "gh issue list" in subprocess_calls[0]
ASSERT "gh issue create" in subprocess_calls[1]
ASSERT "[Skeptic Review] 03_session" in subprocess_calls[1]
```

---

### TS-26-34: Skeptic review passed to Coder as context

**Requirement:** 26-REQ-8.3
**Type:** integration
**Description:** Verify the Skeptic's review.md content is included in the
Coder's system prompt.

**Preconditions:**
- A review.md file exists in the spec directory.
- NodeSessionRunner for the Coder group that succeeds the Skeptic.

**Input:**
- Build prompts for the Coder node.

**Expected:**
- System prompt contains review.md content.

**Assertion pseudocode:**
```
write_file(spec_dir / "review.md", "## Critical\n- Missing edge case")
system_prompt, _ = runner._build_prompts(repo_root, 1, None)
ASSERT "Missing edge case" in system_prompt
```

---

### TS-26-35: Skeptic blocking threshold

**Requirement:** 26-REQ-8.4
**Type:** unit
**Description:** Verify the Skeptic blocks only when critical count exceeds
the configured threshold.

**Preconditions:**
- `block_threshold = 3`.

**Input:**
- Case 1: 3 majority-agreed critical findings → not blocked.
- Case 2: 4 majority-agreed critical findings → blocked.

**Expected:**
- Case 1: `blocked == False`. Case 2: `blocked == True`.

**Assertion pseudocode:**
```
_, blocked1 = converge_skeptic(make_findings(critical_count=3), block_threshold=3)
ASSERT blocked1 == False

_, blocked2 = converge_skeptic(make_findings(critical_count=4), block_threshold=3)
ASSERT blocked2 == True
```

---

### TS-26-36: Skeptic read-only allowlist

**Requirement:** 26-REQ-8.5
**Type:** unit
**Description:** Verify the Skeptic's default allowlist is read-only.

**Preconditions:**
- Registry loaded.

**Input:**
- Get Skeptic's default allowlist.

**Expected:**
- Contains: `ls`, `cat`, `git`, `wc`, `head`, `tail`.
- Does not contain: `rm`, `mv`, `cp`, `mkdir`, `make`, `pytest`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["skeptic"]
allowed = set(entry.default_allowlist)
ASSERT {"ls", "cat", "git", "wc", "head", "tail"}.issubset(allowed)
ASSERT "rm" not in allowed
ASSERT "make" not in allowed
```

---

### TS-26-37: Verifier produces verification.md

**Requirement:** 26-REQ-9.1
**Type:** unit
**Description:** Verify the Verifier template instructs producing a
verification report with per-requirement assessment and verdict.

**Preconditions:**
- Verifier template file exists.

**Input:**
- Read `verifier.md` template content.

**Expected:**
- Template references per-requirement assessment, verdict (PASS/FAIL).
- Template references output path `verification.md`.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/verifier.md")
ASSERT "PASS" in content
ASSERT "FAIL" in content
ASSERT "verification.md" in content
```

---

### TS-26-38: Verifier files GitHub issue on FAIL

**Requirement:** 26-REQ-9.2
**Type:** integration
**Description:** Verify the Verifier files a GitHub issue when verdict is FAIL.

**Preconditions:**
- Mock `gh` CLI subprocess.

**Input:**
- Verifier completes with verdict FAIL for spec "05_memory" group 2.

**Expected:**
- `gh issue create` called with title containing
  `[Verifier] 05_memory group 2: FAIL`.

**Assertion pseudocode:**
```
await post_verifier_session(spec_name="05_memory", group=2, verdict="FAIL", ...)
ASSERT "[Verifier] 05_memory group 2: FAIL" in subprocess_calls[-1]
```

---

### TS-26-39: Retry-predecessor on Verifier failure

**Requirement:** 26-REQ-9.3
**Type:** integration
**Description:** Verify the orchestrator resets the predecessor Coder node
when a Verifier with `retry_predecessor=true` fails.

**Preconditions:**
- Graph: `coder:4 → verifier:5`. Verifier fails.
- Mock session runners.

**Input:**
- Process a failed SessionRecord for the Verifier node.

**Expected:**
- Predecessor `coder:4` reset to `"pending"`.
- Verifier node `verifier:5` reset to `"pending"`.
- Error tracker for `coder:4` contains the Verifier's failure report.

**Assertion pseudocode:**
```
process_session_result(failed_verifier_record)
ASSERT graph_sync.node_states["spec:4"] == "pending"
ASSERT graph_sync.node_states["spec:5"] == "pending"
ASSERT error_tracker["spec:4"] == verifier_failure_message
```

---

### TS-26-40: Retry-predecessor cycle limit

**Requirement:** 26-REQ-9.4
**Type:** integration
**Description:** Verify retry-predecessor does not exceed max_retries.

**Preconditions:**
- `max_retries = 2`. Verifier fails on every attempt.

**Input:**
- Simulate 3 Verifier failures.

**Expected:**
- After attempt 3 (max_retries+1), Verifier is blocked.

**Assertion pseudocode:**
```
FOR attempt IN [1, 2, 3]:
    process_session_result(failed_verifier_record, attempt=attempt)
ASSERT graph_sync.node_states["spec:5"] == "blocked"
```

---

### TS-26-41: GitHub issue search-before-create

**Requirement:** 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3
**Type:** integration
**Description:** Verify `file_or_update_issue()` searches before creating,
updates existing issues, and creates when none found.

**Preconditions:**
- Mock `gh` CLI subprocess.

**Input:**
- Case 1: No existing issue → create.
- Case 2: Existing issue #42 → update body + add comment.

**Expected:**
- Case 1: `gh issue create` called.
- Case 2: `gh issue edit 42` and `gh issue comment 42` called.

**Assertion pseudocode:**
```
# Case 1: no existing
mock_gh_search(returns=[])
url = await file_or_update_issue("[Skeptic Review] spec", "body")
ASSERT "gh issue create" in subprocess_calls[-1]

# Case 2: existing #42
mock_gh_search(returns=[{"number": 42}])
url = await file_or_update_issue("[Skeptic Review] spec", "updated body")
ASSERT "gh issue edit" in subprocess_calls[-1]
```

---

### TS-26-42: build_system_prompt archetype="coder" matches old role="coding"

**Requirement:** 26-REQ-3.5 (via Property 5)
**Type:** unit
**Description:** Verify the refactored prompt builder produces identical
output for the coder archetype as the old role-based builder did for "coding".

**Preconditions:**
- Template files unchanged. Same context/spec_name/task_group inputs.

**Input:**
- `build_system_prompt(context="ctx", task_group=1, spec_name="03_session",
  archetype="coder")`

**Expected:**
- Output identical to pre-refactor
  `build_system_prompt(context="ctx", task_group=1, spec_name="03_session",
  role="coding")`.

**Assertion pseudocode:**
```
new_output = build_system_prompt(context="ctx", task_group=1,
                                  spec_name="03_session", archetype="coder")
old_output = old_build_system_prompt(context="ctx", task_group=1,
                                      spec_name="03_session", role="coding")
ASSERT new_output == old_output
```

## Property Test Cases

### TS-26-P1: Backend Protocol Isolation

**Property:** Property 1 from design.md
**Validates:** 26-REQ-1.1, 26-REQ-2.4
**Type:** property
**Description:** No module outside the claude backend adapter imports from
`claude_code_sdk`.

**For any:** Python file in `agent_fox/` (excluding `session/backends/claude.py`)
**Invariant:** File content does not contain `claude_code_sdk`.

**Assertion pseudocode:**
```
FOR ANY py_file IN glob("agent_fox/**/*.py") - {"session/backends/claude.py"}:
    content = read(py_file)
    ASSERT "claude_code_sdk" not in content
```

---

### TS-26-P2: Message Type Completeness

**Property:** Property 2 from design.md
**Validates:** 26-REQ-1.3, 26-REQ-1.4
**Type:** property
**Description:** Every message from ClaudeBackend is a valid canonical type,
and the stream always ends with exactly one ResultMessage.

**For any:** sequence of mock SDK messages (generated via hypothesis)
**Invariant:** All yielded messages are `AgentMessage` union members. Exactly
one `ResultMessage` appears, and it is the last message.

**Assertion pseudocode:**
```
FOR ANY sdk_messages IN strategy(sdk_message_lists):
    canonical = list(ClaudeBackend._map_messages(sdk_messages))
    FOR msg IN canonical:
        ASSERT isinstance(msg, (ToolUseMessage, AssistantMessage, ResultMessage))
    result_msgs = [m for m in canonical if isinstance(m, ResultMessage)]
    ASSERT len(result_msgs) == 1
    ASSERT canonical[-1] is result_msgs[0]
```

---

### TS-26-P3: Registry Completeness

**Property:** Property 3 from design.md
**Validates:** 26-REQ-3.1, 26-REQ-3.2
**Type:** property
**Description:** All roster archetypes plus coordinator are in the registry
with valid fields.

**For any:** archetype name in `{"coder", "skeptic", "verifier", "librarian",
"cartographer", "coordinator"}`
**Invariant:** Entry exists, has non-empty `templates`, valid
`default_model_tier` in `{"SIMPLE", "STANDARD", "ADVANCED"}`.

**Assertion pseudocode:**
```
FOR ANY name IN ROSTER_PLUS_COORDINATOR:
    entry = ARCHETYPE_REGISTRY[name]
    ASSERT len(entry.templates) >= 1
    ASSERT entry.default_model_tier IN {"SIMPLE", "STANDARD", "ADVANCED"}
```

---

### TS-26-P4: Archetype Fallback

**Property:** Property 4 from design.md
**Validates:** 26-REQ-3.E1, 26-REQ-4.3
**Type:** property
**Description:** Unknown archetype names always fall back to coder.

**For any:** string not in the registry keys (generated via hypothesis text)
**Invariant:** `get_archetype(name)` returns the coder entry, never raises.

**Assertion pseudocode:**
```
FOR ANY name IN text(min_size=1).filter(lambda s: s not in ARCHETYPE_REGISTRY):
    entry = get_archetype(name)
    ASSERT entry.name == "coder"
```

---

### TS-26-P5: Template Resolution Equivalence

**Property:** Property 5 from design.md
**Validates:** 26-REQ-3.5
**Type:** property
**Description:** Coder archetype produces identical prompts to the old
role="coding" path.

**For any:** (context, task_group, spec_name) tuples where context is text,
task_group >= 1, spec_name matches `\d+_\w+`
**Invariant:** `build_system_prompt(archetype="coder")` ==
`old_build_system_prompt(role="coding")` for the same inputs.

**Assertion pseudocode:**
```
FOR ANY (context, task_group, spec_name) IN strategy:
    new = build_system_prompt(context, task_group, spec_name, archetype="coder")
    old = old_build_system_prompt(context, task_group, spec_name, role="coding")
    ASSERT new == old
```

---

### TS-26-P6: Assignment Priority

**Property:** Property 6 from design.md
**Validates:** 26-REQ-5.1, 26-REQ-5.2
**Type:** property
**Description:** The highest-priority layer always wins in archetype assignment.

**For any:** combination of (tag, coordinator_override, graph_default) where
each is either set to a valid archetype or absent
**Invariant:** Final archetype = tag if set, else coordinator if set, else
graph_default.

**Assertion pseudocode:**
```
FOR ANY (tag, coord, default) IN strategy(optional_archetypes x3):
    result = resolve_archetype(tag=tag, coordinator=coord, default=default)
    expected = tag or coord or default or "coder"
    ASSERT result == expected
```

---

### TS-26-P7: Auto-Injection Graph Structure

**Property:** Property 7 from design.md
**Validates:** 26-REQ-5.3, 26-REQ-5.4
**Type:** property
**Description:** Auto-injected nodes have correct edges and no inter-sibling
dependencies.

**For any:** spec with N groups (1..N), Skeptic enabled, Verifier enabled
**Invariant:** Group 0 (skeptic) → Group 1 edge exists. Verifier node
depends on Group N. No edge between sibling auto_post nodes.

**Assertion pseudocode:**
```
FOR ANY n_groups IN integers(min=1, max=10):
    graph = build_graph_with_n_groups(n_groups, skeptic=True, verifier=True)
    ASSERT edge_exists(graph, "spec:0", "spec:1")
    ASSERT graph.nodes["spec:0"].archetype == "skeptic"
    post_nodes = [n for n in graph.nodes.values() if n.archetype in AUTO_POST]
    FOR a, b IN combinations(post_nodes, 2):
        ASSERT NOT edge_exists(graph, a.id, b.id)
        ASSERT NOT edge_exists(graph, b.id, a.id)
```

---

### TS-26-P8: Instance Clamping

**Property:** Property 8 from design.md
**Validates:** 26-REQ-4.E1, 26-REQ-4.E2
**Type:** property
**Description:** Instance counts are clamped to valid ranges.

**For any:** (archetype, instances) where instances is int >= 0
**Invariant:** If archetype="coder", result is 1. If instances > 5, result
is 5. Otherwise result equals instances (or 1 if 0).

**Assertion pseudocode:**
```
FOR ANY (archetype, instances) IN strategy:
    result = clamp_instances(archetype, instances)
    IF archetype == "coder":
        ASSERT result == 1
    ELIF instances > 5:
        ASSERT result == 5
    ELIF instances < 1:
        ASSERT result == 1
    ELSE:
        ASSERT result == instances
```

---

### TS-26-P9: Convergence Determinism

**Property:** Property 9 from design.md
**Validates:** 26-REQ-7.2, 26-REQ-7.4, 26-REQ-7.5
**Type:** property
**Description:** Convergence output is independent of instance ordering.

**For any:** list of N instance outputs, permuted
**Invariant:** `converge_skeptic(permuted)` produces the same merged result
for all permutations.

**Assertion pseudocode:**
```
FOR ANY findings_lists IN strategy(lists_of_findings):
    FOR perm IN permutations(findings_lists):
        merged_a, blocked_a = converge_skeptic(list(perm), threshold=3)
        merged_b, blocked_b = converge_skeptic(findings_lists, threshold=3)
        ASSERT set(normalize(f) for f in merged_a) == set(normalize(f) for f in merged_b)
        ASSERT blocked_a == blocked_b
```

---

### TS-26-P10: Skeptic Blocking Threshold

**Property:** Property 10 from design.md
**Validates:** 26-REQ-7.3, 26-REQ-8.4
**Type:** property
**Description:** Blocking occurs iff majority-agreed criticals exceed threshold.

**For any:** N instances (1-5), list of critical findings per instance,
threshold T
**Invariant:** `blocked == True` iff count of criticals appearing in
>= ceil(N/2) instances > T.

**Assertion pseudocode:**
```
FOR ANY (n_instances, findings_per, threshold) IN strategy:
    _, blocked = converge_skeptic(findings_per, block_threshold=threshold)
    majority_criticals = count_majority_agreed_criticals(findings_per, n_instances)
    ASSERT blocked == (majority_criticals > threshold)
```

---

### TS-26-P11: Verifier Majority Vote

**Property:** Property 11 from design.md
**Validates:** 26-REQ-7.4
**Type:** property
**Description:** Verdict is PASS iff >= ceil(N/2) instances say PASS.

**For any:** list of N verdicts (each "PASS" or "FAIL")
**Invariant:** `converge_verifier(verdicts) == "PASS"` iff
`sum(v == "PASS" for v in verdicts) >= ceil(N/2)`.

**Assertion pseudocode:**
```
FOR ANY verdicts IN lists(sampled_from(["PASS", "FAIL"]), min_size=1, max_size=5):
    result = converge_verifier(verdicts)
    pass_count = sum(1 for v in verdicts if v == "PASS")
    expected = "PASS" if pass_count >= ceil(len(verdicts)/2) else "FAIL"
    ASSERT result == expected
```

---

### TS-26-P12: Retry-Predecessor Correctness

**Property:** Property 12 from design.md
**Validates:** 26-REQ-9.3, 26-REQ-9.4
**Type:** property
**Description:** Retry-predecessor resets the correct predecessor and
respects max_retries.

**For any:** graph with coder→verifier edge, verifier failure, attempt <= max_retries+1
**Invariant:** Predecessor is reset to pending and verifier is reset to pending.
After max_retries+1 failures, verifier is blocked.

**Assertion pseudocode:**
```
FOR ANY (max_retries, n_failures) IN strategy(integers(1,5) x integers(1,10)):
    state = simulate_verifier_failures(n_failures, max_retries)
    IF n_failures <= max_retries + 1:
        ASSERT state["verifier"] IN ("pending", "in_progress")
    ELSE:
        ASSERT state["verifier"] == "blocked"
```

---

### TS-26-P13: GitHub Issue Idempotency

**Property:** Property 13 from design.md
**Validates:** 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3
**Type:** property
**Description:** Repeated calls produce at most one open issue.

**For any:** sequence of N calls (1-5) with the same title prefix
**Invariant:** At most 1 `gh issue create` call. Subsequent calls use
`gh issue edit`.

**Assertion pseudocode:**
```
FOR ANY n_calls IN integers(1, 5):
    mock_gh = MockGH()
    FOR i IN range(n_calls):
        await file_or_update_issue("[Skeptic] spec", f"body {i}")
    ASSERT mock_gh.create_count <= 1
    ASSERT mock_gh.edit_count == max(0, n_calls - 1)
```

---

### TS-26-P14: Backward Compatibility

**Property:** Property 14 from design.md
**Validates:** 26-REQ-4.3, 26-REQ-6.E1
**Type:** property
**Description:** Legacy data without new fields produces correct defaults.

**For any:** plan.json node dict without `archetype` or `instances` keys
**Invariant:** Loaded node has `archetype="coder"` and `instances=1`.

**Assertion pseudocode:**
```
FOR ANY node_data IN strategy(valid_legacy_node_dicts):
    node = _node_from_dict(node_data)
    ASSERT node.archetype == "coder"
    ASSERT node.instances == 1
```

## Edge Case Tests

### TS-26-E1: Backend execute() exception handling

**Requirement:** 26-REQ-1.E1
**Type:** unit
**Description:** Verify a backend exception is caught and returned as a
failed SessionOutcome.

**Preconditions:**
- Mock backend whose `execute()` raises `RuntimeError("SDK crash")`.

**Input:**
- Call `run_session()` with the failing backend.

**Expected:**
- Returns `SessionOutcome` with `status="failed"`,
  `error_message="SDK crash"`.

**Assertion pseudocode:**
```
backend = FailingBackend(error=RuntimeError("SDK crash"))
outcome = await run_session(workspace, ..., backend=backend)
ASSERT outcome.status == "failed"
ASSERT "SDK crash" in outcome.error_message
```

---

### TS-26-E2: ClaudeSDKClient streaming error

**Requirement:** 26-REQ-2.E1
**Type:** unit
**Description:** Verify SDK streaming error yields a ResultMessage with
is_error=True.

**Preconditions:**
- Mock `ClaudeSDKClient` that raises during `receive_response()`.

**Input:**
- Call `ClaudeBackend.execute()`.

**Expected:**
- Stream yields a `ResultMessage` with `is_error=True`.

**Assertion pseudocode:**
```
backend = ClaudeBackend()
messages = collect(backend.execute(...))  # with failing mock
last = messages[-1]
ASSERT isinstance(last, ResultMessage)
ASSERT last.is_error == True
ASSERT last.error_message is not None
```

---

### TS-26-E3: Unknown archetype fallback

**Requirement:** 26-REQ-3.E1
**Type:** unit
**Description:** Verify unknown archetype names fall back to coder with warning.

**Preconditions:**
- Logger captured.

**Input:**
- `get_archetype("nonexistent_archetype")`

**Expected:**
- Returns coder entry. Warning logged.

**Assertion pseudocode:**
```
with caplog at WARNING:
    entry = get_archetype("nonexistent_archetype")
ASSERT entry.name == "coder"
ASSERT any("nonexistent_archetype" in r.message for r in caplog.records)
```

---

### TS-26-E4: Missing template file

**Requirement:** 26-REQ-3.E2
**Type:** unit
**Description:** Verify missing template file raises ConfigError.

**Preconditions:**
- Template directory exists but `skeptic.md` is absent.

**Input:**
- `build_system_prompt(archetype="skeptic")`

**Expected:**
- Raises `ConfigError` with template name in message.

**Assertion pseudocode:**
```
ASSERT_RAISES ConfigError: build_system_prompt(..., archetype="skeptic")
ASSERT "skeptic.md" in str(error)
```

---

### TS-26-E5: Coder instances clamped to 1

**Requirement:** 26-REQ-4.E1
**Type:** unit
**Description:** Verify `instances > 1` for coder is clamped to 1 with warning.

**Preconditions:**
- Logger captured.

**Input:**
- Node with `archetype="coder"`, `instances=3`.

**Expected:**
- Effective instances is 1. Warning logged.

**Assertion pseudocode:**
```
with caplog at WARNING:
    result = clamp_instances("coder", 3)
ASSERT result == 1
ASSERT any("clamped" in r.message or "coder" in r.message for r in caplog.records)
```

---

### TS-26-E6: Instances > 5 clamped

**Requirement:** 26-REQ-4.E2
**Type:** unit
**Description:** Verify `instances > 5` is clamped to 5 with warning.

**Preconditions:**
- Logger captured.

**Input:**
- Node with `archetype="skeptic"`, `instances=10`.

**Expected:**
- Effective instances is 5. Warning logged.

**Assertion pseudocode:**
```
with caplog at WARNING:
    result = clamp_instances("skeptic", 10)
ASSERT result == 5
```

---

### TS-26-E7: Disabled archetype in coordinator override

**Requirement:** 26-REQ-5.E1
**Type:** unit
**Description:** Verify coordinator override referencing a disabled archetype
is ignored with warning.

**Preconditions:**
- Config with `archetypes.librarian = false`.
- Coordinator override setting a node to "librarian".
- Logger captured.

**Input:**
- Build graph with the override.

**Expected:**
- Node retains default archetype ("coder"). Warning logged.

**Assertion pseudocode:**
```
config = make_config(archetypes={"librarian": False})
overrides = [Override(node="spec:3", archetype="librarian")]
with caplog at WARNING:
    graph = build_graph(specs, task_groups, [], config, overrides)
ASSERT graph.nodes["spec:3"].archetype == "coder"
ASSERT any("librarian" in r.message and "disabled" in r.message for r in caplog.records)
```

---

### TS-26-E8: Unknown archetype in tasks.md tag

**Requirement:** 26-REQ-5.E2
**Type:** unit
**Description:** Verify unknown archetype in `[archetype: X]` tag logs
warning and defaults to coder.

**Preconditions:**
- tasks.md with `- [ ] 3. Task [archetype: bogus]`.
- Logger captured.

**Input:**
- Parse tasks, build graph.

**Expected:**
- Group's archetype field is None (or "bogus" → falls back to coder at
  graph builder level). Warning logged.

**Assertion pseudocode:**
```
with caplog at WARNING:
    groups = parse_tasks(path_with_bogus_tag)
    graph = build_graph(...)
ASSERT graph.nodes["spec:3"].archetype == "coder"
```

---

### TS-26-E9: Missing archetypes config section

**Requirement:** 26-REQ-6.E1
**Type:** unit
**Description:** Verify missing `[archetypes]` section uses all defaults.

**Preconditions:**
- Config TOML with no `[archetypes]` section.

**Input:**
- `load_config(path)`.

**Expected:**
- `config.archetypes.coder == True`
- `config.archetypes.skeptic == False`
- `config.archetypes.instances.skeptic == 1`

**Assertion pseudocode:**
```
config = load_config(path_without_archetypes_section)
ASSERT config.archetypes.coder == True
ASSERT config.archetypes.skeptic == False
ASSERT config.archetypes.instances.skeptic == 1
```

---

### TS-26-E10: Partial multi-instance failure

**Requirement:** 26-REQ-7.E1
**Type:** unit
**Description:** Verify convergence proceeds with successful instances when
some fail; all-fail marks node as failed.

**Preconditions:**
- 3 instances. Instance 2 raises an error.

**Input:**
- Case 1: 2 succeed, 1 fails → convergence uses 2 outputs.
- Case 2: All 3 fail → node fails.

**Expected:**
- Case 1: Convergence succeeds with 2 instance outputs.
- Case 2: Node marked as failed.

**Assertion pseudocode:**
```
# Case 1: partial success
results = [success_1, error, success_3]
merged = converge_with_failures(results)
ASSERT merged is not None
ASSERT len(merged.source_instances) == 2

# Case 2: all fail
results = [error, error, error]
merged = converge_with_failures(results)
ASSERT merged is None  # signals node failure
```

---

### TS-26-E11: Skeptic closes issue when no critical findings

**Requirement:** 26-REQ-8.E1
**Type:** integration
**Description:** Verify existing Skeptic issue is closed when re-run finds
zero critical issues.

**Preconditions:**
- Mock `gh` CLI. Existing open issue #42.

**Input:**
- Skeptic completes with zero critical findings.

**Expected:**
- `gh issue close 42` called with resolution comment.

**Assertion pseudocode:**
```
mock_gh_search(returns=[{"number": 42}])
await file_or_update_issue("[Skeptic Review] spec", "", close_if_empty=True)
ASSERT "gh issue close 42" in subprocess_calls
```

---

### TS-26-E12: Retry-predecessor with non-coder predecessor

**Requirement:** 26-REQ-9.E1
**Type:** integration
**Description:** Verify retry-predecessor works regardless of the
predecessor's archetype.

**Preconditions:**
- Graph: `librarian:3 → verifier:4`. Verifier fails.

**Input:**
- Process failed Verifier record.

**Expected:**
- Predecessor `librarian:3` reset to pending.

**Assertion pseudocode:**
```
graph = build_graph_with_edges("spec:3" -> "spec:4")
graph.nodes["spec:3"].archetype = "librarian"
graph.nodes["spec:4"].archetype = "verifier"
process_session_result(failed_verifier_record)
ASSERT graph_sync.node_states["spec:3"] == "pending"
```

---

### TS-26-E13: gh CLI unavailable

**Requirement:** 26-REQ-10.E1
**Type:** unit
**Description:** Verify GitHub issue filing failure is logged but does not
block execution.

**Preconditions:**
- Mock subprocess that raises `FileNotFoundError` (gh not installed).
- Logger captured.

**Input:**
- `file_or_update_issue("[Skeptic] spec", "body")`

**Expected:**
- Returns `None`. Warning logged. No exception raised.

**Assertion pseudocode:**
```
mock_subprocess_raises(FileNotFoundError)
with caplog at WARNING:
    result = await file_or_update_issue("[Skeptic] spec", "body")
ASSERT result is None
ASSERT any("gh" in r.message for r in caplog.records)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 26-REQ-1.1 | TS-26-1 | unit |
| 26-REQ-1.2 | TS-26-2 | unit |
| 26-REQ-1.3 | TS-26-3 | unit |
| 26-REQ-1.4 | TS-26-4 | unit |
| 26-REQ-1.E1 | TS-26-E1 | unit |
| 26-REQ-2.1 | TS-26-5 | unit |
| 26-REQ-2.2 | TS-26-6 | integration |
| 26-REQ-2.3 | TS-26-7 | integration |
| 26-REQ-2.4 | TS-26-8 | unit |
| 26-REQ-2.E1 | TS-26-E2 | unit |
| 26-REQ-3.1 | TS-26-9 | unit |
| 26-REQ-3.2 | TS-26-9 | unit |
| 26-REQ-3.3 | TS-26-10 | unit |
| 26-REQ-3.4 | TS-26-11 | unit |
| 26-REQ-3.5 | TS-26-12, TS-26-42 | unit |
| 26-REQ-3.E1 | TS-26-E3 | unit |
| 26-REQ-3.E2 | TS-26-E4 | unit |
| 26-REQ-4.1 | TS-26-13 | unit |
| 26-REQ-4.2 | TS-26-14 | unit |
| 26-REQ-4.3 | TS-26-15 | unit |
| 26-REQ-4.4 | TS-26-16 | integration |
| 26-REQ-4.E1 | TS-26-E5 | unit |
| 26-REQ-4.E2 | TS-26-E6 | unit |
| 26-REQ-5.1 | TS-26-17 | unit |
| 26-REQ-5.2 | TS-26-18 | unit |
| 26-REQ-5.3 | TS-26-19 | unit |
| 26-REQ-5.4 | TS-26-20 | unit |
| 26-REQ-5.5 | TS-26-21 | unit |
| 26-REQ-5.E1 | TS-26-E7 | unit |
| 26-REQ-5.E2 | TS-26-E8 | unit |
| 26-REQ-6.1 | TS-26-22 | unit |
| 26-REQ-6.2 | TS-26-23 | unit |
| 26-REQ-6.3 | TS-26-24 | unit |
| 26-REQ-6.4 | TS-26-25 | unit |
| 26-REQ-6.5 | TS-26-26 | unit |
| 26-REQ-6.E1 | TS-26-E9 | unit |
| 26-REQ-7.1 | TS-26-27 | integration |
| 26-REQ-7.2 | TS-26-28 | unit |
| 26-REQ-7.3 | TS-26-29 | unit |
| 26-REQ-7.4 | TS-26-30 | unit |
| 26-REQ-7.5 | TS-26-31 | unit |
| 26-REQ-7.E1 | TS-26-E10 | unit |
| 26-REQ-8.1 | TS-26-32 | unit |
| 26-REQ-8.2 | TS-26-33 | integration |
| 26-REQ-8.3 | TS-26-34 | integration |
| 26-REQ-8.4 | TS-26-35 | unit |
| 26-REQ-8.5 | TS-26-36 | unit |
| 26-REQ-8.E1 | TS-26-E11 | integration |
| 26-REQ-9.1 | TS-26-37 | unit |
| 26-REQ-9.2 | TS-26-38 | integration |
| 26-REQ-9.3 | TS-26-39 | integration |
| 26-REQ-9.4 | TS-26-40 | integration |
| 26-REQ-9.E1 | TS-26-E12 | integration |
| 26-REQ-10.1 | TS-26-41 | integration |
| 26-REQ-10.2 | TS-26-41 | integration |
| 26-REQ-10.3 | TS-26-41 | integration |
| 26-REQ-10.E1 | TS-26-E13 | unit |
| Property 1 | TS-26-P1 | property |
| Property 2 | TS-26-P2 | property |
| Property 3 | TS-26-P3 | property |
| Property 4 | TS-26-P4 | property |
| Property 5 | TS-26-P5 | property |
| Property 6 | TS-26-P6 | property |
| Property 7 | TS-26-P7 | property |
| Property 8 | TS-26-P8 | property |
| Property 9 | TS-26-P9 | property |
| Property 10 | TS-26-P10 | property |
| Property 11 | TS-26-P11 | property |
| Property 12 | TS-26-P12 | property |
| Property 13 | TS-26-P13 | property |
| Property 14 | TS-26-P14 | property |
