# Test Specification: Review Archetype Persistence & Review-Only Mode

## Overview

Tests validate that archetype session output is parsed, routed to the correct
insert function, and persisted with supersession. Tests also cover the
review-only CLI mode, review-only graph construction, and retry context
assembly.

## Test Cases

### TS-53-1: Skeptic output parsed and persisted

**Requirement:** 53-REQ-1.1
**Type:** unit
**Description:** Verify that Skeptic session output is parsed into
ReviewFinding instances and inserted via `insert_findings()`.

**Preconditions:**
- Skeptic session completed.
- Output contains valid JSON array of findings.

**Input:**
- Output text: `'Here are the findings:\n[{"severity": "major", "description": "Missing null check", "requirement_ref": "03-REQ-1.1"}]'`
- spec_name: `"03_api"`, task_group: 2, session_id: `"skeptic_03_2"`

**Expected:**
- `insert_findings()` called with 1 `ReviewFinding`.
- Finding has severity="major", description="Missing null check".

**Assertion pseudocode:**
```
mock_insert = mock(insert_findings)
lifecycle.persist_review_findings(output, node_id="skeptic_03_2")
ASSERT mock_insert.called_once
findings = mock_insert.call_args[1]
ASSERT len(findings) == 1
ASSERT findings[0].severity == "major"
```

### TS-53-2: Verifier output parsed and persisted

**Requirement:** 53-REQ-2.1
**Type:** unit
**Description:** Verify that Verifier session output is parsed into
VerificationResult instances and inserted via `insert_verdicts()`.

**Preconditions:**
- Verifier session completed.
- Output contains valid JSON array of verdicts.

**Input:**
- Output text: `'[{"requirement_id": "03-REQ-1.1", "verdict": "PASS", "evidence": "Test passes"}]'`
- spec_name: `"03_api"`, task_group: 2, session_id: `"verifier_03_2"`

**Expected:**
- `insert_verdicts()` called with 1 `VerificationResult`.
- Verdict has requirement_id="03-REQ-1.1", verdict="PASS".

**Assertion pseudocode:**
```
mock_insert = mock(insert_verdicts)
lifecycle.persist_review_findings(output, node_id="verifier_03_2")
ASSERT mock_insert.called_once
verdicts = mock_insert.call_args[1]
ASSERT verdicts[0].verdict == "PASS"
```

### TS-53-3: Oracle output parsed and persisted

**Requirement:** 53-REQ-3.1
**Type:** unit
**Description:** Verify that Oracle session output is parsed into
DriftFinding instances and inserted via `insert_drift_findings()`.

**Preconditions:**
- Oracle session completed.
- Output contains valid JSON array of drift findings.

**Input:**
- Output text: `'[{"severity": "critical", "description": "API endpoint missing", "spec_ref": "03-REQ-2.1", "artifact_ref": "routes.py"}]'`

**Expected:**
- `insert_drift_findings()` called with 1 `DriftFinding`.

**Assertion pseudocode:**
```
mock_insert = mock(insert_drift_findings)
lifecycle.persist_review_findings(output, node_id="oracle_03_0")
ASSERT mock_insert.called_once
```

### TS-53-4: Supersession on re-insert

**Requirement:** 53-REQ-1.2
**Type:** integration
**Description:** Verify that inserting new findings supersedes prior findings
for the same spec + task_group.

**Preconditions:**
- In-memory DuckDB with review_findings table.
- One existing active finding for spec "03_api", task_group 2.

**Input:**
- Insert new finding for same spec + task_group.

**Expected:**
- Prior finding has superseded_by set to new finding's ID.
- New finding has superseded_by = NULL.

**Assertion pseudocode:**
```
insert_findings(conn, [old_finding])
insert_findings(conn, [new_finding])
old_row = conn.execute("SELECT superseded_by FROM review_findings WHERE id = ?", [old_finding.id]).fetchone()
ASSERT old_row.superseded_by IS NOT NULL
new_row = conn.execute("SELECT superseded_by FROM review_findings WHERE id = ?", [new_finding.id]).fetchone()
ASSERT new_row.superseded_by IS NULL
```

