# Test Specification: Test Auditor Archetype

## Overview

Tests verify the auditor archetype across six areas: registry entry and config,
test-writing group detection, auto_mid graph injection, convergence, retry/
circuit breaker logic, and output persistence. All tests are unit tests.
Property tests use Hypothesis for randomized input generation.

## Test Cases

### TS-46-1: Registry Entry Exists

**Requirement:** 46-REQ-1.1, 46-REQ-1.2, 46-REQ-1.3, 46-REQ-1.4
**Type:** unit
**Description:** Verify the auditor entry exists in ARCHETYPE_REGISTRY with
correct fields.

**Preconditions:**
- Import ARCHETYPE_REGISTRY from archetypes module.

**Input:**
- Look up "auditor" in ARCHETYPE_REGISTRY.

**Expected:**
- Entry exists with: injection="auto_mid", retry_predecessor=True,
  task_assignable=True, default_model_tier="STANDARD",
  templates=["auditor.md"], default_allowlist contains all 9 commands.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["auditor"]
ASSERT entry.injection == "auto_mid"
ASSERT entry.retry_predecessor == True
ASSERT entry.task_assignable == True
ASSERT entry.default_model_tier == "STANDARD"
ASSERT entry.templates == ["auditor.md"]
ASSERT set(["ls","cat","git","grep","find","head","tail","wc","uv"]).issubset(set(entry.default_allowlist))
```

### TS-46-2: Get Archetype Returns Auditor

**Requirement:** 46-REQ-1.E1
**Type:** unit
**Description:** Verify get_archetype("auditor") returns the auditor entry.

**Preconditions:**
- Import get_archetype from archetypes module.

**Input:**
- Call get_archetype("auditor").

**Expected:**
- Returns entry with name="auditor", not the coder fallback.

**Assertion pseudocode:**
```
entry = get_archetype("auditor")
ASSERT entry.name == "auditor"
```

### TS-46-3: Config Auditor Field Default

**Requirement:** 46-REQ-2.1, 46-REQ-2.E1
**Type:** unit
**Description:** Verify ArchetypesConfig defaults auditor to False.

**Preconditions:**
- Import ArchetypesConfig.

**Input:**
- Construct ArchetypesConfig with no arguments.

**Expected:**
- auditor field is False.

**Assertion pseudocode:**
```
config = ArchetypesConfig()
ASSERT config.auditor == False
```

### TS-46-4: Config Instance Count Clamping

**Requirement:** 46-REQ-2.2
**Type:** unit
**Description:** Verify auditor instance count is clamped to [1, 5].

**Preconditions:**
- Import ArchetypeInstancesConfig.

**Input:**
- Construct with auditor=0, auditor=6, auditor=3.

**Expected:**
- Values clamped to 1, 5, 3 respectively.

**Assertion pseudocode:**
```
ASSERT ArchetypeInstancesConfig(auditor=0).auditor == 1
ASSERT ArchetypeInstancesConfig(auditor=6).auditor == 5
ASSERT ArchetypeInstancesConfig(auditor=3).auditor == 3
```

### TS-46-5: AuditorConfig Defaults and Clamping

**Requirement:** 46-REQ-2.3, 46-REQ-2.4
**Type:** unit
**Description:** Verify AuditorConfig defaults and clamping behavior.

**Preconditions:**
- Import AuditorConfig.

**Input:**
- Construct with defaults, with min_ts_entries=0, with max_retries=-1.

**Expected:**
- Defaults: min_ts_entries=5, max_retries=2.
- min_ts_entries=0 clamped to 1.
- max_retries=-1 clamped to 0.

**Assertion pseudocode:**
```
default = AuditorConfig()
ASSERT default.min_ts_entries == 5
ASSERT default.max_retries == 2
ASSERT AuditorConfig(min_ts_entries=0).min_ts_entries == 1
ASSERT AuditorConfig(max_retries=-1).max_retries == 0
```

### TS-46-6: Max Retries Zero Means No Retry

**Requirement:** 46-REQ-2.E2
**Type:** unit
**Description:** Verify max_retries=0 is a valid config (auditor runs once).

**Preconditions:**
- Import AuditorConfig.

**Input:**
- Construct with max_retries=0.

**Expected:**
- max_retries is 0 (not clamped to 1).

**Assertion pseudocode:**
```
config = AuditorConfig(max_retries=0)
ASSERT config.max_retries == 0
```

### TS-46-7: Detection Matches Known Patterns

**Requirement:** 46-REQ-3.1, 46-REQ-3.2
**Type:** unit
**Description:** Verify is_test_writing_group detects all specified patterns.

**Preconditions:**
- Import is_test_writing_group from builder module.

**Input:**
- Various group titles containing the specified patterns.

**Expected:**
- Returns True for each matching pattern.

**Assertion pseudocode:**
```
ASSERT is_test_writing_group("Write failing spec tests") == True
ASSERT is_test_writing_group("Write failing tests") == True
ASSERT is_test_writing_group("Create unit test files") == True
ASSERT is_test_writing_group("Create test file structure") == True
ASSERT is_test_writing_group("1. Spec tests") == True
```

### TS-46-8: Detection Case Insensitive

**Requirement:** 46-REQ-3.1
**Type:** unit
**Description:** Verify detection is case-insensitive.

**Preconditions:**
- Import is_test_writing_group.

**Input:**
- "WRITE FAILING SPEC TESTS", "write Failing Spec Tests".

**Expected:**
- Both return True.

**Assertion pseudocode:**
```
ASSERT is_test_writing_group("WRITE FAILING SPEC TESTS") == True
ASSERT is_test_writing_group("write Failing Spec Tests") == True
```

### TS-46-9: Detection Rejects Non-Test Groups

**Requirement:** 46-REQ-3.E1
**Type:** unit
**Description:** Verify is_test_writing_group returns False for non-test
group titles.

**Preconditions:**
- Import is_test_writing_group.

**Input:**
- "Implement core module", "Refactor database layer", "Phase A checkpoint".

**Expected:**
- All return False.

**Assertion pseudocode:**
```
ASSERT is_test_writing_group("Implement core module") == False
ASSERT is_test_writing_group("Refactor database layer") == False
ASSERT is_test_writing_group("Phase A checkpoint") == False
```

### TS-46-10: Detection Matches Substrings

**Requirement:** 46-REQ-3.E2
**Type:** unit
**Description:** Verify detection matches patterns as substrings.

**Preconditions:**
- Import is_test_writing_group.

**Input:**
- "Write failing spec tests for module X".

**Expected:**
- Returns True.

**Assertion pseudocode:**
```
ASSERT is_test_writing_group("Write failing spec tests for module X") == True
```

### TS-46-11: Auto-Mid Injection Creates Node and Edges

**Requirement:** 46-REQ-4.1, 46-REQ-4.2, 46-REQ-4.3
**Type:** unit
**Description:** Verify auto_mid injection inserts auditor node with correct
edges between test-writing group and next group.

**Preconditions:**
- ArchetypesConfig with auditor=True.
- A spec with task groups: group 1 titled "Write failing spec tests",
  group 2 titled "Implement core".
- test_spec.md with >= 5 TS entries.

**Input:**
- Call build_graph with the above config.

**Expected:**
- An auditor node exists between group 1 and group 2.
- Edge from group 1 to auditor node.
- Edge from auditor node to group 2.
- Auditor node has archetype="auditor".
- Auditor node instances match config.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
ASSERT len(auditor_nodes) == 1
ASSERT has_edge(graph, group_1_node, auditor_nodes[0])
ASSERT has_edge(graph, auditor_nodes[0], group_2_node)
ASSERT auditor_nodes[0].instances == config.instances.auditor
```

