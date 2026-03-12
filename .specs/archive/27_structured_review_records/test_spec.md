# Test Specification: Structured Review Records

## Overview

Tests validate the structured review records pipeline end-to-end: schema
creation, JSON parsing, DB insertion with supersession, context rendering,
convergence on DB records, and backward compatibility. Tests use in-memory
DuckDB connections and the existing `schema_conn` / `knowledge_config`
fixtures.

## Test Cases

### TS-27-1: Review Findings Table Created

**Requirement:** 27-REQ-1.1
**Type:** unit
**Description:** Verify that schema migration creates the `review_findings`
table with correct columns.

**Preconditions:**
- In-memory DuckDB connection with schema v1 applied.

**Input:**
- Run migration v2.

**Expected:**
- Table `review_findings` exists with columns: id, severity, description,
  requirement_ref, spec_name, task_group, session_id, superseded_by,
  created_at.

**Assertion pseudocode:**
```
apply_migration_v2(conn)
columns = conn.execute("DESCRIBE review_findings").fetchall()
column_names = [c[0] for c in columns]
ASSERT "id" IN column_names
ASSERT "severity" IN column_names
ASSERT "superseded_by" IN column_names
```

### TS-27-2: Verification Results Table Created

**Requirement:** 27-REQ-2.1
**Type:** unit
**Description:** Verify that schema migration creates the
`verification_results` table with correct columns.

**Preconditions:**
- In-memory DuckDB connection with schema v1 applied.

**Input:**
- Run migration v2.

**Expected:**
- Table `verification_results` exists with columns: id, requirement_id,
  verdict, evidence, spec_name, task_group, session_id, superseded_by,
  created_at.

**Assertion pseudocode:**
```
apply_migration_v2(conn)
columns = conn.execute("DESCRIBE verification_results").fetchall()
column_names = [c[0] for c in columns]
ASSERT "requirement_id" IN column_names
ASSERT "verdict" IN column_names
```

### TS-27-3: Parse Skeptic JSON Output

**Requirement:** 27-REQ-3.1
**Type:** unit
**Description:** Verify that valid Skeptic JSON output is parsed into
ReviewFinding objects.

**Preconditions:**
- None.

**Input:**
- Agent response containing:
  ```json
  {"findings": [{"severity": "critical", "description": "Missing edge case", "requirement_ref": "05-REQ-1.1"}]}
  ```

**Expected:**
- List of one ReviewFinding with severity="critical",
  description="Missing edge case", requirement_ref="05-REQ-1.1".

**Assertion pseudocode:**
```
result = parse_review_output(response, "05_feature", "3", "session-1")
ASSERT len(result) == 1
ASSERT result[0].severity == "critical"
ASSERT result[0].description == "Missing edge case"
ASSERT result[0].requirement_ref == "05-REQ-1.1"
```

### TS-27-4: Parse Verifier JSON Output

**Requirement:** 27-REQ-3.2
**Type:** unit
**Description:** Verify that valid Verifier JSON output is parsed into
VerificationResult objects.

**Preconditions:**
- None.

**Input:**
- Agent response containing:
  ```json
  {"verdicts": [{"requirement_id": "05-REQ-1.1", "verdict": "PASS", "evidence": "All tests pass"}]}
  ```

**Expected:**
- List of one VerificationResult with requirement_id="05-REQ-1.1",
  verdict="PASS", evidence="All tests pass".

**Assertion pseudocode:**
```
result = parse_verification_output(response, "05_feature", "3", "session-1")
ASSERT len(result) == 1
ASSERT result[0].requirement_id == "05-REQ-1.1"
ASSERT result[0].verdict == "PASS"
```

### TS-27-5: Validate JSON Schema Rejects Invalid Blocks

**Requirement:** 27-REQ-3.3
**Type:** unit
**Description:** Verify that JSON blocks missing required fields are
discarded with a warning.

**Preconditions:**
- None.

**Input:**
- Agent response containing:
  ```json
  {"findings": [{"severity": "critical"}, {"severity": "major", "description": "Valid finding"}]}
  ```

**Expected:**
- Only the valid finding is returned. Warning logged for the invalid block.

**Assertion pseudocode:**
```
result = parse_review_output(response, "05_feature", "3", "session-1")
ASSERT len(result) == 1
ASSERT result[0].severity == "major"
```

### TS-27-6: Insert Findings with Supersession

