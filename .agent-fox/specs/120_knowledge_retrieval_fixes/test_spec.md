# Test Specification: Knowledge Retrieval Fixes

## Overview

Tests validate that the knowledge retrieval pipeline delivers stored
knowledge to downstream sessions. Each fix has unit tests for the
modified functions and property tests for key invariants. One integration
smoke test verifies end-to-end summary flow.

## Test Cases

### TS-120-1: set_run_id stores run ID

**Requirement:** 120-REQ-1.1
**Type:** unit
**Description:** Verify that `set_run_id()` stores the run ID on the provider.

**Preconditions:**
- FoxKnowledgeProvider instance with in-memory DuckDB.

**Input:**
- `run_id = "20260429_081931_abc123"`

**Expected:**
- `provider._run_id == "20260429_081931_abc123"`

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(knowledge_db, config)
provider.set_run_id("20260429_081931_abc123")
ASSERT provider._run_id == "20260429_081931_abc123"
```

### TS-120-2: Summaries retrieved after set_run_id

**Requirement:** 120-REQ-1.2, 120-REQ-1.4
**Type:** unit
**Description:** Verify that same-spec summaries are returned when run_id is set.

**Preconditions:**
- In-memory DuckDB with `session_summaries` table.
- One summary record for spec "test_spec", task_group "1", run_id "run1".

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="2")`

**Expected:**
- Result contains at least one `[CONTEXT]` item with the summary text.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="test_spec", task_group="1",
    run_id="run1", archetype="coder", attempt=1, summary="Built module X"))
provider.set_run_id("run1")
result = provider.retrieve("test_spec", "test", task_group="2")
ASSERT any("[CONTEXT]" in item AND "Built module X" in item for item in result)
```

### TS-120-3: Cross-spec summaries retrieved after set_run_id

**Requirement:** 120-REQ-1.5
**Type:** unit
**Description:** Verify cross-spec summaries are returned when run_id is set.

**Preconditions:**
- In-memory DuckDB with `session_summaries` table.
- One summary for spec "other_spec", run_id "run1".

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1")`

**Expected:**
- Result contains at least one `[CROSS-SPEC]` item.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="other_spec", task_group="1",
    run_id="run1", archetype="coder", attempt=1, summary="Changed auth"))
provider.set_run_id("run1")
result = provider.retrieve("test_spec", "test", task_group="1")
ASSERT any("[CROSS-SPEC]" in item AND "Changed auth" in item for item in result)
```

### TS-120-4: Engine calls set_run_id on provider

**Requirement:** 120-REQ-1.3
**Type:** unit
**Description:** Verify the engine wires run_id to the knowledge provider.

**Preconditions:**
- Engine initialization with a mock knowledge provider.

**Input:**
- Engine run initialization path.

**Expected:**
- `set_run_id()` is called on the knowledge provider with the generated run ID.

**Assertion pseudocode:**
```
provider = MockKnowledgeProvider()
engine = Engine(config, knowledge_provider=provider)
engine._init_run(plan, state)
ASSERT provider.set_run_id_called_with == engine._run_id
```

### TS-120-5: Pre-review findings in primary review results

**Requirement:** 120-REQ-2.1
**Type:** unit
**Description:** Verify group 0 findings appear in primary review results for non-zero task groups.

**Preconditions:**
- In-memory DuckDB with `review_findings` table.
- One critical finding for spec "test_spec", task_group "0".
- One major finding for spec "test_spec", task_group "1".

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1")`

**Expected:**
- Result contains `[REVIEW]` items for BOTH the group 0 and group 1 findings.

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="0",
    severity="critical", description="Design issue A"))
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="1",
    severity="major", description="Code issue B"))
result = provider.retrieve("test_spec", "test", task_group="1")
review_items = [i for i in result if i.startswith("[REVIEW]")]
ASSERT len(review_items) == 2
ASSERT any("Design issue A" in i for i in review_items)
ASSERT any("Code issue B" in i for i in review_items)
```

### TS-120-6: Pre-review findings tracked in finding_injections

**Requirement:** 120-REQ-2.2
**Type:** unit
**Description:** Verify group 0 findings are recorded in finding_injections.

**Preconditions:**
- In-memory DuckDB with `review_findings` and `finding_injections` tables.
- One finding for spec "test_spec", task_group "0", known ID "F-001".

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1", session_id="sess-1")`

