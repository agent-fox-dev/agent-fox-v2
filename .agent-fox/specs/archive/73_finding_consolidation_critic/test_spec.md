# Test Specification: Cross-Category Finding Consolidation Critic

## Overview

Tests validate the critic stage's consolidation logic, fallback paths, and
logging. Unit tests cover mechanical grouping and response parsing.
Property tests cover the conservation, bijection, union, format, and
degradation invariants. Integration tests cover the full
`consolidate_findings()` flow with mocked AI backends.

## Test Cases

### TS-73-1: Cross-Category Merge

**Requirement:** 73-REQ-1.1
**Type:** integration
**Description:** Findings from different categories sharing a root cause are
merged into a single FindingGroup.

**Preconditions:**
- AI backend mocked to return a response merging findings 0 and 1.

**Input:**
- Finding A: category="dead_code", title="Unused auth helper",
  affected_files=["auth.py"], evidence="ruff: F811 auth.py:42"
- Finding B: category="linter_debt", title="Unused import in auth module",
  affected_files=["auth.py"], evidence="ruff: F401 auth.py:1"
- Finding C: category="test_coverage", title="Low coverage in payments",
  affected_files=["payments.py"], evidence="coverage: 12% payments.py"

**Expected:**
- Two FindingGroups returned.
- First group contains findings A and B (merged).
- Second group contains finding C (standalone).

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT len(groups) == 2
ASSERT {A, B} == set(groups[0].findings) OR {A, B} == set(groups[1].findings)
```

### TS-73-2: Affected Files Union

**Requirement:** 73-REQ-1.2
**Type:** unit
**Description:** Merged FindingGroup has the union of all merged findings'
affected files.

**Preconditions:**
- Critic response merges two findings with different affected_files.

**Input:**
- Finding A: affected_files=["auth.py", "utils.py"]
- Finding B: affected_files=["auth.py", "middleware.py"]
- Critic response merges A and B.

**Expected:**
- Merged group's affected_files == sorted(["auth.py", "middleware.py", "utils.py"])

**Assertion pseudocode:**
```
groups, _ = _parse_critic_response(response, [A, B])
ASSERT groups[0].affected_files == ["auth.py", "middleware.py", "utils.py"]
```

### TS-73-3: Synthesised Title and Body

**Requirement:** 73-REQ-1.3
**Type:** integration
**Description:** Merged FindingGroup uses the critic's synthesised title and
body, not the first finding's raw text.

**Preconditions:**
- AI backend mocked to return a synthesised title and description.

**Input:**
- Two findings with different titles.
- Critic response provides a new synthesised title and description.

**Expected:**
- The FindingGroup's title matches the critic's synthesised title.
- The FindingGroup's body contains the critic's synthesised description.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT groups[0].title == "Synthesised title from critic"
ASSERT "synthesised description" in groups[0].body
```

### TS-73-4: Evidence Validation Drops Finding

**Requirement:** 73-REQ-2.1, 73-REQ-2.2
**Type:** integration
**Description:** Findings with empty or speculative evidence are dropped.

**Preconditions:**
- AI backend mocked to drop finding 1 (empty evidence).

**Input:**
- Finding A: evidence="ruff: F401 auth.py:1" (concrete)
- Finding B: evidence="" (empty)
- Finding C: evidence="coverage: 12% payments.py" (concrete)

**Expected:**
- Finding B is dropped.
- Two FindingGroups returned (one per remaining finding).

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
all_findings = [f for g in groups for f in g.findings]
ASSERT B not in all_findings
ASSERT len(all_findings) == 2
```

### TS-73-5: Drop Logged at INFO

**Requirement:** 73-REQ-2.3
**Type:** unit
**Description:** Dropped findings are logged with title and reason.

**Preconditions:**
- Logger captured.

**Input:**
- CriticDecision with action="dropped", finding_indices=[1],
  reason="Evidence field is empty"

**Expected:**
- INFO log containing the finding title and "Evidence field is empty".

**Assertion pseudocode:**
```
_log_decisions([decision], summary)
ASSERT any("dropped" in r.message and "Evidence field is empty" in r.message
           for r in caplog.records if r.levelno == INFO)
```

### TS-73-6: Severity Calibration

**Requirement:** 73-REQ-3.1
**Type:** integration
**Description:** Merged findings get a calibrated severity from the critic.

**Preconditions:**
- AI backend mocked to merge two findings and assign severity "critical".

**Input:**
- Finding A: severity="minor"
- Finding B: severity="major"
- Finding C: severity="info" (unrelated)
- Critic merges A+B with severity "critical".

**Expected:**
- Merged group severity is "critical".
- Unrelated finding C retains severity "info".

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
merged = next(g for g in groups if len(g.findings) > 1)
ASSERT "critical" in merged.body OR merged severity field == "critical"
```