**Requirement:** 27-REQ-4.1
**Type:** unit
**Description:** Verify that inserting findings supersedes existing active
records for the same (spec_name, task_group).

**Preconditions:**
- DuckDB with migration v2 applied.
- Two existing active findings for ("05_feature", "3").

**Input:**
- Insert one new finding for ("05_feature", "3").

**Expected:**
- Two existing findings have superseded_by set.
- One new finding has superseded_by IS NULL.

**Assertion pseudocode:**
```
insert_findings(conn, [old_finding_1, old_finding_2])
insert_findings(conn, [new_finding])
active = query_active_findings(conn, "05_feature", "3")
ASSERT len(active) == 1
ASSERT active[0].id == new_finding.id
superseded = conn.execute(
    "SELECT COUNT(*) FROM review_findings WHERE superseded_by IS NOT NULL"
).fetchone()[0]
ASSERT superseded == 2
```

### TS-27-7: Insert Verdicts with Supersession

**Requirement:** 27-REQ-4.2
**Type:** unit
**Description:** Verify that inserting verdicts supersedes existing active
records for the same (spec_name, task_group).

**Preconditions:**
- DuckDB with migration v2 applied.
- One existing active verdict for ("05_feature", "3").

**Input:**
- Insert one new verdict for ("05_feature", "3").

**Expected:**
- Existing verdict has superseded_by set.
- New verdict has superseded_by IS NULL.

**Assertion pseudocode:**
```
insert_verdicts(conn, [old_verdict])
insert_verdicts(conn, [new_verdict])
active = query_active_verdicts(conn, "05_feature", "3")
ASSERT len(active) == 1
ASSERT active[0].id == new_verdict.id
```

### TS-27-8: Causal Links Created on Supersession

**Requirement:** 27-REQ-4.3
**Type:** unit
**Description:** Verify that supersession creates causal links from old
records to new records.

**Preconditions:**
- DuckDB with migration v2 and fact_causes table.
- One existing finding.

**Input:**
- Insert new finding that supersedes the existing one.

**Expected:**
- A causal link exists from old finding ID to new finding ID.

**Assertion pseudocode:**
```
insert_findings(conn, [old_finding])
insert_findings(conn, [new_finding])
links = conn.execute(
    "SELECT * FROM fact_causes WHERE cause_id = ? AND effect_id = ?",
    [str(old_finding.id), str(new_finding.id)]
).fetchall()
ASSERT len(links) == 1
```

### TS-27-9: Render Review Context from DB

**Requirement:** 27-REQ-5.1
**Type:** unit
**Description:** Verify that active findings are rendered as a markdown
section matching the expected format.

**Preconditions:**
- DuckDB with two active findings: one critical, one minor.

**Input:**
- `render_review_context(conn, "05_feature")`

**Expected:**
- Markdown string containing "## Skeptic Review", "### Critical Findings",
  the critical finding description, "### Minor Findings", the minor finding.

**Assertion pseudocode:**
```
md = render_review_context(conn, "05_feature")
ASSERT "## Skeptic Review" IN md
ASSERT "### Critical Findings" IN md
ASSERT "critical finding text" IN md
ASSERT "### Minor Findings" IN md
```

### TS-27-10: Render Verification Context from DB

**Requirement:** 27-REQ-5.2
**Type:** unit
**Description:** Verify that active verdicts are rendered as a markdown
table matching the expected format.

**Preconditions:**
- DuckDB with two active verdicts: one PASS, one FAIL.

**Input:**
- `render_verification_context(conn, "05_feature")`

**Expected:**
- Markdown string containing "## Verification Report", a table with
  Requirement/Status/Notes columns, and "Verdict: FAIL".

**Assertion pseudocode:**
```
md = render_verification_context(conn, "05_feature")
ASSERT "## Verification Report" IN md
ASSERT "| Requirement | Status | Notes |" IN md
ASSERT "PASS" IN md
ASSERT "FAIL" IN md
ASSERT "Verdict: FAIL" IN md
```

### TS-27-11: Rendered Format Matches Legacy

**Requirement:** 27-REQ-5.3
**Type:** unit
**Description:** Verify that rendered markdown structure matches the format
previously produced by Skeptic/Verifier templates.

**Preconditions:**
- DuckDB with representative findings covering all severity levels.

**Input:**
- `render_review_context(conn, "05_feature")`

**Expected:**
- Output contains severity-grouped sections in order: Critical, Major,
  Minor, Observations. Contains a Summary line with counts.