### TS-46-12: Injection Skipped When Disabled

**Requirement:** 46-REQ-4.E1
**Type:** unit
**Description:** Verify no auditor injection when auditor is disabled.

**Preconditions:**
- ArchetypesConfig with auditor=False.
- Spec with test-writing group.

**Input:**
- Call build_graph.

**Expected:**
- No auditor nodes in graph.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
ASSERT len(auditor_nodes) == 0
```

### TS-46-13: Injection Skipped Below TS Threshold

**Requirement:** 46-REQ-4.4
**Type:** unit
**Description:** Verify injection skipped when TS entry count is below
min_ts_entries threshold.

**Preconditions:**
- ArchetypesConfig with auditor=True, min_ts_entries=5.
- test_spec.md with 3 TS entries.

**Input:**
- Call build_graph.

**Expected:**
- No auditor nodes injected.
- INFO log message about skipping.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
ASSERT len(auditor_nodes) == 0
ASSERT "skip" in caplog.text.lower()
```

### TS-46-14: Injection When Test Group Is Last

**Requirement:** 46-REQ-4.E2
**Type:** unit
**Description:** Verify auditor node is injected after last group with no
successor edge when the test-writing group is the only/last group.

**Preconditions:**
- Spec with only one group titled "Write failing spec tests".
- Sufficient TS entries.