**Expected:**
- `finding_injections` table contains a row for finding_id "F-001" and session_id "sess-1".

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(id="F-001", spec_name="test_spec",
    task_group="0", severity="critical", description="X"))
provider.retrieve("test_spec", "test", task_group="1", session_id="sess-1")
rows = conn.execute("SELECT * FROM finding_injections WHERE finding_id = 'F-001'").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].session_id == "sess-1"
```

### TS-120-7: Pre-review findings excluded from cross-group

**Requirement:** 120-REQ-2.3
**Type:** unit
**Description:** Verify group 0 findings do not appear in cross-group results.

**Preconditions:**
- In-memory DuckDB with one group 0 finding and one group 2 finding.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1")`

**Expected:**
- `[CROSS-GROUP]` items contain the group 2 finding but NOT the group 0 finding.

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="0",
    severity="critical", description="Pre-review issue"))
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="2",
    severity="major", description="Group 2 issue"))
result = provider.retrieve("test_spec", "test", task_group="1")
cross_group = [i for i in result if "[CROSS-GROUP]" in i]
ASSERT any("Group 2 issue" in i for i in cross_group)
ASSERT not any("Pre-review issue" in i for i in cross_group)
```

### TS-120-8: Reviewer summary generated and stored

**Requirement:** 120-REQ-3.1
**Type:** unit
**Description:** Verify reviewer sessions produce a summary with finding counts.

**Preconditions:**
- Reviewer session output with 2 critical and 3 major findings.

**Input:**
- `generate_archetype_summary("reviewer", findings=[2 critical, 3 major])`

**Expected:**
- Summary string contains "2 critical" and "3 major".

**Assertion pseudocode:**
```
findings = [
    ReviewFinding(severity="critical", description="Issue A"),
    ReviewFinding(severity="critical", description="Issue B"),
    ReviewFinding(severity="major", description="Issue C"),
    ReviewFinding(severity="major", description="Issue D"),
    ReviewFinding(severity="major", description="Issue E"),
]
summary = generate_archetype_summary("reviewer", findings=findings)
ASSERT "2 critical" in summary
ASSERT "3 major" in summary
ASSERT "Issue A" in summary  # top finding included
```

### TS-120-9: Verifier summary generated and stored

**Requirement:** 120-REQ-3.2
**Type:** unit
**Description:** Verify verifier sessions produce a summary with pass/fail counts.

**Preconditions:**
- Verifier session output with 10 PASS and 2 FAIL verdicts.

**Input:**
- `generate_archetype_summary("verifier", verdicts=[10 PASS, 2 FAIL])`

**Expected:**
- Summary string contains "10 pass" and "2 fail" and the FAIL requirement IDs.

**Assertion pseudocode:**
```
verdicts = [
    VerificationResult(verdict="PASS", requirement_id="REQ-1.1"),
    # ... 9 more PASS
    VerificationResult(verdict="FAIL", requirement_id="REQ-5.E3"),
    VerificationResult(verdict="FAIL", requirement_id="REQ-8.E1"),
]
summary = generate_archetype_summary("verifier", verdicts=verdicts)
ASSERT "10 pass" in summary.lower()
ASSERT "2 fail" in summary.lower()
ASSERT "REQ-5.E3" in summary
ASSERT "REQ-8.E1" in summary
```

### TS-120-10: Same-spec summaries include all archetypes

**Requirement:** 120-REQ-3.3
**Type:** unit
**Description:** Verify query returns reviewer and verifier summaries too.

**Preconditions:**
- In-memory DuckDB with summaries for coder, reviewer, and verifier archetypes.

**Input:**
- `query_same_spec_summaries(conn, "test_spec", "3", "run1")`

**Expected:**
- Returns 3 records (one per archetype).

**Assertion pseudocode:**
```
for arch in ["coder", "reviewer", "verifier"]:
    insert_summary(conn, SummaryRecord(spec_name="test_spec", task_group="1",
        run_id="run1", archetype=arch, attempt=1, summary=f"{arch} did X"))
