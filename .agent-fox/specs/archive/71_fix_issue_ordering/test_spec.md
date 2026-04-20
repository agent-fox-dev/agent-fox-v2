# Test Specification: Fix Issue Ordering and Dependency Detection

## Overview

Tests cover four layers: base ordering, explicit reference parsing, AI batch
triage, and post-fix staleness checks. All AI and platform interactions are
mocked. Property tests verify graph invariants across generated inputs.

## Test Cases

### TS-71-1: Issues fetched in ascending order

**Requirement:** 71-REQ-1.1
**Type:** unit
**Description:** Verify `list_issues_by_label` is called with `direction="asc"`.

**Preconditions:**
- Mock platform with 3 issues (#10, #20, #30)

**Input:**
- Call `_run_issue_check()`

**Expected:**
- Platform called with `sort="created"`, `direction="asc"`

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT platform.list_issues_by_label.called_with(direction="asc")
```

### TS-71-2: Default order is ascending issue number

**Requirement:** 71-REQ-1.2
**Type:** unit
**Description:** With no dependency info, issues processed lowest-number first.

**Preconditions:**
- 2 issues (#30, #10) returned from platform (pre-sorted or not)
- No explicit references, batch < 3 so no AI triage

**Input:**
- Call `_run_issue_check()`

**Expected:**
- Issue #10 processed before #30

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT process_fix_calls == [#10, #30]
```

### TS-71-3: Explicit text references parsed

**Requirement:** 71-REQ-2.1
**Type:** unit
**Description:** Dependency hints in issue body produce edges.

**Preconditions:**
- Issue #20 body contains "depends on #10"
- Both #10 and #20 are in the batch

**Input:**
- `parse_text_references([issue_10, issue_20])`

**Expected:**
- One edge: `DependencyEdge(from_issue=10, to_issue=20, source="explicit")`

**Assertion pseudocode:**
```
edges = parse_text_references([issue_10, issue_20])
ASSERT len(edges) == 1
ASSERT edges[0].from_issue == 10
ASSERT edges[0].to_issue == 20
ASSERT edges[0].source == "explicit"
```

### TS-71-4: GitHub relationships incorporated

**Requirement:** 71-REQ-2.2
**Type:** unit
**Description:** GitHub blocks/is-blocked-by metadata produces edges.

**Preconditions:**
- Mock platform returns relationship: #10 blocks #20

**Input:**
- `fetch_github_relationships(platform, [issue_10, issue_20])`

**Expected:**
- One edge: `DependencyEdge(from_issue=10, to_issue=20, source="github")`

**Assertion pseudocode:**
```
edges = await fetch_github_relationships(platform, issues)
ASSERT len(edges) == 1
ASSERT edges[0].source == "github"
```

### TS-71-5: Multiple text patterns recognized

**Requirement:** 71-REQ-2.3
**Type:** unit
**Description:** All four text patterns are matched case-insensitively.

**Preconditions:**
- Issue bodies with "Depends on #1", "BLOCKED BY #2", "after #3", "Requires #4"
- All referenced issues in batch

**Input:**
- `parse_text_references(issues)`

**Expected:**
- 4 edges extracted

**Assertion pseudocode:**
```
edges = parse_text_references(issues)
ASSERT len(edges) == 4
to_issues = {e.to_issue for e in edges}
ASSERT to_issues contains the issues with the dependency text
```

### TS-71-6: AI triage triggered for batch >= 3

**Requirement:** 71-REQ-3.1
**Type:** unit
**Description:** AI triage is called when batch has 3+ issues.

**Preconditions:**
- 3 issues in batch
- Mock AI triage returning valid TriageResult

**Input:**
- Call `_run_issue_check()`

**Expected:**
- `run_batch_triage` called once

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT run_batch_triage.call_count == 1
```

### TS-71-7: AI triage uses ADVANCED tier

**Requirement:** 71-REQ-3.2
**Type:** unit
**Description:** Triage session uses ADVANCED model tier.

**Preconditions:**
- Mock session runner capturing model tier

**Input:**
- `run_batch_triage(issues, edges, config)`

**Expected:**
- Session created with ADVANCED tier

**Assertion pseudocode:**
```
result = await run_batch_triage(issues, edges, config)
ASSERT session_runner.model_tier == "ADVANCED"
```

### TS-71-8: AI triage returns order, edges, supersession

**Requirement:** 71-REQ-3.3
**Type:** unit
**Description:** TriageResult contains all three fields.

**Preconditions:**
- Mock AI returning valid JSON response

**Input:**
- `run_batch_triage(issues, [], config)`

**Expected:**
- TriageResult with processing_order, edges, supersession_pairs

**Assertion pseudocode:**
```
result = await run_batch_triage(issues, [], config)
ASSERT isinstance(result.processing_order, list)
ASSERT isinstance(result.edges, list)
ASSERT isinstance(result.supersession_pairs, list)
```

### TS-71-9: Explicit edges override AI edges on conflict

**Requirement:** 71-REQ-3.4
**Type:** unit
**Description:** When AI says A->B but explicit says B->A, explicit wins.

**Preconditions:**
- Explicit edge: #10 before #20
- AI edge: #20 before #10

**Input:**
- `merge_edges(explicit_edges, ai_edges)`
- `build_graph(issues, merged)`

**Expected:**
- #10 processed before #20

**Assertion pseudocode:**
```
merged = merge_edges(
    [DependencyEdge(10, 20, "explicit", ...)],
    [DependencyEdge(20, 10, "ai", ...)]
)
order = build_graph(issues, merged)
ASSERT order.index(10) < order.index(20)
```

### TS-71-10: AI triage skipped for batch < 3

**Requirement:** 71-REQ-3.5
**Type:** unit
**Description:** For 1-2 issues, no AI triage is invoked.

**Preconditions:**
- 2 issues in batch

**Input:**
- Call `_run_issue_check()`

**Expected:**
- `run_batch_triage` NOT called

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT run_batch_triage.call_count == 0
```

### TS-71-11: Topological sort produces valid order

**Requirement:** 71-REQ-4.1
**Type:** unit
**Description:** Dependencies are respected in output order.

**Preconditions:**
- Issues #10, #20, #30
- Edges: #10 -> #20, #20 -> #30

**Input:**
- `build_graph(issues, edges)`

**Expected:**
- Order: [10, 20, 30]

**Assertion pseudocode:**
```
order = build_graph(issues, edges)
ASSERT order == [10, 20, 30]
```

### TS-71-12: Tie-breaking by issue number

**Requirement:** 71-REQ-4.2
**Type:** unit
**Description:** Independent issues sorted by ascending number.

**Preconditions:**
- Issues #30, #10, #20 with no edges

**Input:**
- `build_graph(issues, [])`

**Expected:**
- Order: [10, 20, 30]

**Assertion pseudocode:**
```
order = build_graph(issues, [])
ASSERT order == [10, 20, 30]
```

### TS-71-13: Cycle detected and broken

**Requirement:** 71-REQ-4.3
**Type:** unit
**Description:** Cycles are broken at the edge pointing to the oldest issue.

**Preconditions:**
- Issues #10, #20
- Edges: #10 -> #20, #20 -> #10

**Input:**
- `build_graph(issues, edges)`

**Expected:**
- Valid order returned (no cycle)
- #10 first (oldest)
- Warning logged

**Assertion pseudocode:**
```
order = build_graph(issues, edges)
ASSERT order[0] == 10
ASSERT len(order) == 2
ASSERT warning logged containing "cycle"
```

### TS-71-14: Post-fix staleness check runs

**Requirement:** 71-REQ-5.1
**Type:** unit
**Description:** After a successful fix, remaining issues are evaluated.

**Preconditions:**
- 3 issues, #10 fixed successfully
- Mock staleness AI returning #20 as obsolete

**Input:**
- Process fix for #10, then staleness check

**Expected:**
- `check_staleness` called with remaining issues [#20, #30]

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT check_staleness.called
ASSERT check_staleness.call_args.remaining == [issue_20, issue_30]
```

### TS-71-15: Staleness verifies with GitHub API

**Requirement:** 71-REQ-5.2
**Type:** unit
**Description:** Staleness check re-fetches issues from GitHub.

**Preconditions:**
- Mock staleness AI says #20 is obsolete
- Mock platform re-fetch confirms #20 still open

**Input:**
- `check_staleness(fixed_issue, remaining, diff, config)`

**Expected:**
- Platform `list_issues_by_label` called to verify

**Assertion pseudocode:**
```
result = await check_staleness(...)
ASSERT platform.list_issues_by_label.called
```

### TS-71-16: Obsolete issues closed with comment

**Requirement:** 71-REQ-5.3
**Type:** unit
**Description:** Issues determined obsolete are closed on GitHub.

**Preconditions:**
- Staleness identifies #20 as obsolete after fixing #10

**Input:**
- Process staleness result

**Expected:**
- `close_issue(20, "Resolved by fix for #10")` called

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT platform.close_issue.called_with(20, contains("#10"))
```

### TS-71-17: Obsolete issues removed from queue

**Requirement:** 71-REQ-5.4
**Type:** unit
**Description:** Closed issues are not processed in subsequent iterations.

**Preconditions:**
- Issues #10, #20, #30; staleness after #10 closes #20

**Input:**
- Call `_run_issue_check()`

**Expected:**
- `_process_fix` called for #10 and #30 only, not #20

**Assertion pseudocode:**
```
engine._run_issue_check()
processed = [call.args[0].number for call in process_fix.calls]
ASSERT processed == [10, 30]
```

### TS-71-18: Resolved order logged at INFO

**Requirement:** 71-REQ-6.1
**Type:** unit
**Description:** Processing order is logged after triage.

**Preconditions:**
- 3 issues with AI triage

**Input:**
- Call `_run_issue_check()`

**Expected:**
- INFO log containing processing order

**Assertion pseudocode:**
```
with caplog.at_level(INFO):
    engine._run_issue_check()
ASSERT any("processing order" in r.message for r in caplog.records)
```

### TS-71-19: Staleness closure emits audit event

**Requirement:** 71-REQ-6.2
**Type:** unit
**Description:** Audit event emitted when an issue is closed as obsolete.

**Preconditions:**
- Staleness closes #20 after fixing #10

**Input:**
- Process staleness result

**Expected:**
- Audit event with closed_issue=20, fixed_by=10

**Assertion pseudocode:**
```
engine._run_issue_check()
ASSERT audit_event emitted with type "night_shift.issue_obsolete"
ASSERT event.payload["closed_issue"] == 20
ASSERT event.payload["fixed_by"] == 10
```

### TS-71-20: Cycle break logged at WARNING

**Requirement:** 71-REQ-6.3
**Type:** unit
**Description:** Cycle detection and break logged as warning.

**Preconditions:**
- Circular dependency between #10 and #20

**Input:**
- `build_graph(issues, cyclic_edges)`

**Expected:**
- WARNING log mentioning cycle members

**Assertion pseudocode:**
```
with caplog.at_level(WARNING):
    build_graph(issues, cyclic_edges)
ASSERT any("cycle" in r.message for r in caplog.records)
```

## Property Test Cases

### TS-71-P1: Base Ordering Invariant

**Property:** Property 1 from design.md
**Validates:** 71-REQ-1.2, 71-REQ-4.E1
**Type:** property
**Description:** With no edges, order is ascending issue number.

**For any:** list of N issue numbers (1 <= N <= 20), no edges
**Invariant:** `build_graph(issues, []) == sorted(issue_numbers)`

**Assertion pseudocode:**
```
FOR ANY issue_nums IN st.lists(st.integers(1, 1000), min_size=1, max_size=20, unique=True):
    issues = [make_issue(n) for n in issue_nums]
    order = build_graph(issues, [])
    ASSERT order == sorted(issue_nums)
```

### TS-71-P2: Dependency Respect Invariant

**Property:** Property 2 from design.md
**Validates:** 71-REQ-4.1
**Type:** property
**Description:** Every edge is respected in the output order.

**For any:** acyclic set of edges over N issues
**Invariant:** for every edge (A -> B), A appears before B in order

**Assertion pseudocode:**
```
FOR ANY issues, edges IN acyclic_graph_strategy():
    order = build_graph(issues, edges)
    FOR edge IN edges:
        ASSERT order.index(edge.from_issue) < order.index(edge.to_issue)
```

### TS-71-P3: Explicit Edge Precedence

**Property:** Property 3 from design.md
**Validates:** 71-REQ-3.4
**Type:** property
**Description:** Explicit edges always win over AI edges.

**For any:** pair of conflicting edges (explicit A->B, AI B->A)
**Invariant:** merged result contains A->B, not B->A

**Assertion pseudocode:**
```
FOR ANY a, b IN st.integers(1, 1000) where a != b:
    explicit = [DependencyEdge(a, b, "explicit", "")]
    ai = [DependencyEdge(b, a, "ai", "")]
    merged = merge_edges(explicit, ai)
    ASSERT any(e.from_issue == a and e.to_issue == b for e in merged)
    ASSERT not any(e.from_issue == b and e.to_issue == a for e in merged)
```

### TS-71-P4: Cycle Resolution Produces Valid Order

**Property:** Property 4 from design.md
**Validates:** 71-REQ-4.3, 71-REQ-2.E2
**Type:** property
**Description:** Any cyclic graph produces a valid total order after breaking.

**For any:** set of edges (possibly cyclic) over N issues
**Invariant:** `build_graph` returns a permutation of all issue numbers

**Assertion pseudocode:**
```
FOR ANY issues, edges IN graph_strategy():
    order = build_graph(issues, edges)
    ASSERT set(order) == set(issue_numbers)
    ASSERT len(order) == len(issue_numbers)
```

### TS-71-P5: Triage Fallback Produces Valid Order

**Property:** Property 5 from design.md
**Validates:** 71-REQ-3.E1
**Type:** property
**Description:** When triage fails, a valid order is still produced.

**For any:** batch of N issues (N >= 3), triage raises exception
**Invariant:** processing order is a valid permutation of issue numbers

**Assertion pseudocode:**
```
FOR ANY issues IN issue_batch_strategy(min_size=3):
    mock triage to raise TriageError
    order = resolve_order(issues, config)
    ASSERT set(order) == set(i.number for i in issues)
```

### TS-71-P6: Staleness Removal

**Property:** Property 6 from design.md
**Validates:** 71-REQ-5.4
**Type:** property
**Description:** Obsolete issues never appear in subsequent processing.

**For any:** batch where staleness marks K issues as obsolete
**Invariant:** no obsolete issue appears in the post-staleness processing list

**Assertion pseudocode:**
```
FOR ANY batch, obsolete_set IN staleness_strategy():
    remaining = apply_staleness(batch, obsolete_set)
    FOR issue IN obsolete_set:
        ASSERT issue not in remaining
```

### TS-71-P7: Batch Size Gate

**Property:** Property 7 from design.md
**Validates:** 71-REQ-3.5
**Type:** property
**Description:** AI triage never invoked for batches < 3.

**For any:** batch of 1-2 issues
**Invariant:** triage function not called

**Assertion pseudocode:**
```
FOR ANY issues IN issue_batch_strategy(min_size=1, max_size=2):
    mock triage
    resolve_order(issues, config)
    ASSERT triage.call_count == 0
```

## Edge Case Tests

### TS-71-E1: Reference to issue not in batch

**Requirement:** 71-REQ-2.E1
**Type:** unit
**Description:** References to issues outside the batch are ignored.

**Preconditions:**
- Issue #10 body says "depends on #99"
- Only #10 and #20 in batch

**Input:**
- `parse_text_references([issue_10, issue_20])`

**Expected:**
- No edges returned (99 not in batch)

**Assertion pseudocode:**
```
edges = parse_text_references([issue_10, issue_20])
ASSERT len(edges) == 0
```

### TS-71-E2: Explicit reference cycle

**Requirement:** 71-REQ-2.E2
**Type:** unit
**Description:** Cycle from explicit refs broken at oldest issue.

**Preconditions:**
- #10 body: "depends on #20"
- #20 body: "depends on #10"

**Input:**
- Parse and build graph

**Expected:**
- Valid order, #10 first, warning logged

**Assertion pseudocode:**
```
edges = parse_text_references([issue_10, issue_20])
order = build_graph(issues, edges)
ASSERT order[0] == 10
```

### TS-71-E3: AI triage API failure

**Requirement:** 71-REQ-3.E1
**Type:** unit
**Description:** Triage failure falls back to refs + number order.

**Preconditions:**
- 3 issues, mock triage raises RuntimeError
- No explicit refs

**Input:**
- Call `_run_issue_check()`

**Expected:**
- Issues processed in [lowest, middle, highest] order
- Warning logged

**Assertion pseudocode:**
```
mock triage to raise RuntimeError
engine._run_issue_check()
ASSERT process_fix_calls == [10, 20, 30]
ASSERT warning logged containing "triage failed"
```

### TS-71-E4: AI order violates explicit edges

**Requirement:** 71-REQ-3.E2
**Type:** unit
**Description:** Explicit edges correct an invalid AI ordering.

**Preconditions:**
- Explicit edge: #10 before #20
- AI suggests order [20, 10, 30]

**Input:**
- Merge and sort

**Expected:**
- #10 before #20 in final order

**Assertion pseudocode:**
```
order = resolve_with_ai_and_explicit(ai_order=[20,10,30], explicit=[10->20])
ASSERT order.index(10) < order.index(20)
```

### TS-71-E5: Empty dependency graph

**Requirement:** 71-REQ-4.E1
**Type:** unit
**Description:** No edges produces issue-number order.

**Preconditions:**
- 3 issues, no edges of any kind

**Input:**
- `build_graph(issues, [])`

**Expected:**
- Ascending issue number order

**Assertion pseudocode:**
```
order = build_graph([issue_30, issue_10, issue_20], [])
ASSERT order == [10, 20, 30]
```

### TS-71-E6: Staleness AI failure

**Requirement:** 71-REQ-5.E1
**Type:** unit
**Description:** AI failure falls back to GitHub API verification only.

**Preconditions:**
- Staleness AI raises exception
- GitHub re-fetch shows #20 was closed

**Input:**
- `check_staleness(...)`

**Expected:**
- #20 marked obsolete (from GitHub check)
- Processing continues

**Assertion pseudocode:**
```
mock staleness AI to raise
result = await check_staleness(...)
ASSERT 20 in result.obsolete_issues  # from GitHub verification
```

### TS-71-E7: Staleness GitHub re-fetch failure

**Requirement:** 71-REQ-5.E2
**Type:** unit
**Description:** GitHub failure logs warning, continues without removal.

**Preconditions:**
- Staleness AI says #20 is obsolete
- GitHub re-fetch raises IntegrationError

**Input:**
- `check_staleness(...)`

**Expected:**
- Warning logged
- No issues removed (conservative approach)

**Assertion pseudocode:**
```
mock platform re-fetch to raise
result = await check_staleness(...)
ASSERT result.obsolete_issues == []
ASSERT warning logged
```

### TS-71-E8: Failed fix skips staleness

**Requirement:** 71-REQ-5.E3
**Type:** unit
**Description:** Fix pipeline failure skips staleness check.

**Preconditions:**
- #10 fix raises exception

**Input:**
- Call `_run_issue_check()`

**Expected:**
- `check_staleness` NOT called after #10
- Processing continues to #20

**Assertion pseudocode:**
```
mock process_fix(#10) to raise
engine._run_issue_check()
ASSERT check_staleness not called after #10 failure
ASSERT process_fix called for #20
```

### TS-71-E9: Platform sort not supported

**Requirement:** 71-REQ-1.E1
**Type:** unit
**Description:** Local sort applied when platform ignores sort params.

**Preconditions:**
- Platform returns [#30, #10, #20] regardless of sort params

**Input:**
- Call `_run_issue_check()`

**Expected:**
- Issues processed in order [10, 20, 30]

**Assertion pseudocode:**
```
mock platform to return [#30, #10, #20]
engine._run_issue_check()
ASSERT process_fix_calls == [10, 20, 30]
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 71-REQ-1.1 | TS-71-1 | unit |
| 71-REQ-1.2 | TS-71-2 | unit |
| 71-REQ-1.E1 | TS-71-E9 | unit |
| 71-REQ-2.1 | TS-71-3 | unit |
| 71-REQ-2.2 | TS-71-4 | unit |
| 71-REQ-2.3 | TS-71-5 | unit |
| 71-REQ-2.E1 | TS-71-E1 | unit |
| 71-REQ-2.E2 | TS-71-E2 | unit |
| 71-REQ-3.1 | TS-71-6 | unit |
| 71-REQ-3.2 | TS-71-7 | unit |
| 71-REQ-3.3 | TS-71-8 | unit |
| 71-REQ-3.4 | TS-71-9 | unit |
| 71-REQ-3.5 | TS-71-10 | unit |
| 71-REQ-3.E1 | TS-71-E3 | unit |
| 71-REQ-3.E2 | TS-71-E4 | unit |
| 71-REQ-4.1 | TS-71-11 | unit |
| 71-REQ-4.2 | TS-71-12 | unit |
| 71-REQ-4.3 | TS-71-13 | unit |
| 71-REQ-4.E1 | TS-71-E5 | unit |
| 71-REQ-5.1 | TS-71-14 | unit |
| 71-REQ-5.2 | TS-71-15 | unit |
| 71-REQ-5.3 | TS-71-16 | unit |
| 71-REQ-5.4 | TS-71-17 | unit |
| 71-REQ-5.E1 | TS-71-E6 | unit |
| 71-REQ-5.E2 | TS-71-E7 | unit |
| 71-REQ-5.E3 | TS-71-E8 | unit |
| 71-REQ-6.1 | TS-71-18 | unit |
| 71-REQ-6.2 | TS-71-19 | unit |
| 71-REQ-6.3 | TS-71-20 | unit |
| Property 1 | TS-71-P1 | property |
| Property 2 | TS-71-P2 | property |
| Property 3 | TS-71-P3 | property |
| Property 4 | TS-71-P4 | property |
| Property 5 | TS-71-P5 | property |
| Property 6 | TS-71-P6 | property |
| Property 7 | TS-71-P7 | property |