**Input:**
- Call build_graph.

**Expected:**
- Auditor node exists with incoming edge from group 1.
- No outgoing edge from auditor node.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
ASSERT len(auditor_nodes) == 1
ASSERT has_edge(graph, group_1_node, auditor_nodes[0])
outgoing = [e for e in graph.edges if e.source == auditor_nodes[0].id]
ASSERT len(outgoing) == 0
```

### TS-46-15: Coexistence With Skeptic

**Requirement:** 46-REQ-4.E3
**Type:** unit
**Description:** Verify both skeptic and auditor inject without conflict.

**Preconditions:**
- ArchetypesConfig with skeptic=True, auditor=True.
- Spec with test-writing group and sufficient TS entries.

**Input:**
- Call build_graph.

**Expected:**
- Both skeptic (auto_pre at group 0) and auditor (auto_mid) nodes exist.
- No edge conflicts.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
skeptic_nodes = [n for n in graph.nodes if n.archetype == "skeptic"]
auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
ASSERT len(skeptic_nodes) >= 1
ASSERT len(auditor_nodes) >= 1
```

### TS-46-16: Multiple Test Groups Get Multiple Auditors

**Requirement:** 46-REQ-3.3
**Type:** unit
**Description:** Verify an auditor node is injected after each test-writing
group when multiple exist.

**Preconditions:**
- Spec with two groups matching test-writing patterns.
- Sufficient TS entries.

**Input:**
- Call build_graph.