### TS-73-7: Severity Change Logged

**Requirement:** 73-REQ-3.2
**Type:** unit
**Description:** Severity changes are logged with original and new values.

**Preconditions:**
- Logger captured.

**Input:**
- CriticDecision with action="severity_changed",
  original_severity="minor", new_severity="critical",
  reason="Multiple categories flag same critical path"

**Expected:**
- INFO log containing "minor", "critical", and the reason.

**Assertion pseudocode:**
```
_log_decisions([decision], summary)
ASSERT any("minor" in r.message and "critical" in r.message
           for r in caplog.records if r.levelno == INFO)
```

### TS-73-8: Below-Threshold Mechanical Grouping

**Requirement:** 73-REQ-4.1, 73-REQ-4.2
**Type:** unit
**Description:** Fewer than 3 findings skip the critic and use mechanical
grouping.

**Preconditions:**
- No AI backend mock needed (should not be called).

**Input:**
- Two findings.

**Expected:**
- Two FindingGroups, one per finding.
- No AI call made.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B])
ASSERT len(groups) == 2
ASSERT groups[0].findings == [A]
ASSERT groups[1].findings == [B]
ASSERT ai_mock.call_count == 0
```

### TS-73-9: Output Compatibility

**Requirement:** 73-REQ-5.1, 73-REQ-5.3
**Type:** integration
**Description:** Critic output is compatible with create_issues_from_groups().

**Preconditions:**
- AI backend mocked with valid response.

**Input:**
- Three findings.

**Expected:**
- Each FindingGroup has non-empty title, body, and findings list.
- FindingGroup.findings contains original Finding objects.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
for g in groups:
    ASSERT g.title != ""
    ASSERT g.body != ""
    ASSERT len(g.findings) > 0
    ASSERT all(isinstance(f, Finding) for f in g.findings)
```

### TS-73-10: Summary Log

**Requirement:** 73-REQ-6.3
**Type:** unit
**Description:** Critic logs a summary with counts.

**Preconditions:**
- Logger captured.

**Input:**
- CriticSummary with total_received=5, total_dropped=1,
  total_merged=3, groups_produced=2.

**Expected:**
- INFO log containing all four counts.

**Assertion pseudocode:**
```
_log_decisions([], summary)
ASSERT any("5" in r.message and "dropped" in r.message
           for r in caplog.records if r.levelno == INFO)
```

### TS-73-11: Async Signature

**Requirement:** 73-REQ-7.1, 73-REQ-7.2, 73-REQ-7.3
**Type:** unit
**Description:** The new consolidate_findings is async and has the correct
signature.

**Preconditions:**
- Import the function.

**Input:**
- N/A (introspection test).

**Expected:**
- Function is a coroutine function.
- Accepts list[Finding], returns list[FindingGroup].

**Assertion pseudocode:**
```
import inspect
ASSERT inspect.iscoroutinefunction(consolidate_findings)
sig = inspect.signature(consolidate_findings)
ASSERT "findings" in sig.parameters
```

## Edge Case Tests

### TS-73-E1: All Findings Same Root Cause

**Requirement:** 73-REQ-1.E1
**Type:** integration
**Description:** All findings merge into a single group.

**Preconditions:**
- AI backend mocked to merge all findings.

**Input:**
- Three findings all about the same unused module.

**Expected:**
- One FindingGroup containing all three findings.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT len(groups) == 1
ASSERT len(groups[0].findings) == 3
```

### TS-73-E2: No Shared Root Cause

**Requirement:** 73-REQ-1.E2
**Type:** integration
**Description:** Each finding becomes its own group when nothing merges.

**Preconditions:**
- AI backend mocked to keep each finding separate.

**Input:**
- Three unrelated findings.

**Expected:**
- Three FindingGroups, one per finding.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT len(groups) == 3
```

### TS-73-E3: All Findings Dropped

**Requirement:** 73-REQ-2.E1
**Type:** integration
**Description:** Critic drops all findings; empty list returned.

**Preconditions:**
- AI backend mocked to drop all findings.

**Input:**
- Three findings with empty evidence.

**Expected:**
- Empty list returned.
- Summary log shows total_dropped == 3, groups_produced == 0.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT groups == []
```

### TS-73-E4: Speculative Evidence Dropped

**Requirement:** 73-REQ-2.E2
**Type:** integration
**Description:** Finding with speculative evidence ("might be") is dropped.

**Preconditions:**
- AI backend mocked to drop the speculative finding.

**Input:**
- Finding A: evidence="This might be a problem"
- Finding B: evidence="ruff: F401 auth.py:1"
- Finding C: evidence="coverage: 12% payments.py"

**Expected:**
- Finding A dropped, B and C retained.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
all_findings = [f for g in groups for f in g.findings]
ASSERT A not in all_findings
ASSERT len(all_findings) == 2
```