### TS-53-5: Parse failure emits audit event

**Requirement:** 53-REQ-1.E1
**Type:** unit
**Description:** Verify that unparseable archetype output triggers a
`review.parse_failure` audit event.

**Preconditions:**
- Archetype output contains no valid JSON.

**Input:**
- Output text: `"This is just prose with no JSON"`

**Expected:**
- `review.parse_failure` audit event emitted with warning severity.
- Payload contains truncated raw output.

**Assertion pseudocode:**
```
events = capture_audit_events(lifecycle.persist_review_findings("no json here", ...))
failure_events = [e for e in events if e.event_type == "review.parse_failure"]
ASSERT len(failure_events) == 1
ASSERT failure_events[0].severity == "warning"
ASSERT "no json here" IN failure_events[0].payload["raw_output"]
```

### TS-53-6: JSON extraction from markdown fences

**Requirement:** 53-REQ-4.1
**Type:** unit
**Description:** Verify that JSON can be extracted from markdown code fences.

**Preconditions:** None.

**Input:**
- Output text containing: ````json\n[{"severity": "minor"}]\n````

**Expected:**
- `extract_json_array()` returns `[{"severity": "minor"}]`.

**Assertion pseudocode:**
```
result = extract_json_array("Some text\n```json\n[{\"severity\": \"minor\"}]\n```\nMore text")
ASSERT result == [{"severity": "minor"}]
```

### TS-53-7: Invalid fields skipped with warning

**Requirement:** 53-REQ-4.2
**Type:** unit
**Description:** Verify that JSON objects missing required fields are skipped.

**Preconditions:** None.

**Input:**
- JSON array with one valid and one invalid finding (missing description).

**Expected:**
- Only the valid finding is returned.
- Warning logged for the invalid one.

**Assertion pseudocode:**
```
findings = parse_review_findings([{"severity": "major", "description": "ok"}, {"severity": "minor"}], ...)
ASSERT len(findings) == 1
ASSERT warning_logged("missing")
```

### TS-53-8: Retry context includes active findings

**Requirement:** 53-REQ-5.1
**Type:** unit
**Description:** Verify that retry sessions include active critical/major
findings in the coder prompt.

**Preconditions:**
- Active critical finding exists for spec "03_api".
- Session is retry (attempt > 1).

**Input:**
- spec_name: `"03_api"`, attempt: 2.

**Expected:**
- Coder prompt contains the critical finding's description.

**Assertion pseudocode:**
```
insert_findings(conn, [critical_finding_for_03_api])
context = lifecycle._build_retry_context("03_api")
ASSERT "Missing null check" IN context
ASSERT "critical" IN context
```

### TS-53-9: Retry context empty when no findings

**Requirement:** 53-REQ-5.E1
**Type:** unit
**Description:** Verify that retry context is empty when no active
critical/major findings exist.

**Preconditions:**
- No active findings for spec.

**Input:**
- spec_name: `"03_api"`, attempt: 2.

**Expected:**
- Empty string returned.

**Assertion pseudocode:**
```
context = lifecycle._build_retry_context("03_api")
ASSERT context == ""
```

### TS-53-10: Review-only flag skips coder sessions

**Requirement:** 53-REQ-6.1
**Type:** integration
**Description:** Verify that `--review-only` skips coder sessions and runs
only review archetypes.

**Preconditions:**
- Project with 2 specs, each having source files and requirements.md.

**Input:**
- CLI invocation: `agent-fox code --review-only`

**Expected:**
- No coder nodes in the task graph.
- Skeptic, Oracle, and Verifier nodes present.

**Assertion pseudocode:**
```
graph = build_review_only_graph(specs_dir, archetypes_config)
node_archetypes = {n.archetype for n in graph.nodes}
ASSERT "coder" NOT IN node_archetypes
ASSERT "skeptic" IN node_archetypes
ASSERT "verifier" IN node_archetypes
ASSERT "oracle" IN node_archetypes
```

### TS-53-11: Review-only graph per-spec nodes

**Requirement:** 53-REQ-6.2
**Type:** unit
**Description:** Verify that the review-only graph creates correct nodes
per spec based on available artifacts.

**Preconditions:**
- Spec A has source files + requirements.md.
- Spec B has source files but no requirements.md.
- Spec C has requirements.md but no source files.

**Input:**
- Build review-only graph for specs A, B, C.

**Expected:**
- Spec A: Skeptic + Oracle + Verifier nodes.
- Spec B: Skeptic + Oracle nodes (no Verifier).
- Spec C: Verifier node only (no Skeptic/Oracle).

**Assertion pseudocode:**
```
graph = build_review_only_graph(specs_dir, config)
spec_a_nodes = [n for n in graph.nodes if n.spec_name == "spec_a"]
ASSERT {n.archetype for n in spec_a_nodes} == {"skeptic", "oracle", "verifier"}
spec_b_nodes = [n for n in graph.nodes if n.spec_name == "spec_b"]
ASSERT {n.archetype for n in spec_b_nodes} == {"skeptic", "oracle"}
spec_c_nodes = [n for n in graph.nodes if n.spec_name == "spec_c"]
ASSERT {n.archetype for n in spec_c_nodes} == {"verifier"}
```

### TS-53-12: Review-only audit events

**Requirement:** 53-REQ-6.3
**Type:** unit
**Description:** Verify that review-only runs emit audit events with
`mode: "review_only"`.

**Preconditions:**
- Sink dispatcher available.

**Input:**
- Review-only run.

**Expected:**
- `run.start` and `run.complete` events have `mode: "review_only"` in payload.

**Assertion pseudocode:**
```
events = capture_audit_events(run_review_only(...))
start = [e for e in events if e.event_type == "run.start"][0]
ASSERT start.payload["mode"] == "review_only"
complete = [e for e in events if e.event_type == "run.complete"][0]
ASSERT complete.payload["mode"] == "review_only"
```

### TS-53-13: Review-only summary output

**Requirement:** 53-REQ-6.5
**Type:** integration
**Description:** Verify that the review-only summary lists findings by
severity and verdicts by status.

**Preconditions:**
- Review-only run produces findings and verdicts.

**Input:**
- 2 critical findings, 1 PASS verdict, 1 FAIL verdict, 1 major drift finding.

**Expected:**
- Summary output contains counts by severity and status.

**Assertion pseudocode:**
```
output = capture_stdout(run_review_only(...))
ASSERT "2 critical" IN output
ASSERT "1 PASS" IN output
ASSERT "1 FAIL" IN output
ASSERT "1 major" IN output
```

## Edge Case Tests

### TS-53-E1: No specs eligible for review

**Requirement:** 53-REQ-6.E1
**Type:** unit
**Description:** Verify that review-only mode with no eligible specs exits
cleanly.

**Preconditions:**
- No specs have source files or requirements.md.

**Input:**
- `--review-only` with empty specs dir.

**Expected:**
- Message "No specs eligible for review" printed.
- Exit code 0.

**Assertion pseudocode:**
```
result = invoke_cli(["code", "--review-only"], specs_dir=empty_dir)
ASSERT result.exit_code == 0
ASSERT "No specs eligible for review" IN result.output
```

### TS-53-E2: Multiple JSON arrays uses first

**Requirement:** 53-REQ-4.E1
**Type:** unit
**Description:** Verify that when output contains multiple JSON arrays,
the first valid one is used.

**Preconditions:** None.

**Input:**
- Output: `'[{"a": 1}] some text [{"b": 2}]'`

**Expected:**
- Returns `[{"a": 1}]`.

**Assertion pseudocode:**
```
result = extract_json_array('[{"a": 1}] text [{"b": 2}]')
ASSERT result == [{"a": 1}]
```

### TS-53-E3: Review-only with spec filter

**Requirement:** 53-REQ-6.E2
**Type:** unit
**Description:** Verify that `--review-only --spec 03_api` only reviews
the specified spec.

**Preconditions:**
- Multiple specs exist.

**Input:**
- `--review-only --spec 03_api`

**Expected:**
- Only spec 03_api has review nodes in the graph.

**Assertion pseudocode:**
```
graph = build_review_only_graph(specs_dir, config, spec_filter="03_api")
spec_names = {n.spec_name for n in graph.nodes}
ASSERT spec_names == {"03_api"}
```

## Property Test Cases

### TS-53-P1: Parse or warn invariant

**Property:** Property 1 from design.md
**Validates:** 53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1
**Type:** property
**Description:** For any archetype output, either findings are persisted or
a parse_failure event is emitted.

**For any:** random text strings (valid JSON, invalid JSON, empty, markdown).
**Invariant:** `insert_*` is called with >= 1 entry OR a `review.parse_failure`
event is emitted.

**Assertion pseudocode:**
```
FOR ANY output IN text_strings():
    events, inserts = capture(lifecycle.persist_review_findings(output, ...))
    ASSERT inserts > 0 OR has_event(events, "review.parse_failure")
```

### TS-53-P2: Supersession consistency

**Property:** Property 2 from design.md
**Validates:** 53-REQ-1.2, 53-REQ-2.2, 53-REQ-3.2
**Type:** property
**Description:** After N insertions for the same spec+task_group, only the
latest batch has superseded_by=NULL.

**For any:** sequence of 1-5 finding batches for the same spec+task_group.
**Invariant:** Only the last batch's findings have superseded_by=NULL.

**Assertion pseudocode:**
```
FOR ANY batches IN lists(lists(review_findings(), min_size=1), min_size=1, max_size=5):
    FOR batch IN batches:
        insert_findings(conn, batch)
    active = conn.execute("SELECT * FROM review_findings WHERE superseded_by IS NULL AND spec_name = ?", [spec]).fetchall()
    ASSERT all(f.id IN last_batch_ids FOR f IN active)
```

### TS-53-P3: Archetype routing correctness

**Property:** Property 3 from design.md
**Validates:** 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1
**Type:** property
**Description:** Each archetype type routes to the correct insert function.

**For any:** archetype in {"skeptic", "verifier", "oracle"}.
**Invariant:** skeptic→insert_findings, verifier→insert_verdicts,
oracle→insert_drift_findings.

**Assertion pseudocode:**
```
FOR ANY archetype IN sampled_from(["skeptic", "verifier", "oracle"]):
    mock_findings = mock(insert_findings)
    mock_verdicts = mock(insert_verdicts)
    mock_drift = mock(insert_drift_findings)
    lifecycle.archetype = archetype
    lifecycle.persist_review_findings(valid_json_output, ...)
    IF archetype == "skeptic": ASSERT mock_findings.called
    IF archetype == "verifier": ASSERT mock_verdicts.called
    IF archetype == "oracle": ASSERT mock_drift.called
```

### TS-53-P4: JSON extraction robustness

**Property:** Property 4 from design.md
**Validates:** 53-REQ-4.1
**Type:** property
**Description:** Any text containing a valid JSON array yields a non-None
result from extract_json_array.

**For any:** valid JSON array wrapped in random prose.
**Invariant:** `extract_json_array()` returns a non-None list.

**Assertion pseudocode:**
```
FOR ANY prefix IN text(), array IN json_arrays(), suffix IN text():
    result = extract_json_array(prefix + json.dumps(array) + suffix)
    ASSERT result IS NOT NULL
    ASSERT result == array
```

### TS-53-P5: Review-only graph completeness

**Property:** Property 5 from design.md
**Validates:** 53-REQ-6.2
**Type:** property
**Description:** Every eligible spec has the correct archetype nodes.

**For any:** set of specs with varying artifacts (source files, requirements.md).
**Invariant:** Specs with source files have Skeptic+Oracle. Specs with
requirements.md have Verifier.

**Assertion pseudocode:**
```
FOR ANY specs IN lists(spec_configs(has_source=booleans(), has_reqs=booleans())):
    graph = build_review_only_graph(specs)
    FOR spec IN specs:
        nodes = {n.archetype for n in graph.nodes if n.spec_name == spec.name}
        IF spec.has_source: ASSERT {"skeptic", "oracle"} <= nodes
        IF spec.has_reqs: ASSERT "verifier" IN nodes
```

### TS-53-P6: Review-only read-only enforcement

**Property:** Property 6 from design.md
**Validates:** 53-REQ-6.4
**Type:** property
**Description:** All review-only nodes use allowlists that exclude write
commands.

**For any:** review-only graph.
**Invariant:** No node's allowlist contains write commands (cp, mv, rm, mkdir,
touch, tee, sed, awk).

**Assertion pseudocode:**
```
WRITE_COMMANDS = {"cp", "mv", "rm", "mkdir", "touch", "tee", "sed", "awk"}
FOR ANY graph IN review_only_graphs():
    FOR node IN graph.nodes:
        allowlist = set(node.archetype_entry.default_allowlist or [])
        ASSERT allowlist.isdisjoint(WRITE_COMMANDS)
```

### TS-53-P7: Retry context includes findings

**Property:** Property 7 from design.md
**Validates:** 53-REQ-5.1, 53-REQ-5.2
**Type:** property
**Description:** Retry context always includes active critical/major findings.

**For any:** spec with 0-10 active findings of varying severity.
**Invariant:** All active critical and major findings appear in the context
string. Minor and observation findings do not.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(review_findings(severity=sampled_from(["critical","major","minor","observation"]))):
    insert_findings(conn, findings)
    context = build_retry_context(spec_name)
    FOR f IN findings:
        IF f.severity IN ("critical", "major"):
            ASSERT f.description IN context
        ELSE:
            ASSERT f.description NOT IN context
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 53-REQ-1.1 | TS-53-1 | unit |
| 53-REQ-1.2 | TS-53-4 | integration |
| 53-REQ-1.E1 | TS-53-5 | unit |
| 53-REQ-2.1 | TS-53-2 | unit |
| 53-REQ-2.2 | TS-53-4 | integration |
| 53-REQ-2.E1 | TS-53-5 | unit |
| 53-REQ-3.1 | TS-53-3 | unit |
| 53-REQ-3.2 | TS-53-4 | integration |
| 53-REQ-3.E1 | TS-53-5 | unit |
| 53-REQ-4.1 | TS-53-6 | unit |
| 53-REQ-4.2 | TS-53-7 | unit |
| 53-REQ-4.E1 | TS-53-E2 | unit |
| 53-REQ-5.1 | TS-53-8 | unit |
| 53-REQ-5.2 | TS-53-8 | unit |
| 53-REQ-5.E1 | TS-53-9 | unit |
| 53-REQ-6.1 | TS-53-10 | integration |
| 53-REQ-6.2 | TS-53-11 | unit |
| 53-REQ-6.3 | TS-53-12 | unit |
| 53-REQ-6.4 | TS-53-P6 | property |
| 53-REQ-6.5 | TS-53-13 | integration |
| 53-REQ-6.E1 | TS-53-E1 | unit |
| 53-REQ-6.E2 | TS-53-E3 | unit |
| Property 1 | TS-53-P1 | property |
| Property 2 | TS-53-P2 | property |
| Property 3 | TS-53-P3 | property |
| Property 4 | TS-53-P4 | property |
| Property 5 | TS-53-P5 | property |
| Property 6 | TS-53-P6 | property |
| Property 7 | TS-53-P7 | property |