**Expected:**
- Two auditor nodes, one after each test-writing group.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
ASSERT len(auditor_nodes) == 2
```

### TS-46-17: Prompt Template Exists

**Requirement:** 46-REQ-5.1
**Type:** unit
**Description:** Verify auditor.md template file exists in the templates
directory.

**Preconditions:**
- Access to the templates directory.

**Input:**
- Check file existence.

**Expected:**
- File agent_fox/_templates/prompts/auditor.md exists.

**Assertion pseudocode:**
```
template_path = Path("agent_fox/_templates/prompts/auditor.md")
ASSERT template_path.exists()
```

### TS-46-18: Prompt Template Content

**Requirement:** 46-REQ-5.2, 46-REQ-5.3, 46-REQ-5.4, 46-REQ-5.5
**Type:** unit
**Description:** Verify the auditor.md template contains required structural
elements.

**Preconditions:**
- Read auditor.md template content.

**Input:**
- Parse template text.

**Expected:**
- Contains all five audit dimensions.
- Contains JSON output format specification.
- Contains FAIL criteria definition.
- Contains {spec_name} and {task_group} template variables.

**Assertion pseudocode:**
```
content = read("agent_fox/_templates/prompts/auditor.md")
ASSERT "coverage" in content.lower()
ASSERT "assertion strength" in content.lower()
ASSERT "precondition fidelity" in content.lower()
ASSERT "edge case" in content.lower()
ASSERT "independence" in content.lower()
ASSERT "PASS" in content and "WEAK" in content
ASSERT "MISSING" in content and "MISALIGNED" in content
ASSERT "{spec_name}" in content
ASSERT "{task_group}" in content
```

### TS-46-19: Convergence Union Semantics

**Requirement:** 46-REQ-6.1, 46-REQ-6.3
**Type:** unit
**Description:** Verify converge_auditor uses union: worst verdict per TS
entry wins, overall FAIL if any instance FAILs.

**Preconditions:**
- Import converge_auditor, AuditResult, AuditEntry.

**Input:**
- Instance 1: TS-1 PASS, TS-2 WEAK, overall PASS.
- Instance 2: TS-1 MISSING, TS-2 PASS, overall FAIL.

**Expected:**
- Merged: TS-1 MISSING, TS-2 WEAK, overall FAIL.

**Assertion pseudocode:**
```
r1 = AuditResult(entries=[AuditEntry("TS-1", [], "PASS"), AuditEntry("TS-2", [], "WEAK")], overall_verdict="PASS", summary="")
r2 = AuditResult(entries=[AuditEntry("TS-1", [], "MISSING"), AuditEntry("TS-2", [], "PASS")], overall_verdict="FAIL", summary="")
merged = converge_auditor([r1, r2])
ASSERT find_entry(merged, "TS-1").verdict == "MISSING"
ASSERT find_entry(merged, "TS-2").verdict == "WEAK"
ASSERT merged.overall_verdict == "FAIL"
```

### TS-46-20: Convergence Single Instance Passthrough

**Requirement:** 46-REQ-6.E1
**Type:** unit
**Description:** Verify single instance result is returned directly.

**Preconditions:**
- Import converge_auditor.

**Input:**
- A single AuditResult.

**Expected:**
- Returned as-is without modification.

**Assertion pseudocode:**
```
result = AuditResult(entries=[...], overall_verdict="PASS", summary="ok")
merged = converge_auditor([result])
ASSERT merged == result
```

### TS-46-21: Convergence All Instances Fail

**Requirement:** 46-REQ-6.E2
**Type:** unit
**Description:** Verify empty input returns PASS with warning.

**Preconditions:**
- Import converge_auditor.

**Input:**
- Empty list.

**Expected:**
- Returns AuditResult with overall_verdict="PASS" and empty entries.

**Assertion pseudocode:**
```
merged = converge_auditor([])
ASSERT merged.overall_verdict == "PASS"
ASSERT len(merged.entries) == 0
```

### TS-46-22: Convergence No LLM

**Requirement:** 46-REQ-6.4
**Type:** unit
**Description:** Verify convergence function does not import or call any
LLM-related modules.

**Preconditions:**
- Inspect converge_auditor source or module imports.

**Input:**
- Check module-level imports of convergence.py.

**Expected:**
- No imports from claude_code_sdk or similar.

**Assertion pseudocode:**
```
source = inspect.getsource(converge_auditor)
ASSERT "claude" not in source.lower()
ASSERT "llm" not in source.lower()
ASSERT "anthropic" not in source.lower()
```

### TS-46-23: Retry Triggered On FAIL

**Requirement:** 46-REQ-7.1
**Type:** unit
**Description:** Verify auditor FAIL resets predecessor coder to pending.

**Preconditions:**
- Mock orchestrator with auditor node and predecessor coder node.
- Auditor returns FAIL verdict.

**Input:**
- Process auditor session result with FAIL verdict.

**Expected:**
- Predecessor coder node reset to "pending".
- Auditor findings included as error context.

**Assertion pseudocode:**
```
process_session_result(auditor_node, fail_result)
ASSERT graph_sync.node_states[predecessor_id] == "pending"
ASSERT error_tracker[predecessor_id] contains audit findings
```

### TS-46-24: Auditor Re-runs After Retry

**Requirement:** 46-REQ-7.2
**Type:** unit
**Description:** Verify the auditor node is also reset to pending after
triggering a retry.

**Preconditions:**
- Mock orchestrator with auditor node.

**Input:**
- Process auditor FAIL result.

**Expected:**
- Auditor node itself is reset to "pending" (so it re-runs).

**Assertion pseudocode:**
```
process_session_result(auditor_node, fail_result)
ASSERT graph_sync.node_states[auditor_node_id] == "pending"
```

### TS-46-25: Circuit Breaker Blocks After Max Retries

**Requirement:** 46-REQ-7.4, 46-REQ-7.5
**Type:** unit
**Description:** Verify circuit breaker blocks the auditor node and prevents
downstream execution after max retries.

**Preconditions:**
- auditor_config.max_retries = 2.
- Auditor has already been retried 2 times.

**Input:**
- Process auditor FAIL result on attempt 3.

**Expected:**
- Auditor node marked as "blocked".
- Predecessor NOT reset (no more retries).
- Warning log about circuit breaker.

**Assertion pseudocode:**
```
process_session_result(auditor_node, fail_result, attempt=3)
ASSERT graph_sync.node_states[auditor_node_id] == "blocked"
ASSERT graph_sync.node_states[predecessor_id] != "pending"
ASSERT "circuit breaker" in caplog.text.lower()
```

### TS-46-26: Circuit Breaker Files GitHub Issue

**Requirement:** 46-REQ-7.6
**Type:** unit
**Description:** Verify circuit breaker files a GitHub issue.

**Preconditions:**
- Mock file_or_update_issue.
- Circuit breaker trips.

**Input:**
- Process circuit breaker trip.

**Expected:**
- file_or_update_issue called with title containing "circuit breaker".

**Assertion pseudocode:**
```
process_circuit_breaker(auditor_node, findings)
ASSERT mock_file_issue.called
ASSERT "circuit breaker" in mock_file_issue.call_args.title.lower()
```

### TS-46-27: Max Retries Zero Blocks On First FAIL

**Requirement:** 46-REQ-7.E1
**Type:** unit
**Description:** Verify max_retries=0 means auditor blocks on first FAIL.

**Preconditions:**
- auditor_config.max_retries = 0.
- Auditor returns FAIL.

**Input:**
- Process auditor FAIL result on attempt 1.

**Expected:**
- Auditor node marked as "blocked".
- GitHub issue filed.

**Assertion pseudocode:**
```
process_session_result(auditor_node, fail_result, attempt=1, max_retries=0)
ASSERT graph_sync.node_states[auditor_node_id] == "blocked"
ASSERT mock_file_issue.called
```

### TS-46-28: PASS On First Run No Retry

**Requirement:** 46-REQ-7.E2
**Type:** unit
**Description:** Verify PASS verdict does not trigger retry.

**Preconditions:**
- Auditor returns PASS.

**Input:**
- Process auditor PASS result.

**Expected:**
- Predecessor not reset.
- Auditor node completes normally.

**Assertion pseudocode:**
```
process_session_result(auditor_node, pass_result)
ASSERT graph_sync.node_states[predecessor_id] != "pending"
ASSERT graph_sync.node_states[auditor_node_id] == "completed"
```

### TS-46-29: Audit File Written

**Requirement:** 46-REQ-8.1
**Type:** unit
**Description:** Verify audit.md is written to spec directory.

**Preconditions:**
- Mock filesystem.
- AuditResult with entries.

**Input:**
- Call _persist_auditor_results(spec_dir, result).

**Expected:**
- File written at spec_dir / "audit.md".
- Content contains per-entry verdicts.

**Assertion pseudocode:**
```
_persist_auditor_results(spec_dir, result)
content = read(spec_dir / "audit.md")
ASSERT "TS-05-1" in content
ASSERT "PASS" in content or "FAIL" in content
```

### TS-46-30: GitHub Issue On FAIL

**Requirement:** 46-REQ-8.2
**Type:** unit
**Description:** Verify GitHub issue filed on FAIL verdict.

**Preconditions:**
- Mock file_or_update_issue.

**Input:**
- Auditor completes with FAIL verdict.

**Expected:**
- file_or_update_issue called with title "[Auditor] spec_name: FAIL".

**Assertion pseudocode:**
```
handle_auditor_result(spec_name, fail_result)
ASSERT mock_file_issue.called
ASSERT "[Auditor]" in mock_file_issue.call_args.title
ASSERT "FAIL" in mock_file_issue.call_args.title
```

### TS-46-31: GitHub Issue Closed On PASS

**Requirement:** 46-REQ-8.3
**Type:** unit
**Description:** Verify existing GitHub issue is closed on PASS.

**Preconditions:**
- Mock file_or_update_issue.
- Existing open issue.

**Input:**
- Auditor completes with PASS verdict.

**Expected:**
- file_or_update_issue called with close_if_empty=True or equivalent.

**Assertion pseudocode:**
```
handle_auditor_result(spec_name, pass_result)
ASSERT mock_file_issue.called
ASSERT mock_file_issue.call_args includes close logic
```

### TS-46-32: Retry Audit Event Emitted

**Requirement:** 46-REQ-8.4
**Type:** unit
**Description:** Verify auditor.retry audit event is emitted on retry.

**Preconditions:**
- Mock audit sink.

**Input:**
- Auditor triggers retry.

**Expected:**
- Audit event with type "auditor.retry" emitted.
- Event contains spec_name, group_number, attempt.

**Assertion pseudocode:**
```
trigger_auditor_retry(spec_name, group, attempt)
events = mock_sink.events
retry_events = [e for e in events if e.event_type == "auditor.retry"]
ASSERT len(retry_events) == 1
ASSERT retry_events[0].spec_name == spec_name
```

## Edge Case Tests

### TS-46-E1: No Test Groups Detected

**Requirement:** 46-REQ-3.E1
**Type:** unit
**Description:** Verify no auditor injection when no test-writing groups exist.

**Preconditions:**
- All group titles are implementation groups.

**Input:**
- Call build_graph.

**Expected:**
- Zero auditor nodes.

**Assertion pseudocode:**
```
graph = build_graph(specs, task_groups, archetypes_config=config)
ASSERT len([n for n in graph.nodes if n.archetype == "auditor"]) == 0
```

### TS-46-E2: gh CLI Unavailable

**Requirement:** 46-REQ-8.E1
**Type:** unit
**Description:** Verify GitHub issue failure does not block execution.

**Preconditions:**
- Mock subprocess to raise FileNotFoundError for gh.

**Input:**
- Attempt to file issue.

**Expected:**
- Warning logged, no exception raised.

**Assertion pseudocode:**
```
with mock_gh_unavailable:
    handle_auditor_result(spec_name, fail_result)
    # No exception raised