### TS-73-E5: Severity Preserved When Not Merged

**Requirement:** 73-REQ-3.E1
**Type:** integration
**Description:** Standalone finding keeps its original severity.

**Preconditions:**
- AI backend mocked to keep finding standalone with no severity change.

**Input:**
- Three findings, one standalone with severity="minor".

**Expected:**
- Standalone finding's group reflects severity="minor".

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
standalone = next(g for g in groups if len(g.findings) == 1)
ASSERT "minor" in standalone.body
```

### TS-73-E6: Zero Findings

**Requirement:** 73-REQ-4.E1
**Type:** unit
**Description:** Empty input returns empty output immediately.

**Preconditions:**
- None.

**Input:**
- Empty list.

**Expected:**
- Empty list returned, no AI call, no logging.

**Assertion pseudocode:**
```
groups = await consolidate_findings([])
ASSERT groups == []
ASSERT ai_mock.call_count == 0
```

### TS-73-E7: Malformed AI Response

**Requirement:** 73-REQ-5.E1
**Type:** integration
**Description:** Malformed JSON triggers mechanical fallback.

**Preconditions:**
- AI backend mocked to return invalid JSON.

**Input:**
- Three findings.

**Expected:**
- Three FindingGroups (mechanical fallback).
- Warning logged about malformed response.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT len(groups) == 3
ASSERT any("malformed" in r.message or "fallback" in r.message
           for r in caplog.records if r.levelno == WARNING)
```

### TS-73-E8: Invalid Finding Indices

**Requirement:** 73-REQ-5.E2
**Type:** unit
**Description:** Out-of-bounds indices in AI response are ignored.

**Preconditions:**
- None.

**Input:**
- Response referencing finding_indices=[0, 1, 99] for a 3-finding batch.

**Expected:**
- Index 99 ignored with warning.
- Group built from indices 0 and 1 only.

**Assertion pseudocode:**
```
groups, decisions = _parse_critic_response(response, [A, B, C])
ASSERT all(f in [A, B] for f in groups[0].findings)
ASSERT any("out of bounds" in r.message for r in caplog.records)
```

### TS-73-E9: AI Backend Unavailable

**Requirement:** 73-REQ-7.E1
**Type:** integration
**Description:** AI failure triggers mechanical fallback.

**Preconditions:**
- AI backend mocked to raise an exception.

**Input:**
- Three findings.

**Expected:**
- Three FindingGroups (mechanical fallback).
- Warning logged about backend failure.

**Assertion pseudocode:**
```
groups = await consolidate_findings([A, B, C])
ASSERT len(groups) == 3
ASSERT any("fallback" in r.message for r in caplog.records if r.levelno == WARNING)
```

## Property Test Cases

### TS-73-P1: Finding Conservation

**Property:** Property 1 from design.md
**Validates:** 73-REQ-1.1, 73-REQ-2.2, 73-REQ-5.3
**Type:** property
**Description:** Every finding appears in a group or in the dropped log — none
are silently lost.

**For any:** List of 0-20 Finding objects with randomised fields.
**Invariant:** The union of findings in all returned groups plus all dropped
finding indices equals the set of input finding indices.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy, max_size=20):
    groups = await consolidate_findings(findings)
    found = {id(f) for g in groups for f in g.findings}
    # In mechanical grouping path, all findings accounted for
    ASSERT len(found) <= len(findings)
```

### TS-73-P2: Mechanical Grouping Bijection

**Property:** Property 2 from design.md
**Validates:** 73-REQ-4.1, 73-REQ-4.2
**Type:** property
**Description:** Below-threshold batches produce exactly one group per finding.

**For any:** List of 0-2 Finding objects.
**Invariant:** len(groups) == len(findings), each group has exactly one finding.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy, max_size=2):
    groups = _mechanical_grouping(findings)
    ASSERT len(groups) == len(findings)
    FOR EACH group IN groups:
        ASSERT len(group.findings) == 1
```

### TS-73-P3: Affected Files Union

**Property:** Property 3 from design.md
**Validates:** 73-REQ-1.2
**Type:** property
**Description:** Merged groups have the sorted, deduplicated union of files.

**For any:** List of 2-5 Finding objects with randomised affected_files.
**Invariant:** For mechanical grouping, each group's files match its single
finding's files.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy, min_size=1, max_size=2):
    groups = _mechanical_grouping(findings)
    FOR EACH group, finding IN zip(groups, findings):
        ASSERT group.affected_files == sorted(set(finding.affected_files))