records = query_same_spec_summaries(conn, "test_spec", "3", "run1")
ASSERT len(records) == 3
archetypes = {r.archetype for r in records}
ASSERT archetypes == {"coder", "reviewer", "verifier"}
```

### TS-120-11: Prior-run findings surfaced

**Requirement:** 120-REQ-4.1, 120-REQ-4.2
**Type:** unit
**Description:** Verify active findings from a prior run appear as [PRIOR-RUN] items.

**Preconditions:**
- In-memory DuckDB with `review_findings` and `runs` tables.
- One active critical finding created during a prior run.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1")`

**Expected:**
- Result contains a `[PRIOR-RUN]` item with the finding description.

**Assertion pseudocode:**
```
# Insert a prior run and a finding created during it
create_run(conn, "prior_run_id", "hash1")
complete_run(conn, "prior_run_id", "stalled")
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="1",
    severity="critical", description="Unresolved from prior run",
    session_id="prior_session"))
provider.set_run_id("current_run_id")
result = provider.retrieve("test_spec", "test", task_group="1")
ASSERT any("[PRIOR-RUN]" in item AND "Unresolved from prior run" in item for item in result)
```

### TS-120-12: Prior-run findings capped at limit

**Requirement:** 120-REQ-4.3
**Type:** unit
**Description:** Verify prior-run findings are capped at max_items.

**Preconditions:**
- 10 active findings from a prior run.
- `max_prior_run_items = 5`

**Input:**
- `query_prior_run_findings(conn, "test_spec", "current_run_id", max_items=5)`

**Expected:**
- Returns exactly 5 findings, highest severity first.

**Assertion pseudocode:**
```
for i in range(10):
    sev = "critical" if i < 3 else "major"
    insert_finding(conn, ReviewFinding(spec_name="test_spec", severity=sev, ...))
results = query_prior_run_findings(conn, "test_spec", "current_run_id", max_items=5)
ASSERT len(results) == 5
ASSERT all(r.severity == "critical" for r in results[:3])
```

### TS-120-13: Prior-run findings not tracked in finding_injections

**Requirement:** 120-REQ-4.4
**Type:** unit
**Description:** Verify prior-run items are not recorded in finding_injections.

**Preconditions:**
- Active finding from prior run. Provider has session_id set.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1", session_id="sess-1")`

**Expected:**
- `finding_injections` has no rows for prior-run finding IDs.

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(id="F-prior-1", spec_name="test_spec",
    task_group="1", severity="critical", description="Prior issue"))
provider.set_run_id("current_run")
provider.retrieve("test_spec", "test", task_group="1", session_id="sess-1")
rows = conn.execute("SELECT * FROM finding_injections WHERE finding_id = 'F-prior-1'").fetchall()
ASSERT len(rows) == 0
```

## Edge Case Tests

### TS-120-E1: set_run_id never called

**Requirement:** 120-REQ-1.E1
**Type:** unit
**Description:** Summaries return empty when run_id is not set.

**Preconditions:**
- FoxKnowledgeProvider with _run_id = None. Database has summaries.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="2")`

**Expected:**
- No `[CONTEXT]` or `[CROSS-SPEC]` items in result.

**Assertion pseudocode:**
```
insert_summary(conn, SummaryRecord(spec_name="test_spec", ...))
# Do NOT call set_run_id
result = provider.retrieve("test_spec", "test", task_group="2")
ASSERT not any("[CONTEXT]" in i for i in result)
ASSERT not any("[CROSS-SPEC]" in i for i in result)
```

### TS-120-E2: set_run_id with empty string

**Requirement:** 120-REQ-1.E2
**Type:** unit
**Description:** Empty string treated as unset.

**Preconditions:**
- Provider with `set_run_id("")` called.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="2")`

**Expected:**
- No summary items in result.

**Assertion pseudocode:**
```
provider.set_run_id("")
result = provider.retrieve("test_spec", "test", task_group="2")
ASSERT not any("[CONTEXT]" in i for i in result)
```

### TS-120-E3: No group 0 findings

**Requirement:** 120-REQ-2.E1
**Type:** unit
**Description:** When no pre-review findings exist, only same-group findings returned.

**Preconditions:**
- No group 0 findings. One group 1 finding.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="1")`