ASSERT "gh" in caplog.text.lower() or warning logged
```

### TS-46-E3: audit.md Write Failure

**Requirement:** 46-REQ-8.E2
**Type:** unit
**Description:** Verify filesystem error during audit.md write does not block.

**Preconditions:**
- Mock filesystem to raise OSError on write.

**Input:**
- Call _persist_auditor_results.

**Expected:**
- Error logged, no exception raised.

**Assertion pseudocode:**
```
with mock_write_failure:
    _persist_auditor_results(spec_dir, result)
    # No exception raised
ASSERT "error" in caplog.text.lower()
```

### TS-46-E4: TS Entry Count Function

**Requirement:** 46-REQ-4.4
**Type:** unit
**Description:** Verify count_ts_entries correctly counts TS entries.

**Preconditions:**
- A test_spec.md file with known number of TS entries.

**Input:**
- Call count_ts_entries(spec_dir).

**Expected:**
- Returns correct count.

**Assertion pseudocode:**
```
# Create test_spec.md with 7 TS entries
count = count_ts_entries(spec_dir)
ASSERT count == 7
```

### TS-46-E5: TS Entry Count Missing File

**Requirement:** 46-REQ-4.4
**Type:** unit
**Description:** Verify count_ts_entries returns 0 for missing file.

**Preconditions:**
- No test_spec.md in spec_dir.

**Input:**
- Call count_ts_entries(spec_dir).

**Expected:**
- Returns 0.

**Assertion pseudocode:**
```
count = count_ts_entries(empty_spec_dir)
ASSERT count == 0
```

## Property Test Cases

### TS-46-P1: Detection Completeness

**Property:** Property 1 from design.md
**Validates:** 46-REQ-3.1, 46-REQ-3.2, 46-REQ-3.E2
**Type:** property
**Description:** Any string containing a test-writing pattern as a substring
is detected.

**For any:** prefix (text), pattern (sampled from known patterns), suffix (text)
**Invariant:** is_test_writing_group(prefix + pattern + suffix) is True.

**Assertion pseudocode:**
```
FOR ANY prefix IN st.text(max_size=20),
       pattern IN st.sampled_from(KNOWN_PATTERNS),
       suffix IN st.text(max_size=20):
    title = prefix + pattern + suffix
    ASSERT is_test_writing_group(title) == True