**Assertion pseudocode:**
```
md = render_review_context(conn, "05_feature")
sections = ["Critical Findings", "Major Findings", "Minor Findings", "Observations"]
for section in sections:
    ASSERT section IN md
ASSERT "Summary:" IN md
```

### TS-27-12: Converge Skeptic Records

**Requirement:** 27-REQ-6.1
**Type:** unit
**Description:** Verify that multi-instance skeptic convergence on
ReviewFinding records produces correct merged output.

**Preconditions:**
- Three sets of findings from three instances, with some overlap.

**Input:**
- `converge_skeptic_records(instance_findings, block_threshold=0)`

**Expected:**
- Union of unique findings. Critical findings appearing in >= 2 instances
  count toward blocking. blocked=True if threshold exceeded.

**Assertion pseudocode:**
```
merged, blocked = converge_skeptic_records(
    [instance_1_findings, instance_2_findings, instance_3_findings],
    block_threshold=0,
)
ASSERT len(merged) == expected_unique_count
ASSERT blocked == True  # critical in majority
```

### TS-27-13: Converge Verifier Records

**Requirement:** 27-REQ-6.2
**Type:** unit
**Description:** Verify that multi-instance verifier convergence on
VerificationResult records produces correct majority vote.

**Preconditions:**
- Three sets of verdicts from three instances.

**Input:**
- `converge_verifier_records(instance_verdicts)`

**Expected:**
- Each requirement's verdict is the majority vote across instances.

**Assertion pseudocode:**
```
merged = converge_verifier_records(
    [instance_1_verdicts, instance_2_verdicts, instance_3_verdicts],
)
req_1 = [v for v in merged if v.requirement_id == "05-REQ-1.1"][0]
ASSERT req_1.verdict == "PASS"  # 2/3 voted PASS
```

### TS-27-14: GitHub Issue Body from DB

**Requirement:** 27-REQ-7.1
**Type:** unit
**Description:** Verify that GitHub issue body is composed from active
critical findings in the DB.

**Preconditions:**
- DuckDB with active critical findings.

**Input:**
- Format issue body from `query_active_findings` results.

**Expected:**
- Issue body contains each critical finding's description.

**Assertion pseudocode:**
```
findings = query_active_findings(conn, "05_feature")
body = format_issue_body(findings)
ASSERT "critical finding text" IN body
```

### TS-27-15: Skeptic Template Contains JSON Instructions

**Requirement:** 27-REQ-8.1
**Type:** unit
**Description:** Verify that the updated Skeptic template instructs
structured JSON output.

**Preconditions:**
- Template file exists at expected path.

**Input:**
- Read `agent_fox/_templates/prompts/skeptic.md`.

**Expected:**
- Content contains JSON schema example with "findings" array, "severity",
  "description" fields.

**Assertion pseudocode:**
```
content = Path("agent_fox/_templates/prompts/skeptic.md").read_text()
ASSERT '"findings"' IN content
ASSERT '"severity"' IN content
ASSERT '"description"' IN content
```

### TS-27-16: Verifier Template Contains JSON Instructions

**Requirement:** 27-REQ-9.1
**Type:** unit
**Description:** Verify that the updated Verifier template instructs
structured JSON output.

**Preconditions:**
- Template file exists at expected path.

**Input:**
- Read `agent_fox/_templates/prompts/verifier.md`.

**Expected:**
- Content contains JSON schema example with "verdicts" array,
  "requirement_id", "verdict" fields.

**Assertion pseudocode:**
```
content = Path("agent_fox/_templates/prompts/verifier.md").read_text()
ASSERT '"verdicts"' IN content
ASSERT '"requirement_id"' IN content
ASSERT '"verdict"' IN content
```

### TS-27-17: Legacy Review File Migration

**Requirement:** 27-REQ-10.1
**Type:** integration
**Description:** Verify that an existing `review.md` file is migrated into
DB records when no DB records exist.

**Preconditions:**
- Spec directory with `review.md` containing two findings.
- Empty `review_findings` table.

**Input:**
- Call context assembly for the spec.

**Expected:**
- Two ReviewFinding records exist in DB after assembly.

**Assertion pseudocode:**
```
# Setup: write review.md with known findings
assemble_context_with_db(conn, spec_dir, ...)
findings = query_active_findings(conn, spec_name)
ASSERT len(findings) == 2
```

### TS-27-18: Legacy Verification File Migration