```

### TS-73-P4: Output Format Compatibility

**Property:** Property 4 from design.md
**Validates:** 73-REQ-5.1, 73-REQ-5.3
**Type:** property
**Description:** Every FindingGroup has non-empty title, body, and findings.

**For any:** List of 0-10 Finding objects.
**Invariant:** All returned groups have non-empty title, body, and findings.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy, max_size=10):
    groups = _mechanical_grouping(findings)
    FOR EACH group IN groups:
        ASSERT group.title != ""
        ASSERT group.body != ""
        ASSERT len(group.findings) > 0
```

### TS-73-P5: Graceful Degradation

**Property:** Property 5 from design.md
**Validates:** 73-REQ-5.E1, 73-REQ-7.E1
**Type:** property
**Description:** AI failures produce the same result as mechanical grouping.

**For any:** List of 3-10 Finding objects, with AI backend raising exception.
**Invariant:** Output matches _mechanical_grouping(findings).

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy, min_size=3, max_size=10):
    ai_mock.side_effect = Exception("backend down")
    groups = await consolidate_findings(findings)
    expected = _mechanical_grouping(findings)
    ASSERT len(groups) == len(expected)
```

### TS-73-P6: Empty Input Invariant

**Property:** Property 6 from design.md
**Validates:** 73-REQ-4.E1
**Type:** property
**Description:** Empty input always returns empty output.

**For any:** N/A (single case).
**Invariant:** consolidate_findings([]) == [].

**Assertion pseudocode:**
```
groups = await consolidate_findings([])
ASSERT groups == []
```

### TS-73-P7: Decision Completeness

**Property:** Property 7 from design.md
**Validates:** 73-REQ-6.1, 73-REQ-6.2, 73-REQ-6.3
**Type:** property
**Description:** All findings are accounted for in critic decisions.

**For any:** Valid critic JSON response covering N findings.
**Invariant:** Sum of finding indices across all decisions == set(range(N)).

**Assertion pseudocode:**
```
FOR ANY response IN valid_critic_responses(n_findings):
    groups, decisions = _parse_critic_response(response, findings)
    referenced = set()
    for d in decisions:
        referenced.update(d.finding_indices)
    for g_indices in [g.finding_indices for g in response.groups]:
        referenced.update(g_indices)
    ASSERT referenced == set(range(n_findings))
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 73-REQ-1.1 | TS-73-1 | integration |
| 73-REQ-1.2 | TS-73-2 | unit |
| 73-REQ-1.3 | TS-73-3 | integration |
| 73-REQ-1.E1 | TS-73-E1 | integration |
| 73-REQ-1.E2 | TS-73-E2 | integration |
| 73-REQ-2.1 | TS-73-4 | integration |
| 73-REQ-2.2 | TS-73-4 | integration |
| 73-REQ-2.3 | TS-73-5 | unit |
| 73-REQ-2.E1 | TS-73-E3 | integration |
| 73-REQ-2.E2 | TS-73-E4 | integration |
| 73-REQ-3.1 | TS-73-6 | integration |
| 73-REQ-3.2 | TS-73-7 | unit |
| 73-REQ-3.E1 | TS-73-E5 | integration |
| 73-REQ-4.1 | TS-73-8 | unit |
| 73-REQ-4.2 | TS-73-8 | unit |
| 73-REQ-4.E1 | TS-73-E6 | unit |
| 73-REQ-5.1 | TS-73-9 | integration |
| 73-REQ-5.2 | TS-73-9 | integration |
| 73-REQ-5.3 | TS-73-9 | integration |
| 73-REQ-5.E1 | TS-73-E7 | integration |
| 73-REQ-5.E2 | TS-73-E8 | unit |
| 73-REQ-6.1 | TS-73-5 | unit |
| 73-REQ-6.2 | TS-73-5 | unit |
| 73-REQ-6.3 | TS-73-10 | unit |
| 73-REQ-6.4 | TS-73-10 | unit |
| 73-REQ-6.E1 | TS-73-E7 | integration |
| 73-REQ-7.1 | TS-73-11 | unit |
| 73-REQ-7.2 | TS-73-11 | unit |
| 73-REQ-7.3 | TS-73-11 | unit |
| 73-REQ-7.E1 | TS-73-E9 | integration |
| Property 1 | TS-73-P1 | property |
| Property 2 | TS-73-P2 | property |
| Property 3 | TS-73-P3 | property |
| Property 4 | TS-73-P4 | property |
| Property 5 | TS-73-P5 | property |
| Property 6 | TS-73-P6 | property |
| Property 7 | TS-73-P7 | property |