```

### TS-46-P2: Detection Specificity

**Property:** Property 2 from design.md
**Validates:** 46-REQ-3.1, 46-REQ-3.E1
**Type:** property
**Description:** Strings not containing any pattern are not detected.

**For any:** title composed of alphabet characters not forming any pattern
**Invariant:** is_test_writing_group(title) is False.

**Assertion pseudocode:**
```
FOR ANY title IN st.text(alphabet=st.characters(whitelist_categories=("L",)), max_size=50):
    assume(not any(p in title.lower() for p in pattern_strings))
    ASSERT is_test_writing_group(title) == False
```

### TS-46-P3: Injection Graph Integrity

**Property:** Property 3 from design.md
**Validates:** 46-REQ-4.1, 46-REQ-4.2, 46-REQ-4.3, 46-REQ-4.E2
**Type:** property
**Description:** Injected auditor nodes have correct edge structure.

**For any:** number of task groups (1-5), position of test-writing group
**Invariant:** Auditor node has exactly 1 incoming edge from test group,
0 or 1 outgoing edges.

**Assertion pseudocode:**
```
FOR ANY n_groups IN st.integers(1, 5),
       test_group_idx IN st.integers(0, n_groups-1):
    graph = build_graph_with_test_group_at(n_groups, test_group_idx)
    auditor_nodes = [n for n in graph.nodes if n.archetype == "auditor"]
    ASSERT len(auditor_nodes) == 1
    incoming = edges_to(graph, auditor_nodes[0])
    ASSERT len(incoming) == 1
    outgoing = edges_from(graph, auditor_nodes[0])
    ASSERT len(outgoing) <= 1