**Requirement:** 27-REQ-10.2
**Type:** integration
**Description:** Verify that an existing `verification.md` file is migrated
into DB records when no DB records exist.

**Preconditions:**
- Spec directory with `verification.md` containing three verdicts.
- Empty `verification_results` table.

**Input:**
- Call context assembly for the spec.

**Expected:**
- Three VerificationResult records exist in DB after assembly.

**Assertion pseudocode:**
```
assemble_context_with_db(conn, spec_dir, ...)
verdicts = query_active_verdicts(conn, spec_name)
ASSERT len(verdicts) == 3
```

## Edge Case Tests

### TS-27-E1: Migration Failure Raises Error

**Requirement:** 27-REQ-1.E1
**Type:** unit
**Description:** Verify that a failed migration raises KnowledgeStoreError.

**Preconditions:**
- DuckDB connection that will fail on CREATE TABLE (e.g., read-only).

**Input:**
- Attempt migration v2.

**Expected:**
- `KnowledgeStoreError` is raised.

**Assertion pseudocode:**
```
ASSERT_RAISES KnowledgeStoreError:
    apply_migration_v2(read_only_conn)
```

### TS-27-E2: Migration Already Applied Skips

**Requirement:** 27-REQ-2.E1
**Type:** unit
**Description:** Verify that running migration v2 twice succeeds silently.

**Preconditions:**
- DuckDB with migration v2 already applied.

**Input:**
- Run migration v2 again.

**Expected:**
- No error. Tables still exist with same schema.

**Assertion pseudocode:**
```
apply_migration_v2(conn)
apply_migration_v2(conn)  # second call
# No exception raised
columns = conn.execute("DESCRIBE review_findings").fetchall()
ASSERT len(columns) == 9
```

### TS-27-E3: No Valid JSON Returns Empty

**Requirement:** 27-REQ-3.E1
**Type:** unit
**Description:** Verify that an agent response with no valid JSON returns
an empty list.

**Preconditions:**
- None.

**Input:**
- Agent response: "I found several issues but here is my analysis in prose..."

**Expected:**
- Empty list returned. Warning logged.

**Assertion pseudocode:**
```
result = parse_review_output("no json here", "spec", "1", "s1")
ASSERT result == []
```

### TS-27-E4: Unknown Severity Normalized

**Requirement:** 27-REQ-3.E2
**Type:** unit
**Description:** Verify that unknown severity values are normalized to
"observation".

**Preconditions:**
- None.

**Input:**
- JSON with severity "HIGH".

**Expected:**
- Finding with severity "observation". Warning logged.

**Assertion pseudocode:**
```
response = '{"findings": [{"severity": "HIGH", "description": "test"}]}'
result = parse_review_output(response, "spec", "1", "s1")
ASSERT result[0].severity == "observation"
```

### TS-27-E5: No Records to Supersede

**Requirement:** 27-REQ-4.E1
**Type:** unit
**Description:** Verify that inserting findings with no prior records works
cleanly.

**Preconditions:**
- Empty review_findings table.

**Input:**
- Insert two findings.

**Expected:**
- Two active findings. No superseded records.

**Assertion pseudocode:**
```
insert_findings(conn, [finding_1, finding_2])
active = query_active_findings(conn, spec_name, task_group)
ASSERT len(active) == 2
superseded = conn.execute(
    "SELECT COUNT(*) FROM review_findings WHERE superseded_by IS NOT NULL"
).fetchone()[0]
ASSERT superseded == 0
```

### TS-27-E6: DB Unavailable Falls Back to File

**Requirement:** 27-REQ-5.E1
**Type:** unit
**Description:** Verify that context assembly falls back to reading review.md
when the knowledge store is unavailable.

**Preconditions:**
- No DuckDB connection (conn=None).
- Spec directory with review.md file.

**Input:**
- Assemble context with conn=None.

**Expected:**
- Context includes review content from the file.

**Assertion pseudocode:**
```
ctx = assemble_context(spec_dir, task_group, conn=None)
ASSERT "## Skeptic Review" IN ctx
```

### TS-27-E7: No Findings Omits Section

**Requirement:** 27-REQ-5.E2
**Type:** unit
**Description:** Verify that the review section is omitted when no active
findings exist.

**Preconditions:**
- Empty review_findings table.