**Expected:**
- Result contains only the group 1 finding as `[REVIEW]`.

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="1",
    severity="major", description="Code issue"))
result = provider.retrieve("test_spec", "test", task_group="1")
review_items = [i for i in result if i.startswith("[REVIEW]")]
ASSERT len(review_items) == 1
```

### TS-120-E4: Group 0 session does not self-inject

**Requirement:** 120-REQ-2.E2
**Type:** unit
**Description:** Pre-review session (task_group="0") does not see its own findings in cross-group.

**Preconditions:**
- One group 0 finding.

**Input:**
- `retrieve(spec_name="test_spec", task_description="test", task_group="0")`

**Expected:**
- No `[CROSS-GROUP]` items with group 0 findings.

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(spec_name="test_spec", task_group="0",
    severity="critical", description="My own finding"))
result = provider.retrieve("test_spec", "test", task_group="0")
cross_group = [i for i in result if "[CROSS-GROUP]" in i]
ASSERT not any("My own finding" in i for i in cross_group)
```

### TS-120-E5: Reviewer with zero findings

**Requirement:** 120-REQ-3.E1
**Type:** unit
**Description:** Reviewer summary generated even with no findings.

**Preconditions:**
- Empty findings list.

**Input:**
- `generate_archetype_summary("reviewer", findings=[])`

**Expected:**
- Non-empty summary string containing "no findings" or equivalent.

**Assertion pseudocode:**
```
summary = generate_archetype_summary("reviewer", findings=[])
ASSERT len(summary) > 0
ASSERT "no findings" in summary.lower() OR "0 findings" in summary.lower()
```

### TS-120-E6: Verifier with zero verdicts

**Requirement:** 120-REQ-3.E2
**Type:** unit
**Description:** Verifier summary generated even with no verdicts.

**Preconditions:**
- Empty verdicts list.

**Input:**
- `generate_archetype_summary("verifier", verdicts=[])`

**Expected:**
- Non-empty summary string.

**Assertion pseudocode:**
```
summary = generate_archetype_summary("verifier", verdicts=[])
ASSERT len(summary) > 0
```

### TS-120-E7: No prior runs in database

**Requirement:** 120-REQ-4.E1
**Type:** unit
**Description:** Empty prior-run context when no prior runs exist.

**Preconditions:**
- Empty `runs` table.

**Input:**
- `query_prior_run_findings(conn, "test_spec", "current_run", max_items=5)`

**Expected:**
- Empty list returned.

**Assertion pseudocode:**
```
result = query_prior_run_findings(conn, "test_spec", "current_run", max_items=5)
ASSERT result == []
```

### TS-120-E8: All prior findings superseded

**Requirement:** 120-REQ-4.E2
**Type:** unit
**Description:** Empty prior-run context when all findings are superseded.

**Preconditions:**
- All prior-run findings have `superseded_by` set.

**Input:**
- `query_prior_run_findings(conn, "test_spec", "current_run", max_items=5)`

**Expected:**
- Empty list returned.

**Assertion pseudocode:**
```
insert_finding(conn, ReviewFinding(spec_name="test_spec", severity="critical",
    description="Already fixed"))
# Supersede it
conn.execute("UPDATE review_findings SET superseded_by = 'resolved'")
result = query_prior_run_findings(conn, "test_spec", "current_run", max_items=5)
ASSERT result == []
```

## Property Test Cases

### TS-120-P1: run_id Gating

**Property:** Property 1 from design.md
**Validates:** 120-REQ-1.1, 120-REQ-1.2, 120-REQ-1.E1, 120-REQ-1.E2
**Type:** property
**Description:** Summary queries return empty iff run_id is not set or empty.

**For any:** `run_id` in `{None, "", "valid_run_id_123"}`
**Invariant:** When `run_id` is falsy, summary queries return empty. When truthy
and matching summaries exist, queries return non-empty.

**Assertion pseudocode:**
```
FOR ANY run_id IN {None, "", "valid_run_id"}:
    provider = FoxKnowledgeProvider(db, config)
    if run_id is not None:
        provider.set_run_id(run_id)
    insert_summary(conn, SummaryRecord(run_id="valid_run_id", ...))
    result = provider._query_same_spec_summaries(conn, "spec", "2")
    IF run_id is falsy:
        ASSERT result == []
    ELSE:
        ASSERT len(result) > 0
```