```

### TS-46-P4: Convergence Union Semantics

**Property:** Property 4 from design.md
**Validates:** 46-REQ-6.1, 46-REQ-6.3
**Type:** property
**Description:** Merged verdict for each TS entry is the worst across instances.

**For any:** list of AuditResults with random per-entry verdicts
**Invariant:** Each merged entry verdict equals the worst individual verdict
for that TS entry.

**Assertion pseudocode:**
```
FOR ANY results IN st.lists(audit_result_strategy(), min_size=1, max_size=5):
    merged = converge_auditor(results)
    for ts_id in all_ts_ids(results):
        individual_verdicts = [get_verdict(r, ts_id) for r in results]
        ASSERT get_verdict(merged, ts_id) == worst(individual_verdicts)
```

### TS-46-P5: Convergence Determinism

**Property:** Property 5 from design.md
**Validates:** 46-REQ-6.4
**Type:** property
**Description:** Convergence produces identical output for identical input.

**For any:** list of AuditResults
**Invariant:** converge_auditor(input) == converge_auditor(input).

**Assertion pseudocode:**
```
FOR ANY results IN st.lists(audit_result_strategy(), min_size=1, max_size=5):
    ASSERT converge_auditor(results) == converge_auditor(results)
```

### TS-46-P6: Circuit Breaker Bound

**Property:** Property 6 from design.md
**Validates:** 46-REQ-7.3, 46-REQ-7.4
**Type:** property
**Description:** Retry count never exceeds max_retries.

**For any:** max_retries in [0, 10], sequence of FAIL verdicts
**Invariant:** Number of predecessor resets <= max_retries.

**Assertion pseudocode:**
```
FOR ANY max_retries IN st.integers(0, 10):
    reset_count = simulate_retry_loop(max_retries, always_fail=True)
    ASSERT reset_count <= max_retries