**Input:**
- `render_review_context(conn, "05_feature")`

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
result = render_review_context(conn, "05_feature")
ASSERT result IS None
```

### TS-27-E8: Single Instance Skips Convergence

**Requirement:** 27-REQ-6.E1
**Type:** unit
**Description:** Verify that convergence with one instance returns records
directly.

**Preconditions:**
- One instance's findings.

**Input:**
- `converge_skeptic_records([single_instance_findings], block_threshold=0)`

**Expected:**
- Returns the single instance's findings unchanged.

**Assertion pseudocode:**
```
merged, blocked = converge_skeptic_records([findings], block_threshold=0)
ASSERT merged == findings
```

### TS-27-E9: Legacy Parse Failure Skips File

**Requirement:** 27-REQ-10.E1
**Type:** unit
**Description:** Verify that a malformed legacy review.md is skipped with
a warning.

**Preconditions:**
- Spec directory with malformed review.md (no parseable findings).

**Input:**
- Attempt legacy migration.

**Expected:**
- No records inserted. Warning logged. No exception raised.

**Assertion pseudocode:**
```
migrate_legacy_review(conn, spec_dir, spec_name)
findings = query_active_findings(conn, spec_name)
ASSERT len(findings) == 0
```

## Property Test Cases

### TS-27-P1: Supersession Completeness

**Property:** Property 1 from design.md
**Validates:** 27-REQ-4.1, 27-REQ-4.2
**Type:** property
**Description:** After any number of insert rounds for the same
(spec_name, task_group), only the latest round's records are active.

**For any:** Sequence of 1-5 insert rounds, each with 1-10 findings.
**Invariant:** Active record count equals the last round's count.

**Assertion pseudocode:**
```
FOR ANY rounds IN st.lists(st.lists(finding_strategy, min_size=1, max_size=10), min_size=1, max_size=5):
    for round in rounds:
        insert_findings(conn, round)
    active = query_active_findings(conn, spec_name, task_group)
    ASSERT len(active) == len(rounds[-1])
```

### TS-27-P2: Parse-Roundtrip Fidelity

**Property:** Property 2 from design.md
**Validates:** 27-REQ-3.1, 27-REQ-3.2
**Type:** property
**Description:** Valid JSON round-trips through parse without data loss.

**For any:** Finding with severity in VALID_SEVERITIES and non-empty
description.
**Invariant:** Parsed output matches input fields.

**Assertion pseudocode:**
```
FOR ANY severity IN VALID_SEVERITIES, description IN st.text(min_size=1):
    json_str = json.dumps({"findings": [{"severity": severity, "description": description}]})
    result = parse_review_output(json_str, "spec", "1", "s1")
    ASSERT result[0].severity == severity
    ASSERT result[0].description == description
```

### TS-27-P3: Context Rendering Determinism

**Property:** Property 3 from design.md
**Validates:** 27-REQ-5.1, 27-REQ-5.3
**Type:** property
**Description:** Rendering the same DB state produces identical output.

**For any:** Set of 1-20 findings with mixed severities.
**Invariant:** Two calls to render_review_context produce identical strings.

**Assertion pseudocode:**
```
FOR ANY findings IN st.lists(finding_strategy, min_size=1, max_size=20):
    insert_findings(conn, findings)
    md1 = render_review_context(conn, spec_name)
    md2 = render_review_context(conn, spec_name)
    ASSERT md1 == md2
```

### TS-27-P4: Convergence Equivalence

**Property:** Property 4 from design.md
**Validates:** 27-REQ-6.1, 27-REQ-6.2
**Type:** property
**Description:** New convergence produces same results as old convergence
for equivalent input.

**For any:** 2-5 instances, each with 1-10 findings.
**Invariant:** Merged findings and blocking decision match between old and
new implementations.

**Assertion pseudocode:**
```
FOR ANY instance_findings IN st.lists(...):
    old_findings = [[Finding(f.severity, f.description) for f in inst] for inst in instance_findings]
    old_merged, old_blocked = converge_skeptic(old_findings, threshold)
    new_merged, new_blocked = converge_skeptic_records(instance_findings, threshold)
    ASSERT old_blocked == new_blocked
    ASSERT len(old_merged) == len(new_merged)
```

### TS-27-P5: Severity Normalization

**Property:** Property 5 from design.md
**Validates:** 27-REQ-3.3, 27-REQ-3.E2
**Type:** property
**Description:** All parsed findings have valid severities.

**For any:** String severity value (including garbage).
**Invariant:** Parsed severity is in VALID_SEVERITIES.

**Assertion pseudocode:**
```
FOR ANY severity IN st.text(min_size=1, max_size=50):
    json_str = json.dumps({"findings": [{"severity": severity, "description": "test"}]})
    result = parse_review_output(json_str, "spec", "1", "s1")
    IF len(result) > 0:
        ASSERT result[0].severity IN VALID_SEVERITIES