### TS-120-P2: No Duplication Between Review and Cross-Group

**Property:** Property 7 from design.md
**Validates:** 120-REQ-2.1, 120-REQ-2.3
**Type:** property
**Description:** A finding never appears in both [REVIEW] and [CROSS-GROUP].

**For any:** set of findings with random task_groups including "0"
**Invariant:** For any task_group T, the set of finding IDs in REVIEW items
and the set in CROSS-GROUP items are disjoint.

**Assertion pseudocode:**
```
FOR ANY findings IN generate_random_findings(task_groups=["0", "1", "2", "3"]):
    FOR ANY target_group IN ["1", "2", "3"]:
        insert all findings
        result = provider.retrieve(spec, desc, task_group=target_group)
        review_descs = {extract_desc(i) for i in result if "[REVIEW]" in i}
        cross_descs = {extract_desc(i) for i in result if "[CROSS-GROUP]" in i}
        ASSERT review_descs.isdisjoint(cross_descs)
```

### TS-120-P3: Prior-Run Findings Never Tracked

**Property:** Property 6 from design.md
**Validates:** 120-REQ-4.4
**Type:** property
**Description:** Prior-run finding IDs never appear in finding_injections.

**For any:** set of prior-run findings
**Invariant:** After retrieve(), finding_injections contains no prior-run IDs.

**Assertion pseudocode:**
```
FOR ANY prior_findings IN generate_prior_run_findings():
    insert all prior_findings
    provider.retrieve(spec, desc, task_group="1", session_id="sess")
    injected = conn.execute("SELECT finding_id FROM finding_injections").fetchall()
    prior_ids = {f.id for f in prior_findings}
    injected_ids = {row[0] for row in injected}
    ASSERT prior_ids.isdisjoint(injected_ids)
```

### TS-120-P4: Archetype Summary Completeness

**Property:** Property 3 from design.md
**Validates:** 120-REQ-3.1, 120-REQ-3.2, 120-REQ-3.E1, 120-REQ-3.E2
**Type:** property
**Description:** generate_archetype_summary always returns a non-empty string.

**For any:** archetype in {"reviewer", "verifier"}, findings/verdicts list
of length 0..20
**Invariant:** Return value is a non-empty string.

**Assertion pseudocode:**
```
FOR ANY archetype IN {"reviewer", "verifier"}:
    FOR ANY items IN generate_random_items(0, 20):
        IF archetype == "reviewer":
            summary = generate_archetype_summary(archetype, findings=items)
        ELSE:
            summary = generate_archetype_summary(archetype, verdicts=items)
        ASSERT isinstance(summary, str)
        ASSERT len(summary) > 0
```

## Integration Smoke Tests

### TS-120-SMOKE-1: End-to-End Summary Flow

**Execution Path:** Path 1 from design.md
**Description:** Summaries stored during session completion are retrieved by
the next session in the same spec.

**Setup:** In-memory DuckDB with all tables. Real FoxKnowledgeProvider (not
mocked). Stubbed engine session lifecycle (no actual Claude calls).

**Trigger:** Store a summary via `ingest()`, then `retrieve()` for the next
task group.

**Expected side effects:**
- `retrieve()` returns a `[CONTEXT]` item containing the stored summary text.