```

### TS-46-P7: Config Clamping

**Property:** Property 7 from design.md
**Validates:** 46-REQ-2.2, 46-REQ-2.3
**Type:** property
**Description:** Config values are always within valid ranges.

**For any:** integer values for min_ts_entries, max_retries, instances
**Invariant:** min_ts_entries >= 1, max_retries >= 0, instances in [1, 5].

**Assertion pseudocode:**
```
FOR ANY min_ts IN st.integers(-100, 100),
       max_r IN st.integers(-100, 100),
       inst IN st.integers(-100, 100):
    ac = AuditorConfig(min_ts_entries=min_ts, max_retries=max_r)
    ic = ArchetypeInstancesConfig(auditor=inst)
    ASSERT ac.min_ts_entries >= 1
    ASSERT ac.max_retries >= 0
    ASSERT 1 <= ic.auditor <= 5
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 46-REQ-1.1 | TS-46-1 | unit |
| 46-REQ-1.2 | TS-46-1 | unit |
| 46-REQ-1.3 | TS-46-1 | unit |
| 46-REQ-1.4 | TS-46-1 | unit |
| 46-REQ-1.E1 | TS-46-2 | unit |
| 46-REQ-2.1 | TS-46-3 | unit |
| 46-REQ-2.2 | TS-46-4 | unit |
| 46-REQ-2.3 | TS-46-5 | unit |
| 46-REQ-2.4 | TS-46-5 | unit |
| 46-REQ-2.E1 | TS-46-3 | unit |
| 46-REQ-2.E2 | TS-46-6 | unit |
| 46-REQ-3.1 | TS-46-7, TS-46-8 | unit |
| 46-REQ-3.2 | TS-46-7 | unit |
| 46-REQ-3.3 | TS-46-16 | unit |
| 46-REQ-3.E1 | TS-46-9 | unit |
| 46-REQ-3.E2 | TS-46-10 | unit |
| 46-REQ-4.1 | TS-46-11 | unit |
| 46-REQ-4.2 | TS-46-11 | unit |
| 46-REQ-4.3 | TS-46-11 | unit |
| 46-REQ-4.4 | TS-46-13 | unit |
| 46-REQ-4.E1 | TS-46-12 | unit |
| 46-REQ-4.E2 | TS-46-14 | unit |
| 46-REQ-4.E3 | TS-46-15 | unit |
| 46-REQ-5.1 | TS-46-17 | unit |
| 46-REQ-5.2 | TS-46-18 | unit |
| 46-REQ-5.3 | TS-46-18 | unit |
| 46-REQ-5.4 | TS-46-18 | unit |
| 46-REQ-5.5 | TS-46-18 | unit |
| 46-REQ-5.E1 | (covered by spec 26) | - |
| 46-REQ-6.1 | TS-46-19 | unit |
| 46-REQ-6.2 | TS-46-19 | unit |
| 46-REQ-6.3 | TS-46-19 | unit |
| 46-REQ-6.4 | TS-46-22 | unit |
| 46-REQ-6.E1 | TS-46-20 | unit |
| 46-REQ-6.E2 | TS-46-21 | unit |
| 46-REQ-7.1 | TS-46-23 | unit |
| 46-REQ-7.2 | TS-46-24 | unit |
| 46-REQ-7.3 | TS-46-25 | unit |
| 46-REQ-7.4 | TS-46-25 | unit |
| 46-REQ-7.5 | TS-46-25 | unit |
| 46-REQ-7.6 | TS-46-26 | unit |
| 46-REQ-7.E1 | TS-46-27 | unit |
| 46-REQ-7.E2 | TS-46-28 | unit |
| 46-REQ-8.1 | TS-46-29 | unit |
| 46-REQ-8.2 | TS-46-30 | unit |
| 46-REQ-8.3 | TS-46-31 | unit |
| 46-REQ-8.4 | TS-46-32 | unit |
| 46-REQ-8.E1 | TS-46-E2 | unit |
| 46-REQ-8.E2 | TS-46-E3 | unit |
| Property 1 | TS-46-P1 | property |
| Property 2 | TS-46-P2 | property |
| Property 3 | TS-46-P3 | property |
| Property 4 | TS-46-P4 | property |
| Property 5 | TS-46-P5 | property |
| Property 6 | TS-46-P6 | property |
| Property 7 | TS-46-P7 | property |