```

### TS-27-P6: Migration Idempotency

**Property:** Property 6 from design.md
**Validates:** 27-REQ-1.2, 27-REQ-2.2, 27-REQ-2.E1
**Type:** property
**Description:** Running migration multiple times produces same schema.

**For any:** Number of migration runs (1-5).
**Invariant:** Table schemas are identical after each run.

**Assertion pseudocode:**
```
FOR ANY n_runs IN st.integers(min_value=1, max_value=5):
    for _ in range(n_runs):
        apply_migration_v2(conn)
    rf_cols = conn.execute("DESCRIBE review_findings").fetchall()
    vr_cols = conn.execute("DESCRIBE verification_results").fetchall()
    ASSERT len(rf_cols) == 9
    ASSERT len(vr_cols) == 9
```

### TS-27-P7: Fallback Correctness

**Property:** Property 7 from design.md
**Validates:** 27-REQ-5.E1, 27-REQ-10.1
**Type:** property
**Description:** Context always includes review content when available
(from DB or file fallback).

**For any:** Spec with review.md and/or DB findings.
**Invariant:** Context contains review content.

**Assertion pseudocode:**
```
# This is better tested as an integration test with specific scenarios
# rather than property-based, since it involves file I/O
FOR ANY has_db IN st.booleans(), has_file IN st.booleans():
    ASSUME has_db OR has_file
    ctx = assemble_context_with_db(conn_or_none, spec_dir, ...)
    ASSERT "Skeptic Review" IN ctx OR "review" IN ctx.lower()
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 27-REQ-1.1 | TS-27-1 | unit |
| 27-REQ-1.2 | TS-27-P6 | property |
| 27-REQ-1.E1 | TS-27-E1 | unit |
| 27-REQ-2.1 | TS-27-2 | unit |
| 27-REQ-2.2 | TS-27-P6 | property |
| 27-REQ-2.E1 | TS-27-E2 | unit |
| 27-REQ-3.1 | TS-27-3, TS-27-P2 | unit, property |
| 27-REQ-3.2 | TS-27-4, TS-27-P2 | unit, property |
| 27-REQ-3.3 | TS-27-5, TS-27-P5 | unit, property |
| 27-REQ-3.E1 | TS-27-E3 | unit |
| 27-REQ-3.E2 | TS-27-E4, TS-27-P5 | unit, property |
| 27-REQ-4.1 | TS-27-6, TS-27-P1 | unit, property |
| 27-REQ-4.2 | TS-27-7, TS-27-P1 | unit, property |
| 27-REQ-4.3 | TS-27-8 | unit |
| 27-REQ-4.E1 | TS-27-E5 | unit |
| 27-REQ-5.1 | TS-27-9, TS-27-P3 | unit, property |
| 27-REQ-5.2 | TS-27-10 | unit |
| 27-REQ-5.3 | TS-27-11, TS-27-P3 | unit, property |
| 27-REQ-5.E1 | TS-27-E6, TS-27-P7 | unit, property |
| 27-REQ-5.E2 | TS-27-E7 | unit |
| 27-REQ-6.1 | TS-27-12, TS-27-P4 | unit, property |
| 27-REQ-6.2 | TS-27-13, TS-27-P4 | unit, property |
| 27-REQ-6.3 | TS-27-12 | unit |
| 27-REQ-6.E1 | TS-27-E8 | unit |
| 27-REQ-7.1 | TS-27-14 | unit |
| 27-REQ-7.2 | TS-27-14 | unit |
| 27-REQ-7.E1 | TS-27-E6 | unit |
| 27-REQ-8.1 | TS-27-15 | unit |
| 27-REQ-8.2 | TS-27-15 | unit |
| 27-REQ-8.E1 | TS-27-15 | unit |
| 27-REQ-9.1 | TS-27-16 | unit |
| 27-REQ-9.2 | TS-27-16 | unit |
| 27-REQ-9.E1 | TS-27-16 | unit |
| 27-REQ-10.1 | TS-27-17, TS-27-P7 | integration, property |
| 27-REQ-10.2 | TS-27-18 | integration |
| 27-REQ-10.E1 | TS-27-E9 | unit |