**Must NOT satisfy with:** Mocked `_query_same_spec_summaries` (must hit real DB).

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(real_db, config)
provider.set_run_id("test_run")
# Simulate session completion
provider.ingest("spec:1", "test_spec", {
    "session_status": "completed",
    "summary": "Built the auth module",
    "archetype": "coder",
    "task_group": "1",
    "attempt": 1,
    "run_id": "test_run",
})
# Retrieve for next group
result = provider.retrieve("test_spec", "test", task_group="2")
ASSERT any("[CONTEXT]" in item AND "Built the auth module" in item for item in result)
```

### TS-120-SMOKE-2: Pre-Review to Coder Flow

**Execution Path:** Path 2 from design.md
**Description:** Pre-review findings appear as tracked [REVIEW] items (not
[CROSS-GROUP]) in the first coder session.

**Setup:** In-memory DuckDB. Real provider and review_store.

**Trigger:** Insert group 0 findings, then `retrieve()` for group 1 with a
session_id.

**Expected side effects:**
- Group 0 findings in `[REVIEW]` results.
- Finding IDs recorded in `finding_injections`.
- No group 0 findings in `[CROSS-GROUP]` results.

**Must NOT satisfy with:** Mocked `_query_reviews` or `_query_cross_group_reviews`.

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(real_db, config)
insert_findings(conn, [
    ReviewFinding(id="F-1", spec_name="s", task_group="0", severity="critical", description="Bad design"),
])
result = provider.retrieve("s", "test", task_group="1", session_id="sess-1")
ASSERT any("[REVIEW]" in i AND "Bad design" in i for i in result)
ASSERT not any("[CROSS-GROUP]" in i AND "Bad design" in i for i in result)
injections = conn.execute("SELECT * FROM finding_injections WHERE finding_id = 'F-1'").fetchall()
ASSERT len(injections) == 1
```

### TS-120-SMOKE-3: Cross-Run Carry-Forward Flow

**Execution Path:** Path 4 from design.md
**Description:** Unresolved findings from a prior run appear as [PRIOR-RUN]
items in the new run.

**Setup:** In-memory DuckDB. Real provider. Prior run record with active findings.

**Trigger:** Set provider to current run, then `retrieve()`.

**Expected side effects:**
- `[PRIOR-RUN]` items in result.
- No finding_injections entries for prior-run finding IDs.

**Must NOT satisfy with:** Mocked `_query_prior_run_findings`.

**Assertion pseudocode:**
```
# Create prior run
create_run(conn, "old_run", "hash1")
complete_run(conn, "old_run", "stalled")
insert_finding(conn, ReviewFinding(id="F-old", spec_name="s", task_group="1",
    severity="critical", description="Old issue", session_id="old_sess"))
# Current run
provider.set_run_id("new_run")
result = provider.retrieve("s", "test", task_group="1", session_id="new_sess")
ASSERT any("[PRIOR-RUN]" in i AND "Old issue" in i for i in result)
injections = conn.execute("SELECT * FROM finding_injections WHERE finding_id = 'F-old'").fetchall()
ASSERT len(injections) == 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 120-REQ-1.1 | TS-120-1 | unit |
| 120-REQ-1.2 | TS-120-2 | unit |
| 120-REQ-1.3 | TS-120-4 | unit |
| 120-REQ-1.4 | TS-120-2 | unit |
| 120-REQ-1.5 | TS-120-3 | unit |
| 120-REQ-1.E1 | TS-120-E1 | unit |
| 120-REQ-1.E2 | TS-120-E2 | unit |
| 120-REQ-2.1 | TS-120-5 | unit |
| 120-REQ-2.2 | TS-120-6 | unit |
| 120-REQ-2.3 | TS-120-7 | unit |
| 120-REQ-2.4 | TS-120-5 | unit |
| 120-REQ-2.E1 | TS-120-E3 | unit |
| 120-REQ-2.E2 | TS-120-E4 | unit |
| 120-REQ-3.1 | TS-120-8 | unit |
| 120-REQ-3.2 | TS-120-9 | unit |
| 120-REQ-3.3 | TS-120-10 | unit |
| 120-REQ-3.4 | TS-120-10 | unit |
| 120-REQ-3.E1 | TS-120-E5 | unit |
| 120-REQ-3.E2 | TS-120-E6 | unit |
| 120-REQ-4.1 | TS-120-11 | unit |
| 120-REQ-4.2 | TS-120-11 | unit |
| 120-REQ-4.3 | TS-120-12 | unit |
| 120-REQ-4.4 | TS-120-13 | unit |
| 120-REQ-4.5 | TS-120-11 | unit |
| 120-REQ-4.E1 | TS-120-E7 | unit |
| 120-REQ-4.E2 | TS-120-E8 | unit |
| 120-REQ-4.E3 | TS-120-E7 | unit |
| Property 1 | TS-120-P1 | property |
| Property 2 | TS-120-P2 | property |
| Property 3 | TS-120-P4 | property |
| Property 5 | TS-120-11 | unit |
| Property 6 | TS-120-P3 | property |
| Property 7 | TS-120-P2 | property |
